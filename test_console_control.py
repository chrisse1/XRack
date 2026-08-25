"""
Prüft core/console_control.py - OSC-Kodierung, die Fader-Kennlinie der
X-Serie und den kompletten Austausch mit dem Pult.

Für den Austausch läuft ein "Attrappen-Pult": ein UDP-Socket auf
localhost, der wie eine Konsole antwortet. Damit lassen sich
Familienerkennung, Auslesen und Setzen vollständig ohne Hardware
durchspielen - nur die Frage, ob die Kennlinie und die Kanaladressen
zur echten X-Serie passen, bleibt dem Test am Pult vorbehalten.
"""

import socket
import struct
import threading
import time

from core.console_control import (
    FAMILY_X32,
    FAMILY_XAIR,
    MIN_DB,
    ConsoleControl,
    channel_addresses,
    db_to_fader,
    decode,
    encode,
    fader_to_db,
)

# ----------------------------------------------------------------
# 1. OSC-Kodierung gegen die Spezifikation
# ----------------------------------------------------------------

message = encode("/ch/01/mix/fader", 0.75)

assert len(message) % 4 == 0, (
    f"OSC-Nachrichten müssen auf 4 Byte ausgerichtet sein, sind aber "
    f"{len(message)} Byte lang."
)

assert message.startswith(b"/ch/01/mix/fader\x00"), (
    "Adresse muss nullterminiert am Anfang stehen."
)

assert b",f\x00\x00" in message, "Typ-Tag ',f' fehlt oder ist falsch aufgefüllt."

#
# Float muss Big-Endian sein - Little-Endian würde am Pult in einem
# völlig anderen Faderwert landen.
#
assert message[-4:] == struct.pack(">f", 0.75), (
    f"Float ist nicht Big-Endian kodiert: {message[-4:]!r}"
)

print("OK: OSC-Nachricht entspricht der Spezifikation (Ausrichtung, Typ-Tag, Big-Endian)")

#
# Adressen unterschiedlicher Länge - die Auffüllung muss immer stimmen.
#
for address in ("/x", "/ab", "/abc", "/abcd", "/abcde", "/rtn/aux/mix/fader"):
    assert len(encode(address, 0.5)) % 4 == 0, f"Auffüllung falsch bei {address}"

print("OK: Auffüllung stimmt bei Adressen jeder Länge")

# ----------------------------------------------------------------
# 2. Rundlauf durch den eigenen Dekodierer
# ----------------------------------------------------------------

address, arguments = decode(encode("/ch/05/mix/fader", 0.25))
assert address == "/ch/05/mix/fader"
assert abs(arguments[0] - 0.25) < 1e-6

address, arguments = decode(encode("/ch/05/config/name", "Gitarre"))
assert address == "/ch/05/config/name"
assert arguments == ["Gitarre"]

#
# Anfrage ohne Argumente (so wird der aktuelle Wert erfragt)
#
address, arguments = decode(encode("/ch/05/mix/fader"))
assert address == "/ch/05/mix/fader"
assert arguments == []

print("OK: Kodieren und Dekodieren passen zusammen (Float, String, ohne Argumente)")

# ----------------------------------------------------------------
# 3. Fader-Kennlinie
#
# Die X-Serie ist stückweise linear, nicht gleichmäßig - 0 dB liegt bei
# etwa 75 % Reglerweg. Diese Ankerpunkte sind der Kern der Umrechnung.
# ----------------------------------------------------------------

anchors = [
    (1.0, 10.0),
    (0.75, 0.0),
    (0.5, -10.0),
    (0.25, -30.0),
    (0.0625, -60.0),
]

for value, expected_db in anchors:
    actual = fader_to_db(value)
    assert abs(actual - expected_db) < 0.01, (
        f"f={value} sollte {expected_db} dB ergeben, ergibt aber {actual}"
    )

assert fader_to_db(0.0) == float("-inf"), "Fader ganz zu muss -unendlich sein."

