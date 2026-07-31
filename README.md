# XRack

XRack ist ein webbasiertes Mehrkanal-Aufnahme- und Playback-System für
digitale Mischpulte. Es läuft auf einem Raspberry Pi und wird komplett
über ein Webinterface bedient - kein Bildschirm oder Tastatur am Pi
nötig.

## Funktionen

- **Mehrkanalaufnahme** direkt vom Mischpult in Wave64 (.w64), mit frei
  wählbarer Kanalzahl
- **Virtueller Soundcheck**: Aufnahmen werden auf denselben Kanälen
  wiedergegeben, auf denen sie aufgenommen wurden
- **Musikplayer**: Ordner mit Zufallswiedergabe und Dauerschleife
  (z.B. Pause-Musik) oder einzelne Dateien, jeweils auf einem frei
  wählbaren Kanalpaar
- **Pegelmesser** zur Kontrolle der Eingangspegel vor der Aufnahme
- **Webinterface** (Bootstrap), auch als PWA installierbar ("Zum
  Home-Bildschirm hinzufügen" auf iPad/Handy)
- **Installierbar per Script**, inkl. automatischem Start beim Booten
  über systemd

## Voraussetzungen

XRack liest und schreibt immer mit der nativen Kanalzahl des
angeschlossenen Audio-Interfaces (Behringer X-Serie & kompatible
digitale Mischpulte unterstützen keine reduzierte Kanalzahl) - die
Auswahl einzelner Kanäle passiert in Software.

Getestet mit:

- Behringer XAir 18 an einem Raspberry Pi 5, Debian Trixie

Ein Test mit dem Behringer X32 steht noch aus.

## Installation (Raspberry Pi / Debian)

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

Nach der Installation ist das Webinterface unter
`http://<ip-des-pi>:8080` erreichbar.

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

## Lizenz

XRack steht unter der [GNU General Public License v3.0](LICENSE).
