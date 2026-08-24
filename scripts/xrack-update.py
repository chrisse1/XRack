#!/usr/bin/env python3
"""
Aktualisiert XRack aus einer ZIP-Datei (z.B. dem von GitHub
heruntergeladenen Quelltext auf einem USB-Stick).

Wird ausschließlich per sudo durch XRack selbst aufgerufen (siehe
core/updater.py), nie interaktiv.

Ablauf:
    1. ZIP prüfen (sieht das überhaupt nach XRack aus?)
    2. Aktuellen Stand sichern
    3. Dateien tauschen - Nutzerdaten bleiben unangetastet
    4. Bei Bedarf Abhängigkeiten nachinstallieren
    5. Dienst neu starten
    6. Gesundheitsprüfung: antwortet die Weboberfläche wieder?
    7. Wenn nicht: automatisch den alten Stand zurückholen

Warum Python und nicht Bash: Der Updater muss auf einer *bestehenden*
Installation laufen, die er selbst gerade erst aktualisiert. Er darf
deshalb nichts voraussetzen, was dort vielleicht fehlt - rsync, unzip
und curl installiert install.sh nämlich gar nicht. zipfile, urllib und
shutil sind dagegen Teil der Standardbibliothek und damit garantiert
vorhanden.

Der eigentliche Ablauf läuft in einem eigenständigen, transienten
systemd-Task - genau wie bei scripts/xrack-restart.sh. Würde er als
Kindprozess von XRack laufen, würde systemd ihn beim Neustart des
Dienstes (Kill-Mode "control-group") mitsamt dem Dienst erschlagen,
mitten im Dateitausch.
"""

import argparse
import json
import os
import pwd
import shutil
import ssl
import subprocess
import sys
import time
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

WORK_DIR = Path("/var/tmp/xrack-update")
STATUS_FILE = WORK_DIR / "status.json"
BACKUP_DIR = WORK_DIR / "backup"
EXTRACT_DIR = WORK_DIR / "new"
LOG_FILE = WORK_DIR / "update.log"

#
# Diese Pfade gehören dem Nutzer, nicht dem Programm. Sie werden weder
# überschrieben noch gesichert (teils sehr groß) - ein Update darf
# weder Aufnahmen noch die PIN oder die WLAN-Einstellungen verlieren.
#
PRESERVE = {
    "config/local.yaml",
    "config/state.json",
    "recordings",
    "music",
    "certs",
    ".venv",
    ".git",
}

#
# Ohne diese Bestandteile ist es kein brauchbares XRack - dann lieber
# gar nicht erst anfangen.
#
REQUIRED = [
    "main.py",
    "requirements.txt",
    "core",
    "web",
    "writer",
    "reader",
    "recorder",
    "player",
    "audio",
]

HEALTH_ATTEMPTS = 45
HEALTH_INTERVAL = 2.0


def log(message: str) -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n")


