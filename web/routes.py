import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path
from core.audio_file import AudioFile
from audio.models import RecordingInfo
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi import Response
from fastapi import UploadFile, File, Form
from audio.models import DeleteRecordingsRequest
from web.i18n import get_translations

class AudioSelection(BaseModel):
    device_id: str

router = APIRouter()
    
class RecorderChannels(BaseModel):
    channels: int
    
class RecordingSelection(BaseModel):
    filename: str

class SoundcheckSelection(BaseModel):
    filename: str

class MusicFolderSelection(BaseModel):
    path: str
    start_channel: int

class MusicFileSelection(BaseModel):
    path: str
    start_channel: int

class MusicSeekSelection(BaseModel):
    position: float

class MusicFolderCreate(BaseModel):
    path: str
    name: str

class MusicFileDelete(BaseModel):
    path: str

class MusicFilesDelete(BaseModel):
    paths: list[str]

class MusicChannelSelection(BaseModel):
    start_channel: int

class LanguageSelection(BaseModel):
    language: str

class PortSelection(BaseModel):
    port: int

class WifiCredentials(BaseModel):
    ssid: str
    password: str

class BridgeSelection(BaseModel):
    enabled: bool

class PinVerifySelection(BaseModel):
    pin: str

class PinChangeSelection(BaseModel):
    current_pin: str
    new_pin: str

class UsbCopySelection(BaseModel):
    filename: str

class RecordingPrefixSelection(BaseModel):
    prefix: str

class BluetoothPowerSelection(BaseModel):
    enabled: bool

class BluetoothChannelSelection(BaseModel):
    start_channel: int

class BluetoothForgetSelection(BaseModel):
    mac: str

class BluetoothDisconnectSelection(BaseModel):
    mac: str

@router.post("/api/audio/select")
async def audio_select(
    selection: AudioSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.select_audio_device(
        selection.device_id
    )

    return {
        "success": success
    }

@router.post("/api/audio/rescan")
async def rescan_audio_devices(
    request: Request,
):

    application = request.app.state.application

    application.audio_manager.scan()

    return {
        "success": True
    }

@router.get("/", response_class=HTMLResponse)
async def index(request: Request):

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
        },
    )


@router.get("/api/status")
async def status(request: Request):

    application = request.app.state.application

    application.update_status()

    return application.status.model_dump()
    
@router.post("/api/recorder/start")
async def recorder_start(request: Request):

    application = request.app.state.application

    success = application.recorder.start(
        application.record_name_prefix
    )

    return {
        "success": success
    }


@router.post("/api/recorder/stop")
async def recorder_stop(request: Request):

    application = request.app.state.application

    application.recorder.stop()

    return {
        "success": True
    }

@router.post("/api/recorder/channels")
async def recorder_channels(
    selection: RecorderChannels,
    request: Request,
):

    application = request.app.state.application

    success = application.set_record_channels(
        selection.channels
    )

    return {
        "success": success
    }


@router.post("/api/recorder/monitor/start")
async def recorder_monitor_start(request: Request):

    application = request.app.state.application

    success = application.start_level_check()

    return {
        "success": success
    }


@router.post("/api/recorder/monitor/stop")
async def recorder_monitor_stop(request: Request):

    application = request.app.state.application

    application.stop_level_check()

    return {
        "success": True
    }


@router.get("/api/recorder/levels")
async def recorder_levels(request: Request):

    application = request.app.state.application

    return {
        "monitoring": application.recorder.monitoring,
        "levels": application.recorder.levels,
    }

