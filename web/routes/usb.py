"""
USB-Stick: Zustand, Kopiervorgang, Auswerfen.
"""

from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/api/usb/status")
def usb_status(request: Request):

    application = request.app.state.application

    return {
        "connected": application.usb_storage.connected
    }


@router.get("/api/usb/copy_status")
def usb_copy_status(request: Request):

    application = request.app.state.application

    return application.get_usb_copy_status()


@router.post("/api/usb/eject")
def eject_usb(request: Request):

    application = request.app.state.application

    success, message = application.eject_usb()

    return {
        "success": success,
        "message": message,
    }
