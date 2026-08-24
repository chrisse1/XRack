"""
Unterscheidet die zwei Arten von Dateien in `recordings/`:

- **Soundcheck** (`_s`): eine echte Mehrkanal-Aufnahme vom Pult, die
  beim virtuellen Soundcheck wieder auf denselben Kanälen landet.
- **Übungsmix** (`_p`, für "practice"): mehrere zu einer Datei
  zusammengefügte Stereo-Stems zum Mitspielen, siehe
  core/stem_combiner.py.

Das Kürzel steckt bewusst im Dateinamen und nicht in einer separaten
Verwaltungsdatei: so reist die Zuordnung über USB-Stick, Download, DAW
und Backup mit der Datei mit, und XRack muss nirgends Buch führen. Eine
heruntergeladene und später wieder hochgeladene Datei behält dadurch
ihre Art.

Dieses Modul importiert bewusst nichts aus dem Projekt, damit es sowohl
von writer/ als auch von web/ benutzt werden kann, ohne einen
Import-Zyklus zu erzeugen.
"""

from pathlib import Path

MARKER_SOUNDCHECK = "s"
MARKER_PRACTICE = "p"

MARKERS = (MARKER_SOUNDCHECK, MARKER_PRACTICE)

KIND_SOUNDCHECK = "soundcheck"
KIND_PRACTICE = "practice"


def kind_from_filename(filename: str) -> str:
    """
    Ermittelt die Art einer Datei an ihrem Namen.

    Alles ohne `_p`-Kürzel gilt als Soundcheck - das gilt bewusst auch
    für ältere Aufnahmen, die noch ganz ohne Kürzel entstanden sind, und
    für hochgeladene Fremddateien.
    """

    stem = Path(filename).stem

    if stem.endswith(f"_{MARKER_PRACTICE}"):
        return KIND_PRACTICE

    return KIND_SOUNDCHECK


def strip_marker(stem: str) -> str:
    """
    Entfernt ein eventuell vorhandenes Kürzel vom Dateinamen (ohne
    Endung). Namen ganz ohne Kürzel bleiben unverändert - das ist
    wichtig, damit writer/audio_writer.py:_next_index() alte und neue
    Aufnahmen gemeinsam durchzählen kann.
    """

    for marker in MARKERS:

        suffix = f"_{marker}"

        if stem.endswith(suffix):
            return stem[:-len(suffix)]

    return stem
