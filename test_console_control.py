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
    MAIN_ADDRESS,
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
# Wichtig: Ausrichtung allein reicht als Prüfung NICHT. Vier überzählige
# Nullen halten die Nachricht ebenfalls ausgerichtet, schieben aber das
# Typ-Tag um vier Byte nach hinten - der Empfänger liest dann eine
# Nachricht ohne Argumente. Genau das passierte bei jeder Adresse, deren
# Länge beim Teilen durch 4 den Rest 3 lässt (19, 23, 27 Zeichen ...).
# Darum hier jede Restklasse durchgehen und das Argument auch wirklich
# zurücklesen.
#
for length in range(1, 40):

    address = "/" + "a" * (length - 1)

    message = encode(address, 0.5)

    assert len(message) % 4 == 0, (
        f"Auffüllung falsch bei {length} Zeichen"
    )

    back_address, back_arguments = decode(message)

    assert back_address == address, (
        f"Adresse mit {length} Zeichen kam falsch zurück: {back_address!r}"
    )
    assert len(back_arguments) == 1, (
        f"Argument ging verloren bei einer Adresse mit {length} Zeichen "
        f"(Rest {length % 4} beim Teilen durch 4) - das Typ-Tag steht "
        f"an der falschen Stelle."
    )

#
# Byteweise: Adresse plus Nullabschluss, die schon ins Raster passt,
# darf keine weiteren Nullen bekommen.
#
assert encode("/abc").startswith(b"/abc\x00\x00\x00\x00"), (
    "Adresse mit 4 Zeichen wird falsch aufgefüllt."
)
assert len(encode("/ab" + "c" * 16)) == 24, (
    "Eine 19 Zeichen lange Adresse darf nur auf 20 Byte aufgefüllt werden."
)

print("OK: Auffüllung stimmt bei Adressen jeder Länge (auch Rest 3)")

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

#
# 16 Mono + Aux-Paar + Summe
#
assert len(xair) == 18, (
    f"XR18 sollte 18 Regler ergeben (16 + Aux + Summe), ergibt aber {len(xair)}"
)
assert xair[15].address == "/ch/16"
assert xair[16] == ("/rtn/aux", "17+18", False), (
    f"Der Aux-Rückweg fehlt oder heißt anders: {xair[16]}"
)

x32 = channel_addresses(FAMILY_X32, 32)
assert len(x32) == 33, f"X32 sollte 32 + Summe ergeben, ergibt {len(x32)}"
assert x32[0] == ("/ch/01", "1", False)
assert x32[31] == ("/ch/32", "32", False)

print("OK: Kanaladressen stimmen je Familie (X-Air 16+Aux, X32 durchgehend)")

# ----------------------------------------------------------------
# 4b. Die Summe hat je Familie eine eigene Adresse
# ----------------------------------------------------------------

assert xair[-1].is_main is True, "Letzter Regler muss die Summe sein."
assert xair[-1].address == MAIN_ADDRESS[FAMILY_XAIR] == "/lr", xair[-1]
assert xair[-1].label == "Main"

assert x32[-1].is_main is True
assert x32[-1].address == MAIN_ADDRESS[FAMILY_X32] == "/main/st", x32[-1]

#
# Genau ein Summenregler, nicht mehrere
#
assert sum(1 for spec in xair if spec.is_main) == 1
assert sum(1 for spec in x32 if spec.is_main) == 1

print("OK: Summenregler hat je Familie die richtige Adresse (X-Air /lr, X32 /main/st)")

# ----------------------------------------------------------------
# 4c. Mute wird als Integer kodiert - mit umgekehrter Logik
# ----------------------------------------------------------------

message = encode("/ch/01/mix/on", 0)

assert len(message) % 4 == 0
assert b",i\x00\x00" in message, "Typ-Tag ',i' fehlt - Mute braucht einen Integer."
assert message[-4:] == struct.pack(">i", 0), "Integer muss Big-Endian sein."

address, arguments = decode(encode("/ch/05/mix/on", 1))
assert address == "/ch/05/mix/on"
assert arguments == [1]

#
# bool darf nicht versehentlich als Float durchrutschen
#
assert decode(encode("/x", True))[1] == [1]
assert decode(encode("/x", False))[1] == [0]

print("OK: Mute wird als Big-Endian-Integer kodiert (0 = stumm, 1 = an)")

# ----------------------------------------------------------------
# 4d. Gekoppelte Kanalpaare werden zu einem Regler
# ----------------------------------------------------------------

paired = channel_addresses(FAMILY_XAIR, 18, linked={1, 5})

#
# 16 Mono-Kanäle, davon zwei Paare gekoppelt -> 14 Regler,
# dazu Aux-Rückweg und Summe.
#
assert len(paired) == 16, (
    f"Zwei Kopplungen sollten 16 Regler ergeben, ergeben aber {len(paired)}"
)

