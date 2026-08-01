"""
Steuerung des Betriebssystems (Herunterfahren, Dienst-Neustart).

XRack läuft nicht als root. Herunterfahren und Neustart funktionieren
über dedizierte, passwortlose sudo-Regeln, die "install.sh" für den
Dienst-Benutzer einrichtet (siehe /etc/sudoers.d/xrack) - sie
erlauben ausschließlich poweroff/shutdown sowie das feste
Neustart-Skript, sonst nichts.
"""

import logging
import subprocess
from pathlib import Path


class SystemControl:
    """Kapselt privilegierte Systembefehle."""

    def __init__(self):
        self.logger = logging.getLogger("XRack")

    def shutdown(self) -> bool:
        """
        Fährt den Raspberry Pi herunter.
        """

        try:

            result = subprocess.run(
                ["sudo", "-n", "poweroff"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:

                self.logger.error(
                    "Herunterfahren fehlgeschlagen (sudo-Recht "
                    "fehlt? siehe install.sh): %s",
                    result.stderr.strip(),
                )

                return False

            self.logger.info(
                "Herunterfahren angefordert."
            )

            return True

        except Exception as exc:

            self.logger.exception(
                "Herunterfahren fehlgeschlagen: %s",
                exc,
            )

            return False

    def restart_service(self) -> bool:
        """
        Startet den XRack-systemd-Dienst neu (z.B. nach einer
        Port-Änderung). Das Skript selbst wartet kurz, bevor es den
        eigentlichen Neustart auslöst, damit die HTTP-Antwort dieses
        Aufrufs noch beim Client ankommt.
        """

        script = Path("scripts/xrack-restart.sh").resolve()

        try:

            result = subprocess.run(
                ["sudo", "-n", str(script)],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:

                self.logger.error(
                    "Neustart fehlgeschlagen (sudo-Recht fehlt? "
                    "siehe install.sh): %s",
                    result.stderr.strip(),
                )

                return False

            self.logger.info(
                "Dienst-Neustart angefordert."
            )

            return True

        except Exception as exc:

            self.logger.exception(
                "Neustart fehlgeschlagen: %s",
                exc,
            )

            return False
