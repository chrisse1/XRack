"""
Creates and configures the FastAPI application.
"""

from __future__ import annotations

import time

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.routes import router

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.application import Application


def create_app(application: Application):
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def lebenslauf(_app: FastAPI):
        """
        Was beim geordneten Herunterfahren noch zu tun ist.

        Bisher: nichts - und das war eine Lücke. Die
        Diagnose-Aufzeichnung schreibt ihre Abschlusszeile aus ihrem
        eigenen Thread, und der ist ein Daemon-Thread: Beim Beenden
        stirbt er einfach mit, ohne noch etwas zu schreiben. In der
        Datei stand danach kein Abschluss - und die Aufzeichnung
        schliesst daraus, der Prozess sei abgestuerzt (siehe
        core/diagnostics.py).

        Am Geraet sah das so aus: Nach einem voellig geordneten
        "systemctl restart" hielt die Diagnose beim naechsten Start
        fest, der Prozess sei nicht ordentlich beendet worden. Eine
        Warnung, die bei jedem normalen Neustart erscheint, schickt die
        naechste Fehlersuche in die falsche Richtung - schlimmer als
        gar keine.

        Deshalb wird hier abgeschlossen. Danach heisst eine fehlende
        Abschlusszeile wirklich, was sie sagt: Der Prozess war
        ploetzlich weg.
        """

        yield

        try:
            application.diagnostics.stop()

        except Exception as exc:
            #
            # Das Herunterfahren darf daran nicht haengen bleiben.
            #
            application.logger.warning(
                "Diagnose konnte nicht abgeschlossen werden: %s", exc
            )

    app = FastAPI(
    title=application.config.data.application.name,
    version=application.config.data.application.version,
    lifespan=lebenslauf,
)

    app.include_router(router)

    app.mount("/static", StaticFiles(directory="web/static"), name="static")

    templates = Jinja2Templates(directory="web/templates")

    #
    # Cache-Buster für die eigenen statischen Dateien (xrack.js/.css):
    # ändert sich bei jedem Dienst-Neustart, damit der Browser nach
    # einem Update nicht versehentlich eine alte, gecachte Version
    # weiterverwendet (siehe Verwirrung durch den Aufnahme/Soundcheck-
    # Knopf-Fix, der ohne Hard-Refresh nicht sichtbar wurde).
    #
    templates.env.globals["asset_version"] = str(int(time.time()))

    app.state.templates = templates
    app.state.application = application

    return app
