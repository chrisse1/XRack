"""
Herunterfahren und Neustarten des Geraets.
"""

from fastapi import APIRouter, Request

router = APIRouter()

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
