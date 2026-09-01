#!/usr/bin/env python3
"""
Ein Mischpult, das es nicht gibt: XR18-Emulator zum Ausprobieren
ohne Hardware.

XRack spricht mit dem Pult über OSC/UDP und liest sein Audio über
USB. Beides braucht bisher ein echtes Gerät auf dem Tisch. Dieses
Programm stellt sich an dessen Stelle:

    1. Es antwortet auf Port 10024 wie ein XR18 - Fader,
       Stummschaltungen, Kanalnamen, Kopplungen, Snapshots.
    2. Mit --audio spielt es zusätzlich 18 Kanäle Testsignal in ein
       ALSA-Loopback, das XRack dann wie ein Interface aufnehmen
       kann.

Gestartet wird es von Hand, nicht als Dienst:

    python3 scripts/xair-emulator.py
    python3 scripts/xair-emulator.py --audio

Danach in XRack unter Einstellungen 127.0.0.1 als Pult-Adresse
eintragen (oder in der Kanalzug-Karte auf die Lupe drücken - der
Rundruf erreicht auch ein Programm auf demselben Rechner).

Warum eine eigene OSC-Kodierung und nicht die aus
core/console_control.py: Ein Emulator, der den Kodierer der Gegenseite
benutzt, kann dessen Fehler nicht finden - beide wären sich einig,
auch wenn beide falsch lägen. Genau so ein Fehler steckte dort schon
einmal (die Auffüllung bei Adressen mit Rest 3, siehe den Kommentar
bei pad()). Zwei unabhängige Implementierungen prüfen sich
gegenseitig. Nebenbei läuft dieses Programm damit auch auf einem
Rechner, auf dem XRack gar nicht installiert ist - Python allein
genügt.

Das Programm gehört NICHT zu XRack. Es ist Werkzeug daneben; müsste
XRack für den Emulator geändert werden, wäre er keiner.
"""

import argparse
import array
import math
import random
import socket
import struct
import sys
import threading
import time

# ------------------------------------------------------------------
# OSC
# ------------------------------------------------------------------
#
# Gebraucht wird nur ein kleiner Ausschnitt: Nachrichten mit Adresse,
# Typ-Tag und den Argumenttypen i (Ganzzahl), f (Fließkomma) und s
# (Zeichenkette). Keine Bündel, keine Blobs, keine Zeitstempel - die
# X-Serie kommt im Alltag ohne aus, und XRack schickt nichts anderes.
#


def auffuellen(daten: bytes) -> bytes:
    """
    Auf ein Vielfaches von 4 Byte bringen.

    Der Nullabschluss steckt bereits in `daten`. Passt die Länge damit
    schon ins Raster, kommt nichts mehr dazu - vier überzählige Nullen
    würden das Typ-Tag um vier Byte verschieben, und der Empfänger
    läse eine Nachricht ohne Argumente.
    """

    rest = len(daten) % 4

    if rest == 0:
        return daten

    return daten + b"\x00" * (4 - rest)


def osc_bauen(adresse: str, *argumente) -> bytes:
    """Eine OSC-Nachricht zusammensetzen."""

    nachricht = auffuellen(adresse.encode("ascii") + b"\x00")

    tags = ","
    werte = b""

    for argument in argumente:

        #
        # bool vor int: In Python ist bool eine Unterklasse von int.
        #
        if isinstance(argument, bool):
            tags += "i"
            werte += struct.pack(">i", 1 if argument else 0)

        elif isinstance(argument, int):
            tags += "i"
            werte += struct.pack(">i", argument)

        elif isinstance(argument, float):
            tags += "f"
            werte += struct.pack(">f", argument)

        elif isinstance(argument, str):
            tags += "s"
            werte += auffuellen(argument.encode("ascii") + b"\x00")

        else:
            raise TypeError(f"Kein OSC-Typ: {type(argument)}")

    return nachricht + auffuellen(tags.encode("ascii") + b"\x00") + werte


