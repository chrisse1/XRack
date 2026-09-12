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

    # ----------------------------------------------------------------
    # 7. Ein einzelner verlorener Ping ist kein Ausfall
    #
    # Anlass ist eine Zeile vom Gerät: "netz=WEG" stand dort nach
    # EINEM verlorenen Ping. Auf WLAN ist ein verlorenes ICMP-Paket
    # Alltag, und manche Router beantworten ohnehin nicht jeden Ping -
    # als Befund ist das wertlos, und es verdeckt die echten Ausfälle.
    # ----------------------------------------------------------------

    def frisch(antwort_fehlt=True):
        """Eine Diagnose mit Attrappen, Datei geleert."""

        d = Diagnostics(FakeApplication())
        d._close_writer()
        diagnostics_module.LOG_FILE.unlink(missing_ok=True)
        w = d._open_writer()

        d._default_route = lambda: ("192.168.1.1", "wlan0")
        d._temperature = lambda: "45C"
        d._load = lambda: "0.10"
        d._self_check = lambda port: "ok"
        d._adresse = lambda interface: "192.168.1.50/24"
        d._stromsparen = lambda interface: "on"

        diagnostics_module.HEARTBEAT = 9999.0

        return d, w


    def zeilen_von(d, w):

        for handler in w.handlers:
            handler.flush()

        return diagnostics_module.LOG_FILE.read_text(encoding="utf-8")


    proband, schreiber = frisch()
    proband._ping = lambda host: False

    proband._sample(schreiber, 8080)

    inhalt = zeilen_von(proband, schreiber)

    assert "netz=?(1)" in inhalt, (
        f"Nach EINEM verlorenen Ping steht schon ein Urteil da:\n{inhalt}"
    )

    assert "WEG" not in inhalt, (
        f"Ein verlorenes Paket gilt als Netzausfall:\n{inhalt}"
    )

    print("OK: Ein verlorener Ping ergibt ein Fragezeichen, keinen Befund")

    # ----------------------------------------------------------------
    # 8. Drei in Folge sind ein Ausfall - mit Beginn, Dauer und Ende
    # ----------------------------------------------------------------

    proband, schreiber = frisch()
    proband._ping = lambda host: False

    for _ in range(4):
        proband._sample(schreiber, 8080)

    inhalt = zeilen_von(proband, schreiber)

    assert "netz=WEG(3)" in inhalt and "netz=WEG(4)" in inhalt, inhalt

    assert inhalt.count("AUSFALL beginnt") == 1, (
        f"Der Beginn des Ausfalls steht nicht genau einmal da:\n{inhalt}"
    )

    #
    # Und im Beginn stehen die zwei Angaben, die den Fehler einordnen:
    # Ist die Adresse noch da (dann Paketverlust) oder weg (dann
    # Verbindung/DHCP)? Und schläft die Karte?
    #
    assert "adresse=192.168.1.50/24" in inhalt, inhalt
    assert "ps=on" in inhalt, inhalt

    #
    # Jetzt kommt das Netz zurück: eine Zeile, die den Fall abschliesst.
    #
    proband._ping = lambda host: True
    proband._sample(schreiber, 8080)

    inhalt = zeilen_von(proband, schreiber)

    assert inhalt.count("WIEDER-DA") == 1, (
        f"Die abschliessende Zeile fehlt oder steht mehrfach da - dann "
        f"muss man Zeilen zählen, um die Dauer zu erfahren:\n{inhalt}"
    )

    assert "(4 Versuche)" in inhalt, inhalt
    assert "netz=ok" in inhalt.splitlines()[-1], inhalt.splitlines()[-1]

    #
    # Und danach ist der Zähler zurückgesetzt: Ein neuer Fehlschlag
    # beginnt wieder bei eins.
    #
    proband._ping = lambda host: False
    proband._sample(schreiber, 8080)

    assert "netz=?(1)" in zeilen_von(proband, schreiber).splitlines()[-1]

    print("OK: Ein Ausfall wird mit Beginn, Dauer und Ende festgehalten")

    # ----------------------------------------------------------------
    # 9. Ohne Standardroute ist das Netz nicht "weg"
    #
    # Ohne Gateway pingt XRack ins Leere - das sah bisher wie ein
    # Funkloch aus, ist aber ein fehlendes Profil.
    # ----------------------------------------------------------------

    proband, schreiber = frisch()
    proband._default_route = lambda: ("", "")
    proband._ping = lambda host: False

    proband._sample(schreiber, 8080)

    inhalt = zeilen_von(proband, schreiber)

    assert "KEIN-GATEWAY" in inhalt, inhalt
    assert "WEG" not in inhalt, inhalt

    print("OK: Eine fehlende Standardroute heisst nicht 'Netz weg'")

    # ----------------------------------------------------------------
    # 10. Die Funkdaten - der Beacon-Zähler ist der Punkt
    #
    # Springt er, schläft die Karte oder verliert den Anschluss. Er ist
    # die einzige Messung, die das von aussen zeigt.
    # ----------------------------------------------------------------

    funk = scratch / "wireless"
    funk.write_text(
        "Inter-| sta-|   Quality        |   Discarded packets\n"
        " face | tus | link level noise |  nwid  crypt   frag  retry   misc\n"
        " wlan0: 0000   70.  -53.  -256        0      0      0      0     0"
        "        12\n",
        encoding="utf-8",
    )

    netz_sys = scratch / "net"
    (netz_sys / "wlan0").mkdir(parents=True)
    (netz_sys / "wlan0" / "wireless").mkdir()

    diagnostics_module.WIRELESS_PROC = funk
    diagnostics_module.NET_SYS = netz_sys

    proband, schreiber = frisch()
    proband._ping = lambda host: True

    proband._sample(schreiber, 8080)

    inhalt = zeilen_von(proband, schreiber)

    assert "wlan=70/-53dBm" in inhalt, inhalt
    assert "bcn=12" in inhalt, inhalt

    #
    # Beim nächsten Mal steht der Zuwachs dabei - der Wert allein sagt
    # nichts, sein Anstieg alles.
    #
    funk.write_text(
        funk.read_text(encoding="utf-8").replace("     12", "     15"),
        encoding="utf-8",
    )

    proband._temperature = lambda: "46C"
    proband._sample(schreiber, 8080)

    inhalt = zeilen_von(proband, schreiber)

    assert "bcn=15(+3)" in inhalt, (
        f"Der Zuwachs der verpassten Beacons steht nicht dabei:\n{inhalt}"
    )

    #
    # Und ohne Funkschnittstelle fehlt der Teil einfach - ohne Fehler.
    #
    diagnostics_module.NET_SYS = scratch / "gibtsnicht"

    proband._temperature = lambda: "47C"
    proband._sample(schreiber, 8080)

    letzte = zeilen_von(proband, schreiber).splitlines()[-1]

    assert "wlan=" not in letzte, letzte
    assert "temp=47C" in letzte, letzte

    diagnostics_module.WIRELESS_PROC = Path("/proc/net/wireless")
    diagnostics_module.NET_SYS = Path("/sys/class/net")

    print("OK: Funkgüte, Pegel und verpasste Beacons stehen dabei")

    # ----------------------------------------------------------------
    # 11. Ein Neustart von XRack steht als Neustart da
    #
    # DER Befund aus dem Protokoll vom Gerät: Mitten in der
    # Aufzeichnung stand eine zweite Startzeile - XRack war ersetzt
    # worden, und zu sehen war das nur, wenn man genau diese Zeile
    # suchte. Sie liest niemand, der sie nicht erwartet.
    #
    # Die Systemlaufzeit daneben trennt die beiden Ursachen: War auch
    # das System gerade erst hochgefahren, war der ganze Rechner weg.
    # War nur der Prozess jung, war es der Dienst allein.
    # ----------------------------------------------------------------

    proband = Diagnostics(FakeApplication())
    proband._close_writer()
    diagnostics_module.LOG_FILE.unlink(missing_ok=True)

    #
    # Eine Datei, die mitten in der Messung abbricht - so sieht sie
    # aus, wenn der Prozess einfach weg war.
    #
    diagnostics_module.LOG_FILE.write_text(
        "2026-09-12 11:49:05 xrack=ok netz=ok route=wlan0 aktiv=leerlauf\n",
        encoding="utf-8",
    )

    proband._default_route = lambda: ("192.168.1.1", "wlan0")
    proband._temperature = lambda: "45C"
    proband._load = lambda: "0.10"
    proband._self_check = lambda port: "ok"
    proband._ping = lambda host: True
    proband._stromsparen = lambda interface: "on"
    proband._prozess_laufzeit = lambda: 3.0
    proband._system_laufzeit = lambda: 15000.0

    diagnostics_module.INTERVAL = 0.01
    proband.enabled = True

    def gleich_stoppen():
        time.sleep(0.08)
        proband._stop.set()

    threading.Thread(target=gleich_stoppen, daemon=True).start()

    proband._loop()

    inhalt = diagnostics_module.LOG_FILE.read_text(encoding="utf-8")

    assert "NEUSTART" in inhalt, (
        f"Ein Neustart von XRack steht nicht als solcher in der "
        f"Aufzeichnung:\n{inhalt}"
    )

    assert "seit 3s" in inhalt, inhalt

    assert "System seit 4h10m" in inhalt, (
        f"Die Systemlaufzeit fehlt - dann lässt sich 'nur der Dienst' "
        f"nicht von 'der ganze Rechner' unterscheiden:\n{inhalt}"
    )

    assert "nicht ordentlich beendet" in inhalt, (
        f"Dass die vorherige Aufzeichnung abbrach, steht nicht dabei:\n"
        f"{inhalt}"
    )

    assert "prozess=3s system=4h10m ps=on" in inhalt, inhalt

    print("OK: Ein Neustart wird als Neustart gemeldet, samt Systemlaufzeit")

    # ----------------------------------------------------------------
    # 12. Und im Regelfall steht kein Neustart da
    #
    # Eine Warnung, die immer erscheint, ist keine Warnung.
    # ----------------------------------------------------------------

    proband = Diagnostics(FakeApplication())
    proband._close_writer()
    diagnostics_module.LOG_FILE.unlink(missing_ok=True)

    diagnostics_module.LOG_FILE.write_text(
        "2026-09-12 10:00:00 === Aufzeichnung beendet ===\n",
        encoding="utf-8",
    )

    proband._default_route = lambda: ("192.168.1.1", "wlan0")
    proband._temperature = lambda: "45C"
    proband._load = lambda: "0.10"
    proband._self_check = lambda port: "ok"
    proband._ping = lambda host: True
    proband._stromsparen = lambda interface: "off"
    proband._prozess_laufzeit = lambda: 7200.0
    proband._system_laufzeit = lambda: 90000.0

    proband.enabled = True

    def auch_stoppen():
        time.sleep(0.08)
        proband._stop.set()

    threading.Thread(target=auch_stoppen, daemon=True).start()

    proband._loop()

    inhalt = diagnostics_module.LOG_FILE.read_text(encoding="utf-8")

    assert "NEUSTART" not in inhalt and "ABBRUCH" not in inhalt, (
        f"Im Regelfall steht eine Neustart-Warnung da - dann übersieht "
        f"man die echte:\n{inhalt}"
    )

    print("OK: Ohne Neustart steht auch keine Neustart-Warnung da")

    # ----------------------------------------------------------------
    # 13. Beim geordneten Herunterfahren wird abgeschlossen
    #
    # Das ist die Voraussetzung dafür, dass Abschnitt 11 überhaupt
    # etwas aussagt. Der Aufzeichnungs-Thread ist ein Daemon-Thread:
    # Beim Beenden stirbt er mit, ohne noch etwas zu schreiben - und
    # die Aufzeichnung schloss daraus beim nächsten Start, der Prozess
    # sei abgestürzt.
    #
    # Am Gerät sah das so aus: Nach einem völlig geordneten
    # "systemctl restart" hätte dort "nicht ordentlich beendet"
    # gestanden. Eine Warnung, die bei jedem normalen Neustart
    # erscheint, schickt die nächste Fehlersuche in die falsche
    # Richtung.
    #
    # Geprüft wird an der ECHTEN Anwendung: Der lifespan von FastAPI
    # wird durchlaufen, wie uvicorn es beim Herunterfahren tut.
    # ----------------------------------------------------------------

    import asyncio

    from web.server import create_app

    class Ausgabe:
        name = "XRack"
        version = "test"

    class Daten:
        application = Ausgabe()

    class Konfiguration:
        data = Daten()

    class RackMitDiagnose:
        """Nur so viel Application, wie create_app anfasst."""

        def __init__(self, diagnose):
            self.config = Konfiguration()
            self.diagnostics = diagnose
            self.logger = diagnostics_module.logging.getLogger("XRack-Test")

    proband = Diagnostics(FakeApplication())
    proband._close_writer()
    diagnostics_module.LOG_FILE.unlink(missing_ok=True)

    proband._default_route = lambda: ("192.168.1.1", "wlan0")
    proband._temperature = lambda: "45C"
    proband._load = lambda: "0.10"
    proband._self_check = lambda port: "ok"
    proband._ping = lambda host: True
    proband._stromsparen = lambda interface: "off"
    proband._prozess_laufzeit = lambda: 7200.0
    proband._system_laufzeit = lambda: 90000.0

    diagnostics_module.INTERVAL = 0.01

    #
    # Wie im Betrieb gestartet - mit eigenem Thread.
    #
    proband.start()

    time.sleep(0.1)

    app = create_app(RackMitDiagnose(proband))

    async def herunterfahren():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(herunterfahren())

    assert proband.enabled is False, (
        "Die Aufzeichnung läuft nach dem Herunterfahren weiter."
    )

    inhalt = diagnostics_module.LOG_FILE.read_text(encoding="utf-8")

    assert "Aufzeichnung beendet" in inhalt, (
        f"Beim geordneten Herunterfahren fehlt die Abschlusszeile - dann "
        f"hält die Diagnose beim nächsten Start jeden normalen Neustart "
        f"für einen Absturz:\n{inhalt}"
    )

    #
    # Und der Beweis, dass es zusammenpasst: Der nächste Start liest
    # diese Datei und meldet KEINEN Abbruch.
    #
    nachher = Diagnostics(FakeApplication())
    nachher._close_writer()

    assert nachher._vorherige_lief_weiter() is False, (
        "Eine ordentlich abgeschlossene Aufzeichnung gilt trotzdem als "
        "abgebrochen."
    )

    print("OK: Geordnetes Herunterfahren schliesst die Aufzeichnung ab")

    print("Alle Tests erfolgreich.")

finally:
    shutil.rmtree(scratch, ignore_errors=True)
