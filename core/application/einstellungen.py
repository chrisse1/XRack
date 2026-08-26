"""
Sprache, Port und der PIN-Schutz des Einstellungen-Modals.
"""

import re

from core.pin import hash_pin, verify_pin


class EinstellungenMixin:
    """
    Sprache, Port und der PIN-Schutz des Einstellungen-Modals.

    Teil von Application - siehe core/application/__init__.py.
    """

    def set_language(self, language: str) -> bool:
        """
        Ändert die Sprache der Weboberfläche. Wirkt sofort, ohne
        Neustart - Übersetzungen werden bei jedem Seitenaufruf neu
        anhand der aktuellen Konfiguration geladen.
        """

        if language not in ("de", "en"):
            return False

        self.config.set_override("application", "language", language)

        self.config.data.application.language = language

        return True


    def set_port(self, port: int) -> bool:
        """
        Ändert den Port des Webinterfaces. Wird dauerhaft
        gespeichert, wirkt aber erst nach einem Dienst-Neustart
        (siehe restart_service()).
        """

        if not 1 <= port <= 65535:
            return False

        self.config.set_override("server", "port", port)

        self.config.data.server.port = port

        return True


    def pin_protection_enabled(self) -> bool:
        """
        Ist eine PIN zum Schutz des Einstellungen-Modals gesetzt?
        """

        return bool(self.config.data.security.pin_hash)


    def verify_settings_pin(self, pin: str) -> bool:
        """
        Prüft eine eingegebene PIN. Ist keine PIN gesetzt (z.B. vor
        dem ersten install.sh-Lauf mit dieser Funktion), gilt jede
        Eingabe als gültig - die Einstellungen sind dann ungeschützt.
        """

        pin_hash = self.config.data.security.pin_hash

        if not pin_hash:
            return True

        return verify_pin(pin, pin_hash)


    def set_settings_pin(self, current_pin: str, new_pin: str) -> tuple[bool, str]:
        """
        Ändert die PIN fürs Einstellungen-Modal. War noch keine PIN
        gesetzt, wird current_pin nicht geprüft (Erstvergabe).
        """

        if not re.fullmatch(r"\d{4}", new_pin):
            return False, "Neue PIN muss aus genau 4 Ziffern bestehen."

        if not self.verify_settings_pin(current_pin):
            return False, "Aktuelle PIN ist falsch."

        pin_hash = hash_pin(new_pin)

        self.config.set_override("security", "pin_hash", pin_hash)

        self.config.data.security.pin_hash = pin_hash

        return True, "PIN geändert."
