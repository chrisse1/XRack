"""
XRack Bluetooth-Audiostreaming (A2DP-Sink).

Leitet einen eingehenden Bluetooth-Audiostream (Handy/Tablet -> Pi)
auf ein frei wählbares Stereopaar des Interfaces um - technisch
dasselbe Prinzip wie beim Musikspieler (siehe player/music_player.py):
AudioPlaybackBackend + ChannelInserter. Der Unterschied ist nur die
Quelle: statt einer per ffmpeg dekodierten Datei ist es ein
fortlaufender Live-Capture-Stream vom bluez-alsa-Dienst (bluealsa).

Das ALSA-Plugin "bluealsa" liefert dabei IMMER genau das Format, mit
dem der Bluetooth-Codec tatsächlich sendet (16 Bit, üblicherweise
44100 Hz Stereo für den SBC-Standardcodec) - es macht selbst keine
Formatanpassung. Ein vorangestelltes "plug:" ("plug:bluealsa:...")
ist dafür KEINE gültige Lösung: Alsa-lib interpretiert alles nach dem
ersten Doppelpunkt als Parameterliste von "plug" selbst, nicht als
verschachtelten Gerätenamen - das führt zum Laufzeitfehler "Unknown
parameter bluealsa:DEV" und funktioniert nicht. Die Umwandlung auf das
von AudioPlaybackBackend erwartete S32_LE bei der Ziel-Samplerate des
Interfaces übernimmt deshalb, wie schon beim Abspielen von
Musikdateien (siehe player/track_decoder.py), ein ffmpeg-Subprozess.

Wichtig: die bluealsa-Capture-Verbindung (pcm) wird für einen
Kanalwechsel NIE geschlossen und neu geöffnet. Live-Tests zeigten,
dass bluealsa (Stand 4.3.1-3) nach wiederholtem Öffnen/Schließen
desselben Transports dauerhaft "Device or resource busy" liefert -
reproduzierbar sogar mit bluealsas eigenem Kommandozeilenwerkzeug
(bluealsa-aplay), also unabhängig von XRack. Ein Kanalwechsel schließt
und öffnet deshalb ausschließlich AudioPlaybackBackend (rein lokales
ALSA-Wiedergabegerät, ohne bluealsa-Beteiligung) neu, während
bluealsa-Capture und ffmpeg unangetastet weiterlaufen. Nur bei einer
echten Neuverbindung (Handy verbindet sich neu) wird die
bluealsa-Verbindung tatsächlich neu aufgebaut.

Es wird kein Playback erzwungen, solange kein Handy tatsächlich
Audio schickt: Ein Hintergrund-Thread sucht laufend nach einem
verbundenen Gerät und versucht, dessen Capture-PCM zu öffnen - das
schlägt fehl (und wird nach kurzer Pause erneut versucht), solange
kein aktiver A2DP-Medienstream existiert. Genau dieselbe Schleife
sorgt auch dafür, dass eine gleichzeitig laufende Musikwiedergabe
oder ein Soundcheck (die dieselbe Hardware exklusiv belegen) den
Bluetooth-Stream nicht dauerhaft blockieren, sondern er automatisch
weiterläuft, sobald das Gerät wieder frei ist.
"""

import logging
import subprocess
import threading

import alsaaudio

from audio.audio_playback_backend import AudioPlaybackBackend
from audio.models import AudioDevice
from core.bluetooth_control import BluetoothControl

CHANNELS = 2
CHUNK_FRAMES = 1024

# Sendeformat des bluealsa-ALSA-Plugins: immer 16 Bit, die Samplerate
# ist beim mandatorischen SBC-Codec praktisch immer 44100 Hz.
SOURCE_FORMAT = alsaaudio.PCM_FORMAT_S16_LE
SOURCE_RATE = 44100

RETRY_DELAY = 2.0


