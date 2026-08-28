#!/usr/bin/env python3
"""
Herunterfahren und Dienst-Neustart.

Beides laeuft ueber sudo und kann still scheitern - typischerweise,
weil die sudo-Berechtigung fehlt (install.sh nicht gelaufen). Genau
dann darf die Oberflaeche nicht "erledigt" melden: Der Nutzer wuerde
das Netzteil ziehen, waehrend noch eine Aufnahme offen ist.

Geprueft wird mit Attrappen auf dem PATH statt mit echten Aufrufen -
ein Test, der den Rechner herunterfaehrt, waere schlecht.
"""

import os
import stat
import subprocess
import tempfile
from pathlib import Path

from core.system_control import SystemControl

#
# Das Modul protokolliert Fehlschlaege - hier gewollt und deshalb
# stummgeschaltet, sonst sieht die Testausgabe wie ein Absturz aus.
#
import logging
logging.getLogger("XRack").setLevel(logging.CRITICAL)


def sudo_attrappe(ordner: Path, rueckgabe: int, meldung: str = "") -> dict:
    """
    Legt ein 'sudo' an, das nur protokolliert und einen gewuenschten
    Rueckgabewert liefert.
    """

    ordner.mkdir(parents=True, exist_ok=True)
    protokoll = ordner / "protokoll.txt"
    protokoll.write_text("")

    sudo = ordner / "sudo"
    #
    # printf statt echo: In /bin/sh deutet echo ein fuehrendes "-n"
    # als eigene Option und verschluckt es - dann sieht die Attrappe
    # "poweroff" statt "-n poweroff", und die Pruefung auf -n haette
    # faelschlich angeschlagen.
    #
    sudo.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> \"{protokoll}\"\n"
        + (f'printf "%s\\n" "{meldung}" >&2\n' if meldung else "")
        + f"exit {rueckgabe}\n"
    )
    sudo.chmod(sudo.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    umgebung = dict(os.environ)
    umgebung["PATH"] = f"{ordner}:{umgebung['PATH']}"

    return {"protokoll": protokoll, "umgebung": umgebung}


def mit_pfad(umgebung, funktion):
    """Fuehrt etwas mit veraendertem PATH aus und setzt ihn danach zurueck."""

    alt = os.environ.get("PATH", "")
    os.environ["PATH"] = umgebung["PATH"]

    try:
        return funktion()
    finally:
        os.environ["PATH"] = alt


# ====================================================================
# Der gute Fall
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    a = sudo_attrappe(Path(tmp) / "bin", rueckgabe=0)

    s = SystemControl()

    assert mit_pfad(a["umgebung"], s.shutdown) is True

    aufrufe = a["protokoll"].read_text()

    assert "poweroff" in aufrufe, f"poweroff wurde nicht aufgerufen: {aufrufe!r}"
    assert "-n" in aufrufe, (
        "sudo muss mit -n laufen - sonst wartet der Dienst auf eine "
        "Passworteingabe, die niemand sieht."
    )

    print("OK: Herunterfahren ruft 'sudo -n poweroff' und meldet Erfolg")


# ====================================================================
# Fehlt das sudo-Recht, wird das gemeldet - nicht verschluckt
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    a = sudo_attrappe(
        Path(tmp) / "bin", rueckgabe=1,
        meldung="sudo: a password is required",
    )

    s = SystemControl()

    assert mit_pfad(a["umgebung"], s.shutdown) is False, (
        "Ein fehlgeschlagenes Herunterfahren wurde als Erfolg gemeldet. "
        "Der Nutzer zieht dann das Netzteil, waehrend noch aufgenommen wird."
    )

    print("OK: Ein fehlgeschlagenes Herunterfahren meldet auch einen Fehlschlag")


# ====================================================================
# Gibt es gar kein sudo, faellt es weich - kein Absturz
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    leer = Path(tmp) / "leer"
    leer.mkdir()

    s = SystemControl()

    alt = os.environ.get("PATH", "")
    os.environ["PATH"] = str(leer)

    try:
        assert s.shutdown() is False, "Ohne sudo muesste False herauskommen"
    finally:
        os.environ["PATH"] = alt

    print("OK: Fehlt sudo, wird das abgefangen statt zu stuerzen")


# ====================================================================
# Dienst-Neustart
# ====================================================================

with tempfile.TemporaryDirectory() as tmp:

    a = sudo_attrappe(Path(tmp) / "bin", rueckgabe=0)

    s = SystemControl()

    assert mit_pfad(a["umgebung"], s.restart_service) is True

    aufrufe = a["protokoll"].read_text()

    assert "xrack-restart.sh" in aufrufe or "restart" in aufrufe, (
        f"Der Neustart ruft nichts Passendes auf: {aufrufe!r}"
    )

    print("OK: Der Dienst-Neustart ruft das vorgesehene Skript")

with tempfile.TemporaryDirectory() as tmp:

    a = sudo_attrappe(Path(tmp) / "bin", rueckgabe=1)

    s = SystemControl()

    assert mit_pfad(a["umgebung"], s.restart_service) is False

    print("OK: Ein fehlgeschlagener Neustart meldet einen Fehlschlag")


print("Alle System-Tests erfolgreich.")
