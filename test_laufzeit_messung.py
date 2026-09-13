#!/usr/bin/env python3
"""
Prüft die Laufzeitmessung (core/laufzeit_messung.py).

Was hier geprüft wird, ist der Kern der Sache: Ein Mitschnitt mit
BEKANNTER Laufzeit wird künstlich erzeugt, und die Messung muss genau
diese Laufzeit herausbekommen. Damit ist die Rechnung geprüft, ohne
dass ein Pult im Raum steht - und wenn sie am Gerät eine falsche Zahl
liefert, liegt es am Weg und nicht an der Auswertung.

Der Weg selbst (Interface, USB, Pult) lässt sich hier nicht
nachstellen. Genau deshalb gibt es die Messung ja.
"""

import os
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import core.laufzeit_messung as messung  # noqa: E402
from core.laufzeit_messung import (  # noqa: E402
    KLICK_BEI_S,
    KLICK_DAUER_S,
    KLICK_PEGEL,
    VOLLAUSSCHLAG,
    klick_datei,
    klick_finden,
    mittlerer_wert,
    versatz_ms,
)
from reader.w64_reader import W64Reader  # noqa: E402
from writer.w64_writer import W64Writer  # noqa: E402

RATE = 48000


def mitschnitt(ordner: Path, versatz_rahmen: int, kanaele: int = 2,
               rauschen: int = 0, mit_klick: bool = True,
               dauer_s: float = 3.0) -> Path:
    """
    Ein Mitschnitt, wie ihn der Recorder schriebe - mit einem Klick an
    einer genau bekannten Stelle.

    `versatz_rahmen` ist die Laufzeit, die herauskommen muss.
    """

    schreiber = W64Writer()
    schreiber.directory = ordner

    schreiber.open(
        channels=kanaele,
        sample_rate=RATE,
        bits_per_sample=24,
        name_prefix="Pruefmitschnitt",
    )

    klick_von = int(KLICK_BEI_S * RATE) + versatz_rahmen
    klick_bis = klick_von + int(KLICK_DAUER_S * RATE)

    block = bytearray()

    for n in range(int(dauer_s * RATE)):

        if mit_klick and klick_von <= n < klick_bis:
            anteil = (n - klick_von) / max(1, klick_bis - klick_von)
            wert = int(
                KLICK_PEGEL * (VOLLAUSSCHLAG - 1) * (1.0 - anteil)
            )
        else:
            #
            # Grundrauschen als saegender Wechsel - ein fester Wert
            # waere eine Gleichspannung und kein Rauschen.
            #
            wert = rauschen if n % 2 else -rauschen

        block += struct.pack("<i", wert) * kanaele

    schreiber.write(bytes(block))
    schreiber.close()

    return Path(schreiber.filename)


arbeit = tempfile.TemporaryDirectory()
ORDNER = Path(arbeit.name)


# ====================================================================
# 1. Der Klick-Mix ist eine echte Datei mit einem Klick darin
#
# Er wird vom selben Schreiber angelegt wie jede Aufnahme - und muss
# vom eigenen Leser wieder zu lesen sein. Eine Messdatei, die XRack
# selbst nicht lesen kann, wäre der denkbar schlechteste Anfang.
# ====================================================================

KANAELE = 18

klick = klick_datei(ORDNER, KANAELE, RATE)

leser = W64Reader()
leser.open(klick)

assert leser.channels == KANAELE, leser.channels
assert leser.sample_rate == RATE, leser.sample_rate

assert abs(leser.duration - messung.MESSDAUER_S) < 0.01, (
    f"Der Klick-Mix ist {leser.duration:.2f} s lang statt "
    f"{messung.MESSDAUER_S} s."
)

leser.close()

#
# Und der Klick sitzt dort, wo er sitzen soll: Auf sich selbst
# angewandt muss die Messung 0 ergeben.
#
rahmen, schwelle = klick_finden(klick)

assert rahmen >= 0, "Im eigenen Klick-Mix ist kein Klick zu finden."

assert abs(rahmen - int(KLICK_BEI_S * RATE)) <= 2, (
    f"Der Klick steht bei Rahmen {rahmen}, erwartet war "
    f"{int(KLICK_BEI_S * RATE)}."
)

