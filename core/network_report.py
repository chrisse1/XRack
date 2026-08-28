"""
Netzwerk-Selbsttest.

Sammelt in einem Durchgang alles, was man braucht, um ein
Netzwerkproblem an XRack einzukreisen - und sagt dazu, was daran nicht
stimmt.

Warum es das gibt: Bis hierher hat der Nutzer bei jedem Problem ein
Dutzend Kommandos von Hand abgesetzt (iw reg get, nmcli, systemctl
cat, ip addr, ...) und die Ausgaben zusammengesucht. Das ist nichts,
was man von jemandem verlangen sollte, der ein Mischpult bedienen
will. Ein Knopf, eine Ausgabe.

Zwei Teile:

  Der Bericht  - was da ist. Reine Bestandsaufnahme.
  Der Befund   - was davon nicht zusammenpasst. Das ist der Teil, der
                 die Arbeit spart.

Alles, was Wurzelrechte braucht, kommt ueber scripts/xrack-net-ap.sh
--report; der Rest wird hier gelesen. Faellt der Skriptaufruf aus,
fehlt nur dieser Abschnitt - der Bericht kommt trotzdem.
"""

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

#
# Ueberschreibbar, damit der Test einen nachgestellten /sys-Baum
# unterschieben kann.
#
SYS_NET = Path("/sys/class/net")


