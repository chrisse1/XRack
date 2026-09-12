#!/usr/bin/env python3
"""
Prüft das Sichern und Einspielen des TLS-Zertifikats.

Wozu das überhaupt: XRack spricht HTTPS mit einem selbstsignierten
Zertifikat, der Browser fragt deshalb einmal nach. Wer mehrere Racks
hat, bestätigt bei jedem einzeln. Die Abhilfe ist NICHT, ein
Zertifikat mitzuliefern - dann läge der private Schlüssel öffentlich,
und jeder im selben WLAN könnte sich lautlos als XRack ausgeben. Die
Abhilfe ist, dass der Nutzer sein eigenes Zertifikat von Rack zu Rack
trägt.

Drei Dinge müssen dabei stimmen, und das dritte ist das wichtigste:

  1. Was gesichert wurde, muss drüben ankommen und passen.
  2. Was nicht stimmt, darf nicht eingespielt werden - falsches
     Kennwort, fremde Datei, Zertifikat ohne passenden Schlüssel,
     abgelaufenes Zertifikat.
  3. Ein Fehlschlag darf das vorhandene Zertifikat nicht anrühren.
     Wer beim Einspielen sein altes verliert, hat danach gar keins -
     und die Weboberfläche kommt nach dem nächsten Neustart nicht
     mehr hoch.
"""

import subprocess
import sys

from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tempfile  # noqa: E402

from core.tls_store import TlsStore, MINDESTKENNWORT  # noqa: E402


KENNWORT = "einsehrgutesKennwort"


def store(ordner: Path) -> TlsStore:

    return TlsStore(ordner / "xrack.crt", ordner / "xrack.key")


def fremdes_paar(ordner: Path, name: str, tage: int = 3650) -> tuple[Path, Path]:
    """Ein Zertifikat ausserhalb von XRack - für die Gegenproben."""

    crt = ordner / f"{name}.crt"
    key = ordner / f"{name}.key"

    subprocess.run(
        [
            "openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(crt),
            "-days", str(tage),
            "-subj", f"/CN={name}",
            "-addext", f"subjectAltName=DNS:{name}",
        ],
        capture_output=True,
        check=True,
    )

    return crt, key


def p12_bauen(ziel: Path, crt: Path, key: Path, kennwort: str) -> Path:

    subprocess.run(
        [
            "openssl", "pkcs12", "-export",
            "-inkey", str(key), "-in", str(crt),
            "-passout", "stdin", "-out", str(ziel),
        ],
        input=kennwort.encode("utf-8"),
        capture_output=True,
        check=True,
    )

    return ziel


arbeit = tempfile.TemporaryDirectory()
WURZEL = Path(arbeit.name)


# ====================================================================
# 1. Erzeugen: das Zertifikat gilt für die Namen, die man ihm gibt
# ====================================================================

hier_ordner = WURZEL / "rack-a"
hier_ordner.mkdir()

hier = store(hier_ordner)

assert hier.vorhanden() is False
assert hier.zustand()["present"] is False

erfolg, meldung = hier.erzeugen(
    ["xrack-a", "xrack-a.local", "xrack", "xrack.local"]
)

assert erfolg, meldung

namen = hier.namen()

for erwartet in ("xrack-a", "xrack-a.local", "xrack", "xrack.local",
                 "localhost", "127.0.0.1"):

    assert erwartet in namen, (
        f"{erwartet!r} fehlt im Zertifikat: {namen}"
    )

assert hier.deckt_ab("xrack.local"), namen
assert not hier.deckt_ab("fremd.local"), namen

#
# Der Schlüssel gehört niemandem sonst. Ein Schlüssel mit 0644 wäre
# für jeden lesbar, der am Gerät ein Terminal hat.
#
modus = hier.schluessel.stat().st_mode & 0o777

assert modus == 0o600, f"Der Schlüssel steht auf {modus:o} statt 600."

zustand = hier.zustand()

