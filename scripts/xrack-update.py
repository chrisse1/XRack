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

#
# Quelle fuer das Update aus dem Internet. codeload liefert die ZIP
# direkt aus; github.com/.../archive/... leitet nur dorthin weiter.
#
GITHUB_ZIP = "https://codeload.github.com/{repository}/zip/refs/heads/{branch}"

DOWNLOAD_FILE = WORK_DIR / "download.zip"

#
# Eine ZIP mit dem Quelltext liegt bei XRack im niedrigen einstelligen
# Megabyte-Bereich. Die Grenze faengt den Fall ab, dass hinter der
# Adresse etwas voellig anderes steckt - heruntergeladen wird ohnehin
# stueckweise, es landet also nie mehr davon im Speicher.
#
MAX_DOWNLOAD = 200 * 1024 * 1024

DOWNLOAD_TIMEOUT = 60


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
    needs_git_reset: bool = False,
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
        "needs_git_reset": needs_git_reset,
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


def download_package(repository: str, branch: str) -> Path | None:
    """
    Laedt den aktuellen Stand als ZIP von GitHub.

    Danach geht es denselben Weg wie beim USB-Stick weiter: dieselbe
    Pruefung, dieselbe Sicherung, derselbe Rueckfall. Ein zweiter,
    eigener Update-Ablauf fuer den Online-Weg waere ein zweiter Ablauf,
    der schiefgehen kann - und der zweite waere der, den seltener
    jemand ausprobiert.

    Bewusst kein "git pull": Der Rueckfall dieses Skripts beruht auf
    einer Sicherungskopie und einem Dateitausch. Git haette einen
    eigenen, voellig anderen Rueckfallweg - und bei lokal geaenderten
    Dateien bliebe es ueberhaupt stehen.
    """

    url = GITHUB_ZIP.format(repository=repository, branch=branch)

    log(f"Lade herunter: {url}")

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_FILE.unlink(missing_ok=True)

    try:

        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:

            if response.status != 200:
                log(f"Download fehlgeschlagen: HTTP {response.status}")
                return None

            geladen = 0

            with DOWNLOAD_FILE.open("wb") as file:

                while True:

                    block = response.read(64 * 1024)

                    if not block:
                        break

                    geladen += len(block)

                    if geladen > MAX_DOWNLOAD:
                        log("Download abgebrochen: unerwartet gross")
                        DOWNLOAD_FILE.unlink(missing_ok=True)
                        return None

                    file.write(block)

    except Exception as exc:
        log(f"Download fehlgeschlagen: {exc}")
        DOWNLOAD_FILE.unlink(missing_ok=True)
        return None

    log(f"Heruntergeladen: {geladen} Byte")

    return DOWNLOAD_FILE


def git_branch(install_dir: Path) -> str | None:
    """
    Liefert den ausgecheckten Branch - oder None, wenn das Verzeichnis
    keine Git-Arbeitskopie ist, git fehlt oder der Kopf abgetrennt ist.
    """

    if not (install_dir / ".git").is_dir():
        return None

    try:

        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={install_dir}",
                "-C",
                str(install_dir),
                "rev-parse",
                "--abbrev-ref",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

    except (OSError, subprocess.SubprocessError) as exc:
        log(f"git nicht verfügbar: {exc}")
        return None

    if result.returncode != 0:
        log(f"git rev-parse fehlgeschlagen: {result.stderr.strip()}")
        return None

    branch = result.stdout.strip()

    #
    # "HEAD" heißt: abgetrennter Kopf, also kein Branch. Dann gibt es
    # nichts, das man sinnvoll nachziehen könnte.
    #
    return None if branch in ("", "HEAD") else branch


