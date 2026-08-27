"""
Prüft core/console_control.py - OSC-Kodierung, die Fader-Kennlinie der
X-Serie und den kompletten Austausch mit dem Pult.

Für den Austausch läuft ein "Attrappen-Pult": ein UDP-Socket auf
localhost, der wie eine Konsole antwortet. Damit lassen sich
Familienerkennung, Auslesen und Setzen vollständig ohne Hardware
durchspielen - nur die Frage, ob die Kennlinie und die Kanaladressen
zur echten X-Serie passen, bleibt dem Test am Pult vorbehalten.
"""

import logging
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
    broadcast_addresses,
    channel_addresses,
    is_natural_pair,
    pair_addresses,
    db_to_fader,
    decode,
    encode,
    fader_to_db,
    SNAPSHOT_NAME_PROBES,
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

        #
        # Snapshots: Nummer -> Name. Was hier nicht steht, beantwortet
        # die Attrappe mit leerem Namen - so wie ein Pult einen
        # unbenutzten Platz meldet.
        #
        self.snapshots: dict[int, str] = {}
        self.snapshot_index = 0

        #
        # Manche Pulte kennen die Namensadresse womoeglich gar nicht.
        # Damit laesst sich genau das nachstellen.
        #
        self.answer_snapshot_names = True

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
                elif address.startswith("/config/chlink/"):
                    self.chlink[address[len("/config/chlink/"):]] = arguments[0]
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

            elif address == "/-snap/index":
                reply = encode(address, self.snapshot_index)

            elif address.startswith("/-snap/") and address.endswith("/name"):

                if not self.answer_snapshot_names:
                    continue

                nummer = int(address[len("/-snap/"):-len("/name")])
                reply = encode(address, self.snapshots.get(nummer, ""))

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


