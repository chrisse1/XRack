"""
Low-Level Zugriff auf das Audio-Interface für die Wiedergabe.
"""

import logging

import alsaaudio

from audio.audio_backend import WUNSCHFORMAT, formatname
from audio.geraetewache import GERAETEWACHE
from audio.channel_inserter import ChannelInserter
from audio.models import AudioDevice


class AudioPlaybackBackend:
    """Kommuniziert direkt mit ALSA (Wiedergabe)."""

    BYTES_PER_SAMPLE = 4

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        self.device: AudioDevice | None = None

        self._pcm = None

        self._rate = 0
        self._channels = 0
        self._native_channels = 0
        self._format = None
        self._inserter: ChannelInserter | None = None

    @property
    def opened(self) -> bool:
        """True, wenn ein PCM-Handle geöffnet ist."""
        return self._pcm is not None

    def open(
        self,
        device: AudioDevice,
        channels: int,
        rate: int,
        start_channel: int = 0,
        sample_format: int = WUNSCHFORMAT,
    ) -> bool:
        """
        Öffnet das Audiogerät für die Wiedergabe.

        Genau wie beim Aufnehmen wird auch hier immer mit der
        vollen, nativen Kanalzahl des Interfaces geöffnet. Die
        Quelle bringt ggf. weniger Kanäle mit (z.B. 2 für Stereo-
        Musik) - diese werden per ChannelInserter ab `start_channel`
        auf die Kanäle des Interfaces gelegt, alle übrigen Kanäle
        bleiben stumm. So landet z.B. eine Aufnahme wieder auf
        genau den Kanälen, auf denen sie aufgenommen wurde
        (start_channel=0), oder Musik auf frei wählbaren Kanälen
        (z.B. start_channel=16 für Kanal 17+18).

        `sample_format` ist wählbar (aber immer 4 Byte pro Sample,
        siehe BYTES_PER_SAMPLE). Die Vorgabe ist S32_LE, und zwar für
        alle drei Quellen: Musik kommt über ffmpeg als volles S32_LE,
        und die Aufnahmen liegen genauso vor - XRack schreibt in die
        Datei, was das Interface liefert, und das ist S32_LE
        (32-Bit-Container, siehe audio/audio_backend.py und
        writer/w64_writer.py).

        Hier stand als Vorgabe lange S24_LE, und nur der Soundcheck
        benutzte sie (Musik und Bluetooth geben S32_LE ausdrücklich
        mit). Das war falsch für die Daten, die dabei gespielt werden,
        und fiel nur nicht auf, weil die X-Serie S24_LE über USB
        ohnehin nicht anbietet: ALSA nahm S32_LE, und es klang richtig.
        Auf einem Interface, das S24_LE annimmt, hätte derselbe
        Soundcheck aus den unteren 24 Bit gelesen - also aus dem
        Rauschen.
        """

        self.device = device

        self._rate = rate
        self._native_channels = device.channels
        self._channels = channels
        self._format = sample_format

        self._inserter = ChannelInserter(
            input_channels=self._channels,
            output_channels=self._native_channels,
            start_channel=start_channel,
        )

        #
        # Das Öffnen hält den GIL: Weder snd_pcm_open noch die
        # Aushandlung der Hardware-Parameter geben ihn frei, und
        # XRack löst fünf solcher Aushandlungen aus (PCM() und
        # die vier Setter). Solange das läuft, läuft in diesem
        # Prozess KEIN Python - auch der Webserver nicht.
        # Begründung und Quellenlage: audio/geraetewache.py.
        #
        # Gemessen wird es deshalb, statt es zu vermuten.
        #
        with GERAETEWACHE.arbeit(f"Wiedergabegerät öffnen: {device.id}"):

            try:

                self._pcm = alsaaudio.PCM(

                    type=alsaaudio.PCM_PLAYBACK,

                    mode=alsaaudio.PCM_NORMAL,

                    device=device.id,

                )

                actual_rate = self._pcm.setrate(
                    self._rate
                )

                if actual_rate and actual_rate != self._rate:
                    self.logger.warning(
                        "ALSA hat eine andere Samplerate akzeptiert als "
                        "angefordert: gefordert %d Hz, gemeldet %d Hz.",
                        self._rate,
                        actual_rate,
                    )

                self._pcm.setchannels(
                    self._native_channels
                )

                actual_format = self._pcm.setformat(
                    self._format
                )

                if actual_format is not None and actual_format != self._format:

                    gefordert = formatname(self._format)

                    self._format = actual_format

                    self.logger.error(
                        "Das Interface spielt %s statt %s. XRack liefert vier "
                        "Byte je Wert mit 2^31 Vollausschlag - die Wiedergabe "
                        "ist damit nicht verlaesslich. Das Geraet bietet an: "
                        "%s.",
                        formatname(actual_format),
                        gefordert,
                        ", ".join(device.formats) or "unbekannt",
                    )

                self._pcm.setperiodsize(1024)

                #
                # Damit aus gezählten Blöcken Sekunden Ton werden.
                #
                GERAETEWACHE.blockdauer_melden(1024, self._rate)

                self.logger.info(
                    "ALSA Wiedergabe geöffnet: %s | Hardware: %d Ch | Datei: %d Ch | %d Hz",
                    device.id,
                    self._native_channels,
                    self._channels,
                    self._rate,
                )

                return True

            except Exception as exc:

                self.logger.exception(
                    "ALSA Wiedergabe konnte nicht geöffnet werden: %s",
                    exc,
                )

                self._pcm = None

                return False

    def write(self, data: bytes) -> None:
        """
        Schreibt einen Puffer an das Wiedergabegerät.
        """

        if self._pcm is None:
            return

        self._pcm.write(
            self._inserter.insert(data)
        )

        #
        # Der Puls: Jeder Block, der hinausgegangen ist, wird gezählt.
        # Über einen Stillstand hinweg sagt die Differenz, ob in dieser
        # Zeit Ton geflossen ist - und damit, ob Python lief (siehe
        # audio/geraetewache.py).
        #
        GERAETEWACHE.block_geschrieben()

    def close(self) -> None:
        """
        Schließt das Wiedergabegerät.
        """

        #
        # Der Gerätename muss VOR dem Schließen gesichert werden -
        # danach ist self.device leer.
        #
        geraetename = self.device.id if self.device else "?"

        if self._pcm is not None:

            #
            # Auch das Schließen hält den GIL: close() gibt ihn zwar für
            # snd_pcm_drain() frei, für snd_pcm_close() aber nicht
            # (siehe audio/geraetewache.py). Das ist die zweite Hälfte
            # des Befunds vom Gerät - es klemmt beim Starten UND beim
            # Stoppen.
            #
            with GERAETEWACHE.arbeit(
                f"Wiedergabegerät schließen: {geraetename}"
            ):
                self._pcm.close()

            self._pcm = None

        self.device = None

        self.logger.info(
            "ALSA-Wiedergabegerät geschlossen."
        )
