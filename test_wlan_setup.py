"""
Prüft die WLAN-Einrichtung aus install.sh, ohne Funkgerät.

Warum es diesen Test gibt: An install.sh merkt man einen Fehler
frühestens beim Installieren auf dem Gerät - und dann steht man
womöglich ohne Access Point da, also ohne den Zugang, über den man
das Gerät gerade erreichen wollte. Genau so ein Fehler ist hier
schon einmal passiert: Die Prüfung, ob der Adapter 5 GHz kann, suchte
nach "* 5180 MHz". Neuere Versionen von "iw" schreiben aber
"* 5180.0 MHz". Die Prüfung fand deshalb nie etwas, und der Access
Point lief stillschweigend auf dem meist zugestellten 2,4-GHz-Band -
ohne dass irgendwo eine Warnung erschienen wäre.

Geprüft wird gegen nachgestellte Werkzeuge (sudo, nmcli, iw,
systemctl, install, rfkill) im PATH. Die Funktionen selbst werden
unverändert aus install.sh herausgeschnitten und ausgeführt.

Zum Schluss läuft der komplette WLAN-Abschnitt einmal durch, mit
vorgegebenen Antworten - einmal mit zwei Funkgeräten (Heimnetz +
Access Point) und einmal mit nur einem (Heimnetz allein).
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

WURZEL = Path(__file__).parent
INSTALL = WURZEL / "install.sh"

#
# Die zu prüfenden Funktionen stehen zwischen diesen beiden Marken.
#
quelltext = INSTALL.read_text(encoding="utf-8")

#
# Aus install.sh die Funktionen, die dort geblieben sind: die Bridge
# und das Aufraeumen fremder WLAN-Profile.
#
anfang = quelltext.index("setup_ap_bridge() {")
ende = quelltext.index("configure_wifi() {")

FUNKTIONEN = quelltext[anfang:ende]

#
# Die eigentliche Access-Point-Einrichtung ist in ein eigenes Skript
# gewandert, damit sie auch aus dem Einstellungen-Menü heraus
# aufrufbar ist (Nachrüstfall). Für die Prüfungen unten werden beide
# zusammengelegt - install.sh liefert die Bridge und das Aufräumen
# fremder WLAN-Profile, das Skript den Rest.
#
AP_SETUP = (WURZEL / "scripts" / "xrack-ap-setup.sh").read_text(encoding="utf-8")

#
# Aus dem Skript nur die Funktionen übernehmen, nicht seinen
# Hauptteil - der würde beim Einlesen sofort losrichten.
#
FUNKTIONEN += AP_SETUP[
    AP_SETUP.index("#\n# hostapd-Konfiguration schreiben."):
    AP_SETUP.index("if setup_access_point_hostapd ")
]

assert "setup_access_point_hostapd()" in FUNKTIONEN, (
    "Die Access-Point-Funktionen wurden nicht gefunden - hat sich der "
    "Aufbau geändert?"
)

# ----------------------------------------------------------------
# Nachgestellte Werkzeuge
# ----------------------------------------------------------------

FAKE_SUDO = """#!/usr/bin/env bash
# Nachgestelltes sudo: fuehrt den Rest einfach aus.
exec "$@"
"""

FAKE_NMCLI = """#!/usr/bin/env bash
echo "$*" >> "$AP_STATE/nmcli"
if [ "$1" = "-t" ]; then
    #
    # "device status" listet die Funkgeraete, "NAME,TYPE" alle
    # Profile samt Art, alles andere nur die Profilnamen.
    #
    if [ "$4" = "device" ]; then
        cat "$AP_STATE/devices" 2>/dev/null
    elif [ "$3" = "NAME,TYPE" ]; then
        cat "$AP_STATE/profiles" 2>/dev/null
    else
        cat "$AP_STATE/connections" 2>/dev/null
    fi
    exit 0
fi
if [ "$1" = "-g" ]; then
    # nmcli -g <schluessel> connection show <name>
    name="${@: -1}"
    grep -m1 "^$name=" "$AP_STATE/autoconnect" 2>/dev/null | cut -d= -f2-
    exit 0
