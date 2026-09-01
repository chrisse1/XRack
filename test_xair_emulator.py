#!/usr/bin/env python3
"""
Prüft den XR18-Emulator (scripts/xair-emulator.py).

Der Emulator steht an der Stelle, an der sonst ein Mischpult steht.
Damit das etwas wert ist, muss er zwei Prüfungen bestehen:

    1. Er verhält sich wie ein Pult. Den Beweis führt vor allem
       test_console_control.py - die vollständige Testreihe für den
       Pultverkehr läuft gegen dieses Programm.
    2. Er ist ein Programm, nicht nur eine Klasse. Was sich nur
       importieren lässt, hilft niemandem im Terminal.

Dazu kommt hier eine Prüfung, die es vorher gar nicht geben konnte:
XRack und der Emulator kodieren OSC getrennt voneinander. Jeder
dekodiert, was der andere gebaut hat - so fällt ein Fehler auf, den
eine gemeinsame Kodierung auf beiden Seiten gleich falsch machen
würde.

Und das Testsignal wird gerechnet und nachgemessen, ohne dass dafür
eine Soundkarte nötig wäre.
"""

import importlib.util
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent

SKRIPT = WURZEL / "scripts" / "xair-emulator.py"

#
# Der Emulator heißt mit Bindestrich, wie alle Skripte in scripts/ -
# importieren lässt sich das nur über den Umweg, den auch
# test_updater.py geht.
#
spezifikation = importlib.util.spec_from_file_location(
    "xair_emulator", SKRIPT
)

emulator = importlib.util.module_from_spec(spezifikation)
spezifikation.loader.exec_module(emulator)

from core.console_control import (  # noqa: E402
    CHANNELS_X32,
    CHANNELS_XAIR,
    FAMILY_X32,
    FAMILY_XAIR,
    SNAPSHOT_NAME_PROBES,
    ConsoleControl,
    decode,
    encode,
)

from lighting.analysis import Bandanalyse  # noqa: E402
from recorder.level_meter import LevelMeter  # noqa: E402


def steuerung(pult) -> ConsoleControl:
    """
    Ein ConsoleControl, das auf den Emulator zeigt.

    Die Erkennung wird dabei übersprungen (der Emulator lauscht im
    Test auf einem zufälligen Port); alles danach läuft echt.
    """

    control = ConsoleControl()

    control._family = FAMILY_X32 if pult.x32 else FAMILY_XAIR
    control._port = pult.port
    control._detected_for = "127.0.0.1"

    return control


# ====================================================================
# 1. Die beiden Kodierer über Kreuz
#
# Bisher prüfte XRacks Kodierer nur der eigene Dekodierer. Ein Fehler,
# den beide teilen, wäre dabei unsichtbar geblieben - genau so einer
# steckte einmal in der Auffüllung (Adressen mit 19, 23, 27 Zeichen).
# Zwei getrennte Implementierungen sind die Gegenprobe, die dort
# gefehlt hat.
# ====================================================================

for laenge in range(1, 41):

    adresse = "/" + "a" * (laenge - 1)

    #
    # XRack baut, der Emulator liest.
    #
    zurueck, argumente = emulator.osc_lesen(encode(adresse, 0.5))

    assert zurueck == adresse, (laenge, zurueck)
    assert len(argumente) == 1, (
        f"Der Emulator findet bei {laenge} Zeichen kein Argument "
        f"(Rest {laenge % 4} beim Teilen durch 4)."
    )
    assert abs(argumente[0] - 0.5) < 1e-6, argumente

    #
    # Und andersherum.
    #
    zurueck, argumente = decode(emulator.osc_bauen(adresse, 0.5))

    assert zurueck == adresse, (laenge, zurueck)
    assert len(argumente) == 1, (
        f"XRack findet bei {laenge} Zeichen kein Argument."
    )

print("OK: Beide Kodierer lesen einander bei jeder Adresslänge")

