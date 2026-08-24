"""
Prüft die Kennzeichnung von Aufnahmen und Übungsmixen im Dateinamen
(core/recording_kind.py) sowie die fortlaufende Nummerierung in
writer/audio_writer.py.

Der wichtigste Teil ist die Nummerierung: Vergibt _next_index() nach
Einführung des Kürzels versehentlich wieder die 1, überschreibt
W64Writer.open() (Modus "wb") die vorhandene Aufnahme - also echter
Datenverlust.
"""

import shutil
import tempfile
from pathlib import Path

from core.recording_kind import (
    KIND_PRACTICE,
    KIND_SOUNDCHECK,
    MARKER_PRACTICE,
    MARKER_SOUNDCHECK,
    kind_from_filename,
    strip_marker,
)
from writer.audio_writer import AudioWriter


class DummyWriter(AudioWriter):
    """Nur zum Testen der Namensvergabe - schreibt nichts."""

    def open(self, *args, **kwargs):
        pass

    def write(self, data):
        pass

    def close(self):
        pass


def make_writer(directory: Path) -> DummyWriter:
    writer = DummyWriter()
    writer.directory = directory
    return writer


scratch = Path(tempfile.mkdtemp(prefix="xrack_kind_test_"))

try:

    # ----------------------------------------------------------------
    # 1. Namensschema
    # ----------------------------------------------------------------

    writer = make_writer(scratch)

    name = Path(writer.create_filename("w64", prefix="Soundcheck")).name
    assert name == "Soundcheck-1_s.w64", f"Unerwarteter Name: {name}"

    name = Path(
        writer.create_filename(
            "w64",
            prefix="Bohemian Rhapsody",
            marker=MARKER_PRACTICE,
        )
    ).name
    assert name == "Bohemian Rhapsody-1_p.w64", f"Unerwarteter Name: {name}"

    print("OK: Dateinamen tragen das passende Kürzel (_s / _p)")

    # ----------------------------------------------------------------
    # 2. Zwei Aufnahmen hintereinander dürfen NICHT denselben Namen
    #    bekommen (sonst überschreibt die zweite die erste)
    # ----------------------------------------------------------------

    directory = Path(tempfile.mkdtemp(prefix="xrack_kind_seq_"))
    writer = make_writer(directory)

    names = []

    for _ in range(5):
        path = Path(writer.create_filename("w64", prefix="Soundcheck"))
        path.touch()
        names.append(path.name)

    assert len(set(names)) == len(names), (
        f"Namen wiederholen sich - die vorherige Aufnahme würde "
        f"überschrieben: {names}"
    )

    assert names == [
        "Soundcheck-1_s.w64",
        "Soundcheck-2_s.w64",
        "Soundcheck-3_s.w64",
        "Soundcheck-4_s.w64",
        "Soundcheck-5_s.w64",
    ], f"Unerwartete Reihenfolge: {names}"

    print("OK: Fünf Aufnahmen hintereinander bekommen fünf verschiedene Namen")

    shutil.rmtree(directory, ignore_errors=True)

    # ----------------------------------------------------------------
    # 3. Altbestand ohne Kürzel wird mitgezählt
    #
    # Auf einem bestehenden Pi liegen Aufnahmen im alten Schema
    # ("Soundcheck-7.w64"). Der Zähler muss darüber hinweg weiterzählen,
    # sonst fängt er wieder bei 1 an und überschreibt sie.
    # ----------------------------------------------------------------

    directory = Path(tempfile.mkdtemp(prefix="xrack_kind_mixed_"))
    writer = make_writer(directory)

    (directory / "Soundcheck-1.w64").touch()
    (directory / "Soundcheck-7.w64").touch()

    name = Path(writer.create_filename("w64", prefix="Soundcheck")).name
    assert name == "Soundcheck-8_s.w64", (
        f"Zähler ignoriert Altbestand ohne Kürzel: {name} "
        f"(würde eine vorhandene Aufnahme überschreiben)"
    )

    print("OK: Alte Aufnahmen ohne Kürzel werden beim Zählen berücksichtigt")

    # Gemischt: alt, neu mit _s und neu mit _p
    (directory / "Soundcheck-12_s.w64").touch()

    name = Path(writer.create_filename("w64", prefix="Soundcheck")).name
    assert name == "Soundcheck-13_s.w64", f"Unerwarteter Name: {name}"

    print("OK: Gemischtes Verzeichnis (mit und ohne Kürzel) zählt korrekt weiter")

    shutil.rmtree(directory, ignore_errors=True)

    # ----------------------------------------------------------------
    # 4. Präfixe zählen unabhängig voneinander
    # ----------------------------------------------------------------

    directory = Path(tempfile.mkdtemp(prefix="xrack_kind_prefix_"))
    writer = make_writer(directory)

    Path(writer.create_filename("w64", prefix="Soundcheck")).touch()
    Path(writer.create_filename("w64", prefix="Soundcheck")).touch()

    name = Path(
        writer.create_filename("w64", prefix="Konzert", marker=MARKER_PRACTICE)
    ).name

    assert name == "Konzert-1_p.w64", (
        f"Ein neues Präfix muss wieder bei 1 anfangen, bekam: {name}"
    )

    print("OK: Verschiedene Präfixe zählen unabhängig voneinander")

    shutil.rmtree(directory, ignore_errors=True)

    # ----------------------------------------------------------------
    # 5. Art der Datei am Namen erkennen
    # ----------------------------------------------------------------

    cases = [
        ("Bohemian Rhapsody-1_p.w64", KIND_PRACTICE),
        ("Soundcheck-1_s.w64", KIND_SOUNDCHECK),
        # Altbestand ohne Kürzel
        ("Soundcheck-7.w64", KIND_SOUNDCHECK),
        # Hochgeladene Fremddatei
        ("irgendwas.w64", KIND_SOUNDCHECK),
        # Name endet auf "p", aber ohne Unterstrich -> kein Kürzel
        ("Workshop-1.w64", KIND_SOUNDCHECK),
    ]

    for filename, expected in cases:
        actual = kind_from_filename(filename)
        assert actual == expected, (
            f"{filename}: erwartet {expected}, bekommen {actual}"
        )

    print("OK: Art der Datei wird am Namen korrekt erkannt")

    # ----------------------------------------------------------------
    # 6. strip_marker() lässt Namen ohne Kürzel unangetastet
    # ----------------------------------------------------------------

    assert strip_marker("12_s") == "12"
    assert strip_marker("12_p") == "12"
    assert strip_marker("12") == "12"
    assert strip_marker("Workshop") == "Workshop"

    print("OK: strip_marker() entfernt nur echte Kürzel")

    # ----------------------------------------------------------------
    # 7. Ein heruntergeladener und wieder hochgeladener Übungsmix
    #    behält seine Art (das ist der Zweck des Kürzels im Namen)
    # ----------------------------------------------------------------

    roundtrip = "Bohemian Rhapsody-1_p.w64"
    assert kind_from_filename(roundtrip) == KIND_PRACTICE

    print("OK: Kürzel übersteht Download/Upload - die Art bleibt erhalten")

    print("Alle Tests erfolgreich.")

finally:

    shutil.rmtree(scratch, ignore_errors=True)
