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


class WlanControl:
    """Kapselt privilegierte WLAN-/Netzwerkbefehle."""

    def __init__(self):
        self.logger = logging.getLogger("XRack")

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
                "bridge_configured": False,
                "bridge_enabled": False,
                "share_configured": False,
                "share_enabled": False,
                "console_ip": None,
            }

        names = self.connection_names()
        active = self.active_connection_names()

        bridge_enabled = "XRack-Bridge" in active
        share_enabled = "XRack-Share-eth0" in active

        console_ip = None

        if bridge_enabled:
            console_ip = (
                self.get_dhcp_lease_ip("br0")
                or self.get_connected_client_ip("br0")
            )
        elif share_enabled:
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
            "ap_ssid": (
                self.connection_ssid("XRack-AP")
                if "XRack-AP" in names
                else None
            ),
            "bridge_configured": "XRack-Bridge" in names,
            "bridge_enabled": bridge_enabled,
            "share_configured": "XRack-Share-eth0" in names,
            "share_enabled": share_enabled,
            "console_ip": console_ip,
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

        return self._run_script("xrack-net-ap.sh", ssid, password)

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