class NetworkReport:
    """
    Baut den Selbsttest.

    Bekommt die Anwendung hereingereicht statt sich ihre Bausteine
    selbst zu holen - so laesst sich der Bericht mit Attrappen
    pruefen, ohne dass ein Funkgeraet in der Naehe sein muss.
    """

    def __init__(self, application, sys_net: Path | None = None):

        self.application = application
        self.sys_net = sys_net or SYS_NET
        self.logger = logging.getLogger("XRack")

    # ----------------------------------------------------------------
    # Einsammeln
    # ----------------------------------------------------------------

    def _lauf(self, befehl: list[str], timeout: float = 10.0) -> str:
        """Ein Kommando ausfuehren; bei jedem Fehler leerer Text."""

        try:

            ergebnis = subprocess.run(
                befehl,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return ergebnis.stdout.strip()

        except Exception:
            return ""

    def funkgeraete(self) -> list[dict]:
        """
        Alle Funkgeraete mit Bauart und MAC.

        Dieselbe Unterscheidung wie scripts/xrack-wifi-iface.sh:
        eingebaut = Heimnetz, USB = Access Point. Sie steht hier
        bewusst noch einmal, weil der Bericht auch dann etwas sagen
        soll, wenn das Skript fehlt - aber sie darf nicht auseinander
        laufen, also im Zweifel beide Stellen aendern.
        """

        gefunden = []

        if not self.sys_net.exists():
            return gefunden

        for geraet in sorted(self.sys_net.iterdir()):

            if not (geraet / "wireless").exists():
                continue

            try:
                ziel = str((geraet / "device").resolve())
            except OSError:
                ziel = ""

            try:
                mac = (geraet / "address").read_text().strip()
            except OSError:
                mac = ""

            gefunden.append({
                "name": geraet.name,
                "usb": "/usb" in ziel,
                "mac": mac,
            })

        return gefunden

    def ap_konfiguration(self) -> dict:
        """
        Die Werte aus /etc/hostapd/xrack.conf - ueber sudo, weil die
        Datei das WLAN-Passwort enthaelt und nur root gehoert.

        Leeres Ergebnis heisst: kein Access Point eingerichtet, oder
        der Aufruf ging nicht durch. Beides ist kein Grund
        abzubrechen.
        """

        skript = Path("scripts") / "xrack-net-ap.sh"

        ausgabe = self._lauf(
            ["sudo", "-n", str(skript.resolve()), "--report"], timeout=15.0
        )

        werte = {}

        for zeile in ausgabe.splitlines():

            if zeile.startswith("# XRack-Unit-Version:"):
                werte["unit_version"] = zeile.split(":", 1)[1].strip()
                continue

            if "=" in zeile:
                schluessel, _, wert = zeile.partition("=")
                werte[schluessel.strip()] = wert.strip()

        return werte

    # ----------------------------------------------------------------
    # Der Befund - was nicht zusammenpasst
    # ----------------------------------------------------------------

    def befunde(self, wlan: dict, ap_konf: dict, geraete: list[dict]) -> list[str]:
        """
        Auffaelligkeiten in Klartext. Leere Liste heisst: alles
        stimmig.

        Bewusst nur Dinge, die sich aus dem Gesammelten sicher
        ableiten lassen - ein Bericht, der Vermutungen als Befunde
        ausgibt, schickt auf falsche Faehrten.
        """

        gefunden = []

        # --- Funkregion ---------------------------------------------

        if not wlan.get("country"):
            gefunden.append(
                "Keine Funkregion gesetzt. Das WLAN kann dadurch per rfkill "
                "gesperrt bleiben, und der Access Point darf nicht auf 5 GHz "
                "senden. Im Einstellungen-Menü unter Netzwerk das WLAN-Land "
                "setzen."
            )

        # --- Access Point auf dem richtigen Funkgeraet? --------------

        stick = next((g for g in geraete if g["usb"]), None)
        eingebaut = next((g for g in geraete if not g["usb"]), None)

        ap_iface = ap_konf.get("interface")

        if ap_iface and eingebaut and ap_iface == eingebaut["name"]:
            gefunden.append(
                f"Der Access Point ist auf '{ap_iface}' eingestellt - das ist "
                "das eingebaute WLAN. Es kann kein 5 GHz und bricht unter "
                "Last ein. Erwartet wird der USB-Stick."
            )

        if ap_iface and stick and ap_iface != stick["name"]:
            gefunden.append(
                f"Der Access Point ist auf '{ap_iface}' eingestellt, der "
                f"USB-Stick heißt aber '{stick['name']}'. Die Namen können "
                "beim Booten tauschen; ein Neustart des Access Points gleicht "
                "das ab."
            )

        # --- Band ---------------------------------------------------

        if ap_konf.get("hw_mode") == "g" and stick:
            gefunden.append(
                "Der Access Point funkt auf 2,4 GHz. Mit gesetzter Funkregion "
                "und einem 5-GHz-fähigen Stick wäre 5 GHz möglich - dafür den "
                "Access Point einmal neu speichern."
            )

        # --- Zustand der systemd-Unit -------------------------------

        erwartet = getattr(self.application.wlan_control, "_erwartete_unit_version", None)

        if erwartet and ap_konf:

            soll = erwartet()
            ist = ap_konf.get("unit_version")

            if soll and ist and soll != ist:
                gefunden.append(
                    f"Die Access-Point-Unit ist auf Stand {ist}, erwartet wird "
                    f"{soll}. XRack frischt sie beim Start auf - erscheint das "
                    "hier weiterhin, ist dabei etwas schiefgegangen."
                )

        # --- Zugangswege --------------------------------------------

        if wlan.get("bridge_enabled") and wlan.get("console_access_enabled"):
            gefunden.append(
                "Beide Zugangswege zum Mischpult sind eingeschaltet. Sie "
                "schließen sich aus - die Netzwerkbuchse kann nur an einem "
                "hängen."
            )

        return gefunden

    # ----------------------------------------------------------------
    # Zusammensetzen
    # ----------------------------------------------------------------

    def erzeugen(self) -> str:
        """Der ganze Bericht als Klartext."""

        anwendung = self.application
        wlan = anwendung.wlan_control.get_status()

        geraete = self.funkgeraete()
        ap_konf = self.ap_konfiguration()

        host, kanaele, herkunft = anwendung._console_host_and_channels()

        zeilen = []
        z = zeilen.append

        z("XRack - Netzwerk-Selbsttest")
        z(f"Erstellt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
        z(f"Version:  {anwendung.config.data.application.version}")
        z("")

        # --- Funkgeraete --------------------------------------------

        z("FUNKGERÄTE")

        if geraete:
            for g in geraete:
                art = "USB-Stick" if g["usb"] else "eingebaut"
                z(f"  {g['name']:8} {art:12} {g['mac']}")
        else:
            z("  keine gefunden")

        z(f"  Funkregion: {wlan.get('country') or 'nicht gesetzt'}")
        z("")

        # --- Access Point -------------------------------------------

        z("ACCESS POINT")
        z(f"  Stick erkannt: {'ja' if wlan.get('ap_hardware') else 'nein'}")
        z(f"  Läuft:         {'ja' if wlan.get('ap_active') else 'nein'}")
        z(f"  Name (SSID):   {wlan.get('ap_ssid') or '-'}")

        if ap_konf:
            band = {"a": "5 GHz", "g": "2,4 GHz"}.get(ap_konf.get("hw_mode", ""), "?")
            z(f"  Funkgerät:     {ap_konf.get('interface', '?')}")
            z(f"  Band/Kanal:    {band}, Kanal {ap_konf.get('channel', '?')}")
            z(f"  Ländercode:    {ap_konf.get('country_code', 'nicht gesetzt')}")
            z(f"  Unit-Stand:    {ap_konf.get('unit_version', 'ohne Marke')}")
        else:
            z("  Konfiguration: nicht lesbar oder nicht eingerichtet")

        z("")

        # --- Heimnetz -----------------------------------------------

        z("HEIMNETZ")
        z(f"  Verbunden:     {'ja' if wlan.get('home_active') else 'nein'}")
        z(f"  Netz (SSID):   {wlan.get('home_ssid') or '-'}")
        z("")

        # --- Zugangsweg zum Pult ------------------------------------

        z("ZUGANGSWEG ZUM MISCHPULT")
        z(f"  Über Access Point:  {'an' if wlan.get('bridge_enabled') else 'aus'}")
        z(f"  Aus dem Heimnetz:   {'an' if wlan.get('console_access_enabled') else 'aus'}")

        bruecke = anwendung.wlan_control.console_port_bridged()

        z("  Netzwerkbuchse:     " + {
            True: "hängt in der Bridge",
            False: "hängt in keiner Bridge",
            None: "nicht feststellbar",
        }[bruecke])
        z("")

        # --- Mischpult ----------------------------------------------

        z("MISCHPULT")

        if host:
            z(f"  Adresse:   {host}")
            z(f"  Herkunft:  " + {
                "manual": "von Hand eingetragen",
                "lease": "aus der Vergabeliste des Pi",
                "discovered": "per Rundruf gefunden",
            }.get(herkunft, herkunft))
            z(f"  Antwortet: {'ja' if kanaele > 0 else 'nein'}")

            if kanaele > 0:
                z(f"  Kanalzüge: {kanaele}")
        else:
            z("  keine Adresse - nicht gefunden")

        z("")

        # --- Adressen -----------------------------------------------

        adressen = self._lauf(["ip", "-br", "addr"])

        if adressen:
            z("ADRESSEN")
            for zeile in adressen.splitlines():
                if not zeile.startswith("lo "):
                    z("  " + " ".join(zeile.split()))
            z("")

        # --- Aktive Profile -----------------------------------------

        profile = self._lauf(
            ["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"]
        )

        if profile:
            z("AKTIVE NETZWERKPROFILE")
            for zeile in profile.splitlines():
                if zeile and not zeile.startswith("lo:"):
                    z("  " + zeile.replace(":", "  auf  ", 1))
            z("")

        # --- Befund -------------------------------------------------

        gefunden = self.befunde(wlan, ap_konf, geraete)

        z("BEFUND")

        if gefunden:
            for eintrag in gefunden:
                z("  - " + eintrag)
        else:
            z("  Nichts Auffälliges gefunden.")

        return "\n".join(zeilen) + "\n"
