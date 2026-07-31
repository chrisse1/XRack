"""
Speichert einfache Einstellungen (gewähltes Audiogerät, Kanäle)
als JSON-Datei, damit sie einen Neustart überstehen.
"""

import json
import logging
from pathlib import Path


class StateStore:
    """Lädt/speichert Schlüssel-Wert-Paare als JSON-Datei."""

    def __init__(self, path: Path):

        self.path = path

        self.logger = logging.getLogger("XRack")

        self._data: dict = {}

        self.load()

    def load(self) -> None:
        """
        Lädt den gespeicherten Zustand. Fehlt die Datei oder ist
        sie beschädigt, wird einfach mit leerem Zustand begonnen.
        """

        if not self.path.exists():
            self._data = {}
            return

        try:

            with self.path.open("r", encoding="utf-8") as file:
                self._data = json.load(file)

        except (json.JSONDecodeError, OSError) as exc:

            self.logger.warning(
                "Gespeicherter Zustand konnte nicht gelesen werden: %s",
                exc,
            )

            self._data = {}

    def save(self) -> None:
        """
        Schreibt den aktuellen Zustand auf die Platte.
        """

        try:

            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with self.path.open("w", encoding="utf-8") as file:
                json.dump(self._data, file)

        except OSError as exc:

            self.logger.warning(
                "Zustand konnte nicht gespeichert werden: %s",
                exc,
            )

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        """
        Setzt einen Wert und speichert sofort.
        """

        self._data[key] = value

        self.save()