@router.post("/api/recorder/soundcheck/start")
async def soundcheck_start(
    selection: SoundcheckSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.start_soundcheck(
        selection.filename
    )

    return {
        "success": success
    }


@router.post("/api/recorder/soundcheck/stop")
async def soundcheck_stop(request: Request):

    application = request.app.state.application

    application.stop_soundcheck()

    return {
        "success": True
    }


@router.get("/api/music/browse")
async def music_browse(
    request: Request,
    path: str = "",
):

    application = request.app.state.application

    listing = application.music_library.browse(path)

    if listing is None:
        raise HTTPException(
            status_code=404,
            detail="Ordner nicht gefunden.",
        )

    return {
        "path": listing.path,
        "folders": listing.folders,
        "files": listing.files,
    }


@router.post("/api/music/channel")
async def music_channel(
    selection: MusicChannelSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_music_channel_preference(
        selection.start_channel
    )

    return {
        "success": success
    }


@router.post("/api/music/play-folder")
async def music_play_folder(
    selection: MusicFolderSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.play_music_folder(
        selection.path,
        selection.start_channel,
    )

    return {
        "success": success
    }


@router.post("/api/music/play-file")
async def music_play_file(
    selection: MusicFileSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.play_music_file(
        selection.path,
        selection.start_channel,
    )

    return {
        "success": success
    }


@router.post("/api/music/stop")
async def music_stop(request: Request):

    application = request.app.state.application

    application.stop_music()

    return {
        "success": True
    }


@router.post("/api/music/pause")
async def music_pause(request: Request):

    application = request.app.state.application

    application.pause_music()

    return {
        "success": True
    }


@router.post("/api/music/resume")
async def music_resume(request: Request):

    application = request.app.state.application

    application.resume_music()

    return {
        "success": True
    }


@router.post("/api/music/skip")
async def music_skip(request: Request):

    application = request.app.state.application

    application.skip_music()

    return {
        "success": True
    }


@router.post("/api/music/seek")
async def music_seek(
    selection: MusicSeekSelection,
    request: Request,
):

    application = request.app.state.application

    application.seek_music(
        selection.position
    )

    return {
        "success": True
    }


@router.post("/api/music/create-folder")
async def music_create_folder(
    selection: MusicFolderCreate,
    request: Request,
):

    application = request.app.state.application

    success = application.create_music_folder(
        selection.path,
        selection.name,
    )

    return {
        "success": success
    }


@router.post("/api/music/delete")
async def music_delete_file(
    selection: MusicFileDelete,
    request: Request,
):

    application = request.app.state.application

    success = application.delete_music_file(
        selection.path
    )

    return {
        "success": success
    }


@router.post("/api/music/delete-multi")
async def music_delete_files(
    selection: MusicFilesDelete,
    request: Request,
):

    application = request.app.state.application

    deleted = application.delete_music_files(
        selection.paths
    )

    return {
        "deleted": deleted,
        "count": len(deleted),
    }


@router.post("/api/system/shutdown")
async def system_shutdown(request: Request):

    application = request.app.state.application

    success = application.shutdown_system()

    return {
        "success": success
    }


@router.post("/api/system/restart")
async def system_restart(request: Request):

    application = request.app.state.application

    success = application.restart_service()

    return {
        "success": success
    }


@router.get("/api/settings")
async def get_settings(request: Request):

    application = request.app.state.application

    wlan = application.get_wlan_status()

    return {
        "language": application.config.data.application.language,
        "port": application.config.data.server.port,
        "record_name_prefix": application.record_name_prefix,
        "wlan": wlan,
        "pin_protected": application.pin_protection_enabled(),
    }


@router.get("/api/settings/pin/status")
async def get_settings_pin_status(request: Request):

    application = request.app.state.application

    return {
        "protected": application.pin_protection_enabled()
    }


@router.post("/api/settings/pin/verify")
async def verify_settings_pin(
    selection: PinVerifySelection,
    request: Request,
):

    application = request.app.state.application

    success = application.verify_settings_pin(selection.pin)

    return {
        "success": success
    }


@router.post("/api/settings/pin/change")
async def change_settings_pin(
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
async def set_recording_prefix(
    selection: RecordingPrefixSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_record_name_prefix(selection.prefix)

    return {
        "success": success
    }


@router.post("/api/settings/language")
async def set_language(
    selection: LanguageSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_language(selection.language)

    return {
        "success": success
    }


@router.post("/api/settings/port")
async def set_port(
    selection: PortSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_port(selection.port)

    return {
        "success": success
    }


@router.post("/api/settings/wifi/home")
async def set_home_wifi(
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
async def set_ap_wifi(
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


@router.post("/api/settings/bridge")
async def set_bridge(
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


@router.get("/api/bluetooth/status")
async def bluetooth_status(request: Request):

    application = request.app.state.application

    return application.get_bluetooth_status()


@router.post("/api/bluetooth/power")
async def bluetooth_power(
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
async def bluetooth_pair(request: Request):

    application = request.app.state.application

    success, message = application.start_bluetooth_pairing()

    return {
        "success": success,
        "message": message,
    }


@router.post("/api/bluetooth/forget")
async def bluetooth_forget(
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
async def bluetooth_disconnect(
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
async def bluetooth_channel(
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


@router.post("/api/music/upload")
async def music_upload(
    request: Request,
    path: str = Form(""),
    files: list[UploadFile] = File(...),
):

    application = request.app.state.application

    uploaded = []

    for upload in files:

        filename = application.upload_music_file(
            path,
            upload.filename,
            upload.file,
        )

        if filename is not None:
            uploaded.append(filename)

    return {
        "uploaded": uploaded,
        "count": len(uploaded),
    }


def get_recording_info(
    recording: Path,
) -> RecordingInfo:
    """Liest die Informationen einer Aufnahme."""

    audio = AudioFile(recording)

    audio.open()

    return RecordingInfo(
        filename=recording.name,
        channels=audio.channels,
        duration=audio.duration,
        size=recording.stat().st_size,
        sample_rate=audio.sample_rate,
        bits_per_sample=audio.bits_per_sample,
    )
       
@router.post("/api/recording/info")
async def recording_info(
    selection: RecordingSelection,
    request: Request,
):

    application = request.app.state.application

    application.logger.info(
        "Ausgewählte Datei: %s",
        selection.filename,
    )

    recording = (
        application.recorder.writer.directory /
        selection.filename
    )
    
    if not recording.exists():

        return {
            "success": False
        }
        
    audio = AudioFile(recording)

    audio.open()

    application.logger.info(
        "AudioFile: %d Ch | %d Hz | %d Bit | %.1f s",
        audio.channels,
        audio.sample_rate,
        audio.bits_per_sample,
        audio.duration,
    )

    return {

        "success": True,

        "filename": recording.name,

        "size": recording.stat().st_size,

        "channels": audio.channels,

        "sample_rate": audio.sample_rate,

        "bits_per_sample": audio.bits_per_sample,

        "duration": audio.duration,

    }

@router.get("/api/recordings")
async def recordings(request: Request):

    application = request.app.state.application

    items = []

    for recording in sorted(
        application.recorder.writer.directory.glob("*.w64"),
        reverse=True,
    ):
        items.append(
            get_recording_info(recording)
        )

    return items
    
@router.get("/api/audio/devices")
async def audio_devices(request: Request):

    application = request.app.state.application

    application.audio_manager.scan()

    devices = []

    for device in application.audio_manager.get_devices():
        application.logger.info(
            "API: %s | selected=%s",
            device.id,
            application.selected_audio_device.id
            if application.selected_audio_device
            else "None",
        )

        devices.append(
            {
                "id": device.id,
                "name": device.name,
                "description": device.description,
                "channels": device.channels,
                "sample_rate": device.sample_rate,
                "sample_bits": device.sample_bits,
                "formats": device.formats,
            }
        )

    return devices
    
@router.get("/api/recordings/{filename}")
async def download_recording(
    filename: str,
    request: Request,
):
    application = request.app.state.application

    recording = (
        application.recorder.writer.directory
        / filename
    )

    if not recording.exists():
        raise HTTPException(
            status_code=404,
            detail="Aufnahme nicht gefunden.",
        )

    return FileResponse(
        path=recording,
        filename=recording.name,
        media_type="application/octet-stream",
    )
    
@router.delete("/api/recordings/{filename}")
async def delete_recording(
    filename: str,
    request: Request,
):
    application = request.app.state.application

    recording = (
        application.recorder.writer.directory
        / filename
    )

    if not recording.exists():
        raise HTTPException(
            status_code=404,
            detail="Aufnahme nicht gefunden.",
        )

    recording.unlink()

    return Response(status_code=204)
    
@router.post("/api/recordings/delete")
async def delete_recordings(
    request_data: DeleteRecordingsRequest,
    request: Request,
):
    application = request.app.state.application

    directory = application.recorder.writer.directory

    deleted = []

    for filename in request_data.filenames:

        recording = directory / filename

        if recording.exists():
            recording.unlink()
            deleted.append(filename)

    return {
        "deleted": deleted,
        "count": len(deleted),
    }


@router.get("/api/usb/status")
async def usb_status(request: Request):

    application = request.app.state.application

    return {
        "connected": application.usb_storage.connected
    }


@router.post("/api/recordings/copy_to_usb")
async def copy_recording_to_usb(
    selection: UsbCopySelection,
    request: Request,
):

    application = request.app.state.application

    success, already_exists = application.copy_recording_to_usb(
        selection.filename
    )

    return {
        "success": success,
        "already_exists": already_exists,
    }
