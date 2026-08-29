"""
Alle Endpunkte der Weboberflaeche, nach Bereichen aufgeteilt.

Warum hier KEIN "async def" in den Modulen steht, obwohl FastAPI das
anbietet:

Ein async-Handler laeuft im Event-Loop. Blockiert er, steht die
gesamte Weboberflaeche still - auch der Sekundenpuls von /api/status.
Hinter praktisch jedem Endpunkt stecken aber blockierende Aufrufe:
subprocess (nmcli, bluetoothctl, ffmpeg) mit Timeouts bis 30 Sekunden,
Dateizugriffe und UDP-Anfragen ans Mischpult. Antwortet das Pult auf
/info, dann aber nicht mehr - Kabel im Betrieb gezogen -, summieren
sich allein dessen Zeitueberschreitungen auf rund 19 Sekunden.

Nicht-async Handler fuehrt FastAPI selbsttaetig in einem Threadpool
aus. Dort darf blockiert werden, ohne dass es alle anderen Anfragen
mitreisst. Fuer eine Anwendung, die im Kern Unterprozesse und Geraete
bedient, ist das die richtige Betriebsart - nicht die Ausnahme.

Ein Handler darf nur dann async werden, wenn er tatsaechlich "await"
benutzt.

Die Reihenfolge der Einbindung unten spielt eine Rolle, sobald zwei
Pfade sich ueberschneiden koennten. Hier hat jedes Modul seinen
eigenen Pfadanfang, und die einzigen Pfade mit Platzhalter
(/api/recordings/{filename}) liegen zusammen in recordings.py - dort
bleibt ihre urspruengliche Reihenfolge erhalten.
"""

from fastapi import APIRouter

from web.routes import (
    audio,
    bluetooth,
    console,
    diagnostics,
    lighting,
    music,
    recordings,
    seiten,
    settings,
    system,
    update,
    usb,
)

router = APIRouter()

for _teil in (
    seiten,
    audio,
    recordings,
    music,
    bluetooth,
    console,
    settings,
    system,
    usb,
    diagnostics,
    lighting,
    update,
):
    router.include_router(_teil.router)