assert zustand["present"] and not zustand["imported"], zustand
assert zustand["days_left"] > 3600, zustand

print(f"OK: Erzeugt, gültig für {len(namen)} Namen, Schlüssel nur für uns")


# ====================================================================
# 2. Sichern und drüben einspielen
# ====================================================================

daten, meldung = hier.exportieren(KENNWORT)

assert daten, meldung

#
# Und zwar wirklich verschlüsselt: Der Schlüssel darf in der Datei
# nicht im Klartext stehen.
#
assert b"PRIVATE KEY" not in daten, (
    "Der private Schlüssel steht unverschlüsselt in der gesicherten Datei."
)

drueben_ordner = WURZEL / "rack-b"
drueben_ordner.mkdir()

drueben = store(drueben_ordner)

erfolg, meldung = drueben.importieren(daten, KENNWORT)

assert erfolg, meldung

assert drueben.zertifikat.read_bytes() == hier.zertifikat.read_bytes(), (
    "Drüben steht ein anderes Zertifikat als hier - dann fragt der "
    "Browser weiterhin zweimal."
)

assert drueben.namen() == hier.namen(), drueben.namen()

assert drueben.zustand()["imported"] is True, (
    "Das eingespielte Zertifikat ist nicht als übertragen vermerkt - "
    "der nächste Installationslauf würde es wegwerfen."
)

assert drueben.marke.exists()

assert (drueben.schluessel.stat().st_mode & 0o777) == 0o600

#
# Das Paar muss drüben auch wirklich zusammenpassen.
#
assert drueben._paar_passt(drueben.zertifikat, drueben.schluessel), (
    "Zertifikat und Schlüssel passen nach dem Einspielen nicht zusammen."
)

print("OK: Gesichert, eingespielt - drüben steht dasselbe Zertifikat")


# ====================================================================
# 3. Was nicht stimmt, kommt nicht hinein - und zerstört nichts
#
# Das ist der Fall, der zählt. Ein Fehlschlag, der das vorhandene
# Zertifikat mitnimmt, macht aus einem missglückten Versuch ein Rack
# ohne Weboberfläche.
# ====================================================================

vorher_crt = drueben.zertifikat.read_bytes()
vorher_key = drueben.schluessel.read_bytes()

fremd_crt, fremd_key = fremdes_paar(WURZEL, "fremd")

anders_crt, anders_key = fremdes_paar(WURZEL, "anders")

abgelaufen_crt, abgelaufen_key = fremdes_paar(WURZEL, "alt", tage=1)

#
# Ein abgelaufenes Zertifikat lässt sich nicht mit openssl erzeugen
# (negative Laufzeit) - deshalb eines, das gleich abläuft, und die
# Prüfung darauf getrennt.
#

faelle = [
    (
        "falsches Kennwort",
        daten,
        "vollkommenFalsch",
    ),
    (
        "leeres Kennwort",
        daten,
        "",
    ),
    (
        "gar keine Zertifikatsdatei",
        b"Das hier ist ein Textdokument und kein Zertifikat.",
        KENNWORT,
    ),
    (
        "leere Datei",
        b"",
        KENNWORT,
    ),
]

for beschreibung, inhalt, kennwort in faelle:

    erfolg, meldung = drueben.importieren(inhalt, kennwort)

    assert not erfolg, f"{beschreibung}: wurde eingespielt statt abgelehnt."

    assert meldung, f"{beschreibung}: abgelehnt, aber ohne Begründung."

    assert drueben.zertifikat.read_bytes() == vorher_crt, (
        f"{beschreibung}: Das vorhandene Zertifikat wurde beschädigt."
    )

    assert drueben.schluessel.read_bytes() == vorher_key, (
        f"{beschreibung}: Der vorhandene Schlüssel wurde beschädigt."
    )

print("OK: Kaputte Dateien werden begründet abgelehnt, ohne Schaden")


