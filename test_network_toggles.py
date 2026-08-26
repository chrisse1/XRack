"""
Prüft die beiden Netzwerk-Schalter gegeneinander, ohne NetworkManager.

Hintergrund: "Konsole über XRacks Access Point" (die Bridge) und
"Konsole aus dem Heimnetz" (die Freigabe) beanspruchen beide eth0 und
schließen sich deshalb aus. Jedes der beiden Skripte muss das jeweils
andere sauber abräumen.

Genau daran hing ein Fehler: Die Bridge hängt beim Einschalten den
Access Point als Slave ein ("master XRack-Bridge"). Das Freigabe-Skript
fuhr die Bridge zwar herunter, ließ den Access Point aber als Slave
stehen. Folge: Der Access Point lief bis zum nächsten Neustart nicht -
und beim Hochfahren zog NetworkManager mit dem Slave auch dessen Master
wieder hoch, sodass beide Schalter gleichzeitig an waren.

Getestet wird gegen ein nachgestelltes nmcli: ein Skript im PATH, das
Verbindungen und ihren Zustand in Dateien verwaltet und jeden Aufruf
mitschreibt. Damit lässt sich prüfen, was die Skripte *tun*, ohne ein
echtes Netzwerk anzufassen.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SKRIPTE = Path(__file__).parent / "scripts"

#
# Das nachgestellte nmcli. Es kennt nur so viel, wie die beiden
# Schalter-Skripte tatsächlich benutzen - mehr nachzubauen hieße, den
# Test an NetworkManager-Interna zu binden, die hier niemand prüft.
#
FAKE_NMCLI = r"""#!/usr/bin/env bash
#
# Nachgestelltes nmcli fuer die Tests. Zustand liegt in $NM_STATE:
#   connections   - eine Zeile je eingerichteter Verbindung
#   active        - eine Zeile je aktiver Verbindung
#   props/<Name>  - "schluessel=wert" je Zeile
#   calls         - Mitschrift aller Aufrufe
#
echo "$*" >> "$NM_STATE/calls"

prop_datei() { echo "$NM_STATE/props/$1"; }

prop_lesen() {
    grep -m1 "^$2=" "$(prop_datei "$1")" 2>/dev/null | cut -d= -f2-
}

prop_setzen() {
    local datei; datei="$(prop_datei "$1")"
    touch "$datei"
    grep -v "^$2=" "$datei" > "$datei.tmp" 2>/dev/null || true
    echo "$2=$3" >> "$datei.tmp"
    mv "$datei.tmp" "$datei"
}

case "$1 $2 $3" in
  "-t -f NAME")
    if [ "$5" = "--active" ]; then cat "$NM_STATE/active" 2>/dev/null
    else cat "$NM_STATE/connections" 2>/dev/null; fi
    exit 0 ;;
esac

if [ "$1" = "-t" ] && [ "$3" = "NAME,DEVICE" ]; then
    while read -r name; do
        echo "$name:$(prop_lesen "$name" device)"
    done < "$NM_STATE/connections"
    exit 0
fi

if [ "$1" = "-g" ] || { [ "$1" = "-s" ] && [ "$2" = "-g" ]; }; then
    [ "$1" = "-s" ] && shift
    schluessel="$2"; name="${!#}"
    case "$schluessel" in
      connection.interface-name) prop_lesen "$name" device ;;
      *) echo "geheim" ;;
    esac
    exit 0
fi

if [ "$1" = "connection" ]; then
    case "$2" in
      modify)
        name="$3"; shift 3
        while [ $# -gt 0 ]; do
            case "$1" in
              master|connection.master) prop_setzen "$name" master "$2"; shift 2 ;;
              slave-type|connection.slave-type) prop_setzen "$name" slave-type "$2"; shift 2 ;;
              connection.autoconnect) prop_setzen "$name" autoconnect "$2"; shift 2 ;;
              *) shift ;;
            esac
        done
        exit 0 ;;
      up)
        grep -qx "$3" "$NM_STATE/active" 2>/dev/null || echo "$3" >> "$NM_STATE/active"
        exit 0 ;;
      down)
        grep -vx "$3" "$NM_STATE/active" > "$NM_STATE/active.tmp" 2>/dev/null || true
        mv "$NM_STATE/active.tmp" "$NM_STATE/active" 2>/dev/null || true
        exit 0 ;;
      show) exit 0 ;;
    esac
fi

