# XRack

*[English](#english) | [Deutsch](#deutsch)*

<a id="english"></a>

## English

XRack is a web-based multichannel recording and playback system for
digital mixing consoles. It runs on a Raspberry Pi and is fully
controlled through a web interface - no screen or keyboard needed on
the Pi itself.

### Features

- **Multichannel recording** straight from the mixing console to
  Wave64 (.w64), with a freely selectable channel count
- **Virtual soundcheck**: recordings are played back on the same
  channels they were recorded on
- **Music player**: shuffle playback with looping for a whole folder
  (e.g. walk-in music) or single files, each on a freely selectable
  channel pair
- **Level meter** to check input levels before recording
- **Web interface** (Bootstrap) in German or English, installable as a
  PWA ("Add to Home Screen" on iPad/phone)
- **Settings dialog** (gear icon in the header) to change language,
  port, home Wi-Fi/access point credentials, and the Ethernet+AP
  bridge - no re-running the installer needed
- **Installable via script**, including automatic startup on boot via
  systemd

### Requirements

XRack always reads and writes at the native channel count of the
connected audio interface (Behringer X-series & compatible digital
mixing consoles don't support a reduced channel count) - selecting
individual channels happens in software.

Tested with:

- Behringer XAir 18 on a Raspberry Pi 5, Debian Trixie

A test with the Behringer X32 is still pending.

### Installation (Raspberry Pi / Debian)

```bash
git clone <repo-url> XRack
cd XRack
./install.sh
```

`install.sh` also installs `ffmpeg` (for the music player, decodes
MP3/FLAC/... to raw data) and `alsa-utils` (for device detection) via
`apt`, sets up a systemd service that starts XRack automatically on
boot, and grants the service user a tightly scoped sudo permission to
shut down the Pi via the web interface (nothing else - XRack does not
run as root).

Along the way it interactively asks for the preferred language of the
web interface (German or English), the desired port (default: 8080),
and a hostname (default: `xrack`) - saving language and port to
`config/local.yaml` and setting the hostname at the system level via
`hostnamectl`. All three can be changed later: language/port by
editing `config/local.yaml`, the hostname via `hostnamectl
set-hostname <name>` - followed by a service restart
(`sudo systemctl restart xrack`).

After installation the web interface is reachable at
`http://<hostname>.local:<chosen-port>` (default:
`http://xrack.local:8080`) via mDNS (Avahi), or by IP address as a
fallback (`http://<pi-ip>:<chosen-port>`).

Optionally (if two Wi-Fi interfaces are detected and NetworkManager's
`nmcli` is available), the installer can also set up Wi-Fi: one
interface joins your home network as a client (for remote access to
XRack), the other spans its own access point (default name `XRack`)
so a mixing app can talk to XRack/the mixing console directly,
standalone, without any router on site. It also asks for your Wi-Fi
country (ISO code, e.g. `DE`/`US`/`GB`) and sets it via `raspi-config`
- without it, Wi-Fi is often soft-blocked by `rfkill` on a freshly
flashed Pi that never went through the interactive first-boot wizard.
Both connections are configured as NetworkManager connection profiles
(`XRack-Home` / `XRack-AP`) and can be changed later via `nmcli` or
`nmtui`. If a mixing console is connected via Ethernet, the installer
can additionally bridge that Ethernet interface with the access point
(`XRack-Bridge`) so the console and app-connected phones/tablets end
up on the same network - otherwise a control app on an AP client
generally can't discover the console at all, since it lives on a
separate, unreachable subnet. The bridge is only prepared during
installation, not activated immediately - many people configure a
freshly flashed Pi over SSH via Ethernet, and bridging eth0 right away
would cut that session. It's applied on the next reboot instead, which
the installer offers to do right at the end, once everything else is
already set up.

Start/check manually:

```bash
sudo systemctl start xrack     # start the service now
sudo systemctl status xrack    # check status
journalctl -u xrack -f         # view live logs
```

For manual development/troubleshooting outside the service (e.g. as
used so far in this project):

```bash
sudo systemctl stop xrack      # stop the service so port 8080 is free
source .venv/bin/activate
python main.py
```

### License

XRack is licensed under the [GNU General Public License v3.0](LICENSE).

---

<a id="deutsch"></a>

## Deutsch

XRack ist ein webbasiertes Mehrkanal-Aufnahme- und Playback-System für
digitale Mischpulte. Es läuft auf einem Raspberry Pi und wird komplett
über ein Webinterface bedient - kein Bildschirm oder Tastatur am Pi
nötig.

### Funktionen

- **Mehrkanalaufnahme** direkt vom Mischpult in Wave64 (.w64), mit frei
  wählbarer Kanalzahl
- **Virtueller Soundcheck**: Aufnahmen werden auf denselben Kanälen
  wiedergegeben, auf denen sie aufgenommen wurden
- **Musikplayer**: Ordner mit Zufallswiedergabe und Dauerschleife
  (z.B. Pause-Musik) oder einzelne Dateien, jeweils auf einem frei
  wählbaren Kanalpaar
- **Pegelmesser** zur Kontrolle der Eingangspegel vor der Aufnahme
- **Webinterface** (Bootstrap) auf Deutsch oder Englisch, auch als PWA
  installierbar ("Zum Home-Bildschirm hinzufügen" auf iPad/Handy)
- **Einstellungsdialog** (Zahnrad-Icon im Header) für Sprache, Port,
  Heimnetz-/Access-Point-Zugangsdaten und die Ethernet+AP-Bridge -
  ganz ohne erneutes Ausführen des Installationsskripts
- **Installierbar per Script**, inkl. automatischem Start beim Booten
  über systemd

### Voraussetzungen

XRack liest und schreibt immer mit der nativen Kanalzahl des
angeschlossenen Audio-Interfaces (Behringer X-Serie & kompatible
digitale Mischpulte unterstützen keine reduzierte Kanalzahl) - die
Auswahl einzelner Kanäle passiert in Software.

Getestet mit:

- Behringer XAir 18 an einem Raspberry Pi 5, Debian Trixie

Ein Test mit dem Behringer X32 steht noch aus.

### Installation (Raspberry Pi / Debian)

```bash
git clone <repo-url> XRack
cd XRack
./install.sh
```

`install.sh` installiert dabei auch `ffmpeg` (für den Musikspieler,
dekodiert MP3/FLAC/... zu Rohdaten) und `alsa-utils` (für die
Geräteerkennung) über `apt`, richtet einen systemd-Dienst ein, der
XRack automatisch beim Booten startet, und erteilt dem Dienst-
Benutzer eine eng begrenzte sudo-Berechtigung, um den Pi über das
Webinterface herunterfahren zu können (sonst nichts - XRack läuft
nicht als root).

Dabei fragt es interaktiv nach der bevorzugten Sprache des
Webinterfaces (Deutsch oder Englisch), dem gewünschten Port (Standard:
8080) sowie einem Hostnamen (Standard: `xrack`) - Sprache und Port
werden in `config/local.yaml` gespeichert, der Hostname wird direkt
auf Systemebene per `hostnamectl` gesetzt. Alle drei lassen sich
später ändern: Sprache/Port durch Bearbeiten von `config/local.yaml`,
der Hostname per `hostnamectl set-hostname <name>` - jeweils gefolgt
von einem Neustart des Dienstes (`sudo systemctl restart xrack`).

Nach der Installation ist das Webinterface per mDNS (Avahi) unter
`http://<hostname>.local:<gewählter-port>` erreichbar (Standard:
`http://xrack.local:8080`), alternativ per IP-Adresse
(`http://<ip-des-pi>:<gewählter-port>`).

Optional (falls zwei WLAN-Interfaces erkannt werden und
NetworkManagers `nmcli` vorhanden ist) richtet der Installer auch WLAN
ein: ein Interface verbindet sich als Client mit deinem Heimnetz (für
Fernzugriff auf XRack), das andere spannt einen eigenen Access Point
auf (Standardname `XRack`), über den z.B. eine Misch-App direkt mit
XRack/dem Mischpult sprechen kann - komplett standalone, ganz ohne
Router vor Ort. Dabei wird auch nach dem WLAN-Land gefragt (ISO-Code,
z.B. `DE`/`AT`/`CH`) und per `raspi-config` gesetzt - ohne das bleibt
WLAN auf einem frisch geflashten Pi, der nie durch den interaktiven
Ersteinrichtungs-Assistenten gelaufen ist, oft per `rfkill`
softblockiert. Beides wird als NetworkManager-Verbindungsprofil
(`XRack-Home` / `XRack-AP`) angelegt und lässt sich später per `nmcli`
oder `nmtui` ändern. Hängt ein Mischpult per Ethernet am Pi, kann der
Installer dieses Ethernet-Interface zusätzlich mit dem Access Point
bridgen (`XRack-Bridge`), damit Pult und per App verbundene
Handys/Tablets im selben Netz landen - sonst findet eine Steuer-App
auf einem AP-Client das Pult in der Regel gar nicht, weil es in einem
separaten, nicht erreichbaren Subnetz hängt. Die Bridge wird bei der
Installation nur vorbereitet, nicht sofort aktiviert - viele
konfigurieren einen frisch geflashten Pi per SSH über Ethernet, und
eth0 sofort zu bridgen würde genau diese Verbindung kappen. Aktiv wird
sie erst beim nächsten Neustart, den der Installer ganz am Ende
anbietet, wenn der Rest der Installation bereits fertig ist.

Manuell starten/prüfen:

```bash
sudo systemctl start xrack     # Dienst jetzt starten
sudo systemctl status xrack    # Status prüfen
journalctl -u xrack -f         # Live-Logs ansehen
```

Für die manuelle Entwicklung/Fehlersuche außerhalb des Dienstes
(z.B. wie bisher in diesem Projekt):

```bash
sudo systemctl stop xrack      # Dienst anhalten, damit Port 8080 frei ist
source .venv/bin/activate
python main.py
```

### Lizenz

XRack steht unter der [GNU General Public License v3.0](LICENSE).
