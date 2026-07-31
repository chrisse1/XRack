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
source .venv/bin/activate
python main.py
```

`install.sh` installiert dabei auch `ffmpeg` (für den Musikspieler,
dekodiert MP3/FLAC/... zu Rohdaten) und `alsa-utils` (für die
Geräteerkennung) über `apt`.