# ====================================================================
# 4. Zertifikat und Schlüssel, die nicht zusammengehören
#
# openssl baut so ein Paar gar nicht erst in eine PKCS#12-Datei - die
# Probe muss trotzdem stehen, denn eine von Hand gebaute Datei kommt
# nicht durch openssl.
# ====================================================================

assert not drueben._paar_passt(fremd_crt, anders_key), (
    "Ein Zertifikat gilt als zum fremden Schlüssel passend - damit "
    "liesse sich ein Paar einspielen, das erst beim nächsten Start "
    "auffällt, und dann ist die Weboberfläche weg."
)

assert drueben._paar_passt(fremd_crt, fremd_key)

print("OK: Ein Zertifikat ohne seinen Schlüssel fällt auf")


# ====================================================================
# 5. Ein abgelaufenes Zertifikat wird nicht eingespielt
# ====================================================================

class AbgelaufenerStore(TlsStore):
    """
    Tut so, als wäre das Zertifikat abgelaufen.

    Ein wirklich abgelaufenes zu erzeugen geht mit openssl nicht ohne
    Weiteres (negative Laufzeit) - geprüft wird die Entscheidung, und
    die hängt am Ablaufdatum.
    """

    def laeuft_bis(self, pfad=None):

        if pfad is not None and pfad.name.startswith("eingang"):
            return datetime.now(timezone.utc) - timedelta(days=1)

        return super().laeuft_bis(pfad)


alt_store = AbgelaufenerStore(drueben.zertifikat, drueben.schluessel)

erfolg, meldung = alt_store.importieren(daten, KENNWORT)

assert not erfolg and "abgelaufen" in meldung, meldung

assert drueben.zertifikat.read_bytes() == vorher_crt, (
    "Das abgelaufene Zertifikat hat das vorhandene ersetzt."
)

print("OK: Ein abgelaufenes Zertifikat wird abgelehnt")


# ====================================================================
# 6. Ein zu kurzes Kennwort gibt es nicht
#
# Die Datei enthält den Schlüssel, mit dem sich jemand als dieses Rack
# ausgibt. Ein Kennwort aus vier Zeichen wäre ein Feigenblatt.
# ====================================================================

zu_kurz, meldung = hier.exportieren("kurz")

assert zu_kurz is None, "Ein Kennwort aus vier Zeichen wurde akzeptiert."
assert str(MINDESTKENNWORT) in meldung, meldung

leer, meldung = hier.exportieren("")

assert leer is None, "Eine Sicherung ohne Kennwort wurde erstellt."

print(f"OK: Unter {MINDESTKENNWORT} Zeichen gibt es keine Sicherung")


# ====================================================================
# 7. Neu erzeugen hebt die Übertragung wieder auf
#
# Sonst hielte install.sh das Zertifikat weiter für unantastbar,
# obwohl es längst ein anderes ist.
# ====================================================================

erfolg, meldung = drueben.erzeugen(["xrack-b", "xrack-b.local"])

assert erfolg, meldung

assert not drueben.marke.exists(), (
    "Nach dem Neuerzeugen gilt das Zertifikat immer noch als übertragen."
)

assert drueben.zustand()["imported"] is False

assert drueben.zertifikat.read_bytes() != vorher_crt

print("OK: Ein neu erzeugtes Zertifikat gilt nicht mehr als übertragen")


# ====================================================================
# 8. install.sh wirft ein übertragenes Zertifikat nicht weg
#
# Der stillste aller Fehler: Nach einem Update läuft install.sh
# erneut, findet einen fremden Rechnernamen im Zertifikat und erzeugt
# ein neues. Der Browser fragt wieder, und niemand weiss, warum.
# ====================================================================

INSTALL = Path(__file__).resolve().parent / "install.sh"


