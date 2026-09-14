"""
Aufnehmen, Soundcheck, Pegel - und alles, was mit den
fertigen Dateien passiert.
"""

import json
import shutil
import tempfile

from fastapi import APIRouter, Request, HTTPException, Response, UploadFile, File, Form
from audio.models import DeleteRecordingsRequest
from audio.models import RecordingInfo
from core.audio_file import AudioFile
from core.recording_kind import kind_from_filename
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel

router = APIRouter()

    
class RecorderStartChannel(BaseModel):
    start_channel: int


class RecorderChannels(BaseModel):
    channels: int


    
class RecordingSelection(BaseModel):
    filename: str


class SoundcheckSelection(BaseModel):
    filename: str


class UsbCopySelection(BaseModel):
    filename: str


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
        kind=kind_from_filename(recording.name),
    )


    
@router.post("/api/recorder/start")
def recorder_start(request: Request):

    application = request.app.state.application

    success = application.start_recording()

    return {
        "success": success
    }


@router.post("/api/recorder/stop")
def recorder_stop(request: Request):

    application = request.app.state.application

    application.recorder.stop()

    return {
        "success": True
    }


@router.post("/api/recorder/channels")
def recorder_channels(
    selection: RecorderChannels,
    request: Request,
):

    application = request.app.state.application

    #
    # Von Hand gewaehlt: Ab jetzt fasst XRack die Kanalzahl beim
    # Geraetewechsel nicht mehr von sich aus an.
    #
    success = application.set_record_channels(
        selection.channels,
        manuell=True,
    )

    return {
        "success": success
    }


@router.post("/api/recorder/start-channel")
def recorder_start_channel(
    selection: RecorderStartChannel,
    request: Request,
):
    """
    Der erste aufgenommene Kanal.

    Aufgenommen wird ein Fenster, nicht immer der Anfang - am X32
    vielleicht nur die Kanaele 17-24, beim Ueben nur das eigene
    Instrument.
    """

    application = request.app.state.application

    success = application.set_record_start_channel(
        selection.start_channel
    )

    return {
        "success": success
    }


@router.post("/api/recorder/monitor/start")
def recorder_monitor_start(request: Request):

    application = request.app.state.application

    success = application.start_level_check()

    return {
        "success": success
    }


@router.post("/api/recorder/monitor/stop")
def recorder_monitor_stop(request: Request):

    application = request.app.state.application

    application.stop_level_check()

    return {
        "success": True
    }


@router.get("/api/recorder/levels")
def recorder_levels(request: Request):

    application = request.app.state.application

    return {
        "monitoring": application.recorder.monitoring,
        "levels": application.recorder.levels,
    }


