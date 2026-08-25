"""
Update auf zwei Wegen: aus dem Internet (direkt von GitHub) oder über
einen USB-Stick, auf dessen Wurzelverzeichnis die von GitHub
heruntergeladene ZIP-Datei liegt. Beide stoßen denselben Updater an
(scripts/xrack-update.py, per sudo) und laufen dort durch denselben
Ablauf - Erfolgsmeldung, Rückfall und der Hinweis auf install.sh
gelten deshalb für beide gleichermaßen.

Der USB-Weg bleibt der wichtigere: Er ist der einzige, der ohne
Internet funktioniert, und genau dafür gibt es ihn.

Die eigentliche Arbeit macht bewusst ein separates Skript in einem
eigenständigen systemd-Task: XRack aktualisiert sich hier selbst und
startet sich dabei neu - ein Updater, der als Teil des laufenden
Dienstes liefe, würde sich mitten im Dateitausch selbst abschießen.
"""

import json
import logging
import subprocess
from pathlib import Path

from core.usb_storage import UsbStorage

WORK_DIR = Path("/var/tmp/xrack-update")
STATUS_FILE = WORK_DIR / "status.json"

UPDATE_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "xrack-update.py"

INSTALL_DIR = Path(__file__).resolve().parent.parent


class Updater:
    """Sucht Update-Pakete auf dem USB-Stick und startet das Update."""

    def __init__(self, usb_storage: UsbStorage | None = None):

        self.logger = logging.getLogger("XRack")

        self.usb_storage = usb_storage or UsbStorage()

    def find_package(self) -> Path | None:
        """
        Sucht im Wurzelverzeichnis des USB-Sticks nach einer ZIP-Datei.

        Liegen mehrere dort, gewinnt die zuletzt geänderte - das ist
        in aller Regel die frisch heruntergeladene.
        """

        if not self.usb_storage.connected:
            return None

        candidates = [
            path
            for path in self.usb_storage.MOUNT_POINT.glob("*.zip")
            if path.is_file()
        ]

        if not candidates:
            return None

        return max(candidates, key=lambda path: path.stat().st_mtime)

    def get_available(self) -> dict:
        """
        Beschreibt, ob ein Update bereitliegt - fürs Einstellungen-Modal.
        """

        package = self.find_package()

        if package is None:
            return {
                "usb_connected": self.usb_storage.connected,
                "package": "",
                "size": 0,
            }

        return {
            "usb_connected": True,
            "package": package.name,
            "size": package.stat().st_size,
        }

    def start(
        self,
        service_user: str,
        port: int,
        source: str = "usb",
        repository: str = "",
        branch: str = "main",
    ) -> tuple[bool, str]:
        """
        Startet das Update im Hintergrund. Liefert (Erfolg, Meldung) -
        "Erfolg" heißt hier nur, dass der Vorgang angestoßen wurde; das
        Ergebnis liefert get_status().

        `source` ist "usb" (ZIP-Datei vom Stick) oder "github" (wird
        vom Update-Skript selbst heruntergeladen).
        """

        status = self.get_status()

        if status.get("state") == "running":
            return False, "Es läuft bereits ein Update."

        if not UPDATE_SCRIPT.is_file():
            return False, "Update-Skript nicht gefunden."

        if source == "github":

            if not repository:
                return False, "Kein GitHub-Verzeichnis eingestellt."

            quelle = ["--repository", repository, "--branch", branch]

            self.logger.info(
                "Update wird gestartet: %s (%s)", repository, branch
            )

        else:

            package = self.find_package()

            if package is None:
                return False, "Keine ZIP-Datei auf dem USB-Stick gefunden."

            quelle = ["--zip", str(package)]

            self.logger.info("Update wird gestartet: %s", package)

        command = [
            "sudo",
            str(UPDATE_SCRIPT),
            str(INSTALL_DIR),
            service_user,
            str(port),
            *quelle,
        ]

        try:

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:

                self.logger.error(
                    "Update konnte nicht gestartet werden (Code %d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )

                return False, (
                    "Update konnte nicht gestartet werden. Ist die "
                    "sudo-Berechtigung eingerichtet (install.sh)?"
                )

            return True, "started"

        except (subprocess.SubprocessError, OSError) as exc:

            self.logger.exception("Update konnte nicht gestartet werden: %s", exc)

            return False, "Update konnte nicht gestartet werden."

    def get_status(self) -> dict:
        """
        Liest den Fortschritt, den scripts/xrack-update.py schreibt.

        Die Datei liegt außerhalb des Installationsverzeichnisses und
        übersteht damit sowohl den Dateitausch als auch den Neustart
        des Dienstes - genau darum kann das Frontend nach dem Neustart
        weiterpollen und das Ergebnis anzeigen.
        """

        if not STATUS_FILE.is_file():
            return {
                "state": "idle",
                "step": "",
                "message": "",
                "needs_install_script": False,
                "needs_dependencies": False,
                "needs_git_reset": False,
            }

        try:

            with STATUS_FILE.open("r", encoding="utf-8") as file:
                return json.load(file)

        except (json.JSONDecodeError, OSError) as exc:

            self.logger.warning("Update-Status nicht lesbar: %s", exc)

            return {
                "state": "idle",
                "step": "",
                "message": "",
                "needs_install_script": False,
                "needs_dependencies": False,
                "needs_git_reset": False,
            }
