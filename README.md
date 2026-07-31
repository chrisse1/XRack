# XRack

XRack ist ein webbasiertes Mehrkanal-Aufnahme- und Playback-System für digitale Mischpulte.

## Funktionen

- Mehrkanalaufnahme bis 32 Kanäle
- Wave64 (.w64)
- Virtueller Soundcheck
- Musikplayer
- Webinterface
- Installierbar per Script

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