assert paired[0] == ("/ch/01", "1+2", False), paired[0]
assert paired[1] == ("/ch/03", "3", False), paired[1]
assert paired[2] == ("/ch/04", "4", False), paired[2]
assert paired[3] == ("/ch/05", "5+6", False), paired[3]
assert paired[4] == ("/ch/07", "7", False), paired[4]

#
# Kanal 2 und 6 dürfen nicht mehr einzeln auftauchen - sie hängen am
# Regler ihres Partners.
#
addresses = [spec.address for spec in paired]
assert "/ch/02" not in addresses
assert "/ch/06" not in addresses

#
# Aux-Rückweg und Summe bleiben, wo sie sind.
#
assert paired[-2] == ("/rtn/aux", "17+18", False)
assert paired[-1].is_main is True

print("OK: Gekoppelte Paare ergeben einen Regler (1+2), der Rest bleibt einzeln")

#
# Ohne Kopplung ändert sich nichts - das ist der Normalfall.
#
assert channel_addresses(FAMILY_XAIR, 18) == channel_addresses(
    FAMILY_XAIR, 18, linked=set()
)

#
# Auch beim X32, und eine Kopplung am oberen Ende darf nicht über den
# letzten Kanal hinauslaufen.
#
x32_paired = channel_addresses(FAMILY_X32, 32, linked={31})
assert len(x32_paired) == 32, f"31+32 gekoppelt -> 31 Regler + Summe, nicht {len(x32_paired)}"
assert x32_paired[-2] == ("/ch/31", "31+32", False), x32_paired[-2]

