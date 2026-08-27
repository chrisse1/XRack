"""
Einstellungen-Modal: Sprache, Port, WLAN, PIN, Netzwege.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

class LanguageSelection(BaseModel):
    language: str


class PortSelection(BaseModel):
    port: int


class SampleRateSelection(BaseModel):
    sample_rate: int


class WifiCountry(BaseModel):
    """Funkregion als zweistelliger ISO-Laendercode."""

    country: str


class WifiCredentials(BaseModel):
    ssid: str
    password: str


class BridgeSelection(BaseModel):
    enabled: bool


class ConsoleAccessSelection(BaseModel):
    enabled: bool


class FadersAutolockSelection(BaseModel):
    enabled: bool
    seconds: int


class PinVerifySelection(BaseModel):
    pin: str


class PinChangeSelection(BaseModel):
    current_pin: str
    new_pin: str


class RecordingPrefixSelection(BaseModel):
    prefix: str


@router.get("/api/settings")
def get_settings(request: Request):

    application = request.app.state.application

    wlan = application.get_wlan_status()

    console = application.get_console_host()

    return {
        "language": application.config.data.application.language,
        "sample_rate": application.mixer_sample_rate,
        "port": application.config.data.server.port,
        "record_name_prefix": application.record_name_prefix,
        "wlan": wlan,
        "pin_protected": application.pin_protection_enabled(),
        #
        # Leer = automatisch (Vergabeliste oder Suchlauf).
        #
        "console_ip_manual": console["manual"],
        #
        # Welche IP tatsaechlich benutzt wird und woher sie stammt.
        #
        "console_host": console["host"],
        "console_host_source": console["source"],
        "faders_autolock": application.get_faders_autolock(),
    }


@router.get("/api/settings/pin/status")
def get_settings_pin_status(request: Request):

    application = request.app.state.application

    return {
        "protected": application.pin_protection_enabled()
    }


@router.post("/api/settings/pin/verify")
def verify_settings_pin(
    selection: PinVerifySelection,
    request: Request,
):

    application = request.app.state.application

    success = application.verify_settings_pin(selection.pin)

    return {
        "success": success
    }


@router.post("/api/settings/pin/change")
def change_settings_pin(
    selection: PinChangeSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_settings_pin(
        selection.current_pin,
        selection.new_pin,
    )

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/settings/recording")
def set_recording_prefix(
    selection: RecordingPrefixSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_record_name_prefix(selection.prefix)

    return {
        "success": success
    }


@router.post("/api/settings/language")
def set_language(
    selection: LanguageSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_language(selection.language)

    return {
        "success": success
    }


@router.post("/api/settings/sample_rate")
def set_sample_rate(
    selection: SampleRateSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_mixer_sample_rate(selection.sample_rate)

    return {
        "success": success
    }


@router.post("/api/settings/port")
def set_port(
    selection: PortSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_port(selection.port)

    return {
        "success": success
    }


@router.post("/api/settings/wifi/home")
def set_home_wifi(
    credentials: WifiCredentials,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_home_wifi(
        credentials.ssid,
        credentials.password,
    )

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/settings/wifi/ap")
def set_ap_wifi(
    credentials: WifiCredentials,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_ap_wifi(
        credentials.ssid,
        credentials.password,
    )

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/settings/wifi/country")
def set_wifi_country(
    auswahl: WifiCountry,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_wifi_country(auswahl.country)

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/settings/bridge")
def set_bridge(
    selection: BridgeSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_bridge(
        selection.enabled
    )

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/settings/console_access")
def set_console_access(
    selection: ConsoleAccessSelection,
    request: Request,
):
    """
    Schaltet "Konsole aus dem Heimnetz erreichbar machen" - also die
    Ethernet-Freigabe samt Portweiterleitung. Ersetzt die früher
    getrennten Endpunkte /api/settings/share und
    /api/settings/port_forward.
    """

    application = request.app.state.application

    success, message = application.set_console_access(
        selection.enabled
    )

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/settings/faders-autolock")
def settings_faders_autolock(
    selection: FadersAutolockSelection,
    request: Request,
):
    """
    Stellt ein, ob und nach wie vielen Sekunden Ruhe sich die
    Fader-Karte wieder von selbst sperrt.
    """

    application = request.app.state.application

    success, message = application.set_faders_autolock(
        selection.enabled, selection.seconds
    )

    return {
        "success": success,
        "message": message,
        "faders_autolock": application.get_faders_autolock(),
    }
