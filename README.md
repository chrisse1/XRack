# XRack

*[English](#english) | [Deutsch](#deutsch)*

<a id="english"></a>

## English

XRack is a web-based multichannel recorder/player built for **live use
with Behringer X-series digital mixing consoles and compatible
devices** (XAir, X32, ...). It runs on a Raspberry Pi and is fully
controlled through a web interface - no screen or keyboard needed on
the Pi itself.

### Features

- **Virtual soundcheck**: record all channels straight from the
  console to Wave64 (.w64), then play them back on the exact same
  channels - lets the band soundcheck without playing live.
- **Music player**: shuffle-play a whole folder in a loop (e.g.
  walk-in/break music) or single files, on a freely selectable channel
  pair - shows title/artist from the file's metadata when available.
- **Bluetooth audio**: pair a phone/tablet from the dashboard and
  route its audio stream onto a freely selectable channel pair, just
  like the music player. Deliberately optional and off after every
  restart, since Bluetooth is only partially suited for live use.
- Level meter, a settings dialog (language/port/Wi-Fi/bridge), optional
  Wi-Fi client + access point setup, installable as a PWA.

### Requirements

Tested hardware:

- Raspberry Pi 5
- Behringer XAir18 (or a comparable Behringer X-series console)
- optional: a MediaTek MT7612U USB Wi-Fi adapter, for the access point

XRack always reads and writes at the mixing console's native channel
count (X-series consoles don't support a reduced channel count) -
selecting individual channels happens purely in software.

### Installation (Raspberry Pi / Debian)

```bash
git clone https://github.com/chrisse1/XRack.git
cd XRack
./install.sh
```

`install.sh` installs all dependencies and sets up a systemd service
that starts XRack automatically on boot. It interactively asks for the
web interface's language, port, and hostname, and optionally sets up
Wi-Fi (home network + access point) and Bluetooth audio - the prompts
explain each step as you go.

Afterwards the web interface is reachable at
`http://<hostname>.local:<port>` (default: `http://xrack.local:8080`).

Start/check manually:

```bash
sudo systemctl start xrack     # start the service now
sudo systemctl status xrack    # check status
journalctl -u xrack -f         # view live logs
```

### License

XRack is licensed under the [GNU General Public License v3.0](LICENSE).

---

<a id="deutsch"></a>

## Deutsch

XRack ist ein webbasiertes Mehrkanal-Recorder/Player-System für den
**Live-Einsatz mit Behringer-Mischpulten der X-Serie und kompatiblen
Geräten** (XAir, X32, ...). Es läuft auf einem Raspberry Pi und wird
komplett über ein Webinterface bedient - kein Bildschirm oder Tastatur
am Pi nötig.

### Funktionen

- **Virtueller Soundcheck**: Alle Kanäle direkt vom Pult in Wave64
  (.w64) aufnehmen, danach exakt auf denselben Kanälen wieder
  abspielen - die Band kann so soundchecken, ohne live zu spielen.
- **Musikplayer**: Ordner mit Zufallswiedergabe in Dauerschleife (z.B.
  Pausenmusik) oder einzelne Dateien, auf einem frei wählbaren
  Kanalpaar - zeigt Titel/Interpret aus den Metadaten, falls vorhanden.
- **Bluetooth-Audio**: Handy/Tablet direkt vom Dashboard aus koppeln
  und dessen Audiostream auf ein frei wählbares Kanalpaar legen, genau
  wie beim Musikplayer. Bewusst optional und nach jedem Neustart aus,
  da Bluetooth für den Live-Einsatz nur bedingt geeignet ist.
- Pegelmesser, Einstellungsdialog (Sprache/Port/WLAN/Bridge),
  optionale WLAN-Client- und Access-Point-Einrichtung, als PWA
  installierbar.

### Voraussetzungen

Getestete Hardware:

- Raspberry Pi 5
- Behringer XAir18 (oder ein vergleichbares Mischpult der X-Serie)
- optional: ein MediaTek MT7612U USB-WLAN-Adapter, für den Access Point

XRack liest und schreibt immer mit der nativen Kanalzahl des
Mischpults (die X-Serie unterstützt keine reduzierte Kanalzahl) - die
Auswahl einzelner Kanäle passiert rein in Software.

### Installation (Raspberry Pi / Debian)

```bash
git clone https://github.com/chrisse1/XRack.git
cd XRack
./install.sh
```

`install.sh` installiert alle Abhängigkeiten und richtet einen
systemd-Dienst ein, der XRack automatisch beim Booten startet. Es
fragt interaktiv nach Sprache, Port und Hostname des Webinterfaces und
richtet optional WLAN (Heimnetz + Access Point) sowie Bluetooth-Audio
ein - die Abfragen dazu erklären sich beim Durchlaufen von selbst.

Danach ist das Webinterface unter `http://<hostname>.local:<port>`
erreichbar (Standard: `http://xrack.local:8080`).

Manuell starten/prüfen:

```bash
sudo systemctl start xrack     # Dienst jetzt starten
sudo systemctl status xrack    # Status prüfen
journalctl -u xrack -f         # Live-Logs ansehen
```

### Lizenz

XRack steht unter der [GNU General Public License v3.0](LICENSE).