gemessen, grund = versatz_ms(klick, RATE)

assert gemessen == 0, (
    f"Der Klick-Mix gegen sich selbst ergibt {gemessen} ms statt 0 - "
    f"dann ist die Rechnung schon im Ansatz verschoben. ({grund})"
)

print("OK: Der Klick-Mix ist lesbar und der Klick sitzt an seiner Stelle")


# ====================================================================
# 2. Eine bekannte Laufzeit wird genau wiedergefunden
#
# Das ist die Messung. Alles andere ist Beiwerk.
# ====================================================================

for erwartet_ms in (0, 12, 21, 43, 85, 170, 500):

    rahmen = int(erwartet_ms * RATE / 1000)

    datei = mitschnitt(ORDNER, rahmen)

    gemessen, grund = versatz_ms(datei, RATE)

    assert grund == "", grund

    assert abs(gemessen - erwartet_ms) <= 1, (
        f"Bei einer Laufzeit von {erwartet_ms} ms misst XRack "
        f"{gemessen} ms. Der Mitschnitt läge beim Zusammenhören um die "
        f"Differenz daneben."
    )

print("OK: Bekannte Laufzeiten von 0 bis 500 ms werden genau gemessen")


# ====================================================================
# 3. Grundrauschen auf dem Kanal stört nicht
#
# Am Pult liegt auf dem aufgenommenen Kanal selten absolute Stille -
# ein Mikrofon rauscht, ein Verstärker brummt. Die Schwelle richtet
# sich deshalb nach dem gemessenen Grundrauschen und nicht nach einer
# festen Zahl.
# ====================================================================

laut = mitschnitt(ORDNER, int(0.06 * RATE), rauschen=int(0.01 * VOLLAUSSCHLAG))

gemessen, grund = versatz_ms(laut, RATE)

assert grund == "", grund

assert abs(gemessen - 60) <= 1, (
    f"Mit Grundrauschen misst XRack {gemessen} ms statt 60 - das "
    f"Rauschen wurde für den Klick gehalten."
)

print("OK: Grundrauschen auf dem Kanal wird nicht für den Klick gehalten")


# ====================================================================
# 4. Kein Klick ist ein Befund, kein Messwert
#
# Wenn der Weg im Pult nicht geschlossen ist, kommt nichts zurück.
# Dann eine Zahl auszugeben wäre das Schlimmste, was die Messung tun
# könnte: Sie würde stillschweigend falsch korrigieren.
# ====================================================================

still = mitschnitt(ORDNER, 0, mit_klick=False,
                   rauschen=int(0.002 * VOLLAUSSCHLAG))

gemessen, grund = versatz_ms(still, RATE)

assert gemessen < 0, (
    f"Aus einem Mitschnitt ohne Klick kam die Zahl {gemessen} heraus."
)

assert "Pult" in grund and "zurück" in grund, (
    f"Die Begründung sagt nicht, was zu tun ist: {grund!r}"
)

print("OK: Ohne Klick gibt es eine Begründung statt einer Zahl")


# ====================================================================
# 5. Ein zu kurzer Mitschnitt liefert keine erfundene Zahl
#
# Ist die Laufzeit grösser als der Rest des Mitschnitts, steht der
# Klick gar nicht darin.
# ====================================================================

kurz = mitschnitt(ORDNER, int(0.05 * RATE), dauer_s=0.5)

gemessen, grund = versatz_ms(kurz, RATE)

assert gemessen < 0 and grund, (
    f"Aus einem zu kurzen Mitschnitt kam {gemessen} ms heraus."
)

print("OK: Ein zu kurzer Mitschnitt liefert keine erfundene Zahl")


# ====================================================================
# 6. Die erste Flanke zählt, nicht die lauteste Stelle
#
# Durch das Pult kommt der Klick nicht allein zurück: Nachhall,
# Rückkopplung, ein Kompressor, der erst nachregelt. Was danach kommt,
# kann lauter sein als der Anfang - gesucht ist aber der Anfang, denn
# er ist die Laufzeit.
# ====================================================================

