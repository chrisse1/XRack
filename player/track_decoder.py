"""
Dekodiert Musikdateien (MP3, FLAC, WAV, ...) über ffmpeg zu rohem PCM.

Python selbst kann diese Formate nicht dekodieren. ffmpeg wird als
Subprozess gestartet und liefert auf stdout rohes S32_LE-PCM in der
gewünschten Samplerate und Kanalzahl - unabhängig vom Quellformat.

Voraussetzung: ffmpeg ist auf dem System installiert
(z.B. `sudo apt install ffmpeg`).
"""

import logging
import subprocess
from pathlib import Path


def probe_duration(path: Path) -> float:
    """
    Ermittelt die Länge einer Musikdatei in Sekunden über ffprobe
    (Teil von ffmpeg). Liefert 0.0, wenn die Länge nicht bestimmt
    werden kann.
    """

    try:

        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        return float(result.stdout.strip())

    except (
        subprocess.SubprocessError,
        FileNotFoundError,
        ValueError,
        OSError,
    ):

        return 0.0


class TrackDecoder:
    """Startet ffmpeg und liest die dekodierten PCM-Daten."""

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        self._process: subprocess.Popen | None = None

    @property
    def running(self) -> bool:
        return self._process is not None

    def open(
        self,
        path: Path,
        channels: int,
        rate: int,
        start_position: float = 0.0,
    ) -> bool:
        """
        Startet ffmpeg für die angegebene Datei. `start_position`
        (Sekunden) erlaubt das Spulen an eine Stelle im Titel -
        ffmpeg überspringt die Datei bis dahin selbst.
        """

        command = ["ffmpeg", "-v", "error"]

        if start_position > 0:
            command += ["-ss", str(start_position)]

        command += [
            "-i", str(path),
            "-f", "s32le",
            "-acodec", "pcm_s32le",
            "-ar", str(rate),
            "-ac", str(channels),
            "-",
        ]

        try:

            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )

            return True

        except FileNotFoundError:

            self.logger.error(
                "ffmpeg wurde nicht gefunden. "
                "Bitte installieren: sudo apt install ffmpeg"
            )

            self._process = None

            return False

    def read(self, chunk_size: int) -> bytes | None:
        """
        Liest bis zu chunk_size Bytes dekodierte PCM-Daten.
        Liefert None, wenn ffmpeg fertig ist.
        """

        if self._process is None or self._process.stdout is None:
            return None

        data = self._process.stdout.read(chunk_size)

        if not data:
            return None

        return data

    def close(self) -> None:
        """
        Beendet den ffmpeg-Prozess.
        """

        if self._process is None:
            return

        if self._process.poll() is None:

            self._process.terminate()

            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()

        self._process = None
