"""
WLAN-Steuerung (Heimnetz-Client, Access Point, Ethernet-Bridge).

XRack läuft nicht als root. Änderungen an den NetworkManager-
Verbindungsprofilen laufen über feste, per sudo freigegebene
Wrapper-Skripte (siehe scripts/), die "install.sh" einrichtet
(/etc/sudoers.d/xrack) - jedes Skript kapselt genau einen engen
nmcli-Vorgang, SSID/Passwort werden dabei stets als eigenständige
Prozessargumente übergeben (nie über eine Shell zusammengebaut).
"""

import logging
import shutil
import subprocess
from pathlib import Path

#
# Name des NetworkManager-Profils hinter "Konsole aus dem Heimnetz
# erreichbar machen". Wird auch von
# Application._reconcile_port_forward() gebraucht, um abzuleiten, ob
# die Portweiterleitung stehen soll - darum hier einmal zentral.
#
SHARE_CONNECTION = "XRack-Share-eth0"

#
# Name des NetworkManager-Profils, das das Ethernet-Interface in die
# Bridge einhängt ("Konsole über XRacks Access Point erreichbar
# machen"). Der Access Point selbst ist hier bewusst kein Thema mehr:
# Er läuft über hostapd und hängt dauerhaft in derselben Bridge
# (siehe install.sh) - umgeschaltet wird nur noch eth0.
#
BRIDGE_PORT_CONNECTION = "XRack-Bridge-eth0"

#
# Die Bridge selbst. Sie trägt IP, DHCP und Internet-Weitergabe für
# alles, was am Access Point hängt, und läuft deshalb dauerhaft.
#
BRIDGE_CONNECTION = "XRack-Bridge"

#
# Die Geräte hinter den Profilen. Gebraucht werden sie, um beim Kernel
# nachzusehen statt bei NetworkManager - siehe console_port_bridged().
#
BRIDGE_DEVICE = "br0"
CONSOLE_DEVICE = "eth0"

#
# Wo der Kernel seine Netzwerkgeräte auflistet. Als Konstante, damit
# der Test einen nachgestellten Baum unterschieben kann.
#
SYS_NET = Path("/sys/class/net")