def write_status(
    state: str,
    step: str,
    message: str = "",
    needs_install_script: bool = False,
    needs_dependencies: bool = False,
) -> None:
    """
    Schreibt den Fortschritt für das Frontend. Bewusst außerhalb des
    Installationsverzeichnisses, damit der Dateitausch die Statusdatei
    nicht mitten im Vorgang unter den Füßen wegzieht.
    """

    WORK_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "state": state,
        "step": step,
        "message": message,
        "needs_install_script": needs_install_script,
        "needs_dependencies": needs_dependencies,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    temporary = STATUS_FILE.with_suffix(".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        json.dump(payload, file)

    temporary.replace(STATUS_FILE)

    STATUS_FILE.chmod(0o644)


def is_preserved(relative: Path) -> bool:
    """
    True, wenn der Pfad selbst oder einer seiner übergeordneten Ordner
    zu den geschützten Nutzerdaten gehört.
    """

    parts = relative.as_posix()

    for preserved in PRESERVE:
        if parts == preserved or parts.startswith(preserved + "/"):
            return True

    return False


def copy_tree(source: Path, target: Path) -> None:
    """
    Kopiert `source` nach `target` und lässt dabei die geschützten
    Nutzerdaten aus. Vorhandene Dateien werden überschrieben, nicht
    mehr enthaltene bleiben stehen (ein Update soll nichts löschen,
    was es nicht sicher beurteilen kann).
    """

    for root, directories, files in os.walk(source):

        root_path = Path(root)
        relative_root = root_path.relative_to(source)

        #
        # Geschützte Ordner gar nicht erst betreten.
        #
        directories[:] = [
            directory
            for directory in directories
            if not is_preserved(relative_root / directory)
        ]

        destination_root = target / relative_root
        destination_root.mkdir(parents=True, exist_ok=True)

        for name in files:

            if is_preserved(relative_root / name):
                continue

            shutil.copy2(root_path / name, destination_root / name)


def chown_tree(path: Path, user: str) -> None:
    """Gibt das Verzeichnis wieder dem Dienstbenutzer."""

    try:
        entry = pwd.getpwnam(user)
    except KeyError:
        log(f"Benutzer {user} nicht gefunden - Eigentümer bleibt unverändert")
        return

    for root, directories, files in os.walk(path):

        for name in directories + files:
            try:
                os.chown(Path(root) / name, entry.pw_uid, entry.pw_gid, follow_symlinks=False)
            except OSError:
                pass

    try:
        os.chown(path, entry.pw_uid, entry.pw_gid)
    except OSError:
        pass


def find_source_directory(extracted: Path) -> Path | None:
    """
    GitHub-ZIPs enthalten einen einzelnen Ordner (z.B. "XRack-main").
    Liefert den Ordner, in dem main.py liegt.
    """

    if (extracted / "main.py").is_file():
        return extracted

    for candidate in sorted(extracted.iterdir()):
        if candidate.is_dir() and (candidate / "main.py").is_file():
            return candidate

    return None


def check_health(port: int) -> bool:
    """
    Fragt die eigene Weboberfläche ab. XRack läuft je nach Installation
    mit oder ohne TLS (selbstsigniert), darum beide Varianten versuchen.
    """

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    for url in (
        f"https://127.0.0.1:{port}/api/status",
        f"http://127.0.0.1:{port}/api/status",
    ):
        try:
            with urllib.request.urlopen(url, timeout=3, context=context) as response:
                if response.status == 200:
                    return True
        except Exception:
            continue

    return False


def wait_for_health(port: int) -> bool:
    for attempt in range(1, HEALTH_ATTEMPTS + 1):

        if check_health(port):
            log(f"Gesundheitsprüfung erfolgreich nach {attempt} Versuch(en)")
            return True

        time.sleep(HEALTH_INTERVAL)

    log("Gesundheitsprüfung fehlgeschlagen")
    return False


def restart_service() -> bool:
    try:
        subprocess.run(
            ["systemctl", "restart", "xrack.service"],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return True
    except (subprocess.SubprocessError, OSError) as exc:
        log(f"Neustart fehlgeschlagen: {exc}")
        return False


def rollback(reason: str, install_dir: Path, service_user: str, port: int) -> int:
    """
    Holt den gesicherten Stand zurück. Das ist der Grund, warum dieses
    Feature überhaupt vertretbar ist: ohne Rückfall stünde im Fehlerfall
    ein stummer Pi im Rack.
    """

    log(f"Rückfall wird eingeleitet: {reason}")

    write_status(
        "rolling_back",
        "rückfall",
        "Update fehlgeschlagen - alter Stand wird zurückgeholt...",
    )

    if not BACKUP_DIR.is_dir():
        write_status(
            "failed",
            "fehler",
            f"Update fehlgeschlagen und keine Sicherung vorhanden: {reason}",
        )
        return 1

    try:
        copy_tree(BACKUP_DIR, install_dir)
        chown_tree(install_dir, service_user)
    except Exception as exc:
        log(f"Rückfall fehlgeschlagen: {exc}")
        write_status(
            "failed",
            "fehler",
            f"Update fehlgeschlagen ({reason}) und der Rückfall ebenfalls. "
            f"Bitte per SSH nachsehen: {LOG_FILE}",
        )
        return 1

    restart_service()

    if wait_for_health(port):
        write_status(
            "rolled_back",
            "fertig",
            f"Update fehlgeschlagen ({reason}) - der vorherige Stand läuft wieder.",
        )
    else:
        write_status(
            "failed",
            "fehler",
            f"Update fehlgeschlagen ({reason}) und der Rückfall hat nicht "
            f"angeschlagen. Bitte per SSH nachsehen: {LOG_FILE}",
        )

    return 1


def run_update(
    zip_file: Path,
    install_dir: Path,
    service_user: str,
    port: int,
) -> int:

    log(f"Update gestartet: {zip_file} -> {install_dir}")

    # ------------------------------------------------------------
    # 1. ZIP prüfen
    # ------------------------------------------------------------

    write_status("running", "prüfen", "ZIP-Datei wird geprüft...")

    if EXTRACT_DIR.exists():
        shutil.rmtree(EXTRACT_DIR, ignore_errors=True)

    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_file) as archive:
            archive.extractall(EXTRACT_DIR)
    except (zipfile.BadZipFile, OSError) as exc:
        log(f"Entpacken fehlgeschlagen: {exc}")
        write_status(
            "failed",
            "fehler",
            "ZIP-Datei konnte nicht entpackt werden (beschädigt?).",
        )
        return 1

    source_dir = find_source_directory(EXTRACT_DIR)

    if source_dir is None:
        write_status(
            "failed",
            "fehler",
            "In der ZIP-Datei wurde kein XRack gefunden (main.py fehlt).",
        )
        return 1

    for required in REQUIRED:
        if not (source_dir / required).exists():
            write_status(
                "failed",
                "fehler",
                f"Die ZIP-Datei sieht unvollständig aus ({required} fehlt).",
            )
            return 1

    log(f"Quellverzeichnis: {source_dir}")

    # ------------------------------------------------------------
    # 2. Änderungen erkennen, die ein reines Kopieren nicht abdeckt
    # ------------------------------------------------------------

    def differs(name: str) -> bool:
        new = source_dir / name
        old = install_dir / name

        if not new.is_file():
            return False

        if not old.is_file():
            return True

        return new.read_bytes() != old.read_bytes()

    needs_dependencies = differs("requirements.txt")
    needs_install_script = differs("install.sh")

    if needs_dependencies:
        log("requirements.txt hat sich geändert")

    if needs_install_script:
        log("install.sh hat sich geändert - strukturelle Änderungen brauchen einen manuellen Lauf")

    # ------------------------------------------------------------
    # 3. Sichern
    # ------------------------------------------------------------

    write_status("running", "sichern", "Aktueller Stand wird gesichert...")

    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR, ignore_errors=True)

    try:
        copy_tree(install_dir, BACKUP_DIR)
    except Exception as exc:
        log(f"Sicherung fehlgeschlagen: {exc}")
        write_status(
            "failed",
            "fehler",
            "Sicherung fehlgeschlagen - Update abgebrochen, "
            "es wurde nichts verändert.",
        )
        return 1

    log(f"Sicherung abgelegt unter {BACKUP_DIR}")

    # ------------------------------------------------------------
    # 4. Dateien tauschen
    # ------------------------------------------------------------

    write_status("running", "übertragen", "Neue Dateien werden übertragen...")

    try:
        copy_tree(source_dir, install_dir)
        chown_tree(install_dir, service_user)

        for script in (install_dir / "scripts").glob("*"):
            if script.suffix in (".sh", ".py"):
                script.chmod(0o755)

    except Exception as exc:
        log(f"Übertragen fehlgeschlagen: {exc}")
        return rollback(
            "Dateien konnten nicht übertragen werden",
            install_dir,
            service_user,
            port,
        )

    log("Dateien übertragen")

    # ------------------------------------------------------------
    # 5. Abhängigkeiten (nur wenn nötig - und nur mit Netz)
    # ------------------------------------------------------------

    pip = install_dir / ".venv" / "bin" / "pip"

    if needs_dependencies and pip.is_file():

        write_status(
            "running",
            "pakete",
            "Neue Abhängigkeiten werden installiert...",
        )

        try:
            subprocess.run(
                [
                    "runuser", "-u", service_user, "--",
                    str(pip), "install", "-q",
                    "-r", str(install_dir / "requirements.txt"),
                ],
                check=True,
                capture_output=True,
                timeout=600,
            )

            needs_dependencies = False
            log("Abhängigkeiten installiert")

        except (subprocess.SubprocessError, OSError) as exc:
            log(f"pip fehlgeschlagen (kein Netz?): {exc}")

    # ------------------------------------------------------------
    # 6. Neu starten + Gesundheitsprüfung
    # ------------------------------------------------------------

    write_status("running", "neustart", "Dienst wird neu gestartet...")

    if not restart_service():
        return rollback(
            "Dienst ließ sich nicht neu starten",
            install_dir,
            service_user,
            port,
        )

    write_status(
        "running",
        "prüfen",
        "Warte darauf, dass die Weboberfläche wieder antwortet...",
    )

    if not wait_for_health(port):
        return rollback(
            "die Weboberfläche antwortet nach dem Update nicht",
            install_dir,
            service_user,
            port,
        )

    # ------------------------------------------------------------
    # 7. Fertig
    # ------------------------------------------------------------

    message = "Update erfolgreich."

    if needs_install_script:
        message += (
            " Achtung: install.sh hat sich geändert - bitte einmal manuell "
            "ausführen, sonst fehlen Systemeinstellungen."
        )

    if needs_dependencies:
        message += (
            " Achtung: Es werden neue Python-Pakete gebraucht, die ohne "
            "Internetverbindung nicht installiert werden konnten."
        )

    write_status(
        "success",
        "fertig",
        message,
        needs_install_script=needs_install_script,
        needs_dependencies=needs_dependencies,
    )

    log("Update abgeschlossen")

    return 0