schreiber = W64Writer()
schreiber.directory = ORDNER
schreiber.open(channels=2, sample_rate=RATE, bits_per_sample=24,
               name_prefix="Nachhall")

erste = int(KLICK_BEI_S * RATE) + int(0.04 * RATE)
zweite = erste + int(0.15 * RATE)

block = bytearray()

for n in range(int(3.0 * RATE)):

    if erste <= n < erste + 240:
        wert = int(0.2 * VOLLAUSSCHLAG)
    elif zweite <= n < zweite + 240:
        #
        # Deutlich lauter - und trotzdem nicht der gesuchte Anfang.
        #
        wert = int(0.9 * VOLLAUSSCHLAG)
    else:
        wert = 0

    block += struct.pack("<i", wert) * 2

schreiber.write(bytes(block))
schreiber.close()

gemessen, grund = versatz_ms(Path(schreiber.filename), RATE)

assert abs(gemessen - 40) <= 1, (
    f"Gemessen wurden {gemessen} ms statt 40 - gefunden wurde die "
    f"lauteste Stelle statt der ersten. Die Laufzeit wäre damit um "
    f"den Nachhall zu gross."
)

print("OK: Gemessen wird die erste Flanke, nicht die lauteste Stelle")


# ====================================================================
# 7. Der ganze Ablauf - mit einem Pult, das den Klick zurückschickt
#
# Bis hierher war es die Rechnung. Jetzt der Weg, den XRack am Gerät
# geht: Klick-Mix schreiben, abspielen, dabei aufnehmen, auswerten,
# Wert merken, aufräumen.
#
# Nachgestellt ist nur die Hardware - und zwar so, wie sie sich wirklich
# verhält: Das "Pult" schickt zurück, was es bekommt, aber um eine
# bekannte Laufzeit verzögert. Genau diese Laufzeit muss am Ende
# dastehen.
# ====================================================================

import threading  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402

fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE", "PCM_FORMAT_S24_LE", "PCM_FORMAT_S32_LE",
    "PCM_CAPTURE", "PCM_PLAYBACK", "PCM_NORMAL",
):
    setattr(fake_alsaaudio, name, 0)
sys.modules.setdefault("alsaaudio", fake_alsaaudio)

from core.application.musik import MusikMixin  # noqa: E402
from core.state_store import StateStore  # noqa: E402

LAUFZEIT_MS = 75


class Pult:
    """
    Ein Pult, das zurückschickt, was es bekommt - um LAUFZEIT_MS
    verzögert.

    Gerechnet wird mit der UHR und nicht mit Rahmenzählern. Das ist
    der Unterschied, an dem die erste Fassung dieses Versuchs
    vorbeilief: Ein echtes Pult hat kein Gedächtnis und keine Zähler.
    Was zur Zeit t hineingeht, kommt zur Zeit t + Laufzeit heraus -
    ganz gleich, wer wann zu lesen beginnt. Nur so lässt sich prüfen,
    was passiert, wenn der Aufnahmestrom später anläuft als der Ton.
    """

    def __init__(self, laufzeit_s):
        self.laufzeit_s = laufzeit_s
        self.klick_zeiten = []
        self.schloss = threading.Lock()

    def ausgeben(self, daten, kanaele, zeitpunkt=None):
        """Merkt sich, WANN ein Klick hinausgegangen ist."""

        if not _enthaelt_klick(daten, kanaele):
            return

        with self.schloss:
            self.klick_zeiten.append(
                zeitpunkt if zeitpunkt is not None else time.monotonic()
            )

    def klick_im_fenster(self, von, bis):
        """
        Wo im Zeitfenster [von, bis) kommt ein Klick zurück?

        Liefert den Abstand zum Fensteranfang in Sekunden, oder None.
        Auf die Stelle IM Block kommt es an: Sonst wäre die
        nachgestellte Messung auf eine Blocklänge gerundet, und ein
        Fehler von 20 ms fiele nicht auf.
        """

        with self.schloss:
            for zeit in self.klick_zeiten:
                ankunft = zeit + self.laufzeit_s
                if von <= ankunft < bis:
                    return ankunft - von

        return None