def osc_lesen(daten: bytes) -> tuple[str, list]:
    """
    Eine OSC-Nachricht zerlegen.

    Liefert Adresse und Argumente; bei einer Nachricht ohne Typ-Tag
    (so fragt XRack einen Wert ab) eine leere Liste.
    """

    def zeichenkette(stelle: int) -> tuple[str, int]:

        ende = daten.index(b"\x00", stelle)

        text = daten[stelle:ende].decode("ascii", errors="replace")

        #
        # Hinter dem Nullbyte weiter, dann aufs nächste Raster.
        #
        weiter = ende + 1

        return text, weiter + (-weiter % 4)

    adresse, stelle = zeichenkette(0)

    if stelle >= len(daten) or daten[stelle:stelle + 1] != b",":
        return adresse, []

    tags, stelle = zeichenkette(stelle)

    argumente = []

    for tag in tags[1:]:

        if tag == "i":
            argumente.append(struct.unpack_from(">i", daten, stelle)[0])
            stelle += 4

        elif tag == "f":
            argumente.append(struct.unpack_from(">f", daten, stelle)[0])
            stelle += 4

        elif tag == "s":
            text, stelle = zeichenkette(stelle)
            argumente.append(text)

        else:
            #
            # Unbekannter Typ: abbrechen statt raten - danach stimmt
            # die Leseposition ohnehin nicht mehr.
            #
            break

    return adresse, argumente


def wert_zu_db(wert: float) -> float:
    """
    Der Faderweg (0…1) in dB, wie ihn das Pult anzeigt.

    Nur für die Ausgabe im Terminal - damit dort steht, was am Pult
    stünde. Die Kennlinie der X-Serie ist stückweise linear: 0 dB
    liegen bei etwa drei Vierteln des Wegs, nicht in der Mitte.
    """

    if wert <= 0.0:
        return float("-inf")

    if wert >= 0.5:
        return wert * 40.0 - 30.0

    if wert >= 0.25:
        return wert * 80.0 - 50.0

    if wert >= 0.0625:
        return wert * 160.0 - 70.0

    return wert * 480.0 - 90.0


# ------------------------------------------------------------------
# Das Pult
# ------------------------------------------------------------------

PORT_XAIR = 10024
PORT_X32 = 10023

#
# Die Namen der Snapshot-Adressen unterscheiden sich zwischen den
# Familien - beim X-Air heißen sie Snapshots, beim X32 Szenen, und
# der X32 zählt ab 0.
#
SNAP_XAIR = {
    "laden": "/-snap/load",
    "index": "/-snap/index",
    "name": "/-snap/{:02d}/name",
    "anzahl": 64,
    "erster": 1,
}

SNAP_X32 = {
    "laden": "/-action/goscene",
    "index": "/-show/prepos/current",
    "name": "/-show/showfile/scene/{:03d}/name",
    "anzahl": 100,
    "erster": 0,
}

#
# Was auf den Kanälen liegt. Dieselbe Belegung benutzt das Testsignal
# (siehe signal_bauen) - so heißt der Kanal, auf dem die Snare zu
# hören ist, in der Kanalzug-Karte auch "Snare".
#
BELEGUNG = [
    "Kick", "Snare", "HiHat", "Bass", "Git L", "Git R", "Voc",
    "Kanal 8", "Kanal 9", "Kanal 10", "Kanal 11", "Kanal 12",
    "Kanal 13", "Kanal 14", "Kanal 15", "Kanal 16",
]

#
# Der Aux-Rückweg ist beim XR18 das Kanalpaar 17+18. Er trägt hier den
# Lichtmix - genau der Weg, für den es die Einzelkanal-Quelle der
# Lichtshow gibt.
#
NAME_AUX = "Licht-Mix"


