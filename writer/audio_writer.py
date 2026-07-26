"""
Basisklasse für Audio-Dateischreiber.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime


class AudioWriter(ABC):
    """
    Abstrakte Basisklasse für AudioWriter.
    """

    def __init__(self):

        self.filename: str | None = None

    def create_filename(
        self,
        extension: str,
    ) -> str:
        """
        Erstellt Dateiname und Verzeichnis.
        """

        directory = Path("recordings")

        directory.mkdir(
            exist_ok=True
        )

        filename = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        self.filename = str(
            directory / f"{filename}.{extension}"
        )

        return self.filename

    @abstractmethod
    def open(self):
        """
        Öffnet die Ausgabedatei.
        """
        pass

    @abstractmethod
    def write(self, data: bytes):
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
