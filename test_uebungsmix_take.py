#!/usr/bin/env python3
"""
Prüft Stufe 5: aus Übungsmix und Mitschnitt EINE Datei
(core/stem_combiner.py:uebungsmix_mit_take).

Beim Üben legt XRack beides in denselben Wiedergabestrom, ohne etwas zu
schreiben - das ist der richtige Weg fürs "mal eben anhören". Sitzt ein
Versuch aber, will man ihn mitnehmen: auf den Stick, ins Backup, auf ein
anderes XRack. Dafür muss aus zwei Dateien eine werden.

Geprüft wird gegen ECHTE Wave64-Dateien, die XRacks eigener Schreiber
anlegt und sein eigener Leser wieder liest. Eine Attrappe wäre hier
wertlos: Es geht gerade darum, dass Kanäle, Versatz und Länge nach dem
Umschreiben noch stimmen.

Die Werte in den Quellen sind so gewählt, dass jeder Kanal und jeder
Rahmen eindeutig wiederzuerkennen ist - eine Verschiebung um einen Kanal
oder um einen Rahmen fällt damit auf, statt in einem Meer gleicher
Zahlen unterzugehen.
"""

import shutil
import struct
from pathlib import Path

from core.stem_combiner import StemCombineError, uebungsmix_mit_take
from reader.w64_reader import W64Reader
from writer.w64_writer import W64Writer

SCRATCH = Path("recordings_test_take")
RATE = 48000


def wert(kanal: int, rahmen: int) -> int:
    """
    Ein Wert, der Kanal UND Rahmen verrät.

    Kanal 3, Rahmen 7 wird zu 3_000_007 - im Ergebnis lässt sich damit
    ablesen, woher jedes Sample stammt.
    """

    return kanal * 1_000_000 + rahmen


def quelle_schreiben(
    praefix: str, kanaele: int, rahmen: int, start_channel: int,
    marker: str, erster_kanal: int,
) -> Path:
    """
    Eine echte W64-Datei mit erkennbaren Werten.

    `erster_kanal` ist die Nummer, die in den Werten steht - so lässt
    sich Mix (1, 2, ...) von Mitschnitt (9, 10) unterscheiden, auch wenn
    beide bei Kanal 0 ihrer eigenen Datei anfangen.
    """

    writer = W64Writer()
    writer.directory = SCRATCH

    writer.open(
        channels=kanaele,
        sample_rate=RATE,
        bits_per_sample=24,
        name_prefix=praefix,
        marker=marker,
        start_channel=start_channel,
    )

    block = bytearray()

    for n in range(rahmen):
        for k in range(kanaele):
            block += struct.pack("<i", wert(erster_kanal + k, n))

    writer.write(bytes(block))

    pfad = Path(writer.filename)

    writer.close()

    return pfad


def lesen(pfad: Path) -> tuple[W64Reader, list[list[int]]]:
    """Die ganze Datei als [rahmen][kanal]."""

    leser = W64Reader()
    leser.open(pfad)

    roh = b""

    while True:
        stueck = leser.read(4096 * leser.frame_bytes)
        if not stueck:
            break
        roh += stueck

    rahmen = len(roh) // leser.frame_bytes

    werte = [
        [
            struct.unpack_from("<i", roh, (n * leser.channels + k) * 4)[0]
            for k in range(leser.channels)
        ]
        for n in range(rahmen)
    ]

    leser.close()

    return leser, werte


shutil.rmtree(SCRATCH, ignore_errors=True)
SCRATCH.mkdir(parents=True, exist_ok=True)

