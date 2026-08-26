"""
Prüft, woher XRack weiß, ob die Netzwerkbuchse in der Bridge hängt.

Hintergrund - der Fall vom Gerät:

    $ bridge link show
    4: wlan1: ... master br0 state forwarding

eth0 fehlt hier, hängt also in keiner Bridge. Die DHCP-Vergabeliste
von br0 enthielt den Eintrag des Pults trotzdem noch:

    1787782470 e8:eb:1b:c1:85:c8 10.42.0.120 XR18-C1-85-C8 *

Und zwar völlig zu Recht - die Lease lief erst 45 Minuten später ab.
Wer in dieser Lage die Vergabeliste von br0 liest, bekommt eine
Adresse, hinter der niemand mehr antwortet. Das sieht aus, als sei
das Pult erreichbar, obwohl es das nicht ist - und danach sucht man
lange an der falschen Stelle.

NetworkManager kann das nicht sicher beantworten: Dessen Buchführung
sagt nur, ob das Profil aktiviert wurde. Der Kernel weiß es genau,
und genau den fragt XRack jetzt.
"""

import shutil
import tempfile
from pathlib import Path

import core.wlan_control as wlan
from core.wlan_control import WlanControl

scratch = Path(tempfile.mkdtemp())

try:

    def sys_baum(name: str, geraete: dict) -> Path:
        """
        Baut einen nachgestellten /sys/class/net-Baum.

        `geraete` bildet Gerätenamen auf ihren Master ab; None heißt
        "hängt in keiner Bridge".
        """

        wurzel = scratch / name
        wurzel.mkdir(parents=True)

        for geraet, master in geraete.items():

            ordner = wurzel / geraet
            ordner.mkdir()

            if master is not None:
                (wurzel / master).mkdir(exist_ok=True)
                (ordner / "master").symlink_to(wurzel / master)

        return wurzel

    def gefragt(baum: Path):
        wlan.SYS_NET = baum
        return WlanControl().console_port_bridged()

    # ----------------------------------------------------------------
    # 1. Die drei eindeutigen Antworten
    # ----------------------------------------------------------------

    assert gefragt(sys_baum("drin", {"eth0": "br0", "wlan1": "br0"})) is True, (
        "eth0 haengt in br0 - das muss als 'drin' zaehlen."
    )

    assert gefragt(sys_baum("draussen", {"eth0": None, "wlan1": "br0"})) is False, (
        "Genau der Fall vom Geraet: eth0 haengt in keiner Bridge."
    )

    assert gefragt(sys_baum("fremd", {"eth0": "br1", "wlan1": "br0"})) is False, (
        "eth0 haengt in einer ANDEREN Bridge - fuer XRack heisst das aus."
    )

    print("OK: Der Kernel wird richtig gelesen (drin / draussen / fremde Bridge)")

    # ----------------------------------------------------------------
    # 2. Gibt es die Buchse gar nicht, ist das keine Antwort
    #
    # Dann darf XRack nicht "aus" behaupten, sondern muss wieder
    # NetworkManager glauben - sonst waere die Anzeige auf einem
    # Geraet ohne eth0 dauerhaft falsch.
    # ----------------------------------------------------------------

    assert gefragt(sys_baum("ohne", {"wlan1": "br0"})) is None, (
        "Ohne Buchse gibt es nichts zu sagen - erwartet: None."
    )

    print("OK: Ohne Netzwerkbuchse entscheidet weiter NetworkManager")

    # ----------------------------------------------------------------
    # 3. Der eigentliche Fehler: Profil aktiv, Buchse trotzdem draussen
    #
    # Vorher haette XRack hier die Vergabeliste von br0 gelesen und
    # 10.42.0.120 gemeldet - eine Adresse, hinter der nichts mehr ist.
    # ----------------------------------------------------------------

    wlan.SYS_NET = sys_baum("luege", {"eth0": None, "wlan1": "br0"})

    steuerung = WlanControl()

    #
    # NetworkManager behauptet, das Bridge-Profil laufe.
    #
    steuerung.connection_names = lambda: [
        "XRack-Home", "XRack-Bridge", "XRack-Bridge-eth0", "XRack-Share-eth0",
    ]
    steuerung.active_connection_names = lambda: [
        "XRack-Home", "XRack-Bridge", "XRack-Bridge-eth0",
    ]
    steuerung.ap_ssid = lambda: "XRack"
    steuerung.get_home_ip = lambda: None

    gefragte_interfaces = []

    steuerung.get_dhcp_lease_ip = lambda iface: (
        gefragte_interfaces.append(iface), "10.42.0.120"
    )[1]
    steuerung.get_connected_client_ip = lambda iface: None

    #
    # "available" haengt an nmcli - hier vorhanden oder nicht, der
    # Rest der Antwort ist davon unabhaengig.
    #
    type(steuerung).available = property(lambda self: True)

    status = steuerung.get_status()

    assert status["bridge_enabled"] is False, (
        "XRack glaubt NetworkManager statt dem Kernel - und liest gleich "
        "eine veraltete Adresse aus der Vergabeliste von br0."
    )

    assert gefragte_interfaces == [], (
        f"Es wurde trotzdem eine Vergabeliste gelesen: {gefragte_interfaces}"
    )

    assert status["console_ip"] is None, (
        f"Es wurde eine Konsolen-IP gemeldet, obwohl die Buchse gar nicht "
        f"in der Bridge haengt: {status['console_ip']}"
    )

    print("OK: Haengt die Buchse nicht in der Bridge, wird auch keine "
          "veraltete Adresse gemeldet")

    # ----------------------------------------------------------------
    # 4. Und andersherum: Buchse drin -> Vergabeliste von br0
    # ----------------------------------------------------------------

    wlan.SYS_NET = sys_baum("drin2", {"eth0": "br0", "wlan1": "br0"})

    gefragte_interfaces.clear()

    status = steuerung.get_status()

    assert status["bridge_enabled"] is True
    assert gefragte_interfaces == ["br0"], gefragte_interfaces
    assert status["console_ip"] == "10.42.0.120"

    print("OK: Haengt sie drin, wird die Vergabeliste von br0 gelesen")

    print("Alle Tests erfolgreich.")

finally:
    shutil.rmtree(scratch, ignore_errors=True)
