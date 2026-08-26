"""
Prüft "Mischpult erneut suchen" (Application.search_console).

Warum es diesen Test gibt: Die Suche trennt die Kabelverbindung kurz,
damit das angeschlossene Pult wieder per DHCP nach einer Adresse
fragt. Das ist genau dann richtig, wenn an eth0 auch wirklich das
Pult hängt - also im Bridge- oder im Freigabe-Betrieb.

Hängen Pult und Pi dagegen zusammen an einem Router, ist eth0 die
Leitung dorthin. XRack würde sich beim Suchen die eigene Verbindung
unter den Füßen wegziehen - und der Nutzer säße vor einer Oberfläche,
die nicht mehr antwortet, weil er auf "suchen" gedrückt hat.

Deshalb steht hier vor allem eine Frage: Wann wird getrennt und wann
nicht.
"""

import logging
import sys
import types

#
# Application zieht die halbe Audio-Kette mit rein - alsaaudio gibt es
# hier nicht (nur auf dem Pi).
#
fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE", "PCM_FORMAT_S24_LE", "PCM_FORMAT_S24_3LE",
    "PCM_FORMAT_S32_LE", "PCM_CAPTURE", "PCM_PLAYBACK",
    "PCM_NORMAL", "PCM_NONBLOCK",
):
    setattr(fake_alsaaudio, name, 0)

fake_alsaaudio.ALSAAudioError = Exception
fake_alsaaudio.cards = lambda: []
fake_alsaaudio.pcms = lambda *args, **kwargs: []
fake_alsaaudio.PCM = type("FakePCM", (), {"__init__": lambda self, *a, **k: None})
sys.modules["alsaaudio"] = fake_alsaaudio

from core.application import Application


class FakeWlanControl:

    def __init__(self, bridge=False, share=False):
        self.bridge = bridge
        self.share = share
        self.getrennt = 0

    def get_status(self):
        return {
            "bridge_enabled": self.bridge,
            "console_access_enabled": self.share,
            "console_ip": None,
        }

    def reconnect_console(self):
        self.getrennt += 1
        return True, ""


class FakeConsoleControl:
    """
    `gefunden` ist die Adresse, die der Rundruf liefern soll - None
    heisst: niemand antwortet.
    """

    def __init__(self, gefunden=None):
        self.gefunden = gefunden
        self.verworfen = 0
        self.rundrufe = []

    def detect_reset(self):
        self.verworfen += 1

    def discover(self, force=False):
        self.rundrufe.append(force)
        return self.gefunden


def anwendung(bridge=False, share=False, lease=None, gefunden=None):
    """
    Baut eine Application ohne __init__ - das wuerde Audiogeraete
    suchen und Threads starten.
    """

    app = Application.__new__(Application)

    app.logger = logging.getLogger("XRack")
    app.wlan_control = FakeWlanControl(bridge=bridge, share=share)
    app.console_control = FakeConsoleControl(gefunden=gefunden)

    #
    # Die uebliche Reihenfolge (von Hand, Vergabeliste, Rundruf)
    # steckt in _console_host_and_channels und wird anderswo geprueft
    # - hier zaehlt nur, ob dabei schon etwas herauskommt.
    #
    app._console_host_and_channels = lambda: (
        lease, 18, "lease" if lease else "discovered"
    )

    return app


# ----------------------------------------------------------------
# 1. Am Kabel wird getrennt
# ----------------------------------------------------------------

for bridge, share, wie in (
    (True, False, "Konsole ueber XRacks Access Point"),
    (False, True, "Konsole aus dem Heimnetz"),
):

    app = anwendung(bridge=bridge, share=share, lease="10.42.0.120")

    ergebnis = app.search_console()

    assert app.wlan_control.getrennt == 1, (
        f"{wie}: Die Verbindung wurde nicht getrennt - dann fragt das "
        f"Pult auch nicht neu nach einer Adresse."
    )
    assert ergebnis["cable_reset"] is True
    assert ergebnis["found"] is True
    assert ergebnis["host"] == "10.42.0.120"

print("OK: In beiden Kabel-Betriebsarten wird die Verbindung getrennt")

# ----------------------------------------------------------------
# 2. Ohne Kabelbetrieb wird NICHT getrennt
#
# Der wichtigste Fall: Haengen Pult und Pi an einem Router, ist eth0
# die Leitung dorthin - und XRack wuerde sich selbst abschneiden.
# ----------------------------------------------------------------

app = anwendung(bridge=False, share=False, gefunden="192.168.1.55")

ergebnis = app.search_console()

assert app.wlan_control.getrennt == 0, (
    "Ohne Kabel-Betriebsart wurde eth0 getrennt. Haengen Pult und Pi "
    "an einem Router, kappt XRack damit die eigene Verbindung."
)
assert ergebnis["cable_reset"] is False

print("OK: Ohne Kabel-Betriebsart bleibt die Verbindung unangetastet")

# ----------------------------------------------------------------
# 3. Gemerktes wird verworfen - sonst sucht man dieselbe alte Adresse
# ----------------------------------------------------------------

assert app.console_control.verworfen == 1, (
    "Die gemerkte Adresse/Pultfamilie wurde nicht verworfen."
)

print("OK: Adresse und Pultfamilie werden vor der Suche verworfen")

# ----------------------------------------------------------------
# 4. Findet die Vergabeliste nichts, wird der Rundruf erzwungen
#
# Ohne "force" gilt die uebliche Wartezeit von 30 Sekunden zwischen
# zwei Rundrufen - wer ausdruecklich auf "suchen" drueckt, wuerde
# dann eine Antwort bekommen, die vielleicht eine halbe Minute alt
# ist.
# ----------------------------------------------------------------

assert app.console_control.rundrufe == [True], (
    f"Der Rundruf wurde nicht erzwungen: {app.console_control.rundrufe}"
)

print("OK: Der Rundruf wird erzwungen, wenn sonst nichts gefunden wird")

# ----------------------------------------------------------------
# 5. Steht die Adresse schon in der Vergabeliste, kein Rundruf
#
# Ein Rundruf kostet eine knappe Sekunde - unnoetig, wenn die
# Adresse ohnehin bekannt ist.
# ----------------------------------------------------------------

app = anwendung(bridge=True, lease="10.42.0.120")

app.search_console()

assert app.console_control.rundrufe == [], (
    "Es wurde gesucht, obwohl die Adresse schon bekannt war."
)

print("OK: Bei bekannter Adresse wird nicht zusaetzlich gesucht")

# ----------------------------------------------------------------
# 6. Nichts gefunden: sauber melden statt so zu tun als ob
# ----------------------------------------------------------------

app = anwendung(bridge=True, lease=None, gefunden=None)

ergebnis = app.search_console()

assert ergebnis["found"] is False, ergebnis
assert ergebnis["host"] is None, ergebnis
assert ergebnis["source"] is None, ergebnis

print("OK: Wird nichts gefunden, sagt die Antwort das auch")

print("Alle Tests erfolgreich.")
