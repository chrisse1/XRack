#!/usr/bin/env python3
"""
USB-Stick: Kopieren mit Fortschritt und die Behandlung von Fehlern.

Der Kopiervorgang laeuft ueber Aufnahmen, die Stunden Arbeit sind -
was hier schiefgeht, faellt erst auf, wenn die Datei am Zielort
gebraucht wird. Deshalb steht hier vor allem, was NICHT passieren
darf: eine halbe Datei zuruecklassen, eine vorhandene ueberschreiben,
oder ohne Stick still etwas tun.
"""

import tempfile
from pathlib import Path

from core.usb_storage import UsbStorage


def stick(wurzel: Path, angeschlossen: bool = True) -> UsbStorage:
    """UsbStorage mit einem Ordner statt eines echten Einhaengepunkts."""

    ziel = wurzel / "stick"
    ziel.mkdir(exist_ok=True)

    s = UsbStorage()
    s.MOUNT_POINT = ziel

    #
    # connected prueft is_mount() - ein gewoehnlicher Ordner ist das
    # nicht, also hier ausdruecklich setzen.
    #
    type(s).connected = property(lambda self: angeschlossen)

    return s


# ====================================================================
# Der gute Fall, samt Fortschritt
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)
    s = stick(wurzel)

    #
    # Ueber drei Bloecke gross (Blockgroesse 4 MiB), damit der
    # Fortschritt mehrfach gemeldet wird - bei nur einer Meldung
    # waere die Pruefung auf Monotonie gegenstandslos.
    #
    from core.usb_storage import _COPY_CHUNK_SIZE

    quelle = wurzel / "Soundcheck-1.wav"
    quelle.write_bytes(b"A" * (3 * _COPY_CHUNK_SIZE + 17))

    schritte = []

    erfolg, schon_da = s.copy_file(quelle, on_progress=lambda k, g: schritte.append((k, g)))

    assert erfolg is True and schon_da is False, (erfolg, schon_da)

    ziel = s.MOUNT_POINT / "Soundcheck-1.wav"

    assert ziel.read_bytes() == quelle.read_bytes(), "Inhalt stimmt nicht ueberein"

    assert schritte, "Es kam keine einzige Fortschrittsmeldung"

    assert schritte[-1][0] == quelle.stat().st_size, (
        f"Der Fortschritt endet nicht bei der Dateigroesse: {schritte[-1]}"
    )
    assert all(g == quelle.stat().st_size for _, g in schritte), (
        "Die Gesamtgroesse schwankt zwischen den Meldungen"
    )
    assert schritte == sorted(schritte), "Der Fortschritt laeuft nicht monoton"

    assert len(schritte) >= 4, (
        f"Zu wenige Meldungen ({len(schritte)}) - dann sagt die Pruefung auf "
        "Monotonie nichts aus."
    )

    print(f"OK: Datei kopiert, {len(schritte)} Fortschrittsmeldungen, monoton")


# ====================================================================
# Eine vorhandene Datei wird nicht ueberschrieben
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)
    s = stick(wurzel)

    quelle = wurzel / "Soundcheck-1.wav"
    quelle.write_bytes(b"neu")

    ziel = s.MOUNT_POINT / "Soundcheck-1.wav"
    ziel.write_bytes(b"schon da")

    erfolg, schon_da = s.copy_file(quelle)

    assert erfolg is True and schon_da is True, (erfolg, schon_da)
    assert ziel.read_bytes() == b"schon da", (
        "Eine vorhandene Datei auf dem Stick wurde ueberschrieben."
    )

    print("OK: Eine vorhandene Datei bleibt unangetastet")


# ====================================================================
# Ohne Stick passiert nichts
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)
    s = stick(wurzel, angeschlossen=False)

    quelle = wurzel / "Soundcheck-1.wav"
    quelle.write_bytes(b"x")

    assert s.copy_file(quelle) == (False, False)
    assert list(s.MOUNT_POINT.iterdir()) == [], "Ohne Stick wurde geschrieben"

    print("OK: Ohne Stick wird nichts geschrieben")


