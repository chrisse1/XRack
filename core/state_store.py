"""
Speichert einfache Einstellungen (gewähltes Audiogerät, Kanäle)
als JSON-Datei, damit sie einen Neustart überstehen.
"""

import json
import logging
import os
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

        Erst vollständig in eine Nebendatei, dann umbenennen. Ein
        Umbenennen im selben Verzeichnis ist unteilbar: Es gibt keinen
        Moment, in dem die Zieldatei halb geschrieben dasteht.

        Das ist hier keine Förmlichkeit. XRack läuft auf einem Gerät im
        Rack, das auch mal einfach vom Strom getrennt wird. Direkt in
        die Zieldatei geschrieben, hinterlässt so ein Moment eine
        abgeschnittene Datei - und load() fängt den Fehler zwar ab,
        startet dann aber still mit leerem Zustand. Weg wären
        Audiogerät, Kanalzahl, Pult-IP, Sperrzeit und die
        Kopplungs-Buchführung, ohne dass irgendwo etwas aufblinkt.

        Dasselbe Muster benutzt schon scripts/xrack-update.py für seine
        Statusdatei.
        """

        temporaer = self.path.with_suffix(".tmp")

        try:

            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with temporaer.open("w", encoding="utf-8") as file:

                json.dump(self._data, file)

                #
                # Vor dem Umbenennen wirklich auf die Platte bringen.
                # Ohne das steht der Inhalt womöglich noch im
                # Schreibpuffer des Systems, während der neue Name
                # bereits gilt - dann zeigt der Name nach einem
                # Stromausfall auf eine leere Datei.
                #
                file.flush()
                os.fsync(file.fileno())

            temporaer.replace(self.path)

        except OSError as exc:

            self.logger.warning(
                "Zustand konnte nicht gespeichert werden: %s",
                exc,
            )

            #
            # Halbe Nebendatei nicht liegen lassen.
            #
            temporaer.unlink(missing_ok=True)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value) -> None:
        """
        Setzt einen Wert und speichert sofort.
        """

        self._data[key] = value

        self.save()