def main() -> int:

    parser = argparse.ArgumentParser(description="XRack aus einer ZIP-Datei aktualisieren.")
    parser.add_argument("zip_file")
    parser.add_argument("install_dir")
    parser.add_argument("service_user")
    parser.add_argument("port", nargs="?", default="8080")
    parser.add_argument("--detached", action="store_true", help=argparse.SUPPRESS)

    arguments = parser.parse_args()

    zip_file = Path(arguments.zip_file)
    install_dir = Path(arguments.install_dir)

    try:
        port = int(arguments.port)
    except ValueError:
        port = 8080

    if not arguments.detached:

        if not zip_file.is_file():
            print(f"ZIP-Datei nicht gefunden: {zip_file}", file=sys.stderr)
            return 3

        if not install_dir.is_dir():
            print(f"Installationsverzeichnis nicht gefunden: {install_dir}", file=sys.stderr)
            return 3

        WORK_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.unlink(missing_ok=True)

        write_status("running", "start", "Update wird vorbereitet...")

        #
        # An einen eigenständigen systemd-Task übergeben, damit der
        # Neustart des Dienstes den Updater nicht mit erschlägt.
        #
        subprocess.Popen(
            [
                "systemd-run",
                f"--unit=xrack-update-{os.getpid()}",
                "--collect",
                sys.executable,
                os.path.abspath(__file__),
                str(zip_file),
                str(install_dir),
                arguments.service_user,
                str(port),
                "--detached",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return 0

    return run_update(zip_file, install_dir, arguments.service_user, port)


if __name__ == "__main__":
    sys.exit(main())