print("OK: Kennlinie trifft alle Ankerpunkte (0 dB bei 75 % Reglerweg)")

for value, expected_db in anchors:
    actual = db_to_fader(expected_db)
    assert abs(actual - value) < 1e-6, (
        f"{expected_db} dB sollte f={value} ergeben, ergibt aber {actual}"
    )

assert db_to_fader(float("-inf")) == 0.0
assert db_to_fader(MIN_DB) == 0.0

print("OK: Umkehrung trifft dieselben Ankerpunkte")

#
# Rundlauf über den ganzen Bereich
#
worst = 0.0

for step in range(1, 1001):

    value = step / 1000.0
    back = db_to_fader(fader_to_db(value))
    worst = max(worst, abs(back - value))

assert worst < 1e-6, f"Rundlauf weicht um bis zu {worst} ab."

print(f"OK: Rundlauf über den ganzen Reglerweg (Abweichung < {worst:.1e})")

#
# Werte jenseits der Grenzen dürfen nicht ausbrechen
#
assert db_to_fader(999.0) == 1.0
assert db_to_fader(-999.0) == 0.0
assert fader_to_db(2.0) == 10.0

print("OK: Werte außerhalb des Bereichs werden begrenzt")

# ----------------------------------------------------------------
# 4. Kanaladressen je Konsolenfamilie
#
# Der heikelste Punkt: Beim X-Air sind 18 USB-Kanäle NICHT /ch/01..18,
# sondern 16 Mono-Kanäle plus ein Aux-Rückweg-Paar.
# ----------------------------------------------------------------

xair = channel_addresses(FAMILY_XAIR, 18)

assert len(xair) == 17, (
    f"XR18 sollte 17 Regler ergeben (16 + Aux-Paar), ergibt aber {len(xair)}"
)
assert xair[15] == ("/ch/16", "16")
assert xair[16] == ("/rtn/aux", "17+18"), (
    f"Der Aux-Rückweg fehlt oder heißt anders: {xair[16]}"
)

x32 = channel_addresses(FAMILY_X32, 32)
assert len(x32) == 32
assert x32[0] == ("/ch/01", "1")
assert x32[31] == ("/ch/32", "32")

print("OK: Kanaladressen stimmen je Familie (X-Air 16+Aux, X32 durchgehend)")

# ----------------------------------------------------------------
# 5. Attrappen-Pult: kompletter Austausch ohne Hardware
# ----------------------------------------------------------------


class FakeConsole:
    """
    Antwortet wie ein Mischpult der X-Serie: auf Anfragen ohne
    Argumente mit dem gemerkten Wert, auf Anfragen mit Argument durch
    Übernehmen des Werts.
    """

    def __init__(self):

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("127.0.0.1", 0))
        self.port = self.socket.getsockname()[1]

        self.faders: dict[str, float] = {}
        self.names: dict[str, str] = {}
        self.received: list[tuple[str, list]] = []

        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):

        self.socket.settimeout(0.1)

        while self._running:

            try:
                data, sender = self.socket.recvfrom(4096)
            except (socket.timeout, OSError):
                continue

            address, arguments = decode(data)
            self.received.append((address, arguments))

            if arguments:
                #
                # Setzen
                #
                if address.endswith("/mix/fader"):
                    self.faders[address] = arguments[0]
                continue

            #
            # Abfragen
            #
            if address == "/info":
                reply = encode("/info", "V2.07", "XR18", "1.17")

            elif address.endswith("/mix/fader"):
                reply = encode(address, self.faders.get(address, 0.75))

            elif address.endswith("/config/name"):
                reply = encode(address, self.names.get(address, ""))

            else:
                continue

            self.socket.sendto(reply, sender)

    def stop(self):
        self._running = False
        self._thread.join(timeout=1.0)
        self.socket.close()


console = FakeConsole()

