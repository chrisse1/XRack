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


print("Alle USB-Tests erfolgreich.")
