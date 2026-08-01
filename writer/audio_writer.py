"""
Basisklasse für Audio-Dateischreiber.
"""

from abc import ABC, abstractmethod
from pathlib import Path


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
    ) -> str:
        """
        Erstellt Dateiname und Verzeichnis. Der Dateiname besteht aus
        `prefix` und einer fortlaufenden Nummer (z.B. "Soundcheck-1",
        "Soundcheck-2", ...) - die nächste freie Nummer wird dabei
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

        filename = f"{safe_prefix}-{index}"

        self.filename = str(
            self.directory / f"{filename}.{extension}"
        )

        return self.filename

    def _next_index(self, prefix: str, extension: str) -> int:
        """
        Ermittelt die nächste freie fortlaufende Nummer für `prefix`
        anhand der im Verzeichnis vorhandenen Dateien.
        """

        marker = f"{prefix}-"
        suffix = f".{extension}"
        highest = 0

        for path in self.directory.iterdir():

            name = path.name

            if not name.startswith(marker) or not name.endswith(suffix):
                continue

            number = name[len(marker):-len(suffix)]

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
    ):
        """
        Öffnet die Ausgabedatei.
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
