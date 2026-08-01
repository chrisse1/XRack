"""
XRack Recorder.
"""

import logging
import threading

from audio.audio_backend import AudioBackend
from recorder.level_meter import LevelMeter
from writer.audio_writer import AudioWriter
from writer.w64_writer import W64Writer
from time import monotonic
from pathlib import Path

class Recorder:
    """
    Verwaltet Audioaufnahmen und die reine Pegelmessung.

    Beide teilen sich denselben Aufnahme-Thread (ALSA erlaubt kein
    gleichzeitiges Lesen von zwei Stellen aus): "Pegel testen"
    startet den Thread ohne in eine Datei zu schreiben, eine echte
    Aufnahme schaltet das Schreiben zusätzlich dazu - nahtlos, ohne
    den Thread neu zu starten, falls bereits pegelgeprüft wird.
    """

    def __init__(
        self,
        backend: AudioBackend,
    ):

        self.logger = logging.getLogger(
            "XRack"
        )

        self.backend = backend

        self._active = False

        self._write_to_file = False

        self._thread: threading.Thread | None = None

        self.writer: AudioWriter = W64Writer()

        self.meter: LevelMeter | None = None

        self._buffer_count = 0

        self._bytes_written = 0

        self._start_time = None

        self._current_filename = ""

        self._last_duration = 0.0

    @property
    def recording(self) -> bool:
        """
        True während einer echten Aufnahme (Datei wird geschrieben).
        """

        return self._active and self._write_to_file

    @property
    def monitoring(self) -> bool:
        """
        True, wenn der Aufnahme-Thread läuft (Pegel testen oder
        Aufnahme - beides aktiviert die Pegelmessung).
        """

        return self._active

    @property
    def levels(self) -> list[float]:
        """
        Aktuelle Pegel je Kanal (0.0 - 1.0+, leer wenn inaktiv).
        """

        if self.meter is None:
            return []

        return self.meter.levels

    def start(self, name_prefix: str = "Soundcheck") -> bool:
        """
        Startet die Aufnahme. Läuft bereits eine reine
        Pegelprüfung, wird sie nahtlos zur Aufnahme erweitert.
        `name_prefix` bestimmt den Dateinamen ("<Präfix>-<Nummer>").
        """

        if self.recording:
            return False

        self._buffer_count = 0
        self._bytes_written = 0
        self._start_time = monotonic()

        self.writer.open(
            channels=self.backend.channels,
            sample_rate=self.backend.rate,
            bits_per_sample=24,
            name_prefix=name_prefix,
        )

        self._current_filename = self.writer.filename

        self._write_to_file = True

        self.logger.info(
            "Aufnahmedatei: %s",
            self._current_filename,
        )

        self._ensure_thread_running()

        self.logger.info(
            "Recorder gestartet."
        )

        return True

    def stop(self) -> None:
        """
        Stoppt die Aufnahme (und damit auch die Pegelmessung
        vollständig).
        """

        if not self.recording:
            return

        #
        # Dauer der Aufnahme merken
        #
        if self._start_time is not None:
            self._last_duration = (
                monotonic() - self._start_time
            )

        self._start_time = None

        self._stop_thread()

        self.writer.close()

        self.logger.info(
            "Recorder gestoppt."
        )

    def start_monitoring(self) -> bool:
        """
        Startet die reine Pegelprüfung, ohne aufzuzeichnen.
        """

        if self._active:
            return False

        self._write_to_file = False

        self._ensure_thread_running()

        self.logger.info(
            "Pegelprüfung gestartet."
        )

        return True

    def stop_monitoring(self) -> None:
        """
        Stoppt die reine Pegelprüfung (nicht während einer echten
        Aufnahme aufrufen - dafür ist stop() da).
        """

        if not self._active or self._write_to_file:
            return

        self._stop_thread()

        self.logger.info(
            "Pegelprüfung gestoppt."
        )

    def _ensure_thread_running(self) -> None:

        if self._active:
            return

        self.meter = LevelMeter(
            channels=self.backend.channels
        )

        self._active = True

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
        )

        self._thread.start()

    def _stop_thread(self) -> None:

        self._active = False

        self._write_to_file = False

        if self._thread is not None:

            self._thread.join()

            self._thread = None

        self.meter = None

    def _worker(self) -> None:
        """
        Hauptschleife: liest kontinuierlich vom Audio-Interface,
        aktualisiert die Pegel und schreibt bei aktiver Aufnahme
        zusätzlich in die Datei.
        """

        self.logger.info(
            "Recorder-Thread gestartet."
        )

        while self._active:

            data = self.backend.read()

            if data is None:

                continue

            if self.meter is not None:
                self.meter.update(data)

            if not self._write_to_file:
                continue

            self.writer.write(data)

            self._buffer_count += 1

            self._bytes_written += len(data)

            if self._buffer_count % 100 == 0:

                self.logger.info(
                    "Recorder: %d Buffer | %.2f MB",
                    self._buffer_count,
                    self.mb_written,
                )

    @property
    def buffer_count(self) -> int:
        return self._buffer_count

    @property
    def bytes_written(self) -> int:
        return self._bytes_written
        
    @property
    def duration(self) -> float:
        """
        Dauer der aktuellen bzw. letzten Aufnahme.
        """

        if self.recording:
            return monotonic() - self._start_time

        return self._last_duration
        
    @property
    def mb_written(self) -> float:

        return self._bytes_written / 1024 / 1024


    @property
    def gigabytes_written(self) -> float:

        return self._bytes_written / 1024 / 1024 / 1024
        
    @property
    def current_filename(self) -> str:
        """
        Name der aktuell aufgenommenen bzw. zuletzt aufgenommenen Datei.
        """

        return self._current_filename
        
    @property
    def recordings(self) -> list[str]:
        """
        Liefert alle vorhandenen Aufnahmen.
        """

        recording_path = Path("recordings")

        if not recording_path.exists():
            return []

        return sorted(
            [
                file.name
                for file in recording_path.glob("*.w64")
            ],
            reverse=True,
        )
