"""
Prüft die beiden Netzwerk-Schalter gegeneinander, ohne NetworkManager.

Hintergrund: "Konsole über XRacks Access Point" (eth0 in der Bridge)
und "Konsole aus dem Heimnetz" (die Freigabe) beanspruchen beide eth0
und schließen sich deshalb aus. Jedes der beiden Skripte muss das
jeweils andere sauber abräumen.

Der Access Point selbst gehört seit der Umstellung auf hostapd nicht
mehr zum Umschaltvorgang: Er hängt dauerhaft in der Bridge br0, und
umgeschaltet wird nur noch, ob eth0 mit dazukommt. Genau daran hing
vorher ein Fehler - die Bridge hängte beim Einschalten den Access
Point als Slave ein, das Freigabe-Skript ließ ihn als Slave stehen,
und danach lief der Access Point bis zum nächsten Neustart nicht.
Beim Hochfahren zog NetworkManager mit dem Slave dessen Master wieder
hoch, sodass beide Schalter gleichzeitig an waren.

Deshalb prüft dieser Test jetzt vor allem eines mit: Die Bridge muss
in JEDER Stellung beider Schalter laufen bleiben - sie trägt IP,
DHCP und Internet-Weitergabe für alles, was am Access Point hängt.

Getestet wird gegen ein nachgestelltes nmcli: ein Skript im PATH, das
Verbindungen und ihren Zustand in Dateien verwaltet und jeden Aufruf
mitschreibt. Damit lässt sich prüfen, was die Skripte *tun*, ohne ein
echtes Netzwerk anzufassen. Für den Access Point selbst kommen weiter
unten eine nachgestellte hostapd-Konfiguration und ein nachgestelltes
systemctl dazu.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SKRIPTE = Path(__file__).parent / "scripts"

#
# Das nachgestellte nmcli. Es kennt nur so viel, wie die beiden
# Schalter-Skripte tatsächlich benutzen - mehr nachzubauen hieße, den
# Test an NetworkManager-Interna zu binden, die hier niemand prüft.
#
FAKE_NMCLI = r"""#!/usr/bin/env bash
#
# Nachgestelltes nmcli fuer die Tests. Zustand liegt in $NM_STATE:
#   connections   - eine Zeile je eingerichteter Verbindung
#   active        - eine Zeile je aktiver Verbindung
#   props/<Name>  - "schluessel=wert" je Zeile
#   calls         - Mitschrift aller Aufrufe
#
echo "$*" >> "$NM_STATE/calls"

prop_datei() { echo "$NM_STATE/props/$1"; }

prop_lesen() {
    grep -m1 "^$2=" "$(prop_datei "$1")" 2>/dev/null | cut -d= -f2-
}

prop_setzen() {
    local datei; datei="$(prop_datei "$1")"
    touch "$datei"
    grep -v "^$2=" "$datei" > "$datei.tmp" 2>/dev/null || true
    echo "$2=$3" >> "$datei.tmp"
    mv "$datei.tmp" "$datei"
}

case "$1 $2 $3" in
  "-t -f NAME")
    if [ "$5" = "--active" ]; then cat "$NM_STATE/active" 2>/dev/null
    else cat "$NM_STATE/connections" 2>/dev/null; fi
    exit 0 ;;
esac

if [ "$1" = "-t" ] && [ "$3" = "NAME,DEVICE" ]; then
    #
    # Mit "--active" nur die laufenden - echtes nmcli macht genau
    # diesen Unterschied, und davon haengt ab, ob ein Skript die
    # Buchse als belegt ansieht.
    #
    quelle="$NM_STATE/connections"
    for a in "$@"; do
        [ "$a" = "--active" ] && quelle="$NM_STATE/active"
    done
    while read -r name; do
        [ -n "$name" ] || continue
        echo "$name:$(prop_lesen "$name" device)"
    done < "$quelle"
    exit 0
fi

if [ "$1" = "-g" ] || { [ "$1" = "-s" ] && [ "$2" = "-g" ]; }; then
    [ "$1" = "-s" ] && shift
    schluessel="$2"; name="${!#}"
    case "$schluessel" in
      connection.interface-name) prop_lesen "$name" device ;;
      *) echo "geheim" ;;
    esac
    exit 0
fi

if [ "$1" = "connection" ]; then
    case "$2" in
      modify)
        name="$3"; shift 3
        while [ $# -gt 0 ]; do
            case "$1" in
              master|connection.master) prop_setzen "$name" master "$2"; shift 2 ;;
              slave-type|connection.slave-type) prop_setzen "$name" slave-type "$2"; shift 2 ;;
              connection.autoconnect) prop_setzen "$name" autoconnect "$2"; shift 2 ;;
              *) shift ;;
            esac
        done
        exit 0 ;;
      up)
        grep -qx "$3" "$NM_STATE/active" 2>/dev/null || echo "$3" >> "$NM_STATE/active"
        exit 0 ;;
      down)
        grep -vx "$3" "$NM_STATE/active" > "$NM_STATE/active.tmp" 2>/dev/null || true
        mv "$NM_STATE/active.tmp" "$NM_STATE/active" 2>/dev/null || true
        exit 0 ;;
      show) exit 0 ;;
    esac
fi