#
# Alle drei Typen, auch gemischt - so wie die /info-Antwort aussieht.
#
for werte in (
    (7,),
    (-3,),
    (0.25,),
    ("Kick",),
    ("V2.07", "XRack-Testpult", "XR18", "1.17"),
):

    adresse, zurueck = emulator.osc_lesen(encode("/probe", *werte))

    assert adresse == "/probe", adresse
    assert len(zurueck) == len(werte), (werte, zurueck)

    for erwartet, gelesen in zip(werte, zurueck):

        if isinstance(erwartet, float):
            assert abs(gelesen - erwartet) < 1e-6, (erwartet, gelesen)
        else:
            assert gelesen == erwartet, (erwartet, gelesen)

    adresse, zurueck = decode(emulator.osc_bauen("/probe", *werte))

    assert len(zurueck) == len(werte), (werte, zurueck)

print("OK: Ganzzahl, Fließkomma und Zeichenkette gehen in beide Richtungen")

#
# Byteweise gleich: Zwei Kodierer, die dasselbe meinen, müssen
# dasselbe schreiben. Das ist die schärfste Form der Gegenprobe -
# sie fällt schon bei einem einzigen Füllbyte zu viel.
#
for probe in (
    ("/ch/01/mix/fader", (0.75,)),
    ("/ch/16/config/name", ("Kanal 16",)),
    ("/config/chlink/9-10", (1,)),
    ("/-snap/03/name", ()),
    ("/abc", ()),
):

    assert encode(probe[0], *probe[1]) == emulator.osc_bauen(
        probe[0], *probe[1]
    ), f"Die beiden Kodierer schreiben {probe[0]} verschieden."

print("OK: Beide schreiben dieselben Bytes")


# ====================================================================
# 2. Ein voller Durchlauf mit echtem ConsoleControl
# ====================================================================

pult = emulator.Pult(vorbelegt=True)

try:

    control = steuerung(pult)

    zuege = control.get_channels("127.0.0.1", CHANNELS_XAIR)

    assert zuege is not None, "Der Emulator hat nicht geantwortet."

    beschriftung = [zug["label"] for zug in zuege]
    namen = [zug["name"] for zug in zuege]

    #
    # Die Gitarre liegt vorbelegt als gekoppeltes Paar auf 5+6 - aus
    # 18 Kanälen werden dadurch 17 Züge.
    #
    assert "5+6" in beschriftung, beschriftung
    assert "17+18" in beschriftung, beschriftung
    assert beschriftung[-1] == "Main", beschriftung

    assert namen[0] == "Kick" and namen[1] == "Snare", namen
    assert "Licht-Mix" in namen, namen

    print("OK: Die Kanalzüge kommen mit Namen und dem gekoppelten Paar")

    #
    # Setzen und zurücklesen - über die Kennlinie hin und zurück.
    #
    assert control.set_fader("127.0.0.1", CHANNELS_XAIR, 3, -6.0) is True

    time.sleep(0.1)

    assert abs(pult.faders["/ch/03/mix/fader"] - 0.6) < 1e-6, (
        pult.faders["/ch/03/mix/fader"]
    )

    zuege = control.get_channels("127.0.0.1", CHANNELS_XAIR)

    assert abs(zuege[2]["db"] - (-6.0)) < 0.01, zuege[2]

    assert control.set_mute("127.0.0.1", CHANNELS_XAIR, 3, True) is True

    time.sleep(0.1)

    assert pult.on["/ch/03/mix/on"] == 0, pult.on

    assert control.get_channels("127.0.0.1", CHANNELS_XAIR)[2]["muted"] is True

    print("OK: Pegel und Stummschaltung gehen hin und kommen zurück")

    # ----------------------------------------------------------------
    # Die Kopplung wirkt wirklich
    #
    # Das ist der Unterschied zu einer Attrappe, die das Häkchen nur
    # merkt: XRack schickt bei einem gekoppelten Paar NUR noch an den
    # ungeraden Kanal (pair_addresses) und verlässt sich darauf, dass
    # das Pult den anderen mitzieht. Zieht es nicht mit, fällt das
    # niemandem auf - bis am echten Pult die halbe Musik stehen
    # bleibt.
    # ----------------------------------------------------------------

    assert control.set_link("127.0.0.1", CHANNELS_XAIR, 9, True) is True

    time.sleep(0.1)

    assert pult.chlink.get("9-10") == 1, pult.chlink

    eigener = pult.faders["/ch/10/mix/fader"]

    assert abs(eigener - 0.5) > 1e-6, (
        "Der Versuch taugt nur, wenn der zweite Kanal vorher woanders "
        "steht."
    )

    assert control.set_pair_fader(
        "127.0.0.1", CHANNELS_XAIR, 9, -10.0
    ) is True

    time.sleep(0.1)

    #
    # Geschickt wurde nur an den ersten Kanal - der zweite steht
    # unverändert da, wo er stand.
    #
    assert abs(pult.faders["/ch/09/mix/fader"] - 0.5) < 1e-6, pult.faders
    assert pult.faders["/ch/10/mix/fader"] == eigener, (
        "Der zweite Kanal wurde einzeln angesprochen."
    )

    def gelesen(adresse: str) -> float:
        """Was das Pult auf eine Abfrage dieser Adresse antwortet."""

        antwort = control._request("127.0.0.1", pult.port, encode(adresse))

        assert antwort is not None, f"{adresse} antwortet gar nicht."

        return decode(antwort)[1][0]

    #
    # ... gelesen wird am zweiten trotzdem der Wert des ersten.
    #
    assert abs(gelesen("/ch/10/mix/fader") - 0.5) < 1e-6, (
        f"Der gekoppelte Partner folgt nicht: "
        f"{gelesen('/ch/10/mix/fader')} statt 0.5"
    )

    #
    # Entkoppelt steht er wieder für sich.
    #
    assert control.set_link("127.0.0.1", CHANNELS_XAIR, 9, False) is True

    time.sleep(0.1)

    assert abs(gelesen("/ch/10/mix/fader") - eigener) < 1e-6, (
        "Auch ohne Kopplung folgt der zweite Kanal noch."
    )

    print("OK: Ein gekoppeltes Paar zieht den zweiten Kanal wirklich mit")

    # ----------------------------------------------------------------
    # Snapshots: Namen lesen, Platz aufrufen
    # ----------------------------------------------------------------

    snapshots = control.get_snapshots("127.0.0.1")

    benannt = [eintrag for eintrag in snapshots if eintrag["name"]]

    assert [eintrag["name"] for eintrag in benannt] == [
        "Soundcheck", "Set 1", "Zugabe",
    ], benannt

    assert [eintrag for eintrag in snapshots if eintrag["current"]][0][
        "index"
    ] == 1, snapshots[:3]

    vorher = pult.faders["/ch/01/mix/fader"]

    assert control.load_snapshot("127.0.0.1", 3) is True

    time.sleep(0.15)

    assert pult.snapshot_index == 3, pult.snapshot_index
    assert pult.faders["/ch/01/mix/fader"] != vorher, (
        "Der aufgerufene Snapshot hat die Fader nicht bewegt."
    )

    print("OK: Snapshots werden gelesen, und das Aufrufen bewegt die Fader")