exit 0
"""


class Netzwerk:
    """Ein nachgestelltes NetworkManager-Setup."""

    def __init__(self, verzeichnis: Path, mit_ap: bool = True):

        self.pfad = verzeichnis
        (self.pfad / "props").mkdir(parents=True)

        verbindungen = ["XRack-Home", "XRack-Share-eth0"]

        if mit_ap:
            verbindungen += ["XRack-AP", "XRack-Bridge", "XRack-Bridge-eth0"]

        (self.pfad / "connections").write_text(
            "\n".join(verbindungen) + "\n", encoding="utf-8"
        )
        (self.pfad / "active").write_text("XRack-Home\n", encoding="utf-8")

        if mit_ap:
            self.setze("XRack-AP", "device", "wlan1")

        self.setze("XRack-Share-eth0", "device", "eth0")

        #
        # nmcli-Attrappe in einen eigenen bin-Ordner legen und dem
        # PATH voranstellen.
        #
        binordner = self.pfad / "bin"
        binordner.mkdir()

        nmcli = binordner / "nmcli"
        nmcli.write_text(FAKE_NMCLI, encoding="utf-8")
        nmcli.chmod(0o755)

        self.umgebung = dict(os.environ)
        self.umgebung["NM_STATE"] = str(self.pfad)
        self.umgebung["PATH"] = f"{binordner}:{os.environ['PATH']}"

    def setze(self, name: str, schluessel: str, wert: str) -> None:
        datei = self.pfad / "props" / name
        zeilen = [
            z for z in (datei.read_text(encoding="utf-8").splitlines()
                        if datei.exists() else [])
            if not z.startswith(f"{schluessel}=")
        ]
        zeilen.append(f"{schluessel}={wert}")
        datei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

    def lies(self, name: str, schluessel: str) -> str:
        datei = self.pfad / "props" / name
        if not datei.exists():
            return ""
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            if zeile.startswith(f"{schluessel}="):
                return zeile.split("=", 1)[1]
        return ""

    def aktiv(self) -> set:
        datei = self.pfad / "active"
        if not datei.exists():
            return set()
        return set(datei.read_text(encoding="utf-8").split())

    def aktiviere(self, name: str) -> None:
        with (self.pfad / "active").open("a", encoding="utf-8") as f:
            f.write(name + "\n")

    def schalte(self, skript: str, modus: str):
        return subprocess.run(
            [str(SKRIPTE / skript), modus],
            env=self.umgebung,
            capture_output=True,
            text=True,
            timeout=30,
        )


scratch = Path(tempfile.mkdtemp())

try:

    # ----------------------------------------------------------------
    # 1. Bridge an: Der Access Point wird Slave der Bridge
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "a")

    ergebnis = netz.schalte("xrack-bridge-toggle.sh", "on")

    assert ergebnis.returncode == 0, ergebnis.stderr

    assert netz.lies("XRack-AP", "master") == "XRack-Bridge", (
        "Die Bridge muss den Access Point als Slave einhaengen."
    )
    assert netz.lies("XRack-AP", "slave-type") == "bridge"

    print("OK: Bridge an haengt den Access Point als Slave ein")

    # ----------------------------------------------------------------
    # 2. Bridge aus: Der Access Point wird wieder eigenstaendig
    # ----------------------------------------------------------------

    ergebnis = netz.schalte("xrack-bridge-toggle.sh", "off")

    assert ergebnis.returncode == 0, ergebnis.stderr

    assert netz.lies("XRack-AP", "master") == "", (
        f"Der Access Point haengt noch an "
        f"{netz.lies('XRack-AP', 'master')!r}"
    )

    print("OK: Bridge aus loest den Access Point wieder heraus")

    # ----------------------------------------------------------------
    # 3. Der eigentliche Fehler: Freigabe an, waehrend die Bridge laeuft
    #
    # Die Freigabe muss die Bridge vollstaendig abraeumen - also auch
    # den Access Point wieder herausloesen. Bleibt er Slave, laeuft er
    # bis zum Neustart nicht, und beim Hochfahren zieht er die Bridge
    # wieder mit hoch: Dann sind beide Schalter an, obwohl sie sich
    # ausschliessen.
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "b")

    assert netz.schalte("xrack-bridge-toggle.sh", "on").returncode == 0
    assert netz.lies("XRack-AP", "master") == "XRack-Bridge"
    assert "XRack-Bridge" in netz.aktiv()

    ergebnis = netz.schalte("xrack-share-toggle.sh", "on")

    assert ergebnis.returncode == 0, ergebnis.stderr

    assert netz.lies("XRack-AP", "master") == "", (
        "Die Freigabe hat die Bridge heruntergefahren, den Access Point "
        "aber als Slave stehenlassen. Er laeuft dann bis zum Neustart "
        "nicht - und beim Hochfahren zieht NetworkManager mit ihm die "
        "Bridge wieder hoch."
    )
    assert netz.lies("XRack-AP", "slave-type") == ""

    print("OK: Freigabe an loest den Access Point aus der Bridge")

    # ----------------------------------------------------------------
    # 4. Danach darf nur noch die Freigabe aktiv sein
    # ----------------------------------------------------------------

    aktiv = netz.aktiv()

    assert "XRack-Share-eth0" in aktiv, aktiv
    assert "XRack-Bridge" not in aktiv, (
        f"Bridge und Freigabe sind gleichzeitig aktiv: {sorted(aktiv)}"
    )

    assert netz.lies("XRack-Bridge", "autoconnect") == "no", (
        "Die Bridge darf nach dem Umschalten nicht von selbst wiederkommen."
    )

    print("OK: Nach dem Umschalten ist nur die Freigabe aktiv")

    # ----------------------------------------------------------------
    # 5. Und in die andere Richtung genauso
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "c")

    assert netz.schalte("xrack-share-toggle.sh", "on").returncode == 0
    assert "XRack-Share-eth0" in netz.aktiv()

    assert netz.schalte("xrack-bridge-toggle.sh", "on").returncode == 0

    aktiv = netz.aktiv()

    assert "XRack-Bridge" in aktiv, aktiv
    assert "XRack-Share-eth0" not in aktiv, (
        f"Freigabe laeuft trotz eingeschalteter Bridge weiter: {sorted(aktiv)}"
    )
    assert netz.lies("XRack-Share-eth0", "autoconnect") == "no"

    print("OK: Bridge an raeumt die Freigabe ab")

    # ----------------------------------------------------------------
    # 6. Ohne eingerichteten Access Point darf die Freigabe trotzdem gehen
    #
    # Nicht jede Installation hat einen Access Point. Das Abraeumen der
    # Bridge darf dann nicht zum Abbruch fuehren.
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "d", mit_ap=False)

    ergebnis = netz.schalte("xrack-share-toggle.sh", "on")

    assert ergebnis.returncode == 0, (
        f"Ohne Access Point schlug die Freigabe fehl: {ergebnis.stderr}"
    )
    assert "XRack-Share-eth0" in netz.aktiv()

    print("OK: Ohne Access Point laesst sich die Freigabe trotzdem schalten")

    # ----------------------------------------------------------------
    # 7. Der Lease-Leser darf keine abgelaufenen Adressen melden
    #
    # dnsmasq laesst abgelaufene Eintraege eine Weile in der Datei
    # stehen. Wurde nur die letzte Zeile genommen, meldete XRack eine
    # Adresse, unter der laengst nichts mehr antwortet - und das sieht
    # aus, als sei die Konsole erreichbar. Danach sucht man lange an
    # der falschen Stelle.
    # ----------------------------------------------------------------

    import time

    lease_skript = SKRIPTE / "xrack-dhcp-lease.sh"

    def lease_lesen(zeilen: list[str]) -> str:
        """Legt eine Lease-Datei an und fragt das Skript danach."""

        ordner = Path(tempfile.mkdtemp(dir=scratch))

        #
        # Das Skript baut den Pfad aus dem Interface-Namen. Deshalb
        # einen "Interface-Namen" uebergeben, der auf unsere Datei
        # zeigt - so bleibt das Skript unveraendert pruefbar.
        #
        datei = ordner / "dnsmasq-test.leases"
        datei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

        inhalt = lease_skript.read_text(encoding="utf-8").replace(
            "/var/lib/NetworkManager/dnsmasq-${IFACE}.leases",
            str(ordner / "dnsmasq-${IFACE}.leases"),
        )

        kopie = ordner / "lease.sh"
        kopie.write_text(inhalt, encoding="utf-8")
        kopie.chmod(0o755)

        return subprocess.run(
            [str(kopie), "test"], capture_output=True, text=True, timeout=10
        ).stdout.strip()

    jetzt = int(time.time())

    #
    # Gueltige Lease wird gemeldet.
    #
    assert lease_lesen([
        f"{jetzt + 3600} 11:22:33:44:55:66 10.77.0.120 pult *"
    ]) == "10.77.0.120"

    #
    # Abgelaufene NICHT.
    #
    assert lease_lesen([
        f"{jetzt - 3600} 11:22:33:44:55:66 10.77.0.99 alt *"
    ]) == "", "Eine abgelaufene Lease wurde als aktuelle Adresse gemeldet."

    #
    # Steht eine abgelaufene HINTER einer gueltigen, gewinnt die
    # gueltige - "letzte Zeile" allein waere hier falsch.
    #
    assert lease_lesen([
        f"{jetzt + 3600} 11:22:33:44:55:66 10.77.0.120 pult *",
        f"{jetzt - 3600} aa:bb:cc:dd:ee:ff 10.77.0.99 alt *",
    ]) == "10.77.0.120", (
        "Eine abgelaufene Lease hat eine gueltige verdraengt."
    )

    #
    # Zeitstempel 0 heisst bei dnsmasq "laeuft nie ab".
    #
    assert lease_lesen([
        "0 11:22:33:44:55:66 10.77.0.120 dauerhaft *"
    ]) == "10.77.0.120"

    #
    # Leere Datei: keine Ausgabe, kein Fehler.
    #
    assert lease_lesen([""]) == ""

    print("OK: Der Lease-Leser meldet nur gueltige Adressen")

    print("Alle Tests erfolgreich.")

finally:
    shutil.rmtree(scratch, ignore_errors=True)
