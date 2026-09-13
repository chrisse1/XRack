"""
Die Laufzeit durch das Pult messen - mit einem Klick.

Warum gemessen und nicht gerechnet:

Beim Zusammenhören von Übungsmix und Mitschnitt hinkt der Mitschnitt
hinterher. XRack schreibt in den ALSA-Puffer, das Pult wandelt, mischt
und schickt zurück, XRack liest wieder aus einem Puffer. Die
Periodengrösse (1024 Rahmen, bei 48 kHz 21,3 ms) ist davon nur ein
Summand: Verzögert wird nicht um eine Periode, sondern um so viel, wie
der Puffer gerade trägt, und ALSA beginnt erst zu spielen, wenn er
voll genug ist. Wie voll, sagt ALSA nur auf Nachfrage, und pyalsaaudio
reicht diese Frage nicht durch. Dazu kommt die Strecke durch USB und
durch das Pult - Wandlung, Mischung, Routing -, die am Pultmodell, an
der Samplerate und am Weg durch das Pult hängt.

Eine Zahl daraus zu rechnen hiesse raten. Gemessen wird sie mit einem
Aufwand von vier Sekunden.

**Was gemessen wird, ist genau das, was nachher korrigiert wird.** Der
Versuch geht denselben Weg wie das Üben mit Mitschnitt: XRack spielt
einen Klick-Mix ab und nimmt dabei auf. Steht der Klick im Mix bei
einer Sekunde und im Mitschnitt bei 1,08 s, dann ist die Laufzeit
80 ms - ohne eine einzige Annahme über Puffer, Perioden oder Pulte.

Voraussetzung ist eine Schleife im Pult: Der ausgegebene Klick muss
auf einem Kanal zurückkommen, der gerade aufgenommen wird. Die kann
XRack nicht selbst herstellen; deshalb geht der Klick auf ALLE
Ausgabekanäle - so trägt ihn jeder USB-Rückweg, und es genügt der
Weg, der zum Üben ohnehin eingerichtet ist.
"""

import logging
import struct
from pathlib import Path

from reader.w64_reader import W64Reader
from writer.w64_writer import W64Writer

logger = logging.getLogger("XRack")


#
# Der Klick sitzt nicht am Anfang: Der Strom muss erst eingeschwungen
# sein, und der Mitschnitt braucht ein Stueck Stille davor, aus dem
# sich das Grundrauschen ablesen laesst.
#
KLICK_BEI_S = 1.0

#
# Kurz genug, um die Flanke genau zu finden, lang genug, um durch
# einen Kompressor oder eine Frequenzweiche im Pult zu kommen. Ein
# einzelner Abtastwert waere theoretisch schaerfer - und praktisch
# oft gar nicht wiederzufinden.
#
KLICK_DAUER_S = 0.005

#
# Ein Viertel des Vollausschlags. Laut genug, um sich vom Rauschen
# abzuheben, leise genug, um niemanden zu erschrecken und nichts zu
# uebersteuern.
#
KLICK_PEGEL = 0.25

#
# Wie lang der Klick-Mix ist. Nach dem Klick bleiben damit zwei
# Sekunden - so viel Laufzeit kann keine Anlage haben, und mehr
# Messdauer kostet nur Platz.
#
MESSDAUER_S = 3.0

#
# Wie oft gemessen wird.
#
# Eine einzelne Zahl ist keine Messung, sondern ein Wert. Erst mehrere
# Laeufe zeigen, ob er steht: Kommt dreimal dasselbe heraus, ist es
# eine Eigenschaft der Anlage und laesst sich anwenden. Streut es, ist
# es keine Konstante - und dann waere es falsch, so zu tun, als sei
# sie eine.
#
# Drei Laeufe kosten gut zehn Sekunden. Das ist einmal im Leben einer
# Anlage zu verschmerzen.
#
MESSUNGEN = 3

