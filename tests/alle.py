#!/usr/bin/env python3
"""
Die ganze Testreihe, ein Kommando:

    python3 tests/alle.py
    python3 tests/alle.py wlan ueben     (nur, was dazu passt)

Jede Testdatei ist ein eigenständiges Programm und wird als eigener
Prozess gestartet. Das ist Absicht und kein Umweg:

  - Die Tests stellen Module um (sys.modules["alsaaudio"] wird durch
    eine Attrappe ersetzt), verbiegen Konstanten und lassen Threads
    laufen. In einem gemeinsamen Prozess trüge ein Test das ins
    nächste Programm hinein, und dann hinge das Ergebnis an der
    Reihenfolge.
  - Ein Absturz reisst nur seinen eigenen Lauf mit. Die übrigen laufen
    weiter, und am Ende steht, was ALLES nicht geht - nicht nur das
    Erste.

Ausgegeben wird je Datei eine Zeile; wer scheitert, bekommt seine
letzten Zeilen dazu. Der Rückgabewert ist die Anzahl der gescheiterten
Dateien - damit taugt das Programm auch als Torwächter vor einem
Commit.

Gestartet wird mit demselben Python, mit dem dieses Programm läuft
(sys.executable). Auf dem Pi ist das XRacks eigene Umgebung, sofern man
sie aufruft - und nur dort liegen psutil und die übrigen Abhängigkeiten.
"""

import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent

#
# So lange darf eine einzelne Datei brauchen. Die Browser-Prüfungen
# starten Chromium mehrfach, die Laufzeitmessung wartet auf echte
# Sekunden - zwanzig Minuten sind grosszügig, aber nicht unendlich:
# Ein Versuch, der haengt, soll die Reihe nicht anhalten.
#
FRIST_S = 1200


def dateien(muster: list[str]) -> list[Path]:

    alle = sorted(HIER.glob("test_*.py"))

    if not muster:
        return alle

    return [
        pfad for pfad in alle
        if any(teil.lower() in pfad.name.lower() for teil in muster)
    ]


def main() -> int:

    zu_pruefen = dateien(sys.argv[1:])

    if not zu_pruefen:
        print("Keine passende Testdatei gefunden.")
        return 1

    breite = max(len(pfad.name) for pfad in zu_pruefen)

    gescheitert = []

    begonnen = time.monotonic()

    for pfad in zu_pruefen:

        print(f"{pfad.name:<{breite}}  ... ", end="", flush=True)

        start = time.monotonic()

        try:

            lauf = subprocess.run(
                [sys.executable, str(pfad)],
                capture_output=True,
                text=True,
                timeout=FRIST_S,
                cwd=str(HIER.parent),
            )

            erfolg = lauf.returncode == 0
            ausgabe = lauf.stdout + lauf.stderr

        except subprocess.TimeoutExpired:

            erfolg = False
            ausgabe = f"Zeitüberschreitung nach {FRIST_S} s."

        dauer = time.monotonic() - start

        #
        # Übersprungene Prüfungen sind kein Erfolg zum Danebenlegen und
        # kein Fehler - sie sollen aber auffallen, sonst haelt man eine
        # Reihe fuer vollstaendig, in der der halbe Browser-Teil fehlt.
        #
        uebersprungen = "ÜBERSPRUNGEN" in ausgabe or "übersprungen" in ausgabe

        if erfolg:
            zeichen = "übersprungen" if uebersprungen else "ok"
        else:
            zeichen = "FEHLER"
            gescheitert.append((pfad.name, ausgabe))

        print(f"{zeichen}  ({dauer:.0f} s)")

    print()

    for name, ausgabe in gescheitert:

        print(f"--- {name} " + "-" * max(0, 60 - len(name)))

        zeilen = [z for z in ausgabe.splitlines() if z.strip()]

        print("\n".join(zeilen[-15:]))
        print()

    gesamt = time.monotonic() - begonnen

    print(
        f"{len(zu_pruefen) - len(gescheitert)} von {len(zu_pruefen)} "
        f"Dateien erfolgreich, {gesamt / 60:.1f} Minuten."
    )

    return len(gescheitert)


if __name__ == "__main__":
    sys.exit(main())