finally:
    pult.stop()


# ====================================================================
# 3. Die Störfälle
#
# Beides sind Zustände, die XRack abfangen muss, weil sie am echten
# Gerät vorkommen: ein Pult, das die Kopplungsabfrage nicht kennt,
# und eines, das keine Snapshot-Namen liefert. Ohne Bremse liefe
# XRack in jeden einzelnen Zeitablauf.
# ====================================================================

pult = emulator.Pult()

try:

    pult.answer_chlink = False

    control = steuerung(pult)

    pult.received.clear()

    control.get_channels("127.0.0.1", CHANNELS_XAIR)

    versuche = [
        adresse for adresse, _ in pult.received
        if adresse.startswith("/config/chlink/")
    ]

    assert len(versuche) == 1, (
        f"Beim ersten Schweigen muss genau einmal gefragt werden, "
        f"gefragt wurde {len(versuche)}-mal."
    )

    pult.received.clear()

    control.get_channels("127.0.0.1", CHANNELS_XAIR)

    assert not [
        adresse for adresse, _ in pult.received
        if adresse.startswith("/config/chlink/")
    ], "Danach darf gar nicht mehr gefragt werden."

    print("OK: Ein Pult ohne Kopplungsabfrage wird genau einmal gefragt")

finally:
    pult.stop()


pult = emulator.Pult()

try:

    pult.answer_snapshot_names = False

    control = steuerung(pult)

    pult.received.clear()

    snapshots = control.get_snapshots("127.0.0.1")

    versuche = [
        adresse for adresse, _ in pult.received
        if adresse.endswith("/name")
    ]

    assert len(versuche) <= SNAPSHOT_NAME_PROBES, (
        f"Ohne Namen darf höchstens {SNAPSHOT_NAME_PROBES}-mal gefragt "
        f"werden, gefragt wurde {len(versuche)}-mal."
    )

    assert len(snapshots) == 64, len(snapshots)

    print("OK: Ohne Snapshot-Namen wird das Auslesen früh aufgegeben")