exit 0
"""


#
# Nachgestelltes "ip": Merkt sich jedes Schalten der Verbindung. Damit
# laesst sich pruefen, ob die Umschalt-Skripte die Verbindung wirklich
# kurz trennen - das ist es, was das Mischpult zum erneuten DHCP
# bewegt.
#
FAKE_IP = r"""#!/usr/bin/env bash
if [ "$1" = "link" ] && [ "$2" = "show" ]; then
    grep -qx "$3" "$NM_STATE/interfaces" 2>/dev/null && exit 0
    exit 1
fi
if [ "$1" = "link" ] && [ "$2" = "set" ]; then
    echo "$3 $4" >> "$NM_STATE/link"
fi
#
# "ip -4 addr show br0" - hat die Bridge eine Adresse? Die Datei
# "bridge-adresse" entscheidet das im Test.
#
if [ "$1" = "-4" ] && [ "$2" = "addr" ]; then
    if [ -f "$NM_STATE/bridge-adresse" ]; then
        echo "    inet 10.42.0.1/24 brd 10.42.0.255 scope global br0"
    fi
    exit 0
fi
exit 0
"""

#
# Nachgestelltes "sleep": Die Skripte warten auf echte Hardware. Im
# Test soll das nicht dauern.
#
FAKE_SLEEP = "#!/usr/bin/env bash\nexit 0\n"


class Netzwerk:
    """Ein nachgestelltes NetworkManager-Setup."""

    def __init__(self, verzeichnis: Path, mit_bridge: bool = True):

        self.pfad = verzeichnis
        (self.pfad / "props").mkdir(parents=True)

        verbindungen = ["XRack-Home", "XRack-Share-eth0", "XRack-Wired-eth0"]

        aktiv = ["XRack-Home"]

        if mit_bridge:

            verbindungen += ["XRack-Bridge", "XRack-Bridge-eth0"]

            #
            # Die Bridge läuft von Anfang an - so ist es auf dem Gerät
            # auch: Der Access Point funkt hinein, unabhängig davon,
            # ob gerade ein Mischpult am Kabel hängt.
            #
            aktiv.append("XRack-Bridge")

        (self.pfad / "connections").write_text(
            "\n".join(verbindungen) + "\n", encoding="utf-8"
        )
        (self.pfad / "active").write_text(
            "\n".join(aktiv) + "\n", encoding="utf-8"
        )

        self.setze("XRack-Share-eth0", "device", "eth0")

        #
        # nmcli-Attrappe in einen eigenen bin-Ordner legen und dem
        # PATH voranstellen.
        #
        binordner = self.pfad / "bin"
        binordner.mkdir()

        nmcli = binordner / "nmcli"
        nmcli.write_text(FAKE_NMCLI, encoding="utf-8")
        nmcli.chmod(0o755)

        for name, inhalt in (("ip", FAKE_IP), ("sleep", FAKE_SLEEP)):
            datei = binordner / name
            datei.write_text(inhalt, encoding="utf-8")
            datei.chmod(0o755)

        (self.pfad / "interfaces").write_text("eth0\nwlan1\n", encoding="utf-8")

        #
        # Im Normalfall trägt die Bridge ihre Adresse. Einzelne Tests
        # nehmen sie weg, um den beobachteten Ausfall nachzustellen.
        #
        (self.pfad / "bridge-adresse").write_text("da\n", encoding="utf-8")

        self.umgebung = dict(os.environ)
        self.umgebung["NM_STATE"] = str(self.pfad)
        self.umgebung["PATH"] = f"{binordner}:{os.environ['PATH']}"

    def setze(self, name: str, schluessel: str, wert: str) -> None:
        datei = self.pfad / "props" / name
        zeilen = [
            z for z in (datei.read_text(encoding="utf-8").splitlines()
                        if datei.exists() else [])
            if not z.startswith(f"{schluessel}=")
        ]
        zeilen.append(f"{schluessel}={wert}")
        datei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

    def lies(self, name: str, schluessel: str) -> str:
        datei = self.pfad / "props" / name
        if not datei.exists():
            return ""
        for zeile in datei.read_text(encoding="utf-8").splitlines():
            if zeile.startswith(f"{schluessel}="):
                return zeile.split("=", 1)[1]
        return ""

    def aktiv(self) -> set:
        datei = self.pfad / "active"
        if not datei.exists():
            return set()
        return set(datei.read_text(encoding="utf-8").split())

    def linkschaltungen(self) -> list:
        """Was am Anschluss geschaltet wurde, in der Reihenfolge."""

        datei = self.pfad / "link"

        if not datei.exists():
            return []

        return datei.read_text(encoding="utf-8").split("\n")[:-1]

    def aktiviere(self, name: str) -> None:
        with (self.pfad / "active").open("a", encoding="utf-8") as f:
            f.write(name + "\n")

    def schalte(self, skript: str, modus: str):
        return subprocess.run(
            [str(SKRIPTE / skript), modus],
            env=self.umgebung,
            capture_output=True,
            text=True,
            timeout=30,
        )


def bridge_neuaufbauten(netz) -> list:
    """
    Die Aufrufe, die die Bridge SELBST hochfahren - nicht ihren
    eth0-Anschluss (der heisst "XRack-Bridge-eth0" und wird beim
    Einschalten ohnehin hochgefahren).

    Die Attrappe schreibt die ganze Befehlszeile mit, also etwa
    "-w 10 connection up XRack-Bridge". Ein Vergleich auf den
    Zeilenanfang geht deshalb ins Leere - und ein Test, der nie etwas
    findet, besteht immer.
    """

    datei = netz.pfad / "calls"

    if not datei.exists():
        return []

    return [
        zeile
        for zeile in datei.read_text(encoding="utf-8").splitlines()
        if "connection up XRack-Bridge" in zeile
        and "XRack-Bridge-eth0" not in zeile
    ]


scratch = Path(tempfile.mkdtemp())

try:

    # ----------------------------------------------------------------
    # 1. Bridge an: eth0 kommt in die Bridge
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "a")

    ergebnis = netz.schalte("xrack-bridge-toggle.sh", "on")

    assert ergebnis.returncode == 0, ergebnis.stderr

    assert "XRack-Bridge-eth0" in netz.aktiv(), (
        f"eth0 haengt nicht in der Bridge: {sorted(netz.aktiv())}"
    )
    assert netz.lies("XRack-Bridge-eth0", "autoconnect") == "yes", (
        "Die Bridge-Stellung muss einen Neustart ueberleben."
    )

    print("OK: Bridge an haengt eth0 in die Bridge")

    # ----------------------------------------------------------------
    # 2. Bridge aus: eth0 raus - die Bridge selbst bleibt oben
    #
    # Das ist der Kern der Umstellung. Vorher wurde beim Ausschalten
    # die ganze Bridge heruntergefahren; der Access Point hing als
    # Slave darin und war damit weg. Jetzt traegt die Bridge IP,
    # DHCP und Internet-Weitergabe fuer den Access Point und muss in
    # jeder Stellung laufen.
    # ----------------------------------------------------------------

    ergebnis = netz.schalte("xrack-bridge-toggle.sh", "off")

    assert ergebnis.returncode == 0, ergebnis.stderr

    assert "XRack-Bridge-eth0" not in netz.aktiv(), (
        f"eth0 haengt noch in der Bridge: {sorted(netz.aktiv())}"
    )
    assert netz.lies("XRack-Bridge-eth0", "autoconnect") == "no"

    assert "XRack-Bridge" in netz.aktiv(), (
        "Die Bridge wurde mit abgeschaltet - damit waere der Access "
        "Point ohne IP, DHCP und Internet-Weitergabe."
    )

    print("OK: Bridge aus nimmt eth0 heraus, laesst die Bridge aber laufen")

    # ----------------------------------------------------------------
    # 3. Freigabe an, waehrend eth0 in der Bridge haengt
    #
    # Die Freigabe muss eth0 aus der Bridge nehmen - aber eben nur
    # eth0, nicht die Bridge.
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "b")

    assert netz.schalte("xrack-bridge-toggle.sh", "on").returncode == 0
    assert "XRack-Bridge-eth0" in netz.aktiv()

    ergebnis = netz.schalte("xrack-share-toggle.sh", "on")

    assert ergebnis.returncode == 0, ergebnis.stderr

    aktiv = netz.aktiv()

    assert "XRack-Share-eth0" in aktiv, aktiv
    assert "XRack-Bridge-eth0" not in aktiv, (
        f"Bridge und Freigabe beanspruchen gleichzeitig eth0: {sorted(aktiv)}"
    )
    assert netz.lies("XRack-Bridge-eth0", "autoconnect") == "no", (
        "eth0 darf nach dem Umschalten nicht von selbst wieder in die "
        "Bridge zurueckkommen."
    )

    print("OK: Freigabe an nimmt eth0 aus der Bridge")

    # ----------------------------------------------------------------
    # 4. Auch dabei bleibt der Access Point in Betrieb
    # ----------------------------------------------------------------

    assert "XRack-Bridge" in netz.aktiv(), (
        "Die Freigabe hat die Bridge mit abgeschaltet - der Access "
        "Point stuende dann ohne DHCP da."
    )

    print("OK: Der Access Point laeuft auch beim Umschalten weiter")

    # ----------------------------------------------------------------
    # 5. Und in die andere Richtung genauso
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "c")

    assert netz.schalte("xrack-share-toggle.sh", "on").returncode == 0
    assert "XRack-Share-eth0" in netz.aktiv()

    assert netz.schalte("xrack-bridge-toggle.sh", "on").returncode == 0

    aktiv = netz.aktiv()

    assert "XRack-Bridge-eth0" in aktiv, aktiv
    assert "XRack-Share-eth0" not in aktiv, (
        f"Freigabe laeuft trotz eingeschalteter Bridge weiter: {sorted(aktiv)}"
    )
    assert netz.lies("XRack-Share-eth0", "autoconnect") == "no"
    assert "XRack-Bridge" in aktiv

    print("OK: Bridge an raeumt die Freigabe ab")

    # ----------------------------------------------------------------
    # 6. Ohne eingerichtete Bridge darf die Freigabe trotzdem gehen
    #
    # Nicht jede Installation hat einen Access Point. Das Abraeumen
    # der Bridge darf dann nicht zum Abbruch fuehren.
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "d", mit_bridge=False)

    ergebnis = netz.schalte("xrack-share-toggle.sh", "on")

    assert ergebnis.returncode == 0, (
        f"Ohne Bridge schlug die Freigabe fehl: {ergebnis.stderr}"
    )
    assert "XRack-Share-eth0" in netz.aktiv()

    print("OK: Ohne Access Point laesst sich die Freigabe trotzdem schalten")

    # ----------------------------------------------------------------
    # 6b. Beide Schalter muessen die Verbindung kurz trennen
    #
    # Die beiden Zugangswege liegen in verschiedenen Netzen (Bridge
    # 10.42.0.x, Freigabe 10.77.0.x). Der Pi stellt sich beim
    # Umschalten sofort um - das angeschlossene Pult aber nicht: Es
    # fragt erst dann wieder per DHCP nach, wenn die Verbindung
    # tatsaechlich weg war. Bleibt sie durchgehend bestehen, behaelt es
    # seine alte Adresse, bis die Lease abläuft. Deshalb half bisher
    # nur Kabel ziehen oder ein Neustart.
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "e")

    assert netz.schalte("xrack-share-toggle.sh", "on").returncode == 0

    geschaltet = netz.linkschaltungen()

    assert "eth0 down" in geschaltet and "eth0 up" in geschaltet, (
        f"Die Freigabe hat die Verbindung nicht getrennt: {geschaltet}"
    )
    assert geschaltet.index("eth0 down") < geschaltet.index("eth0 up"), (
        f"Erst trennen, dann wieder verbinden: {geschaltet}"
    )

    print("OK: Die Freigabe trennt die Verbindung kurz (erzwingt neues DHCP)")

    netz = Netzwerk(scratch / "f")

    assert netz.schalte("xrack-bridge-toggle.sh", "on").returncode == 0

    geschaltet = netz.linkschaltungen()

    assert "eth0 down" in geschaltet and "eth0 up" in geschaltet, (
        f"Die Bridge hat die Verbindung nicht getrennt: {geschaltet}"
    )

    print("OK: Die Bridge trennt die Verbindung ebenfalls kurz")

    #
    # Beim Ausschalten dagegen nicht: Dort wechselt kein Netz, und ein
    # unnoetiges Trennen wuerde nur alles kurz stoeren.
    #
    netz = Netzwerk(scratch / "g")

    assert netz.schalte("xrack-share-toggle.sh", "off").returncode == 0

    assert netz.linkschaltungen() == [], (
        f"Beim Ausschalten wurde unnoetig getrennt: {netz.linkschaltungen()}"
    )

    print("OK: Beim Ausschalten bleibt die Verbindung unangetastet")

    # ----------------------------------------------------------------
    # 7. Der Lease-Leser darf keine abgelaufenen Adressen melden
    #
    # dnsmasq laesst abgelaufene Eintraege eine Weile in der Datei
    # stehen. Wurde nur die letzte Zeile genommen, meldete XRack eine
    # Adresse, unter der laengst nichts mehr antwortet - und das sieht
    # aus, als sei die Konsole erreichbar. Danach sucht man lange an
    # der falschen Stelle.
    # ----------------------------------------------------------------

    import time

    lease_skript = SKRIPTE / "xrack-dhcp-lease.sh"

    def lease_lesen(zeilen: list[str]) -> str:
        """Legt eine Lease-Datei an und fragt das Skript danach."""

        ordner = Path(tempfile.mkdtemp(dir=scratch))

        #
        # Das Skript baut den Pfad aus dem Interface-Namen. Deshalb
        # einen "Interface-Namen" uebergeben, der auf unsere Datei
        # zeigt - so bleibt das Skript unveraendert pruefbar.
        #
        datei = ordner / "dnsmasq-test.leases"
        datei.write_text("\n".join(zeilen) + "\n", encoding="utf-8")

        inhalt = lease_skript.read_text(encoding="utf-8").replace(
            "/var/lib/NetworkManager/dnsmasq-${IFACE}.leases",
            str(ordner / "dnsmasq-${IFACE}.leases"),
        )

        kopie = ordner / "lease.sh"
        kopie.write_text(inhalt, encoding="utf-8")
        kopie.chmod(0o755)

        return subprocess.run(
            [str(kopie), "test"], capture_output=True, text=True, timeout=10
        ).stdout.strip()

    jetzt = int(time.time())

    #
    # Gueltige Lease wird gemeldet.
    #
    assert lease_lesen([
        f"{jetzt + 3600} 11:22:33:44:55:66 10.77.0.120 pult *"
    ]) == "10.77.0.120"

    #
    # Abgelaufene NICHT.
    #
    assert lease_lesen([
        f"{jetzt - 3600} 11:22:33:44:55:66 10.77.0.99 alt *"
    ]) == "", "Eine abgelaufene Lease wurde als aktuelle Adresse gemeldet."

    #
    # Steht eine abgelaufene HINTER einer gueltigen, gewinnt die
    # gueltige - "letzte Zeile" allein waere hier falsch.
    #
    assert lease_lesen([
        f"{jetzt + 3600} 11:22:33:44:55:66 10.77.0.120 pult *",
        f"{jetzt - 3600} aa:bb:cc:dd:ee:ff 10.77.0.99 alt *",
    ]) == "10.77.0.120", (
        "Eine abgelaufene Lease hat eine gueltige verdraengt."
    )

    #
    # Zeitstempel 0 heisst bei dnsmasq "laeuft nie ab".
    #
    assert lease_lesen([
        "0 11:22:33:44:55:66 10.77.0.120 dauerhaft *"
    ]) == "10.77.0.120"

    #
    # Leere Datei: keine Ausgabe, kein Fehler.
    #
    assert lease_lesen([""]) == ""

    print("OK: Der Lease-Leser meldet nur gueltige Adressen")

    # ----------------------------------------------------------------
    # 8. Access Point umbenennen: hostapd-Konfiguration umschreiben
    #
    # Seit der Umstellung auf hostapd aendert das Einstellungen-Menue
    # nicht mehr ein NetworkManager-Profil, sondern zwei Zeilen in
    # /etc/hostapd/xrack.conf. Alles andere darin - Band, Kanal,
    # Ländercode, Verschluesselung - muss dabei stehenbleiben.
    # ----------------------------------------------------------------

    HOSTAPD_VORLAGE = """# Von install.sh erzeugt (XRack)
