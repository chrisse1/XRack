#!/usr/bin/env python3
"""
Prüft die Audioanalyse der Lichtshow.

Hier lässt sich prüfen, was am Gerät am schwersten zu beurteilen
wäre: ob ein Basston wirklich im Bassband landet und nicht überall,
ob die Bänder unabhängig vom Pegel gleich bleiben, und ob aus dem
richtigen Kanalpaar gehört wird.

Was hier NICHT geprüft werden kann: ob die Show am Ende gut aussieht.
Das entscheidet das Auge vor Ort. Die Zahlen hier sichern nur ab,
dass die Grundlage stimmt.
"""

import array
import math

from lighting.analysis import (
    SNARE_AUSSCHLAG,
    SNARE_EMPFINDLICHKEIT,
    SNARE_SCHWELLE,
    Bandanalyse,
    Stimmungserkennung,
    snare_grenzen,
)

RATE = 48000
BLOCK = 1024


def sinus_bloecke(hz: float, bloecke: int = 40, amplitude: float = 0.8,
                  channels: int = 2, auf: tuple = (0, 1)) -> list:
    """
    Baut PCM-Blöcke (S32_LE, verschachtelt) mit einem Sinus auf den
    angegebenen Kanälen; alle anderen bleiben still.
    """

    daten = array.array("i")

    for n in range(BLOCK * bloecke):

        wert = int(amplitude * math.sin(2 * math.pi * hz * n / RATE) * (2 ** 31 - 1))

        for kanal in range(channels):
            daten.append(wert if kanal in auf else 0)

    roh = daten.tobytes()
    schritt = BLOCK * channels * 4

    return [roh[i:i + schritt] for i in range(0, len(roh) - schritt + 1, schritt)]


def stille_bloecke(bloecke: int = 40, channels: int = 2) -> list:

    return [bytes(BLOCK * channels * 4)] * bloecke


def durchlauf(bloecke: list, **kwargs) -> dict:
    """Alle Blöcke verrechnen und den letzten Stand liefern."""

    analyse = Bandanalyse(rate=RATE, **kwargs)

    stand = analyse.stand()

    for block in bloecke:
        stand = analyse.verarbeite(block)

    return stand


# ====================================================================
# 1. Landet ein Ton im richtigen Band?
# ====================================================================

for hz, band, andere in (
    (60, "low", ("mid", "high")),
    (800, "mid", ("low", "high")),
    (8000, "high", ("low", "mid")),
):

    stand = durchlauf(sinus_bloecke(hz), channels=2)

    for gegenprobe in andere:
        assert stand[band] > stand[gegenprobe] * 2, (
            f"{hz} Hz: '{band}' ({stand[band]:.2f}) muss deutlich über "
            f"'{gegenprobe}' ({stand[gegenprobe]:.2f}) liegen."
        )

print("OK: Tiefe, mittlere und hohe Töne landen im jeweils richtigen Band")


# ====================================================================
# 2. Der Pegel darf die Bänder nicht verschieben
#
# Was vom Pult kommt, schwankt je nach Aufbau um Größenordnungen. Die
# Show muss bei leisem wie bei lautem Signal dasselbe Bild ergeben -
# nur eben heller oder dunkler.
# ====================================================================

laut = durchlauf(sinus_bloecke(60, amplitude=0.9), channels=2)
leise = durchlauf(sinus_bloecke(60, amplitude=0.05), channels=2)

for band in ("low", "mid", "high"):
    assert abs(laut[band] - leise[band]) < 0.1, (
        f"Band '{band}' verschiebt sich mit dem Pegel: laut {laut[band]:.2f}, "
        f"leise {leise[band]:.2f}"
    )

#
# Der Gesamtpegel dagegen MUSS dem Signal folgen - an ihm hängt die
# Stille-Erkennung.
#
assert laut["level"] > leise["level"] * 5, (laut["level"], leise["level"])

print("OK: Die Bänder bleiben pegelunabhängig, der Gesamtpegel folgt dem Signal")


