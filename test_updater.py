"""
Prüft den Updater (scripts/xrack-update.py) in einer Sandbox - also
ohne echten Dienst, echten systemd oder echtes Netz.

Der wichtigste Teil ist der Rückfall: Wenn das Update einen kaputten
Stand hinterlässt, muss der alte Stand automatisch zurückkommen. Ohne
diese Zusicherung wäre das Feature ein Fußschuss - im Fehlerfall stünde
sonst ein stummer Pi im Rack.

Ebenso wichtig: Nutzerdaten (Aufnahmen, PIN, WLAN-Einstellungen) dürfen
ein Update unter keinen Umständen verlieren.
"""

import importlib.util
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

#
# Das Skript liegt in scripts/ und ist kein Paketmodul - direkt laden.
#
spec = importlib.util.spec_from_file_location(
    "xrack_update",
    Path(__file__).parent / "scripts" / "xrack-update.py",
)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def build_install(directory: Path) -> None:
    """Legt eine minimale, realistisch bestückte Installation an."""

    for name in updater.REQUIRED:

        target = directory / name

        if "." in name:
            target.write_text(f"alt: {name}\n", encoding="utf-8")
        else:
            target.mkdir(parents=True, exist_ok=True)
            (target / "__init__.py").write_text("# alt\n", encoding="utf-8")

    (directory / "core" / "application.py").write_text("# alte Fassung\n", encoding="utf-8")

    #
    # Nutzerdaten, die das Update auf keinen Fall anfassen darf
    #
    (directory / "config").mkdir(exist_ok=True)
    (directory / "config" / "local.yaml").write_text("pin_hash: geheim\n", encoding="utf-8")
    (directory / "config" / "state.json").write_text('{"record_channels": 18}', encoding="utf-8")
    (directory / "config" / "default.yaml").write_text("version: 1.0.0\n", encoding="utf-8")

    (directory / "recordings").mkdir(exist_ok=True)
    (directory / "recordings" / "Soundcheck-1_s.w64").write_bytes(b"AUFNAHME")

    (directory / "music").mkdir(exist_ok=True)
    (directory / "music" / "song.mp3").write_bytes(b"MUSIK")

    (directory / "certs").mkdir(exist_ok=True)
    (directory / "certs" / "cert.pem").write_text("ZERTIFIKAT\n", encoding="utf-8")

    (directory / ".venv").mkdir(exist_ok=True)
    (directory / ".venv" / "marker").write_text("venv\n", encoding="utf-8")


def build_zip(path: Path, top_level: str = "XRack-main", complete: bool = True) -> None:
    """Baut eine ZIP wie der GitHub-Download - mit Ordner obendrauf."""

    staging = Path(tempfile.mkdtemp()) / top_level
    staging.mkdir(parents=True)

    names = updater.REQUIRED if complete else ["main.py", "core"]

    for name in names:
        target = staging / name
        if "." in name:
            target.write_text(f"neu: {name}\n", encoding="utf-8")
        else:
            target.mkdir(parents=True, exist_ok=True)
            (target / "__init__.py").write_text("# neu\n", encoding="utf-8")

    (staging / "core" / "application.py").write_text("# NEUE Fassung\n", encoding="utf-8")
    (staging / "core" / "brandneu.py").write_text("# ganz neu\n", encoding="utf-8")

    (staging / "config").mkdir(exist_ok=True)
    (staging / "config" / "default.yaml").write_text("version: 2.0.0\n", encoding="utf-8")

    #
    # Auch die ZIP enthält (wie GitHub) keine Nutzerdaten - aber wir
    # legen bewusst eine local.yaml hinein, um zu prüfen, dass sie
    # NICHT übernommen wird.
    #
    (staging / "config" / "local.yaml").write_text("pin_hash: FALSCH\n", encoding="utf-8")

    with zipfile.ZipFile(path, "w") as archive:
        for item in staging.rglob("*"):
            archive.write(item, item.relative_to(staging.parent))