def align_git(install_dir: Path, branch: str, service_user: str) -> bool:
    """
    Zieht die Git-Arbeitskopie auf den gerade eingespielten Stand nach.

    Ohne das zeigt HEAD weiter auf den alten Commit, während die Dateien
    schon die neuen sind - ein späteres "git pull" bricht dann mit
    "local changes would be overwritten" ab.

    Zwei bewusste Einschränkungen:

    Erstens läuft das nur, wenn der ausgecheckte Branch derselbe ist,
    aus dem das Update kam. Wer auf einem Entwicklungszweig sitzt und
    aus main aktualisiert, will seinen Zweig nicht auf main gezogen
    bekommen - da ist der bloße Hinweis richtig.

    Zweitens steht das hier ganz am Ende, nach bestandener
    Gesundheitsprüfung, und nicht mitten im Ablauf. Der Rückfall beruht
    auf Sicherungskopie und Dateitausch; wäre git Teil davon, müsste
    auch der Rückfall git zurückdrehen, und aus einem Weg würden zwei,
    die zusammenpassen müssen. Scheitert das Nachziehen hier, ist
    nichts kaputt - es bleibt beim Hinweis.

    Der Preis dieser Reihenfolge: Zwischen dem Herunterladen der ZIP
    und diesem Zeitpunkt könnte jemand auf den Branch pushen, dann
    holte das "reset" einen minimal neueren Stand als den geprüften.
    Das Fenster ist Sekunden groß und betrifft nur ein Projekt, auf das
    während des eigenen Updates jemand anders pusht.
    """

    def git(*arguments) -> subprocess.CompletedProcess | None:

        try:

            return subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={install_dir}",
                    "-C",
                    str(install_dir),
                    *arguments,
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

        except (OSError, subprocess.SubprocessError) as exc:
            log(f"git {' '.join(arguments)} fehlgeschlagen: {exc}")
            return None

    result = git("fetch", "origin", branch)

    if result is None or result.returncode != 0:
        log(f"git fetch fehlgeschlagen: {result.stderr.strip() if result else '-'}")
        return False

    #
    # FETCH_HEAD statt origin/<branch>: Das setzt "git fetch" immer,
    # unabhängig davon, wie die Verfolgungszweige eingerichtet sind.
    #
    result = git("reset", "--hard", "FETCH_HEAD")

    if result is None or result.returncode != 0:
        log(f"git reset fehlgeschlagen: {result.stderr.strip() if result else '-'}")
        return False

    log(f"Git-Arbeitskopie auf {branch} nachgezogen")

    #
    # git lief als root, die Dateien gehören jetzt root. Zurückgeben,
    # sonst kann der Dienstbenutzer sein eigenes Verzeichnis nicht mehr
    # verwalten.
    #
    chown_tree(install_dir, service_user)

    return True


def run_update(
    zip_file: Path,
    install_dir: Path,
    service_user: str,
    port: int,
    branch: str = "",
) -> int:
    """
    `branch` ist nur beim Weg über das Internet gesetzt - nur dort ist
    bekannt, welcher Stand eingespielt wurde, und nur dann lässt sich
    eine Git-Arbeitskopie sinnvoll nachziehen. Beim USB-Stick bringt
    der Nutzer irgendeine ZIP mit; welchem Commit die entspricht, weiß
    hier niemand.
    """

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

        #
        # Die systemd-Unit des Access Points neu schreiben.
        #
        # Sie wird sonst ausschliesslich beim Anlegen des Access
        # Points geschrieben (xrack-ap-setup.sh). Eine bestehende
        # Installation bekaeme neue ExecStartPre-Zeilen also nie zu
        # sehen - zum Beispiel den Abgleich der Geraetenamen, der
        # verhindert, dass nach einem Neustart der Access Point auf
        # dem eingebauten Chip landet.
        #
        # Tut nichts, wenn gar kein Access Point eingerichtet ist,
        # und darf folgenlos scheitern: Ein Update soll daran nicht
        # haengenbleiben.
        #
        try:

            subprocess.run(
                [
                    str(install_dir / "scripts" / "xrack-ap-setup.sh"),
                    "--refresh-unit",
                ],
                capture_output=True,
                timeout=30,
            )

        except Exception as exc:
            log(f"Access-Point-Unit nicht aktualisiert: {exc}")

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

    #
    # Ist das Installationsverzeichnis eine Git-Arbeitskopie, laeuft
    # git jetzt hinterher: Der Updater tauscht die Dateien direkt aus
    # und laesst .git bewusst unangetastet (siehe PRESERVE), HEAD zeigt
    # also weiter auf den alten Stand. Ein spaeteres "git pull" bricht
    # deshalb mit "local changes would be overwritten" ab. Das ist kein
    # Schaden - nur unerwartet, wenn man es nicht weiss.
    #
    # Bewusst nur ein Hinweis und kein automatisches "git reset --hard":
    # Das wuerde alles verwerfen, was auf dem Geraet von Hand geaendert
    # wurde. Diese Entscheidung gehoert dem Nutzer, nicht dem Updater.
    #
    needs_git_reset = (install_dir / ".git").is_dir()

    ausgecheckt = None

    if needs_git_reset:

        log("Installationsverzeichnis ist eine Git-Arbeitskopie")

        ausgecheckt = git_branch(install_dir)

        #
        # Nachziehen nur, wenn derselbe Branch ausgecheckt ist, aus dem
        # das Update kam. Sitzt dort ein Entwicklungszweig und kam das
        # Update aus main, wäre ein "reset" ein Zweigwechsel hinter dem
        # Rücken des Nutzers - dann bleibt es beim Hinweis.
        #
        if branch and ausgecheckt == branch:

            if align_git(install_dir, branch, service_user):
                needs_git_reset = False

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

    if needs_git_reset:

        message += (
            " Hinweis: Das Verzeichnis ist eine Git-Arbeitskopie. XRack "
            "tauscht die Dateien direkt aus, git weiß davon nichts - ein "
            "späteres \"git pull\" schlägt deshalb fehl."
        )

        if ausgecheckt and branch and ausgecheckt != branch:
            #
            # Der haeufigste Fall: Auf dem Geraet liegt ein
            # Entwicklungszweig, aktualisiert wurde aus main. Dann ist
            # der genaue Befehl hilfreicher als ein allgemeiner Rat.
            #
            message += (
                f" Ausgecheckt ist \"{ausgecheckt}\", eingespielt wurde "
                f"\"{branch}\". Zurück zum Entwickeln: "
                f"\"git reset --hard origin/{ausgecheckt}\" "
                f"(nach einem \"git fetch\")."
            )
        else:
            message += " Mit \"git reset --hard\" zieht man git wieder nach."

    write_status(
        "success",
        "fertig",
        message,
        needs_install_script=needs_install_script,
        needs_dependencies=needs_dependencies,
        needs_git_reset=needs_git_reset,
    )

    log("Update abgeschlossen")

    return 0


