"""
Prüft die Diagnose-Aufzeichnung (core/diagnostics.py).

Der wichtigste Teil ist die Lückenerkennung: Ein Wächter innerhalb des
überwachten Programms kann seinen eigenen Stillstand nicht melden -
sichtbar wird er nur als Lücke in der Zeitreihe. Wird die nicht
ausdrücklich erkannt und beziffert, geht genau der Befund verloren, für
den die Aufzeichnung gebaut wurde.

Ebenso wichtig: Ausgeschaltet darf sie nichts kosten, und ein Fehler in
der Messung darf die Aufzeichnung nicht beenden.
"""

import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

#
# Application zieht die Audio-Kette mit rein - alsaaudio gibt es hier
# nicht. Ein Fake-Modul genügt, dieser Test benutzt es nie.
#
fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE",
    "PCM_FORMAT_S24_LE",
    "PCM_FORMAT_S24_3LE",
    "PCM_FORMAT_S32_LE",
    "PCM_CAPTURE",
    "PCM_PLAYBACK",
    "PCM_NORMAL",
    "PCM_NONBLOCK",
):
    setattr(fake_alsaaudio, name, 0)

fake_alsaaudio.ALSAAudioError = Exception
fake_alsaaudio.cards = lambda: []
fake_alsaaudio.pcms = lambda *args, **kwargs: []
fake_alsaaudio.PCM = type("FakePCM", (), {"__init__": lambda self, *a, **k: None})
sys.modules["alsaaudio"] = fake_alsaaudio

import core.diagnostics as diagnostics_module
from core.diagnostics import Diagnostics


class FakeRecorder:
    recording = False


class FakePlayer:
    playing = False
    current_filename = ""


class FakeBluetoothPlayer:
    streaming = False


class FakeApplication:
    """Nur so viel Application, wie die Diagnose anfasst."""

    def __init__(self):
        self.recorder = FakeRecorder()
        self.player = FakePlayer()
        self.music_player = FakePlayer()
        self.bluetooth_player = FakeBluetoothPlayer()
        self.config = types.SimpleNamespace(
            data=types.SimpleNamespace(
                server=types.SimpleNamespace(port=8080)
            )
        )


scratch = Path(tempfile.mkdtemp(prefix="xrack_diag_test_"))

#
# Aufzeichnung ins Testverzeichnis umlenken, damit der Lauf nichts im
# Projekt hinterlässt.
#
diagnostics_module.LOG_DIR = scratch
diagnostics_module.LOG_FILE = scratch / "diagnose.log"

