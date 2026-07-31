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
web interface (German or English) and the desired port (default:
8080), and saves both to `config/local.yaml`. Both can be changed
later at any time by editing that file and restarting the service
(`sudo systemctl restart xrack`).

After installation the web interface is reachable at
`http://<pi-ip>:<chosen-port>` (default: port 8080).

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
Webinterfaces (Deutsch oder Englisch) sowie dem gewünschten Port
(Standard: 8080) und speichert beides in `config/local.yaml`. Beides
lässt sich später jederzeit durch Bearbeiten dieser Datei und einen
Neustart des Dienstes (`sudo systemctl restart xrack`) ändern.

Nach der Installation ist das Webinterface unter
`http://<ip-des-pi>:<gewählter-port>` erreichbar (Standard: Port 8080).

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
