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