# ====================================================================
# 3. Stille ist Stille
# ====================================================================

stand = durchlauf(stille_bloecke(), channels=2)

assert stand["low"] == 0.0 and stand["mid"] == 0.0 and stand["high"] == 0.0, stand
assert stand["level"] < 0.001, stand
assert stand["beat"] is False

print("OK: Aus Stille wird keine Lichtshow")


# ====================================================================
# 4. Aus dem richtigen Kanalpaar hören
#
# Der Block enthält ALLE Kanäle des Interfaces verschachtelt. Wer
# hier danebengreift, bekommt eine Show zum falschen Signal - und
# merkt es womöglich nie, weil irgendetwas ja leuchtet.
# ====================================================================

#
# Achtkanaliges Interface, Musik liegt auf 5+6 (Index 4+5).
#
bloecke = sinus_bloecke(60, channels=8, auf=(4, 5))

falsch = durchlauf(bloecke, channels=8, links=0, rechts=1)
richtig = durchlauf(bloecke, channels=8, links=4, rechts=5)

assert falsch["level"] < 0.001, (
    "Auf dem falschen Kanalpaar darf nichts ankommen: " + str(falsch)
)
assert richtig["level"] > 0.1, richtig
assert richtig["low"] > richtig["high"] * 2, richtig

print("OK: Es wird genau das gewählte Kanalpaar gehört, nicht irgendeines")


# ====================================================================
# 5. Schläge
#
# Kein Takterkenner im musikalischen Sinn - ein Schlag ist ein
# deutlicher Ausreißer im Bass gegenüber dem, was gerade üblich war.
# Geprüft wird deshalb die Größenordnung, nicht die exakte Zahl.
# ====================================================================

def kick_bloecke(kicks: int = 8, bpm: int = 120, channels: int = 2) -> list:
    """Kurze Bassschläge im Takt, dazwischen Ruhe."""

    periode = int(RATE * 60.0 / bpm)
    laenge = int(0.05 * RATE)

    daten = array.array("i")

    for n in range(periode * kicks):

        stelle = n % periode

        if stelle < laenge:
            huelle = 1.0 - stelle / laenge
            wert = int(0.9 * huelle * math.sin(2 * math.pi * 60 * n / RATE) * (2 ** 31 - 1))
        else:
            wert = 0

        for _ in range(channels):
            daten.append(wert)

    roh = daten.tobytes()
    schritt = BLOCK * channels * 4

    return [roh[i:i + schritt] for i in range(0, len(roh) - schritt + 1, schritt)]


analyse = Bandanalyse(rate=RATE, channels=2)

gemeldet = sum(1 for block in kick_bloecke(kicks=8) if analyse.verarbeite(block)["beat"])

assert 6 <= gemeldet <= 14, (
    f"Bei acht Bassschlägen wurden {gemeldet} gemeldet - das ist zu weit "
    f"daneben (ein paar Doppelmeldungen sind für Licht verkraftbar)."
)

print(f"OK: Bassschläge werden erkannt ({gemeldet} Meldungen bei 8 Schlägen)")

#
# Und ein Dauerton darf nicht dauernd Schläge auslösen - sonst
# flackert das Licht durchgehend statt im Takt.
#
analyse = Bandanalyse(rate=RATE, channels=2)
bloecke = sinus_bloecke(60, bloecke=200)

gemeldet = sum(1 for block in bloecke if analyse.verarbeite(block)["beat"])

assert gemeldet < 20, (
    f"Ein gleichbleibender Ton hat {gemeldet} Schläge ausgelöst - erwartet "
    f"werden nur die am Anfang."
)

print(f"OK: Ein Dauerton löst kaum Schläge aus ({gemeldet} bei {len(bloecke)} Blöcken)")


# ====================================================================
# 6. Musik, Sprache, Stille auseinanderhalten
#
# Die unsicherste Stelle der ganzen Lichtsteuerung. Geprüft wird
# deshalb vor allem, dass NICHT vorschnell umgeschaltet wird - eine
# ruhige Stelle im Stück darf die Show nicht abwürgen.
# ====================================================================