#
# Ab dieser Streuung gilt der Wert nicht als verlaesslich.
#
# Eine Periode sind bei 48 kHz gut 21 ms; was darunter bleibt, ist die
# Koernigkeit der Puffer und kein Widerspruch.
#
SPANNE_WARNUNG_MS = 10

VOLLAUSSCHLAG = 2 ** 31

#
# Ab wann gilt ein Ausschlag als der Klick? Das Vielfache bezieht sich
# auf das gemessene Grundrauschen, die Untergrenze verhindert, dass
# bei voelliger Stille schon ein einzelnes gekipptes Bit als Treffer
# gilt.
#
SCHWELLE_FAKTOR = 8.0
SCHWELLE_MINDESTENS = 0.02


def klick_datei(ordner: Path, kanaele: int, rate: int) -> Path:
    """
    Schreibt den Klick-Mix - eine echte Wave64, wie XRack sie sonst
    auch schreibt.

    Auf ALLEN Kanälen derselbe Klick: XRack weiss nicht, welchen Weg
    das Pult zurückführt, und so ist es auch egal.
    """

    schreiber = W64Writer()

    schreiber.directory = Path(ordner)

    schreiber.open(
        channels=kanaele,
        sample_rate=rate,
        bits_per_sample=24,
        name_prefix="Laufzeitmessung",
    )

    rahmen_gesamt = int(MESSDAUER_S * rate)

    klick_von = int(KLICK_BEI_S * rate)
    klick_bis = klick_von + max(1, int(KLICK_DAUER_S * rate))

    stiller_rahmen = bytes(kanaele * 4)

    block = bytearray()

    for n in range(rahmen_gesamt):

        if klick_von <= n < klick_bis:

            #
            # Scharfer Anfang, weiches Ende.
            #
            # Der Anfang ist die Messung: Gesucht wird die erste
            # Stelle ueber der Schwelle, und die soll der erste Wert
            # des Klicks sein. Mit einem sanften Einschwingen faende
            # man ihn erst ein paar Abtastwerte spaeter - jedes Mal
            # gleich viel, aber jedes Mal zu spaet.
            #
            # Das Ende darf dagegen ausklingen; ein Rechteck an beiden
            # Enden knackt nur unnoetig.
            #
            anteil = (n - klick_von) / max(1, klick_bis - klick_von)

            wert = int(
                KLICK_PEGEL * (VOLLAUSSCHLAG - 1) * (1.0 - anteil)
            )

            block += struct.pack("<i", wert) * kanaele

        else:
            block += stiller_rahmen

    schreiber.write(bytes(block))
    schreiber.close()

    return Path(schreiber.filename)


def klick_finden(pfad: Path) -> tuple[int, float]:
    """
    Sucht den ersten Ausschlag im Mitschnitt.

    Liefert (Rahmen, Schwelle). Rahmen ist -1, wenn nichts gefunden
    wurde - dann ist der Weg im Pult nicht geschlossen, und das ist
    ein Befund und kein Messwert.

    Gesucht wird die erste Flanke, nicht die lauteste Stelle: Was
    danach kommt, sind Nachhall und Rückkopplung des Weges. Der Anfang
    ist die Laufzeit.
    """

    leser = W64Reader()

    try:
        leser.open(pfad)
    except (OSError, ValueError) as fehler:
        logger.error("Mitschnitt nicht lesbar: %s (%s)", pfad, fehler)
        return -1, 0.0

    try:

        rahmen_bytes = leser.frame_bytes
        kanaele = leser.channels

        if rahmen_bytes <= 0 or kanaele <= 0:
            return -1, 0.0

        #
        # Blockweise, nicht in einem Zug: Der Mitschnitt ist zwar kurz,
        # aber der Leser hat eine Blockschnittstelle, und die wird
        # benutzt, statt an ihr vorbeizugreifen.
        #
        stuecke = []

        while True:

            stueck = leser.read(256 * 1024)

            if not stueck:
                break

            stuecke.append(stueck)

        daten = b"".join(stuecke)

        if not daten:
            return -1, 0.0

    finally:
        leser.close()

    rahmen_gesamt = len(daten) // rahmen_bytes

    if rahmen_gesamt <= 0:
        return -1, 0.0

    #
    # Das Grundrauschen aus dem Anfang: Dort ist es still, denn der
    # Klick kann fruehestens zu seiner eigenen Zeit ankommen - eine
    # negative Laufzeit gibt es nicht.
    #
    ruhe_bis = min(rahmen_gesamt, int(0.3 * leser.sample_rate))

    grundrauschen = 0

    for n in range(ruhe_bis):
        grundrauschen = max(
            grundrauschen, _spitze(daten, n, kanaele, rahmen_bytes)
        )

    schwelle = max(
        grundrauschen * SCHWELLE_FAKTOR,
        SCHWELLE_MINDESTENS * VOLLAUSSCHLAG,
    )

    for n in range(ruhe_bis, rahmen_gesamt):

        if _spitze(daten, n, kanaele, rahmen_bytes) >= schwelle:
            return n, schwelle

    return -1, schwelle