print("OK: Kopplung funktioniert auch beim X32 und läuft nicht über den letzten Kanal hinaus")

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
        self.on: dict[str, int] = {}
        self.received: list[tuple[str, list]] = []

        #
        # Gekoppelte Paare, Schluessel wie "1-2". Was hier nicht steht,
        # beantwortet die Attrappe je nach answer_chlink entweder mit 0
        # oder gar nicht - so laesst sich auch ein Pult nachstellen, das
        # die Abfrage ueberhaupt nicht kennt.
        #
        self.chlink: dict[str, int] = {}
        self.answer_chlink = True
        self.fdrmute: int | None = None

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
                elif address.endswith("/mix/on"):
                    self.on[address] = arguments[0]
                continue

            #
            # Abfragen
            #
            if address == "/info":
                reply = encode("/info", "V2.07", "XR18", "1.17")

            elif address.endswith("/mix/fader"):
                reply = encode(address, self.faders.get(address, 0.75))

            elif address.endswith("/mix/on"):
                reply = encode(address, self.on.get(address, 1))

            elif address.endswith("/config/name"):
                reply = encode(address, self.names.get(address, ""))

            elif address.startswith("/config/chlink/"):

                if not self.answer_chlink:
                    continue

                pair = address[len("/config/chlink/"):]
                reply = encode(address, self.chlink.get(pair, 0))

            elif address == "/config/linkcfg/fdrmute":

                if self.fdrmute is None:
                    continue

                reply = encode(address, self.fdrmute)

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
    assert len(channels) == 18, (
        f"Erwartet 18 Regler (16 + Aux + Summe), bekommen {len(channels)}"
    )

    assert channels[0]["name"] == "Click"
    assert abs(channels[0]["db"] - 0.0) < 0.01, channels[0]
    assert channels[1]["name"] == "Gitarre"
    assert abs(channels[1]["db"] - (-10.0)) < 0.01, channels[1]
    assert channels[16]["label"] == "17+18"
    assert channels[17]["label"] == "Main"
    assert channels[17]["is_main"] is True

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
    assert control.set_fader("127.0.0.1", 18, 19, 0.0) is False

    print("OK: Ungültige Kanalnummern werden abgelehnt")

    # ----------------------------------------------------------------
    # 5b. Summenregler landet auf seiner eigenen Adresse
    # ----------------------------------------------------------------

    assert control.set_fader("127.0.0.1", 18, 18, 0.0) is True

    time.sleep(0.1)

    assert "/lr/mix/fader" in console.faders, (
        f"Die Summe wurde nicht angesprochen: {sorted(console.faders)}"
    )
    assert abs(console.faders["/lr/mix/fader"] - 0.75) < 1e-6

    print("OK: Der Summenregler landet beim X-Air auf /lr")

    # ----------------------------------------------------------------
    # 5c. Stummschaltung - mit umgekehrter Logik
    # ----------------------------------------------------------------

    assert control.set_mute("127.0.0.1", 18, 3, True) is True

    time.sleep(0.1)

    assert console.on["/ch/03/mix/on"] == 0, (
        f"Stumm muss 0 senden, gesendet wurde "
        f"{console.on.get('/ch/03/mix/on')}"
    )

    assert control.set_mute("127.0.0.1", 18, 3, False) is True

    time.sleep(0.1)

    assert console.on["/ch/03/mix/on"] == 1, "Wieder an muss 1 senden."

    print("OK: Stummschaltung sendet 0, Aufheben sendet 1 (umgekehrte Logik)")

    #
    # ... und wird auch richtig zurückgelesen
    #
    console.on["/ch/04/mix/on"] = 0

    channels = control.get_channels("127.0.0.1", 18)

    assert channels[3]["muted"] is True, (
        f"Stummer Kanal wurde nicht erkannt: {channels[3]}"
    )
    assert channels[2]["muted"] is False

    print("OK: Stummschaltung wird korrekt zurückgelesen")

    #
    # Auch die Summe lässt sich stummschalten
    #
    assert control.set_mute("127.0.0.1", 18, 18, True) is True

    time.sleep(0.1)

    assert console.on["/lr/mix/on"] == 0

    print("OK: Auch die Summe lässt sich stummschalten")

    assert control.set_mute("127.0.0.1", 18, 19, True) is False

    # ----------------------------------------------------------------
    # 5d. Gekoppelte Paare am Pult abfragen
    # ----------------------------------------------------------------

    console.chlink["1-2"] = 1
    console.chlink["5-6"] = 1

    channels = control.get_channels("127.0.0.1", 18)

    assert len(channels) == 16, (
        f"Zwei gekoppelte Paare sollten 16 Regler ergeben, es sind {len(channels)}"
    )
    assert channels[0]["label"] == "1+2", channels[0]
    assert channels[3]["label"] == "5+6", channels[3]

    #
    # Der Name kommt vom ersten Kanal des Paars.
    #
    assert channels[0]["name"] == "Click"

    print("OK: Gekoppelte Paare werden am Pult erkannt und zusammengefasst")

    #
    # Entscheidend: Ein Befehl auf den zusammengefassten Regler muss
    # denselben Kanal treffen, den die Oberfläche anzeigt. Regler 4 ist
    # jetzt "5+6" - der Befehl gehört auf /ch/05, nicht auf /ch/04.
    #
    console.faders.pop("/ch/05/mix/fader", None)

    assert control.set_fader("127.0.0.1", 18, 4, 0.0) is True

    time.sleep(0.1)

    assert "/ch/05/mix/fader" in console.faders, (
        f"Regler 5+6 hat den falschen Kanal getroffen: {sorted(console.faders)}"
    )

    print("OK: Der zusammengefasste Regler trifft den ersten Kanal des Paars")

    #
    # Sind Fader und Mute laut Pult NICHT an die Kopplung gebunden
    # (das gibt es beim X32), darf nicht zusammengefasst werden - sonst
    # bewegt sich sichtbar nur die Hälfte.
    #
    console.fdrmute = 0
    control._fader_link = None

    channels = control.get_channels("127.0.0.1", 18)

    assert len(channels) == 18, (
        f"Bei entkoppelten Fadern müssen alle 18 Regler einzeln bleiben, "
        f"es sind {len(channels)}"
    )

    print("OK: Folgen die Fader der Kopplung nicht, bleibt jeder Kanal einzeln")

    #
    # Ein Pult, das die Abfrage gar nicht kennt: Es darf nicht bei jedem
    # Auffrischen acht Zeitüberschreitungen kosten - nach dem ersten
    # Fehlversuch wird nicht mehr gefragt.
    #
    console.fdrmute = None
    console.answer_chlink = False

    control._fader_link = None
    control._link_supported = True

    console.received.clear()

    started = time.monotonic()
    channels = control.get_channels("127.0.0.1", 18)
    elapsed = time.monotonic() - started

    probes = [a for a, _ in console.received if a.startswith("/config/chlink/")]

    assert len(channels) == 18
    assert len(probes) == 1, (
        f"Nach dem ersten erfolglosen Versuch darf nicht weitergefragt "
        f"werden, gefragt wurde aber {len(probes)}x"
    )

    #
    # Zweiter Durchgang: jetzt gar keine Abfrage mehr.
    #
    console.received.clear()
    control.get_channels("127.0.0.1", 18)

    assert not [a for a, _ in console.received if a.startswith("/config/chlink/")], (
        "Das Pult wird weiter nach Kopplungen gefragt, obwohl es sie nicht kennt."
    )

    print(
        f"OK: Kennt das Pult die Kopplungs-Abfrage nicht, wird nur einmal "
        f"gefragt ({elapsed:.2f}s)"
    )

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
    assert fresh.set_mute("127.0.0.1", 18, 1, True) is False

    print("OK: Ohne Pult liefert get_channels None (nicht erreichbar), set_fader False")

finally:
    console.stop()

print("Alle Tests erfolgreich.")