@router.post("/api/recorder/soundcheck/start")
def soundcheck_start(
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
def soundcheck_stop(request: Request):

    application = request.app.state.application

    application.stop_soundcheck()

    return {
        "success": True
    }


       
@router.post("/api/recording/info")
def recording_info(
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

        "kind": kind_from_filename(recording.name),

    }


@router.get("/api/recordings")
def recordings(request: Request):

    application = request.app.state.application

    items = []

    for recording in sorted(
        application.recorder.writer.directory.glob("*.w64"),
        reverse=True,
    ):
        #
        # Eine einzelne beschädigte/keine echte Wave64-Datei (z.B.
        # durch einen fehlgeschlagenen Upload oder eine abgebrochene
        # Aufnahme) darf nicht die gesamte Liste zum Absturz bringen.
        #
        try:
            items.append(
                get_recording_info(recording)
            )
        except Exception as exc:
            application.logger.warning(
                "Aufnahme %s übersprungen (keine gültige Wave64-Datei): %s",
                recording.name,
                exc,
            )

    return items


    
@router.get("/api/recordings/{filename}")
def download_recording(
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
def delete_recording(
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
def delete_recordings(
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


@router.post("/api/recordings/upload")
def upload_recordings(
    request: Request,
    files: list[UploadFile] = File(...),
):
    """
    Lädt .w64-Aufnahmen ins Aufnahmeverzeichnis hoch - z.B. um eine
    zuvor gesicherte Aufnahme wieder verfügbar zu machen. Andere
    Formate werden abgelehnt, da die Aufnahmen-Karte (Liste,
    Soundcheck-Wiedergabe) ausschließlich XRacks eigenes Wave64-
    Format versteht (siehe reader/w64_reader.py).
    """

    application = request.app.state.application

    directory = application.recorder.writer.directory

    directory.mkdir(parents=True, exist_ok=True)

    uploaded = []

    for upload in files:

        #
        # Nur den reinen Dateinamen übernehmen (kein Pfad aus dem
        # Upload verwenden) - wie bei /api/music/upload.
        #
        filename = Path(upload.filename).name

        if not filename or Path(filename).suffix.lower() != ".w64":
            continue

        destination = directory / filename

        with destination.open("wb") as target:
            shutil.copyfileobj(upload.file, target)

        #
        # Header sofort prüfen, statt eine kaputte/keine echte
        # Wave64-Datei stillschweigend im Verzeichnis liegen zu
        # lassen, wo sie erst später (z.B. beim Laden der Liste)
        # auffallen würde.
        #
        try:
            AudioFile(destination).open()
        except Exception as exc:
            application.logger.warning(
                "Hochgeladene Datei %s ist keine gültige Wave64-Datei, "
                "wird verworfen: %s",
                filename,
                exc,
            )
            destination.unlink()
            continue

        uploaded.append(filename)

    return {
        "uploaded": uploaded,
    }


@router.post("/api/recordings/combine")
def combine_recordings(
    request: Request,
    name: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    start_channel: int = Form(1),
    sources: str = Form(""),
):
    """
    Übungsmix: legt mehrere Stereo-Stems zusammen (siehe
    core/stem_combiner.py). Die Reihenfolge bestimmt die
    Kanalzuordnung (Quelle 1 -> Kanal 1+2, ...).

    Eine Quelle kann von zwei Orten kommen:

      - HOCHGELADEN vom Rechner oder Tablet. Sie landet in einem
        Scratch-Verzeichnis und wird nach getaner Arbeit gelöscht.
      - Aus der MUSIKBIBLIOTHEK, also von einer Datei, die schon auf
        dem Gerät liegt. Seit die Stems auch vom USB-Stick kommen
        können, ist das der übliche Weg - sie dann durch den Browser
        wieder hochzuladen wäre genau der Umweg über die Leitung, den
        der Stick vermeiden sollte. Diese Datei wird NICHT gelöscht.

    `sources` sagt, in welcher REIHENFOLGE beides zusammengehört - als
    JSON-Liste aus {"kind": "upload"} und
    {"kind": "library", "path": "Proben/klick.wav"}. Ohne die Angabe
    bliebe nur zu raten, ob der Upload vor oder hinter der Datei aus
    der Bibliothek liegt, und die Stems lägen auf den falschen Kanälen.

    Fehlt `sources` ganz, gilt der alte Weg: alles Uploads, in ihrer
    Reihenfolge.
    """

    application = request.app.state.application

    scratch_dir = Path(tempfile.mkdtemp(prefix="xrack_stem_combine_"))

    hochgeladen = []

    for index, upload in enumerate(files):

        suffix = Path(upload.filename or "").suffix or ".wav"

        destination = scratch_dir / f"stem_{index}{suffix}"

        with destination.open("wb") as target:
            shutil.copyfileobj(upload.file, target)

        hochgeladen.append(destination)

    def aufraeumen_und_melden(meldung: str) -> dict:

        for pfad in hochgeladen:
            pfad.unlink(missing_ok=True)

        try:
            scratch_dir.rmdir()
        except OSError:
            pass

        return {"success": False, "message": meldung}

    if not sources:
        reihenfolge = [{"kind": "upload"} for _ in hochgeladen]

    else:

        try:
            reihenfolge = json.loads(sources)

        except ValueError:
            return aufraeumen_und_melden("Die Reihenfolge ist unlesbar.")

        if not isinstance(reihenfolge, list):
            return aufraeumen_und_melden("Die Reihenfolge ist unlesbar.")

    file_paths = []

    offene_uploads = list(hochgeladen)

    for eintrag in reihenfolge:

        art = (eintrag or {}).get("kind") if isinstance(eintrag, dict) else None

        if art == "upload":

            if not offene_uploads:
                return aufraeumen_und_melden(
                    "Es fehlt eine hochgeladene Datei."
                )

            file_paths.append(offene_uploads.pop(0))

        elif art == "library":

            #
            # Aufgeloest wird gegen die Bibliothek, nicht gegen das
            # Dateisystem: Was vom Browser kommt, darf nicht
            # bestimmen, WO gelesen wird.
            #
            pfad = application.music_library.resolve(
                str(eintrag.get("path", ""))
            )

            if pfad is None or not pfad.is_file():
                return aufraeumen_und_melden(
                    "Eine Datei aus der Bibliothek gibt es nicht."
                )

            file_paths.append(pfad)

        else:
            return aufraeumen_und_melden("Unbekannte Quelle.")

    success, message = application.start_stem_combine(
        name,
        file_paths,
        start_channel,
        #
        # Weggeraeumt wird nur, was hochgeladen wurde.
        #
        temporaer=hochgeladen,
    )

    if not success:
        return aufraeumen_und_melden(message)

    return {
        "success": success,
        "message": message,
    }


class TakeZusammenfuehren(BaseModel):
    mix: str
    take: str
    name: str


@router.post("/api/recordings/combine-take")
def combine_take(
    auswahl: TakeZusammenfuehren,
    request: Request,
):
    """
    Schreibt aus einem Übungsmix und einem seiner Mitschnitte eine neue
    Datei (Stufe 5).

    Anders als /api/recordings/combine werden hier keine Dateien
    hochgeladen - beide liegen schon auf dem Gerät. Den Fortschritt
    liefert dieselbe Statusabfrage, denn es ist dieselbe Arbeit: Am
    Ende steht ein Übungsmix.
    """

    application = request.app.state.application

    success, message = application.start_take_zusammenfuehren(
        auswahl.mix,
        auswahl.take,
        auswahl.name,
    )

    return {
        "success": success,
        "message": message,
    }


@router.get("/api/recordings/combine/status")
def combine_recordings_status(request: Request):

    application = request.app.state.application

    return application.get_stem_combine_status()


@router.post("/api/recordings/copy_to_usb")
def copy_recording_to_usb(
    selection: UsbCopySelection,
    request: Request,
):

    application = request.app.state.application

    success, status = application.start_usb_copy(
        selection.filename
    )

    return {
        "success": success,
        "status": status,
    }