def main() -> int:

    parser = argparse.ArgumentParser(
        description="XRack aus einer ZIP-Datei aktualisieren."
    )
    parser.add_argument("install_dir")
    parser.add_argument("service_user")
    parser.add_argument("port", nargs="?", default="8080")

    #
    # Genau eine der beiden Quellen: eine ZIP-Datei (USB-Stick) oder
    # ein GitHub-Verzeichnis (Internet). Ab da laufen beide Wege durch
    # denselben Ablauf.
    #
    parser.add_argument("--zip", dest="zip_file", default="")
    parser.add_argument("--repository", default="")
    parser.add_argument("--branch", default="main")

    parser.add_argument("--detached", action="store_true", help=argparse.SUPPRESS)

    arguments = parser.parse_args()

    install_dir = Path(arguments.install_dir)

    try:
        port = int(arguments.port)
    except ValueError:
        port = 8080

    if arguments.zip_file and arguments.repository:
        print(
            "--zip und --repository schließen sich aus: entweder die "
            "ZIP-Datei vom Stick oder der Download von GitHub.",
            file=sys.stderr,
        )
        return 3

    if not arguments.zip_file and not arguments.repository:
        print(
            "Es fehlt die Quelle: --zip <Datei> oder --repository <Nutzer/Projekt>.",
            file=sys.stderr,
        )
        return 3

    zip_file = Path(arguments.zip_file) if arguments.zip_file else None

    if not arguments.detached:

        if zip_file is not None and not zip_file.is_file():
            print(f"ZIP-Datei nicht gefunden: {zip_file}", file=sys.stderr)
            return 3

        if not install_dir.is_dir():
            print(f"Installationsverzeichnis nicht gefunden: {install_dir}", file=sys.stderr)
            return 3

        WORK_DIR.mkdir(parents=True, exist_ok=True)
        LOG_FILE.unlink(missing_ok=True)

        write_status("running", "start", "Update wird vorbereitet...")

        weitergabe = ["--zip", str(zip_file)] if zip_file is not None else [
            "--repository",
            arguments.repository,
            "--branch",
            arguments.branch,
        ]

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
                str(install_dir),
                arguments.service_user,
                str(port),
                *weitergabe,
                "--detached",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        return 0

    #
    # Ab hier läuft der eigenständige Task. Beim Online-Weg wird die
    # ZIP erst jetzt geholt - der Download dauert und darf den
    # aufrufenden Dienst nicht blockieren.
    #
    if zip_file is None:

        write_status("running", "laden", "Update wird heruntergeladen...")

        zip_file = download_package(arguments.repository, arguments.branch)

        if zip_file is None:
            write_status(
                "failed",
                "fehler",
                "Der Download von GitHub ist fehlgeschlagen. "
                "Besteht eine Internetverbindung?",
            )
            return 1

    #
    # Der Branch wird nur beim Online-Weg weitergereicht - beim
    # USB-Stick ist unbekannt, welchem Stand die ZIP entspricht.
    #
    return run_update(
        zip_file,
        install_dir,
        arguments.service_user,
        port,
        branch=arguments.branch if arguments.repository else "",
    )


if __name__ == "__main__":
    sys.exit(main())