class Pult:
    """
    Ein Mischpult der X-Serie, so weit XRack es anspricht.

    Auf eine Nachricht ohne Argumente antwortet es mit dem gemerkten
    Wert, auf eine mit Argument übernimmt es ihn. Das ist das ganze
    Protokoll.
    """

    def __init__(
        self,
        port: int = 0,
        adresse: str = "127.0.0.1",
        x32: bool = False,
        vorbelegt: bool = False,
        verzoegerung: float = 0.0,
        stumm: list[str] | None = None,
        melden=None,
    ):

        self.x32 = bool(x32)

        self.kanaele = 32 if self.x32 else 16
        self.summe = "/main/st" if self.x32 else "/lr"
        self.aux = None if self.x32 else "/rtn/aux"

        self.snap = SNAP_X32 if self.x32 else SNAP_XAIR

        #
        # Alles nach der vollen Adresse abgelegt ("/ch/01/mix/fader").
        # Was hier nicht steht, beantwortet das Pult mit seinem
        # Grundwert - ein echtes hat schließlich auch für jeden Kanal
        # eine Stellung.
        #
        self.faders: dict[str, float] = {}
        self.names: dict[str, str] = {}
        self.on: dict[str, int] = {}

        #
        # Kopplungen, Schlüssel wie "9-10" (nicht zweistellig).
        #
        self.chlink: dict[str, int] = {}

        #
        # Snapshots: Nummer -> Name, dazu die gespeicherten Stellungen.
        # Ein Platz ohne Namen ist unbenutzt.
        #
        self.snapshots: dict[int, str] = {}
        self.snapshot_werte: dict[int, dict[str, float | int]] = {}
        self.snapshot_index = 0

        #
        # Schalter, um widerspenstige Pulte nachzustellen. Jeder
        # entspricht einem Verhalten, das XRack abfangen muss.
        #
        self.answer_chlink = True
        self.answer_snapshot_names = True

        #
        # /config/linkcfg/fdrmute gibt es nur beim X32. Ein X-Air
        # schweigt dazu - und XRack muss dieses Schweigen als "die
        # Fader folgen der Kopplung" lesen.
        #
        self.fdrmute: int | None = 1 if self.x32 else None

        self.verzoegerung = float(verzoegerung)
        self.stumm = list(stumm or [])

        self.melden = melden

        #
        # Alles, was hereinkam - die Testreihe sieht hier nach, ob
        # XRack eine Abfrage wirklich unterlassen hat.
        #
        self.received: list[tuple[str, list]] = []

        if vorbelegt:
            self._vorbelegen()

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((adresse, port))
        self.port = self.socket.getsockname()[1]

        self._laeuft = True
        self._thread = threading.Thread(target=self._bedienen, daemon=True)
        self._thread.start()

    # --------------------------------------------------------------
    # Adressen
    # --------------------------------------------------------------

    def kanaladressen(self) -> list[str]:
        """Alle Kanalzüge in der Reihenfolge des Pults."""

        adressen = [f"/ch/{nummer:02d}" for nummer in range(1, self.kanaele + 1)]

        if self.aux:
            adressen.append(self.aux)

        adressen.append(self.summe)

        return adressen

    def _paar(self, adresse: str) -> tuple[str, int] | None:
        """
        Zu einem Kanal das Kopplungspaar und die eigene Nummer.

        Liefert None für alles, was kein nummerierter Kanal ist - der
        Aux-Rückweg und die Summe lassen sich nicht koppeln.
        """

        if not adresse.startswith("/ch/"):
            return None

        try:
            nummer = int(adresse[4:6])
        except ValueError:
            return None

        erster = nummer - 1 if nummer % 2 == 0 else nummer

        return f"{erster}-{erster + 1}", nummer

    def _fuehrend(self, adresse: str) -> str:
        """
        Bei einem gekoppelten Paar antwortet der zweite Kanal mit dem
        Wert des ersten.

        Das ist der Punkt, an dem eine Kopplung mehr ist als ein
        gemerktes Häkchen: XRack schickt bei einem gekoppelten Paar
        nur noch an den ungeraden Kanal und verlässt sich darauf, dass
        das Pult den anderen mitzieht.
        """

        teil = adresse.rsplit("/", 2)

        if len(teil) < 3:
            return adresse

        kanal = teil[0]
        endung = "/" + "/".join(teil[1:])

        paar = self._paar(kanal)

        if paar is None:
            return adresse

        schluessel, nummer = paar

        if nummer % 2 == 1 or self.chlink.get(schluessel) != 1:
            return adresse

        return f"/ch/{nummer - 1:02d}{endung}"

    # --------------------------------------------------------------
    # Vorbelegung
    # --------------------------------------------------------------

    def _vorbelegen(self) -> None:
        """
        Ein Pult, an dem schon jemand gearbeitet hat.

        Von selbst ändert sich davon nichts - alles, was sich danach
        bewegt, kommt von XRack. Nur so bleibt jeder Versuch
        wiederholbar.
        """

        for nummer in range(1, self.kanaele + 1):

            adresse = f"/ch/{nummer:02d}"

            if nummer <= len(BELEGUNG):
                self.names[f"{adresse}/config/name"] = BELEGUNG[nummer - 1]
            else:
                self.names[f"{adresse}/config/name"] = f"Kanal {nummer}"

            self.faders[f"{adresse}/mix/fader"] = 0.75
            self.on[f"{adresse}/mix/on"] = 1

        if self.aux:
            self.names[f"{self.aux}/config/name"] = NAME_AUX
            self.faders[f"{self.aux}/mix/fader"] = 0.75
            self.on[f"{self.aux}/mix/on"] = 1

        self.names[f"{self.summe}/config/name"] = "Main"
        self.faders[f"{self.summe}/mix/fader"] = 0.75
        self.on[f"{self.summe}/mix/on"] = 1

        #
        # Die Gitarre liegt als Stereopaar auf 5+6 und ist gekoppelt.
        #
        self.chlink["5-6"] = 1

        erster = self.snap["erster"]

        self.snapshots = {
            erster: "Soundcheck",
            erster + 1: "Set 1",
            erster + 2: "Zugabe",
        }

        #
        # Was in den Plätzen steht: dieselben Kanäle, andere
        # Stellungen. Beim Aufrufen springen die Fader - so sieht man,
        # dass wirklich etwas passiert ist.
        #
        self.snapshot_werte = {
            erster: {
                f"/ch/{nummer:02d}/mix/fader": 0.75
                for nummer in range(1, self.kanaele + 1)
            },
            erster + 1: {
                f"/ch/{nummer:02d}/mix/fader": 0.55 + 0.02 * nummer
                for nummer in range(1, self.kanaele + 1)
            },
            erster + 2: {
                f"/ch/{nummer:02d}/mix/fader": 0.85
                for nummer in range(1, self.kanaele + 1)
            },
        }

        self.snapshot_index = erster

    # --------------------------------------------------------------
    # Bedienung
    # --------------------------------------------------------------

    def _bedienen(self) -> None:
        """Nimmt Nachrichten an, bis stop() gerufen wird."""

        #
        # Kurzer Zeitablauf, damit der Faden das Ende schnell merkt.
        #
        self.socket.settimeout(0.1)

        while self._laeuft:

            try:
                daten, absender = self.socket.recvfrom(4096)
            except (socket.timeout, OSError):
                continue

            try:
                adresse, argumente = osc_lesen(daten)
            except (ValueError, struct.error):
                #
                # Kein OSC - ein echtes Pult schweigt dazu.
                #
                continue

            self.received.append((adresse, argumente))

            if any(muster in adresse for muster in self.stumm):
                continue

            if self.verzoegerung:
                time.sleep(self.verzoegerung)

            antwort = self._behandeln(adresse, argumente)

            if antwort is not None:
                #
                # Immer an den Absender: XRack öffnet für jede Anfrage
                # ein neues Socket, eine feste Rückadresse gäbe es
                # also gar nicht.
                #
                self.socket.sendto(antwort, absender)

    def _behandeln(self, adresse: str, argumente: list) -> bytes | None:
        """Eine Nachricht beantworten - oder schweigen."""

        if argumente:
            self._setzen(adresse, argumente[0])
            return None

        return self._abfragen(adresse)

    def _setzen(self, adresse: str, wert) -> None:
        """Einen Wert übernehmen."""

        if adresse.endswith("/mix/fader"):

            self.faders[adresse] = float(wert)

            self._sagen(
                f"{adresse} = {float(wert):.3f}  "
                f"({wert_zu_db(float(wert)):+.1f} dB)"
            )

        elif adresse.endswith("/mix/on"):

            self.on[adresse] = int(wert)

            self._sagen(
                f"{adresse} = {int(wert)}  "
                f"({'an' if int(wert) else 'stumm'})"
            )

        elif adresse.endswith("/config/name"):

            self.names[adresse] = str(wert)
            self._sagen(f"{adresse} = {wert!r}")

        elif adresse.startswith("/config/chlink/"):

            paar = adresse[len("/config/chlink/"):]

            self.chlink[paar] = int(wert)

            self._sagen(
                f"Kopplung {paar}: "
                f"{'gekoppelt' if int(wert) else 'getrennt'}"
            )

        elif adresse == self.snap["laden"]:

            self.snapshot_laden(int(wert))

        else:
            self._sagen(f"{adresse} = {wert!r} (unbekannt, gemerkt wird nichts)")

    def _abfragen(self, adresse: str) -> bytes | None:
        """Den gemerkten Wert liefern."""

        if adresse in ("/info", "/xinfo"):
            #
            # Vier Zeichenketten wie ein echtes Pult: Serverfassung,
            # Name im Netz, Modell, Firmware. XRack liest davon nichts
            # - es genügt ihm, dass ueberhaupt etwas kommt -, aber
            # andere Programme (X-AIR-Edit) schauen hinein.
            #
            return osc_bauen(
                adresse,
                "V2.07",
                "XRack-Testpult",
                "XR18" if not self.x32 else "X32",
                "1.17",
            )

        if adresse == "/status":
            return osc_bauen(adresse, "active", "127.0.0.1", "XRack-Testpult")

        if adresse.endswith("/mix/fader"):
            quelle = self._fuehrend(adresse)
            return osc_bauen(adresse, self.faders.get(quelle, 0.75))

        if adresse.endswith("/mix/on"):
            quelle = self._fuehrend(adresse)
            return osc_bauen(adresse, self.on.get(quelle, 1))

        if adresse.endswith("/config/name"):
            return osc_bauen(adresse, self.names.get(adresse, ""))

        if adresse.startswith("/config/chlink/"):

            if not self.answer_chlink:
                return None

            paar = adresse[len("/config/chlink/"):]

            return osc_bauen(adresse, self.chlink.get(paar, 0))

        if adresse == "/config/linkcfg/fdrmute":

            if self.fdrmute is None:
                return None

            return osc_bauen(adresse, int(self.fdrmute))

        if adresse == self.snap["index"]:
            return osc_bauen(adresse, int(self.snapshot_index))

        nummer = self._snapshot_nummer(adresse)

        if nummer is not None:

            if not self.answer_snapshot_names:
                return None

            return osc_bauen(adresse, self.snapshots.get(nummer, ""))

        return None

    def _snapshot_nummer(self, adresse: str) -> int | None:
        """
        Die Platznummer aus einer Namensadresse - oder None, wenn die
        Adresse keine ist.
        """

        muster = self.snap["name"]

        vorn, hinten = muster.split("{", 1)
        hinten = hinten.split("}", 1)[1]

        if not adresse.startswith(vorn) or not adresse.endswith(hinten):
            return None

        mitte = adresse[len(vorn):len(adresse) - len(hinten)]

        try:
            return int(mitte)
        except ValueError:
            return None

    def snapshot_laden(self, nummer: int) -> None:
        """
        Einen gespeicherten Platz aufrufen.

        Der eingreifendste Befehl, den XRack ans Pult schickt - und
        deshalb der, bei dem man sehen soll, dass er ankommt: Der
        Index wandert mit, und die Fader springen auf den
        gespeicherten Stand.
        """

        self.snapshot_index = int(nummer)

        werte = self.snapshot_werte.get(int(nummer))

        if not werte:
            self._sagen(f"Snapshot {nummer} aufgerufen (leerer Platz)")
            return

        for adresse, wert in werte.items():

            if adresse.endswith("/mix/on"):
                self.on[adresse] = int(wert)
            else:
                self.faders[adresse] = float(wert)

        self._sagen(
            f"Snapshot {nummer} aufgerufen "
            f"({self.snapshots.get(int(nummer)) or 'ohne Namen'}) - "
            f"{len(werte)} Werte gesetzt"
        )

    def _sagen(self, text: str) -> None:

        if self.melden is not None:
            self.melden(text)

    def stop(self) -> None:

        self._laeuft = False
        self._thread.join(timeout=1.0)
        self.socket.close()


