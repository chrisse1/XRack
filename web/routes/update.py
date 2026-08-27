"""
Update aus dem Internet oder vom USB-Stick.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class UpdateSelection(BaseModel):
    #
    # "usb" (ZIP-Datei vom Stick) oder "github" (aus dem Internet).
    # Voreinstellung ist der USB-Weg, damit ein aelteres Frontend, das
    # noch gar keine Quelle mitschickt, weiter funktioniert.
    #
    source: str = "usb"

    #
    # Ein Rueckschritt auf eine aeltere Version. Setzt die Oberflaeche
    # nur, wenn der Nutzer die Rueckfrage bejaht hat.
    #
    allow_downgrade: bool = False


@router.get("/api/update/info")
def update_info(request: Request):
    """
    Liefert die laufende Version, ob eine ZIP auf dem USB-Stick liegt,
    und den Fortschritt eines laufenden Updates.
    """

    application = request.app.state.application

    return application.get_update_info()


@router.post("/api/update/start")
def update_start(request: Request, selection: UpdateSelection):
    """
    Startet das Update - aus dem Internet oder aus der ZIP-Datei auf
    dem USB-Stick.

    Der Dienst startet sich dabei selbst neu - die Antwort kommt also
    noch, bevor das Update durch ist. Den Ausgang liefert
    GET /api/update/status, dessen Statusdatei den Neustart übersteht.
    """

    application = request.app.state.application

    success, message = application.start_update(
        selection.source, allow_downgrade=selection.allow_downgrade
    )

    return {
        "success": success,
        "message": message,
    }


@router.get("/api/update/status")
def update_status(request: Request):

    application = request.app.state.application

    return application.get_update_status()


@router.post("/api/update/acknowledge")
def update_acknowledge(request: Request):
    """
    Quittiert das Ergebnis des letzten Updates - danach zeigt das
    Einstellungen-Modal es nicht mehr an.
    """

    application = request.app.state.application

    return {"success": application.acknowledge_update()}