DAUER = BLOCK / RATE   # rund 21 ms je Block

erkennung = Stimmungserkennung(stille_sekunden=6.0, sprache_sekunden=12.0)

#
# Erst Musik mit Schlägen.
#
for _ in range(50):
    erkennung.aktualisieren(
        {"level": 0.5, "beat": True, "low": 1.0, "mid": 0.3, "high": 0.1}, DAUER
    )

assert erkennung.zustand == "music", erkennung.zustand

#
# Dann Stille - aber noch nicht lange genug.
#
for _ in range(int(3.0 / DAUER)):
    erkennung.aktualisieren(
        {"level": 0.0, "beat": False, "low": 0.0, "mid": 0.0, "high": 0.0}, DAUER
    )

assert erkennung.zustand == "music", (
    "Nach drei Sekunden Stille darf noch nicht umgeschaltet werden - eine "
    "Pause zwischen zwei Stücken ist keine Ansage."
)

#
# Und jetzt lange genug.
#
for _ in range(int(4.0 / DAUER)):
    erkennung.aktualisieren(
        {"level": 0.0, "beat": False, "low": 0.0, "mid": 0.0, "high": 0.0}, DAUER
    )

assert erkennung.zustand == "silence", erkennung.zustand

print("OK: Stille wird erkannt - aber erst nach der eingestellten Wartezeit")

#
# Sprache: Es kommt etwas, aber ohne Bassschlag. Auch das braucht
# seine Zeit.
#
erkennung = Stimmungserkennung(stille_sekunden=6.0, sprache_sekunden=12.0)

for _ in range(int(8.0 / DAUER)):
    erkennung.aktualisieren(
        {"level": 0.2, "beat": False, "low": 0.1, "mid": 0.8, "high": 0.3}, DAUER
    )

assert erkennung.zustand == "music", (
    "Acht Sekunden ohne Bassschlag sind noch keine Ansage - das kann eine "
    "ruhige Strophe sein."
)

for _ in range(int(5.0 / DAUER)):
    erkennung.aktualisieren(
        {"level": 0.2, "beat": False, "low": 0.1, "mid": 0.8, "high": 0.3}, DAUER
    )

assert erkennung.zustand == "speech", erkennung.zustand

#
# Kommt der Takt zurück, ist es wieder Musik.
#
erkennung.aktualisieren(
    {"level": 0.5, "beat": True, "low": 1.0, "mid": 0.3, "high": 0.1}, DAUER
)

assert erkennung.zustand == "music", erkennung.zustand

print("OK: Sprache wird erst nach langer Entprellzeit angenommen - und "
      "sofort widerrufen, wenn der Takt zurückkommt")


# ====================================================================
# 7. Echte Musik, nicht nur saubere Einzelschläge
#
# Am Gerät ist die Show nach rund zehn Sekunden auf die
# Rückfallszene gesprungen - mitten in der Musik. Ursache war die
# Schlagerkennung: Sie verglich die TRÄGE Hüllkurve (250 ms Abfall,
# fürs Licht gedacht) mit ihrem eigenen Mittel. Unter durchgehendem
# Bass fällt die zwischen zwei Kicks gar nicht weit genug ab, ein
# Kick ragt nicht mehr heraus - gemessen kamen 5 Schläge in 20
# Sekunden an, wo 40 zu erwarten waren, mit einer Lücke von 19,5
# Sekunden.
#
# Der alte Test hat das nicht gefunden, weil sein Signal zu sauber
# war: einzelne Kicks mit Stille dazwischen. So sieht echte,
# komprimierte Musik nie aus. Deshalb steht hier jetzt ein Signal,
# das dem näher kommt.
# ====================================================================