def _enthaelt_klick(daten, kanaele):

    schritt = kanaele * 4 * 64

    for stelle in range(0, max(0, len(daten) - 4), schritt):
        wert = struct.unpack("<i", daten[stelle:stelle + 4])[0]
        if abs(wert) > 0.1 * VOLLAUSSCHLAG:
            return True

    return False


class Ausgang:
    """Der Wiedergabeweg - er reicht alles ans Pult weiter."""

    def __init__(self, pult):
        self.pult = pult
        self.opened = False
        self.kanaele = 2
        self.rate = RATE

        #
        # Wann der naechste Block zu hoeren ist. None heisst: noch
        # nichts geschrieben, der erste Block laeuft sofort.
        #
        self.faellig = None

    def open(self, device, channels, rate, start_channel=0,
             sample_format=None):
        #
        # Ein echtes ALSA-Geraet braucht zum Oeffnen Zeit, und zwar
        # jedes Mal unterschiedlich viel.
        #
        time.sleep(0.12)
        self.kanaele = channels
        self.rate = rate
        self.opened = True

        #
        # Ein frisch geoeffnetes Geraet faengt neu an zu takten. Ohne
        # das liefe die Zeitrechnung des vorigen Laufs weiter, und der
        # naechste Lauf haette seine Bloecke allesamt "ueberfaellig" -
        # er schuettete sie ohne Pause hinaus.
        #
        self.faellig = None

        return True

    def write(self, daten):
        #
        # In ECHTZEIT annehmen, nicht schneller.
        #
        # Ein ALSA-Geraet nimmt die Bloecke im Takt der Samplerate an.
        # Die erste Fassung dieser Attrappe schluckte sie fuenfmal so
        # schnell; solange das Pult Rahmen zaehlte, fiel das nicht auf.
        # Sobald es nach der Uhr arbeitet - und nur so laesst sich ein
        # verspaeteter Aufnahmestrom nachstellen -, waere der Klick
        # lange vor seiner Zeit draussen.
        #
        # Getaktet wird auf einen FAELLIGKEITSPUNKT, nicht mit einer
        # festen Pause je Block. Der Unterschied ist der zwischen
        # einer Uhr und einer Sanduhr: Die feste Pause haengt jede
        # Verspaetung der Maschine an alle folgenden Bloecke an, und
        # auf einer belasteten Maschine ging dieser Versuch dadurch
        # gelegentlich fehl - ein Lauf lag dann 50 ms hinter den
        # anderen. Ein ALSA-Geraet kennt das nicht: Es hat seine
        # eigene Uhr, und genau dafuer ist sein Puffer da. Ein Block,
        # der spaet angeliefert wird, ist trotzdem zu seiner Zeit zu
        # hoeren.
        #
        rahmen = len(daten) / (self.kanaele * 4)

        jetzt = time.monotonic()

        if self.faellig is None:
            self.faellig = jetzt

        rest = self.faellig - jetzt

        if rest > 0:
            time.sleep(rest)

        #
        # Zu hoeren ist der Block ab seinem Faelligkeitspunkt - nicht
        # ab dem Moment, in dem diese Funktion zurueckkehrt.
        #
        self.pult.ausgeben(daten, self.kanaele, self.faellig)

        self.faellig += rahmen / self.rate

    def close(self):
        self.opened = False


