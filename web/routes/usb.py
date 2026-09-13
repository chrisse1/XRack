"""
USB-Stick: Zustand, Kopieren in beide Richtungen, Auswerfen.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class UsbImport(BaseModel):
    #
    # Pfade RELATIV zum Stick - was hier ankommt, wird gegen den
    # Einhaengepunkt aufgeloest und darf ihn nicht verlassen (siehe
    # UsbStorage.aufloesen).
    #
    sources: list[str]

    #
    # "music" oder "recordings".
    #
    target: str

    #
    # Nur bei "music": der Ordner in der Bibliothek.
    #
    folder: str = ""

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


@router.get("/api/usb/browse")
def usb_browse(
    request: Request,
    path: str = "",
    target: str = "music",
):
    """
    Was auf dem Stick liegt - Ordner und Dateien dieses Ordners.

    `target` entscheidet nur darüber, was als verwendbar gilt: Musik
    oder Aufnahmen. Gelesen wird immer dasselbe Verzeichnis.
    """

    application = request.app.state.application

    inhalt = application.usb_browse(path, target)

    if inhalt is None:
        return {
            "available": False,
            "path": "",
            "folders": [],
            "files": [],
        }

    return {"available": True, **inhalt}


@router.post("/api/usb/import")
def usb_import(auswahl: UsbImport, request: Request):
    """
    Holt Dateien und ganze Ordner vom Stick auf das Gerät.

    Die Arbeit läuft im Hintergrund (ein Album sind schnell ein paar
    hundert Megabyte); den Fortschritt liefert
    GET /api/usb/import_status.
    """

    application = request.app.state.application

    success, message = application.start_usb_import(
        auswahl.sources,
        auswahl.target,
        auswahl.folder,
    )

    return {
        "success": success,
        "message": message,
    }


@router.get("/api/usb/import_status")
def usb_import_status(request: Request):

    application = request.app.state.application

    return application.get_usb_import_status()


@router.post("/api/usb/eject")
def eject_usb(request: Request):

    application = request.app.state.application

    success, message = application.eject_usb()

    return {
        "success": success,
        "message": message,
    }
