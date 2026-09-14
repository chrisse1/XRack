#!/usr/bin/env python3
"""
Stems für einen Übungsmix: hochgeladen ODER schon auf dem Gerät.

Bis hierher mussten alle Stems durch den Browser hochgeladen werden.
Seit Dateien auch vom USB-Stick kommen können, liegen sie oft schon auf
dem Gerät - und sie dann wieder hochzuladen wäre genau der Umweg über
die Leitung, den der Stick vermeiden sollte. Bei Stems geht es um
hundert Megabyte aufwärts.

Zwei Dinge entscheiden sich dabei, und beide können still schiefgehen:

  - Die REIHENFOLGE ist die Kanalzuordnung (Quelle 1 -> Kanal 1+2).
    Sie läuft über beide Quellen hinweg. Wird sie nicht ausdrücklich
    mitgeschickt, bleibt der Gegenseite nur zu raten, ob der Upload vor
    oder hinter der Datei vom Gerät liegt - und die Stems lägen auf den
    falschen Kanälen. Hören würde man das erst beim Üben.
  - Was WEGGERÄUMT wird. Die Uploads sind Kopien und gehören gelöscht.
    Eine Datei aus der Bibliothek nicht: Sonst verschwände mit dem
    fertigen Übungsmix die Datei, aus der er entstanden ist.

Geprüft wird die echte Route und nicht die Anwendungsschicht dahinter:
Genau dazwischen sitzt die Zuordnung.

Aufgerufen wird sie direkt statt über einen Testclient - der bräuchte
httpx, und XRacks Umgebung soll für die Testreihe nichts nachinstallieren
müssen (dieselbe Regel wie beim Update über den USB-Stick).
"""

#
# Der Suchpfad zur Projektwurzel - siehe tests/_wurzel.py. Muss VOR
# allen Importen aus XRack stehen.
#
from _wurzel import WURZEL  # noqa: F401,E402


import io
import shutil
import tempfile
from pathlib import Path

from fastapi import UploadFile

from player.music_library import MusicLibrary
from web.routes.recordings import combine_recordings


class Anfrage:
    """Nur so viel Request, wie die Route anfasst."""

    def __init__(self, anwendung):

        class Zustand:
            pass

        class App:
            pass

        self.app = App()
        self.app.state = Zustand()
        self.app.state.application = anwendung


def hochladen(name: str, inhalt: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(inhalt))


class Anwendung:
    """Nur so viel Application, wie die Route anfasst."""

    def __init__(self, wurzel: Path):

        self.music_library = MusicLibrary(wurzel / "musik")

        self.gestartet = []

        self.antwort = (True, "started")

    def start_stem_combine(self, name, file_paths, start_channel=1,
                           temporaer=None):

        self.gestartet.append({
            "name": name,
            "pfade": [Path(p) for p in file_paths],
            "start": start_channel,
            "temporaer": [Path(p) for p in (temporaer or [])],
        })

        return self.antwort


with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)

    (wurzel / "musik" / "Proben").mkdir(parents=True)

    klick = wurzel / "musik" / "Proben" / "klick.wav"
    klick.write_bytes(b"k" * 100)

    anwendung = Anwendung(wurzel)

    anfrage = Anfrage(anwendung)

    # ================================================================
    # 1. Gemischt - und die Reihenfolge bleibt
    #
    # Gewählt ist: Kanal 1+2 die Datei vom Gerät, Kanal 3+4 ein
    # Upload, Kanal 5+6 wieder das Gerät. Genau so muss es ankommen.
    # ================================================================

    antwort = combine_recordings(
        anfrage,
        name="Probe",
        files=[hochladen("gitarre.wav", b"g" * 50)],
        start_channel=1,
        sources=(
            '[{"kind":"library","path":"Proben/klick.wav"},'
            ' {"kind":"upload"},'
            ' {"kind":"library","path":"Proben/klick.wav"}]'
        ),
    )

    assert antwort["success"] is True, antwort

    lauf = anwendung.gestartet[-1]

    arten = [
        "bibliothek" if pfad == klick.resolve() else "upload"
        for pfad in lauf["pfade"]
    ]

    assert arten == ["bibliothek", "upload", "bibliothek"], (
        f"Die Reihenfolge kam als {arten} an. Damit lägen die Stems auf "
        f"den falschen Kanälen - und hören würde man das erst beim Üben."
    )

    print("OK: Die Reihenfolge über beide Quellen hinweg bleibt erhalten")

    # ================================================================
    # 2. Weggeräumt wird nur, was hochgeladen wurde
    # ================================================================

    assert len(lauf["temporaer"]) == 1, lauf["temporaer"]

    assert klick.resolve() not in lauf["temporaer"], (
        "Die Datei aus der Bibliothek steht auf der Aufräumliste - dann "
        "verschwände mit dem fertigen Übungsmix die Datei, aus der er "
        "entstanden ist."
    )

    assert lauf["temporaer"][0] in lauf["pfade"], lauf

    print("OK: Aufgeräumt werden nur die Uploads")

    # ================================================================
    # 3. Eine Datei, die es nicht gibt - und ein Ausbruch
    #
    # Was vom Browser kommt, darf nicht bestimmen, WO gelesen wird.
    # ================================================================

    vorher = len(anwendung.gestartet)

    for pfad, wovon in (
        ("Proben/gibtsnicht.wav", "Datei existiert nicht"),
        ("../../etc/passwd", "Ausbruch aus der Bibliothek"),
    ):

        antwort = combine_recordings(
            anfrage,
            name="Probe",
            files=[hochladen("gitarre.wav", b"g" * 50)],
            start_channel=1,
            sources=(
                '[{"kind":"library","path":"' + pfad + '"},'
                ' {"kind":"upload"}]'
            ),
        )

        assert antwort["success"] is False, f"{wovon}: angenommen."

        assert len(anwendung.gestartet) == vorher, (
            f"{wovon}: Es wurde trotzdem etwas gestartet."
        )

    print("OK: Fehlende Dateien und Ausbrüche werden abgewiesen")

    # ================================================================
    # 4. Ohne "sources" gilt der alte Weg
    #
    # Die Route ist älter als die Bibliotheks-Quelle. Ein Aufruf ohne
    # die Angabe muss weiter funktionieren - sonst wäre jeder ältere
    # Browser-Tab kaputt.
    # ================================================================

    antwort = combine_recordings(
        anfrage,
        name="Alt",
        files=[hochladen("a.wav", b"a" * 10), hochladen("b.wav", b"b" * 10)],
        start_channel=1,
        sources="",
    )

    assert antwort["success"] is True, antwort

    alt = anwendung.gestartet[-1]

    assert len(alt["pfade"]) == 2, alt

    assert alt["temporaer"] == alt["pfade"], (
        "Ohne Angabe sind alle Quellen Uploads - und alle gehören "
        "weggeräumt."
    )

    print("OK: Der alte Weg (nur Uploads) funktioniert unverändert")

    # ================================================================
    # 5. Scheitert der Start, bleibt kein Upload liegen
    # ================================================================

    anwendung.antwort = (False, "Es läuft bereits eine Zusammenführung.")

    #
    # Die Ordner der GELUNGENEN Läufe oben bleiben liegen - dort räumt
    # sonst der Hintergrundlauf auf, den es hier nicht gibt. Gefragt
    # ist also nur, ob der fehlgeschlagene Lauf einen HINZUFÜGT.
    #
    vorhandene = set(
        Path(tempfile.gettempdir()).glob("xrack_stem_combine_*")
    )

    antwort = combine_recordings(
        anfrage,
        name="Probe",
        files=[hochladen("a.wav", b"a" * 10), hochladen("b.wav", b"b" * 10)],
        start_channel=1,
        sources="",
    )

    assert antwort["success"] is False, antwort

    neue = set(
        Path(tempfile.gettempdir()).glob("xrack_stem_combine_*")
    ) - vorhandene

    assert neue == set(), (
        f"Nach dem Fehlschlag bleibt ein Verzeichnis mit hochgeladenen "
        f"Dateien liegen: {neue}"
    )

    #
    # Und die gelungenen Laeufe raeumen wir hier selbst weg - der
    # Hintergrundlauf, der das sonst tut, ist hier nachgestellt.
    #
    for ordner in vorhandene:
        shutil.rmtree(ordner, ignore_errors=True)

    print("OK: Ein Fehlschlag lässt keine hochgeladenen Reste zurück")