class Eingang:
    """
    Der Aufnahmeweg - er holt sich, was das Pult zurückschickt.

    Mit einem ANLAUF: Der erste Block nach einer Pause kostet Zeit
    (der Faden muss anlaufen, ALSA den Strom in Gang bringen und eine
    volle Periode sammeln). Genau diese Spanne hat am Gerät die
    Messung verdorben, solange der Aufnahmestrom erst mit der Aufnahme
    gestartet wurde - der Mitschnitt begann dadurch später als der
    Ton.
    """

    RAHMEN = 1024

    #
    # So lange braucht der Strom, bis der erste Block da ist.
    #
    # Laenger als das Oeffnen des Wiedergabegeraets (0,12 s) - sonst
    # waere der Strom schon von selbst bereit, wenn der erste Ton
    # hinausgeht, und ein fehlender Vorlauf fiele nicht auf. Auf einem
    # belasteten Pi ist genau das der Fall, den es zu treffen gilt.
    #
    ANLAUF_S = 0.25

    def __init__(self, pult, kanaele, rate):
        self.pult = pult
        self.opened = True
        self.channels = kanaele
        self.native_channels = kanaele
        self.rate = rate
        self.start_channel = 0

        self.blockdauer = self.RAHMEN / rate

        #
        # None heisst: Der Strom steht. Der naechste Block kostet den
        # Anlauf, und die Zeitrechnung beginnt erst dann.
        #
        self.gelesen_bis = None

    def read(self):

        #
        # Der Strom stand: Anlauf zahlen und die Zeitrechnung HIER
        # beginnen. Alles davor ist verpasst - genau wie bei ALSA.
        #
        if self.gelesen_bis is None:
            time.sleep(self.ANLAUF_S)
            self.gelesen_bis = time.monotonic()

        von = self.gelesen_bis
        bis = von + self.blockdauer

        #
        # In Echtzeit warten, bis der Block wirklich vorbei ist. Die
        # Fenster stossen dabei lueckenlos aneinander - ein echter
        # Strom verliert zwischen zwei Bloecken nichts.
        #
        rest = bis - time.monotonic()

        if rest > 0:
            time.sleep(rest)

        self.gelesen_bis = bis

        versatz = self.pult.klick_im_fenster(von, bis)

        block = bytearray()

        anfang = (
            int(versatz * self.rate) if versatz is not None else None
        )

        for n in range(self.RAHMEN):

            wert = (
                int(0.2 * VOLLAUSSCHLAG)
                if anfang is not None and anfang <= n < anfang + 240
                else 0
            )

            block += struct.pack("<i", wert) * self.channels

        return bytes(block)

    def aufnahmebreite(self, daten):
        return daten

    def strom_anhalten(self):
        """Der Strom steht wieder - der naechste Block kostet Anlauf."""

        self.gelesen_bis = None


class Geraet:
    id = "hw:1,0"
    channels = 2
    name = "Pruefpult"


class Anwendung(MusikMixin):
    """Die echten Methoden auf nachgestellter Hardware."""

    def __init__(self, ordner, spieler, aufnehmer):

        self.logger = logging.getLogger("XRack")

        self.state_store = StateStore(ordner / "state.json")

        self.music_player = spieler
        self.recorder = aufnehmer
        self.player = types.SimpleNamespace(playing=False)

        self.selected_audio_device = Geraet()
        self.mixer_sample_rate = RATE
        self.record_name_prefix = "Soundcheck"

        self.player_mode = "practice"
        self.practice_repeat = False
        self.practice_record = False
        self.practice_recording = False
        self.practice_active = False
        self.practice_offset_ms = 0

        self._laufzeit_lock = threading.Lock()
        self._laufzeit_stand = {
            "active": False, "success": None, "ms": 0, "error": "",
        }


import logging  # noqa: E402

from player.music_library import MusicLibrary  # noqa: E402
from player.music_player import MusicPlayer  # noqa: E402
from recorder.recorder import Recorder  # noqa: E402

lauf_ordner = tempfile.TemporaryDirectory()
LAUF = Path(lauf_ordner.name)

pult = Pult(laufzeit_s=LAUFZEIT_MS / 1000)

spieler = MusicPlayer(Ausgang(pult), MusicLibrary(LAUF))

eingang = Eingang(pult, Geraet.channels, RATE)

aufnehmer = Recorder(eingang)

#
# Ein RELATIVES Aufnahmeverzeichnis - genau wie am Geraet
# ("./recordings", siehe config/default.yaml), und dafuer ins
# Arbeitsverzeichnis gewechselt.
#
# Das ist kein Detail: Hier stand einmal ein absoluter Pfad, und damit
# blieb ein Fehler unsichtbar, der am Geraet jede Messung scheitern
# liess. XRack baute den Pfad zum Mitschnitt aus Verzeichnis UND
# Dateiname zusammen, obwohl der Dateiname den Pfad schon enthaelt.
# Bei einem absoluten Verzeichnis gewinnt der absolute Pfad rechts und
# die Verdopplung faellt nicht auf; bei "./recordings" wird
# "recordings/recordings/..." daraus.
#
# Ein Pfad wie "../../tmp/xyz" taugt dafuer uebrigens auch nicht: Er
# kuerzt sich beim Verdoppeln selbst wieder weg. Es muss ein Name
# ohne Aufstieg sein, so wie am Geraet.
#
altes_verzeichnis = os.getcwd()
os.chdir(LAUF)

