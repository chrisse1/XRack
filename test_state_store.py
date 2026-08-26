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

    # ---------------------------------------------------------
    # 5. Der Schreibvorgang ist unteilbar
    #
    # XRack laeuft auf einem Geraet, das auch mal einfach vom Strom
    # getrennt wird. Wird direkt in die Zieldatei geschrieben, gibt es
    # einen Moment, in dem sie abgeschnitten dasteht - und beim
    # naechsten Start faengt load() das zwar ab, startet dann aber
    # still mit leerem Zustand. Saemtliche Einstellungen waeren weg,
    # ohne dass irgendwo etwas aufblinkt.
    #
    # Geprueft wird deshalb nicht das Ergebnis, sondern der Weg
    # dorthin: Waehrend geschrieben wird, muss die Zieldatei entweder
    # ihren alten Inhalt haben oder den neuen - nie etwas dazwischen.
    # ---------------------------------------------------------

    import json
    import threading

    atom_path = Path(tmp_dir) / "config" / "atomar.json"

    store5 = StateStore(atom_path)
    store5.set("wert", "alt")

    gesehen = []
    weiter = threading.Event()

    def mitlesen():
        """Liest die Zieldatei, waehrend geschrieben wird."""

        while not weiter.is_set():

            try:
                gesehen.append(json.loads(atom_path.read_text(encoding="utf-8")))
            except FileNotFoundError:
                gesehen.append("fehlt")
            except json.JSONDecodeError:
                gesehen.append("halb")
            except OSError:
                pass

    leser = threading.Thread(target=mitlesen, daemon=True)
    leser.start()

    #
    # Viele Schreibvorgaenge mit wachsendem Inhalt, damit der Leser
    # moeglichst oft mitten hinein faellt.
    #
    for runde in range(200):
        store5.set("wert", "neu" * (runde + 1))

    weiter.set()
    leser.join(timeout=5.0)

    assert gesehen, "Der Leser hat gar nichts gesehen - Test taugt nichts."

    kaputt = [g for g in gesehen if g in ("halb", "fehlt")]

    assert not kaputt, (
        f"Bei {len(kaputt)} von {len(gesehen)} Blicken stand die Datei "
        f"unvollstaendig da - der Schreibvorgang ist nicht unteilbar."
    )

    print(
        f"OK: Waehrend {len(gesehen)} Blicken war die Zustandsdatei nie "
        f"unvollstaendig"
    )

    #
    # Und die Nebendatei darf nicht liegenbleiben.
    #
    assert not atom_path.with_suffix(".tmp").exists(), (
        "Die temporaere Datei wurde nicht aufgeraeumt."
    )

    print("OK: Es bleibt keine Nebendatei liegen")

print("Alle Tests erfolgreich.")
