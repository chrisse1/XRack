#!/usr/bin/env python3
"""
Die Sperrmatrix als Tabelle: Was darf gleichzeitig laufen?

Die Regel dahinter ist keine Vorsicht, sondern die Hardware. Das
Interface nimmt EINEN Wiedergabestrom an - zwei gleichzeitig scheitern
in ALSA, und zu sehen wäre nur ein Knopf, der nichts tut. Ein
Aufnahmestrom daneben ist dagegen kein Problem; genau davon lebt
XRack.

Die Tabelle steht hier und nicht in Prosa, weil sich beim Umbau der
Üben-Karte gezeigt hat, wie leicht eine Zeile davon verlorengeht: Üben
läuft über den Musikspieler, Aufnahme + Musik war immer erlaubt - also
ist Aufnahme + Üben es auch, und das ist der ganze Sinn des
Mitschneidens. Wer eine Sperre "sicherheitshalber" ergänzt, nimmt
genau die Funktion wieder weg.

Geprüft werden die ECHTEN Methoden der Anwendungsschicht; nur die
Hardware darunter ist nachgestellt.
"""

import sys
import tempfile
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE", "PCM_FORMAT_S24_LE", "PCM_FORMAT_S32_LE",
    "PCM_CAPTURE", "PCM_PLAYBACK", "PCM_NORMAL",
):
    setattr(fake_alsaaudio, name, 0)
sys.modules.setdefault("alsaaudio", fake_alsaaudio)

from core.application.aufnahme import AufnahmeMixin  # noqa: E402
from core.application.musik import MusikMixin  # noqa: E402
from core.state_store import StateStore  # noqa: E402


MIX = "Uebung-1_p.w64"
AUFNAHME = "Soundcheck-1_s.w64"
MUSIKSTUECK = "lied.mp3"


class Spieler:
    """Der Musikspieler - er spielt Musik UND Übungsmixe."""

    def __init__(self):
        self.playing = False
        self.paused = False
        self.wiederholen = False

    def set_wiederholen(self, an):
        self.wiederholen = bool(an)

    def stop(self):
        self.playing = False

    def play_file(self, *a, **k):
        self.playing = True
        return True

    def play_folder(self, *a, **k):
        self.playing = True
        return True

    def play_practice(self, *a, **k):
        self.playing = True
        return True


class Soundcheckspieler:
    """Der eigene Spieler für Aufnahmen."""

    def __init__(self):
        self.playing = False

    def start(self, *a, **k):
        self.playing = True
        return True

    def stop(self):
        self.playing = False


class Schreiber:
    def __init__(self, ordner):
        self.directory = ordner


class Aufnehmer:
    def __init__(self, ordner, namen):
        self.writer = Schreiber(ordner)
        self.recordings = list(namen)
        self.bereit = True
        self.recording = False

    def start(self, name_prefix="Soundcheck", trenner="-"):
        if not self.bereit or self.recording:
            return False
        self.recording = True
        return True

    def stop(self):
        self.recording = False


class Buecherei:
    """Die Musikbibliothek - sie findet jede Datei."""

    def __init__(self, ordner):
        self.ordner = ordner

    def resolve(self, pfad):
        return self.ordner / pfad


class Protokoll:
    def warning(self, *a, **k):
        pass

    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class Anwendung(AufnahmeMixin, MusikMixin):
    """
    Die echten Sperren auf nachgestellter Hardware.

    Zusammengesetzt wie die richtige Application (core/application/
    __init__.py), nur ohne ALSA, Netzwerk und DMX.
    """

    def __init__(self, ordner: Path):

        self.logger = Protokoll()

        self.state_store = StateStore(ordner / "state.json")

        self.music_player = Spieler()
        self.player = Soundcheckspieler()
        self.recorder = Aufnehmer(ordner, [MIX, AUFNAHME])
        self.music_library = Buecherei(ordner)

        self.selected_audio_device = "hw:1,0"
        self.mixer_sample_rate = 48000
        self.record_name_prefix = "Soundcheck"

        self.music_channel_preference = 1
        self.player_mode = "practice"
        self.practice_repeat = False
        self.practice_record = False
        self.practice_recording = False
        self.practice_active = False
        self.practice_offset_ms = 0


arbeit = tempfile.TemporaryDirectory()
ORDNER = Path(arbeit.name)

for name in (MIX, AUFNAHME, MUSIKSTUECK):
    (ORDNER / name).write_bytes(b"x")


# --------------------------------------------------------------------
# Die vier Dinge, die laufen können - und wie man sie startet
# --------------------------------------------------------------------

def laeuft_aufnahme(app):
    app.recorder.recording = True


def laeuft_soundcheck(app):
    app.player.playing = True


def laeuft_musik(app):
    app.music_player.playing = True


def laeuft_ueben(app):
    app.music_player.playing = True
    app.practice_active = True


def starte_aufnahme(app):
    return app.start_recording()


def starte_soundcheck(app):
    return app.start_soundcheck(AUFNAHME)


def starte_musik(app):
    return app.play_music_file(MUSIKSTUECK, 1)


def starte_ueben(app):
    erfolg, _ = app.start_practice(MIX)
    return erfolg


VORHER = {
    "nichts": lambda app: None,
    "Aufnahme": laeuft_aufnahme,
    "Soundcheck": laeuft_soundcheck,
    "Musik": laeuft_musik,
    "Üben": laeuft_ueben,
}

STARTEN = {
    "Aufnahme": starte_aufnahme,
    "Soundcheck": starte_soundcheck,
    "Musik": starte_musik,
    "Üben": starte_ueben,
}


# ====================================================================
# Die Tabelle
#
# Lesart: "läuft gerade X - darf Y starten?"
#
# Die Begründung steht dabei, denn eine Tabelle ohne Begründung ist
# beim nächsten Umbau nur ein Hindernis, das man wegräumt.
# ====================================================================

