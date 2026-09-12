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

Aus demselben Grund steht dort auch der **erste aufgenommene Kanal**,
wenn es nicht Kanal 1 war: `Probe-3_s9.w64` wurde ab Kanal 9
aufgenommen. Ohne diese Angabe landete die Aufnahme beim virtuellen
Soundcheck wieder auf Kanal 1 - also auf den falschen Kanälen des
Pults, und zwar ohne dass es jemandem auffiele, bis der Ton aus dem
falschen Weg kommt.

Namen ohne Ziffer meinen Kanal 1. Das gilt für alles, was vor dieser
Erweiterung entstanden ist, und ist der Normalfall.

Dieses Modul importiert bewusst nichts aus dem Projekt, damit es sowohl
von writer/ als auch von web/ benutzt werden kann, ohne einen
Import-Zyklus zu erzeugen.
"""

import re

from pathlib import Path

MARKER_SOUNDCHECK = "s"
MARKER_PRACTICE = "p"

MARKERS = (MARKER_SOUNDCHECK, MARKER_PRACTICE)

#
# Das Kürzel am Ende des Namens: Unterstrich, ein Buchstabe, und
# optional der erste aufgenommene Kanal.
#
KUERZEL = re.compile(r"_([" + "".join(MARKERS) + r"])(\d*)$")

KIND_SOUNDCHECK = "soundcheck"
KIND_PRACTICE = "practice"


def kind_from_filename(filename: str) -> str:
    """
    Ermittelt die Art einer Datei an ihrem Namen.

    Alles ohne `_p`-Kürzel gilt als Soundcheck - das gilt bewusst auch
    für ältere Aufnahmen, die noch ganz ohne Kürzel entstanden sind, und
    für hochgeladene Fremddateien.
    """

    treffer = KUERZEL.search(Path(filename).stem)

    if treffer is not None and treffer.group(1) == MARKER_PRACTICE:
        return KIND_PRACTICE

    return KIND_SOUNDCHECK


def strip_marker(stem: str) -> str:
    """
    Entfernt ein eventuell vorhandenes Kürzel vom Dateinamen (ohne
    Endung), samt Kanalangabe. Namen ganz ohne Kürzel bleiben
    unverändert - das ist wichtig, damit
    writer/audio_writer.py:_next_index() alte und neue Aufnahmen
    gemeinsam durchzählen kann.
    """

    return KUERZEL.sub("", stem)


def start_channel_from_filename(filename: str) -> int:
    """
    Der erste aufgenommene Kanal (1-basiert) - 1, wenn nichts
    dabeisteht.

    Das ist die Zahl, mit der die Aufnahme beim virtuellen Soundcheck
    wieder auf denselben Kanälen landet, auf denen sie entstanden ist.
    """

    treffer = KUERZEL.search(Path(filename).stem)

    if treffer is None or not treffer.group(2):
        return 1

    try:
        return max(1, int(treffer.group(2)))
    except ValueError:
        return 1


def marker_mit_kanal(marker: str, start_channel: int = 1) -> str:
    """
    Das Kürzel, wie es in den Dateinamen gehört.

    Bei Kanal 1 bleibt es beim blossen Buchstaben - so heissen alle
    bisherigen Aufnahmen, und daran soll sich für den Normalfall
    nichts ändern.
    """

    if start_channel and start_channel > 1:
        return f"{marker}{int(start_channel)}"

    return marker