def musik_bloecke(sekunden: int = 20, bpm: int = 120,
                  channels: int = 2) -> list:
    """
    Durchgehender Bass + Kicks darüber + Mitten + etwas Rauschen.
    Die Hüllkurve fällt also nie auf Null.
    """

    import random

    random.seed(1)

    periode = int(RATE * 60.0 / bpm)
    kick_laenge = 0.06 * RATE

    daten = array.array("i")

    for n in range(RATE * sekunden):

        stelle = n % periode

        kick = max(0.0, 1.0 - stelle / kick_laenge) if stelle < kick_laenge else 0.0

        wert = (
            0.35 * math.sin(2 * math.pi * 80 * n / RATE)
            + 0.45 * kick * math.sin(2 * math.pi * 55 * n / RATE)
            + 0.15 * math.sin(2 * math.pi * 900 * n / RATE)
            + 0.05 * random.uniform(-1.0, 1.0)
        )

        roh = int(max(-1.0, min(1.0, wert)) * (2 ** 31 - 1))

        for _ in range(channels):
            daten.append(roh)

    bytes_roh = daten.tobytes()
    schritt = BLOCK * channels * 4

    return [bytes_roh[i:i + schritt]
            for i in range(0, len(bytes_roh) - schritt + 1, schritt)]


analyse = Bandanalyse(rate=RATE, channels=2)

schlaege = 0
luecke = 0.0
groesste_luecke = 0.0

for block in musik_bloecke():

    if analyse.verarbeite(block)["beat"]:
        schlaege += 1
        luecke = 0.0
    else:
        luecke += BLOCK / RATE
        groesste_luecke = max(groesste_luecke, luecke)

#
# 20 Sekunden bei 120 bpm sind 40 Schlaege. Ein paar mehr oder
# weniger sind fuer Licht gleichgueltig - was zaehlt, ist die
# Groessenordnung.
#
assert 25 <= schlaege <= 60, (
    f"Bei rund 40 Bassschlägen in echter Musik wurden {schlaege} gemeldet."
)

#
# Und das ist die Zusicherung, an der es haengt: Die groesste Luecke
# ohne Schlag muss deutlich unter jeder brauchbaren Wartezeit fuer
# die Spracherkennung liegen. Sonst springt die Show mitten im Stueck
# auf die Rueckfallszene.
#
assert groesste_luecke < 3.0, (
    f"Größte Lücke ohne erkannten Schlag: {groesste_luecke:.1f} s - damit "
    f"hält jede Spracherkennung die Musik irgendwann für eine Ansage."
)

print(f"OK: In echter Musik kommen die Schläge durch ({schlaege} Stück, "
      f"größte Lücke {groesste_luecke:.1f} s)")


# ====================================================================
# 8. Die Spracherkennung ist standardmäßig aus
#
# Das ist eine Entscheidung aus dem Betrieb: "Kein Bassschlag" ist
# kein Beweis für eine Ansage. Eine Ballade, ein akustisches Set,
# eine lange Einleitung - alles kann eine Weile ohne erkennbaren Kick
# auskommen. Springt die Show dann auf eine feste Szene, leuchtet sie
# nicht aus, sondern falsch, und niemand weiß warum.
# ====================================================================

erkennung = Stimmungserkennung()

assert erkennung.sprache_sekunden == 0.0, (
    "Die Spracherkennung muss standardmäßig aus sein."
)

#
# Fuenf Minuten Signal ohne einen einzigen Schlag - und trotzdem
# bleibt es Musik.
#
for _ in range(int(300.0 / DAUER)):
    erkennung.aktualisieren(
        {"level": 0.3, "beat": False, "low": 0.2, "mid": 0.7, "high": 0.4}, DAUER
    )

assert erkennung.zustand == "music", (
    "Ohne eingeschaltete Spracherkennung darf nie auf 'Sprache' "
    "umgeschaltet werden: " + erkennung.zustand
)

#
# Stille bleibt davon unberuehrt - die ist eindeutig messbar.
#
for _ in range(int(10.0 / DAUER)):
    erkennung.aktualisieren(
        {"level": 0.0, "beat": False, "low": 0.0, "mid": 0.0, "high": 0.0}, DAUER
    )

assert erkennung.zustand == "silence", erkennung.zustand

