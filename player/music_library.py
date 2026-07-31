"""
Zugriff auf die Musikbibliothek (Ordner/Dateien unterhalb des
konfigurierten Musikverzeichnisses).
"""

import random
import shutil
from dataclasses import dataclass, field
from pathlib import Path

AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".flac",
    ".ogg",
    ".m4a",
    ".aac",
    ".wma",
}


@dataclass
class MusicListing:
    """Inhalt eines Ordners der Musikbibliothek."""

    path: str
    folders: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


class MusicLibrary:
    """
    Kapselt den lesenden Zugriff auf das Musikverzeichnis.

    Alle Pfade von außen sind relativ zum Musikverzeichnis und
    werden vor der Nutzung dagegen abgesichert (kein Verlassen des
    Verzeichnisses über "..").
    """

    def __init__(self, root: Path):
        self.root = root

    def resolve(self, relative_path: str) -> Path | None:
        """
        Löst einen relativen Pfad sicher gegen das Musikverzeichnis
        auf. Liefert None, wenn der Pfad das Verzeichnis verlässt
        oder nicht existiert.
        """

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        candidate = (self.root / relative_path).resolve()

        root_resolved = self.root.resolve()

        if root_resolved not in candidate.parents and candidate != root_resolved:
            return None

        if not candidate.exists():
            return None

        return candidate

    def browse(self, relative_path: str = "") -> MusicListing | None:
        """
        Liefert Unterordner und Musikdateien eines Ordners.
        """

        folder = self.resolve(relative_path) if relative_path else self.root

        if relative_path:
            if folder is None or not folder.is_dir():
                return None
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            folder = self.root

        folders = sorted(
            entry.name
            for entry in folder.iterdir()
            if entry.is_dir()
        )

        files = sorted(
            entry.name
            for entry in folder.iterdir()
            if entry.is_file()
            and entry.suffix.lower() in AUDIO_EXTENSIONS
        )

        return MusicListing(
            path=relative_path,
            folders=folders,
            files=files,
        )

    def create_folder(self, relative_path: str, name: str) -> bool:
        """
        Legt einen neuen Unterordner an.
        """

        parent = self.resolve(relative_path)

        if parent is None or not parent.is_dir():
            return False

        name = name.strip()

        if not name or "/" in name or "\\" in name or name in (".", ".."):
            return False

        new_folder = parent / name

        if new_folder.exists():
            return False

        new_folder.mkdir()

        return True

    def save_upload(
        self,
        relative_path: str,
        filename: str,
        source,
    ) -> str | None:
        """
        Speichert eine hochgeladene Musikdatei in einem Ordner.
        Liefert den gespeicherten Dateinamen oder None bei Fehlern.
        """

        folder = self.resolve(relative_path)

        if folder is None or not folder.is_dir():
            return None

        #
        # Nur den reinen Dateinamen übernehmen (kein Pfad aus dem
        # Upload verwenden).
        #
        filename = Path(filename).name

        if not filename:
            return None

        if Path(filename).suffix.lower() not in AUDIO_EXTENSIONS:
            return None

        destination = folder / filename

        with destination.open("wb") as target:
            shutil.copyfileobj(source, target)

        return filename

    def delete_file(self, relative_path: str) -> bool:
        """
        Löscht eine Musikdatei aus der Bibliothek.
        """

        path = self.resolve(relative_path)

        if path is None or not path.is_file():
            return False

        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            return False

        path.unlink()

        return True

    def find_audio_files(self, folder: Path) -> list[Path]:
        """
        Findet rekursiv alle Musikdateien in einem Ordner.
        """

        return [
            path
            for path in folder.rglob("*")
            if path.is_file()
            and path.suffix.lower() in AUDIO_EXTENSIONS
        ]

    def build_shuffled_playlist(self, folder: Path) -> list[Path]:
        """
        Erstellt eine zufällig gemischte Wiedergabeliste.
        """

        files = self.find_audio_files(folder)

        random.shuffle(files)

        return files