finally:
    pult.stop()


# ====================================================================
# 4. Der X32-Modus
#
# Diese Zweige hat bisher NICHTS geprüft - es gibt kein X32 zum
# Nachsehen. Der Emulator ist die einzige Gelegenheit, sie überhaupt
# einmal laufen zu lassen.
# ====================================================================

pult = emulator.Pult(x32=True, vorbelegt=True)

try:

    control = steuerung(pult)

    zuege = control.get_channels("127.0.0.1", CHANNELS_X32)

    #
    # 32 Kanäle und die Summe, davon 5+6 zu einem Regler gekoppelt:
    # 32 Züge.
    #
    assert len(zuege) == 32, (
        f"Erwartet 32 Regler (31 Kanalzüge plus Summe): {len(zuege)}"
    )
    assert zuege[-1]["label"] == "Main", zuege[-1]

    #
    # Die Summe liegt beim X32 woanders - genau das ist der Punkt.
    #
    assert control.set_fader(
        "127.0.0.1", CHANNELS_X32, len(zuege), 0.0
    ) is True

    time.sleep(0.1)

    assert "/main/st/mix/fader" in pult.faders, sorted(pult.faders)[:5]

    #
    # Szenen statt Snapshots: andere Adresse, andere Zählweise (ab 0).
    #
    snapshots = control.get_snapshots("127.0.0.1")

    assert snapshots[0]["index"] == 0, snapshots[0]
    assert snapshots[0]["name"] == "Soundcheck", snapshots[0]

    assert control.load_snapshot("127.0.0.1", 2) is True

    time.sleep(0.15)

    assert pult.snapshot_index == 2, pult.snapshot_index

    assert [
        adresse for adresse, _ in pult.received
        if adresse == "/-action/goscene"
    ], "Die Szene wurde nicht über /-action/goscene aufgerufen."

    print("OK: Der X32-Modus antwortet auf seinen eigenen Adressen")

    #
    # /config/linkcfg/fdrmute gibt es nur beim X32. Ein X-Air
    # schweigt dazu - und XRack liest genau dieses Schweigen als "die
    # Fader folgen der Kopplung" (siehe _fader_follows_link). Würde
    # der Emulator hier antworten, ginge dieser Zweig nie durch die
    # Prüfung.
    #
    antwort = control._request(
        "127.0.0.1", pult.port, encode("/config/linkcfg/fdrmute")
    )

    assert antwort is not None and decode(antwort)[1] == [1], (
        f"Der X32 muss die Kopplungsvorgabe kennen: {antwort!r}"
    )

    xair = emulator.Pult()

    try:

        stumm = ConsoleControl()._request(
            "127.0.0.1", xair.port, encode("/config/linkcfg/fdrmute")
        )

        assert stumm is None, (
            "Ein X-Air darf zu /config/linkcfg/fdrmute schweigen - "
            f"geantwortet wurde: {stumm!r}"
        )

    finally:
        xair.stop()

    print("OK: Die Kopplungsvorgabe kennt nur der X32")

    #
    # Und die Familienerkennung findet ihn auf 10023. Dafür werden
    # die Portnummern im Modul umgebogen - der Emulator lauscht im
    # Test auf einem zufälligen Port.
    #
    import core.console_control as ccmodul

    xair_alt, x32_alt = ccmodul.PORT_XAIR, ccmodul.PORT_X32

    try:

        #
        # XAIR zuerst: Dort antwortet niemand, also muss die Erkennung
        # weiterziehen. Ein freier Port, den nichts belegt.
        #
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as leer:

            leer.bind(("127.0.0.1", 0))
            frei = leer.getsockname()[1]

        ccmodul.PORT_XAIR = frei
        ccmodul.PORT_X32 = pult.port

        frisch = ConsoleControl()

        assert frisch.detect("127.0.0.1") == FAMILY_X32, (
            "Auf dem zweiten Port wurde das Pult nicht mehr gefunden."
        )

    finally:
        ccmodul.PORT_XAIR, ccmodul.PORT_X32 = xair_alt, x32_alt

    print("OK: Die Erkennung findet ihn auf dem zweiten Port")