aufnehmer.writer.directory = Path("recordings")

anwendung = Anwendung(LAUF, spieler, aufnehmer)

#
# Die Messdatei ist drei Sekunden lang - der Lauf dauert also
# mindestens so lange. Kuerzer geht es nicht: Gemessen wird eine
# Laufzeit, und die braucht Zeit.
#
erfolg, meldung = anwendung.start_laufzeit_messung()

assert erfolg, meldung

frist = time.monotonic() + 90

while anwendung.laufzeit_status()["active"] and time.monotonic() < frist:
    time.sleep(0.1)

stand = anwendung.laufzeit_status()

assert stand["success"] is True, (
    f"Die Messung kam zu keinem Ergebnis: {stand}"
)

assert abs(stand["ms"] - LAUFZEIT_MS) <= 25, (
    f"Gemessen wurden {stand['ms']} ms, das Pult verzögert um "
    f"{LAUFZEIT_MS} ms. (Die Toleranz ist grosszügig: Die "
    f"nachgestellten Puffer laufen nicht taktgenau - es geht darum, "
    f"dass die richtige Grössenordnung herauskommt und nicht Null.)"
)

#
# Die Zahl steht hier ausgeschrieben und nicht als messung.MESSUNGEN:
# Sonst prueft sich die Konstante gegen sich selbst, und ein einziger
# Lauf bestuende die Pruefung genauso.
#
assert len(stand["werte"]) == 3, (
    f"Gemessen wurde {len(stand['werte'])}-mal statt dreimal: "
    f"{stand['werte']}. Eine einzelne Zahl ist keine Messung - erst "
    f"mehrere Läufe zeigen, ob sie steht."
)

#
# Eine Periode Unschaerfe bleibt: Der Lesethread bekommt seinen ersten
# Block irgendwo innerhalb einer Periode (gut 21 ms bei 48 kHz). Mehr
# darf es nicht sein - dann waere der Anlauf wieder im Spiel.
#
assert stand["spanne"] <= 25, (
    f"Die Läufe gehen um {stand['spanne']} ms auseinander "
    f"({stand['werte']}), obwohl das Pult jedes Mal gleich verzögert. "
    f"Mehr als eine Periode heisst: Der Mitschnitt beginnt nicht "
    f"verlässlich mit dem Ton."
)

assert stand["unsicher"] is False, stand

assert anwendung.practice_offset_ms == stand["ms"], (
    "Der gemessene Wert wurde nicht als Versatz übernommen - dann "
    "hätte die Messung nichts bewirkt."
)

assert StateStore(LAUF / "state.json").get(
    "practice_offset_ms"
) == stand["ms"], "Der gemessene Wert wurde nicht am Gerät gemerkt."

print(f"OK: Der ganze Ablauf misst die Laufzeit ({stand['ms']} ms)")


# ====================================================================
# 8. Die Messung räumt hinter sich auf
#
# Klick-Mix und Mitschnitt sind Wegwerfdateien. Blieben sie liegen,
# stünden sie in der Aufnahmenliste, und niemand wüsste, wozu.
# ====================================================================

geblieben = sorted(p.name for p in (LAUF / "recordings").glob("*.w64"))

assert geblieben == [], (
    f"Nach der Messung liegen noch Dateien herum: {geblieben}"
)

assert aufnehmer.recording is False, "Die Aufnahme läuft noch."

assert spieler.playing is False, "Die Wiedergabe läuft noch."

print("OK: Die Messung räumt Klick und Mitschnitt wieder weg")


# ====================================================================
# 9. Zwei Messungen gleichzeitig gibt es nicht
# ====================================================================