class FakeStoreKanaele:
    """Zustandsspeicher ohne Eintraege - die Pult-IP kommt aus der Vergabeliste."""

    def get(self, key, default=None):
        return default

    def set(self, key, value):
        pass


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
    # 5e. Stereopaar direkt regeln (Musikspieler-/Bluetooth-Karte)
    # ----------------------------------------------------------------

    #
    # Ausgangslage zuruecksetzen: Die Kopplungstests davor haben den
    # gemerkten Zustand veraendert.
    #
    console.chlink.clear()
    console.answer_chlink = True
    console.fdrmute = None

    control.detect_reset()
    control._family = FAMILY_XAIR
    control._port = console.port
    control._detected_for = "127.0.0.1"

    #
    # Reine Adressrechnung: ungekoppelt zwei Adressen, gekoppelt eine,
    # und beim natuerlichen Stereopaar ohnehin nur eine.
    #
    assert pair_addresses(FAMILY_XAIR, 18, 9) == ["/ch/09", "/ch/10"]
    assert pair_addresses(FAMILY_XAIR, 18, 9, linked={9}) == ["/ch/09"]
    assert pair_addresses(FAMILY_XAIR, 18, 17) == ["/rtn/aux"]
    assert pair_addresses(FAMILY_X32, 32, 31) == ["/ch/31", "/ch/32"]

    #
    # Ausserhalb der Kanaele: leere Liste statt einer geratenen Adresse.
    #
    assert pair_addresses(FAMILY_XAIR, 18, 19) == []

    assert is_natural_pair(FAMILY_XAIR, 18, 17) is True
    assert is_natural_pair(FAMILY_XAIR, 18, 9) is False
    assert is_natural_pair(FAMILY_X32, 32, 17) is False

    print("OK: Ein Stereopaar wird je nach Kopplung ueber eine oder zwei Adressen geregelt")

    #
    # Ungekoppelt muss der Wert an BEIDE Kanaele gehen - sonst bewegte
    # sich nur die halbe Musik.
    #
    console.faders.pop("/ch/09/mix/fader", None)
    console.faders.pop("/ch/10/mix/fader", None)

    assert control.set_pair_fader("127.0.0.1", 18, 9, -10.0) is True

    time.sleep(0.1)

    assert abs(console.faders["/ch/09/mix/fader"] - 0.5) < 1e-6, console.faders
    assert abs(console.faders["/ch/10/mix/fader"] - 0.5) < 1e-6, console.faders

    print("OK: Ungekoppelt geht der Pegel an beide Kanaele des Paars")

    assert control.set_pair_mute("127.0.0.1", 18, 9, True) is True

    time.sleep(0.1)

    assert console.on["/ch/09/mix/on"] == 0
    assert console.on["/ch/10/mix/on"] == 0

    print("OK: Auch die Stummschaltung erfasst beide Kanaele")

    #
    # Auslesen: vom ersten Kanal des Paars.
    #
    zustand = control.get_pair("127.0.0.1", 18, 9)

    assert zustand is not None
    assert abs(zustand["db"] - (-10.0)) < 0.01, zustand
    assert zustand["muted"] is True, zustand
    assert zustand["linked"] is False, zustand
    assert zustand["natural"] is False, zustand

    print("OK: Pegel und Stummschaltung des Paars werden zurueckgelesen")

    #
    # Koppeln - und danach darf nur noch eine Adresse bedient werden.
    # Zweimal zu senden wuerde einen absichtlichen Versatz einebnen.
    #
    assert control.set_link("127.0.0.1", 18, 9, True) is True

    time.sleep(0.1)

    assert console.chlink.get("9-10") == 1, console.chlink

    console.faders.pop("/ch/10/mix/fader", None)

    assert control.set_pair_fader("127.0.0.1", 18, 9, 0.0) is True

    time.sleep(0.1)

    assert abs(console.faders["/ch/09/mix/fader"] - 0.75) < 1e-6
    assert "/ch/10/mix/fader" not in console.faders, (
        "Trotz Kopplung wurde der zweite Kanal noch einzeln angesprochen."
    )

    assert control.get_pair("127.0.0.1", 18, 9)["linked"] is True

    print("OK: Nach dem Koppeln wird nur noch der erste Kanal angesprochen")

    #
    # Entkoppeln geht genauso wieder zurueck.
    #
    assert control.set_link("127.0.0.1", 18, 9, False) is True

    time.sleep(0.1)

    assert console.chlink.get("9-10") == 0

    console.faders.pop("/ch/10/mix/fader", None)

    assert control.set_pair_fader("127.0.0.1", 18, 9, 0.0) is True

    time.sleep(0.1)

    assert "/ch/10/mix/fader" in console.faders, (
        "Nach dem Entkoppeln muss wieder an beide Kanaele gesendet werden."
    )

    print("OK: Nach dem Entkoppeln gehen die Werte wieder an beide Kanaele")

    #
    # Das natuerliche Stereopaar: eine Adresse, und nichts zu koppeln.
    # Genau der Fall, den der XR18 mit 17+18 mitbringt.
    #
    zustand = control.get_pair("127.0.0.1", 18, 17)

    assert zustand["natural"] is True, zustand
    assert zustand["linked"] is True, zustand

    console.received.clear()

    assert control.set_link("127.0.0.1", 18, 17, True) is False, (
        "Beim Aux-Rueckweg gibt es nichts zu koppeln."
    )

    assert not [a for a, _ in console.received if a.startswith("/config/chlink")], (
        "Trotzdem wurde eine Kopplung ans Pult geschickt."
    )

    print("OK: Beim natuerlichen Stereopaar wird gar nicht erst gekoppelt")

    #
    # Feinheit, die beim Zusammenlegen der Lesewege leicht verlorengeht:
    # Antwortet der Fader nicht, liefert get_pair None - die Karte
    # blendet sich dann aus. Die ganze Kanalliste dagegen gibt bei
    # einem stummen Kanal nicht auf, sondern zeigt ihn als "zu".
    # "Kein Wert" und "-unendlich" sind zwei verschiedene Dinge.
    #
    class StummerFader:
        """Antwortet auf alles - nur nicht auf Faderabfragen."""

        def __init__(self, echt):
            self.echt = echt

        def __enter__(self):
            self.vorher = self.echt._request

            def gefiltert(host, port, message):
                if decode(message)[0].endswith("/mix/fader"):
                    return None
                return self.vorher(host, port, message)

            self.echt._request = gefiltert
            return self

        def __exit__(self, *_):
            self.echt._request = self.vorher

    with StummerFader(control):

        assert control.get_pair("127.0.0.1", 18, 9) is None, (
            "Ohne Faderantwort muss get_pair None liefern."
        )

        kanaele = control.get_channels("127.0.0.1", 18)

        assert kanaele is not None, (
            "Die Kanalliste darf wegen eines stummen Faders nicht aufgeben."
        )
        #
        # MIN_DB, nicht None: Die Kanalliste setzt einen unbeantworteten
        # Fader auf den untersten Wert. Die Oberflaeche zeigt den
        # ohnehin als "-unendlich" an.
        #
        assert kanaele[0]["db"] == MIN_DB, (
            f"Ohne Antwort gehoert der Kanal ganz nach unten: {kanaele[0]}"
        )

    print("OK: Ohne Faderantwort liefert das Paar None, die Kanalliste -unendlich")

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

    # ----------------------------------------------------------------
    # 7. Suchlauf per Rundruf
    #
    # Der Fall, fuer den es ihn gibt: Pult und Pi haengen zusammen an
    # einem Router. Dann vergibt der Router die Adressen, der Pi hat
    # keine Vergabeliste - ohne Suchlauf bliebe die Konsole unsichtbar.
    # ----------------------------------------------------------------

    #
    # Rundruf-Adressen: mindestens eine, und niemals die von loopback -
    # dorthin zu senden faende nie ein Pult.
    #
    adressen = broadcast_addresses()

    assert adressen, "Es wurde keine einzige Rundruf-Adresse ermittelt."
    assert all(not a.startswith("127.") for a in adressen), adressen

    print(f"OK: Rundruf-Adressen werden ermittelt ({', '.join(adressen)})")

    #
    # Der eigentliche Suchlauf gegen die Attrappe. Die lauscht auf
    # localhost und auf einem zufaelligen Port, ein echter Rundruf
    # erreicht sie also nicht - deshalb wird fuer den Test die
    # Adressliste auf genau ihren Sockel gelenkt.
    #
    import core.console_control as ccmodul

    sucher = ConsoleControl()

    original_broadcast = ccmodul.broadcast_addresses
    original_xair = ccmodul.PORT_XAIR
    original_x32 = ccmodul.PORT_X32

    ccmodul.broadcast_addresses = lambda: ["127.0.0.1"]
    ccmodul.PORT_XAIR = console.port
    ccmodul.PORT_X32 = console.port

    try:

        gefunden = sucher.discover()

        assert gefunden == "127.0.0.1", (
            f"Das Pult wurde nicht gefunden: {gefunden}"
        )

        print("OK: Das Pult antwortet auf den Rundruf und wird gefunden")

        #
        # Die Bremse: Die Fader-Karte fragt alle zwei Sekunden. Ohne
        # sie ginge bei jeder Abfrage ein Rundruf ins Netz.
        #
        console.received.clear()

        for _ in range(5):
            assert sucher.discover() == "127.0.0.1"

        assert not console.received, (
            f"Trotz Bremse wurde erneut gesucht: {console.received}"
        )

        print("OK: Wiederholte Abfragen loesen keinen neuen Rundruf aus")

        #
        # Nach detect_reset() muss wieder gesucht werden - sonst
        # bliebe eine geaenderte Adresse fuer immer unentdeckt.
        #
        sucher.detect_reset()

        assert sucher.discover() == "127.0.0.1"
        assert console.received, "Nach detect_reset() wurde nicht neu gesucht."

        print("OK: Nach dem Zuruecksetzen wird wieder gesucht")

    finally:
        ccmodul.broadcast_addresses = original_broadcast
        ccmodul.PORT_XAIR = original_xair
        ccmodul.PORT_X32 = original_x32

    #
    # Antwortet niemand, darf der Suchlauf None liefern und nicht
    # haengen - sonst stuende die Oberflaeche bei jedem Aufruf.
    #
    leer = ConsoleControl()

    started = time.monotonic()
    assert leer.discover() is None
    elapsed = time.monotonic() - started

    assert elapsed < 3.0, f"Suchlauf ohne Pult dauerte {elapsed:.1f}s"

    print(f"OK: Ohne Pult liefert der Suchlauf None und haengt nicht ({elapsed:.2f}s)")

    # ----------------------------------------------------------------
    # 8. Reihenfolge, in der die Pult-IP gesucht wird
    #
    # Von Hand vor Vergabeliste vor Suchlauf. Eine falsche Reihenfolge
    # faellt nicht auf - sie benutzt einfach still die falsche Adresse.
    # ----------------------------------------------------------------

    import types

    from core.application import Application

    class FakeStore:

        def __init__(self, werte=None):
            self.werte = dict(werte or {})

        def get(self, key, default=None):
            return self.werte.get(key, default)

        def set(self, key, value):
            self.werte[key] = value

    zuruecksetzungen = []

    def stub(manual="", lease=None, discovered=None, channels=18):
        return types.SimpleNamespace(
            #
            # Steht hier bewusst noch drin, obwohl die Kanalzahl es
            # nicht mehr benutzt: So faellt auf, falls sie je wieder
            # von hier gezogen wird.
            #
            selected_audio_device=None,
            state_store=FakeStore({"console_ip_manual": manual}),
            wlan_control=types.SimpleNamespace(
                get_status=lambda: {"console_ip": lease}
            ),
            console_control=types.SimpleNamespace(
                discover=lambda: discovered,
                #
                # Die Kanalzahl kommt vom Pult - erreichbar heisst
                # channels, nicht erreichbar heisst 0.
                #
                channel_count=lambda host: channels if host else 0,
                #
                # set_console_host() verwirft das Gemerkte - hinter
                # einer neuen Adresse kann ein anderes Pult stecken.
                #
                detect_reset=lambda: zuruecksetzungen.append(True),
            ),
            logger=logging.getLogger("XRack-Test"),
        )

    #
    # Von Hand schlaegt alles andere - wer sie eintraegt, hat einen Grund.
    #
    host, kanaele, herkunft = Application._console_host_and_channels(
        stub(manual="10.0.0.5", lease="192.168.7.2", discovered="172.16.0.9")
    )
    assert (host, kanaele, herkunft) == ("10.0.0.5", 18, "manual"), (host, herkunft)

    #
    # Ohne Eintrag gewinnt die Vergabeliste des Pi: Steht die Konsole
    # dort, haengt sie per Kabel am Pi - naeher geht es nicht.
    #
    host, _, herkunft = Application._console_host_and_channels(
        stub(lease="192.168.7.2", discovered="172.16.0.9")
    )
    assert (host, herkunft) == ("192.168.7.2", "lease"), (host, herkunft)

    #
    # Und erst wenn beides fehlt, der Suchlauf - der Fall "beide am
    # Router".
    #
    host, _, herkunft = Application._console_host_and_channels(
        stub(discovered="172.16.0.9")
    )
    assert (host, herkunft) == ("172.16.0.9", "discovered"), (host, herkunft)

    #
    # Findet auch der nichts, bleibt es bei None - die Karte zeigt dann
    # ihren Hinweis statt toter Regler.
    #
    host, _, _ = Application._console_host_and_channels(stub())
    assert host is None

    print("OK: Die Pult-IP wird in der richtigen Reihenfolge gesucht")

    #
    # Leerzeichen im Eingabefeld duerfen nicht als Adresse durchgehen -
    # sonst schiebe XRack OSC-Pakete an einen leeren Hostnamen.
    #
    host, _, herkunft = Application._console_host_and_channels(
        stub(manual="   ", lease="192.168.7.2")
    )
    assert (host, herkunft) == ("192.168.7.2", "lease"), (host, herkunft)

    print("OK: Ein leeres Feld schaltet zurueck auf die automatische Suche")

    #
    # Ungueltige Eingaben werden abgelehnt, gueltige gemerkt.
    #
    eintragen = stub()

    assert Application.set_console_host(eintragen, "keine-ip")[0] is False
    assert Application.set_console_host(eintragen, "999.1.1.1")[0] is False
    assert Application.set_console_host(eintragen, "192.168.1.50")[0] is True

    assert eintragen.state_store.get("console_ip_manual") == "192.168.1.50"

    print("OK: Ungueltige Adressen werden abgelehnt, gueltige gemerkt")

    #
    # Beim Eintragen muss das Gemerkte verworfen werden. Sonst
    # spraeche XRack die neue Adresse mit der Familie und dem Port des
    # alten Pults an - und wunderte sich, dass niemand antwortet.
    #
    assert zuruecksetzungen, "Nach einer neuen Adresse wurde nicht zurueckgesetzt."

    print("OK: Eine neue Adresse verwirft die gemerkte Pult-Erkennung")

    # ----------------------------------------------------------------
    # 9. Automatische Sperre der Kanalzuege
    # ----------------------------------------------------------------

    sperre = stub()

    #
    # Voreinstellung: an, nach einer Minute.
    #
    voreinstellung = Application.get_faders_autolock(sperre)

    assert voreinstellung == {"enabled": True, "seconds": 60}, voreinstellung

    #
    # Gueltige Werte werden gemerkt.
    #
    assert Application.set_faders_autolock(sperre, True, 120)[0] is True
    assert Application.get_faders_autolock(sperre) == {
        "enabled": True,
        "seconds": 120,
    }

    #
    # Grenzen: zu kurz waere unbenutzbar - gesperrt, bevor man den
    # Regler losgelassen hat.
    #
    assert Application.set_faders_autolock(sperre, True, 1)[0] is False
    assert Application.set_faders_autolock(sperre, True, 99999)[0] is False
    assert Application.set_faders_autolock(sperre, True, "viel")[0] is False

    #
    # Abgelehnte Werte duerfen den gemerkten nicht ueberschreiben.
    #
    assert Application.get_faders_autolock(sperre)["seconds"] == 120, (
        "Ein abgelehnter Wert hat den gemerkten ueberschrieben."
    )

    print("OK: Die automatische Sperre nimmt nur sinnvolle Zeiten an")

    #
    # Die Zeit bleibt gemerkt, auch wenn die Sperre aus ist - sonst
    # muesste man sie beim Wiedereinschalten neu eingeben.
    #
    assert Application.set_faders_autolock(sperre, False, 300)[0] is True
    assert Application.get_faders_autolock(sperre) == {
        "enabled": False,
        "seconds": 300,
    }

    print("OK: Die Zeit bleibt gemerkt, auch wenn die Sperre aus ist")

    # ----------------------------------------------------------------
    # 10. XRack merkt sich nur die selbst gesetzten Kopplungen
    #
    # Eine Kopplung, die am Pult eingerichtet wurde, gehoert dem
    # Nutzer. XRack darf sie nicht ungefragt aufloesen - und deshalb
    # auch gar nicht erst zum Entkoppeln anbieten.
    # ----------------------------------------------------------------

    gesetzt = []

    kopplung = types.SimpleNamespace(
        selected_audio_device=types.SimpleNamespace(channels=18),
        state_store=FakeStore({"console_ip_manual": "127.0.0.1"}),
        wlan_control=types.SimpleNamespace(get_status=lambda: {"console_ip": None}),
        console_control=types.SimpleNamespace(
            set_link=lambda host, channels, start, linked: (
                gesetzt.append((start, linked)) or True
            ),
            channel_count=lambda host: 18,
        ),
        logger=logging.getLogger("XRack-Test"),
    )

    #
    # Die Aufloesung der Pult-IP ist hier nicht der Pruefgegenstand -
    # sie hat ihren eigenen Abschnitt weiter oben.
    #
    kopplung._console_host_and_channels = (
        lambda: Application._console_host_and_channels(kopplung)
    )
    kopplung._linked_by_xrack = lambda: Application._linked_by_xrack(kopplung)

    assert Application.set_console_pair_link(kopplung, 9, True) is True
    assert gesetzt == [(9, True)]

    assert kopplung.state_store.get("console_linked_by_xrack") == [9]

    #
    # Ein zweites Paar kommt dazu, nicht an dessen Stelle.
    #
    assert Application.set_console_pair_link(kopplung, 3, True) is True
    assert kopplung.state_store.get("console_linked_by_xrack") == [3, 9]

    #
    # Entkoppeln nimmt es wieder aus der Liste.
    #
    assert Application.set_console_pair_link(kopplung, 9, False) is True
    assert kopplung.state_store.get("console_linked_by_xrack") == [3]

    print("OK: XRack merkt sich, welche Paare es selbst gekoppelt hat")

    #
    # Scheitert das Senden ans Pult, darf auch nichts gemerkt werden -
    # sonst boete XRack spaeter an, etwas zu entkoppeln, das es nie
    # gekoppelt hat.
    #
    kopplung.console_control.set_link = lambda host, channels, start, linked: False

    assert Application.set_console_pair_link(kopplung, 11, True) is False
    assert kopplung.state_store.get("console_linked_by_xrack") == [3], (
        "Trotz fehlgeschlagener Kopplung wurde etwas gemerkt."
    )

    print("OK: Eine fehlgeschlagene Kopplung wird nicht gemerkt")

    # ----------------------------------------------------------------
    # Snapshots: auflisten und laden
    #
    # Die Adressen dafuer sind belegt (siehe Kommentar in
    # core/console_control.py), die fuer die NAMEN dagegen nicht -
    # deshalb steht hier ausdruecklich auch der Fall, dass das Pult
    # darauf gar nicht antwortet.
    # ----------------------------------------------------------------

    console.snapshots = {1: "Soundcheck", 2: "", 3: "Konzert"}
    console.snapshot_index = 3

    control.detect_reset()
    control._family = FAMILY_XAIR
    control._port = console.port
    control._detected_for = "127.0.0.1"

    snapshots = control.get_snapshots("127.0.0.1")

    assert snapshots is not None, "Keine Antwort vom Pult."
    assert len(snapshots) == 64, f"X-Air hat 64 Snapshots, bekommen: {len(snapshots)}"

    assert snapshots[0] == {"index": 1, "name": "Soundcheck", "current": False}, (
        snapshots[0]
    )

    #
    # Ein unbenutzter Platz hat keinen Namen - und einen leeren
    # Namen zurueckzugeben waere schlechter, als ehrlich None zu
    # sagen: Die Oberflaeche kann dann "Snapshot 2" anzeigen.
    #
    assert snapshots[1]["name"] is None, snapshots[1]

    assert snapshots[2] == {"index": 3, "name": "Konzert", "current": True}, (
        snapshots[2]
    )

    print("OK: Snapshots werden mit Namen und aktuellem Platz gelesen")

    # ----------------------------------------------------------------
    # Die Liste wird gemerkt - sie zu holen kostet 64 Abfragen
    # ----------------------------------------------------------------

    vorher = len(console.received)

    control.get_snapshots("127.0.0.1")

    assert len(console.received) == vorher, (
        f"Die gemerkte Liste wurde nicht benutzt - {len(console.received) - vorher} "
        f"zusaetzliche Abfragen."
    )

    control.get_snapshots("127.0.0.1", force=True)

    assert len(console.received) > vorher, (
        "Mit force muss trotzdem neu gelesen werden."
    )

    print("OK: Die Liste wird gemerkt, force liest neu")

    # ----------------------------------------------------------------
    # Kennt das Pult die Namensadresse nicht, wird nach wenigen
    # Versuchen aufgegeben
    #
    # Ohne diesen Abbruch liefe jede der 64 Abfragen in ihre eigene
    # Zeitueberschreitung - bei 0,3 s pro Abfrage waeren das fast
    # zwanzig Sekunden Stillstand.
    # ----------------------------------------------------------------

    console.answer_snapshot_names = False
    console.received.clear()

    control.detect_reset()
    control._family = FAMILY_XAIR
    control._port = console.port
    control._detected_for = "127.0.0.1"

    snapshots = control.get_snapshots("127.0.0.1")

    assert snapshots is not None
    assert len(snapshots) == 64, "Die Plaetze muss es trotzdem alle geben."
    assert all(eintrag["name"] is None for eintrag in snapshots)

    namensabfragen = [
        adresse for adresse, _ in console.received
        if adresse.startswith("/-snap/") and adresse.endswith("/name")
    ]

    assert len(namensabfragen) <= SNAPSHOT_NAME_PROBES, (
        f"Es wurde weitergefragt, obwohl niemand antwortet: "
        f"{len(namensabfragen)} Abfragen"
    )

    print("OK: Schweigt das Pult zu den Namen, wird nach wenigen Versuchen aufgegeben")

    console.answer_snapshot_names = True

    # ----------------------------------------------------------------
    # Laden: die richtige Adresse mit der richtigen Nummer
    # ----------------------------------------------------------------

    console.received.clear()

    assert control.load_snapshot("127.0.0.1", 7) is True

    time.sleep(0.1)

    geladen = [
        (adresse, argumente) for adresse, argumente in console.received
        if adresse == "/-snap/load"
    ]

    assert geladen == [("/-snap/load", [7])], (
        f"Falsche Adresse oder falscher Wert: {console.received}"
    )

    print("OK: Laden schickt /-snap/load mit der Nummer")

    # ----------------------------------------------------------------
    # Nummern, die es nicht gibt, gar nicht erst schicken
    # ----------------------------------------------------------------

    console.received.clear()

    assert control.load_snapshot("127.0.0.1", 0) is False, (
        "Der X-Air zaehlt ab 1 - 0 gibt es nicht."
    )
    assert control.load_snapshot("127.0.0.1", 65) is False

    time.sleep(0.1)

    assert console.received == [], (
        f"Es wurde trotzdem etwas geschickt: {console.received}"
    )

    print("OK: Unmoegliche Snapshot-Nummern werden nicht geschickt")

    # ----------------------------------------------------------------
    # Nach dem Laden ist die gemerkte Liste hinfaellig
    #
    # Der Snapshot kann Kopplungen anders setzen, und "aktuell" zeigt
    # sonst weiter auf den alten Platz.
    # ----------------------------------------------------------------

    control.get_snapshots("127.0.0.1")

    console.snapshot_index = 7
    console.received.clear()

    control.load_snapshot("127.0.0.1", 7)

    frisch = control.get_snapshots("127.0.0.1")

    assert frisch is not None
    assert frisch[6]["current"] is True, (
        "Nach dem Laden zeigt die Liste noch den alten aktuellen Platz."
    )

    print("OK: Nach dem Laden wird die Liste neu gelesen")

    # ----------------------------------------------------------------
    # Die Kanalzahl kommt vom Pult, nicht vom Audiointerface
    #
    # Rueckfall-Test zu einem Fehler aus dem Feld: Pult per Rundruf im
    # selben Netz gefunden, Snapshots erschienen - die Kanalzuege
    # nicht. Grund war, dass die Kanalzahl aus dem gewaehlten
    # Audiointerface stammte. Ohne angestecktes Interface war sie
    # null, und die Karte meldete "keine Verbindung", obwohl das Pult
    # gerade geantwortet hatte.
    #
    # Die beiden haben nichts miteinander zu tun: Die Fader laufen
    # ueber Netzwerk, das Interface ueber USB.
    # ----------------------------------------------------------------

    import types

    from core.application import Application

    control.detect_reset()
    control._family = FAMILY_XAIR
    control._port = console.port
    control._detected_for = "127.0.0.1"

    assert control.channel_count("127.0.0.1") == 18, (
        "Ein X-Air hat 16 Kanaele plus Aux-Rueckweg."
    )

    def pult_stub(interface_kanaele):
        """Application-Attrappe mit und ohne gewaehltes Audiointerface."""

        zeug = types.SimpleNamespace(
            selected_audio_device=(
                types.SimpleNamespace(channels=interface_kanaele)
                if interface_kanaele
                else None
            ),
            state_store=FakeStoreKanaele(),
            wlan_control=types.SimpleNamespace(
                get_status=lambda: {"console_ip": "127.0.0.1"}
            ),
            console_control=control,
            logger=logging.getLogger("XRack-Test"),
        )

        zeug._console_host_and_channels = (
            lambda: Application._console_host_and_channels(zeug)
        )

        return zeug

    mit = Application.get_console_channels(pult_stub(18))
    ohne = Application.get_console_channels(pult_stub(0))

    assert mit["available"] is True, mit
    assert ohne["available"] is True, (
        "Ohne gewaehltes Audiointerface fehlen die Kanalzuege - genau "
        f"der gemeldete Fehler: {ohne}"
    )

    beschriftungen = [zug["label"] for zug in ohne["channels"]]

    assert beschriftungen == [zug["label"] for zug in mit["channels"]], (
        "Das Audiointerface darf die Kanalzuege nicht veraendern."
    )
    assert beschriftungen[-2:] == ["17+18", "Main"], beschriftungen

    print(
        "OK: Die Kanalzuege haengen am Pult, nicht am Audiointerface "
        f"({len(beschriftungen)} Zuege mit und ohne Interface)"
    )

    # ----------------------------------------------------------------
    # Und die Fallunterscheidung bleibt ehrlich: Adresse bekannt, Pult
    # stumm -> "antwortet nicht", nicht "kein Zugangsweg". Sonst
    # schickt die Oberflaeche den Nutzer in die Einstellungen, obwohl
    # dort alles richtig steht.
    # ----------------------------------------------------------------

    control.detect_reset()

    stumm = Application.get_console_channels(pult_stub(0))

    assert stumm["available"] is False
    assert stumm["reason"] == "no_response", stumm
    assert stumm["host"] == "127.0.0.1", stumm

    print("OK: Stummes Pult meldet 'antwortet nicht', nicht 'kein Zugangsweg'")

finally:
    console.stop()

#
# Bewusst ausserhalb des finally: Im finally wuerde die Meldung auch
# dann erscheinen, wenn gerade eine Pruefung fehlgeschlagen ist.
#
print("Alle Tests erfolgreich.")
