#!/usr/bin/env python3
"""
Prüft, dass die Suche nach der Pult-Adresse nicht im Sekundentakt
sudo aufruft.

Anlass ist das Journal des Geräts. Beim Umschalten der Freigabe standen
dort zwölf Zeilen in sechs Sekunden:

    sudo[6452]: pi : COMMAND=/home/pi/XRack/scripts/xrack-dhcp-lease.sh eth0
    sudo[6486]: pi : COMMAND=/home/pi/XRack/scripts/xrack-dhcp-lease.sh eth0
    ...

Die Ursache: Die Kanalzug-Karte fragt jede Sekunde nach dem Pult, und
dahinter lag der volle WLAN-Statusbericht - rund acht Aufrufe von
nmcli und Hilfsskripten, darunter dieser sudo-Lauf mit eigener
PAM-Sitzung. Das funktioniert, macht das Journal aber unlesbar, und
genau darin haben wir dann einen Fehler gesucht.

Zwei Dinge müssen jetzt stimmen, und das zweite ist das wichtigere:

  1. Im Takt wird nicht mehr nachgefragt als nötig.
  2. Nach einem Umschalten steht trotzdem sofort die neue Adresse da -
     ein Puffer, der die Anzeige verzögert, wäre ein neuer Fehler.
"""

import logging
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

#
# alsaaudio gibt es hier nicht - Application zieht die Audiokette mit.
#
fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE", "PCM_FORMAT_S24_LE", "PCM_FORMAT_S24_3LE",
    "PCM_FORMAT_S32_LE", "PCM_CAPTURE", "PCM_PLAYBACK", "PCM_NORMAL",
):
    setattr(fake_alsaaudio, name, 0)

fake_alsaaudio.ALSAAudioError = Exception
fake_alsaaudio.cards = lambda: []
fake_alsaaudio.pcms = lambda *a, **k: []
fake_alsaaudio.PCM = type("FakePCM", (), {"__init__": lambda self, *a, **k: None})
sys.modules["alsaaudio"] = fake_alsaaudio

from core.application import Application  # noqa: E402
from core.wlan_control import (  # noqa: E402
    BRIDGE_PORT_CONNECTION,
    SHARE_CONNECTION,
    WlanControl,
)


# ====================================================================
# 1. Ohne Kabelweg wird gar nicht erst nach einer Lease gefragt
#
# Der häufigste Fall: Pult und Pi hängen an einem Router. Dann gibt es
# keine Vergabeliste des Pi - und trotzdem lief bisher jede Sekunde
# der sudo-Lauf.
# ====================================================================

class Zaehlend(WlanControl):
    """Zählt mit, was nach draußen geht - ohne es zu tun."""

    def __init__(self, bridged=False, aktiv=(), lease="10.77.0.120"):

        self.leases = 0
        self.nmcli = 0
        self.nachbarn = 0

        self._bridged = bridged
        self._aktiv = list(aktiv)
        self._lease = lease

    @property
    def available(self):
        return True

    def console_port_bridged(self):
        return self._bridged

    def active_connection_names(self):
        self.nmcli += 1
        return list(self._aktiv)

    def get_dhcp_lease_ip(self, interface):
        self.leases += 1
        return self._lease

    def get_connected_client_ip(self, interface):
        self.nachbarn += 1
        return None


ohne_kabel = Zaehlend(bridged=False, aktiv=[])

assert ohne_kabel.konsolen_lease_ip() is None

assert ohne_kabel.leases == 0, (
    f"Ohne Kabelweg wurde {ohne_kabel.leases} Mal die Vergabeliste "
    f"gelesen - dafür läuft jedes Mal sudo, und zu holen ist dort "
    f"nichts."
)

print("OK: Ohne Kabelweg kein sudo-Lauf")


#
# Mit Freigabe dagegen genau einmal - und der Kernel-Blick auf die
# Bridge kostet keinen Unterprozess.
#
mit_freigabe = Zaehlend(bridged=False, aktiv=[SHARE_CONNECTION])

assert mit_freigabe.konsolen_lease_ip() == "10.77.0.120"
assert mit_freigabe.leases == 1, mit_freigabe.leases

mit_bridge = Zaehlend(bridged=True)

assert mit_bridge.konsolen_lease_ip() == "10.77.0.120"
assert mit_bridge.leases == 1
assert mit_bridge.nmcli == 0, (
    "Bei gebrückter Buchse wurde trotzdem nmcli gefragt - der Kernel "
    "hatte die Antwort schon."
)