try:

    # ----------------------------------------------------------------
    # 1. Ausgeschaltet kostet nichts
    # ----------------------------------------------------------------

    application = FakeApplication()
    diagnostics = Diagnostics(application)

    assert diagnostics.enabled is False
    assert diagnostics._thread is None, "Ohne Start darf kein Thread laufen."

    status = diagnostics.get_status()
    assert status["enabled"] is False
    assert status["size"] == 0

    #
    # Stoppen ohne Start darf nicht knallen
    #
    diagnostics.stop()

    print("OK: Ausgeschaltet läuft kein Thread und es entsteht keine Datei")

    # ----------------------------------------------------------------
    # 2. Lückenerkennung - der Kern
    #
    # Steht der Prozess, fehlen Messungen. Genau das muss als Lücke
    # samt Dauer in der Aufzeichnung stehen.
    # ----------------------------------------------------------------

    diagnostics = Diagnostics(FakeApplication())
    writer = diagnostics._open_writer()

    #
    # Messung und Netzabfragen durch Attrappen ersetzen - der Test
    # prüft die Schreiblogik, nicht das Netzwerk.
    #
    diagnostics._self_check = lambda port: "ok"
    diagnostics._ping = lambda host: True
    diagnostics._default_route = lambda: ("192.168.1.1", "wlan0")
    diagnostics._temperature = lambda: "45C"
    diagnostics._load = lambda: "0.10"

    diagnostics_module.INTERVAL = 0.01
    diagnostics_module.HEARTBEAT = 0.05
    diagnostics_module.GAP_THRESHOLD = 0.2

    diagnostics.enabled = True

    import threading

    thread = threading.Thread(target=diagnostics._loop, daemon=True)
    thread.start()

    time.sleep(0.1)

    #
    # Stillstand simulieren: Der Thread selbst schläft nicht - wir
    # halten ihn an, indem wir den Takt kurz aussetzen lassen. Dafür
    # genügt es, die Zeitrechnung zu überspringen: Wir warten länger
    # als die Schwelle, ohne dass der Thread misst.
    #
    diagnostics._stop.set()
    thread.join(timeout=1.0)

    diagnostics._stop.clear()
    time.sleep(0.4)

    thread = threading.Thread(target=diagnostics._loop, daemon=True)
    thread.start()
    time.sleep(0.1)

    diagnostics.enabled = False
    diagnostics._stop.set()
    thread.join(timeout=1.0)

    for handler in writer.handlers:
        handler.flush()

    content = diagnostics_module.LOG_FILE.read_text(encoding="utf-8")

    assert "Aufzeichnung gestartet" in content, content
    assert "xrack=ok" in content, content
    assert "netz=ok" in content, content
    assert "aktiv=leerlauf" in content, content

    print("OK: Normale Messungen landen in der Aufzeichnung")

    # ----------------------------------------------------------------
    # 2b. Lücke wird ausdrücklich beziffert
    # ----------------------------------------------------------------

    diagnostics = Diagnostics(FakeApplication())
    diagnostics._close_writer()
    diagnostics_module.LOG_FILE.unlink(missing_ok=True)

    writer = diagnostics._open_writer()

    #
    # Den Zeitgeber so manipulieren, dass zwischen zwei Durchläufen
    # scheinbar viel Zeit vergeht - genau die Situation "Prozess stand".
    #
    ticks = iter([0.0, 12.0, 12.01, 12.02])
    real_monotonic = time.monotonic
    diagnostics_module.time.monotonic = lambda: next(ticks, 99.0)

    diagnostics._self_check = lambda port: "ok"
    diagnostics._ping = lambda host: True
    diagnostics._default_route = lambda: ("192.168.1.1", "wlan0")
    diagnostics._temperature = lambda: "45C"
    diagnostics._load = lambda: "0.10"

    diagnostics.enabled = True

    #
    # Zwei Durchläufe genügen: Der zweite sieht die künstliche Lücke.
    #
    def stop_after_two():
        time.sleep(0.05)
        diagnostics._stop.set()

    threading.Thread(target=stop_after_two, daemon=True).start()
    diagnostics._loop()

    diagnostics_module.time.monotonic = real_monotonic

    for handler in writer.handlers:
        handler.flush()

    content = diagnostics_module.LOG_FILE.read_text(encoding="utf-8")

    assert "LÜCKE" in content, (
        f"Ein Stillstand von 12 s wurde nicht als Lücke vermerkt:\n{content}"
    )
    assert "12.0 s" in content, (
        f"Die Dauer der Lücke fehlt oder stimmt nicht:\n{content}"
    )

    print("OK: Ein Stillstand wird als Lücke mit Dauer vermerkt")

    # ----------------------------------------------------------------
    # 3. Auffälligkeiten werden immer geschrieben
    # ----------------------------------------------------------------

    diagnostics = Diagnostics(FakeApplication())
    diagnostics._close_writer()
    diagnostics_module.LOG_FILE.unlink(missing_ok=True)
    writer = diagnostics._open_writer()

    diagnostics._default_route = lambda: ("192.168.1.1", "wlan0")
    diagnostics._temperature = lambda: "45C"
    diagnostics._load = lambda: "0.10"
    diagnostics._self_check = lambda port: "KEINE-ANTWORT"
    diagnostics._ping = lambda host: False

    diagnostics_module.HEARTBEAT = 9999.0

    for _ in range(3):
        diagnostics._sample(writer, 8080)

    for handler in writer.handlers:
        handler.flush()

    content = diagnostics_module.LOG_FILE.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if "xrack=" in line]

    assert len(lines) == 3, (
        f"Auffällige Messungen müssen jedes Mal geschrieben werden, "
        f"nicht nur bei Änderung - gefunden: {len(lines)}\n{content}"
    )
    assert "KEINE-ANTWORT" in content and "netz=WEG" in content

    print("OK: Auffälligkeiten werden bei jeder Messung geschrieben")

    # ----------------------------------------------------------------
    # 4. Im Normalfall keine Zeilenflut
    # ----------------------------------------------------------------

    diagnostics = Diagnostics(FakeApplication())
    diagnostics._close_writer()
    diagnostics_module.LOG_FILE.unlink(missing_ok=True)
    writer = diagnostics._open_writer()

    diagnostics._default_route = lambda: ("192.168.1.1", "wlan0")
    diagnostics._temperature = lambda: "45C"
    diagnostics._load = lambda: "0.10"
    diagnostics._self_check = lambda port: "ok"
    diagnostics._ping = lambda host: True

    diagnostics_module.HEARTBEAT = 9999.0

    for _ in range(10):
        diagnostics._sample(writer, 8080)

    for handler in writer.handlers:
        handler.flush()

    content = diagnostics_module.LOG_FILE.read_text(encoding="utf-8")
    lines = [line for line in content.splitlines() if "xrack=" in line]

    assert len(lines) == 1, (
        f"Bei unverändertem Zustand darf nur eine Zeile entstehen, "
        f"nicht {len(lines)} - sonst läuft die Datei voll.\n{content}"
    )

    print("OK: Unveränderter Zustand erzeugt keine Zeilenflut")

    # ----------------------------------------------------------------
    # 5. Zustandswechsel wird festgehalten
    #
    # Das ist der eigentliche Mehrwert gegenüber einem externen
    # Skript: Was tat XRack, als es passierte?
    # ----------------------------------------------------------------

    application = FakeApplication()
    diagnostics = Diagnostics(application)
    diagnostics._close_writer()
    diagnostics_module.LOG_FILE.unlink(missing_ok=True)
    writer = diagnostics._open_writer()

    diagnostics._default_route = lambda: ("192.168.1.1", "wlan0")
    diagnostics._temperature = lambda: "45C"
    diagnostics._load = lambda: "0.10"
    diagnostics._self_check = lambda port: "ok"
    diagnostics._ping = lambda host: True

    diagnostics._sample(writer, 8080)

    application.player.playing = True
    application.player.current_filename = "Bohemian Rhapsody-1_p.w64"

    diagnostics._sample(writer, 8080)

    for handler in writer.handlers:
        handler.flush()

    content = diagnostics_module.LOG_FILE.read_text(encoding="utf-8")

    assert "aktiv=leerlauf" in content
    assert "wiedergabe:Bohemian Rhapsody-1_p.w64" in content, (
        f"Der Wechsel in die Wiedergabe fehlt:\n{content}"
    )

    print("OK: XRacks eigener Zustand steht in der Aufzeichnung")

    # ----------------------------------------------------------------
    # 6. Ein Fehler in der Messung beendet die Aufzeichnung nicht
    # ----------------------------------------------------------------

    diagnostics = Diagnostics(FakeApplication())
    diagnostics._close_writer()
    diagnostics_module.LOG_FILE.unlink(missing_ok=True)

    def exploding_activity():
        raise RuntimeError("Simulierter Fehler")

    diagnostics._activity = exploding_activity
    diagnostics._default_route = lambda: ("192.168.1.1", "wlan0")
    diagnostics._self_check = lambda port: "ok"
    diagnostics._ping = lambda host: True

    diagnostics_module.INTERVAL = 0.01
    diagnostics.enabled = True

    def stop_soon():
        time.sleep(0.08)
        diagnostics._stop.set()

    threading.Thread(target=stop_soon, daemon=True).start()

    #
    # Darf nicht mit einer Ausnahme abbrechen
    #
    diagnostics._loop()

    content = diagnostics_module.LOG_FILE.read_text(encoding="utf-8")

    assert "Messung fehlgeschlagen" in content, content
    assert "Aufzeichnung beendet" in content, (
        f"Die Schleife ist an einem Messfehler gestorben:\n{content}"
    )

    print("OK: Ein Fehler in der Messung beendet die Aufzeichnung nicht")

    print("Alle Tests erfolgreich.")

finally:
    shutil.rmtree(scratch, ignore_errors=True)