MATRIX = [
    # (läuft, starten, erlaubt, warum)

    ("nichts", "Aufnahme",   True,  "nichts im Weg"),
    ("nichts", "Soundcheck", True,  "nichts im Weg"),
    ("nichts", "Musik",      True,  "nichts im Weg"),
    ("nichts", "Üben",       True,  "nichts im Weg"),

    #
    # Ein Aufnahmestrom und ein Wiedergabestrom gehen nebeneinander -
    # davon lebt XRack.
    #
    ("Aufnahme", "Musik", True,
     "ein Aufnahme-, ein Wiedergabestrom - das kann das Interface"),

    ("Aufnahme", "Üben", True,
     "GENAU DARUM GEHT ES beim Mitschneiden: zum Mix spielen und sich "
     "dabei aufnehmen"),

    #
    # Aber nicht dieselbe Datei lesen und schreiben.
    #
    ("Aufnahme", "Soundcheck", False,
     "dieselbe Datei würde gelesen und beschrieben"),

    ("Soundcheck", "Aufnahme", False,
     "dieselbe Datei würde gelesen und beschrieben"),

    #
    # Zwei Wiedergabestroeme kann das Interface nicht. Diese vier
    # Zeilen sind der Grund, warum die Ueben-Karte ein Umschalter ist
    # und nicht eine zweite Karte daneben.
    #
    ("Soundcheck", "Musik", False, "zwei Wiedergabeströme"),
    ("Soundcheck", "Üben",  False, "zwei Wiedergabeströme"),
    ("Musik", "Soundcheck", False, "zwei Wiedergabeströme"),
    ("Üben",  "Soundcheck", False, "zwei Wiedergabeströme"),

    #
    # Musik und Ueben teilen sich den Spieler. Ein Titelwechsel ist
    # erlaubt (Musik loest Musik ab), eine laufende Uebung aber nicht:
    # Sie verschwaende sonst stillschweigend - samt Mitschnitt, der
    # weiterliefe.
    #
    ("Musik", "Üben",  False, "ein Spieler, eine Quelle"),
    ("Üben",  "Musik", False,
     "die Übung verschwände stillschweigend, der Mitschnitt liefe weiter"),
    ("Üben",  "Üben",  False, "erst anhalten"),

    #
    # Waehrend einer Uebung aufnehmen: erlaubt. Das ist dieselbe Zeile
    # wie Aufnahme+Ueben, nur von der anderen Seite - und sie ist die
    # wichtigste der Tabelle.
    #
    ("Üben", "Aufnahme", True,
     "ein Aufnahmestrom neben dem Wiedergabestrom"),

    ("Musik", "Aufnahme", True,
     "ein Aufnahmestrom neben dem Wiedergabestrom"),
]


fehler = []

for laeuft, starten, erlaubt, warum in MATRIX:

    app = Anwendung(ORDNER)

    VORHER[laeuft](app)

    ergebnis = bool(STARTEN[starten](app))

    if ergebnis is not erlaubt:

        fehler.append(
            f"  Es läuft {laeuft}, gestartet wird {starten}: "
            f"{'erlaubt' if ergebnis else 'abgelehnt'} - erwartet war "
            f"{'erlaubt' if erlaubt else 'abgelehnt'} ({warum})"
        )

assert not fehler, (
    "Die Sperrmatrix stimmt nicht mehr:\n" + "\n".join(fehler)
)

print(f"OK: Alle {len(MATRIX)} Kombinationen verhalten sich wie festgelegt")


# ====================================================================
# Ein Übungsmix ist kein Soundcheck
#
# Beide sind .w64-Dateien im selben Ordner, und lange spielte der
# Soundcheck-Knopf auch Übungsmixe ab. Damit gab es den Weg zweimal -
# und der über den Soundcheck-Spieler konnte weniger: kein Anhalten,
# kein Spulen, keine Schleife. Zum Üben ist genau das nötig.
# ====================================================================

app = Anwendung(ORDNER)

assert app.start_soundcheck(AUFNAHME), (
    "Eine Aufnahme lässt sich nicht mehr als Soundcheck abspielen - "
    "das ist der Sinn der Karte."
)

app.player.playing = False

assert not app.start_soundcheck(MIX), (
    "Ein Übungsmix lässt sich weiterhin über den Soundcheck abspielen. "
    "Damit gibt es den Weg zweimal, und der hier kann weder anhalten "
    "noch spulen."
)

print("OK: Der Soundcheck spielt Aufnahmen - und nur die")


# ====================================================================
# Die Übung endet auch, wenn niemand stoppt
#
# Ein Stück ist zu Ende, keine Schleife - dann hört der Spieler von
# selbst auf. Bliebe XRack dabei auf "es läuft eine Übung" stehen,
# liesse sich danach nie wieder Musik starten.
# ====================================================================

app = Anwendung(ORDNER)

erfolg, meldung = app.start_practice(MIX)

assert erfolg, meldung
assert app.practice_active is True

#
# Der Spieler ist von selbst fertig. Gemerkt wird das bei der
# naechsten Statusabfrage - genau die Stelle wird hier gerufen.
#
app.music_player.playing = False

app.uebung_nachfuehren()

assert app.practice_active is False, (
    "XRack hält sich noch für übend, obwohl der Spieler längst still "
    "ist."
)

assert app.play_music_file(MUSIKSTUECK, 1), (
    "Nach dem Ende der Übung liess sich keine Musik starten - XRack "
    "hielt sich für weiterhin übend."
)

print("OK: Eine beendete Übung blockiert nichts mehr")


arbeit.cleanup()

print("Alle Tests der Sperrmatrix erfolgreich.")
