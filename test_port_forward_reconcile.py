"""
Prüft den Abgleich der Portweiterleitung
(Application._reconcile_port_forward()) - ohne echtes iptables, ohne
NetworkManager, ohne Hardware.

Hintergrund: iptables-Regeln überleben keinen Neustart, die gemerkte
Einstellung dagegen schon. Ein einmaliger Versuch beim Start reicht
nicht, weil die Konsole zu diesem Zeitpunkt über die gerade erst
hochgefahrene Freigabe noch keine DHCP-Lease hat - die Konsolen-IP ist
also noch unbekannt. Genau das war der gemeldete Fehler: Die Oberfläche
zeigte "an", im System existierte aber keine Regel, und erst Aus- und
Einschalten half.
"""

import sys
import types

#
# Application zieht die halbe Audio-Kette mit rein - alsaaudio gibt es
# hier nicht (nur auf dem Pi). Ein Fake-Modul genügt, es wird von
# diesem Test nie benutzt.
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

from core.application import Application


class FakeWlanControl:
    """
    Ersetzt WlanControl: liefert eine steuerbare Konsolen-IP und
    protokolliert, welche Regeln gesetzt wurden.
    """

    def __init__(self, console_ip=None):
        self.console_ip = console_ip
        self.calls = []
        self.status_calls = 0
        self.succeed = True

    def get_status(self):
        self.status_calls += 1
        return {"console_ip": self.console_ip}

    def set_port_forward(self, enabled, console_ip):
        self.calls.append((enabled, console_ip))

        if self.succeed:
            return True, "ok"

        return False, "Regel konnte nicht gesetzt werden."


def make_application(console_ip=None, enabled=True) -> Application:
    """
    Baut eine Application, ohne __init__ zu durchlaufen - das würde
    Audiogeräte suchen, Threads starten und Konfiguration schreiben.
    Für den Abgleich braucht es nur eine Handvoll Felder.
    """

    application = Application.__new__(Application)

    application.logger = __import__("logging").getLogger("XRack")
    application.wlan_control = FakeWlanControl(console_ip)
    application.port_forward_enabled = enabled
    application._port_forward_applied_ip = None

    return application


# ----------------------------------------------------------------
# 1. Der gemeldete Fehlerfall
#
# Beim Start ist die Konsolen-IP noch unbekannt. Sobald sie auftaucht,
# muss die Regel ohne weiteres Zutun gesetzt werden.
# ----------------------------------------------------------------

application = make_application(console_ip=None, enabled=True)

application._reconcile_port_forward()

assert application.wlan_control.calls == [], (
    "Ohne bekannte Konsolen-IP darf keine Regel gesetzt werden."
)
print("OK: Ohne Konsolen-IP (direkt nach dem Start) passiert nichts")

# Die Konsole bekommt ihre DHCP-Lease
application.wlan_control.console_ip = "192.168.4.10"

application._reconcile_port_forward()

assert application.wlan_control.calls == [(True, "192.168.4.10")], (
    f"Regel wurde nicht nachgeholt: {application.wlan_control.calls}"
)
print("OK: Sobald die Konsolen-IP auftaucht, wird die Regel nachgeholt")

# ----------------------------------------------------------------
# 2. Kein Dauerfeuer: gleiche IP -> kein erneuter iptables-Aufruf
# ----------------------------------------------------------------

for _ in range(5):
    application._reconcile_port_forward()

assert len(application.wlan_control.calls) == 1, (
    f"Regel wurde mehrfach gesetzt, obwohl sich nichts geändert hat: "
    f"{application.wlan_control.calls}"
)
print("OK: Bei unveränderter IP wird die Regel nicht immer wieder neu gesetzt")

# ----------------------------------------------------------------
# 3. Lease-Wechsel: neue IP -> genau einmal neu setzen
# ----------------------------------------------------------------

application.wlan_control.console_ip = "192.168.4.11"

application._reconcile_port_forward()
application._reconcile_port_forward()

assert application.wlan_control.calls == [
    (True, "192.168.4.10"),
    (True, "192.168.4.11"),
], f"Unerwartete Aufrufe: {application.wlan_control.calls}"
print("OK: Bekommt die Konsole eine andere IP, wird die Regel genau einmal erneuert")

