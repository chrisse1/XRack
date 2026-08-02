#!/usr/bin/env python3
"""
XRack Bluetooth-Kopplungs-Agent ("Just Works", ohne PIN-/Code-
Bestätigung).

Ersetzt bt-agent aus dem bluez-tools-Paket (Stand 2017), das sich
zwar erfolgreich als Standard-Agent registriert, Kopplungsanfragen
gegen ein aktuelles BlueZ (getestet: 5.82) aber offenbar nicht
zuverlässig beantwortet - iOS zeigte einen Bestätigungscode an, den
niemand automatisch annahm, wodurch die Kopplung fehlschlug.

Diese eigene, minimale Implementierung folgt exakt dem offiziellen
BlueZ-Beispielagenten (bluez/test/simple-agent) und beantwortet jede
Anfrage sofort automatisch positiv - keine Rückfrage kommt beim
Nutzer an, egal welche Kopplungsmethode das jeweilige Gerät verlangt.
Läuft dauerhaft als eigener systemd-Dienst (siehe install.sh), nicht
über die XRack-Python-Umgebung (.venv), da python3-dbus/python3-gi
System-Pakete sind.
"""

import sys

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

AGENT_PATH = "/xrack/agent"
CAPABILITY = "NoInputNoOutput"


class Agent(dbus.service.Object):
    """Beantwortet jede Kopplungsanfrage automatisch positiv."""

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        print("Release", flush=True)

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        print(f"AuthorizeService: {device} {uuid} -> ok", flush=True)

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        print(f"RequestPinCode: {device} -> 0000", flush=True)
        return "0000"

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        print(f"RequestPasskey: {device} -> 0", flush=True)
        return dbus.UInt32(0)

    @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        print(f"DisplayPasskey: {device} {passkey:06d} ({entered})", flush=True)

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def DisplayPinCode(self, device, pincode):
        print(f"DisplayPinCode: {device} {pincode}", flush=True)

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        print(f"RequestConfirmation: {device} {passkey:06d} -> ok", flush=True)

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        print(f"RequestAuthorization: {device} -> ok", flush=True)

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        print("Cancel", flush=True)


def main() -> int:

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    bus = dbus.SystemBus()

    Agent(bus, AGENT_PATH)

    manager = dbus.Interface(
        bus.get_object("org.bluez", "/org/bluez"),
        "org.bluez.AgentManager1",
    )

    manager.RegisterAgent(AGENT_PATH, CAPABILITY)
    manager.RequestDefaultAgent(AGENT_PATH)

    print(f"Agent registriert ({CAPABILITY}) und als Standard gesetzt.", flush=True)

    GLib.MainLoop().run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