scratch = Path(tempfile.mkdtemp(prefix="xrack_update_test_"))

try:

    # ----------------------------------------------------------------
    # 1. Geschützte Pfade werden erkannt
    # ----------------------------------------------------------------

    protected = [
        "config/local.yaml",
        "config/state.json",
        "recordings",
        "recordings/Soundcheck-1_s.w64",
        "music/Album/song.mp3",
        "certs/cert.pem",
        ".venv/bin/python",
    ]

    for item in protected:
        assert updater.is_preserved(Path(item)), f"{item} müsste geschützt sein"

    for item in ["main.py", "core/application.py", "config/default.yaml", "web/i18n.py"]:
        assert not updater.is_preserved(Path(item)), f"{item} dürfte nicht geschützt sein"

    print("OK: Nutzerdaten werden als geschützt erkannt, Programmdateien nicht")

    # ----------------------------------------------------------------
    # 2. copy_tree() lässt Nutzerdaten unangetastet
    # ----------------------------------------------------------------

    install = scratch / "install"
    install.mkdir()
    build_install(install)

    source = scratch / "source"
    source.mkdir()
    (source / "config").mkdir()
    (source / "config" / "local.yaml").write_text("pin_hash: FALSCH\n", encoding="utf-8")
    (source / "config" / "default.yaml").write_text("version: 2.0.0\n", encoding="utf-8")
    (source / "recordings").mkdir()
    (source / "recordings" / "fremd.w64").write_bytes(b"DARF NICHT ANKOMMEN")
    (source / "main.py").write_text("neu: main.py\n", encoding="utf-8")

    updater.copy_tree(source, install)

    assert (install / "config" / "local.yaml").read_text() == "pin_hash: geheim\n", (
        "local.yaml wurde überschrieben - PIN und WLAN-Einstellungen wären weg!"
    )
    assert (install / "config" / "state.json").read_text() == '{"record_channels": 18}'
    assert (install / "recordings" / "Soundcheck-1_s.w64").read_bytes() == b"AUFNAHME"
    assert not (install / "recordings" / "fremd.w64").exists(), (
        "Fremde Datei ist in recordings/ gelandet"
    )
    assert (install / ".venv" / "marker").exists()
    assert (install / "certs" / "cert.pem").exists()

    # Programmdateien dagegen schon
    assert (install / "main.py").read_text() == "neu: main.py\n"
    assert (install / "config" / "default.yaml").read_text() == "version: 2.0.0\n"

    print("OK: copy_tree() überschreibt Programmdateien, aber keine Nutzerdaten")

    shutil.rmtree(install)

    # ----------------------------------------------------------------
    # 3. ZIP-Prüfung: Quellordner finden und Vollständigkeit
    # ----------------------------------------------------------------

    extracted = scratch / "extracted"
    extracted.mkdir()

    zip_path = scratch / "XRack-main.zip"
    build_zip(zip_path)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(extracted)

    found = updater.find_source_directory(extracted)
    assert found is not None, "Quellordner in der ZIP nicht gefunden"
    assert found.name == "XRack-main", f"Falscher Quellordner: {found}"

    print("OK: Quellordner in der GitHub-ZIP wird gefunden")

    # Unvollständige ZIP
    extracted_bad = scratch / "extracted_bad"
    extracted_bad.mkdir()

    bad_zip = scratch / "kaputt.zip"
    build_zip(bad_zip, complete=False)

    with zipfile.ZipFile(bad_zip) as archive:
        archive.extractall(extracted_bad)

    bad_source = updater.find_source_directory(extracted_bad)
    assert bad_source is not None

    missing = [name for name in updater.REQUIRED if not (bad_source / name).exists()]
    assert missing, "Unvollständige ZIP müsste auffallen"

    print(f"OK: Unvollständige ZIP fällt auf ({len(missing)} Bestandteile fehlen)")

    # Ein Ordner ganz ohne XRack
    empty = scratch / "leer"
    (empty / "irgendwas").mkdir(parents=True)
    assert updater.find_source_directory(empty) is None

    print("OK: ZIP ohne XRack wird abgelehnt")

    # ----------------------------------------------------------------
    # 4. Voller Durchlauf mit erzwungenem Rückfall
    #
    # Das ist der Kern: Der Dienst kommt nach dem Update nicht hoch
    # (Gesundheitsprüfung schlägt fehl) - der alte Stand muss
    # automatisch zurückkommen.
    # ----------------------------------------------------------------

    install = scratch / "install2"
    install.mkdir()
    build_install(install)

    work = scratch / "work"
    updater.WORK_DIR = work
    updater.STATUS_FILE = work / "status.json"
    updater.BACKUP_DIR = work / "backup"
    updater.EXTRACT_DIR = work / "new"
    updater.LOG_FILE = work / "update.log"
    updater.DOWNLOAD_FILE = work / "download.zip"

    # Systemaufrufe und Netz durch Attrappen ersetzen
    updater.restart_service = lambda: True
    updater.chown_tree = lambda path, user: None
    updater.HEALTH_ATTEMPTS = 2
    updater.HEALTH_INTERVAL = 0.01

    #
    # Realistischer Fehlerfall: die NEUE Fassung antwortet nicht, der
    # zurückgeholte alte Stand danach schon. Die ersten zwei Abfragen
    # (= ein voller wait_for_health-Durchlauf) schlagen also fehl,
    # danach ist der Dienst wieder da.
    #
    health_calls = {"count": 0}

    def flaky_health(port):
        health_calls["count"] += 1
        return health_calls["count"] > updater.HEALTH_ATTEMPTS

    updater.check_health = flaky_health

    result = updater.run_update(zip_path, install, "xrack", 8080)

    assert result == 1, "Fehlgeschlagenes Update müsste einen Fehler melden"

    import json
    status = json.loads((work / "status.json").read_text(encoding="utf-8"))

    assert status["state"] == "rolled_back", (
        f"Erwartet 'rolled_back', bekommen '{status['state']}' - "
        f"der automatische Rückfall hat nicht funktioniert!"
    )

    # Der alte Stand muss wieder da sein
    assert (install / "core" / "application.py").read_text() == "# alte Fassung\n", (
        "Nach dem Rückfall steht immer noch die neue Fassung da"
    )
    assert (install / "config" / "default.yaml").read_text() == "version: 1.0.0\n", (
        "Nach dem Rückfall ist die Version nicht zurückgesetzt"
    )

    # Und die Nutzerdaten haben den ganzen Vorgang überlebt
    assert (install / "config" / "local.yaml").read_text() == "pin_hash: geheim\n"
    assert (install / "recordings" / "Soundcheck-1_s.w64").read_bytes() == b"AUFNAHME"
    assert (install / "music" / "song.mp3").read_bytes() == b"MUSIK"

    print("OK: Kaputtes Update fällt automatisch auf den alten Stand zurück")
    print("OK: Nutzerdaten überleben auch ein fehlgeschlagenes Update")

    # ----------------------------------------------------------------
    # 5. Voller Durchlauf, der gelingt
    # ----------------------------------------------------------------

    install = scratch / "install3"
    install.mkdir()
    build_install(install)

    shutil.rmtree(work, ignore_errors=True)
    updater.check_health = lambda port: True  # Dienst kommt hoch

    result = updater.run_update(zip_path, install, "xrack", 8080)

    assert result == 0, "Erfolgreiches Update müsste 0 liefern"

    status = json.loads((work / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "success", f"Erwartet 'success', bekommen '{status['state']}'"

    # Neue Fassung ist da
    assert (install / "core" / "application.py").read_text() == "# NEUE Fassung\n"
    assert (install / "core" / "brandneu.py").exists(), "Neue Datei fehlt"
    assert (install / "config" / "default.yaml").read_text() == "version: 2.0.0\n"

    # Nutzerdaten unberührt
    assert (install / "config" / "local.yaml").read_text() == "pin_hash: geheim\n", (
        "Das Update hat die PIN/WLAN-Einstellungen überschrieben!"
    )
    assert (install / "config" / "state.json").read_text() == '{"record_channels": 18}'
    assert (install / "recordings" / "Soundcheck-1_s.w64").read_bytes() == b"AUFNAHME"
    assert (install / "music" / "song.mp3").read_bytes() == b"MUSIK"
    assert (install / ".venv" / "marker").exists(), "Die virtuelle Umgebung wurde angefasst"
    assert (install / "certs" / "cert.pem").exists()

    print("OK: Erfolgreiches Update spielt die neue Fassung ein")
    print("OK: PIN, Einstellungen, Aufnahmen, Musik und venv bleiben unangetastet")

    # ----------------------------------------------------------------
    # 6. Beschädigte ZIP bricht ab, ohne etwas zu verändern
    # ----------------------------------------------------------------

    install = scratch / "install4"
    install.mkdir()
    build_install(install)

    broken = scratch / "beschaedigt.zip"
    broken.write_bytes(b"das ist gar keine ZIP-Datei")

    shutil.rmtree(work, ignore_errors=True)

    result = updater.run_update(broken, install, "xrack", 8080)

    assert result == 1
    status = json.loads((work / "status.json").read_text(encoding="utf-8"))
    assert status["state"] == "failed"

    assert (install / "core" / "application.py").read_text() == "# alte Fassung\n", (
        "Eine beschädigte ZIP hat trotzdem Dateien verändert"
    )

    print("OK: Beschädigte ZIP bricht ab, ohne etwas zu verändern")

    # ----------------------------------------------------------------
    # 7. Schlimmster Fall: auch der Rückfall kommt nicht hoch
    #
    # Dann kann XRack nichts mehr retten - aber die Meldung muss klar
    # sagen, dass jetzt Handarbeit nötig ist, und wo das Protokoll
    # liegt. Eine irreführende Erfolgsmeldung wäre hier das Schlimmste.
    # ----------------------------------------------------------------

    install = scratch / "install5"
    install.mkdir()
    build_install(install)

    shutil.rmtree(work, ignore_errors=True)
    updater.check_health = lambda port: False

    result = updater.run_update(zip_path, install, "xrack", 8080)

    assert result == 1
    status = json.loads((work / "status.json").read_text(encoding="utf-8"))

    assert status["state"] == "failed", (
        f"Erwartet 'failed', bekommen '{status['state']}'"
    )
    assert "SSH" in status["message"], (
        f"Die Meldung müsste auf Handarbeit hinweisen: {status['message']}"
    )

    print("OK: Wenn auch der Rückfall scheitert, gibt es eine ehrliche Fehlermeldung")

    # ----------------------------------------------------------------
    # Hinweis auf die Git-Arbeitskopie
    #
    # Der Updater tauscht die Dateien direkt aus und laesst .git in
    # Ruhe - HEAD zeigt danach weiter auf den alten Stand, und ein
    # spaeteres "git pull" bricht ab. Das ist kein Schaden, aber es
    # muss dabeistehen, sonst sucht man den Fehler an der falschen
    # Stelle.
    # ----------------------------------------------------------------

    install = scratch / "install-git"
    install.mkdir()
    build_install(install)
    (install / ".git").mkdir()

    shutil.rmtree(work, ignore_errors=True)
    updater.check_health = lambda port: True
    updater.restart_service = lambda: True

    assert updater.run_update(zip_path, install, "xrack", 8080) == 0

    status = json.loads((work / "status.json").read_text(encoding="utf-8"))

    assert status["needs_git_reset"] is True, status
    assert "git" in status["message"], status["message"]

    #
    # .git muss dabei erhalten bleiben - sonst waere die Arbeitskopie
    # nach dem ersten Update keine mehr.
    #
    assert (install / ".git").is_dir(), "Der Updater hat .git geloescht."

    print("OK: Bei einer Git-Arbeitskopie weist die Erfolgsmeldung darauf hin")

    #
    # Ohne .git darf der Hinweis nicht erscheinen - sonst wuerde er
    # jeden Nutzer verwirren, den er gar nicht betrifft.
    #
    install = scratch / "install-ohne-git"
    install.mkdir()
    build_install(install)

    shutil.rmtree(work, ignore_errors=True)

    assert updater.run_update(zip_path, install, "xrack", 8080) == 0

    status = json.loads((work / "status.json").read_text(encoding="utf-8"))

    assert status["needs_git_reset"] is False, status
    assert "git" not in status["message"], status["message"]

    print("OK: Ohne Git-Arbeitskopie bleibt der Hinweis weg")

    # ----------------------------------------------------------------
    # Download aus dem Internet
    #
    # Gegen einen eigenen HTTP-Server auf localhost - kein echtes Netz.
    # ----------------------------------------------------------------

    import http.server
    import threading

    inhalt = zip_path.read_bytes()

    class Handler(http.server.BaseHTTPRequestHandler):

        def do_GET(self):

            if self.path == "/chrisse1/XRack/main":
                self.send_response(200)
                self.send_header("Content-Length", str(len(inhalt)))
                self.end_headers()
                self.wfile.write(inhalt)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    adresse = f"http://127.0.0.1:{server.server_port}"

    original_url = updater.GITHUB_ZIP
    updater.GITHUB_ZIP = adresse + "/{repository}/{branch}"

    try:

        geladen = updater.download_package("chrisse1/XRack", "main")

        assert geladen is not None, "Der Download hat nichts geliefert."
        assert geladen.read_bytes() == inhalt, (
            "Die heruntergeladene Datei stimmt nicht mit der Vorlage überein."
        )

        print("OK: Update aus dem Internet wird heruntergeladen")

        #
        # Ein unbekanntes Verzeichnis darf nicht in einer halben Datei
        # enden, sondern muss sauber None liefern - nur dann kann der
        # Aufrufer eine ehrliche Fehlermeldung schreiben, statt eine
        # kaputte ZIP zu entpacken.
        #
        assert updater.download_package("gibt/esnicht", "main") is None

        print("OK: Fehlgeschlagener Download liefert None statt einer halben Datei")

        #
        # Der heruntergeladene Stand muss denselben Weg gehen wie eine
        # ZIP vom Stick - genau das ist der Sinn der Sache: eine
        # Mechanik, ein Rueckfall.
        #
        install = scratch / "install-online"
        install.mkdir()
        build_install(install)

        shutil.rmtree(work, ignore_errors=True)

        geladen = updater.download_package("chrisse1/XRack", "main")

        assert updater.run_update(geladen, install, "xrack", 8080) == 0

        assert (install / "main.py").read_text(encoding="utf-8").startswith("neu"), (
            "Der heruntergeladene Stand wurde nicht eingespielt."
        )

        print("OK: Der heruntergeladene Stand laeuft durch denselben Ablauf")

    finally:
        updater.GITHUB_ZIP = original_url
        server.shutdown()

    # ----------------------------------------------------------------
    # Git-Arbeitskopie nachziehen
    #
    # Gegen ein echtes lokales Repository - kein Netz noetig. Der
    # Ursprung enthaelt denselben Stand wie die ZIP; genau so ist es in
    # Wirklichkeit auch, weil beide vom selben Branch stammen.
    # ----------------------------------------------------------------

    import os
    import subprocess

    def git(verzeichnis, *argumente):
        return subprocess.run(
            ["git", "-C", str(verzeichnis), *argumente],
            capture_output=True,
            text=True,
        )

    verfuegbar = subprocess.run(
        ["git", "--version"], capture_output=True
    ).returncode == 0

    if not verfuegbar:
        print("HINWEIS: git fehlt - Nachzieh-Tests uebersprungen")

    else:

        umgebung = {
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        }
        os.environ.update(umgebung)

        #
        # Ursprung aufbauen: derselbe Inhalt, den auch die ZIP bringt.
        #
        ursprung = scratch / "origin"
        ursprung.mkdir()

        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(ursprung)

        quelle = updater.find_source_directory(ursprung)

        #
        # Die echte .gitignore mitnehmen: Genau sie ist der Grund,
        # warum ein "reset --hard" auf dem Pi ungefaehrlich ist -
        # Aufnahmen, Musik, PIN und venv sind gar nicht verfolgt. Ohne
        # sie wuerde der Test etwas pruefen, das es so nicht gibt.
        #
        shutil.copy(
            Path(__file__).parent / ".gitignore", quelle / ".gitignore"
        )

        git(quelle, "init", "-q", "-b", "main")
        git(quelle, "add", "-A")
        git(quelle, "commit", "-q", "-m", "Stand aus der ZIP")

        commit = git(quelle, "rev-parse", "HEAD").stdout.strip()

        #
        # Arbeitskopie: derselbe Branch, aber noch der alte Stand.
        #
        arbeitskopie = scratch / "install-arbeitskopie"

        assert git(
            scratch, "clone", "-q", str(quelle), str(arbeitskopie)
        ).returncode == 0, "Klonen fehlgeschlagen"

        for eintrag in arbeitskopie.iterdir():
            if eintrag.name != ".git":
                shutil.rmtree(eintrag) if eintrag.is_dir() else eintrag.unlink()

        build_install(arbeitskopie)

        shutil.rmtree(work, ignore_errors=True)
        updater.check_health = lambda port: True

        assert updater.run_update(
            zip_path, arbeitskopie, "xrack", 8080, branch="main"
        ) == 0

        status = json.loads((work / "status.json").read_text(encoding="utf-8"))

        assert status["needs_git_reset"] is False, (
            f"git wurde nicht nachgezogen: {status}"
        )
        assert "git" not in status["message"], status["message"]

        #
        # Der eigentliche Beweis: Nach dem Update ist die Arbeitskopie
        # sauber und zeigt auf den richtigen Commit. Genau das ist die
        # Voraussetzung dafuer, dass ein spaeteres "git pull" laeuft.
        #
        assert git(arbeitskopie, "status", "--porcelain").stdout.strip() == "", (
            "Die Arbeitskopie ist nach dem Update immer noch schmutzig:\n"
            + git(arbeitskopie, "status", "--porcelain").stdout
        )

        #
        # Und die Nutzerdaten muessen das Nachziehen ueberstanden
        # haben - "reset --hard" fasst nicht verfolgte Dateien nicht
        # an, aber genau darauf verlaesst sich der ganze Ansatz.
        #
        for geschuetzt in ("recordings", "music", "config/state.json", ".venv"):
            assert (arbeitskopie / geschuetzt).exists(), (
                f"Das Nachziehen hat Nutzerdaten verloren: {geschuetzt}"
            )
        assert git(arbeitskopie, "rev-parse", "HEAD").stdout.strip() == commit, (
            "HEAD zeigt nicht auf den eingespielten Stand."
        )
        assert git(
            arbeitskopie, "rev-parse", "--abbrev-ref", "HEAD"
        ).stdout.strip() == "main", "Der Branch wurde abgetrennt."

        print("OK: Nach dem Online-Update ist die Git-Arbeitskopie sauber und aktuell")

        #
        # Gegenprobe zur wichtigsten Einschraenkung: Sitzt auf dem
        # Geraet ein anderer Branch, darf NICHT nachgezogen werden -
        # das waere ein Zweigwechsel hinter dem Ruecken des Nutzers.
        #
        git(arbeitskopie, "checkout", "-q", "-b", "entwicklung")

        for eintrag in arbeitskopie.iterdir():
            if eintrag.name != ".git":
                shutil.rmtree(eintrag) if eintrag.is_dir() else eintrag.unlink()

        build_install(arbeitskopie)

        shutil.rmtree(work, ignore_errors=True)

        assert updater.run_update(
            zip_path, arbeitskopie, "xrack", 8080, branch="main"
        ) == 0

        status = json.loads((work / "status.json").read_text(encoding="utf-8"))

        assert status["needs_git_reset"] is True, (
            f"Auf einem fremden Branch darf nicht nachgezogen werden: {status}"
        )
        assert git(
            arbeitskopie, "rev-parse", "--abbrev-ref", "HEAD"
        ).stdout.strip() == "entwicklung", (
            "Der Updater hat den Branch gewechselt."
        )

        #
        # ... und die Meldung muss dann den passenden Befehl nennen,
        # nicht nur allgemein auf git verweisen.
        #
        assert "entwicklung" in status["message"], status["message"]

        print("OK: Auf einem fremden Branch wird nicht nachgezogen, sondern erklaert")

        #
        # Beim USB-Weg ist kein Branch bekannt - dann bleibt es beim
        # Hinweis, auch wenn zufaellig der richtige Branch ausgecheckt
        # ist. Raten waere hier das Falsche.
        #
        git(arbeitskopie, "checkout", "-q", "main")

        shutil.rmtree(work, ignore_errors=True)

        assert updater.run_update(zip_path, arbeitskopie, "xrack", 8080) == 0

        status = json.loads((work / "status.json").read_text(encoding="utf-8"))

        assert status["needs_git_reset"] is True, (
            f"Ohne bekannten Branch darf nicht nachgezogen werden: {status}"
        )

        print("OK: Ohne bekannten Branch (USB-Weg) bleibt es beim Hinweis")

    # ----------------------------------------------------------------
    # Quittieren: "Update erfolgreich" darf nicht ewig stehenbleiben
    #
    # Die Statusdatei liegt in /var/tmp und wird nie geloescht - ohne
    # Quittung begruesst einen die Meldung noch Tage spaeter.
    # ----------------------------------------------------------------

    import types

    from core.application import Application

    class FakeStore:

        def __init__(self):
            self.werte = {}

        def get(self, key, default=None):
            return self.werte.get(key, default)

        def set(self, key, value):
            self.werte[key] = value

    def stub(status):
        return types.SimpleNamespace(
            updater=types.SimpleNamespace(get_status=lambda: status),
            state_store=FakeStore(),
        )

    erfolg = {
        "state": "success",
        "step": "fertig",
        "message": "Update erfolgreich.",
        "updated_at": "2026-08-24T21:15:00",
    }

    self = stub(erfolg)

    assert Application.get_update_status(self)["state"] == "success", (
        "Ein frisches Ergebnis muss angezeigt werden."
    )

    assert Application.acknowledge_update(self) is True

    assert Application.get_update_status(self)["state"] == "idle", (
        "Nach dem Quittieren darf das Ergebnis nicht mehr erscheinen."
    )

    print("OK: Ein quittiertes Update-Ergebnis verschwindet aus der Anzeige")

    #
    # Entscheidend: Das naechste Update hat einen anderen Zeitstempel
    # und muss deshalb wieder auftauchen. Wuerde nur ein "gesehen"-Flag
    # gesetzt, bliebe die Anzeige fuer immer stumm.
    #
    self.updater.get_status = lambda: dict(erfolg, updated_at="2026-08-25T09:00:00")

    assert Application.get_update_status(self)["state"] == "success", (
        "Ein neues Update muss trotz frueherer Quittung angezeigt werden."
    )

    print("OK: Ein spaeteres Update wird trotz frueherer Quittung wieder angezeigt")

    #
    # Ein laufendes Update laesst sich nicht quittieren - sonst waere
    # das Ergebnis weg, bevor es ueberhaupt feststeht.
    #
    laeuft = stub({"state": "running", "step": "übertragen", "message": ""})

    assert Application.acknowledge_update(laeuft) is False

    print("OK: Ein laufendes Update laesst sich nicht vorab quittieren")

    print("Alle Tests erfolgreich.")

finally:

    shutil.rmtree(scratch, ignore_errors=True)
