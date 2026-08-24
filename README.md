# XRack

*[English](#english) | [Deutsch](#deutsch)*

### Demo

https://github.com/user-attachments/assets/2ce5bc1c-d05e-409c-8a5c-fde638b21ed6

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
- **Practice mix**: combine several stereo files - say a click track,
  your own instrument and the rest of the band from a stem separation -
  into one multichannel recording. File 1 lands on channels 1+2, file 2
  on 3+4 and so on, so at the console you can dial in exactly what you
  want to hear while practising, and fade your own part back in
  whenever you need it.
- **Music player**: shuffle-play a whole folder in a loop (e.g.
  walk-in/break music) or single files, on a freely selectable channel
  pair - shows title/artist from the file's metadata when available.
- **Bluetooth audio**: pair a phone/tablet from the dashboard and
  route its audio stream onto a freely selectable channel pair, just
  like the music player. Deliberately optional and off after every
  restart, since Bluetooth is only partially suited for live use.
- **Reach the console from your home network**: one switch, and the
  console plugged into the Pi's Ethernet port becomes reachable from
  your home network through XRack's own IP - so X32-Edit, X-AIR-Edit or
  Mixing Station work without rewiring anything. The address to type
  into the app is shown right below the switch.
- Level meter, a settings dialog (language, port, Wi-Fi, console
  access, mixer sample rate), optional Wi-Fi client + access point
  setup, installable as a PWA.
- **Copy to USB drive**: plug in a USB stick and a button appears next
  to each recording to copy it straight to the stick's root folder -
  no folder picker, no re-copying a file that's already there.
- **Upload recordings**: add .w64 files to the recording list straight
  from the web interface - handy for playing back a practice mix built
  elsewhere. Recordings and practice mixes are labelled as such in the
  list (and marked `_s` / `_p` in their file names), so it stays clear
  what each file is for.
- **Update from a USB stick**: put the release ZIP from GitHub in the
  root folder of a stick, plug it in and press one button. Recordings,
  music and every setting are kept - and if the web interface doesn't
  come back afterwards, XRack restores the previous version on its own.

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
web interface's language, port, hostname, and a 4-digit PIN that
protects the settings dialog from unauthorized changes (can be changed
later in the settings dialog itself), and optionally sets up Wi-Fi
(home network + access point) and Bluetooth audio - the prompts
explain each step as you go. It also sets up automatic USB drive
mounting, so plugging in a stick is enough for the "copy to USB
drive" button to work - no extra configuration needed.

Afterwards the web interface is reachable at
`https://<hostname>.local:<port>` (default: `https://xrack.local:8080`).
The certificate is self-signed (a real, browser-trusted certificate
isn't possible for a device that's often fully offline on its own
access point) - your browser will show a one-time security warning on
first visit ("Advanced" -> "Proceed anyway"), then remembers the
exception for that device.

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
- **Übungsmix**: Mehrere Stereo-Dateien - etwa Click, das eigene
  Instrument und der Rest der Band aus einer Stem-Trennung - zu einer
  Mehrkanal-Aufnahme zusammenfassen. Datei 1 landet auf Kanal 1+2,
  Datei 2 auf 3+4 und so weiter. Am Pult stellt man sich damit genau
  ein, was man beim Üben hören will, und dreht sich das eigene
  Instrument bei Bedarf dazu.
- **Musikplayer**: Ordner mit Zufallswiedergabe in Dauerschleife (z.B.
  Pausenmusik) oder einzelne Dateien, auf einem frei wählbaren
  Kanalpaar - zeigt Titel/Interpret aus den Metadaten, falls vorhanden.
- **Bluetooth-Audio**: Handy/Tablet direkt vom Dashboard aus koppeln
  und dessen Audiostream auf ein frei wählbares Kanalpaar legen, genau
  wie beim Musikplayer. Bewusst optional und nach jedem Neustart aus,
  da Bluetooth für den Live-Einsatz nur bedingt geeignet ist.
- **Konsole aus dem Heimnetz erreichbar machen**: Ein Schalter, und das
  per Kabel angeschlossene Pult ist aus dem Heimnetz über XRacks eigene
  IP ansprechbar - X32-Edit, X-AIR-Edit oder Mixing Station
  funktionieren damit, ohne etwas umzustecken. Die Adresse, die in die
  App gehört, steht direkt unter dem Schalter.
- Pegelmesser, Einstellungsdialog (Sprache, Port, WLAN, Zugang zur
  Konsole, Mischpult-Samplerate), optionale WLAN-Client- und
  Access-Point-Einrichtung, als PWA installierbar.
- **Auf USB-Stick kopieren**: USB-Stick anschließen, schon erscheint
  neben jeder Aufnahme ein Button, der sie direkt ins Wurzelverzeichnis
  des Sticks kopiert - keine Ordnerauswahl, kein doppeltes Kopieren
  einer bereits vorhandenen Datei.
- **Aufnahmen hochladen**: .w64-Dateien direkt über die Weboberfläche
  in die Aufnahmenliste laden - praktisch, um einen anderswo erzeugten
  Übungsmix abzuspielen. Aufnahmen und Übungsmixe sind in der Liste als
  solche gekennzeichnet (und im Dateinamen mit `_s` bzw. `_p`
  markiert), damit klar bleibt, wofür eine Datei gedacht ist.
- **Update über USB-Stick**: Release-ZIP von GitHub ins
  Wurzelverzeichnis eines Sticks legen, anstecken, einen Knopf drücken.
  Aufnahmen, Musik und sämtliche Einstellungen bleiben erhalten - und
  falls die Weboberfläche danach nicht zurückkommt, stellt XRack den
  vorherigen Stand selbsttätig wieder her.

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
fragt interaktiv nach Sprache, Port und Hostname des Webinterfaces
sowie einer 4-stelligen PIN, die das Einstellungen-Menü vor unbefugten
Änderungen schützt (später im Einstellungen-Menü selbst änderbar), und
richtet optional WLAN (Heimnetz + Access Point) sowie Bluetooth-Audio
ein - die Abfragen dazu erklären sich beim Durchlaufen von selbst.
Außerdem wird das automatische Einhängen von USB-Sticks eingerichtet,
damit der "Auf USB-Stick kopieren"-Button ohne weitere Einrichtung
funktioniert, sobald ein Stick angeschlossen wird.

Danach ist das Webinterface unter `https://<hostname>.local:<port>`
erreichbar (Standard: `https://xrack.local:8080`). Das Zertifikat ist
selbstsigniert (ein "echtes", vom Browser automatisch akzeptiertes
Zertifikat ist für ein Gerät, das oft komplett offline über den
eigenen Access Point läuft, nicht möglich) - der Browser zeigt beim
ersten Aufruf einmalig eine Sicherheitswarnung ("Erweitert" ->
"Trotzdem fortfahren"), merkt sich die Ausnahme danach für dieses
Gerät.

Manuell starten/prüfen:

```bash
sudo systemctl start xrack     # Dienst jetzt starten
sudo systemctl status xrack    # Status prüfen
journalctl -u xrack -f         # Live-Logs ansehen
```

### Lizenz

XRack steht unter der [GNU General Public License v3.0](LICENSE).
