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
            }

        names = self.connection_names()
        active = self.active_connection_names()

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
            "bridge_enabled": "XRack-Bridge" in active,
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
        Schaltet die Ethernet+Access-Point-Bridge an oder aus.
        """

        return self._run_script(
            "xrack-bridge-toggle.sh",
            "on" if enabled else "off",
        )