def installer_laesst_stehen(mit_marke: bool) -> bool:
    """Ruft zertifikat_passt aus install.sh mit fremdem Hostnamen auf."""

    with tempfile.TemporaryDirectory() as ordner:

        ziel = Path(ordner)
        (ziel / "certs").mkdir()

        laden = store(ziel / "certs")
        laden.erzeugen(["ein-anderes-rack", "ein-anderes-rack.local"])

        if mit_marke:
            laden.marke.write_text("x", encoding="utf-8")

        skript = ziel / "lauf.sh"
        skript.write_text(
            "export XRACK_INSTALL_SOURCE_ONLY=1\n"
            f"source {INSTALL}\n"
            f'INSTALL_DIR="{ziel}"\n'
            'XRACK_HOSTNAME="dieses-rack"\n'
            "zertifikat_passt && echo BEHALTEN || echo NEU\n",
            encoding="utf-8",
        )

        lauf = subprocess.run(
            ["bash", str(skript)], capture_output=True, text=True, timeout=60
        )

        assert "BEHALTEN" in lauf.stdout or "NEU" in lauf.stdout, (
            f"zertifikat_passt hat nichts gesagt:\n{lauf.stdout}\n{lauf.stderr}"
        )

        return "BEHALTEN" in lauf.stdout


assert installer_laesst_stehen(mit_marke=True), (
    "install.sh wirft ein übertragenes Zertifikat weg, weil es auf einen "
    "anderen Rechnernamen lautet - damit wäre die ganze Übertragung nach "
    "dem nächsten Update wieder aufgehoben."
)

assert not installer_laesst_stehen(mit_marke=False), (
    "install.sh behält ein fremdes Zertifikat auch OHNE die Marke - dann "
    "prüft es den Rechnernamen gar nicht mehr."
)

print("OK: install.sh behält das übertragene und nur das übertragene")


# ====================================================================
# 9. Wer darf überhaupt an den Schlüssel?
#
# Der wunde Punkt der ganzen Sache. Alle übrigen Schnittstellen von
# XRack sind ohne Anmeldung erreichbar - wer im Netz steht, darf das
# Rack bedienen, so ist es gewollt. Der private Schlüssel ist etwas
# anderes: Wer ihn hat, gibt sich später und woanders als dieses Rack
# aus, lautlos, und bekommt die PIN mitgeliefert, sobald jemand sie
# eintippt.
#
# Deshalb wird hier - und nur hier - die PIN auf dem SERVER geprüft.
# ====================================================================

from core.application.zertifikat import ZertifikatMixin  # noqa: E402
from core.pin_bremse import PinBremse  # noqa: E402


class Namen:

    def __init__(self, name=""):
        self.name = name

    def hostname(self):
        return "rack-im-versuch"


class Rack(ZertifikatMixin):
    """
    Nur so viel Application, wie das Zertifikat braucht.

    Die echte Anwendung zöge ALSA, psutil und das Pult mit herein -
    geprüft werden soll aber die Entscheidung, wer darf.
    """

    def __init__(self, pin, laden, alias="", bremse=None):

        self._pin = pin
        self.tls_store = laden
        self.mdns_alias = Namen(alias)
        self.pin_bremse = bremse or PinBremse()

    def pin_protection_enabled(self):
        return self._pin is not None

    def verify_settings_pin(self, pin):

        if self._pin is None:
            return True

        return pin == self._pin


#
# Ohne PIN gar nichts - auch nicht mit leerer Eingabe.
#
ohne_pin = Rack(None, hier)

for name, aufruf in (
    ("Sichern", lambda r: r.zertifikat_sichern("", KENNWORT)[0]),
    ("Einspielen", lambda r: r.zertifikat_einspielen("", KENNWORT, daten)[0]),
    ("Neu erzeugen", lambda r: r.zertifikat_erneuern("")[0]),
):

    ergebnis = aufruf(ohne_pin)

    assert not ergebnis, (
        f"{name} geht ohne vergebene PIN - dann könnte jeder im Netz den "
        f"privaten Schlüssel abholen, und XRack hätte sich genau das "
        f"eingehandelt, wogegen es kein mitgeliefertes Zertifikat gibt."
    )

