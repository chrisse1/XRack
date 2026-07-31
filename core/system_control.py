"""
Steuerung des Betriebssystems (Herunterfahren).

XRack läuft nicht als root. Das Herunterfahren funktioniert über
eine dedizierte, passwortlose sudo-Regel, die "install.sh" für den
Dienst-Benutzer einrichtet (siehe /etc/sudoers.d/xrack) - sie
erlaubt ausschließlich poweroff/shutdown, sonst nichts.
"""

import logging
import subprocess


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