print("OK: Mit Kabelweg genau eine Abfrage, und nmcli nur wenn nötig")


# ====================================================================
# 2. Der Takt fragt nicht jede Sekunde nach
# ====================================================================

class PultAttrappe:
    """Zählt, wie oft die Adresse wirklich ermittelt wird."""

    def __init__(self):
        self.abfragen = 0

    def konsolen_lease_ip(self):
        self.abfragen += 1
        return "10.77.0.120"


class Speicher:

    def __init__(self, werte=None):
        self.werte = dict(werte or {})

    def get(self, schluessel, vorgabe=None):
        return self.werte.get(schluessel, vorgabe)

    def set(self, schluessel, wert):
        self.werte[schluessel] = wert


class Pultsteuerung:

    def __init__(self):
        self.kanaele = 18

    def channel_count(self, host):
        return self.kanaele

    def discover(self, force=False):
        return None

    def detect_reset(self):
        pass


def rack() -> Application:
    """
    Eine Anwendung, die nur so weit aufgebaut ist, wie die Frage nach
    dem Pult reicht - die echte zieht ALSA, psutil und das Pult mit.
    """

    selbst = object.__new__(Application)

    selbst.wlan_control = PultAttrappe()
    selbst.state_store = Speicher()
    selbst.console_control = Pultsteuerung()

    selbst._lease_ip = None
    selbst._lease_geprueft = 0.0

    #
    # Geschrieben wird nur ins Protokoll - hierhin, wo es niemanden
    # stoert.
    #
    selbst.logger = logging.getLogger("XRack-Versuch")

    return selbst


proband = rack()

#
# Zwanzig Abfragen, wie zwanzig Sekunden Kanalzug-Karte.
#
for _ in range(20):
    host, kanaele, quelle = proband._console_host_and_channels()

assert host == "10.77.0.120" and quelle == "lease", (host, quelle)

assert proband.wlan_control.abfragen == 1, (
    f"Zwanzig Abfragen haben {proband.wlan_control.abfragen} Mal nach "
    f"der Vergabeliste gefragt. Genau das stand als sudo-Flut im "
    f"Journal des Geräts."
)

print("OK: Zwanzig Abfragen im Takt ergeben eine einzige Nachfrage")


# ====================================================================
# 3. Nach dem Umschalten gilt sofort die neue Adresse
#
# Das ist der Punkt, an dem ein Puffer zum Fehler wird: Wer die
# Freigabe umschaltet, darf nicht zehn Sekunden die alte Adresse
# sehen.
# ====================================================================

for name, umschalten in (
    ("Bridge", lambda r: r.set_bridge(True)),
    ("Freigabe", lambda r: r.set_console_access(True)),
    ("Pult-IP von Hand", lambda r: r.set_console_host("")),
):

    proband = rack()

    #
    # Einmal fragen - danach steckt der alte Wert im Puffer.
    #
    proband._console_host_and_channels()

    vorher = proband.wlan_control.abfragen

    #
    # Umschalten. Die Attrappen darunter tun nichts, aber der Puffer
    # muss weg sein.
    #
    proband.wlan_control.set_bridge = lambda *a, **k: (True, "")
    proband.wlan_control.set_share = lambda *a, **k: (True, "")
    proband.wlan_control.set_port_forward = lambda *a, **k: (True, "")
    proband._port_forward_applied_ip = None

    umschalten(proband)

    proband._console_host_and_channels()

    assert proband.wlan_control.abfragen == vorher + 1, (
        f"Nach '{name}' wurde die Adresse nicht neu ermittelt - die "
        f"Karte zeigte bis zu zehn Sekunden die alte, und das sieht "
        f"aus wie ein Fehler."
    )

print("OK: Nach Bridge, Freigabe und Handeintrag wird neu nachgesehen")


# ====================================================================
# 4. Eine von Hand eingetragene Adresse fragt nie nach
# ====================================================================

proband = rack()
proband.state_store.set("console_ip_manual", "192.168.1.99")

for _ in range(5):
    host, _, quelle = proband._console_host_and_channels()

assert host == "192.168.1.99" and quelle == "manual", (host, quelle)

assert proband.wlan_control.abfragen == 0, (
    "Bei einer von Hand eingetragenen Adresse wird trotzdem die "
    "Vergabeliste gelesen."
)

print("OK: Eine eingetragene Adresse kostet keine Abfrage")


print("Alle Tests zur Pult-Adresse erfolgreich.")
