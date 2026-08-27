"""
Fader, Stummschaltung und Kopplung am Mischpult (OSC).
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

class PairFaderSelection(BaseModel):
    #
    # Erster Kanal des Stereopaars (immer ungerade).
    #
    start: int
    #
    # None bedeutet "Fader ganz zu" - als JSON gibt es kein -inf.
    #
    db: float | None


class PairMuteSelection(BaseModel):
    start: int
    muted: bool


class PairLinkSelection(BaseModel):
    start: int
    linked: bool


class ConsoleHostSelection(BaseModel):
    #
    # Leer heisst: wieder automatisch suchen.
    #
    ip: str = ""


class SnapshotSelection(BaseModel):
    index: int


class MuteSelection(BaseModel):
    channel: int
    muted: bool


class FaderSelection(BaseModel):
    channel: int
    #
    # None bedeutet "Fader ganz zu" (-unendlich) - als JSON gibt es
    # kein -inf.
    #
    db: float | None


@router.get("/api/console/snapshots")
def console_snapshots(request: Request, force: bool = False):
    """
    Die gespeicherten Snapshots des Pults.
    """

    return request.app.state.application.get_console_snapshots(force=force)


@router.post("/api/console/snapshot/load")
def load_console_snapshot(auswahl: SnapshotSelection, request: Request):
    """
    Ruft einen Snapshot auf. Die Rückfrage davor macht die
    Oberfläche - hier wird nur noch ausgeführt.
    """

    success, message = request.app.state.application.load_console_snapshot(
        auswahl.index
    )

    return {"success": success, "message": message}


@router.post("/api/console/search")
def search_console(request: Request):
    """
    Sucht das Mischpult neu (siehe Application.search_console).
    """

    return request.app.state.application.search_console()


@router.get("/api/console/pair")
def console_pair(request: Request, start: int):
    """
    Pegel und Stummschaltung des Stereopaars, das im Musikspieler oder
    bei Bluetooth gewählt ist - damit man dafür nicht zur Fader-Karte
    scrollen muss.
    """

    application = request.app.state.application

    return application.get_console_pair(start)


@router.post("/api/console/pair/fader")
def console_pair_fader(
    selection: PairFaderSelection,
    request: Request,
):

    application = request.app.state.application

    return {
        "success": application.set_console_pair_fader(
            selection.start, selection.db
        )
    }


@router.post("/api/console/pair/mute")
def console_pair_mute(
    selection: PairMuteSelection,
    request: Request,
):

    application = request.app.state.application

    return {
        "success": application.set_console_pair_mute(
            selection.start, selection.muted
        )
    }


@router.post("/api/console/pair/link")
def console_pair_link(
    selection: PairLinkSelection,
    request: Request,
):
    """
    Koppelt das Kanalpaar am Pult oder hebt die Kopplung auf.
    """

    application = request.app.state.application

    return {
        "success": application.set_console_pair_link(
            selection.start, selection.linked
        )
    }


@router.post("/api/console/host")
def console_host(
    selection: ConsoleHostSelection,
    request: Request,
):
    """
    Trägt die IP des Mischpults von Hand ein - für den Fall, dass Pult
    und Pi zusammen an einem Router hängen und der Suchlauf nichts
    findet. Ein leerer Wert schaltet zurück auf die automatische Suche.
    """

    application = request.app.state.application

    success, message = application.set_console_host(selection.ip)

    return {
        "success": success,
        "message": message,
    }


@router.get("/api/console/channels")
def console_channels(request: Request):
    """
    Kanalnamen und Faderstellungen des Mischpults für die Fader-Karte.

    Wird vom Frontend nur abgefragt, solange die Fader entsperrt sind -
    im gesperrten Normalfall entsteht dadurch gar kein Netzverkehr zum
    Pult.
    """

    application = request.app.state.application

    return application.get_console_channels()


@router.post("/api/console/fader")
def set_console_fader(
    selection: FaderSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_console_fader(
        selection.channel,
        selection.db,
    )

    return {
        "success": success,
    }


@router.post("/api/console/mute")
def set_console_mute(
    selection: MuteSelection,
    request: Request,
):

    application = request.app.state.application

    success = application.set_console_mute(
        selection.channel,
        selection.muted,
    )

    return {
        "success": success,
    }
