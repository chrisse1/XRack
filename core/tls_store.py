"""
Das TLS-Zertifikat: ansehen, sichern, einspielen, neu erzeugen.

Warum es das gibt: XRack spricht HTTPS mit einem selbstsignierten
Zertifikat, und der Browser fragt deshalb einmal nach, bevor er die
Seite zeigt. Das ist zu ertragen - einmal. Wer zwei oder drei Racks
betreibt (Proberaum, Studio, Anlage), bestätigt aber bei jedem
einzeln, und mit jeder Neuinstallation wieder.

Die Abhilfe ist nicht, ein Zertifikat mitzuliefern. Dann läge der
private Schlüssel öffentlich, und jeder im selben WLAN könnte sich
lautlos als XRack ausgeben - samt der PIN, die jemand eintippt. Die
Abhilfe ist, dass der NUTZER sein Zertifikat von seinem einen Rack
auf sein anderes trägt: Zusammen mit dem gemeinsamen Namen (siehe
core/mdns_alias.py) ist das für den Browser dann ein Ziel mit einem
Zertifikat - eine Bestätigung für alle Racks.

Unterwegs ist die Datei mit einem Kennwort verschlüsselt (PKCS#12,
AES-256). Ein privater Schlüssel, der ungeschützt über ein Tablet
oder einen Stick wandert, wäre derselbe Fehler wie der mitgelieferte,
nur langsamer.

Gearbeitet wird mit dem openssl-Programm, nicht mit einer
Python-Bibliothek: install.sh erzeugt das Zertifikat schon damit, es
ist auf jedem Raspberry Pi OS vorhanden, und XRack spart sich eine
Abhängigkeit, die auf dem Pi gebaut werden müsste.
"""

import logging
import os
import re
import subprocess
import tempfile

from datetime import datetime, timezone
from pathlib import Path


#
# Kürzer ergibt keinen Schutz. Die Datei enthält den Schlüssel, mit
# dem sich jemand als dieses Rack ausgeben kann - ein vierstelliges
# Etwas wäre in Minuten durchprobiert.
#
MINDESTKENNWORT = 8

#
# Zehn Jahre, wie install.sh. Ein Zertifikat, das mitten in einer
# Spielzeit abläuft, ist genau das, was niemand gebrauchen kann.
#
LAUFZEIT_TAGE = 3650

#
# Diese Namen trägt jedes Zertifikat, zusätzlich zu den übergebenen.
#
IMMER = ("localhost",)
IMMER_IP = ("127.0.0.1",)


