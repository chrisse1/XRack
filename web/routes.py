from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


class AudioSelection(BaseModel):
    device_id: str

router = APIRouter()

@router.post("/api/audio/select")
async def audio_select(
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

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):

    application = request.app.state.application
    
    application.update_status()
    
    return request.app.state.templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "application": application,
            "status": application.status,
        },
    )


@router.get("/api/status")
async def status(request: Request):

    application = request.app.state.application

    application.update_status()

    return application.status.model_dump()
    
@router.post("/api/recorder/start")
async def recorder_start(request: Request):

    application = request.app.state.application

    success = application.recorder.start()

    return {
        "success": success
    }


@router.post("/api/recorder/stop")
async def recorder_stop(request: Request):

    application = request.app.state.application

    application.recorder.stop()

    return {
        "success": True
    }
    
@router.get("/api/audio/devices")
async def audio_devices(request: Request):

    application = request.app.state.application

    application.audio_manager.scan()

    devices = []

    for device in application.audio_manager.get_devices():

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
