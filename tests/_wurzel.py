"""
Der Suchpfad für die Testreihe - und der Weg zur Wurzel des Projekts.

Die Tests liegen in tests/, XRacks Module eine Ebene darüber. Wird eine
Testdatei direkt gestartet ("python3 tests/test_x.py"), steht in
sys.path nur ihr eigenes Verzeichnis - "import core.audio_file" fände
dann nichts.

Deshalb setzt jede Testdatei als ERSTE Zeile

    from _wurzel import WURZEL  # noqa: F401

Das tut zweierlei: Es legt die Projektwurzel in den Suchpfad, und es
liefert sie als Pfad - denn die halbe Testreihe greift auf Dateien
daneben zu (install.sh, scripts/, web/templates/). Ohne die Konstante
stünde in jeder Datei ein eigenes "Path(__file__).parent.parent", und
beim nächsten Umzug wären es wieder fünfzig Stellen.

Warum kein pytest mit conftest.py: XRacks Tests sind eigenständige
Programme, die man einzeln starten kann und die ihre Befunde im
Klartext ausgeben ("OK: ..."). Auf dem Pi ist kein pytest installiert,
und die Testreihe soll dort laufen, ohne etwas nachzuinstallieren -
dieselbe Regel wie beim Update über den USB-Stick.
"""

import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

if str(WURZEL) not in sys.path:
    sys.path.insert(0, str(WURZEL))
