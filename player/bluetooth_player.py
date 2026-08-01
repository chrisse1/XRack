"""
XRack Bluetooth-Audiostreaming (A2DP-Sink).

Leitet einen eingehenden Bluetooth-Audiostream (Handy/Tablet -> Pi)
auf ein frei wählbares Stereopaar des Interfaces um - technisch
dasselbe Prinzip wie beim Musikspieler (siehe player/music_player.py):
AudioPlaybackBackend + ChannelInserter. Der Unterschied ist nur die
Quelle: statt einer per ffmpeg dekodierten Datei ist es ein
fortlaufender Live-Capture-Stream vom bluez-alsa-Dienst (bluealsa),
der über das ALSA-Plugin "bluealsa" als ganz normales PCM-Capture-
Gerät angesprochen wird.

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
import threading

import alsaaudio

from audio.audio_playback_backend import AudioPlaybackBackend
from audio.models import AudioDevice
from core.bluetooth_control import BluetoothControl

CHANNELS = 2
CHUNK_FRAMES = 1024
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
        Ändert das Ziel-Stereopaar (0-basiert). Wirkt beim nächsten
        neu erkannten Verbindungsaufbau, eine bereits laufende
        Wiedergabe wird nicht mitten im Stream umgehängt.
        """

        self._start_channel = start_channel

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
        dann erneut.
        """

        pcm = None

        try:

            pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_CAPTURE,
                mode=alsaaudio.PCM_NORMAL,
                device=f"plug:bluealsa:DEV={mac},PROFILE=a2dp",
            )

            pcm.setrate(self._rate)
            pcm.setchannels(CHANNELS)
            pcm.setformat(alsaaudio.PCM_FORMAT_S32_LE)
            pcm.setperiodsize(CHUNK_FRAMES)

        except Exception as exc:

            self.logger.debug(
                "Bluetooth: kein aktiver Audiostream von %s (%s).",
                mac,
                exc,
            )
            pcm = None

        if pcm is None:
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
            self._stop_event.wait(RETRY_DELAY)
            return

        self._streaming = True

        self.logger.info(
            "Bluetooth-Wiedergabe gestartet: %s -> Kanal %d+%d",
            self._connected_name,
            self._start_channel + 1,
            self._start_channel + 2,
        )

        try:

            while self._enabled and not self._stop_event.is_set():

                length, data = pcm.read()

                if length <= 0:
                    break

                self.backend.write(data)

        finally:

            pcm.close()
            self.backend.close()
            self._streaming = False

            self.logger.info(
                "Bluetooth-Wiedergabe beendet (%s).",
                self._connected_name,
            )