erlaubt, meldung = ohne_pin.zertifikat_erlaubt("")

assert "PIN" in meldung, meldung

print("OK: Ohne vergebene PIN gibt XRack den Schlüssel nicht heraus")


#
# Mit PIN: falsche abgelehnt, richtige durchgelassen.
#
mit_pin = Rack("4711", hier)

abgelehnt, meldung = mit_pin.zertifikat_sichern("0000", KENNWORT)

assert abgelehnt is None, "Eine falsche PIN kam an den Schlüssel."

gesichert, meldung = mit_pin.zertifikat_sichern("4711", KENNWORT)

assert gesichert, meldung

print("OK: Mit PIN kommt nur die richtige an den Schlüssel")


# ====================================================================
# 10. Die Bremse gegen das Durchprobieren
#
# Vier Ziffern sind 10000 Möglichkeiten. Ohne Bremse ist das eine
# Sache von Minuten - und dann liegt der Schlüssel beim Angreifer.
# ====================================================================

bremse = PinBremse(versuche=3, sperre=0.4)

geschuetzt = Rack("4711", hier, bremse=bremse)

for versuch in range(3):

    erlaubt, _ = geschuetzt.zertifikat_erlaubt("0000")

    assert not erlaubt, "Eine falsche PIN wurde durchgelassen."

#
# Jetzt ist zu, und zwar auch für die RICHTIGE PIN - sonst wäre die
# Bremse keine.
#
erlaubt, meldung = geschuetzt.zertifikat_erlaubt("4711")

assert not erlaubt, (
    "Nach drei Fehlversuchen geht es sofort weiter - dann bremst nichts, "
    "und 10000 Versuche sind schnell durch."
)

assert "warten" in meldung.lower(), meldung

import time  # noqa: E402

time.sleep(0.5)

erlaubt, meldung = geschuetzt.zertifikat_erlaubt("4711")

assert erlaubt, (
    f"Nach der Wartezeit bleibt es gesperrt: {meldung}"
)

print("OK: Nach drei Fehlversuchen ist eine Weile Ruhe, danach geht es weiter")


# ====================================================================
# 11. Was die Oberfläche angezeigt bekommt
#
# Vor allem: ob der gemeinsame Name im Zertifikat steht. Tut er das
# nicht, fragt der Browser unter diesem Namen weiter nach - und die
# ganze Übertragung hätte ihren Zweck verfehlt, ohne dass es jemandem
# auffällt.
# ====================================================================

passend = Rack("4711", hier, alias="xrack")

zustand = passend.get_zertifikat()

assert zustand["alias"] == "xrack", zustand
assert zustand["alias_covered"] is True, (
    f"Der gemeinsame Name gilt als nicht abgedeckt, obwohl er im "
    f"Zertifikat steht: {zustand}"
)
assert zustand["pin_required"] is False, zustand

unpassend = Rack("4711", hier, alias="ganz-anders")

assert unpassend.get_zertifikat()["alias_covered"] is False, (
    "Ein gemeinsamer Name, der NICHT im Zertifikat steht, gilt als "
    "abgedeckt - dann bleibt die Rückfrage im Browser, und niemand "
    "erfährt, warum."
)

assert Rack(None, hier).get_zertifikat()["pin_required"] is True

#
# Und die Namen, die ein neues Zertifikat bekäme: eigener Name und
# der gemeinsame, jeweils mit und ohne .local.
#
assert passend.zertifikat_namen() == [
    "rack-im-versuch", "rack-im-versuch.local", "xrack", "xrack.local",
], passend.zertifikat_namen()

assert Rack("4711", hier).zertifikat_namen() == [
    "rack-im-versuch", "rack-im-versuch.local",
]

print("OK: Die Oberfläche erfährt, ob der gemeinsame Name mit drinsteht")


arbeit.cleanup()

print("Alle Zertifikats-Tests erfolgreich.")
