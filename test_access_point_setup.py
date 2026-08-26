"""
Prüft die Access-Point-Einrichtung aus install.sh, ohne Funkgerät.

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

anfang = quelltext.index('XRACK_HOSTAPD_CONF="')
ende = quelltext.index("configure_wifi() {")

FUNKTIONEN = quelltext[anfang:ende]

assert "setup_access_point_hostapd()" in FUNKTIONEN, (
    "Die Access-Point-Funktionen wurden nicht gefunden - hat sich der "
    "Aufbau von install.sh geändert?"
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
    cat "$AP_STATE/connections" 2>/dev/null
    exit 0
fi
if [ "$2" = "add" ]; then
    echo "$4" >> "$AP_STATE/connections"
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

    print("Alle Tests erfolgreich.")

finally:
    shutil.rmtree(scratch, ignore_errors=True)