# ------------------------------------------------------------------
# Das Interface: 18 Kanäle Testsignal
# ------------------------------------------------------------------
#
# XRack findet seine Geräte über "arecord -l" und öffnet hw:Karte,Gerät
# - ein Interface muss also eine echte Soundkarte sein. Die liefert
# das Kernelmodul snd-aloop: Was hier hineingespielt wird, kommt auf
# der anderen Seite als Aufnahme heraus.
#
# Die Werte werden so geschrieben, wie XRack sie liest: 2^31 ist
# Vollausschlag (siehe recorder/level_meter.py und
# lighting/analysis.py). Der Umweg über das Loopback kopiert die Bytes
# nur, also kommt genau das an, was hier steht.
#

VOLLAUSSCHLAG = 2.0 ** 31

#
# Ein Takt bei 120 Schlägen je Minute - zwei Sekunden. Einmal
# gerechnet, dann in einer Schleife geschrieben.
#
BPM = 120.0
SCHLAEGE = 4


def signal_bauen(kanaele: int = 18, rate: int = 48000,
                 bpm: float = BPM) -> bytes:
    """
    Einen Takt Testsignal bauen, verschachtelt wie ALSA es liefert.

    Die Belegung entspricht den Kanalnamen des Pults (siehe BELEGUNG):
    Auf Kanal 2 liegt die Snare, und in der Kanalzug-Karte steht an
    Kanal 2 "Snare". Die Kanäle 8 bis 16 tragen je so viele kurze
    Pieptöne, wie ihre Nummer sagt - damit sich in einer Aufnahme
    nachsehen lässt, ob jede Spur da gelandet ist, wo sie hingehört.

    Das Paar 17+18 trägt den Lichtmix: Bassdrum und Snare vorn, keine
    Stimme. Genau dafür gibt es die Einzelkanal-Quelle der Lichtshow.
    """

    schlag = 60.0 / bpm
    rahmen = int(round(rate * schlag * SCHLAEGE))

    #
    # Ein eigener Zufall mit fester Saat: Zwei Aufrufe liefern
    # denselben Block. Ein Testsignal, das sich bei jedem Lauf
    # aendert, waere als Prueffeld wertlos.
    #
    wuerfel = random.Random(1809)

    rausch = [wuerfel.uniform(-1.0, 1.0) for _ in range(rahmen)]

    def leer() -> list[float]:
        return [0.0] * rahmen

    def anschlag(spur: list[float], start: int, dauer: float,
                 stimme, staerke: float) -> None:
        """Einen Schlag mit abfallender Hüllkurve einzeichnen."""

        laenge = min(int(dauer * rate), rahmen - start)

        for i in range(max(0, laenge)):

            huelle = math.exp(-5.0 * i / (dauer * rate))

            spur[start + i] += staerke * huelle * stimme(start + i, i)

    kick = leer()
    snare = leer()
    hihat = leer()
    bass = leer()
    git_l = leer()
    git_r = leer()
    voc = leer()

    for schlag_nr in range(SCHLAEGE):

        start = int(schlag_nr * schlag * rate)

        #
        # Bassdrum auf jeder Viertel: tiefer Sinus, der beim Anschlag
        # kurz nach oben zieht.
        #
        anschlag(
            kick, start, 0.25,
            lambda _, i: math.sin(
                2.0 * math.pi * (55.0 + 60.0 * math.exp(-40.0 * i / rate))
                * i / rate
            ),
            0.9,
        )

        #
        # Snare auf 2 und 4: Rauschen mit etwas Körper. Das ist der
        # Schlag, auf den die Lichtshow blitzt.
        #
        if schlag_nr % 2 == 1:

            anschlag(
                snare, start, 0.18,
                lambda n, i: 0.7 * rausch[n % rahmen]
                + 0.3 * math.sin(2.0 * math.pi * 190.0 * i / rate),
                0.85,
            )

        #
        # HiHat auf jeder Achtel: kurzes, helles Rauschen. Die
        # Differenz benachbarter Zufallswerte hebt die Höhen an - eine
        # Hochpass-Andeutung, die genügt.
        #
        for achtel in (0, 1):

            anschlag(
                hihat, start + int(achtel * schlag * rate / 2), 0.05,
                lambda n, i: rausch[n % rahmen] - rausch[(n - 1) % rahmen],
                0.25,
            )

        #
        # Bass: je Schlag ein Ton, gehalten.
        #
        grundton = (55.0, 73.42, 65.41, 82.41)[schlag_nr % 4]

        anschlag(
            bass, start, schlag,
            lambda _, i, f=grundton: math.sin(2.0 * math.pi * f * i / rate),
            0.5,
        )

    #
    # Gitarre: ein liegender Akkord, links und rechts leicht
    # verstimmt, damit sich die beiden Kanäle unterscheiden lassen.
    #
    for i in range(rahmen):

        zeit = i / rate

        git_l[i] = 0.22 * (
            math.sin(2.0 * math.pi * 220.0 * zeit)
            + math.sin(2.0 * math.pi * 277.2 * zeit)
            + math.sin(2.0 * math.pi * 329.6 * zeit)
        ) / 3.0

        git_r[i] = 0.22 * (
            math.sin(2.0 * math.pi * 220.7 * zeit)
            + math.sin(2.0 * math.pi * 277.9 * zeit)
            + math.sin(2.0 * math.pi * 330.4 * zeit)
        ) / 3.0

        #
        # Gesang: Mitten mit Vibrato - laut genug, um in einem Mix
        # zu stören, und genau deshalb im Lichtmix nicht dabei.
        #
        voc[i] = 0.35 * math.sin(
            2.0 * math.pi * (440.0 + 25.0 * math.sin(2.0 * math.pi * 5.0 * zeit))
            * zeit
        ) * (0.5 + 0.5 * math.sin(2.0 * math.pi * 0.5 * zeit))

    #
    # Der Lichtmix: Schlagzeug vorn, keine Stimme.
    #
    #
    # Der Faktor haelt die Summe unter dem Vollausschlag: Vier
    # Zutaten, die einzeln fast bis oben gehen, uebersteuern sonst -
    # und ein uebersteuerter Lichtmix macht aus jedem Schlag
    # denselben.
    #
    licht = [
        0.55 * (kick[i] + snare[i] + 0.3 * hihat[i] + 0.2 * bass[i])
        for i in range(rahmen)
    ]

    spuren: dict[int, list[float]] = {
        1: kick, 2: snare, 3: hihat, 4: bass,
        5: git_l, 6: git_r, 7: voc,
    }

    #
    # Kanal 8 bis 16: so viele Pieptöne wie die Kanalnummer.
    #
    for nummer in range(8, 17):

        spur = leer()

        for piep in range(nummer):

            start = int(piep * 0.1 * rate)

            anschlag(
                spur, start, 0.06,
                lambda _, i: math.sin(2.0 * math.pi * 1000.0 * i / rate),
                0.5,
            )

        spuren[nummer] = spur

    spuren[17] = licht
    spuren[18] = list(licht)

    #
    # Verschachteln. Die Zuweisung auf eine Schrittweite kopiert der
    # Interpreter in einem Rutsch - eine Schleife über 1,7 Millionen
    # Werte wäre auf einem Pi spürbar langsam.
    #
    block = array.array("i", bytes(4 * rahmen * kanaele))

    for nummer, spur in spuren.items():

        if nummer > kanaele:
            continue

        block[nummer - 1::kanaele] = array.array("i", [
            max(-2147483647, min(2147483647, int(wert * VOLLAUSSCHLAG * 0.9)))
            for wert in spur
        ])

    return block.tobytes()