def _spitze(daten: bytes, rahmen: int, kanaele: int,
            rahmen_bytes: int) -> int:
    """Der groesste Betrag eines Rahmens ueber alle Kanaele."""

    anfang = rahmen * rahmen_bytes

    groesste = 0

    for kanal in range(kanaele):

        versatz = anfang + kanal * 4

        wert = struct.unpack("<i", daten[versatz:versatz + 4])[0]

        groesste = max(groesste, abs(wert))

    return groesste


def mittlerer_wert(werte: list[int]) -> int:
    """
    Der mittlere der gemessenen Werte - nicht ihr Durchschnitt.

    Ein einzelner Ausreisser (ein Knacken auf der Leitung, ein
    verpasster Puffer) zöge den Durchschnitt mit sich; den mittleren
    Wert lässt er unberührt. Bei drei Läufen heisst das: Zwei müssen
    sich einig sein, der dritte darf danebenliegen.
    """

    if not werte:
        return 0

    geordnet = sorted(werte)

    return geordnet[len(geordnet) // 2]


def versatz_ms(mitschnitt: Path, rate: int) -> tuple[int, str]:
    """
    Die Laufzeit in Millisekunden - oder eine Begründung, warum nicht.

    Die Rechnung ist die ganze Messung: Der Klick steht im Mix bei
    KLICK_BEI_S. Wo er im Mitschnitt steht, ist diese Sekunde plus die
    Laufzeit des Weges. Die Differenz ist der gesuchte Wert.

    **Warum dabei oft eine sehr kleine Zahl herauskommt** - das ist
    kein Fehler, sondern die Bauart: Auf der Ausgabeseite verzögert der
    ALSA-Puffer den Ton um seine Füllung. Auf der Aufnahmeseite wirkt
    derselbe Puffer andersherum: Der erste Block, den XRack liest, ist
    der ÄLTESTE im Ring - der Mitschnitt beginnt also ein Stück in der
    Vergangenheit. Beide Puffer sind gleich gross (1024 Rahmen je
    Periode, siehe audio/audio_backend.py und
    audio/audio_playback_backend.py), und damit heben sie sich weitgehend
    auf. Übrig bleibt der wirkliche Weg durch USB und Pult, und der
    sind wenige Millisekunden.
    """

    rahmen, _ = klick_finden(mitschnitt)

    if rahmen < 0:
        return -1, (
            "Im Mitschnitt ist kein Klick zu finden. Führt am Pult ein "
            "Weg vom Wiedergabekanal zurück auf einen Kanal, der gerade "
            "aufgenommen wird?"
        )

    versatz = rahmen - int(KLICK_BEI_S * rate)

    if versatz < 0:
        return -1, (
            "Der Klick steht vor seiner eigenen Zeit - da stimmt etwas "
            "nicht. Lag auf dem aufgenommenen Kanal schon vorher ein "
            "Signal an?"
        )

    return int(round(versatz * 1000 / rate)), ""
