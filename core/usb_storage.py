"""
USB-Stick-Zugriff fürs Kopieren von Aufnahmen.

Das eigentliche Einhängen/Aushängen passiert unabhängig von XRack
über eine udev-Regel + einen systemd-Dienst (siehe install.sh) - hier
wird nur geprüft, ob unter dem festen Mountpunkt gerade ein
Datenträger eingehängt ist, und dorthin kopiert.
"""

import shutil
from pathlib import Path


class UsbStorage:
    """Kapselt den Zugriff auf den automatisch eingehängten USB-Stick."""

    MOUNT_POINT = Path("/media/xrack-usb")

    @property
    def connected(self) -> bool:
        """True, wenn gerade ein USB-Stick eingehängt ist."""

        return self.MOUNT_POINT.is_mount()

    def copy_file(self, source: Path) -> tuple[bool, bool]:
        """
        Kopiert eine Datei ins Wurzelverzeichnis des USB-Sticks.

        Liefert (erfolgreich, bereits_vorhanden). Ist dort schon eine
        gleichnamige Datei vorhanden, wird nicht erneut kopiert.
        """

        if not self.connected:
            return False, False

        target = self.MOUNT_POINT / source.name

        if target.exists():
            return True, True

        try:
            shutil.copy2(source, target)
        except OSError:
            return False, False

        return True, False