fi
if [ "$2" = "add" ]; then
    #
    # Den Profilnamen hinter "con-name" herausfischen, damit spaetere
    # Abfragen das Profil auch finden.
    #
    while [ $# -gt 0 ]; do
        if [ "$1" = "con-name" ]; then
            echo "$2" >> "$AP_STATE/connections"
            break
        fi
        shift
    done
fi
exit 0
"""

FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$AP_STATE/systemctl"
if [ "$1" = "is-active" ]; then
    [ -f "$AP_STATE/hostapd-laeuft" ] && exit 0
    exit 1
fi
if [ "$1" = "restart" ]; then
    #
    # Der nachgestellte hostapd startet nur, wenn das Band im
    # Testfall als moeglich hinterlegt ist.
    #
    band="$(grep -m1 '^hw_mode=' "$AP_STATE/xrack.conf" | cut -d= -f2)"
    if grep -qx "$band" "$AP_STATE/moegliche-baender" 2>/dev/null; then
        touch "$AP_STATE/hostapd-laeuft"
    else
        rm -f "$AP_STATE/hostapd-laeuft"
    fi
fi
exit 0
"""

FAKE_IW = """#!/usr/bin/env bash
if [ "$1" = "dev" ] && [ "$3" = "info" ]; then
    echo "Interface $2"
    echo "\twiphy 1"
    if [ -f "$AP_STATE/hostapd-laeuft" ]; then
        echo "\ttype AP"
    else
        echo "\ttype managed"
    fi
    exit 0
fi
if [ "$1" = "phy" ] && [ "$3" = "info" ]; then
    cat "$AP_STATE/phy-info" 2>/dev/null
    exit 0
fi
exit 0
"""

FAKE_STILL = """#!/usr/bin/env bash
exit 0
"""

#
# Auszuege echter "iw phy"-Ausgaben. Der Unterschied zwischen den
# beiden ersten ist genau der Fehler, um den es oben geht.
#
PHY_5GHZ_NEU = """\tFrequencies:
\t\t* 2412.0 MHz [1] (20.0 dBm)
\t\t* 5180.0 MHz [36] (23.0 dBm)
\t\t* 5260.0 MHz [52] (23.0 dBm) (radar detection)
"""

PHY_5GHZ_ALT = """\tFrequencies:
\t\t* 2412 MHz [1] (20.0 dBm)
\t\t* 5180 MHz [36] (23.0 dBm)
"""

PHY_NUR_24 = """\tFrequencies:
\t\t* 2412 MHz [1] (20.0 dBm)
\t\t* 2437 MHz [6] (20.0 dBm)
"""

PHY_5GHZ_GESPERRT = """\tFrequencies:
\t\t* 2412.0 MHz [1] (20.0 dBm)
\t\t* 5180.0 MHz [36] (disabled)
"""

PHY_5GHZ_KEIN_SENDEN = """\tFrequencies:
\t\t* 2412.0 MHz [1] (20.0 dBm)
\t\t* 5180.0 MHz [36] (23.0 dBm) (no IR)
"""


def lauf(ordner: Path, befehl: str, phy_info: str = "",
         baender=("a", "g")) -> subprocess.CompletedProcess:
    """
    Führt `befehl` mit den Funktionen aus install.sh in einer
    nachgestellten Umgebung aus.
    """

    ordner.mkdir(parents=True, exist_ok=True)

    binordner = ordner / "bin"
    binordner.mkdir(exist_ok=True)

    for name, inhalt in (
        ("sudo", FAKE_SUDO),
        ("nmcli", FAKE_NMCLI),
        ("systemctl", FAKE_SYSTEMCTL),
        ("iw", FAKE_IW),
        ("rfkill", FAKE_STILL),
        ("sleep", FAKE_STILL),
    ):
        datei = binordner / name
        datei.write_text(inhalt, encoding="utf-8")
        datei.chmod(0o755)

    (ordner / "phy-info").write_text(phy_info, encoding="utf-8")
    (ordner / "moegliche-baender").write_text(
        "\n".join(baender) + "\n", encoding="utf-8"
    )

    umgebung = dict(os.environ)
    umgebung["AP_STATE"] = str(ordner)
    umgebung["PATH"] = f"{binordner}:{os.environ['PATH']}"
    umgebung["XRACK_LANGUAGE"] = "de"

    #
    # Die Pfade, die auf dem echten System unter /etc lägen, hier in
    # den Testordner umbiegen - alles andere bleibt unverändert.
    #
    vorbereitung = "\n".join([
        "L() { printf '%s' \"$1\"; }",
        FUNKTIONEN,
        f'XRACK_HOSTAPD_CONF="{ordner}/xrack.conf"',
        f'XRACK_HOSTAPD_UNIT="{ordner}/xrack-hostapd.service"',
        f'XRACK_NM_UNMANAGED="{ordner}/nm-unmanaged.conf"',
    ])

    return subprocess.run(
        ["bash", "-c", vorbereitung + "\n" + befehl],
        env=umgebung,
        capture_output=True,
        text=True,
        timeout=60,
    )


scratch = Path(tempfile.mkdtemp())

try:

    # ----------------------------------------------------------------
    # 1. 5 GHz wird erkannt - in beiden Schreibweisen von "iw"
    # ----------------------------------------------------------------

    for name, phy, erwartet_mode, erwartet_kanal, warum in (
        ("neu", PHY_5GHZ_NEU, "a", "36", "5180.0 MHz (neuere iw-Ausgabe)"),
        ("alt", PHY_5GHZ_ALT, "a", "36", "5180 MHz (aeltere iw-Ausgabe)"),
        ("nur24", PHY_NUR_24, "g", "6", "Adapter kann nur 2,4 GHz"),
        ("gesperrt", PHY_5GHZ_GESPERRT, "g", "6", "Kanal 36 ist gesperrt"),
        ("noir", PHY_5GHZ_KEIN_SENDEN, "g", "6", "auf Kanal 36 darf nicht gesendet werden"),
    ):

        ordner = scratch / f"band-{name}"

        ergebnis = lauf(
            ordner,
            'setup_access_point_hostapd wlan1 "XRack" "geheim123" "DE"',
            phy_info=phy,
        )

        assert ergebnis.returncode == 0, ergebnis.stderr

        conf = (ordner / "xrack.conf").read_text(encoding="utf-8").splitlines()

        assert f"hw_mode={erwartet_mode}" in conf, (
            f"{warum}: erwartet hw_mode={erwartet_mode}, bekommen: {conf}"
        )
        assert f"channel={erwartet_kanal}" in conf, (
            f"{warum}: erwartet channel={erwartet_kanal}, bekommen: {conf}"
        )

    print("OK: Das Band wird richtig gewaehlt (auch bei '5180.0 MHz')")

    # ----------------------------------------------------------------
    # 2. Ohne Ländercode bleibt es bei 2,4 GHz
    #
    # Ohne Landesangabe darf hostapd auf 5 GHz gar nicht senden - und
    # "00" ist die Welt-Region, die dort ebenfalls nichts erlaubt.
    # ----------------------------------------------------------------

    for land in ("", "00"):

        ordner = scratch / f"land-{land or 'leer'}"

        ergebnis = lauf(
            ordner,
            f'setup_access_point_hostapd wlan1 "XRack" "geheim123" "{land}"',
            phy_info=PHY_5GHZ_NEU,
        )

        conf = (ordner / "xrack.conf").read_text(encoding="utf-8")

        assert "hw_mode=g" in conf, f"Land {land!r}: {conf}"
        assert "country_code" not in conf, (
            f"Land {land!r} wurde als Laendercode eingetragen: {conf}"
        )

    print("OK: Ohne brauchbaren Laendercode bleibt es bei 2,4 GHz")

    # ----------------------------------------------------------------
    # 3. Die Konfiguration enthält, worauf es ankommt
    # ----------------------------------------------------------------

    ordner = scratch / "konfig"

    lauf(
        ordner,
        'setup_access_point_hostapd wlan1 "Meine Buehne" "geheim123" "DE"',
        phy_info=PHY_5GHZ_NEU,
    )

    conf = (ordner / "xrack.conf").read_text(encoding="utf-8")
    zeilen = conf.splitlines()

    for pflicht, warum in (
        ("interface=wlan1", "auf welchem Funkgeraet"),
        ("bridge=br0", "der Access Point muss in die Bridge - sonst kein DHCP"),
        ("ssid=Meine Buehne", "Leerzeichen im Namen muessen erhalten bleiben"),
        ("wpa=2", "WPA2"),
        ("wpa_key_mgmt=WPA-PSK", "Anmeldung per Passwort"),
        ("rsn_pairwise=CCMP", "AES statt des alten TKIP"),
        ("wpa_passphrase=geheim123", "das Passwort selbst"),
        ("country_code=DE", "Funkregion"),
    ):
        assert pflicht in zeilen, f"{pflicht} fehlt ({warum}): {zeilen}"

    #
    # TKIP darf nirgends auftauchen: Neuere Handys handeln es
    # mitunter aus und scheitern dann am Schluesselaustausch - fuer
    # den Nutzer sieht das aus wie ein falsches Passwort.
    #
    assert "TKIP" not in conf, conf

    print("OK: Die hostapd-Konfiguration enthaelt das Noetige")

    # ----------------------------------------------------------------
    # 4. NetworkManager wird das Funkgerät entzogen
    #
    # Ohne das funken hostapd und wpa_supplicant gleichzeitig auf
    # demselben Geraet.
    # ----------------------------------------------------------------

    unmanaged = (ordner / "nm-unmanaged.conf").read_text(encoding="utf-8")

    assert "unmanaged-devices=interface-name:wlan1" in unmanaged, unmanaged

    nmcli_aufrufe = (ordner / "nmcli").read_text(encoding="utf-8")

    assert "device set wlan1 managed no" in nmcli_aufrufe, nmcli_aufrufe

    print("OK: NetworkManager laesst das Access-Point-Interface in Ruhe")

    # ----------------------------------------------------------------
    # 5. Der Dienst startet beim Booten mit
    # ----------------------------------------------------------------

    unit = (ordner / "xrack-hostapd.service").read_text(encoding="utf-8")

    assert "ExecStart=/usr/sbin/hostapd" in unit, unit
    assert "Restart=always" in unit, unit
    assert "WantedBy=multi-user.target" in unit, unit

    systemctl_aufrufe = (ordner / "systemctl").read_text(encoding="utf-8")

    assert "enable xrack-hostapd.service" in systemctl_aufrufe, systemctl_aufrufe
    assert "daemon-reload" in systemctl_aufrufe

    print("OK: Der Access Point kommt nach einem Neustart von selbst wieder")

    # ----------------------------------------------------------------
    # 6. Kommt 5 GHz nicht hoch, wird auf 2,4 GHz zurückgefallen
    #
    # Nicht jede Funkregion gibt die Kanaele frei, und nicht jeder
    # Treiber macht mit. Ohne Rueckfall stuende der Nutzer ganz ohne
    # Access Point da.
    # ----------------------------------------------------------------

    ordner = scratch / "rueckfall"

    ergebnis = lauf(
        ordner,
        'setup_access_point_hostapd wlan1 "XRack" "geheim123" "DE"',
        phy_info=PHY_5GHZ_NEU,
        baender=("g",),          # nur 2,4 GHz laesst sich starten
    )

    assert ergebnis.returncode == 0, (
        f"Kein Rueckfall auf 2,4 GHz: {ergebnis.stdout} {ergebnis.stderr}"
    )

    conf = (ordner / "xrack.conf").read_text(encoding="utf-8")

    assert "hw_mode=g" in conf, conf

    print("OK: Scheitert 5 GHz, laeuft der Access Point auf 2,4 GHz")

    # ----------------------------------------------------------------
    # 7. Startet hostapd gar nicht, bekommt NetworkManager das
    #    Funkgerät zurück
    #
    # Sonst waere das Interface nach einem gescheiterten Versuch fuer
    # niemanden mehr benutzbar - auch nicht fuer den Rueckfallweg
    # ueber NetworkManager.
    # ----------------------------------------------------------------

    ordner = scratch / "gescheitert"

    ergebnis = lauf(
        ordner,
        'setup_access_point_hostapd wlan1 "XRack" "geheim123" "DE"',
        phy_info=PHY_5GHZ_NEU,
        baender=(),              # gar nichts startet
    )

    assert ergebnis.returncode != 0, (
        "Ein nicht startender Access Point wurde als Erfolg gemeldet."
    )

    assert not (ordner / "nm-unmanaged.conf").exists(), (
        "Das Funkgeraet bleibt NetworkManager entzogen, obwohl hostapd "
        "nicht laeuft - dann kann es niemand mehr benutzen."
    )

    nmcli_aufrufe = (ordner / "nmcli").read_text(encoding="utf-8")

    assert "device set wlan1 managed yes" in nmcli_aufrufe, nmcli_aufrufe

    systemctl_aufrufe = (ordner / "systemctl").read_text(encoding="utf-8")

    assert "disable --now xrack-hostapd.service" in systemctl_aufrufe, (
        systemctl_aufrufe
    )

    print("OK: Nach einem Fehlschlag ist das Funkgeraet wieder frei")

    # ----------------------------------------------------------------
    # 8. Die Bridge: feste Adresse, eth0 bleibt zunächst draußen
    #
    # Die feste Adresse verhindert, dass NetworkManager das Subnetz je
    # nach Reihenfolge zwischen 10.42.0.x und 10.42.1.x verschiebt -
    # die Portweiterleitung zeigte sonst auf eine veraltete
    # Konsolen-IP. Und eth0 muss aus bleiben, weil sonst eine laufende
    # SSH-Sitzung ueber eth0 mitten in der Installation abreisst.
    # ----------------------------------------------------------------

    ordner = scratch / "bridge"

    ergebnis = lauf(ordner, "setup_ap_bridge")

    assert ergebnis.returncode == 0, ergebnis.stderr

    aufrufe = (ordner / "nmcli").read_text(encoding="utf-8")

    assert "ipv4.addresses 10.42.0.1/24" in aufrufe, aufrufe
    assert "ipv4.method shared" in aufrufe, aufrufe

    eth0_zeile = [
        z for z in aufrufe.splitlines() if "XRack-Bridge-eth0" in z
    ]

    assert eth0_zeile, aufrufe
    assert all("connection.autoconnect no" in z for z in eth0_zeile), (
        f"eth0 wuerde sofort in die Bridge gehen: {eth0_zeile}"
    )

    print("OK: Die Bridge bekommt eine feste Adresse, eth0 bleibt aus")

    # ----------------------------------------------------------------
    # 9. Fremde WLAN-Profile werden stillgelegt, nicht geloescht
    #
    # Raspberry Pi OS legt beim Schreiben der Speicherkarte oft schon
    # ein WLAN-Profil an ("preconfigured"). Bleibt es neben
    # XRack-Home mit "autoconnect yes" stehen, entscheidet
    # NetworkManager nach einem Neustart, welches gewinnt - und das
    # sieht von aussen wie Zufall aus.
    # ----------------------------------------------------------------

    ordner = scratch / "fremdprofile"
    ordner.mkdir(parents=True)

    (ordner / "profiles").write_text(
        "preconfigured:802-11-wireless\n"
        "XRack-Home:802-11-wireless\n"
        "Wired connection 1:802-3-ethernet\n"
        "Schon-aus:802-11-wireless\n",
        encoding="utf-8",
    )
    (ordner / "autoconnect").write_text(
        "preconfigured=yes\nXRack-Home=yes\n"
        "Wired connection 1=yes\nSchon-aus=no\n",
        encoding="utf-8",
    )

    ergebnis = lauf(ordner, "disable_foreign_wifi_profiles")

    assert ergebnis.returncode == 0, ergebnis.stderr

    aufrufe = (ordner / "nmcli").read_text(encoding="utf-8")

    assert "connection modify preconfigured connection.autoconnect no" in aufrufe, (
        f"Das mitgelieferte WLAN-Profil bleibt aktiv: {aufrufe}"
    )

    assert "modify XRack-Home" not in aufrufe, (
        f"XRack-Home hat sich selbst abgeschaltet: {aufrufe}"
    )

    assert "Wired connection" not in aufrufe, (
        f"Die Kabelverbindung wurde mit abgeschaltet: {aufrufe}"
    )

    #
    # Nachsehen darf es - nur aendern nicht, wenn schon aus.
    #
    assert "modify Schon-aus" not in aufrufe, (
        f"Ein bereits abgeschaltetes Profil wurde nochmal geaendert: {aufrufe}"
    )

    #
    # Nichts darf verschwinden: Wer gerade ueber genau dieses Profil
    # per SSH verbunden ist, soll es spaeter wiederfinden.
    #
    assert "connection delete" not in aufrufe, (
        f"Ein fremdes Profil wurde geloescht statt stillgelegt: {aufrufe}"
    )

    print("OK: Fremde WLAN-Profile werden stillgelegt, nicht geloescht")

    # ================================================================
    # Der ganze WLAN-Abschnitt, einmal durchgespielt
    #
    # Bis hierher wurden einzelne Funktionen geprueft. Was dabei nicht
    # auffaellt: ob der Ablauf als Ganzes durchlaeuft - also ob die
    # Abfragen in der richtigen Reihenfolge kommen und ob am Ende das
    # Richtige eingerichtet ist. Genau das kann man auf einem frisch
    # aufgesetzten Pi erst merken, wenn es zu spaet ist.
    #
    # Deshalb hier: install.sh wird eingelesen (nicht ausgefuehrt,
    # siehe XRACK_INSTALL_SOURCE_ONLY), und configure_wifi laeuft mit
    # vorgegebenen Antworten gegen nachgestellte Werkzeuge.
    #
    # Die Abfragen lesen teils mit "read -s" (Passwoerter), das
    # braucht ein Terminal - deshalb laeuft das Ganze in einer
    # Pseudo-Konsole.
    # ================================================================

    def wlan_einrichten(ordner: Path, geraete: list[str],
                        antworten: list[str]) -> tuple[str, dict]:
        """
        Spielt configure_wifi mit `antworten` durch und liefert
        (Ausgabe, erzeugte Dateien).

        Gestartet wird über "script", weil configure_wifi nur bei
        einem echten Terminal überhaupt loslegt ("[ -t 0 ]") und die
        Passwortabfragen mit "read -s" arbeiten. "script" stellt eine
        Pseudo-Konsole bereit und reicht die Antworten hinein.
        """

        ordner.mkdir(parents=True, exist_ok=True)

        binordner = ordner / "bin"
        binordner.mkdir(exist_ok=True)

        for name, inhalt in (
            ("sudo", FAKE_SUDO),
            ("nmcli", FAKE_NMCLI),
            ("systemctl", FAKE_SYSTEMCTL),
            ("iw", FAKE_IW),
            ("rfkill", FAKE_STILL),
            ("sleep", FAKE_STILL),
            ("raspi-config", FAKE_STILL),
        ):
            datei = binordner / name
            datei.write_text(inhalt, encoding="utf-8")
            datei.chmod(0o755)

        (ordner / "devices").write_text(
            "".join(f"{g}:wifi\n" for g in geraete) + "eth0:ethernet\n",
            encoding="utf-8",
        )

        #
        # Nachgestelltes /sys: Daran erkennt xrack-wifi-iface.sh, was
        # eingebaut ist und was am USB haengt. Die Pfade sind den
        # echten nachempfunden - beim Stick steckt "usb1" darin, beim
        # eingebauten Chip der SD-/MMC-Zweig.
        #
        sysnet = ordner / "sys-net"

        for nummer, geraet in enumerate(geraete):

            (sysnet / geraet / "wireless").mkdir(parents=True, exist_ok=True)

            if nummer == 0:
                echt = sysnet / "devices" / "platform" / "soc" / "mmc_host" / "mmc1"
            else:
                echt = sysnet / "devices" / "platform" / "scb" / "usb1" / "1-1"

            echt.mkdir(parents=True, exist_ok=True)

            verweis = sysnet / geraet / "device"

            if not verweis.exists():
                verweis.symlink_to(echt)

        (sysnet / "eth0").mkdir(parents=True, exist_ok=True)
        (ordner / "phy-info").write_text(PHY_5GHZ_NEU, encoding="utf-8")
        (ordner / "moegliche-baender").write_text("a\ng\n", encoding="utf-8")

        #
        # Ein mitgeliefertes WLAN-Profil, wie es der Raspberry Pi
        # Imager anlegt.
        #
        (ordner / "profiles").write_text(
            "preconfigured:802-11-wireless\n", encoding="utf-8"
        )
        (ordner / "autoconnect").write_text(
            "preconfigured=yes\n", encoding="utf-8"
        )

        skript = ordner / "lauf.sh"
        skript.write_text(
            "\n".join([
                "export XRACK_INSTALL_SOURCE_ONLY=1",
                f"source {INSTALL}",
                "XRACK_LANGUAGE=de",
                "configure_wifi",
                'echo "ERGEBNIS-CLIENT=${XRACK_WLAN_CLIENT_SSID}"',
                'echo "ERGEBNIS-AP=${XRACK_WLAN_AP_SSID}"',
                'echo "ERGEBNIS-BRIDGE=${XRACK_WLAN_BRIDGE}"',
            ]),
            encoding="utf-8",
        )

        umgebung = dict(os.environ)
        umgebung["AP_STATE"] = str(ordner)
        umgebung["XRACK_SYS_NET"] = str(ordner / "sys-net")
        umgebung["XRACK_HOSTAPD_CONF"] = str(ordner / "xrack.conf")
        umgebung["XRACK_HOSTAPD_UNIT"] = str(ordner / "xrack-hostapd.service")
        umgebung["XRACK_NM_UNMANAGED"] = str(ordner / "nm-unmanaged.conf")
        umgebung["PATH"] = f"{binordner}:{os.environ['PATH']}"

        ergebnis = subprocess.run(
            ["script", "-qec", f"bash {skript}", "/dev/null"],
            input=("\n".join(antworten) + "\n").encode(),
            capture_output=True,
            env=umgebung,
            timeout=120,
        )

        return ergebnis.stdout.decode(errors="replace"), {
            "conf": ordner / "xrack.conf",
            "nmcli": ordner / "nmcli",
        }

    # ----------------------------------------------------------------
    # 10. Zwei Funkgeraete: Heimnetz UND Access Point
    # ----------------------------------------------------------------

    ausgabe, dateien = wlan_einrichten(
        scratch / "ablauf-zwei",
        ["wlan0", "wlan1"],
        [
            "j",                # WLAN-Verbindung einrichten?
            "DE",               # Land
            "MeinHeimnetz",     # SSID
            "heimpasswort", "heimpasswort",
            "j",                # Access Point einrichten?
            "",                 # AP-Name: Vorgabe (XRack)
            "appasswort", "appasswort",
        ],
    )

    assert "ERGEBNIS-CLIENT=MeinHeimnetz" in ausgabe, ausgabe[-2000:]
    assert "ERGEBNIS-AP=XRack" in ausgabe, ausgabe[-2000:]
    assert "ERGEBNIS-BRIDGE=ja" in ausgabe, ausgabe[-2000:]

    conf = dateien["conf"].read_text(encoding="utf-8")

    assert "ssid=XRack" in conf, conf
    assert "wpa_passphrase=appasswort" in conf, conf
    assert "interface=wlan1" in conf, conf

    aufrufe = dateien["nmcli"].read_text(encoding="utf-8")

    assert "con-name XRack-Home" in aufrufe, aufrufe
    assert "con-name XRack-Share-eth0" in aufrufe, aufrufe

    #
    # Das mitgelieferte WLAN-Profil darf sich nicht mehr von selbst
    # verbinden - sonst wacht der Pi je nach Laune im falschen Netz
    # auf.
    #
    assert "modify preconfigured connection.autoconnect no" in aufrufe, aufrufe

    print("OK: Mit zwei Funkgeraeten kommen Heimnetz und Access Point")

    # ----------------------------------------------------------------
    # 11. Nur ein Funkgeraet: Heimnetz trotzdem
    #
    # Vorher wurde in diesem Fall das ganze WLAN-Setup uebersprungen.
    # Wer nur das eingebaute WLAN hat (kein USB-Stick), stand danach
    # ohne jede WLAN-Einrichtung da - und musste sie von Hand
    # nachholen, obwohl der Installer sie haette machen koennen.
    # ----------------------------------------------------------------

    ausgabe, dateien = wlan_einrichten(
        scratch / "ablauf-eins",
        ["wlan0"],
        [
            "j",                # WLAN-Verbindung einrichten?
            "DE",
            "MeinHeimnetz",
            "heimpasswort", "heimpasswort",
            "j",                # Access Point einrichten? (geht nicht)
        ],
    )

    assert "ERGEBNIS-CLIENT=MeinHeimnetz" in ausgabe, (
        "Mit nur einem Funkgeraet wurde auch die Heimnetz-Verbindung "
        f"uebersprungen:\n{ausgabe[-2000:]}"
    )

    assert "ERGEBNIS-AP=" in ausgabe and "ERGEBNIS-AP=XRack" not in ausgabe, (
        f"Auf dem einzigen Funkgeraet wurde ein Access Point "
        f"aufgespannt:\n{ausgabe[-2000:]}"
    )

    assert not dateien["conf"].exists(), (
        "Es wurde eine hostapd-Konfiguration geschrieben, obwohl es "
        "nur ein Funkgeraet gibt."
    )

    aufrufe = dateien["nmcli"].read_text(encoding="utf-8")

    assert "con-name XRack-Home" in aufrufe, aufrufe
    assert "con-name XRack-AP" not in aufrufe, aufrufe

    print("OK: Mit einem Funkgeraet kommt wenigstens das Heimnetz")

    # ----------------------------------------------------------------
    # 12. Wer wofuer zustaendig ist
    #
    # Eingebaut = Heimnetz, USB-Stick = Access Point. Das wird nicht
    # mehr abgefragt: Der eingebaute Chip taugt als Client, aber nur
    # schlecht als Access Point - die Abfrage hat nur Gelegenheit
    # gegeben, es falsch einzustellen.
    # ----------------------------------------------------------------

    def sys_baum_wlan(name, geraete):
        """geraete: {Name: "usb" oder "intern"}"""

        wurzel = scratch / name
        (wurzel / "devices" / "usb1").mkdir(parents=True, exist_ok=True)
        (wurzel / "devices" / "mmc1").mkdir(parents=True, exist_ok=True)

        for geraet, art in geraete.items():
            (wurzel / geraet / "wireless").mkdir(parents=True, exist_ok=True)
            ziel = wurzel / "devices" / ("usb1" if art == "usb" else "mmc1")
            verweis = wurzel / geraet / "device"
            if not verweis.exists():
                verweis.symlink_to(ziel)

        return wurzel

    def zustaendig(baum, rolle):
        return subprocess.run(
            [str(WURZEL / "scripts" / "xrack-wifi-iface.sh"), rolle],
            env={**os.environ, "XRACK_SYS_NET": str(baum)},
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()

    baum = sys_baum_wlan("zwei", {"wlan0": "intern", "wlan1": "usb"})

    assert zustaendig(baum, "client") == "wlan0", "Heimnetz gehoert dem eingebauten Chip."
    assert zustaendig(baum, "ap") == "wlan1", "Der Access Point gehoert dem USB-Stick."

    #
    # Auch wenn der Stick zuerst auftaucht - die Reihenfolge der
    # Geraetenamen darf nicht entscheiden.
    #
    baum = sys_baum_wlan("umgekehrt", {"wlan0": "usb", "wlan1": "intern"})

    assert zustaendig(baum, "client") == "wlan1", zustaendig(baum, "client")
    assert zustaendig(baum, "ap") == "wlan0", zustaendig(baum, "ap")

    #
    # Nur das eingebaute: Heimnetz ja, Access Point nein.
    #
    baum = sys_baum_wlan("nur-intern", {"wlan0": "intern"})

    assert zustaendig(baum, "client") == "wlan0"
    assert zustaendig(baum, "ap") == "", (
        "Auf dem eingebauten Chip darf kein Access Point aufgespannt werden."
    )

    print("OK: Eingebaut ist Heimnetz, USB ist Access Point")

    # ----------------------------------------------------------------
    # 13. WLAN uebersprungen, Access Point trotzdem
    #
    # Die beiden Fragen sind getrennt - wer keinen Heimnetz-Anschluss
    # will, soll trotzdem einen Access Point bekommen koennen.
    # ----------------------------------------------------------------

    ausgabe, dateien = wlan_einrichten(
        scratch / "nur-ap",
        ["wlan0", "wlan1"],
        [
            "n",                # keine WLAN-Verbindung
            "j",                # aber ein Access Point
            "DE",               # Land - wird auch auf diesem Weg gefragt
            "Buehne",
            "appasswort", "appasswort",
        ],
    )

    assert "ERGEBNIS-CLIENT=" in ausgabe and "ERGEBNIS-CLIENT=Mein" not in ausgabe
    assert "ERGEBNIS-AP=Buehne" in ausgabe, ausgabe[-2000:]

    conf = dateien["conf"].read_text(encoding="utf-8")

    assert "ssid=Buehne" in conf, conf

    #
    # Ohne Funkregion faehrt der Access Point bestenfalls auf dem
    # zugestellten 2,4-GHz-Band. Auf diesem Weg wurde bisher gar
    # nicht danach gefragt - die WLAN-Frage war ja verneint.
    #
    assert "country_code=DE" in conf, (
        f"Die Funkregion ist beim Access Point nicht angekommen:\n{conf}"
    )
    assert "hw_mode=a" in conf, "Mit Funkregion sollte 5 GHz drin sein."

    print("OK: Ohne Heimnetz-WLAN laesst sich trotzdem ein Access Point einrichten")

    # ----------------------------------------------------------------
    # 14. Beides uebersprungen - das Geruest steht trotzdem
    #
    # Das ist die Voraussetzung fuers Nachruesten: Wer hier alles
    # ueberspringt, soll spaeter im Einstellungen-Menue umschalten
    # koennen, ohne install.sh erneut laufen zu lassen.
    # ----------------------------------------------------------------

    ausgabe, dateien = wlan_einrichten(
        scratch / "nichts", ["wlan0", "wlan1"], ["n", "n"],
    )

    assert "ERGEBNIS-BRIDGE=ja" in ausgabe, ausgabe[-2000:]

    aufrufe = dateien["nmcli"].read_text(encoding="utf-8")

    for pflicht in ("con-name XRack-Bridge", "con-name XRack-Bridge-eth0",
                    "con-name XRack-Share-eth0"):
        assert pflicht in aufrufe, (
            f"{pflicht} fehlt - dann laesst sich spaeter nichts umschalten:\n{aufrufe}"
        )

    #
    # Und der Fall, der im Feld zugeschlagen hat: Genau so wurde
    # installiert - frischer Pi, weder WLAN noch Access Point. Danach
    # war er per Kabel nicht mehr erreichbar und tauchte im Router
    # nicht mehr auf.
    #
    # Der Grund: NetworkManager erzeugt seine automatische
    # Kabelverbindung nur, solange fuer das Geraet gar kein Profil
    # passt. Die beiden XRack-Profile oben (beide "autoconnect no")
    # beenden das - und dann bringt niemand mehr die Buchse hoch.
    #
    assert "con-name XRack-Wired-eth0" in aufrufe, (
        f"Es gibt kein Profil, das die Netzwerkbuchse normal hochbringt - "
        f"der Pi waere nach dem Neustart per Kabel nicht erreichbar:\n{aufrufe}"
    )

    kabelzeile = [
        zeile for zeile in aufrufe.splitlines()
        if "con-name XRack-Wired-eth0" in zeile
    ]

    assert all("ipv4.method auto" in z for z in kabelzeile), (
        f"Die Kabelverbindung holt sich keine Adresse per DHCP: {kabelzeile}"
    )
    assert all("connection.autoconnect yes" in z for z in kabelzeile), (
        f"Die Kabelverbindung kommt nicht von selbst hoch: {kabelzeile}"
    )

    #
    # Ohne den Hostnamen im DHCP-Antrag lernt der Router ihn nicht -
    # dann ist der Pi nur ueber die IP zu erreichen. Das ist der
    # zweite Weg zum Geraet, unabhaengig von ".local", und der
    # einzige, der auch ohne mDNS auf dem anfragenden Geraet
    # funktioniert.
    #
    assert all("ipv4.dhcp-send-hostname yes" in z for z in kabelzeile), (
        f"Der Router erfaehrt den Hostnamen nicht: {kabelzeile}"
    )

    print("OK: Auch ohne Antworten steht das Geruest zum Nachruesten")
    print("OK: Die Netzwerkbuchse bleibt ganz normal per DHCP erreichbar")

    # ----------------------------------------------------------------
    # 15. Der Nachruestfall selbst
    #
    # Im Einstellungen-Menue einen Access Point setzen, obwohl noch
    # keiner eingerichtet ist: xrack-net-ap.sh muss dann an
    # xrack-ap-setup.sh weiterreichen, statt "nicht eingerichtet" zu
    # melden.
    # ----------------------------------------------------------------

    ordner = scratch / "nachruesten"
    ordner.mkdir(parents=True)

    binordner = ordner / "bin"
    binordner.mkdir()

    for name, inhalt in (
        ("nmcli", FAKE_NMCLI), ("systemctl", FAKE_SYSTEMCTL),
        ("iw", FAKE_IW), ("rfkill", FAKE_STILL), ("sleep", FAKE_STILL),
    ):
        datei = binordner / name
        datei.write_text(inhalt, encoding="utf-8")
        datei.chmod(0o755)

    (ordner / "connections").write_text("XRack-Home\n", encoding="utf-8")
    (ordner / "phy-info").write_text(PHY_5GHZ_NEU, encoding="utf-8")
    (ordner / "moegliche-baender").write_text("a\ng\n", encoding="utf-8")

    sysnet = sys_baum_wlan("nachruesten-sys", {"wlan0": "intern", "wlan1": "usb"})

    ergebnis = subprocess.run(
        [str(WURZEL / "scripts" / "xrack-net-ap.sh"), "SpaeterAP", "spaetgeheim"],
        env={
            **os.environ,
            "AP_STATE": str(ordner),
            "XRACK_SYS_NET": str(sysnet),
            "XRACK_HOSTAPD_CONF": str(ordner / "xrack.conf"),
            "XRACK_HOSTAPD_UNIT": str(ordner / "unit"),
            "XRACK_NM_UNMANAGED": str(ordner / "nm.conf"),
            "PATH": f"{binordner}:{os.environ['PATH']}",
        },
        capture_output=True, text=True, timeout=60,
    )

    assert ergebnis.returncode == 0, (
        f"Nachruesten fehlgeschlagen: {ergebnis.stdout} {ergebnis.stderr}"
    )

    conf = (ordner / "xrack.conf").read_text(encoding="utf-8")

    assert "ssid=SpaeterAP" in conf, conf
    assert "wpa_passphrase=spaetgeheim" in conf, conf
    assert "interface=wlan1" in conf, "Auch beim Nachruesten der USB-Stick."

    print("OK: Ein Access Point laesst sich ohne install.sh nachruesten")

    print("Alle Tests erfolgreich.")

finally:
    shutil.rmtree(scratch, ignore_errors=True)