class WlanControl:
    """Kapselt privilegierte WLAN-/Netzwerkbefehle."""

    def __init__(self):
        self.logger = logging.getLogger("XRack")

        #
        # Die SSID des Access Points steht seit der Umstellung auf
        # hostapd in einer nur für root lesbaren Datei (sie enthält
        # auch das Passwort) und wird deshalb über ein sudo-Skript
        # gelesen. get_status() wird aber häufig aufgerufen - unter
        # anderem bei jeder Suche nach der Konsolen-IP -, und ein
        # Prozessstart je Aufruf wäre dort verschwendete Zeit.
        # Ändern kann sich der Name ohnehin nur über set_ap_wifi(),
        # und genau dort wird der Zwischenspeicher verworfen.
        #
        self._ap_ssid: str | None = None
        self._ap_ssid_gelesen = False

    @property
    def available(self) -> bool:
        """
        True, wenn NetworkManager (nmcli) auf diesem System
        vorhanden ist.
        """

        return shutil.which("nmcli") is not None

    def _nmcli(self, *args: str) -> str | None:
        """
        Führt einen lesenden nmcli-Befehl aus (kein sudo nötig -
        NetworkManager erlaubt normalen Nutzern das Lesen
        nicht-geheimer Verbindungsdaten). Liefert None bei Fehlern.
        """

        try:

            result = subprocess.run(
                ["nmcli", *args],
                capture_output=True,
                text=True,
                timeout=10,
            )

        except Exception:
            return None

        if result.returncode != 0:
            return None

        return result.stdout

    def connection_names(self) -> list[str]:
        """
        Liefert die Namen aller vorhandenen NetworkManager-
        Verbindungsprofile.
        """

        output = self._nmcli("-t", "-f", "NAME", "connection", "show")

        if output is None:
            return []

        return [line for line in output.splitlines() if line]

    def active_connection_names(self) -> list[str]:
        """
        Liefert die Namen aller aktuell aktiven Verbindungsprofile.
        """

        output = self._nmcli(
            "-t", "-f", "NAME", "connection", "show", "--active"
        )

        if output is None:
            return []

        return [line for line in output.splitlines() if line]

    def connection_ssid(self, name: str) -> str | None:
        """
        Liefert die SSID eines vorhandenen WLAN-Verbindungsprofils.
        """

        output = self._nmcli(
            "-g", "802-11-wireless.ssid", "connection", "show", name
        )

        if output is None:
            return None

        return output.strip() or None

    def ap_ssid(self) -> str | None:
        """
        Liefert den Namen des eingerichteten Access Points, oder
        None, wenn keiner eingerichtet ist.
        """

        if not self._ap_ssid_gelesen:

            self._ap_ssid = self._run_script_read("xrack-ap-info.sh")

            #
            # Auf einem Gerät, das die neue Fassung eingespielt, aber
            # install.sh noch nicht erneut durchlaufen hat, gibt es
            # die sudo-Freigabe für dieses Skript noch nicht. Dann
            # gilt der alte Weg: der Access Point aus NetworkManager.
            # Ohne diesen Rückfall verschwände der Name des Access
            # Points nach einem Update einfach aus der Anzeige.
            #
            if self._ap_ssid is None and "XRack-AP" in self.connection_names():
                self._ap_ssid = self.connection_ssid("XRack-AP")

            self._ap_ssid_gelesen = True

        return self._ap_ssid

    def ap_hardware_present(self) -> bool:
        """
        True, wenn ein Funkgerät für einen Access Point da ist - also
        ein zweites, per USB angeschlossenes.

        Dieselbe Regel wie in scripts/xrack-wifi-iface.sh (dort wird
        sie für install.sh und die Einrichtung gebraucht, hier für die
        Anzeige): Das eingebaute WLAN geht ins Heimnetz, der USB-Stick
        spannt den Access Point auf. Ändert sich die Regel, muss sie
        an beiden Stellen geändert werden.

        Gelesen wird der Kernel statt NetworkManager, denn genau
        dieses Gerät wird NetworkManager ja entzogen, sobald hostapd
        es übernimmt.
        """

        if not SYS_NET.exists():
            return False

        for geraet in sorted(SYS_NET.iterdir()):

            if not (geraet / "wireless").exists():
                continue

            try:
                ziel = (geraet / "device").resolve()
            except OSError:
                continue

            if "/usb" in str(ziel):
                return True

        return False

    def ap_running(self) -> bool:
        """
        True, wenn der Access Point tatsächlich funkt.

        Zwei Wege, weil es zwei geben kann: hostapd (der Normalfall)
        und das alte NetworkManager-Profil (der Rückfallweg, siehe
        scripts/xrack-ap-setup.sh).
        """

        try:

            ergebnis = subprocess.run(
                ["systemctl", "is-active", "--quiet", "xrack-hostapd.service"],
                capture_output=True,
                timeout=5,
            )

            if ergebnis.returncode == 0:
                return True

        except Exception:
            pass

        return "XRack-AP" in self.active_connection_names()

    def console_port_bridged(self) -> bool | None:
        """
        True, wenn die Netzwerkbuchse tatsächlich in der Bridge hängt.

        Warum nicht NetworkManager fragen: Dessen Buchführung sagt nur,
        ob das Profil aktiviert wurde - nicht, ob das Gerät auch
        wirklich in der Bridge steckt. Genau das kann auseinanderlaufen,
        und der Schaden ist dann heimtückisch: Die DHCP-Vergabeliste von
        br0 enthält den Eintrag des Pults noch stundenlang weiter (die
        Lease läuft ja nicht sofort ab). XRack meldete also eine
        Konsolen-IP, hinter der niemand mehr antwortet - und das sieht
        aus, als sei das Pult erreichbar, obwohl es das nicht ist.

        Der Kernel weiß es genau: /sys/class/net/eth0/master ist ein
        Verweis auf das Gerät, in dem die Buchse hängt - und existiert
        gar nicht, wenn sie in keiner Bridge steckt.

        Liefert None, wenn sich das nicht feststellen lässt (kein
        Linux, kein solches Gerät). Dann entscheidet weiter
        NetworkManager.
        """

        pfad = SYS_NET / CONSOLE_DEVICE

        if not pfad.exists():
            return None

        master = pfad / "master"

        if not master.is_symlink():
            #
            # Buchse vorhanden, aber in keiner Bridge - das ist eine
            # eindeutige Antwort, kein "weiß nicht".
            #
            return False

        try:
            return master.resolve().name == BRIDGE_DEVICE
        except OSError:
            return None

    def get_connected_client_ip(self, interface: str) -> str | None:
        """
        Liefert die IP-Adresse des zuletzt über `interface`
        erreichbaren Geräts (z.B. das per Ethernet angeschlossene
        Mischpult) aus der Nachbartabelle (ARP) - ein normaler,
        unprivilegierter Befehl, kein sudo nötig.
        """

        try:

            result = subprocess.run(
                ["ip", "-4", "neigh", "show", "dev", interface],
                capture_output=True,
                text=True,
                timeout=5,
            )

        except Exception:
            return None

        if result.returncode != 0:
            return None

        #
        # Format je Zeile: "<ip> dev <iface> lladdr <mac> <state>".
        # Nur Zustände mit einer tatsächlich (noch) gültigen Zuordnung
        # zählen - FAILED/INCOMPLETE bedeuten "aktuell nicht
        # erreichbar" und werden ignoriert.
        #
        for line in result.stdout.splitlines():

            parts = line.split()

            if not parts:
                continue

            if parts[-1] in ("REACHABLE", "STALE", "DELAY", "PROBE", "PERMANENT"):
                return parts[0]

        return None

    def get_dhcp_lease_ip(self, interface: str) -> str | None:
        """
        Liefert die zuletzt von NetworkManagers eingebautem dnsmasq
        (Modus "ipv4.method shared") auf `interface` vergebene
        DHCP-Lease-IP - zuverlässiger als get_connected_client_ip(),
        da sie sofort bei der Vergabe feststeht und nicht erst
        späteren IP-Verkehr voraussetzt. Die Lease-Datei liegt unter
        /var/lib/NetworkManager/ und ist nur für root lesbar, daher
        über das feste sudo-Skript.
        """

        output = self._run_script_read(
            "xrack-dhcp-lease.sh", interface
        )

        return output or None

    def get_home_ip(self) -> str | None:
        """
        Liefert die IP, unter der XRack selbst im Heimnetz erreichbar
        ist - genau die Adresse, die der Nutzer in seine Steuerungs-App
        einträgt, wenn die Konsole aus dem Heimnetz erreichbar gemacht
        wurde (die Weiterleitung läuft über XRacks eigene IP, nicht
        über die der Konsole).

        Liefert None, wenn die Heimnetz-Verbindung nicht aktiv ist.
        """

        output = self._nmcli(
            "-g", "IP4.ADDRESS", "connection", "show", "XRack-Home"
        )

        if not output:
            return None

        #
        # nmcli liefert die Adresse mit Präfixlänge ("192.168.1.22/24")
        # und bei mehreren Adressen mehrere Zeilen - die erste genügt.
        #
        first = output.strip().splitlines()[0] if output.strip() else ""

        address = first.split("/")[0].strip()

        return address or None

    def get_status(self) -> dict:
        """
        Liefert den aktuellen (nicht-geheimen) WLAN-Status fürs
        Einstellungs-Modal.
        """

        if not self.available:
            return {
                "available": False,
                "home_ssid": None,
                "ap_ssid": None,
                "ap_hardware": False,
                "ap_active": False,
                "home_active": False,
                "bridge_configured": False,
                "bridge_enabled": False,
                "console_access_configured": False,
                "console_access_enabled": False,
                "console_ip": None,
                "home_ip": None,
            }

        names = self.connection_names()
        active = self.active_connection_names()

        #
        # "Konsole über XRacks Access Point erreichbar" heißt genau:
        # Hängt eth0 in der Bridge? Die Bridge selbst läuft dauerhaft
        # (der Access Point funkt hinein) und taugt deshalb nicht als
        # Anzeige dafür.
        #
        # Gefragt wird der Kernel, nicht NetworkManager: Ein aktiviertes
        # Profil heißt noch nicht, dass die Buchse auch wirklich in der
        # Bridge steckt (siehe console_port_bridged). Nur wenn sich das
        # nicht feststellen lässt, zählt wieder das Profil.
        #
        bridged = self.console_port_bridged()

        bridge_enabled = (
            bridged
            if bridged is not None
            else BRIDGE_PORT_CONNECTION in active
        )

        #
        # "Konsole aus dem Heimnetz erreichbar machen" ist technisch die
        # Ethernet-Freigabe (XRack-Share-eth0) plus die Portweiterleitung.
        # Die Weiterleitung wird nicht separat gemerkt, sondern von
        # Application._reconcile_port_forward() aus diesem Zustand
        # abgeleitet - so können Anzeige und Wirklichkeit nicht
        # auseinanderlaufen.
        #
        console_access_enabled = SHARE_CONNECTION in active

        ap_hardware = self.ap_hardware_present()
        ap_active = self.ap_running() if ap_hardware else False

        console_ip = None

        if bridge_enabled:
            console_ip = (
                self.get_dhcp_lease_ip("br0")
                or self.get_connected_client_ip("br0")
            )
        elif console_access_enabled:
            console_ip = (
                self.get_dhcp_lease_ip("eth0")
                or self.get_connected_client_ip("eth0")
            )

        return {
            "available": True,
            "home_ssid": (
                self.connection_ssid("XRack-Home")
                if "XRack-Home" in names
                else None
            ),
            "ap_ssid": self.ap_ssid(),

            #
            # Steckt ueberhaupt ein USB-WLAN-Stick? Ohne den gibt es
            # keinen Access Point, und die Oberflaeche sagt das
            # deutlich, statt eine Eingabemaske anzubieten, die
            # nirgends hinfuehrt.
            #
            "ap_hardware": ap_hardware,

            #
            # Funkt er auch gerade? Davon haengt ab, ob "Konsole ueber
            # XRacks Access Point" ueberhaupt sinnvoll ist.
            #
            "ap_active": ap_active,

            #
            # Und besteht eine Verbindung ins Heimnetz? Ohne die gibt
            # es nichts, worueber die Konsole aus dem Heimnetz
            # erreichbar waere.
            #
            "home_active": "XRack-Home" in active,
            "bridge_configured": (
                BRIDGE_PORT_CONNECTION in names
                and BRIDGE_CONNECTION in names
            ),
            "bridge_enabled": bridge_enabled,
            "console_access_configured": SHARE_CONNECTION in names,
            "console_access_enabled": console_access_enabled,
            "console_ip": console_ip,
            "home_ip": self.get_home_ip(),
        }

    def _run_script(self, name: str, *args: str) -> tuple[bool, str]:

        script = Path("scripts") / name

        try:

            result = subprocess.run(
                ["sudo", "-n", str(script.resolve()), *args],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:

                message = result.stderr.strip() or result.stdout.strip()

                self.logger.error(
                    "%s fehlgeschlagen: %s",
                    name,
                    message,
                )

                return False, message

            return True, ""

        except subprocess.TimeoutExpired:

            self.logger.error(
                "%s: Zeitüberschreitung.",
                name,
            )

            return False, "Zeitüberschreitung."

        except Exception as exc:

            self.logger.exception(
                "%s fehlgeschlagen: %s",
                name,
                exc,
            )

            return False, str(exc)

    def _run_script_read(self, name: str, *args: str) -> str | None:
        """
        Wie _run_script(), aber für rein lesende Skripte, die einen
        Wert auf stdout ausgeben - liefert die getrimmte
        Standardausgabe bei Erfolg, sonst None (kein Logging bei
        Fehlschlag - eine leere/fehlende Lease-Datei ist normal,
        solange nichts angeschlossen ist).
        """

        script = Path("scripts") / name

        try:

            result = subprocess.run(
                ["sudo", "-n", str(script.resolve()), *args],
                capture_output=True,
                text=True,
                timeout=10,
            )

        except Exception:
            return None

        if result.returncode != 0:
            return None

        return result.stdout.strip() or None

    def set_home_wifi(self, ssid: str, password: str) -> tuple[bool, str]:
        """
        Setzt SSID/Passwort der Heimnetz-Verbindung neu.
        """

        return self._run_script("xrack-net-home.sh", ssid, password)

    def set_ap_wifi(self, ssid: str, password: str) -> tuple[bool, str]:
        """
        Setzt SSID/Passwort des Access Points neu.
        """

        erfolg, meldung = self._run_script("xrack-net-ap.sh", ssid, password)

        #
        # Auch im Fehlerfall verwerfen: Das Skript stellt bei einem
        # Fehlschlag zwar die alten Werte wieder her, aber wenn schon
        # etwas schiefging, ist neu nachsehen billiger als raten.
        #
        self._ap_ssid_gelesen = False

        return erfolg, meldung

    def set_bridge(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet die Ethernet+Access-Point-Bridge an oder aus. Schließt
        sich mit der Ethernet+Heimnetz-Freigabe (set_share()) aus -
        beide beanspruchen dasselbe Ethernet-Interface, das
        Umschalt-Skript deaktiviert die jeweils andere Betriebsart
        automatisch mit.
        """

        return self._run_script(
            "xrack-bridge-toggle.sh",
            "on" if enabled else "off",
        )

    def set_share(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet die Ethernet+Heimnetz-Freigabe an oder aus (NAT statt
        echter Bridge - siehe scripts/xrack-share-toggle.sh für die
        Begründung). Schließt sich mit der Ethernet+Access-Point-
        Bridge (set_bridge()) aus.
        """

        return self._run_script(
            "xrack-share-toggle.sh",
            "on" if enabled else "off",
        )

    def reconnect_console(self) -> tuple[bool, str]:
        """
        Trennt die Kabelverbindung kurz und stellt sie wieder her -
        macht also das nach, was ein Ab- und Anstecken des Kabels
        bewirkt (siehe scripts/xrack-link-bounce.sh).

        Warum das von Hand auslösbar sein muss: Beim Umschalten der
        Betriebsart macht das Umschalt-Skript das ohnehin. Nur passiert
        genau das eben nicht, wenn sich sonst etwas ändert - das Pult
        wird später eingesteckt, es oder der Pi wird neu gestartet,
        oder das Pult hält noch eine Adresse aus einem früheren Netz.
        Dann half bisher nur: hinter das Gerät greifen und das Kabel
        ziehen. Genau das macht dieser Weg, ohne aufzustehen.
        """

        return self._run_script("xrack-link-bounce.sh", "eth0")

    def set_port_forward(
        self,
        enabled: bool,
        console_ip: str | None,
    ) -> tuple[bool, str]:
        """
        Schaltet die Portweiterleitung (macht die per Bridge/Freigabe
        angeschlossene Konsole über UDP 10023/10024 aus dem Heimnetz
        erreichbar) an oder aus. `console_ip` ist beim Einschalten
        Pflicht (siehe get_status()["console_ip"]).
        """

        if enabled:

            if not console_ip:
                return False, "Keine Konsolen-IP bekannt."

            return self._run_script(
                "xrack-port-forward.sh", "on", console_ip
            )

        return self._run_script("xrack-port-forward.sh", "off")
