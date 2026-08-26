"""
Diagnose-Aufzeichnung fuer sporadische Fehler.
"""

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

router = APIRouter()

class DiagnosticsSelection(BaseModel):
    enabled: bool


@router.get("/api/diagnostics/status")
def diagnostics_status(request: Request):

    application = request.app.state.application

    return application.get_diagnostics_status()


@router.post("/api/diagnostics")
def set_diagnostics(
    selection: DiagnosticsSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_diagnostics(selection.enabled)

    return {
        "success": success,
        "message": message,
    }


@router.get("/api/diagnostics/download")
def download_diagnostics(request: Request):
    """
    Liefert die Aufzeichnung zum Herunterladen - damit man sie zur
    Fehlersuche weitergeben kann, ohne sie per SSH holen zu müssen.
    """

    application = request.app.state.application

    path = Path(application.get_diagnostics_status()["path"])

    if not path.is_file():
        return {"success": False}

    return FileResponse(
        path,
        media_type="text/plain",
        filename="xrack-diagnose.log",
    )