KARTENLISTE = "/proc/asound/cards"


def loopback_geraet(quelle: str = KARTENLISTE) -> str | None:
    """
    Die Wiedergabeseite des ALSA-Loopbacks suchen.

    Zurück kommt der ALSA-Name (etwa "hw:2,0") oder None, wenn das
    Modul nicht geladen ist. Die Nummer wird gelesen und nicht
    geraten: Wo das Loopback landet, hängt davon ab, was sonst noch
    steckt.
    """

    try:
        with open(quelle, encoding="utf-8") as datei:
            zeilen = datei.read().splitlines()
    except OSError:
        return None

    for zeile in zeilen:

        if "Loopback" not in zeile:
            continue

        teil = zeile.strip().split()

        if not teil or not teil[0].isdigit():
            continue

        return f"hw:{int(teil[0])},0"

    return None


def audio_starten(kanaele: int, rate: int, geraet: str | None,
                  melden) -> threading.Thread | None:
    """
    Das Testsignal in das Loopback spielen.

    Das Modul selbst wird nicht geladen - das braucht Rechte, die ein
    Testwerkzeug nicht bekommen soll. Fehlt es, sagt das Programm,
    was zu tun ist.
    """

    if geraet is None:
        geraet = loopback_geraet()

    if geraet is None:

        melden(
            "Kein ALSA-Loopback gefunden. Einmalig laden mit:\n"
            "    sudo modprobe snd-aloop\n"
            "Dauerhaft: 'snd-aloop' in /etc/modules eintragen."
        )

        return None

    try:
        import alsaaudio
    except ImportError:

        melden(
            "Das Modul pyalsaaudio fehlt - ohne das gibt es kein Audio.\n"
            "    pip install pyalsaaudio   (in XRacks .venv ist es schon drin)"
        )

        return None

    melden(f"Testsignal wird gerechnet ({kanaele} Kanäle, {rate} Hz) ...")

    block = signal_bauen(kanaele=kanaele, rate=rate)

    try:

        pcm = alsaaudio.PCM(
            type=alsaaudio.PCM_PLAYBACK,
            mode=alsaaudio.PCM_NORMAL,
            device=geraet,
        )

        pcm.setchannels(kanaele)
        pcm.setrate(rate)
        pcm.setformat(alsaaudio.PCM_FORMAT_S24_LE)
        pcm.setperiodsize(1024)

    except Exception as fehler:

        melden(
            f"Das Loopback ({geraet}) ließ sich nicht öffnen: {fehler}\n"
            "Nimmt der Kernel weniger Kanäle an, hilft --kanaele."
        )

        return None

    #
    # Die Aufnahmeseite ist die Karte daneben: Was nach hw:X,0 geht,
    # kommt aus hw:X,1 heraus. Genau das ist in XRack zu wählen.
    #
    karte = geraet.split(":", 1)[1].split(",", 1)[0]

    melden(
        f"Audio läuft. In XRack das Gerät \"hw:{karte},1\" (Loopback, "
        f"Gerät 1) wählen - {kanaele} Kanäle, {rate} Hz."
    )

    haeppchen = 1024 * kanaele * 4

    def schleife():

        while True:

            for stelle in range(0, len(block), haeppchen):

                try:
                    pcm.write(block[stelle:stelle + haeppchen])
                except Exception:
                    return

    faden = threading.Thread(target=schleife, daemon=True)
    faden.start()

    return faden


