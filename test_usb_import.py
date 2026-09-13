#!/usr/bin/env python3
"""
Vom USB-Stick auf das Gerät: die Entscheidungen der Anwendungsschicht
(core/application/usb.py).

Was der eigentliche Kopiervorgang darf und was nicht, steht in
test_usb_storage.py. Hier geht es um das, was davor entschieden wird -
und jede dieser Entscheidungen hat einen Weg, auf dem sie schiefgehen
kann:

  - Das ZIEL. Zwei gibt es, und sie sind verschieden: Die
    Musikbibliothek hat Ordner, das Aufnahmeverzeichnis ist flach. Ein
    Zielordner, den es nicht gibt, darf nicht stillschweigend zur
    Wurzel werden.
  - Der PLATZ. Eine halb kopierte Datei auf einer vollen SD-Karte ist
    der unangenehmste Ausgang, den es hier gibt - sie sieht aus wie
    eine ganze.
  - Das AUSWERFEN. Ein Stick, der mitten im Holen ausgehängt wird,
    hinterlässt genau solche halben Dateien.

Gebaut wird nicht die ganze Application (die zöge ALSA, Netzwerk und
DMX nach sich), sondern das Mixin auf nachgestellter Umgebung: Die
Entscheidungen stehen vollständig darin.
"""

import logging
import shutil
import tempfile
import threading
import time
from pathlib import Path

from core.application.usb import UsbMixin
from core.usb_storage import UsbStorage
from player.music_library import MusicLibrary


class Schreiber:
    def __init__(self, ordner: Path):
        self.directory = ordner


class Aufnehmer:
    def __init__(self, ordner: Path):
        self.writer = Schreiber(ordner)


class Anwendung(UsbMixin):
    """Die echten Methoden aus dem Mixin, ohne echte Hardware."""

    def __init__(self, wurzel: Path):

        self.logger = logging.getLogger("XRack-Test")

        self.usb_storage = UsbStorage()
        self.usb_storage.MOUNT_POINT = wurzel / "stick"

        type(self.usb_storage).connected = property(lambda self: True)

        self.music_library = MusicLibrary(wurzel / "musik")
        self.recorder = Aufnehmer(wurzel / "recordings")

        self._usb_copy_lock = threading.Lock()
        self.usb_copy_state = {"active": False}

        self._usb_import_lock = threading.Lock()

        self.usb_import_state = {
            "active": False,
            "file": "",
            "copied": 0,
            "total": 0,
            "success": None,
            "error": "",
            "report": None,
        }


def warten(anwendung: Anwendung, frist: float = 20.0) -> dict:
    """Bis der Hintergrundlauf fertig ist."""

    ende = time.monotonic() + frist

    while time.monotonic() < ende:

        stand = anwendung.get_usb_import_status()

        if not stand["active"]:
            return stand

        time.sleep(0.05)

    raise AssertionError("Der Kopiervorgang wurde nicht fertig.")