finally:
    pult.stop()


# ====================================================================
# 5. Das Programm, nicht nur die Klasse
#
# Der Emulator wird gestartet, wie ihn jemand von Hand startet, und
# über einen echten ConsoleControl angesprochen. Was nur als
# importierte Klasse funktioniert, hilft im Terminal niemandem.
# ====================================================================

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as suche:

    suche.bind(("127.0.0.1", 0))
    port = suche.getsockname()[1]

lauf = subprocess.Popen(
    [sys.executable, str(SKRIPT), "--port", str(port),
     "--adresse", "127.0.0.1"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

try:

    control = ConsoleControl()

    #
    # Hier wird die Erkennung NICHT übersprungen: Sie ist Teil
    # dessen, was geprüft werden soll. Nur der Port wird umgebogen.
    #
    import core.console_control as ccmodul

    xair_alt = ccmodul.PORT_XAIR
    ccmodul.PORT_XAIR = port

    try:

        familie = None

        #
        # Dem Programm einen Moment geben - es muss erst starten.
        #
        for _ in range(50):

            familie = control.detect("127.0.0.1")

            if familie is not None:
                break

            control.detect_reset()
            time.sleep(0.1)

        assert familie == FAMILY_XAIR, (
            "Das gestartete Programm wurde nicht als X-Air erkannt.\n"
            + (lauf.stderr.read() if lauf.poll() is not None else "")
        )

        zuege = control.get_channels("127.0.0.1", CHANNELS_XAIR)

        assert zuege, "Keine Kanalzüge vom gestarteten Programm."

        assert zuege[0]["name"] == "Kick", zuege[0]

        assert control.set_fader("127.0.0.1", CHANNELS_XAIR, 1, -20.0) is True

        time.sleep(0.15)

        assert abs(
            control.get_channels("127.0.0.1", CHANNELS_XAIR)[0]["db"] + 20.0
        ) < 0.01, "Der gesetzte Wert kam nicht zurück."

    finally:
        ccmodul.PORT_XAIR = xair_alt

    print("OK: Von Hand gestartet verhält es sich genauso")

finally:

    lauf.terminate()

    try:
        lauf.wait(timeout=5)
    except subprocess.TimeoutExpired:
        lauf.kill()


# ====================================================================
# 6. Das Testsignal
#
# Gerechnet und nachgemessen, ohne Soundkarte: Was hier stimmt,
# stimmt auch auf dem Pi - der Weg durch das ALSA-Loopback kopiert
# nur Bytes.
# ====================================================================

block = emulator.signal_bauen(kanaele=18, rate=48000)

rahmen = len(block) // (18 * 4)

assert rahmen == 96000, (
    f"Ein Takt bei 120 Schlägen sind zwei Sekunden, also 96000 Rahmen "
    f"- gerechnet wurden {rahmen}."
)

pegel = LevelMeter(18, decay=1.0).update(block)

#
# Kein Kanal übersteuert, und keiner ist versehentlich still.
#
for nummer, wert in enumerate(pegel, 1):

    assert 0.1 < wert < 1.0, (
        f"Kanal {nummer} liegt bei {wert:.3f} - still oder übersteuert."
    )

print(f"OK: Alle 18 Kanäle tragen Signal (Kick {pegel[0]:.2f}, "
      f"Snare {pegel[1]:.2f}, Lichtmix {pegel[16]:.2f})")

#
# Die Kanäle 8 bis 16 tragen so viele Pieptöne, wie ihre Nummer sagt.
# Damit lässt sich in einer Aufnahme nachsehen, ob jede Spur dort
# gelandet ist, wo sie hingehört - der Fehler, den man sonst erst
# beim Abhören merkt.
#
for nummer in (8, 12, 16):

    werte = struct.unpack_from(
        f"<{rahmen * 18}i", block, 0
    )[nummer - 1::18]

    #
    # Ein Piep ist ein Block, in dem der Pegel über die Hälfte geht;
    # gezählt werden die Übergänge von leise nach laut.
    #
    grenze = 0.25 * (2.0 ** 31)

    pieptoene = 0
    war_laut = False

    for stelle in range(0, rahmen, 480):

        laut = max(
            abs(wert) for wert in werte[stelle:stelle + 480]
        ) > grenze

        if laut and not war_laut:
            pieptoene += 1

        war_laut = laut

    assert pieptoene == nummer, (
        f"Kanal {nummer} muss {nummer} Pieptöne tragen, gezählt wurden "
        f"{pieptoene}."
    )

print("OK: Jeder Kanal ab 8 nennt seine Nummer in Pieptönen")

#
# Und der eigentliche Zweck des Lichtmixes: Die Lichtshow muss darauf
# die Snare finden - auf 2 und 4, und nur dort. Damit hängt der
# Emulator an derselben Kette wie die Show selbst.
#
analyse = Bandanalyse(rate=48000, channels=18, links=16, rechts=None)

haeppchen = 1024 * 18 * 4

treffer = []

for runde in range(3):

    for stelle in range(0, len(block), haeppchen):

        stand = analyse.verarbeite(block[stelle:stelle + haeppchen])

        if stand.get("snare"):
            treffer.append(runde * 2.0 + stelle / (18 * 4 * 48000))

#
# Der erste Takt geht für den Anlauf der Erkennung drauf (eine
# Sekunde, siehe SNARE_ANLAUF_S). Danach muss jeder Schlag kommen:
# zwei je Takt, also vier in den restlichen zwei Takten.
#
spaet = [zeit for zeit in treffer if zeit >= 2.0]

assert len(spaet) == 4, (
    f"Erwartet werden zwei Snares je Takt, gefunden: "
    f"{[round(zeit, 2) for zeit in treffer]}"
)

#
# Auf den Schlägen 2 und 4, nicht irgendwo: 0,5 s und 1,5 s im Takt.
#
for zeit in spaet:

    im_takt = zeit % 2.0

    assert 0.4 < im_takt < 0.7 or 1.4 < im_takt < 1.7, (
        f"Ein Treffer liegt bei {im_takt:.2f} s im Takt - das ist "
        f"weder Schlag 2 noch Schlag 4."
    )

print(f"OK: Die Lichtshow findet die Snare im Lichtmix "
      f"({[round(zeit % 2.0, 2) for zeit in spaet]} s im Takt)")

#
# Wo das Loopback landet, hängt davon ab, was sonst noch steckt - die
# Nummer wird deshalb aus der Kartenliste gelesen. Geprüft wird das
# an einer nachgestellten Liste, damit es auch auf einem Rechner
# ohne Soundkarte durchläuft.
#
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as ordner:

    liste = Path(ordner) / "cards"

    liste.write_text(
        " 0 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones\n"
        "                      bcm2835 Headphones\n"
        " 1 [U192k          ]: USB-Audio - UMC1820\n"
        "                      BEHRINGER UMC1820 at usb-0000:01:00.0-1.3\n"
        " 2 [Loopback       ]: Loopback - Loopback\n"
        "                      Loopback 1\n",
        encoding="utf-8",
    )

    assert emulator.loopback_geraet(str(liste)) == "hw:2,0", (
        "Die Karte des Loopbacks wird falsch gelesen: "
        + str(emulator.loopback_geraet(str(liste)))
    )

    #
    # Ohne geladenes Modul steht dort nichts - dann muss None
    # herauskommen, damit das Programm sagen kann, was zu tun ist,
    # statt an einem geratenen Gerät zu scheitern.
    #
    ohne = Path(ordner) / "ohne"

    ohne.write_text(
        " 0 [Headphones     ]: bcm2835_headpho - bcm2835 Headphones\n",
        encoding="utf-8",
    )

    assert emulator.loopback_geraet(str(ohne)) is None
    assert emulator.loopback_geraet(str(Path(ordner) / "gibtsnicht")) is None

print("OK: Das Loopback wird in der Kartenliste gefunden, nicht geraten")

#
# Zweimal gerechnet ist zweimal dasselbe. Ein Testsignal, das sich
# bei jedem Lauf ändert, wäre als Prüffeld wertlos - dann hinge das
# Ergebnis am Zufall statt am Programm.
#
assert emulator.signal_bauen(kanaele=18, rate=48000) == block, (
    "Zwei Durchläufe liefern verschiedene Signale."
)

print("OK: Das Testsignal ist bei jedem Lauf dasselbe")


print("Alle Emulator-Tests erfolgreich.")