# ------------------------------------------------------------------
# Programm
# ------------------------------------------------------------------


def main() -> int:

    zerleger = argparse.ArgumentParser(
        description=(
            "Stellt ein Behringer XR18 nach, damit sich XRack ohne "
            "Hardware ausprobieren lässt."
        ),
    )

    zerleger.add_argument(
        "--port", type=int, default=None,
        help="UDP-Port (Vorgabe: 10024, mit --x32 10023)",
    )
    zerleger.add_argument(
        "--adresse", default="0.0.0.0",
        help="Adresse, auf der gelauscht wird (Vorgabe: alle)",
    )
    zerleger.add_argument(
        "--x32", action="store_true",
        help="Als X32 antworten statt als X-Air",
    )
    zerleger.add_argument(
        "--ohne-chlink", action="store_true",
        help="Kopplungsabfragen unbeantwortet lassen",
    )
    zerleger.add_argument(
        "--ohne-snapshot-namen", action="store_true",
        help="Namen der Snapshots nicht liefern",
    )
    zerleger.add_argument(
        "--verzoegerung", type=float, default=0.0,
        help="Antwortzeit in Millisekunden (Vorgabe: sofort)",
    )
    zerleger.add_argument(
        "--stumm", action="append", default=[],
        help="Adressen, die dieses Muster enthalten, unbeantwortet lassen",
    )
    zerleger.add_argument(
        "--ausfuehrlich", action="store_true",
        help="Auch Abfragen anzeigen, nicht nur Änderungen",
    )
    zerleger.add_argument(
        "--audio", action="store_true",
        help="Zusätzlich Testsignal in das ALSA-Loopback spielen",
    )
    zerleger.add_argument(
        "--audio-geraet", default=None,
        help="Wiedergabeseite des Loopbacks (Vorgabe: selbst suchen)",
    )
    zerleger.add_argument(
        "--kanaele", type=int, default=18,
        help="Kanäle des Testsignals (Vorgabe: 18)",
    )
    zerleger.add_argument(
        "--rate", type=int, default=48000,
        help="Abtastrate des Testsignals (Vorgabe: 48000)",
    )

    argumente = zerleger.parse_args()

    port = argumente.port

    if port is None:
        port = PORT_X32 if argumente.x32 else PORT_XAIR

    def melden(text: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {text}", flush=True)

    try:

        pult = Pult(
            port=port,
            adresse=argumente.adresse,
            x32=argumente.x32,
            vorbelegt=True,
            verzoegerung=argumente.verzoegerung / 1000.0,
            stumm=argumente.stumm,
            melden=melden,
        )

    except OSError as fehler:

        print(
            f"Port {port} lässt sich nicht belegen: {fehler}\n"
            "Läuft der Emulator schon? Oder ein echtes Pult im selben "
            "Netz - dann hilft --port.",
            file=sys.stderr,
        )

        return 1

    pult.answer_chlink = not argumente.ohne_chlink
    pult.answer_snapshot_names = not argumente.ohne_snapshot_namen

    if argumente.ausfuehrlich:

        #
        # Ausführlich heißt wirklich alles - die Kanalzug-Karte fragt
        # jede Sekunde über sechzig Mal ab, das wird schnell viel.
        #
        urspruenglich = pult._abfragen

        def mitschreiben(adresse):

            antwort = urspruenglich(adresse)

            melden(
                f"? {adresse}"
                + ("" if antwort is not None else "   (keine Antwort)")
            )

            return antwort

        pult._abfragen = mitschreiben

    print(
        "\n"
        f"  {'X32' if argumente.x32 else 'XR18'}-Emulator läuft auf Port {port}.\n"
        f"  {pult.kanaele} Kanäle"
        + (", Aux-Rückweg" if pult.aux else "")
        + f" und Summe, {len(pult.snapshots)} Snapshots.\n"
        "\n"
        "  In XRack unter Einstellungen als Pult-Adresse 127.0.0.1\n"
        "  eintragen - oder in der Kanalzug-Karte die Lupe drücken.\n"
        "\n"
        "  Was XRack ändert, steht hier. Beenden mit Strg-C.\n",
        flush=True,
    )

    if argumente.audio:

        audio_starten(
            kanaele=argumente.kanaele,
            rate=argumente.rate,
            geraet=argumente.audio_geraet,
            melden=melden,
        )

    try:

        while True:
            time.sleep(3600)

    except KeyboardInterrupt:
        print("\nEmulator beendet.")

    finally:
        pult.stop()

    return 0


if __name__ == "__main__":
    sys.exit(main())
