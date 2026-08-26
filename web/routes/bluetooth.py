"""
Bluetooth-Zuspielung vom Handy.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

class BluetoothPowerSelection(BaseModel):
    enabled: bool


class BluetoothChannelSelection(BaseModel):
    start_channel: int


class BluetoothForgetSelection(BaseModel):
    mac: str


class BluetoothDisconnectSelection(BaseModel):
    mac: str


@router.get("/api/bluetooth/status")
def bluetooth_status(request: Request):

    application = request.app.state.application

    return application.get_bluetooth_status()


@router.post("/api/bluetooth/power")
def bluetooth_power(
    selection: BluetoothPowerSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.set_bluetooth_power(
        selection.enabled
    )

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/bluetooth/pair")
def bluetooth_pair(request: Request):

    application = request.app.state.application

    success, message = application.start_bluetooth_pairing()

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/bluetooth/forget")
def bluetooth_forget(
    selection: BluetoothForgetSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.forget_bluetooth_device(
        selection.mac
    )

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/bluetooth/disconnect")
def bluetooth_disconnect(
    selection: BluetoothDisconnectSelection,
    request: Request,
):

    application = request.app.state.application

    success, message = application.disconnect_bluetooth_device(
        selection.mac
    )

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/bluetooth/channel")
def bluetooth_channel(
    selection: BluetoothChannelSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_bluetooth_channel_preference(
        selection.start_channel
    )

    return {
        "success": success
    }