with anwendung._laufzeit_lock:
    anwendung._laufzeit_stand["active"] = True

erfolg, meldung = anwendung.start_laufzeit_messung()

assert not erfolg and meldung, "Eine zweite Messung wurde angenommen."

with anwendung._laufzeit_lock:
    anwendung._laufzeit_stand["active"] = False

#
# Und nicht gegen eine laufende Wiedergabe: Die Messung ist selbst
# eine - zwei gleichzeitig kann das Interface nicht.
#
anwendung.practice_active = True
anwendung.music_player._playing = True

erfolg, meldung = anwendung.start_laufzeit_messung()

assert not erfolg and meldung, (
    "Die Messung startete gegen eine laufende Wiedergabe."
)

anwendung.practice_active = False
anwendung.music_player._playing = False

print("OK: Die Messung startet nicht gegen etwas Laufendes")


# ====================================================================
# 10. Streuende Läufe werden als solche gemeldet
#
# Drei gleiche Zahlen sind ein Befund, drei verschiedene eine Warnung.
# Ein fester Versatz gleicht nur aus, was auch fest ist - streut es,
# wäre die Zahl eine Scheingenauigkeit, und der Nutzer verschöbe
# seinen Mitschnitt nach einem Wert, den es gar nicht gibt.
#
# Geprüft an der Stelle, die das Urteil fällt: Mit der Attrappe eines
# Pults, das immer gleich verzögert, liesse sich Streuung gar nicht
# erzeugen.
# ====================================================================

anwendung._laufzeit_fertig(True, 40, "", [35, 40, 95])

stand = anwendung.laufzeit_status()

assert stand["spanne"] == 60, (
    f"Die Spanne von [35, 40, 95] ist {stand['spanne']} statt 60."
)

assert stand["unsicher"] is True, (
    "Läufe zwischen 35 und 95 ms gelten als verlässlich - das sind "
    "fast drei Perioden Unterschied, und ein fester Versatz gleicht "
    "so etwas nicht aus."
)

assert stand["werte"] == [35, 40, 95], stand["werte"]

#
# Und der Gegenfall: Eine Streuung innerhalb einer Periode (gut 21 ms
# bei 48 kHz) ist kein Widerspruch, sondern die Koernigkeit der
# Puffer.
#
anwendung._laufzeit_fertig(True, 72, "", [71, 72, 88])

stand = anwendung.laufzeit_status()

assert stand["spanne"] == 17 and stand["unsicher"] is False, stand

print("OK: Streuende Läufe werden gemeldet, dichte nicht")


# ====================================================================
# 11. Der mittlere Wert, nicht der kleinste und nicht der Durchschnitt
#
# Ein einzelner Ausreisser (ein Knacken auf der Leitung, ein
# verpasster Puffer) zöge den Durchschnitt mit sich; den mittleren
# Wert lässt er unberührt. Bei drei Läufen heisst das: Zwei müssen
# sich einig sein, der dritte darf danebenliegen.
# ====================================================================

for werte, erwartet, warum in (
    ([40, 40, 40], 40, "drei gleiche"),
    ([35, 40, 95], 40, "ein Ausreisser nach oben"),
    ([0, 40, 41], 40, "ein Ausreisser nach unten"),
    ([40], 40, "ein einzelner Wert"),
    ([], 0, "gar keiner"),
):
    assert mittlerer_wert(werte) == erwartet, (
        f"{warum}: {werte} ergibt {mittlerer_wert(werte)} statt "
        f"{erwartet}"
    )

#
# Der Unterschied zu den naheliegenden Alternativen - daran haengt,
# dass dieser Versuch ueberhaupt etwas zeigt.
#
assert mittlerer_wert([0, 40, 41]) != min([0, 40, 41])

assert mittlerer_wert([35, 40, 95]) != round(sum([35, 40, 95]) / 3)

print("OK: Genommen wird der mittlere Wert, nicht der kleinste")


os.chdir(altes_verzeichnis)

lauf_ordner.cleanup()

arbeit.cleanup()

print("Alle Tests der Laufzeitmessung erfolgreich.")
