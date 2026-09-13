#!/usr/bin/env python3
"""
Fragt das Mischpult, welche OSC-Adressen es kennt - nur lesend.

Anlass: In der Kanalfader-Karte soll ein Schalter A/D <-> USB
erscheinen, also das, was man im Mischpult heute von Hand umlegt.
Welche Adresse das ist, steht in einer Bibliothek
(onyx-and-iris/xair-api-python, xair_api/shared.py: usbinput ->
"rtnsw"). Eine Bibliothek ist aber keine Hardware. Bevor XRack darauf
baut, soll das Pult selbst antworten.

    python3 scripts/xrack-pult-fragen.py
    python3 scripts/xrack-pult-fragen.py 192.168.1.77

Ohne Adresse wird gesucht: erst die von Hand eingetragene aus
config/state.json, dann der Rundruf - dieselbe Reihenfolge wie in
XRack.

GESCHRIEBEN WIRD NICHTS. Jede Anfrage geht ohne Argumente hinaus; die
X-Serie antwortet darauf mit dem aktuellen Wert. Am Pult aendert sich
dabei nichts, auch nicht die Lautstaerke - man kann das Programm also
mitten in einer Probe laufen lassen.

Gelesen wird ueber core/console_control.py, also ueber XRacks eigenen
OSC-Kodierer. Das ist hier ausdruecklich gewollt (anders als beim
Emulator, der bewusst einen eigenen hat): Gefragt ist nicht, ob
irgendeine Software das Pult erreicht, sondern ob XRack es tut.

Zu jeder Frage steht eine ERWARTUNG dabei. Das Programm sagt nicht nur
"Antwort da", sondern auch, ob sie zu der Erwartung passt - eine
Antwort vom falschen Typ waere sonst leicht zu uebersehen.

Die beiden ersten Zeilen sind Gegenkontrollen: Adressen, die XRack
heute schon benutzt. Antworten die nicht, ist das Pult nicht
erreichbar - dann sagt "keine Antwort" bei den uebrigen nichts ueber
die Adressen aus. Die letzte Zeile ist die Gegenkontrolle in die
andere Richtung: eine Adresse, die es an der X-Serie nicht geben
sollte. Antwortet sie doch, antwortet das Pult auf alles, und das
ganze Programm beweist nichts.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.console_control import (  # noqa: E402
    ConsoleControl,
    FAMILY_XAIR,
    decode,
    encode,
)
from core.state_store import StateStore  # noqa: E402


#
# (Adresse, erwarteter Typ, wozu)
#
# Die Kanalnummern sind 1 und 3, weil genau die am Geraet gebraucht
# wurden: Kanal 1 und 2 nehmen auf, Kanal 3 war der, dessen Eingang auf
# USB stand.
#
FRAGEN = [
    ("/ch/01/mix/fader", float, "Gegenkontrolle: antwortet das Pult ueberhaupt?"),
    ("/ch/01/config/name", str, "Gegenkontrolle: und auch auf Text?"),
    ("/ch/01/preamp/rtnsw", int, "DER SCHALTER: 0 = A/D, 1 = USB"),
    ("/ch/03/preamp/rtnsw", int, "derselbe Schalter auf Kanal 3"),
    ("/ch/01/config/rtnsrc", int, "welcher USB-Rueckweg auf dem Kanal liegt"),
    ("/ch/01/preamp/rtntrim", float, "Pegelkorrektur des USB-Wegs"),
    ("/ch/01/config/insrc", int, "welcher Eingang analog auf dem Kanal liegt"),
    ("/rtn/aux/preamp/rtnsw", int, "hat der Aux-Rueckweg (17+18) den Schalter?"),
    ("/ch/01/config/source", int, "X32-Weg - an einem X-Air erwartet: nichts"),
]


def pult_finden() -> str | None:
    """Dieselbe Reihenfolge wie in XRack: Eintrag, dann Rundruf."""

    steuerung = ConsoleControl()

    try:
        laden = StateStore(Path(__file__).resolve().parent.parent / "config" / "state.json")
        eingetragen = (laden.get("console_ip_manual") or "").strip()
    except Exception:
        eingetragen = ""

    if eingetragen:
        print(f"Eingetragene Pult-Adresse: {eingetragen}")
        return eingetragen

    print("Keine Adresse eingetragen - Rundruf laeuft ...")

    return steuerung.discover(force=True)


def fragen(steuerung: ConsoleControl, host: str) -> None:

    breite = max(len(adresse) for adresse, _, _ in FRAGEN)

    for adresse, typ, wozu in FRAGEN:

        antwort = steuerung._request(host, steuerung._port, encode(adresse))

        if antwort is None:
            ergebnis = "keine Antwort"

        else:

            zurueck, argumente = decode(antwort)

            if not argumente:
                ergebnis = f"Antwort ohne Wert (Adresse: {zurueck})"

            else:

                wert = argumente[0]

                passt = "" if isinstance(wert, typ) else (
                    f"  ACHTUNG: erwartet war {typ.__name__}, "
                    f"bekommen {type(wert).__name__}"
                )

                ergebnis = f"{wert!r}{passt}"

        print(f"  {adresse:<{breite}}  {ergebnis}")
        print(f"  {'':<{breite}}  ({wozu})")


def main() -> int:

    host = sys.argv[1] if len(sys.argv) > 1 else pult_finden()

    if not host:
        print(
            "Kein Mischpult gefunden. Adresse als Argument angeben, oder in "
            "XRack unter Einstellungen eintragen."
        )
        return 1

    steuerung = ConsoleControl()

    familie = steuerung.detect(host)

    if familie is None:
        print(f"Auf {host} antwortet kein Pult (weder Port 10024 noch 10023).")
        return 1

    print(f"Pult auf {host}:{steuerung._port} - Familie {familie}")

    if familie != FAMILY_XAIR:
        print(
            "\nAchtung: Die Fragen unten sind fuer die X-Air-Serie. An einem "
            "X32 ist \"keine Antwort\" bei rtnsw deshalb zu erwarten - und "
            "die letzte Zeile (/config/source) umgekehrt die interessante."
        )

    print()

    fragen(steuerung, host)

    print(
        "\nBitte die Ausgabe zurueckschicken. Entscheidend sind die beiden "
        "Gegenkontrollen oben (antwortet das Pult?) und die Zeile mit "
        "rtnsw (gibt es den Schalter, und je Kanal?)."
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