try:

    control = ConsoleControl()

    #
    # Die Attrappe lauscht auf einem zufälligen Port - die Erkennung
    # umgehen und den Port direkt setzen, damit der restliche Ablauf
    # echt bleibt.
    #
    control._family = FAMILY_XAIR
    control._port = console.port
    control._detected_for = "127.0.0.1"

    console.names["/ch/01/config/name"] = "Click"
    console.names["/ch/02/config/name"] = "Gitarre"
    console.faders["/ch/01/mix/fader"] = 0.75
    console.faders["/ch/02/mix/fader"] = 0.5

    channels = control.get_channels("127.0.0.1", 18)

    assert channels is not None, "Attrappen-Pult hat nicht geantwortet."
    assert len(channels) == 17, f"Erwartet 17 Regler, bekommen {len(channels)}"

    assert channels[0]["name"] == "Click"
    assert abs(channels[0]["db"] - 0.0) < 0.01, channels[0]
    assert channels[1]["name"] == "Gitarre"
    assert abs(channels[1]["db"] - (-10.0)) < 0.01, channels[1]
    assert channels[16]["label"] == "17+18"

    print("OK: Kanalnamen und Faderwerte werden vom Pult gelesen")

    #
    # Unbenannter Kanal liefert einen leeren Namen, keinen Fehler
    #
    assert channels[5]["name"] == ""

    print("OK: Unbenannte Kanäle liefern einen leeren Namen statt eines Fehlers")

    #
    # Setzen
    #
    assert control.set_fader("127.0.0.1", 18, 2, -10.0) is True

    time.sleep(0.1)

    assert abs(console.faders["/ch/02/mix/fader"] - 0.5) < 1e-6, (
        f"Pult hat den Wert nicht übernommen: {console.faders.get('/ch/02/mix/fader')}"
    )

    print("OK: Faderwert kommt beim Pult an (-10 dB -> 0.5)")

    #
    # Der Aux-Rückweg muss auf seiner eigenen Adresse landen, nicht
    # auf /ch/17 - genau der Fall, der beim X-Air leicht schiefgeht.
    #
    assert control.set_fader("127.0.0.1", 18, 17, 0.0) is True

    time.sleep(0.1)

    assert "/rtn/aux/mix/fader" in console.faders, (
        f"Aux-Rückweg wurde nicht angesprochen: {sorted(console.faders)}"
    )
    assert "/ch/17/mix/fader" not in console.faders

    print("OK: Kanal 17+18 landet beim X-Air auf dem Aux-Rückweg, nicht auf /ch/17")

    #
    # Ungültige Kanalnummern werden abgelehnt
    #
    assert control.set_fader("127.0.0.1", 18, 0, 0.0) is False
    assert control.set_fader("127.0.0.1", 18, 18, 0.0) is False

    print("OK: Ungültige Kanalnummern werden abgelehnt")

    # ----------------------------------------------------------------
    # 6. Familienerkennung
    # ----------------------------------------------------------------

    fresh = ConsoleControl()

    #
    # Kein Pult an dieser Adresse: darf nicht hängen und muss None
    # liefern. Ein hoher, ungenutzter Port steht für "niemand da".
    #
    started = time.monotonic()
    assert fresh.detect("127.0.0.1") is None, (
        "Ohne Pult darf keine Familie erkannt werden."
    )
    elapsed = time.monotonic() - started

    assert elapsed < 2.0, (
        f"Erkennung ohne Pult dauerte {elapsed:.1f}s - der Timeout greift nicht."
    )

    print(f"OK: Ohne Pult wird nichts erkannt, und es hängt nicht ({elapsed:.2f}s)")

    #
    # Ohne erkanntes Pult liefert get_channels None statt einer leeren
    # Liste - die Oberfläche unterscheidet daran "nicht erreichbar" von
    # "keine Kanäle".
    #
    assert fresh.get_channels("127.0.0.1", 18) is None
    assert fresh.set_fader("127.0.0.1", 18, 1, 0.0) is False

    print("OK: Ohne Pult liefert get_channels None (nicht erreichbar), set_fader False")

finally:
    console.stop()

print("Alle Tests erfolgreich.")
