"""
Auswahl und Erkennung des Audiointerfaces.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

#
# Warum hier KEIN "async def" steht, obwohl FastAPI das anbietet:
#
# Ein async-Handler laeuft im Event-Loop. Blockiert er, steht die
# gesamte Weboberflaeche still - auch der Sekundenpuls von
# /api/status. Hinter praktisch jedem Endpunkt hier stecken aber
# blockierende Aufrufe: subprocess (nmcli, bluetoothctl, ffmpeg) mit
# Timeouts bis 30 Sekunden, Dateizugriffe und UDP-Anfragen ans
# Mischpult. Antwortet das Pult auf /info, dann aber nicht mehr - Kabel
# im Betrieb gezogen -, summieren sich allein dessen Zeitueberschreitungen
# auf rund 19 Sekunden.
#
# Nicht-async Handler fuehrt FastAPI selbsttaetig in einem Threadpool
# aus. Dort darf blockiert werden, ohne dass es alle anderen Anfragen
# mitreisst. Fuer eine Anwendung, die im Kern Unterprozesse und Geraete
# bedient, ist das die richtige Betriebsart - nicht die Ausnahme.
#
# Ein Handler darf hier nur dann async werden, wenn er tatsaechlich
# "await" benutzt.
#

class AudioSelection(BaseModel):
    device_id: str


@router.post("/api/audio/select")
def audio_select(
    selection: AudioSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.select_audio_device(
        selection.device_id
    )

    return {
        "success": success
    }


@router.post("/api/audio/rescan")
def rescan_audio_devices(
    request: Request,
):

    application = request.app.state.application

    application.rescan_audio_devices()

    application.refresh_port_forward()

    return {
        "success": True
    }


    
@router.get("/api/audio/devices")
def audio_devices(request: Request):

    application = request.app.state.application

    application.audio_manager.scan()

    devices = []

    for device in application.audio_manager.get_devices():
        application.logger.info(
            "API: %s | selected=%s",
            device.id,
            application.selected_audio_device.id
            if application.selected_audio_device
            else "None",
        )

        devices.append(
            {
                "id": device.id,
                "name": device.name,
                "description": device.description,
                "channels": device.channels,
                "sample_rate": device.sample_rate,
                "sample_bits": device.sample_bits,
                "formats": device.formats,
            }
        )

    return devices