# ====================================================================
# Bricht das Kopieren ab, bleibt keine halbe Datei liegen
#
# Das ist der wichtigste Fall: Eine abgeschnittene Aufnahme auf dem
# Stick sieht aus wie eine gute, bis man sie oeffnet.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)
    s = stick(wurzel)

    quelle = wurzel / "Soundcheck-1.wav"
    quelle.write_bytes(b"B" * (2 * 1024 * 1024))

    def platte_voll(kopiert, gesamt):
        #
        # Stellt einen vollen Stick nach: Der Fehler faellt mitten im
        # Schreiben an, nicht beim Oeffnen.
        #
        raise OSError(28, "No space left on device")

    erfolg, schon_da = s.copy_file(quelle, on_progress=platte_voll)

    assert erfolg is False and schon_da is False, (erfolg, schon_da)

    reste = list(s.MOUNT_POINT.iterdir())

    assert reste == [], (
        f"Nach dem Abbruch liegt eine unvollstaendige Datei auf dem Stick: "
        f"{[p.name for p in reste]}"
    )

    print("OK: Nach einem Abbruch bleibt keine halbe Datei zurueck")


# ====================================================================
# Die andere Richtung: vom Stick auf das Geraet
#
# Die gab es lange nicht, und sie hat gefehlt: Fuer Musik half
# wenigstens der Upload ueber den Browser, fuer Aufnahmen gab es gar
# nichts - ein Uebungsmix aus dem Backup kam nicht wieder auf das
# Geraet.
#
# Was hier schiefgehen kann, ist schlimmer als beim Hinkopieren: Das
# Ziel ist die SD-Karte, auf der XRack arbeitet. Eine ueberschriebene
# Datei, eine halbe Datei oder ein Pfad, der aus dem Stick
# herausfuehrt, treffen das Geraet selbst.
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    wurzel = Path(tmp)

    s = stick(wurzel)

    #
    # Ein Stick, wie er wirklich aussieht: ein Album mit Unterordner,
    # eine lose Datei, etwas Unbrauchbares und der Muell, den
    # Betriebssysteme hinterlassen.
    #
    (s.MOUNT_POINT / "Album" / "CD1").mkdir(parents=True)
    (s.MOUNT_POINT / "Album" / "CD1" / "01 Intro.mp3").write_bytes(b"a" * 100)
    (s.MOUNT_POINT / "Album" / "CD1" / "02 Lied.flac").write_bytes(b"b" * 200)
    (s.MOUNT_POINT / "Album" / "cover.jpg").write_bytes(b"c" * 10)
    (s.MOUNT_POINT / "lose.mp3").write_bytes(b"d" * 50)
    (s.MOUNT_POINT / "notiz.txt").write_bytes(b"e")
    (s.MOUNT_POINT / "System Volume Information").mkdir()
    (s.MOUNT_POINT / "._versteckt.mp3").write_bytes(b"f")

    from core.usb_storage import ENDUNGEN_AUFNAHMEN, ENDUNGEN_MUSIK

    inhalt = s.browse("", ENDUNGEN_MUSIK)

    assert inhalt["folders"] == ["Album"], (
        f"Die Ordner stimmen nicht: {inhalt['folders']} - der Muell des "
        f"Betriebssystems und Verstecktes gehoeren nicht dazu."
    )

    namen = [d["name"] for d in inhalt["files"]]

    assert namen == ["lose.mp3", "notiz.txt"], namen

    #
    # Unbrauchbares wird AUFGEFUEHRT, nur gekennzeichnet. Wer seine
    # Datei gar nicht sieht, sucht sie; wer sie ausgegraut sieht,
    # versteht warum.
    #
    brauchbar = {d["name"]: d["usable"] for d in inhalt["files"]}

    assert brauchbar == {"lose.mp3": True, "notiz.txt": False}, brauchbar

    assert [d["size"] for d in inhalt["files"] if d["name"] == "lose.mp3"] \
        == [50], inhalt["files"]

    print("OK: Der Stick laesst sich durchsehen, samt Groessen und Eignung")

    # ----------------------------------------------------------------
    # Kein Ausbruch aus dem Stick
    #
    # Was vom Browser kommt, darf nicht bestimmen, WO gelesen wird -
    # sonst waere das ein Dateimanager fuer das ganze System.
    # ----------------------------------------------------------------

    for boese in ("..", "../..", "Album/../..", "/etc"):

        assert s.aufloesen(boese) is None, (
            f"{boese!r} fuehrt aus dem Stick heraus: {s.aufloesen(boese)}"
        )

    assert s.browse("..") is None

    print("OK: Pfade, die aus dem Stick herausfuehren, werden abgewiesen")

    # ----------------------------------------------------------------
    # Ordner wandern MIT ihrer Struktur
    # ----------------------------------------------------------------

    musik = wurzel / "musik"
    musik.mkdir()

    gebraucht = s.groesse_von(["Album", "lose.mp3"], ENDUNGEN_MUSIK)

    assert gebraucht == 350, (
        f"Gebraucht werden {gebraucht} Byte - erwartet 350 (100 + 200 + "
        f"50; cover.jpg zaehlt nicht mit)."
    )

    gesehen = []

    bericht = s.hereinkopieren(
        ["Album", "lose.mp3"],
        musik,
        endungen=ENDUNGEN_MUSIK,
        on_progress=lambda k, g, name: gesehen.append((k, g, name)),
    )

    assert bericht["kopiert"] == 3, bericht
    assert bericht["uebersprungen"] == 0, bericht
    assert bericht["fehlgeschlagen"] == 0, bericht

    liegt = sorted(
        str(pfad.relative_to(musik))
        for pfad in musik.rglob("*") if pfad.is_file()
    )

    assert liegt == [
        "Album/CD1/01 Intro.mp3",
        "Album/CD1/02 Lied.flac",
        "lose.mp3",
    ], (
        f"Die Struktur stimmt nicht: {liegt}. Ein Album gehoert als Album "
        f"in die Bibliothek - sonst liegen zwei Alben mit '01 Intro.mp3' "
        f"uebereinander."
    )

    assert "cover.jpg" not in str(liegt), liegt

    assert gesehen and gesehen[-1][0] == gesehen[-1][1] == 350, (
        f"Der Fortschritt endet nicht bei 100%: {gesehen[-3:]}"
    )

    print(f"OK: Ordner wandern mit ihrer Struktur ({liegt})")

    # ----------------------------------------------------------------
    # Vorhandenes wird UEBERSPRUNGEN, nicht ueberschrieben
    #
    # Dieselbe Regel wie beim Kopieren auf den Stick. Was man sich mit
    # einem Fehlgriff zerstoert, ist sonst genau das, was man aufheben
    # wollte.
    # ----------------------------------------------------------------

    (musik / "lose.mp3").write_bytes(b"WICHTIG")

    zweiter = s.hereinkopieren(
        ["lose.mp3"], musik, endungen=ENDUNGEN_MUSIK
    )

    assert zweiter["uebersprungen"] == 1 and zweiter["kopiert"] == 0, zweiter

    assert (musik / "lose.mp3").read_bytes() == b"WICHTIG", (
        "Eine vorhandene Datei wurde ueberschrieben."
    )

    print("OK: Gleichnamige Dateien bleiben unberuehrt")

    # ----------------------------------------------------------------
    # Ins Aufnahmeverzeichnis flach, und nur Wave64
    #
    # Dieses Verzeichnis ist flach - eine Datei in einem Unterordner
    # faende XRack dort nie wieder.
    # ----------------------------------------------------------------

    (s.MOUNT_POINT / "Sicherung").mkdir()
    (s.MOUNT_POINT / "Sicherung" / "Umbrella-1_p.w64").write_bytes(b"w" * 20)
    (s.MOUNT_POINT / "Sicherung" / "beipack.mp3").write_bytes(b"m" * 5)

    aufnahmen = wurzel / "recordings"
    aufnahmen.mkdir()

    bericht = s.hereinkopieren(
        ["Sicherung"],
        aufnahmen,
        endungen=ENDUNGEN_AUFNAHMEN,
        flach=True,
    )

    assert bericht["kopiert"] == 1, bericht

    liegt = sorted(
        str(pfad.relative_to(aufnahmen))
        for pfad in aufnahmen.rglob("*") if pfad.is_file()
    )

    assert liegt == ["Umbrella-1_p.w64"], (
        f"Im Aufnahmeverzeichnis liegt {liegt} - es gehoert flach, und "
        f"Musik gehoert gar nicht hinein."
    )

    print("OK: Aufnahmen landen flach, und nur Wave64")

    # ----------------------------------------------------------------
    # Ein Abbruch hinterlaesst keine halbe Datei
    #
    # Das Ziel ist die SD-Karte, auf der XRack arbeitet. Eine halbe
    # Datei mit dem richtigen Namen faellt erst auf, wenn man sie
    # braucht - deshalb wird daneben geschrieben und erst am Ende
    # umbenannt.
    # ----------------------------------------------------------------

    ziel_eng = wurzel / "eng"
    ziel_eng.mkdir()

    def platzt(kopiert, gesamt, name):
        raise OSError(28, "No space left on device")

    bericht = s.hereinkopieren(
        ["lose.mp3"],
        ziel_eng,
        endungen=ENDUNGEN_MUSIK,
        on_progress=platzt,
    )

    assert bericht["fehlgeschlagen"] == 1, bericht

    reste = list(ziel_eng.iterdir())

    assert reste == [], (
        f"Nach dem Abbruch liegt etwas im Ziel: {[p.name for p in reste]}"
    )

    print("OK: Nach einem Abbruch bleibt auch hier nichts Halbes liegen")

    # ----------------------------------------------------------------
    # Und wenn NIEMAND aufraeumt
    #
    # Der Fehlerzweig oben raeumt auf - deshalb sagt er nichts darueber,
    # ob daneben geschrieben und erst am Ende umbenannt wird. Der
    # Unterschied zeigt sich erst, wenn gar kein Aufraeumen mehr
    # stattfindet: Strom weg, SIGKILL, Stick gezogen.
    #
    # Nachgestellt mit einer Ausnahme, die der Fehlerzweig NICHT faengt.
    # Was dann liegen bleibt, darf nicht wie eine fertige Datei
    # aussehen: Eine halbe Aufnahme mit dem richtigen Namen faellt erst
    # auf, wenn man sie braucht.
    # ----------------------------------------------------------------

    ziel_hart = wurzel / "hart"
    ziel_hart.mkdir()

    def stirbt(kopiert, gesamt, name):
        raise KeyboardInterrupt("Strom weg")

    try:
        s.hereinkopieren(
            ["lose.mp3"],
            ziel_hart,
            endungen=ENDUNGEN_MUSIK,
            on_progress=stirbt,
        )

    except KeyboardInterrupt:
        pass

    else:
        raise AssertionError(
            "Der harte Abbruch wurde verschluckt - dann sagt dieser "
            "Versuch nichts."
        )

    fertige = [
        pfad.name for pfad in ziel_hart.iterdir()
        if not pfad.name.endswith(".teil")
    ]

    assert fertige == [], (
        f"Nach einem harten Abbruch liegt {fertige} im Ziel und sieht aus "
        f"wie eine fertige Datei. Geschrieben gehoert daneben (.teil), "
        f"umbenannt erst am Ende - das ist unteilbar."
    )

    print("OK: Auch ohne Aufraeumen entsteht keine Datei mit richtigem Namen")


print("Alle USB-Tests erfolgreich.")