print("OK: Sprache wird nur erkannt, wenn man es ausdrücklich einschaltet - "
      "Stille immer")


# ====================================================================
# 9. Die Snare
#
# Auch das ist keine Instrumentenerkennung, und es soll auch so
# dastehen: Gemeldet wird ein scharfer, LAUTER Einsatz im
# Mittenband, der Hoehen mitbringt. In den allermeisten Stuecken ist
# das die Snare.
#
# Geprueft wird deshalb nicht "erkennt sie eine Snare", sondern:
# Kommt bei einem Schlagzeugmuster ungefaehr die richtige Zahl an,
# und - viel wichtiger - schweigt sie bei dem, was KEINE Snare ist?
# ====================================================================

def schlagzeug(kick=True, snare=True, hihat=False, bass=False,
               bpm=120, takte=8, channels=2) -> list:
    """
    Ein einfaches Schlagzeugmuster.

    Kick auf jeder Zaehlzeit, Snare auf jeder zweiten, Hi-Hat auf
    jeder Achtel, dazu auf Wunsch eine durchgehende Basslinie. Die
    Snare besteht aus Rumpf (200 Hz) und Teppich (3 kHz) - genau die
    beiden Anteile, an denen die Erkennung sie festmacht.
    """

    periode = int(RATE * 60.0 / bpm)
    kick_laenge = int(0.05 * RATE)
    snare_laenge = int(0.04 * RATE)
    achtel = periode // 2
    hihat_laenge = int(0.02 * RATE)

    daten = array.array("i")

    for n in range(periode * takte):

        stelle = n % periode
        wert = 0.0

        if kick and stelle < kick_laenge:
            huelle = 1.0 - stelle / kick_laenge
            wert += 0.9 * huelle * math.sin(2 * math.pi * 60 * n / RATE)

        if snare and (n // periode) % 2 == 1 and stelle < snare_laenge:
            huelle = 1.0 - stelle / snare_laenge
            wert += 0.5 * huelle * math.sin(2 * math.pi * 200 * n / RATE)
            wert += 0.5 * huelle * math.sin(2 * math.pi * 3000 * n / RATE)

        if hihat:
            stelle_achtel = n % achtel

            if stelle_achtel < hihat_laenge:
                huelle = 1.0 - stelle_achtel / hihat_laenge
                wert += 0.35 * huelle * math.sin(2 * math.pi * 9000 * n / RATE)

        if bass:
            wert += 0.5 * math.sin(2 * math.pi * 80 * n / RATE)

        roh_wert = int(max(-1.0, min(1.0, wert)) * (2 ** 31 - 1))

        for _ in range(channels):
            daten.append(roh_wert)

    roh = daten.tobytes()
    schritt = BLOCK * channels * 4

    return [roh[i:i + schritt] for i in range(0, len(roh) - schritt + 1, schritt)]


def snares(bloecke: list,
           empfindlichkeit: float = SNARE_EMPFINDLICHKEIT) -> int:

    analyse = Bandanalyse(
        rate=RATE, channels=2, snare_empfindlichkeit=empfindlichkeit
    )

    return sum(1 for block in bloecke if analyse.verarbeite(block)["snare"])


#
# Die Abbildung Empfindlichkeit -> Schwelle/Ausschlag muss die
# dokumentierten Anker treffen. Die Mitte des Reglers ist der Stand,
# der am Geraet gefaellt; laufen die Zahlen davon weg, klingt eine
# frische Einrichtung anders als die eingestellte.
#
schwelle, ausschlag = snare_grenzen(SNARE_EMPFINDLICHKEIT)

assert abs(schwelle - SNARE_SCHWELLE) < 1e-9, (schwelle, SNARE_SCHWELLE)
assert abs(ausschlag - SNARE_AUSSCHLAG) < 1e-9, (ausschlag, SNARE_AUSSCHLAG)

#
# Und die Richtung: mehr Empfindlichkeit heisst weniger streng.
#
assert snare_grenzen(1.0) < snare_grenzen(0.0), (
    "Die Empfindlichkeit ist verkehrt herum: mehr muss lockerer heißen."
)

print("OK: Die Mitte des Reglers trifft die dokumentierten Zahlen")

#
# Vier Snares in acht Takten. Eine Meldung mehr ist der erste Block:
# Dort ist die laufende Spitze noch der Anfangswert, und alles ragt
# darueber hinaus. Das ist beim Kick genauso und fuer Licht
# verkraftbar - ein Blitz beim Einsetzen der Musik.
#
gemeldet = snares(schlagzeug())

assert 4 <= gemeldet <= 6, (
    f"Bei vier Snares wurden {gemeldet} gemeldet."
)

print(f"OK: Snares werden erkannt ({gemeldet} Meldungen bei 4 Schlägen)")

#
# Mit Hi-Hats dazwischen muessen die Snares weiterhin durchkommen.
#
gemeldet = snares(schlagzeug(hihat=True))

assert gemeldet >= 4, (
    f"Mit Hi-Hats kommen nur noch {gemeldet} Snares durch."
)

print(f"OK: Auch mit Hi-Hats kommen die Snares durch ({gemeldet} Meldungen)")

#
# Und jetzt der Teil, auf den es ankommt: Was KEINE Snare ist, darf
# auch keine sein.
#
# Ein Signal aus lauter Kicks hat beim ersten Anlauf acht von acht
# Malen eine Snare gemeldet - die steile Flanke des Kicks laesst auch
# die Mitten ausschlagen. Das Blitzlicht haette also auf der Bassdrum
# gezuckt. Erst die Bedingung "es muessen Hoehen dabei sein" hat das
# getrennt: Beim Kick lagen die bei 0,04 der Spitze, bei der Snare
# bei 0,65.
#
gemeldet = snares(schlagzeug(snare=False))

assert gemeldet <= 1, (
    f"Ein Signal aus lauter Kicks OHNE Snare hat {gemeldet} Snares gemeldet."
)

print(f"OK: Der Kick allein löst keine Snare aus ({gemeldet} Meldungen)")

#
# Und die Hi-Hat auch nicht - die ist fast nur oben und hat keinen
# Rumpf.
#
gemeldet = snares(schlagzeug(kick=False, snare=False, hihat=True))

assert gemeldet <= 1, (
    f"Hi-Hats allein haben {gemeldet} Snares gemeldet."
)

print(f"OK: Die Hi-Hat allein löst keine Snare aus ({gemeldet} Meldungen)")

#
# Auch bei voller Empfindlichkeit nicht - dann traegt die Lautstaerke
# nichts mehr bei, und die Trennung vom Kick haengt allein an den
# Hoehen. Ohne diese Bedingung meldete dasselbe Signal acht Snares
# statt einer.
#
gemeldet = snares(schlagzeug(snare=False), 1.0)

assert gemeldet <= 2, (
    f"Der Kick allein hat bei voller Empfindlichkeit {gemeldet} Snares "
    f"gemeldet - die Höhen sortieren ihn nicht mehr aus."
)

print(f"OK: Auch ganz aufgedreht bleibt der Kick draußen ({gemeldet})")

#
# Der schwierigste Fall, und er ist beim Messen aufgefallen: Kick und
# Hi-Hat auf demselben Achtel. Der Kick liefert den Rumpf, die Hi-Hat
# die Hoehen - zusammen sieht das aus wie eine Snare, und keine der
# beiden festen Bedingungen greift.
#
# Das laesst sich mit drei Baendern nicht sauber trennen, und es soll
# hier auch nicht behauptet werden. Was gilt: Wer die Empfindlichkeit
# herunterdreht, wird es los - das ist genau die Aufgabe des Reglers.
# An dem kuenstlichen Muster hier kommen bei voller Empfindlichkeit
# alle acht Paare durch, ganz unten noch eines.
#
gemeldet = snares(schlagzeug(snare=False, hihat=True), 0.0)

assert gemeldet <= 2, (
    f"Kick und Hi-Hat zusammen haben auch bei kleinster Empfindlichkeit "
    f"{gemeldet} Snares gemeldet - dann hilft der Regler nicht mehr."
)

assert snares(schlagzeug(snare=False, hihat=True), 1.0) > gemeldet, (
    "Bei voller Empfindlichkeit muss mehr durchkommen - sonst tut der "
    "Regler an dieser Stelle nichts."
)

print(f"OK: Kick und Hi-Hat lassen sich mit dem Regler aussperren ({gemeldet})")

#
# Und der Rumpf ist es, der die Hi-Hat aussortiert - auch ganz
# aufgedreht, wo die Lautstaerke nichts mehr beitraegt und alles an
# der Bedingung "Mitten gegen Hoehen" haengt.
#
gemeldet = snares(schlagzeug(kick=False, snare=False, hihat=True), 1.0)

assert gemeldet <= 1, (
    f"Hi-Hats allein haben bei voller Empfindlichkeit {gemeldet} Snares "
    f"gemeldet - der fehlende Rumpf sortiert sie nicht mehr aus."
)

print(f"OK: Auch ganz aufgedreht bleibt die Hi-Hat draußen ({gemeldet})")

#
# Ein gehaltener Ton ist keine Snare, auch wenn er laut ist.
#
# Ein Saegezahn hat einen Grundton in den Mitten und Obertoene bis
# weit nach oben - er erfuellt also alles ausser der einen
# Bedingung, dass es ein AUSSCHLAG sein muss und kein Dauerzustand.
# Ohne die meldete er 25 Snares in vier Sekunden; das Blitzlicht
# haette durch ein gehaltenes Gitarrenbrett hindurchgeflackert.
#
def saegezahn(hz: float = 400.0, bloecke: int = 200,
              amplitude: float = 0.7, channels: int = 2) -> list:

    daten = array.array("i")

    for n in range(BLOCK * bloecke):

        wert = amplitude * (2.0 * ((n * hz / RATE) % 1.0) - 1.0)

        roh_wert = int(wert * (2 ** 31 - 1))

        for _ in range(channels):
            daten.append(roh_wert)

    roh = daten.tobytes()
    schritt = BLOCK * channels * 4

    return [roh[i:i + schritt] for i in range(0, len(roh) - schritt + 1, schritt)]


gemeldet = snares(saegezahn())

assert gemeldet <= 8, (
    f"Ein gehaltener Ton hat {gemeldet} Snares gemeldet - damit blitzt es "
    f"durch jede laute Fläche hindurch."
)

print(f"OK: Ein gehaltener Ton ist keine Snare ({gemeldet} Meldungen in 200 Blöcken)")

#
# In der Stille bleibt es still. Dafuer sorgt die laufende Spitze:
# Sie faellt nie unter ihren Mindestwert, und gegen den wird
# gemessen.
#
assert snares([bytes(BLOCK * 2 * 4)] * 200) == 0, (
    "In der Stille darf keine Snare gemeldet werden."
)

print("OK: In der Stille gibt es keine Snare")

#
# Und der Regler muss wirklich reichen.
#
# Das war der Anlass fuer die Umstellung: Vorher bewegte er nur eine
# von vier Bedingungen, und am Geraet blieb nur der unterste Anschlag
# brauchbar. Jetzt dreht er Schwelle und Ausschlag zugleich - und
# zwar so weit, dass zwischen den Enden Faktoren liegen und nicht
# ein paar Prozent.
#
muster = schlagzeug(hihat=True, bass=True)

streng = snares(muster, 0.0)
mitte = snares(muster, SNARE_EMPFINDLICHKEIT)
locker = snares(muster, 1.0)

assert streng < mitte < locker, (
    f"Der Regler reicht nicht: {streng} / {mitte} / {locker}"
)

assert locker >= streng * 3, (
    f"Zwischen den Enden liegt zu wenig: {streng} gegen {locker}"
)

print(f"OK: Der Regler reicht von {streng} über {mitte} bis {locker} Meldungen")


print("Alle Analyse-Tests erfolgreich.")