try:

    # ================================================================
    # 1. Kanäle und Länge
    #
    # Der Mix liegt ab Kanal 1 und hat vier Kanäle, der Mitschnitt ab
    # Kanal 9 und hat zwei. Herauskommen muss eine Datei über zehn
    # Kanäle, in der beide auf IHREN Plätzen stehen - dazwischen still.
    # ================================================================

    mix = quelle_schreiben("Umbrella", 4, 100, 1, "p", erster_kanal=1)
    take = quelle_schreiben("Umbrella-Take", 2, 100, 9, "s", erster_kanal=9)

    assert "_p" in mix.name, mix.name
    assert "_s9" in take.name, take.name

    writer = W64Writer()
    writer.directory = SCRATCH

    ergebnis = uebungsmix_mit_take(mix, take, "Umbrella-fertig", writer=writer)

    neu = SCRATCH / ergebnis

    assert neu.is_file(), ergebnis

    #
    # Wieder ein Übungsmix, und er sagt, wo er hingehört: ab Kanal 1.
    #
    assert ergebnis.endswith("_p.w64"), (
        f"Das Ergebnis ist kein Übungsmix ab Kanal 1: {ergebnis}"
    )

    leser, werte = lesen(neu)

    assert leser.channels == 10, (
        f"Erwartet zehn Kanäle (Mix 1-4, Lücke, Mitschnitt 9-10), "
        f"bekommen {leser.channels}"
    )

    assert len(werte) == 100, f"{len(werte)} Rahmen statt 100"

    #
    # Rahmen 7, beispielhaft: Mix auf 1-4, Stille auf 5-8, Mitschnitt
    # auf 9-10.
    #
    rahmen = werte[7]

    for kanal in (1, 2, 3, 4, 9, 10):
        assert rahmen[kanal - 1] == wert(kanal, 7), (
            f"Kanal {kanal} in Rahmen 7 trägt {rahmen[kanal - 1]}, "
            f"erwartet {wert(kanal, 7)} - da ist etwas verrutscht."
        )

    for kanal in (5, 6, 7, 8):
        assert rahmen[kanal - 1] == 0, (
            f"Kanal {kanal} müsste still sein, trägt aber "
            f"{rahmen[kanal - 1]}."
        )

    print(f"OK: Beide Quellen stehen auf ihren Kanälen ({ergebnis})")

    # ================================================================
    # 2. Der Versatz wird angewandt - und nur auf den Mitschnitt
    #
    # Der Mitschnitt hinkt dem Mix um die Laufzeit durch das Pult
    # hinterher (gemessen, siehe core/laufzeit_messung.py). Beim Üben
    # wird er deshalb vorgezogen. Geschieht das beim Schreiben NICHT,
    # ist die neue Datei um diese Millisekunden verschoben - und genau
    # das hört man, denn dafür wurde die Messung ja gebaut.
    # ================================================================

    #
    # 10 ms bei 48 kHz sind 480 Rahmen. Die Quellen sind länger, damit
    # danach noch etwas übrig ist.
    #
    mix2 = quelle_schreiben("Versatz", 2, 2000, 1, "p", erster_kanal=1)
    take2 = quelle_schreiben("Versatz-Take", 2, 2000, 3, "s", erster_kanal=3)

    writer = W64Writer()
    writer.directory = SCRATCH

    ergebnis2 = uebungsmix_mit_take(
        mix2, take2, "Versatz-fertig", versatz_ms=10.0, writer=writer
    )

    leser2, werte2 = lesen(SCRATCH / ergebnis2)

    assert leser2.channels == 4, leser2.channels

    #
    # Im Rahmen 0 steht beim Mix der Rahmen 0, beim Mitschnitt aber
    # schon der Rahmen 480.
    #
    assert werte2[0][0] == wert(1, 0), werte2[0]

    assert werte2[0][2] == wert(3, 480), (
        f"Der Mitschnitt wurde nicht vorgezogen: Kanal 3 trägt "
        f"{werte2[0][2]}, erwartet {wert(3, 480)} (10 ms = 480 Rahmen)."
    )

    #
    # Und weiter hinten gilt derselbe Abstand - der Versatz ist eine
    # Verschiebung, keine einmalige Lücke.
    #
    assert werte2[1000][2] == wert(3, 1480), werte2[1000][:4]

    print("OK: Der Mitschnitt wird um den gemessenen Versatz vorgezogen")

    # ================================================================
    # 3. Die Länge richtet sich nach dem Mix
    #
    # Die Aufnahme läuft oft noch weiter, wenn das Stück zu Ende ist -
    # und sie fängt durch den Versatz später an. Beides darf die neue
    # Datei nicht verlängern oder verkürzen.
    # ================================================================

    kurz = quelle_schreiben("Kurz", 2, 50, 1, "p", erster_kanal=1)
    lang = quelle_schreiben("Kurz-Take", 2, 500, 3, "s", erster_kanal=3)

    writer = W64Writer()
    writer.directory = SCRATCH

    ergebnis3 = uebungsmix_mit_take(kurz, lang, "Kurz-fertig", writer=writer)

    _, werte3 = lesen(SCRATCH / ergebnis3)

    assert len(werte3) == 50, (
        f"Der längere Mitschnitt hat die Datei auf {len(werte3)} Rahmen "
        f"verlängert - sie gehört so lang wie der Mix."
    )

    #
    # Umgekehrt: Ist der Mitschnitt kürzer, wird mit Stille aufgefüllt
    # statt abgeschnitten.
    #
    langer_mix = quelle_schreiben("Lang", 2, 500, 1, "p", erster_kanal=1)
    kurzer_take = quelle_schreiben("Lang-Take", 2, 50, 3, "s", erster_kanal=3)

    writer = W64Writer()
    writer.directory = SCRATCH

    ergebnis4 = uebungsmix_mit_take(
        langer_mix, kurzer_take, "Lang-fertig", writer=writer
    )

    _, werte4 = lesen(SCRATCH / ergebnis4)

    assert len(werte4) == 500, (
        f"Der kürzere Mitschnitt hat die Datei auf {len(werte4)} Rahmen "
        f"gekürzt - der Mix gibt die Länge vor."
    )

    assert werte4[49][2] == wert(3, 49), werte4[49]

    assert werte4[300][0] == wert(1, 300), (
        "Der Mix hört mit dem Mitschnitt auf."
    )

    assert werte4[300][2] == 0, (
        f"Hinter dem Ende des Mitschnitts steht kein Stille, sondern "
        f"{werte4[300][2]}."
    )

    print("OK: Die Länge richtet sich nach dem Mix, nicht nach dem Take")

    # ================================================================
    # 4. Was nicht geht, sagt es
    # ================================================================

    try:
        uebungsmix_mit_take(
            SCRATCH / "gibtsnicht.w64", take, "Nix"
        )
        raise AssertionError("Eine fehlende Datei fiel nicht auf.")

    except StemCombineError as fehler:
        assert "nicht gefunden" in str(fehler), fehler

    #
    # Verschiedene Abtastraten: Beide Dateien stammen vom selben Gerät.
    # Sind die Raten verschieden, stimmt etwas anderes nicht - und ein
    # stillschweigendes Umrechnen verdeckte das.
    #
    anders = W64Writer()
    anders.directory = SCRATCH

    anders.open(
        channels=2, sample_rate=44100, bits_per_sample=24,
        name_prefix="Fremd-Take", marker="s", start_channel=3,
    )
    anders.write(struct.pack("<i", 1) * 2 * 10)
    fremd = Path(anders.filename)
    anders.close()

    try:
        uebungsmix_mit_take(mix2, fremd, "Nix")
        raise AssertionError("Verschiedene Abtastraten fielen nicht auf.")

    except StemCombineError as fehler:
        assert "Abtastraten" in str(fehler), fehler

    print("OK: Fehlende Datei und verschiedene Raten werden gemeldet")

finally:
    shutil.rmtree(SCRATCH, ignore_errors=True)

print("Alle Tests zu Mix + Mitschnitt erfolgreich.")
