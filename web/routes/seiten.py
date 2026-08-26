"""
Die Seite selbst und der Sekundenpuls des Dashboards.
"""

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from web.i18n import get_translations

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def index(request: Request):

    application = request.app.state.application

    application.update_status()

    language = application.config.data.application.language

    translations = get_translations(language)

    return request.app.state.templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "application": application,
            "status": application.status,
            "lang": language,
            "t": translations,
            "i18n_json": json.dumps(translations, ensure_ascii=False),
            #
            # Direkt in die Seite: Die Fader-Karte braucht die
            # Einstellung sofort beim Laden. Ueber /api/settings zu
            # gehen wuerde bei jedem Seitenaufruf einen Suchlauf nach
            # dem Pult anstossen - fuer zwei Zahlen zu viel.
            #
            "faders_autolock_json": json.dumps(
                application.get_faders_autolock()
            ),
        },
    )


@router.get("/api/status")
def status(request: Request):

    application = request.app.state.application

    application.update_status()

    return application.status.model_dump()
