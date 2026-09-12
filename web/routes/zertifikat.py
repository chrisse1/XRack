"""
Das TLS-Zertifikat: sichern, einspielen, neu erzeugen.

Diese Endpunkte sind die einzigen, die die PIN wirklich auf dem
Server pruefen (siehe Application.zertifikat_erlaubt). Ueberall sonst
ist die PIN ein Riegel vor dem Einstellungen-Dialog; hier geht es um
den privaten Schluessel, und der ist eine andere Sache.
"""

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter()


class ZertifikatPin(BaseModel):
    pin: str = ""


class ZertifikatSicherung(BaseModel):
    pin: str = ""
    password: str = ""


@router.get("/api/tls")
def get_tls(request: Request):
    """Zustand des Zertifikats - ohne PIN, es steht nichts Geheimes drin."""

    application = request.app.state.application

    return application.get_zertifikat()


@router.get("/api/tls/certificate")
def download_tls(request: Request):
    """
    Das Zertifikat als Datei - zum Einrichten auf einem Geraet.

    Ohne PIN, mit Absicht: Hier geht nur der oeffentliche Teil heraus,
    und der steht bei jedem Verbindungsaufbau ohnehin auf der Leitung.
    Wer ihn auf seinem Tablet in den Zertifikatsspeicher legt, wird die
    Rueckfrage des Browsers ganz los.
    """

    application = request.app.state.application

    daten, name = application.zertifikat_datei()

    if daten is None:
        return {
            "success": False,
            "message": name,
        }

    return Response(
        content=daten,
        media_type="application/x-x509-ca-cert",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
        },
    )


@router.post("/api/tls/renew")
def renew_tls(auswahl: ZertifikatPin, request: Request):
    """Ein neues Zertifikat fuer die aktuellen Namen."""

    application = request.app.state.application

    erfolg, meldung = application.zertifikat_erneuern(auswahl.pin)

    return {
        "success": erfolg,
        "message": meldung,
    }


@router.post("/api/tls/export")
def export_tls(auswahl: ZertifikatSicherung, request: Request):
    """
    Das Zertifikat als verschluesselte Datei.

    Bei einem Fehlschlag kommt JSON zurueck, bei Erfolg die Datei -
    deshalb prueft die Oberflaeche den Inhaltstyp und nicht bloss den
    Statuscode.
    """

    application = request.app.state.application

    daten, meldung = application.zertifikat_sichern(
        auswahl.pin,
        auswahl.password,
    )

    if daten is None:
        return {
            "success": False,
            "message": meldung,
        }

    return Response(
        content=daten,
        media_type="application/x-pkcs12",
        headers={
            "Content-Disposition":
                'attachment; filename="xrack-zertifikat.p12"',
            #
            # Der Schluessel gehoert in keinen Zwischenspeicher.
            #
            "Cache-Control": "no-store",
        },
    )


@router.post("/api/tls/import")
async def import_tls(
    request: Request,
    file: UploadFile = File(...),
    pin: str = Form(""),
    password: str = Form(""),
):
    """Ein gesichertes Zertifikat uebernehmen."""

    application = request.app.state.application

    daten = await file.read()

    erfolg, meldung = application.zertifikat_einspielen(
        pin,
        password,
        daten,
    )

    return {
        "success": erfolg,
        "message": meldung,
    }
