"""
Musikspieler: Blaettern, Abspielen, Hochladen, Loeschen.
"""

from fastapi import APIRouter, Request, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

router = APIRouter()

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


class PlayerModeSelection(BaseModel):
    mode: str


class PracticeSelection(BaseModel):
    filename: str
    repeat: bool = False
    record: bool = False
    take: str = ""


class PracticeRecordSelection(BaseModel):
    record: bool


class PracticeRepeatSelection(BaseModel):
    repeat: bool


@router.get("/api/music/browse")
def music_browse(
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
def music_channel(
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
def music_play_folder(
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
def music_play_file(
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


@router.post("/api/player/mode")
def set_player_mode(auswahl: PlayerModeSelection, request: Request):
    """
    Zwischen Musikspieler und Ueben umschalten.

    Die Karte tauscht dabei ihre Quelle aus - deshalb nicht, solange
    etwas laeuft (siehe Application.set_player_mode).
    """

    application = request.app.state.application

    erfolg, meldung = application.set_player_mode(auswahl.mode)

    return {
        "success": erfolg,
        "message": meldung,
    }


@router.post("/api/practice/start")
def start_practice(auswahl: PracticeSelection, request: Request):
    """Einen Uebungsmix abspielen."""

    application = request.app.state.application

    erfolg, meldung = application.start_practice(
        auswahl.filename,
        auswahl.repeat,
        auswahl.record,
        auswahl.take,
    )

    return {
        "success": erfolg,
        "message": meldung,
    }


@router.post("/api/practice/stop")
def stop_practice(request: Request):
    """
    Das Ueben beenden - samt Mitschnitt, wenn dieser Lauf ihn
    gestartet hat.
    """

    application = request.app.state.application

    return {
        "success": application.stop_practice()
    }


@router.post("/api/practice/record")
def set_practice_record(auswahl: PracticeRecordSelection, request: Request):
    """Den Schalter "Mitschneiden" merken."""

    application = request.app.state.application

    return {
        "success": application.set_practice_record(auswahl.record)
    }


@router.post("/api/practice/repeat")
def set_practice_repeat(auswahl: PracticeRepeatSelection, request: Request):
    """Die Schleife ein- oder ausschalten."""

    application = request.app.state.application

    return {
        "success": application.set_practice_repeat(auswahl.repeat)
    }


@router.post("/api/music/stop")
def music_stop(request: Request):

    application = request.app.state.application

    application.stop_music()

    return {
        "success": True
    }


@router.post("/api/music/pause")
def music_pause(request: Request):

    application = request.app.state.application

    application.pause_music()

    return {
        "success": True
    }


@router.post("/api/music/resume")
def music_resume(request: Request):

    application = request.app.state.application

    application.resume_music()

    return {
        "success": True
    }


@router.post("/api/music/skip")
def music_skip(request: Request):

    application = request.app.state.application

    application.skip_music()

    return {
        "success": True
    }


@router.post("/api/music/seek")
def music_seek(
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
def music_create_folder(
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
def music_delete_file(
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
def music_delete_files(
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


@router.post("/api/music/upload")
def music_upload(
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