# ====================================================================
# 6. Der ECHTE Hintergrundlauf räumt nur die Uploads weg
#
# Das ist der gefährlichste Punkt der ganzen Sache, und er war bis
# hierher ungeprüft: Oben wird nur festgestellt, WAS die Route als
# Aufräumliste weiterreicht. Ob der Hintergrundlauf sich daran hält,
# steht damit noch nicht fest - und hielte er sich nicht daran,
# verschwände mit dem fertigen Übungsmix die Datei, aus der er
# entstanden ist. Stems sind Arbeit: gekauft, aus Moises geholt,
# geschnitten.
#
# Gelaufen wird deshalb die echte Methode, nur das Zusammenlegen
# selbst ist nachgestellt (es bräuchte ffmpeg und echte Audiodaten -
# beides prüft test_stem_combiner.py).
# ====================================================================

import logging  # noqa: E402
import threading  # noqa: E402

import core.application.aufnahme as aufnahme_modul  # noqa: E402

from core.application.aufnahme import AufnahmeMixin  # noqa: E402


class Hintergrund(AufnahmeMixin):

    def __init__(self):
        self.logger = logging.getLogger("XRack-Test")
        self.mixer_sample_rate = 48000
        self._stem_combine_lock = threading.Lock()
        self.stem_combine_state = {
            "active": True, "success": None, "error": "", "filename": "",
        }


with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)

    bibliothek = wurzel / "musik"
    bibliothek.mkdir()

    bleibt = bibliothek / "klick.wav"
    bleibt.write_bytes(b"k" * 10)

    scratch = wurzel / "scratch"
    scratch.mkdir()

    weg = scratch / "stem_0.wav"
    weg.write_bytes(b"u" * 10)

    echtes_zusammenlegen = aufnahme_modul.combine_stems

    aufnahme_modul.combine_stems = (
        lambda *args, **kwargs: "Probe-1_p.w64"
    )

    try:

        Hintergrund()._run_stem_combine(
            "Probe",
            [bleibt, weg],
            1,
            temporaer=[weg],
        )

    finally:
        aufnahme_modul.combine_stems = echtes_zusammenlegen

    assert not weg.exists(), (
        "Die hochgeladene Kopie liegt noch da - sie gehört weg, sonst "
        "füllt sich /tmp mit Stems."
    )

    assert bleibt.exists(), (
        "Die Datei aus der Bibliothek wurde GELÖSCHT. Damit verschwände "
        "mit jedem Übungsmix das Material, aus dem er entstanden ist."
    )

    assert scratch.exists() is False or not any(scratch.iterdir()), (
        "Das Scratch-Verzeichnis ist nicht leer."
    )

    assert bibliothek.exists(), (
        "Die Bibliothek selbst wurde weggeräumt - das Aufräumen greift "
        "über die Dateien hinaus."
    )

    print("OK: Der echte Hintergrundlauf löscht nur die Uploads")


print("Alle Tests zu den Stem-Quellen erfolgreich.")