with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)

    anwendung = Anwendung(wurzel)

    stick = anwendung.usb_storage.MOUNT_POINT

    (stick / "Album").mkdir(parents=True)
    (stick / "Album" / "lied.mp3").write_bytes(b"a" * 1000)
    (stick / "Umbrella-1_p.w64").write_bytes(b"w" * 500)

    (wurzel / "musik" / "Proben").mkdir(parents=True)
    (wurzel / "recordings").mkdir(parents=True)

    # ================================================================
    # 1. In die Musikbibliothek, in den gewählten Ordner
    # ================================================================

    erfolg, meldung = anwendung.start_usb_import(
        ["Album"], "music", "Proben"
    )

    assert erfolg, meldung

    stand = warten(anwendung)

    assert stand["success"] is True, stand

    assert stand["report"]["kopiert"] == 1, stand["report"]

    ziel = wurzel / "musik" / "Proben" / "Album" / "lied.mp3"

    assert ziel.is_file(), (
        f"Die Datei liegt nicht im gewählten Ordner. Da ist: "
        f"{sorted(str(p) for p in (wurzel / 'musik').rglob('*'))}"
    )

    print("OK: Musik landet im gewählten Ordner der Bibliothek")

    # ================================================================
    # 2. In die Aufnahmen - flach, und nur Wave64
    # ================================================================

    erfolg, meldung = anwendung.start_usb_import(
        ["Umbrella-1_p.w64", "Album"], "recordings"
    )

    assert erfolg, meldung

    stand = warten(anwendung)

    assert stand["success"] is True, stand

    liegt = sorted(p.name for p in (wurzel / "recordings").iterdir())

    assert liegt == ["Umbrella-1_p.w64"], (
        f"Im Aufnahmeverzeichnis liegt {liegt} - die Musikdatei gehört "
        f"dort nicht hinein."
    )

    print("OK: Aufnahmen landen flach im Aufnahmeverzeichnis")

    # ================================================================
    # 3. Was nicht geht, sagt es - und tut nichts
    # ================================================================

    for quellen, ziel_art, ordner, wovon in (
        ([], "music", "", "ohne Auswahl"),
        (["Album"], "wohin_auch_immer", "", "unbekanntes Ziel"),
        (["Album"], "music", "GibtsNicht", "Zielordner existiert nicht"),
    ):

        erfolg, meldung = anwendung.start_usb_import(
            quellen, ziel_art, ordner
        )

        assert erfolg is False, f"{wovon}: wurde angenommen."

        assert meldung, f"{wovon}: keine Begründung."

        assert anwendung.get_usb_import_status()["active"] is False, (
            f"{wovon}: Es läuft trotzdem etwas."
        )

    print("OK: Fehlende Auswahl, falsches Ziel und fehlender Ordner "
          "werden abgewiesen")

    # ================================================================
    # 4. Kein Platz - dann wird gar nicht erst angefangen
    #
    # Eine halb kopierte Datei auf einer vollen Karte sieht aus wie
    # eine ganze. Deshalb wird VOR dem Kopieren gerechnet.
    # ================================================================

    echte_pruefung = Anwendung._freier_platz

    Anwendung._freier_platz = lambda self, ordner: 100

    try:

        erfolg, meldung = anwendung.start_usb_import(
            ["Album"], "music", "Proben"
        )

        assert erfolg is False, "Mit 100 Byte frei wurde losgelegt."

        assert "Platz" in meldung, meldung

        assert "1000" not in meldung or "MB" in meldung, meldung

    finally:
        Anwendung._freier_platz = echte_pruefung

    print("OK: Ohne Platz wird nicht angefangen, sondern gesagt warum")

    # ================================================================
    # 5. Auswerfen, während geholt wird: nein
    #
    # Ein Stick, der mitten im Kopieren ausgehängt wird, hinterlässt
    # halbe Dateien auf dem Gerät.
    # ================================================================

    with anwendung._usb_import_lock:
        anwendung.usb_import_state["active"] = True

    try:
        erfolg, meldung = anwendung.eject_usb()

        assert erfolg is False and meldung == "busy", (erfolg, meldung)

    finally:
        with anwendung._usb_import_lock:
            anwendung.usb_import_state["active"] = False

    print("OK: Während des Holens lässt sich der Stick nicht auswerfen")

    # ================================================================
    # 6. Das Ziel entscheidet, was verwendbar ist
    # ================================================================

    musik = anwendung.usb_browse("", "music")
    aufnahmen = anwendung.usb_browse("", "recordings")

    def brauchbar(inhalt):
        return {d["name"]: d["usable"] for d in inhalt["files"]}

    assert brauchbar(musik) == {"Umbrella-1_p.w64": False}, brauchbar(musik)

    assert brauchbar(aufnahmen) == {"Umbrella-1_p.w64": True}, (
        brauchbar(aufnahmen)
    )

    print("OK: Dieselbe Datei ist je nach Ziel verwendbar oder nicht")


print("Alle Tests zum Holen vom USB-Stick erfolgreich.")