interface=wlan1
bridge=br0
driver=nl80211
ssid=XRack
country_code=DE
ieee80211d=1
hw_mode=a
channel=36
wpa=2
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
ieee80211w=1
wpa_passphrase=altesPasswort
"""

    FAKE_SYSTEMCTL = r"""#!/usr/bin/env bash
echo "$*" >> "$NM_STATE/systemctl"
if [ "$1" = "is-active" ]; then
    #
    # Der Access Point kommt mit der SSID "KAPUTT" nicht hoch - so
    # laesst sich der Rueckfall auf die alten Werte pruefen.
    #
    grep -q '^ssid=KAPUTT$' "$XRACK_TEST_CONF" && exit 1
    exit 0
fi
exit 0
"""

    #
    # Nachgestelltes "install": Der Test laeuft nicht als root, -o/-g
    # koennen also nicht gelten. Kopiert und geschuetzt wird trotzdem
    # echt - genau das ist ja die Eigenschaft, die zaehlt.
    #
    FAKE_INSTALL = r"""#!/usr/bin/env bash
echo "$*" >> "$NM_STATE/install"
ziel="${@: -1}"
quelle="${@: -2:1}"
cp "$quelle" "$ziel"
"""

    def ap_umgebung(ordner: Path, inhalt: str = HOSTAPD_VORLAGE):
        """
        Legt eine nachgestellte hostapd-Umgebung an und liefert
        (Skript-Kopie, Konfigurationsdatei, Umgebung).
        """

        ordner.mkdir(parents=True)

        conf = ordner / "xrack.conf"
        conf.write_text(inhalt, encoding="utf-8")

        binordner = ordner / "bin"
        binordner.mkdir()

        for name, quelltext in (
            ("systemctl", FAKE_SYSTEMCTL),
            ("install", FAKE_INSTALL),
            ("sleep", FAKE_SLEEP),
        ):
            datei = binordner / name
            datei.write_text(quelltext, encoding="utf-8")
            datei.chmod(0o755)

        #
        # Das Skript wird kopiert, damit "$(dirname $0)" hier
        # hinzeigt - der Pfad zur hostapd-Datei kommt dagegen ueber
        # XRACK_HOSTAPD_CONF.
        #
        # Frueher wurde dafuer die Zeile CONF="/etc/hostapd/xrack.conf"
        # im Text ersetzt. Das ging genau so lange gut, bis die Zeile
        # sich aenderte: Danach traf die Ersetzung nicht mehr, das
        # Skript arbeitete stillschweigend auf dem echten /etc-Pfad -
        # und der Test prueft nichts mehr von dem, was er zu pruefen
        # vorgibt. Die Umgebungsvariable kann nicht danebengehen.
        #
        skript = ordner / "net-ap.sh"
        skript.write_text(
            (SKRIPTE / "xrack-net-ap.sh").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        skript.chmod(0o755)

        umgebung = dict(os.environ)
        umgebung["NM_STATE"] = str(ordner)
        umgebung["XRACK_TEST_CONF"] = str(conf)
        umgebung["XRACK_HOSTAPD_CONF"] = str(conf)
        umgebung["PATH"] = f"{binordner}:{os.environ['PATH']}"

        return skript, conf, umgebung

    def ap_setzen(skript, umgebung, ssid, passwort):
        return subprocess.run(
            [str(skript), ssid, passwort],
            env=umgebung,
            capture_output=True,
            text=True,
            timeout=30,
        )

    skript, conf, umgebung = ap_umgebung(scratch / "ap1")

    ergebnis = ap_setzen(skript, umgebung, "Neuer Name", "neuesGeheimnis")

    assert ergebnis.returncode == 0, ergebnis.stderr

    zeilen = conf.read_text(encoding="utf-8").splitlines()

    assert "ssid=Neuer Name" in zeilen, zeilen
    assert "wpa_passphrase=neuesGeheimnis" in zeilen, zeilen
    assert "ssid=XRack" not in zeilen
    assert "wpa_passphrase=altesPasswort" not in zeilen

    for unveraendert in (
        "hw_mode=a", "channel=36", "country_code=DE",
        "rsn_pairwise=CCMP", "ieee80211w=1", "bridge=br0",
    ):
        assert unveraendert in zeilen, (
            f"{unveraendert} ist beim Umbenennen verlorengegangen: {zeilen}"
        )

    assert (scratch / "ap1" / "systemctl").read_text(
        encoding="utf-8"
    ).count("restart") == 1, "Der Access Point wurde nicht neu gestartet."

    print("OK: Umbenennen aendert nur SSID und Passwort")

    #
    # Die Datei darf hinterher nicht fuer alle lesbar sein - sie
    # enthaelt das WLAN-Passwort im Klartext. Geprueft wird, womit
    # das Skript sie ablegt (der Test selbst laeuft nicht als root
    # und koennte den Besitzer gar nicht setzen).
    #
    abgelegt = (scratch / "ap1" / "install").read_text(encoding="utf-8")

    assert "-m 0600" in abgelegt and "-o root" in abgelegt, (
        f"Die hostapd-Konfiguration wird zu offen abgelegt: {abgelegt}"
    )

    print("OK: Die Konfiguration bleibt nur fuer root lesbar")

    # ----------------------------------------------------------------
    # 9. Kommt der Access Point nicht hoch, zaehlen wieder die alten
    #    Werte
    #
    # Ohne das stuende jemand nach einem missglueckten Versuch ohne
    # Access Point da - und bei einem Access Point ist der oft der
    # einzige Zugang zum Geraet.
    # ----------------------------------------------------------------

    skript, conf, umgebung = ap_umgebung(scratch / "ap2")

    vorher = conf.read_text(encoding="utf-8")

    ergebnis = ap_setzen(skript, umgebung, "KAPUTT", "trotzdemLang")

    assert ergebnis.returncode != 0, (
        "Ein nicht startender Access Point wurde als Erfolg gemeldet."
    )
    assert conf.read_text(encoding="utf-8") == vorher, (
        "Nach dem Fehlschlag stehen die untauglichen Werte noch drin."
    )

    print("OK: Nach einem Fehlschlag gelten wieder die alten Werte")

    # ----------------------------------------------------------------
    # 10. Unbrauchbare Eingaben werden abgewiesen
    #
    # Ein Zeilenumbruch in der SSID wuerde in der hostapd-Datei eine
    # neue Einstellung erzeugen - der Rest der Zeile landete dann als
    # Befehl in der Konfiguration.
    # ----------------------------------------------------------------

    skript, conf, umgebung = ap_umgebung(scratch / "ap3")

    vorher = conf.read_text(encoding="utf-8")

    for ssid, passwort, warum in (
        ("Name", "kurz", "zu kurzes Passwort"),
        ("Zeile1\nwpa_passphrase=offen", "langgenug1", "Zeilenumbruch in der SSID"),
        ("", "langgenug1", "leere SSID"),
        ("x" * 33, "langgenug1", "zu lange SSID"),
    ):
        ergebnis = ap_setzen(skript, umgebung, ssid, passwort)

        assert ergebnis.returncode != 0, f"Angenommen trotz {warum}."
        assert conf.read_text(encoding="utf-8") == vorher, (
            f"Die Konfiguration wurde trotz {warum} veraendert."
        )

    print("OK: Unbrauchbare SSIDs und Passwoerter werden abgewiesen")

    # ----------------------------------------------------------------
    # 11. Den Namen wieder auslesen
    #
    # XRack laeuft nicht als root und kann die hostapd-Datei nicht
    # selbst oeffnen - dafuer gibt es xrack-ap-info.sh.
    # ----------------------------------------------------------------

    def ap_name(inhalt: str, ordner: Path) -> str:

        ordner.mkdir(parents=True)

        conf = ordner / "xrack.conf"
        conf.write_text(inhalt, encoding="utf-8")

        skript = ordner / "ap-info.sh"
        skript.write_text(
            (SKRIPTE / "xrack-ap-info.sh").read_text(encoding="utf-8").replace(
                'CONF="/etc/hostapd/xrack.conf"', f'CONF="{conf}"'
            ),
            encoding="utf-8",
        )
        skript.chmod(0o755)

        return subprocess.run(
            [str(skript)], capture_output=True, text=True, timeout=10
        ).stdout.strip()

    assert ap_name(HOSTAPD_VORLAGE, scratch / "info1") == "XRack"

    #
    # SSIDs duerfen Leerzeichen und Gleichheitszeichen enthalten.
    #
    assert ap_name(
        HOSTAPD_VORLAGE.replace("ssid=XRack", "ssid=Bue hne=2"),
        scratch / "info2",
    ) == "Bue hne=2"

    #
    # Das Passwort darf dabei unter keinen Umstaenden mit
    # herauskommen.
    #
    ausgabe = ap_name(HOSTAPD_VORLAGE, scratch / "info3")

    assert "altesPasswort" not in ausgabe, ausgabe

    print("OK: Der Name des Access Points laesst sich auslesen")

    # ----------------------------------------------------------------
    # 12. Der Kabel-Trick allein, ohne Umschalten
    #
    # Beim Umschalten trennen die beiden Skripte die Verbindung
    # ohnehin kurz. Nur passiert genau das eben nicht, wenn sich sonst
    # etwas aendert - das Pult wird spaeter eingesteckt, es oder der
    # Pi wird neu gestartet, oder das Pult haelt noch eine Adresse aus
    # einem frueheren Netz. Dafuer laesst sich das Skript jetzt auch
    # einzeln aufrufen (Knopf im Einstellungen-Fenster).
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "kabel")

    ergebnis = subprocess.run(
        [str(SKRIPTE / "xrack-link-bounce.sh"), "eth0"],
        env=netz.umgebung,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert ergebnis.returncode == 0, ergebnis.stderr

    geschaltet = netz.linkschaltungen()

    assert geschaltet == ["eth0 down", "eth0 up"], (
        f"Erst trennen, dann wieder verbinden - bekommen: {geschaltet}"
    )

    print("OK: Der Kabel-Trick laesst sich einzeln ausloesen")

    #
    # Einen Anschluss, den es nicht gibt, darf das Skript nicht als
    # Fehler melden: Nicht jede Installation hat jeden Anschluss, und
    # ein Fehlschlag hier wuerde im Einstellungen-Fenster als roter
    # Hinweis landen, obwohl nichts kaputt ist.
    #
    netz = Netzwerk(scratch / "kabel-fehlt")

    ergebnis = subprocess.run(
        [str(SKRIPTE / "xrack-link-bounce.sh"), "gibtsnicht0"],
        env=netz.umgebung,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert ergebnis.returncode == 0, (
        f"Ein fehlender Anschluss wurde als Fehler gemeldet: {ergebnis.stderr}"
    )
    assert netz.linkschaltungen() == [], netz.linkschaltungen()

    print("OK: Ein fehlender Anschluss ist kein Fehler")

    # ----------------------------------------------------------------
    # 13. Die Bridge ohne Adresse wird neu aufgebaut
    #
    # Beobachtet am Geraet: Nach dem Zurueckschalten war der
    # Bridge-Port angehaengt, die Kabelverbindung getrennt und wieder
    # verbunden - und trotzdem kam kein einziges DHCP-Paket zurueck.
    # In der Gegenrichtung hatte derselbe Ablauf zwei Sekunden spaeter
    # ein DHCPACK gebracht. Der Unterschied lag an der antwortenden
    # Seite: Auf br0 hat niemand geantwortet.
    #
    # "Verbindung aktiv" heisst eben nicht "Bridge traegt ihre
    # Adresse" - und ohne Adresse kein DHCP-Server.
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "bridge-ohne-adresse")

    #
    # Die Bridge gilt als aktiv, hat aber keine Adresse.
    #
    netz.aktiviere("XRack-Bridge")
    (netz.pfad / "bridge-adresse").unlink()

    assert netz.schalte("xrack-bridge-toggle.sh", "on").returncode == 0

    #
    # Gemeint ist die Bridge selbst - nicht ihr eth0-Anschluss, der
    # heisst "XRack-Bridge-eth0" und wird ohnehin hochgefahren.
    #
    aufrufe = bridge_neuaufbauten(netz)

    assert aufrufe, (
        "Die Bridge wurde nicht neu aufgebaut, obwohl ihr die Adresse "
        "fehlte."
    )

    print("OK: Fehlt der Bridge die Adresse, wird sie neu aufgebaut")

    # ----------------------------------------------------------------
    # 14. Mit Adresse wird sie in Ruhe gelassen
    #
    # Ein Neuaufbau unterbricht kurz den Verkehr aller am Access Point
    # angemeldeten Geraete - das darf nur passieren, wenn es noetig
    # ist.
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "bridge-mit-adresse")
    netz.aktiviere("XRack-Bridge")

    assert netz.schalte("xrack-bridge-toggle.sh", "on").returncode == 0

    aufrufe = bridge_neuaufbauten(netz)

    assert aufrufe == [], (
        f"Die laufende Bridge wurde unnoetig neu aufgebaut: {aufrufe}"
    )

    print("OK: Eine laufende Bridge mit Adresse bleibt unangetastet")

    # ----------------------------------------------------------------
    # 15. Auch beim Einschalten der Freigabe wird nachgesehen
    #
    # Das ist der Moment, in dem die Bridge ihren einzigen von
    # NetworkManager verwalteten Anschluss verliert - also genau der
    # Zeitpunkt, an dem der Ausfall entsteht. Ihn dort zu bemerken ist
    # besser, als ihn beim Zurueckschalten zu reparieren.
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "freigabe-prueft-bridge")
    netz.aktiviere("XRack-Bridge")
    (netz.pfad / "bridge-adresse").unlink()

    assert netz.schalte("xrack-share-toggle.sh", "on").returncode == 0

    aufrufe = (netz.pfad / "calls").read_text(encoding="utf-8")

    assert "connection up XRack-Bridge" in aufrufe, (
        f"Beim Einschalten der Freigabe wurde die Bridge nicht "
        f"nachgesehen:\n{aufrufe}"
    )

    print("OK: Die Freigabe sieht beim Umschalten nach der Bridge")

    # ----------------------------------------------------------------
    # 16. Nach dem Ausschalten muss die Buchse wieder normal laufen
    #
    # Der Fehler, der das noetig gemacht hat: NetworkManager erzeugt
    # seine automatische Kabelverbindung nur, solange fuer das Geraet
    # gar kein Profil passt. Sobald XRack eigene anlegt (Bridge und
    # Freigabe, beide mit "autoconnect no"), hoert das auf. Ohne ein
    # drittes Profil mit "autoconnect yes" bleibt die Buchse danach
    # ohne aktives Profil liegen - keine Adresse, im Router nicht zu
    # sehen. Ein frisch aufgesetzter Pi war so per Kabel nicht mehr
    # erreichbar.
    # ----------------------------------------------------------------

    def kabelprofil_aktiv(netz) -> bool:
        return "XRack-Wired-eth0" in netz.aktiv()

    for skript, wie in (
        ("xrack-bridge-toggle.sh", "Bridge"),
        ("xrack-share-toggle.sh", "Freigabe"),
    ):

        netz = Netzwerk(scratch / f"kabel-zurueck-{skript}")
        netz.aktiviere("XRack-Bridge")
        netz.aktiviere("XRack-Wired-eth0")

        assert netz.schalte(skript, "on").returncode == 0

        assert not kabelprofil_aktiv(netz), (
            f"{wie} an: Die normale Kabelverbindung laeuft weiter - "
            f"beide wollen eth0."
        )
        assert netz.lies("XRack-Wired-eth0", "autoconnect") == "no", (
            f"{wie} an: Die Kabelverbindung wuerde sich eth0 beim "
            f"naechsten Start zurueckholen."
        )

        assert netz.schalte(skript, "off").returncode == 0

        assert netz.lies("XRack-Wired-eth0", "autoconnect") == "yes", (
            f"{wie} aus: Die Buchse bleibt ohne selbsttaetiges Profil "
            f"liegen - nach einem Neustart waere der Pi per Kabel nicht "
            f"mehr erreichbar."
        )
        assert kabelprofil_aktiv(netz), (
            f"{wie} aus: Die Buchse wurde nicht wieder hochgefahren."
        )

    print("OK: Nach dem Ausschalten laeuft die Buchse wieder normal")

    # ----------------------------------------------------------------
    # 17. Auf einem Geraet ohne dieses Profil wird es angelegt
    #
    # Damit niemand fuer die Korrektur install.sh erneut durchlaufen
    # lassen muss.
    # ----------------------------------------------------------------

    netz = Netzwerk(scratch / "kabel-fehlt-noch")

    #
    # Zustand vor dieser Fassung: Das Profil gibt es noch gar nicht.
    #
    (netz.pfad / "connections").write_text(
        "XRack-Home\nXRack-Share-eth0\nXRack-Bridge\nXRack-Bridge-eth0\n",
        encoding="utf-8",
    )

    assert netz.schalte("xrack-share-toggle.sh", "off").returncode == 0

    aufrufe = (netz.pfad / "calls").read_text(encoding="utf-8")

    assert "con-name XRack-Wired-eth0" in aufrufe, (
        f"Das fehlende Kabelprofil wurde nicht angelegt:\n{aufrufe}"
    )

    print("OK: Ein fehlendes Kabelprofil wird nachgelegt")

    
finally:
    shutil.rmtree(scratch, ignore_errors=True)


# ====================================================================
# LAN-Modus
#
# Kein eigener Zustand, sondern der, in dem keiner der beiden anderen
# Zugangswege laeuft. set_lan_mode() schaltet deshalb nur ab, was
# gerade an ist - und fasst das Netzwerk gar nicht an, wenn ohnehin
# schon LAN-Modus herrscht.
# ====================================================================

import logging as _logging
import types as _types

from core.application import Application


def _lan_attrappe(bridge_an: bool, heimnetz_an: bool, erfolg: bool = True):
    """Anwendung mit protokollierenden Schaltern."""

    aufrufe = []

    zeug = _types.SimpleNamespace(
        wlan_control=_types.SimpleNamespace(
            get_status=lambda: {
                "bridge_enabled": bridge_an,
                "console_access_enabled": heimnetz_an,
            },
            set_bridge=lambda an: (
                aufrufe.append(("bridge", an)) or (erfolg, "" if erfolg else "Bridge kaputt")
            ),
            set_share=lambda an: (
                aufrufe.append(("share", an)) or (erfolg, "" if erfolg else "Freigabe kaputt")
            ),
            set_port_forward=lambda an, ip: aufrufe.append(("forward", an)),
        ),
        logger=_logging.getLogger("XRack-Test"),
        _port_forward_applied_ip="10.77.0.5",
    )

    zeug.set_bridge = lambda an: Application.set_bridge(zeug, an)
    zeug.set_console_access = lambda an: Application.set_console_access(zeug, an)

    return zeug, aufrufe


# ---- Access-Point-Weg ist an: nur der wird abgeschaltet -------------

app, aufrufe = _lan_attrappe(bridge_an=True, heimnetz_an=False)

erfolg, meldung = Application.set_lan_mode(app)

assert erfolg is True, meldung
assert ("bridge", False) in aufrufe, aufrufe
assert not any(name == "share" for name, _ in aufrufe), (
    f"Die Heimnetz-Freigabe wurde angefasst, obwohl sie aus war: {aufrufe}"
)

print("OK: LAN-Modus schaltet den Access-Point-Weg ab")


# ---- Heimnetz-Weg ist an: Weiterleitung zuerst weg ------------------

app, aufrufe = _lan_attrappe(bridge_an=False, heimnetz_an=True)

erfolg, _ = Application.set_lan_mode(app)

assert erfolg is True
assert ("share", False) in aufrufe, aufrufe

#
# Die Portweiterleitung muss VOR der Freigabe fallen - danach ist die
# Konsolen-IP nicht mehr bekannt, und die Regel bliebe stehen.
#
assert aufrufe.index(("forward", False)) < aufrufe.index(("share", False)), (
    f"Reihenfolge stimmt nicht: {aufrufe}"
)
assert app._port_forward_applied_ip is None, (
    "Die gemerkte Konsolen-IP wurde nicht verworfen."
)

print("OK: LAN-Modus raeumt die Portweiterleitung vor der Freigabe ab")


# ---- Schon im LAN-Modus: gar nichts anfassen ------------------------

app, aufrufe = _lan_attrappe(bridge_an=False, heimnetz_an=False)

erfolg, _ = Application.set_lan_mode(app)

assert erfolg is True
assert aufrufe == [], (
    f"Im LAN-Modus wurde trotzdem am Netzwerk gedreht: {aufrufe}"
)

print("OK: Ist schon LAN-Modus, wird nichts geschaltet")


# ---- Scheitert das Abschalten, wird das gemeldet --------------------

app, aufrufe = _lan_attrappe(bridge_an=True, heimnetz_an=False, erfolg=False)

erfolg, meldung = Application.set_lan_mode(app)

assert erfolg is False, "Ein Fehlschlag wurde als Erfolg gemeldet"
assert "Bridge kaputt" in meldung, meldung

print("OK: Ein fehlgeschlagenes Umschalten meldet einen Fehler")

print("Alle Tests erfolgreich.")
