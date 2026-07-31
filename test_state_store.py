"""
Prüft StateStore: Speichern/Laden, fehlende Datei, beschädigte
Datei.
"""

import tempfile
from pathlib import Path

from core.state_store import StateStore

with tempfile.TemporaryDirectory() as tmp_dir:

    state_path = Path(tmp_dir) / "config" / "state.json"

    # ---------------------------------------------------------
    # 1. Fehlende Datei -> leerer Zustand, Standardwerte greifen
    # ---------------------------------------------------------

    store = StateStore(state_path)
    assert store.get("audio_device_id") is None
    assert store.get("record_channels", 18) == 18
    print("OK: Fehlende Datei liefert Standardwerte")

    # ---------------------------------------------------------
    # 2. Speichern und in einer neuen Instanz wiederfinden
    # ---------------------------------------------------------

    store.set("audio_device_id", "hw:1,0")
    store.set("record_channels", 8)
    store.set("music_channel", 17)

    assert state_path.exists(), "set() sollte die Datei sofort anlegen."

    store2 = StateStore(state_path)
    assert store2.get("audio_device_id") == "hw:1,0"
    assert store2.get("record_channels") == 8
    assert store2.get("music_channel") == 17
    print("OK: Gespeicherte Werte werden in neuer Instanz korrekt geladen")

    # ---------------------------------------------------------
    # 3. Werte überschreiben
    # ---------------------------------------------------------

    store2.set("record_channels", 18)
    store3 = StateStore(state_path)
    assert store3.get("record_channels") == 18
    print("OK: Überschreiben funktioniert")

    # ---------------------------------------------------------
    # 4. Beschädigte Datei -> kein Absturz, leerer Zustand
    # ---------------------------------------------------------

    state_path.write_text("{ das ist kein gueltiges JSON", encoding="utf-8")

    store4 = StateStore(state_path)
    assert store4.get("record_channels", 18) == 18
    print("OK: Beschädigte Datei führt nicht zum Absturz")

print("Alle Tests erfolgreich.")