# ----------------------------------------------------------------
# 4. Konsole verschwindet -> beim Wiederauftauchen neu setzen
# ----------------------------------------------------------------

application.wlan_control.console_ip = None
application._reconcile_port_forward()

application.wlan_control.console_ip = "192.168.4.11"
application._reconcile_port_forward()

assert application.wlan_control.calls[-1] == (True, "192.168.4.11")
assert len(application.wlan_control.calls) == 3, (
    f"Nach dem Wiederauftauchen wurde nicht neu gesetzt: "
    f"{application.wlan_control.calls}"
)
print("OK: Verschwindet die Konsole zwischenzeitlich, wird danach neu gesetzt")

# ----------------------------------------------------------------
# 5. Aus heißt aus - und kostet nichts
# ----------------------------------------------------------------

application = make_application(console_ip="192.168.4.10", enabled=False)

for _ in range(3):
    application._reconcile_port_forward()

assert application.wlan_control.calls == [], (
    "Bei ausgeschalteter Portweiterleitung darf nichts gesetzt werden."
)
assert application.wlan_control.status_calls == 0, (
    "Bei ausgeschalteter Portweiterleitung darf nicht einmal der "
    "Status abgefragt werden (das startet Subprozesse)."
)
print("OK: Ist die Weiterleitung aus, läuft kein einziger Subprozess")

# ----------------------------------------------------------------
# 6. Schlägt das Setzen fehl, wird es beim nächsten Mal erneut versucht
# ----------------------------------------------------------------

application = make_application(console_ip="192.168.4.10", enabled=True)
application.wlan_control.succeed = False

application._reconcile_port_forward()
application._reconcile_port_forward()

assert len(application.wlan_control.calls) == 2, (
    "Nach einem Fehlschlag muss erneut versucht werden, statt den "
    "Zustand fälschlich als gesetzt zu merken."
)
assert application._port_forward_applied_ip is None
print("OK: Ein Fehlschlag wird nicht als Erfolg gemerkt, sondern erneut versucht")

# ----------------------------------------------------------------
# 7. refresh_port_forward() erzwingt ein Neusetzen
# ----------------------------------------------------------------

application = make_application(console_ip="192.168.4.10", enabled=True)

application._reconcile_port_forward()
assert len(application.wlan_control.calls) == 1

application.refresh_port_forward()
assert len(application.wlan_control.calls) == 2, (
    "Der manuelle Notnagel muss die Regel auch bei gleicher IP neu setzen."
)
print("OK: refresh_port_forward() setzt die Regel auch bei gleicher IP neu")

# ----------------------------------------------------------------
# 8. Der Abgleich muss auch tatsächlich regelmäßig laufen
#
# Die Logik oben nützt nichts, wenn sie niemand aufruft - genau das war
# der ursprüngliche Fehler (ein einziger Versuch beim Start, danach
# nie wieder). Darum hier den Schleifen-Thread selbst prüfen.
# ----------------------------------------------------------------

import threading
import time

application = make_application(console_ip=None, enabled=True)
application.PORT_FORWARD_INTERVAL = 0.01

runs = {"count": 0}

def counting_reconcile():
    runs["count"] += 1

    # Beim zweiten Durchlauf taucht die Konsole auf
    if runs["count"] == 2:
        application.wlan_control.console_ip = "192.168.4.10"

    # Ein Fehler darf die Schleife nicht beenden
    if runs["count"] == 3:
        raise RuntimeError("Simulierter Fehler im Abgleich")

application._reconcile_port_forward = counting_reconcile

thread = threading.Thread(target=application._port_forward_loop, daemon=True)
thread.start()

time.sleep(0.3)

assert runs["count"] > 3, (
    f"Der Abgleich lief nur {runs['count']}x - er muss wiederholt "
    f"aufgerufen werden, sonst wird die Regel nach einem Neustart nie "
    f"nachgeholt."
)

assert thread.is_alive(), (
    "Ein Fehler im Abgleich hat den Thread beendet - danach würde die "
    "Portweiterleitung bis zum nächsten Neustart nie mehr gesetzt."
)

print(
    f"OK: Der Abgleich läuft wiederholt ({runs['count']}x) und übersteht "
    f"einen Fehler"
)

print("Alle Tests erfolgreich.")
