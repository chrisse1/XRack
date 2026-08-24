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

    print("Alle Tests erfolgreich.")

finally:

    shutil.rmtree(scratch, ignore_errors=True)
