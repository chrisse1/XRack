"""
Herunterfahren, Neustarten und der Netzwerk-Selbsttest.
"""

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get("/api/system/network-report")
def network_report(request: Request):
    """
    Der Netzwerk-Selbsttest. Klartext, damit man ihn ohne Umweg
    ansehen, kopieren und weiterschicken kann.
    """

    application = request.app.state.application

    return PlainTextResponse(application.netzwerk_selbsttest())


@router.post("/api/system/shutdown")
def system_shutdown(request: Request):

    application = request.app.state.application

    success = application.shutdown_system()

    return {
        "success": success
    }


@router.post("/api/system/restart")
def system_restart(request: Request):

    application = request.app.state.application

    success = application.restart_service()

    return {
        "success": success
    }
