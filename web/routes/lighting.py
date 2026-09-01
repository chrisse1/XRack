"""
Lichtsteuerung über DMX.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class LightingEnabledSelection(BaseModel):
    enabled: bool


class LightingTemplateSelection(BaseModel):
    id: str = ""
    name: str
    channels: list[str]


class LightingIdSelection(BaseModel):
    id: str


class LightingFixtureSelection(BaseModel):
    id: str = ""
    name: str
    template: str
    address: int

    #
    # Vorgabe wie im Modell: Wer die Art nicht mitschickt, bekommt
    # das Verhalten, das es vor den Arten gab.
    #
    kind: str = "effect"


class LightingValuesSelection(BaseModel):
    id: str
    values: list[int]


class LightingBrightnessSelection(BaseModel):
    id: str
    brightness: int


class LightingSceneSelection(BaseModel):
    name: str
    id: str = ""


class LightingPortSelection(BaseModel):
    port: str


@router.get("/api/lighting/status")
def lighting_status(request: Request):

    application = request.app.state.application

    return application.get_lighting_status()


#
# Der DMX-Ausgang: einmalig nach der Installation zuzuordnen. Frueher
# ein Gang ins Terminal (ola_dev_info / ola_patch), jetzt zwei Aufrufe
# von den Einstellungen aus.
#

@router.get("/api/lighting/dmx/ports")
def lighting_dmx_ports(request: Request):

    application = request.app.state.application

    return application.get_dmx_ports()


@router.post("/api/lighting/dmx/patch")
def lighting_dmx_patch(
    selection: LightingPortSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.patch_dmx_port(selection.port)

    return {"success": success, "message": message}


@router.post("/api/lighting/enabled")
def lighting_enabled(
    selection: LightingEnabledSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_lighting_enabled(selection.enabled)

    return {"success": success, "message": message}


@router.post("/api/lighting/template")
def lighting_template(
    selection: LightingTemplateSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.save_light_template(selection.model_dump())

    return {"success": success, "message": message}


@router.post("/api/lighting/template/delete")
def lighting_template_delete(
    selection: LightingIdSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.delete_light_template(selection.id)

    return {"success": success, "message": message}


@router.post("/api/lighting/fixture")
def lighting_fixture(
    selection: LightingFixtureSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.save_light_fixture(selection.model_dump())

    return {"success": success, "message": message}


@router.post("/api/lighting/fixture/delete")
def lighting_fixture_delete(
    selection: LightingIdSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.delete_light_fixture(selection.id)

    return {"success": success, "message": message}


@router.post("/api/lighting/values")
def lighting_values(
    selection: LightingValuesSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_light_fixture_values(
        selection.id, selection.values
    )

    return {"success": success, "message": message}


@router.post("/api/lighting/brightness")
def lighting_brightness(
    selection: LightingBrightnessSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_light_fixture_brightness(
        selection.id, selection.brightness
    )

    return {"success": success, "message": message}


@router.post("/api/lighting/blackout")
def lighting_blackout(request: Request):

    application = request.app.state.application

    success, message = application.light_blackout()

    return {"success": success, "message": message}


@router.post("/api/lighting/scene")
def lighting_scene(
    selection: LightingSceneSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.save_light_scene(
        selection.name, selection.id
    )

    return {"success": success, "message": message}


@router.post("/api/lighting/scene/activate")
def lighting_scene_activate(
    selection: LightingIdSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.activate_light_scene(selection.id)

    return {"success": success, "message": message}


@router.post("/api/lighting/scene/delete")
def lighting_scene_delete(
    selection: LightingIdSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.delete_light_scene(selection.id)

    return {"success": success, "message": message}


class LightingShowSettings(BaseModel):
    channel: int | None = None
    channel_mono: bool | None = None
    sensitivity: float | None = None
    effect_mode: str | None = None
    pulse_seconds: float | None = None
    pulse_base: float | None = None
    snare_strobe: bool | None = None
    snare_sense: float | None = None
    snare_power: float | None = None
    color_low: str | None = None
    color_mid: str | None = None
    color_high: str | None = None
    color_low_1: str | None = None
    color_mid_1: str | None = None
    color_high_1: str | None = None
    color_low_2: str | None = None
    color_mid_2: str | None = None
    color_high_2: str | None = None
    fallback_scene: str | None = None
    silence_threshold: float | None = None
    silence_seconds: float | None = None
    speech_seconds: float | None = None
    background_seconds: float | None = None
    background_beats: int | None = None
    color_invert: bool | None = None
    invert_beats: int | None = None
    fade_seconds: float | None = None


@router.post("/api/lighting/show/start")
def lighting_show_start(request: Request):

    application = request.app.state.application

    success, message = application.start_light_show()

    return {"success": success, "message": message}


@router.post("/api/lighting/show/stop")
def lighting_show_stop(request: Request):

    application = request.app.state.application

    success, message = application.stop_light_show()

    return {"success": success, "message": message}


@router.post("/api/lighting/show/settings")
def lighting_show_settings(
    selection: LightingShowSettings,
    request: Request,
):

    application = request.app.state.application

    #
    # Nur mitgeschickte Felder weiterreichen: Ein Formular, das nur
    # die Empfindlichkeit aendert, soll nicht nebenbei das Kanalpaar
    # zurueckstellen.
    #
    werte = {
        name: wert
        for name, wert in selection.model_dump().items()
        if wert is not None
    }

    success, message = application.set_light_show_settings(werte)

    return {"success": success, "message": message}
