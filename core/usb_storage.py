"""
USB-Stick-Zugriff fürs Kopieren von Aufnahmen.

Das eigentliche Einhängen/Aushängen passiert unabhängig von XRack
über eine udev-Regel + einen systemd-Dienst (siehe install.sh) - hier
wird nur geprüft, ob unter dem festen Mountpunkt gerade ein
Datenträger eingehängt ist, dorthin kopiert und (auf Wunsch aus dem
Webinterface) wieder ausgehängt.
"""

import logging
import subprocess
from pathlib import Path
from typing import Callable

_COPY_CHUNK_SIZE = 4 * 1024 * 1024


class UsbStorage:
    """Kapselt den Zugriff auf den automatisch eingehängten USB-Stick."""

    MOUNT_POINT = Path("/media/xrack-usb")

    def __init__(self):
        self.logger = logging.getLogger("XRack")

    @property
    def connected(self) -> bool:
        """True, wenn gerade ein USB-Stick eingehängt ist."""

        return self.MOUNT_POINT.is_mount()

    def copy_file(
        self,
        source: Path,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[bool, bool]:
        """
        Kopiert eine Datei ins Wurzelverzeichnis des USB-Sticks.

        Liefert (erfolgreich, bereits_vorhanden). Ist dort schon eine
        gleichnamige Datei vorhanden, wird nicht erneut kopiert.
        `on_progress(kopierte_bytes, gesamt_bytes)` wird nach jedem
        gelesenen Block aufgerufen, damit das Webinterface eine
        Fortschrittsanzeige zeigen kann.
        """

        if not self.connected:
            return False, False

        target = self.MOUNT_POINT / source.name

        if target.exists():
            return True, True

        total = source.stat().st_size
        copied = 0

        try:

            with source.open("rb") as src, target.open("wb") as dst:

                while True:

                    chunk = src.read(_COPY_CHUNK_SIZE)

                    if not chunk:
                        break

                    dst.write(chunk)

                    copied += len(chunk)

                    if on_progress is not None:
                        on_progress(copied, total)

        except OSError:

            target.unlink(missing_ok=True)

            return False, False

        return True, False

    def eject(self) -> tuple[bool, str]:
        """
        Hängt den USB-Stick sicher aus, damit er entfernt werden kann.
        """

        script = Path("scripts") / "xrack-usb-unmount.sh"

        try:

            result = subprocess.run(
                ["sudo", "-n", str(script.resolve())],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:

                message = result.stderr.strip() or result.stdout.strip()

                self.logger.error(
                    "USB-Stick auswerfen fehlgeschlagen: %s",
                    message,
                )

                return False, message

            return True, ""

        except subprocess.TimeoutExpired:

            self.logger.error("USB-Stick auswerfen: Zeitüberschreitung.")

            return False, "Zeitüberschreitung."

        except Exception as exc:

            self.logger.exception(
                "USB-Stick auswerfen fehlgeschlagen: %s",
                exc,
            )

            return False, str(exc)
