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
        
        self.directory = Path("recordings")

        self.channels = 0
        self.sample_rate = 0
        self.bits_per_sample = 0

    def create_filename(
        self,
        extension: str,
    ) -> str:
        """
        Erstellt Dateiname und Verzeichnis.
        """

        self.directory.mkdir(
            exist_ok=True
        )

        filename = datetime.now().strftime(
            "%Y-%m-%d_%H-%M-%S"
        )

        self.filename = str(
            self.directory / f"{filename}.{extension}"
        )

        return self.filename

    @abstractmethod
    def open(
        self,
        channels: int,
        sample_rate: int,
        bits_per_sample: int,
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
