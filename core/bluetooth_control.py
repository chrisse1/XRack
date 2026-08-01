"""
Bluetooth-Steuerung (Adapter an/aus, Koppeln, Geräte vergessen).

XRack läuft nicht als root. Änderungen am Bluetooth-Adapter laufen
über feste, per sudo freigegebene Wrapper-Skripte (siehe scripts/),
die "install.sh" einrichtet (/etc/sudoers.d/xrack) - genau wie beim
WLAN (core/wlan_control.py). Lesende bluetoothctl-Aufrufe brauchen
kein sudo, BlueZ erlaubt normalen Nutzern das Lesen des Adapter-/
Geräte-Status über den System-D-Bus.
"""

import logging
import shutil
import subprocess
from pathlib import Path


class BluetoothControl:
    """Kapselt privilegierte Bluetooth-Befehle."""

    def __init__(self):
        self.logger = logging.getLogger("XRack")

    @property
    def available(self) -> bool:
        """
        True, wenn bluetoothctl (BlueZ) auf diesem System vorhanden
        ist.
        """

        return shutil.which("bluetoothctl") is not None

    def _bluetoothctl(self, *args: str) -> str | None:
        """
        Führt einen lesenden bluetoothctl-Befehl aus (kein sudo
        nötig). Liefert None bei Fehlern.
        """

        try:

            result = subprocess.run(
                ["bluetoothctl", *args],
                capture_output=True,
                text=True,
                timeout=10,
            )

        except Exception:
            return None

        if result.returncode != 0:
            return None

        return result.stdout

    def _paired_devices(self) -> list[tuple[str, str]]:
        """
        Liefert (MAC, Name) aller gekoppelten Geräte.
        """

        return self._parse_device_list(
            self._bluetoothctl("devices", "Paired")
        )

    def _connected_devices(self) -> list[tuple[str, str]]:
        """
        Liefert (MAC, Name) aller aktuell verbundenen Geräte.
        """

        return self._parse_device_list(
            self._bluetoothctl("devices", "Connected")
        )

    @staticmethod
    def _parse_device_list(output: str | None) -> list[tuple[str, str]]:

        if not output:
            return []

        devices = []

        for line in output.splitlines():

            if not line.startswith("Device "):
                continue

            parts = line.split(" ", 2)

            if len(parts) < 2:
                continue

            mac = parts[1]
            name = parts[2] if len(parts) > 2 else mac

            devices.append((mac, name))

        return devices

    def connected_device_mac(self) -> str | None:
        """
        Liefert die MAC-Adresse des ersten aktuell verbundenen
        Geräts (für den Audiostream, siehe player/bluetooth_player.py).
        """

        connected = self._connected_devices()

        return connected[0][0] if connected else None

    def connected_device_name(self) -> str | None:
        """
        Liefert den Namen des ersten aktuell verbundenen Geräts.
        """

        connected = self._connected_devices()

        return connected[0][1] if connected else None

    def paired_device_name(self) -> str | None:
        """
        Liefert den Namen des ersten gekoppelten Geräts (unabhängig
        davon, ob es gerade verbunden ist).
        """

        paired = self._paired_devices()

        return paired[0][1] if paired else None

    def get_status(self) -> dict:
        """
        Liefert den aktuellen Bluetooth-Status fürs Webinterface.
        """

        if not self.available:
            return {
                "available": False,
                "powered": False,
                "discoverable": False,
                "paired_device": None,
            }

        info = self._bluetoothctl("show") or ""

        return {
            "available": True,
            "powered": "Powered: yes" in info,
            "discoverable": "Discoverable: yes" in info,
            "paired_device": (
                self.connected_device_name()
                or self.paired_device_name()
            ),
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

    def set_power(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet den Bluetooth-Adapter an oder aus.
        """

        return self._run_script(
            "xrack-bt-power.sh",
            "on" if enabled else "off",
        )

    def start_pairing(self) -> tuple[bool, str]:
        """
        Macht XRack für 120 Sekunden koppelbar (Just-Works, ohne
        PIN-Bestätigung - der laufende Kopplungs-Agent, siehe
        install.sh, nimmt eingehende Kopplungsanfragen automatisch
        an).
        """

        return self._run_script("xrack-bt-pair.sh")

    def forget_devices(self) -> tuple[bool, str]:
        """
        Entfernt alle gekoppelten Bluetooth-Geräte.
        """

        return self._run_script("xrack-bt-forget.sh")
