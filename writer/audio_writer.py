"""
Basisklasse für Audio-Dateischreiber.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from core.recording_kind import MARKER_SOUNDCHECK, strip_marker


class AudioWriter(ABC):
    """
    Abstrakte Basisklasse für AudioWriter.
    """

    def __init__(self):

        self.filename: str | None = None
        
        self.directory = Path("recordings")

        self.channels = 0
        self.sample_rate = 0
        self.bits_per_sample = 0

    def create_filename(
        self,
        extension: str,
        prefix: str = "Soundcheck",
        marker: str = MARKER_SOUNDCHECK,
    ) -> str:
        """
        Erstellt Dateiname und Verzeichnis. Der Dateiname besteht aus
        `prefix`, einer fortlaufenden Nummer und einem Kürzel für die
        Art der Datei (z.B. "Soundcheck-1_s", "Bohemian Rhapsody-1_p") -
        siehe core/recording_kind.py. Die nächste freie Nummer wird
        anhand der bereits vorhandenen Dateien mit demselben Präfix
        ermittelt, nicht separat gespeichert. Das übersteht Löschen
        einzelner Aufnahmen und Neustarts, und ein Präfixwechsel
        fängt automatisch wieder bei 1 an.
        """

        self.directory.mkdir(
            exist_ok=True
        )

        safe_prefix = prefix.strip() if prefix and prefix.strip() else "Soundcheck"

        index = self._next_index(safe_prefix, extension)

        filename = f"{safe_prefix}-{index}_{marker}"

        self.filename = str(
            self.directory / f"{filename}.{extension}"
        )

        return self.filename

    def _next_index(self, prefix: str, extension: str) -> int:
        """
        Ermittelt die nächste freie fortlaufende Nummer für `prefix`
        anhand der im Verzeichnis vorhandenen Dateien.

        Berücksichtigt dabei sowohl Namen *mit* Kürzel
        ("Soundcheck-1_s.w64") als auch ältere ohne
        ("Soundcheck-1.w64") - sonst würde der Zähler nach der
        Einführung des Kürzels wieder bei 1 anfangen und die
        vorhandene Aufnahme beim Öffnen überschreiben.
        """

        start = f"{prefix}-"
        suffix = f".{extension}"
        highest = 0

        for path in self.directory.iterdir():

            name = path.name

            if not name.startswith(start) or not name.endswith(suffix):
                continue

            number = strip_marker(name[len(start):-len(suffix)])

            if number.isdigit():
                highest = max(highest, int(number))

        return highest + 1

    @abstractmethod
    def open(
        self,
        channels: int,
        sample_rate: int,
        bits_per_sample: int,
        name_prefix: str = "Soundcheck",
        marker: str = MARKER_SOUNDCHECK,
    ):
        """
        Öffnet die Ausgabedatei. `marker` kennzeichnet die Art der
        Datei im Dateinamen, siehe core/recording_kind.py.
        """
        pass

    @abstractmethod
    def write(
        self,
        data: bytes,
    ):
        """
        Schreibt Audiodaten.
        """
        pass

    @abstractmethod
    def close(self):
        """
        Schließt die Ausgabedatei.
        """
        pass