class BluetoothPlayer:
    """Streamt eingehendes Bluetooth-Audio auf gewählte Kanäle."""

    def __init__(
        self,
        backend: AudioPlaybackBackend,
        control: BluetoothControl,
    ):

        self.logger = logging.getLogger("XRack")

        self.backend = backend
        self.control = control

        self._enabled = False
        self._streaming = False
        self._connected_name = ""

        self._device: AudioDevice | None = None
        self._start_channel = 0
        self._rate = 48000

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._channel_change_event = threading.Event()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def streaming(self) -> bool:
        return self._streaming

    @property
    def connected_device_name(self) -> str:
        return self._connected_name

    def set_start_channel(self, start_channel: int) -> None:
        """
        Ändert das Ziel-Stereopaar (0-basiert). Läuft gerade eine
        Wiedergabe, wird nur das lokale Wiedergabegerät kurz neu
        geöffnet (siehe Moduldoku) - die bluealsa-Verbindung bleibt
        dabei komplett unberührt.
        """

        if start_channel == self._start_channel:
            return

        self._start_channel = start_channel

        if self._streaming:
            self._channel_change_event.set()

    def start(
        self,
        device: AudioDevice,
        start_channel: int,
        rate: int,
    ) -> None:
        """
        Aktiviert die Bluetooth-Wiedergabe (Hintergrund-Überwachung).
        """

        if self._enabled:
            self.set_start_channel(start_channel)
            return

        self._device = device
        self._start_channel = start_channel
        self._rate = rate
        self._enabled = True
        self._stop_event.clear()
        self._channel_change_event.clear()

        self._thread = threading.Thread(
            target=self._monitor,
            daemon=True,
        )
        self._thread.start()

        self.logger.info(
            "Bluetooth-Überwachung gestartet."
        )

    def stop(self) -> None:
        """
        Deaktiviert die Bluetooth-Wiedergabe wieder vollständig.
        """

        if not self._enabled:
            return

        self._enabled = False
        self._stop_event.set()
        self._channel_change_event.clear()

        if self._thread is not None:
            self._thread.join()
            self._thread = None

        self._streaming = False
        self._connected_name = ""

        self.logger.info(
            "Bluetooth-Überwachung gestoppt."
        )

    def _monitor(self) -> None:

        while self._enabled:

            mac = self.control.connected_device_mac()

            if mac is None:
                self._stop_event.wait(RETRY_DELAY)
                continue

            self._connected_name = (
                self.control.connected_device_name() or mac
            )

            self._stream_from(mac)

        self._streaming = False

    def _stream_from(self, mac: str) -> None:
        """
        Versucht, den Audiostream eines verbundenen Geräts zu öffnen
        und weiterzuleiten, solange er läuft. Kehrt zurück, sobald
        kein Stream (mehr) verfügbar ist - der Aufrufer versucht es
        dann erneut. Ein Kanalwechsel während der Wiedergabe (siehe
        set_start_channel) führt NICHT zu einem Rücksprung hierher -
        er wird direkt in der Schreibschleife unten behandelt.
        """

        try:

            pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_CAPTURE,
                mode=alsaaudio.PCM_NORMAL,
                device=f"bluealsa:DEV={mac},PROFILE=a2dp",
            )

            pcm.setrate(SOURCE_RATE)
            pcm.setchannels(CHANNELS)
            pcm.setformat(SOURCE_FORMAT)
            pcm.setperiodsize(CHUNK_FRAMES)

        except Exception as exc:

            self.logger.debug(
                "Bluetooth: kein aktiver Audiostream von %s (%s).",
                mac,
                exc,
            )
            self._stop_event.wait(RETRY_DELAY)
            return

        try:

            ffmpeg_process = subprocess.Popen(
                [
                    "ffmpeg", "-v", "error",
                    "-f", "s16le",
                    "-ar", str(SOURCE_RATE),
                    "-ac", str(CHANNELS),
                    "-i", "pipe:0",
                    "-f", "s32le",
                    "-acodec", "pcm_s32le",
                    "-ar", str(self._rate),
                    "-ac", str(CHANNELS),
                    "-",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )

        except FileNotFoundError:

            self.logger.error(
                "Bluetooth: ffmpeg nicht gefunden - "
                "Audioumwandlung nicht möglich."
            )
            pcm.close()
            self._stop_event.wait(RETRY_DELAY)
            return

        if not self.backend.open(
            self._device,
            channels=CHANNELS,
            rate=self._rate,
            start_channel=self._start_channel,
            sample_format=alsaaudio.PCM_FORMAT_S32_LE,
        ):
            pcm.close()
            self._terminate_ffmpeg(ffmpeg_process)
            self._stop_event.wait(RETRY_DELAY)
            return

        self._streaming = True

        self._channel_change_event.clear()

        self.logger.info(
            "Bluetooth-Wiedergabe gestartet: %s -> Kanal %d+%d",
            self._connected_name,
            self._start_channel + 1,
            self._start_channel + 2,
        )

        #
        # bluealsa-Capture (pcm) und ffmpeg-stdin gehören exklusiv
        # diesem Feeder-Thread - ein blockierendes pcm.read() lässt
        # sich von außen nicht sicher unterbrechen, deshalb läuft es
        # in einem eigenen Thread, den dieser Aufruf am Ende (nach
        # Abbruch/Fehler der Leseschleife unten) einfach mitbeendet.
        # Ein Kanalwechsel (siehe unten) rührt dieses Handle nicht an.
        #

        def feed() -> None:

            try:

                while self._enabled and not self._stop_event.is_set():

                    length, data = pcm.read()

                    if length <= 0:
                        break

                    try:
                        ffmpeg_process.stdin.write(data)
                    except (BrokenPipeError, OSError):
                        break

            finally:

                pcm.close()

                try:
                    ffmpeg_process.stdin.close()
                except OSError:
                    pass

        feeder_thread = threading.Thread(target=feed, daemon=True)
        feeder_thread.start()

        chunk_bytes = (
            CHUNK_FRAMES *
            CHANNELS *
            AudioPlaybackBackend.BYTES_PER_SAMPLE
        )

        try:

            while self._enabled and not self._stop_event.is_set():

                if self._channel_change_event.is_set():
                    self._channel_change_event.clear()
                    self._reopen_backend()

                data = ffmpeg_process.stdout.read(chunk_bytes)

                if not data:
                    break

                self.backend.write(data)

        finally:

            feeder_thread.join(timeout=2)

            self._terminate_ffmpeg(ffmpeg_process)

            self.backend.close()
            self._streaming = False

            self.logger.info(
                "Bluetooth-Wiedergabe beendet (%s).",
                self._connected_name,
            )

    def _reopen_backend(self) -> None:
        """
        Öffnet nur das lokale Wiedergabegerät mit dem neuen
        Zielkanal neu - die bluealsa-Verbindung/ffmpeg-Pipeline
        läuft währenddessen ununterbrochen weiter.
        """

        self.backend.close()

        if not self.backend.open(
            self._device,
            channels=CHANNELS,
            rate=self._rate,
            start_channel=self._start_channel,
            sample_format=alsaaudio.PCM_FORMAT_S32_LE,
        ):
            self.logger.error(
                "Bluetooth: Wiedergabegerät konnte nach Kanalwechsel "
                "nicht neu geöffnet werden (belegt?)."
            )
            return

        self.logger.info(
            "Bluetooth: Zielkanal gewechselt -> Kanal %d+%d",
            self._start_channel + 1,
            self._start_channel + 2,
        )

    @staticmethod
    def _terminate_ffmpeg(process: subprocess.Popen) -> None:

        if process.poll() is not None:
            return

        process.terminate()

        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