class TlsStore:
    """
    Zertifikat und Schlüssel an ihrem Platz (config/server.ssl_*).

    Jeder schreibende Schritt prüft ERST vollständig und schreibt
    DANN: Ein halb eingespieltes Paar wäre der schlimmste Ausgang -
    der Dienst käme nach dem nächsten Neustart nicht mehr hoch, und
    das Rack wäre nur noch mit Tastatur und Bildschirm zu erreichen.
    """

    def __init__(self, zertifikat: Path, schluessel: Path):

        self.logger = logging.getLogger("XRack")

        self.zertifikat = Path(zertifikat)
        self.schluessel = Path(schluessel)

    # ----------------------------------------------------------------
    # Hilfsmittel
    # ----------------------------------------------------------------

    @property
    def marke(self) -> Path:
        """
        Zeigt an, dass das Zertifikat eingespielt wurde.

        Eine Datei und kein Eintrag in state.json, weil install.sh
        danach sehen muss - in bash, ohne JSON zu lesen. Ohne sie
        würde der nächste Installationslauf das übertragene
        Zertifikat wegwerfen, weil es nicht auf DIESEN Rechnernamen
        lautet.
        """

        return self.zertifikat.with_name(self.zertifikat.name + ".imported")

    def _openssl(self, *args: str, eingabe: bytes | None = None):
        """openssl aufrufen, ohne dass etwas Geheimes in der Prozessliste steht."""

        return subprocess.run(
            ["openssl", *args],
            input=eingabe,
            capture_output=True,
            timeout=30,
        )

    @staticmethod
    def _pem_schneiden(daten: bytes, anfang: bytes) -> bytes:
        """
        Alles vor dem ersten PEM-Block wegwerfen.

        openssl schreibt beim Auspacken einer PKCS#12-Datei noch
        "Bag Attributes" davor. Die meisten Leser überspringen das,
        aber "die meisten" reicht nicht für eine Datei, an der der
        Start des Dienstes hängt.
        """

        stelle = daten.find(anfang)

        return daten[stelle:] if stelle > 0 else daten

    # ----------------------------------------------------------------
    # Ansehen
    # ----------------------------------------------------------------

    def vorhanden(self) -> bool:

        return self.zertifikat.is_file() and self.schluessel.is_file()

    def namen(self, pfad: Path | None = None) -> list[str]:
        """Für welche Namen und Adressen das Zertifikat gilt."""

        pfad = pfad or self.zertifikat

        if not pfad.is_file():
            return []

        lauf = self._openssl("x509", "-in", str(pfad), "-noout", "-text")

        if lauf.returncode != 0:
            return []

        text = lauf.stdout.decode("utf-8", "replace")

        gefunden = re.findall(r"(?:DNS|IP Address):([^,\s]+)", text)

        #
        # Reihenfolge behalten, Doppelte weg - die Liste steht so in
        # der Oberfläche.
        #
        eindeutig = []

        for name in gefunden:
            if name not in eindeutig:
                eindeutig.append(name)

        return eindeutig

    def laeuft_bis(self, pfad: Path | None = None) -> datetime | None:

        pfad = pfad or self.zertifikat

        if not pfad.is_file():
            return None

        lauf = self._openssl("x509", "-in", str(pfad), "-noout", "-enddate")

        if lauf.returncode != 0:
            return None

        roh = lauf.stdout.decode("utf-8", "replace").strip()

        if not roh.startswith("notAfter="):
            return None

        try:
            return datetime.strptime(
                roh[len("notAfter="):], "%b %d %H:%M:%S %Y %Z"
            ).replace(tzinfo=timezone.utc)

        except ValueError:
            return None

    def zustand(self) -> dict:
        """Was die Oberfläche über das Zertifikat wissen muss."""

        if not self.vorhanden():
            return {
                "present": False,
                "imported": False,
                "installable": False,
                "names": [],
                "valid_until": "",
                "days_left": 0,
            }

        ende = self.laeuft_bis()

        rest = 0

        if ende is not None:
            rest = max(
                0,
                int((ende - datetime.now(timezone.utc)).total_seconds() // 86400),
            )

        return {
            "present": True,
            "imported": self.marke.exists(),
            "installable": self.installierbar(),
            "names": self.namen(),
            "valid_until": ende.strftime("%Y-%m-%d") if ende else "",
            "days_left": rest,
        }

    def installierbar(self, pfad: Path | None = None) -> bool:
        """
        Laesst sich das Zertifikat auf einem Geraet in den
        Zertifikatsspeicher legen?

        Dazu muss es sich selbst als Zertifizierungsstelle ausweisen
        ("basicConstraints CA:TRUE"). Android nimmt es sonst gar nicht
        an, und Firefox fuehrt es nicht unter den Zertifizierungs-
        stellen.

        openssl setzt das bei einem selbstsignierten Zertifikat von
        sich aus - die vorhandenen tragen es also schon. Geprueft wird
        es trotzdem: Faellt es einmal weg, merkt das niemand ausser
        dem Nutzer am Tablet, und der kann es nicht einordnen.
        """

        pfad = pfad or self.zertifikat

        if not pfad.is_file():
            return False

        lauf = self._openssl("x509", "-in", str(pfad), "-noout", "-text")

        if lauf.returncode != 0:
            return False

        text = lauf.stdout.decode("utf-8", "replace")

        return "CA:TRUE" in text

    def oeffentlich(self) -> bytes | None:
        """
        Der oeffentliche Teil zum Herunterladen - ohne Schluessel.

        Diese Datei geht OHNE PIN und OHNE Kennwort heraus, und das ist
        richtig: Der oeffentliche Teil des Zertifikats geht bei jedem
        Verbindungsaufbau ueber die Leitung, an jeden, der fragt. Er
        ist kein Geheimnis und kann keines sein.

        Genau deshalb steht die Probe darunter. Sie prueft nicht die
        Datei, sie prueft UNS: Wer hier eines Tages versehentlich die
        Schluesseldatei einsetzt, verschenkt den Schluessel an jeden im
        Netz. Lieber nichts ausliefern als das.
        """

        if not self.zertifikat.is_file():
            return None

        daten = self.zertifikat.read_bytes()

        if b"PRIVATE KEY" in daten:

            self.logger.error(
                "Abbruch: In %s steht ein privater Schluessel - diese Datei "
                "wird nicht ausgeliefert.",
                self.zertifikat,
            )

            return None

        if b"-----BEGIN CERTIFICATE-----" not in daten:
            return None

        return daten

    def deckt_ab(self, name: str) -> bool:
        """Gilt das Zertifikat für diesen Namen?"""

        name = (name or "").strip().lower()

        if not name:
            return True

        return name in [eintrag.lower() for eintrag in self.namen()]

    # ----------------------------------------------------------------
    # Schreiben - immer erst prüfen, dann ersetzen
    # ----------------------------------------------------------------

    def _ablegen(self, zertifikat: bytes, schluessel: bytes) -> None:
        """
        Beide Dateien austauschen, jede für sich unteilbar.

        Geschrieben wird daneben und dann umbenannt: Ein abgebrochener
        Schreibvorgang hinterlässt sonst eine halbe Datei, und der
        Dienst startet nicht mehr.
        """

        self.zertifikat.parent.mkdir(parents=True, exist_ok=True)

        neu_crt = self.zertifikat.with_suffix(self.zertifikat.suffix + ".neu")
        neu_key = self.schluessel.with_suffix(self.schluessel.suffix + ".neu")

        neu_crt.write_bytes(zertifikat)

        #
        # Der Schlüssel gehört nur uns - und zwar von Anfang an, nicht
        # erst nach dem Schreiben.
        #
        alt = os.umask(0o077)

        try:
            neu_key.write_bytes(schluessel)
            neu_key.chmod(0o600)
        finally:
            os.umask(alt)

        os.replace(neu_crt, self.zertifikat)
        os.replace(neu_key, self.schluessel)

    def erzeugen(self, namen: list[str]) -> tuple[bool, str]:
        """
        Ein neues selbstsigniertes Zertifikat für die genannten Namen.

        Danach fragt der Browser einmal erneut - das ist der Preis
        und steht so auch in der Oberfläche.
        """

        sauber = []

        for name in namen:

            name = (name or "").strip().lower()

            if name and name not in sauber:
                sauber.append(name)

        if not sauber:
            return False, "Kein Name für das Zertifikat."

        eintraege = [f"DNS:{name}" for name in sauber]
        eintraege += [f"DNS:{name}" for name in IMMER if name not in sauber]
        eintraege += [f"IP:{adresse}" for adresse in IMMER_IP]

        with tempfile.TemporaryDirectory() as ordner:

            crt = Path(ordner) / "neu.crt"
            key = Path(ordner) / "neu.key"

            lauf = self._openssl(
                "req", "-x509", "-nodes", "-newkey", "rsa:2048",
                "-keyout", str(key),
                "-out", str(crt),
                "-days", str(LAUFZEIT_TAGE),
                "-subj", f"/CN={sauber[0]}",
                "-addext", "subjectAltName=" + ",".join(eintraege),
            )

            if lauf.returncode != 0 or not crt.is_file() or not key.is_file():

                self.logger.error(
                    "Zertifikat konnte nicht erzeugt werden: %s",
                    lauf.stderr.decode("utf-8", "replace").strip(),
                )

                return False, "Das Zertifikat konnte nicht erzeugt werden."

            self._ablegen(crt.read_bytes(), key.read_bytes())

        #
        # Selbst erzeugt heisst: nicht mehr eingespielt. Sonst hielte
        # install.sh es weiter für unantastbar.
        #
        self.marke.unlink(missing_ok=True)

        self.logger.info("Neues TLS-Zertifikat erzeugt: %s", ", ".join(sauber))

        return True, ""

    def exportieren(self, kennwort: str) -> tuple[bytes | None, str]:
        """
        Zertifikat und Schlüssel als verschlüsselte PKCS#12-Datei.

        Das Kennwort schützt die Datei dort, wo sie liegt - auf einem
        Tablet, in einem Download-Ordner, auf einem Stick. Wer sie
        ohne Kennwort herumliegen liesse, hätte den Schlüssel
        verschenkt.
        """

        if len(kennwort or "") < MINDESTKENNWORT:
            return None, (
                f"Das Kennwort muss mindestens {MINDESTKENNWORT} Zeichen "
                f"lang sein - es ist das Einzige, was die Datei schützt."
            )

        if not self.vorhanden():
            return None, "Es gibt kein Zertifikat zum Sichern."

        with tempfile.TemporaryDirectory() as ordner:

            ziel = Path(ordner) / "xrack.p12"

            lauf = self._openssl(
                "pkcs12", "-export",
                "-inkey", str(self.schluessel),
                "-in", str(self.zertifikat),
                "-name", "XRack",
                #
                # Ausdruecklich AES: Aeltere openssl-Fassungen packen
                # den Zertifikatsteil sonst mit RC2-40 ein, und das
                # ist heute kein Schutz mehr.
                #
                "-keypbe", "AES-256-CBC",
                "-certpbe", "AES-256-CBC",
                "-macalg", "sha256",
                "-passout", "stdin",
                "-out", str(ziel),
                eingabe=kennwort.encode("utf-8"),
            )

            if lauf.returncode != 0 or not ziel.is_file():

                self.logger.error(
                    "Zertifikat konnte nicht gesichert werden: %s",
                    lauf.stderr.decode("utf-8", "replace").strip(),
                )

                return None, "Das Zertifikat konnte nicht gesichert werden."

            return ziel.read_bytes(), ""

    def _paar_passt(self, zertifikat: Path, schluessel: Path) -> bool:
        """
        Gehören Zertifikat und Schlüssel zusammen?

        Beide tragen denselben öffentlichen Schlüssel, wenn sie ein
        Paar sind. Ohne diese Probe liesse sich ein Paar einspielen,
        das erst beim nächsten Start des Dienstes auffällt - und dann
        ist die Weboberfläche weg.
        """

        eins = self._openssl(
            "x509", "-in", str(zertifikat), "-noout", "-pubkey"
        )

        zwei = self._openssl("pkey", "-in", str(schluessel), "-pubout")

        if eins.returncode != 0 or zwei.returncode != 0:
            return False

        return eins.stdout.strip() == zwei.stdout.strip()

    def importieren(self, daten: bytes, kennwort: str) -> tuple[bool, str]:
        """
        Ein gesichertes Zertifikat einspielen.

        Geprüft wird alles, bevor irgendetwas geschrieben wird:
        Kennwort, Vollständigkeit, Zusammengehörigkeit und
        Gültigkeit. Was hier durchrutscht, merkt man erst, wenn die
        Weboberfläche nach einem Neustart nicht mehr kommt.
        """

        if not daten:
            return False, "Die Datei ist leer."

        if not kennwort:
            return False, "Ohne Kennwort lässt sich die Datei nicht öffnen."

        with tempfile.TemporaryDirectory() as ordner:

            quelle = Path(ordner) / "eingang.p12"
            crt = Path(ordner) / "eingang.crt"
            key = Path(ordner) / "eingang.key"

            quelle.write_bytes(daten)

            geheim = kennwort.encode("utf-8")

            zert_lauf = self._openssl(
                "pkcs12", "-in", str(quelle), "-passin", "stdin",
                "-nokeys", "-out", str(crt),
                eingabe=geheim,
            )

            if zert_lauf.returncode != 0:

                meldung = zert_lauf.stderr.decode("utf-8", "replace")

                if "invalid password" in meldung or "mac verify" in meldung.lower():
                    return False, "Das Kennwort stimmt nicht."

                return False, (
                    "Die Datei ist keine gesicherte XRack-Zertifikatsdatei."
                )

            schluessel_lauf = self._openssl(
                "pkcs12", "-in", str(quelle), "-passin", "stdin",
                "-nocerts", "-nodes", "-out", str(key),
                eingabe=geheim,
            )

            if schluessel_lauf.returncode != 0:
                return False, "Die Datei ist keine gesicherte XRack-Zertifikatsdatei."

            zertifikat = self._pem_schneiden(
                crt.read_bytes(), b"-----BEGIN CERTIFICATE-----"
            )

            schluessel = self._pem_schneiden(
                key.read_bytes(), b"-----BEGIN"
            )

            if b"-----BEGIN CERTIFICATE-----" not in zertifikat:
                return False, "In der Datei steht kein Zertifikat."

            if b"-----BEGIN" not in schluessel:
                return False, (
                    "In der Datei steht kein privater Schlüssel - ohne ihn "
                    "kann XRack das Zertifikat nicht benutzen."
                )

            crt.write_bytes(zertifikat)
            key.write_bytes(schluessel)

            if not self._paar_passt(crt, key):
                return False, (
                    "Zertifikat und Schlüssel in der Datei gehören nicht "
                    "zusammen."
                )

            ende = self.laeuft_bis(crt)

            if ende is None:
                return False, "Das Zertifikat in der Datei ist unlesbar."

            if ende <= datetime.now(timezone.utc):
                return False, (
                    f"Das Zertifikat ist am {ende.strftime('%Y-%m-%d')} "
                    f"abgelaufen."
                )

            namen = self.namen(crt)

            self._ablegen(zertifikat, schluessel)

        self.marke.write_text(
            datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC\n"),
            encoding="utf-8",
        )

        self.logger.info(
            "TLS-Zertifikat eingespielt, gültig für: %s", ", ".join(namen)
        )

        return True, ""
