"""
Creates and configures the FastAPI application.
"""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from web.routes import router

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.application import Application


def create_app(application: Application):
    """Create and configure the FastAPI application."""

    app = FastAPI(
    title=application.config.data.application.name,
    version=application.config.data.application.version,
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
