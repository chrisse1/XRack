"""
Steuert die Kanalfader des Mischpults über OSC (Open Sound Control)
per UDP - damit man beim Üben nicht zwischen XRack und X-AIR-Edit/
X32-Edit hin- und herwechseln muss.

Bewusst nur Lautstärke: kein EQ, keine Sends, kein Routing.

Warum OSC hier von Hand kodiert wird statt über python-osc: Eine neue
Zeile in requirements.txt hätte zur Folge, dass das Update über den
USB-Stick "pip install" ausführen müsste - und damit Internet bräuchte,
also genau das, was der Stick-Weg vermeidet (siehe
scripts/xrack-update.py). Eine OSC-Nachricht ist einfach genug, um sie
mit der Standardbibliothek zu erzeugen.

Voraussetzung: Die Konsole muss über Netzwerk erreichbar sein, also per
Kabel am Pi hängen (Schalter "Konsole aus dem Heimnetz erreichbar
machen" oder der Access-Point-Weg). Über das USB-Audiokabel allein gibt
es keinen Steuerweg.
"""

import logging
import math
import socket
import struct
import time
from typing import NamedTuple

import psutil

#
# X32/M32 lauschen auf 10023, die X-Air-Serie (XR12/16/18, X18) auf
# 10024. Welche Familie angeschlossen ist, ermittelt detect() selbst.
#
PORT_X32 = 10023
PORT_XAIR = 10024

FAMILY_X32 = "x32"
FAMILY_XAIR = "xair"

#
# Antwortzeit im lokalen Netz liegt weit darunter - kurz genug, dass ein
# stummes Pult die Weboberfläche nicht hängen lässt.
#
TIMEOUT = 0.3

MIN_DB = -90.0

#
# ------------------------------------------------------------------
# Snapshots (X-Air) bzw. Szenen (X32)
# ------------------------------------------------------------------
#
# Beide Familien koennen einen gespeicherten Gesamtzustand aufrufen,
# nennen ihn aber verschieden und sprechen ihn ueber verschiedene
# Adressen an.
#
# Belegt sind diese Adressen ueber eine im Feld benutzte Bibliothek
# (wrodie/behringer-mixer) und die offizielle OSC-Beschreibung:
#
#   X-Air:  /-snap/load   (int)  Snapshot aufrufen
#           /-snap/index  (int)  aktuell geladener Snapshot
#   X32:    /-action/goscene       (int)  Szene aufrufen
#           /-show/prepos/current  (int)  aktuelle Szene
#
# Die Namen der einzelnen Plaetze sind dagegen NICHT belegt - die
# Adressen unten sind der ueblicherweise verwendete Aufbau. Deshalb
# ist das Auslesen der Namen so gebaut, dass es folgenlos scheitern
# darf: Antwortet das Pult darauf nicht, zeigt die Oberflaeche eben
# nur Nummern. Das Aufrufen selbst haengt nicht daran.
#
SNAPSHOT_LOAD = {
    FAMILY_XAIR: "/-snap/load",
    FAMILY_X32: "/-action/goscene",
}

SNAPSHOT_CURRENT = {
    FAMILY_XAIR: "/-snap/index",
    FAMILY_X32: "/-show/prepos/current",
}

#
# {} wird durch die Platznummer ersetzt - beim X-Air zweistellig
# ("01"), beim X32 dreistellig ("000") und dort ab 0 gezaehlt.
#
SNAPSHOT_NAME = {
    FAMILY_XAIR: "/-snap/{:02d}/name",
    FAMILY_X32: "/-show/showfile/scene/{:03d}/name",
}

SNAPSHOT_COUNT = {
    FAMILY_XAIR: 64,
    FAMILY_X32: 100,
}

#
# Der X32 zaehlt seine Szenen ab 0, der X-Air seine Snapshots ab 1.
#
SNAPSHOT_FIRST = {
    FAMILY_XAIR: 1,
    FAMILY_X32: 0,
}

#
# So viele Plaetze werden angetastet, bevor das Auslesen der Namen
# aufgegeben wird. Antwortet das Pult auf keinen davon, kennt es die
# Namensadresse nicht - dann kosten weitere 60 Versuche nur Zeit
# (jeder einzelne laeuft in seine Zeitueberschreitung).
#
SNAPSHOT_NAME_PROBES = 3

#
# Wie lange die gelesene Liste gilt. Snapshots aendern sich selten,
# und die Liste zu holen kostet je nach Pult bis zu hundert Abfragen.
#
SNAPSHOT_CACHE_SECONDS = 60.0
MAX_DB = 10.0

#
# Suchlauf per Rundruf: So finden auch X-AIR-Edit und X32-Edit ihre
# Pulte. Gebraucht wird das, wenn Pult und Pi zusammen an einem Router
# hängen - dann ist nicht der Pi der DHCP-Server, und seine
# Vergabeliste kennt die Konsole gar nicht.
#
DISCOVERY_TIMEOUT = 0.6

#
# Wie oft höchstens gesucht wird. Die Fader-Karte fragt im entsperrten
# Zustand alle zwei Sekunden - ohne diese Bremse ginge bei jeder
# Abfrage ein Rundruf ins Netz.
#
DISCOVERY_INTERVAL = 30.0


def broadcast_addresses() -> list[str]:
    """
    Liefert die Rundruf-Adressen aller IPv4-Schnittstellen.

    Nicht einfach 255.255.255.255: Hat der Pi mehrere Schnittstellen
    (WLAN und Kabel), entscheidet dabei die Routing-Tabelle, über
    welche gesendet wird - und das ist womöglich nicht die, an der das
    Pult hängt. Je Schnittstelle ihre eigene Adresse zu nehmen erreicht
    beide.
    """

    result = []

    try:

        for addresses in psutil.net_if_addrs().values():

            for address in addresses:

                if address.family != socket.AF_INET:
                    continue

                if not address.broadcast:
                    continue

                if address.address.startswith("127."):
                    continue

                if address.broadcast not in result:
                    result.append(address.broadcast)

    except Exception:
        #
        # Schnittstellen nicht auslesbar - dann wenigstens der
        # allgemeine Rundruf.
        #
        pass

    if not result:
        result.append("255.255.255.255")

    return result


def pad(data: bytes) -> bytes:
    """
    Füllt auf ein Vielfaches von 4 Byte auf - OSC verlangt das für
    Strings und Blobs.

    Der Nullabschluss steckt schon in `data`. Passt die Länge damit
    bereits ins 4-Byte-Raster, wird NICHT weiter aufgefüllt - "4 -
    len % 4" hätte hier vier überzählige Nullen angehängt. Die
    Nachricht bliebe zwar ausgerichtet, aber das Typ-Tag stünde vier
    Byte zu spät, und der Empfänger läse eine Nachricht ohne
    Argumente. Betroffen war jede Adresse mit 19, 23, 27 ... Zeichen
    - dass es bisher nicht auffiel, lag nur daran, dass keine der
    verwendeten Adressen diese Länge hatte.
    """

    return data + b"\x00" * (-len(data) % 4)


def encode(address: str, *arguments) -> bytes:
    """
    Baut eine OSC-Nachricht. Unterstützt Float und String als Argumente
    - mehr braucht es für Fader und Kanalnamen nicht.
    """

    message = pad(address.encode("ascii") + b"\x00")

    tags = ","
    values = b""

    for argument in arguments:

        #
        # bool zuerst prüfen: In Python ist bool eine Unterklasse von
        # int, sonst würde True als Integer 1 durchrutschen - was hier
        # zwar zufällig richtig wäre, aber nur zufällig.
        #
        if isinstance(argument, bool):
            tags += "i"
            values += struct.pack(">i", 1 if argument else 0)

        elif isinstance(argument, float):
            tags += "f"
            values += struct.pack(">f", argument)

        elif isinstance(argument, int):
            tags += "i"
            values += struct.pack(">i", argument)

        elif isinstance(argument, str):
            tags += "s"
            values += pad(argument.encode("ascii") + b"\x00")

        else:
            raise TypeError(f"Nicht unterstützter OSC-Typ: {type(argument)}")

    message += pad(tags.encode("ascii") + b"\x00")

    return message + values


def decode(data: bytes) -> tuple[str, list]:
    """
    Zerlegt eine OSC-Nachricht in Adresse und Argumente. Liefert eine
    leere Argumentliste, wenn die Nachricht keine (lesbaren) enthält.
    """

    def read_string(offset: int) -> tuple[str, int]:

        end = data.index(b"\x00", offset)

        text = data[offset:end].decode("ascii", errors="replace")

        #
        # Weiter zum nächsten 4-Byte-Raster.
        #
        return text, offset + (len(text) // 4 + 1) * 4

    address, offset = read_string(0)

    if offset >= len(data) or data[offset:offset + 1] != b",":
        return address, []

    tags, offset = read_string(offset)

    arguments = []

    for tag in tags[1:]:

        if tag == "f":
            arguments.append(struct.unpack_from(">f", data, offset)[0])
            offset += 4

        elif tag == "i":
            arguments.append(struct.unpack_from(">i", data, offset)[0])
            offset += 4

        elif tag == "s":
            text, offset = read_string(offset)
            arguments.append(text)

        else:
            #
            # Unbekannter Typ: Rest verwerfen, statt falsch zu raten.
            #
            break

    return address, arguments


def fader_to_db(value: float) -> float:
    """
    Rechnet den OSC-Faderwert (0.0-1.0) in dB um.

    Die Kennlinie der X-Serie ist stückweise linear, nicht gleichmäßig:
    0 dB liegt bei etwa 0.75 Reglerweg, nicht bei der Hälfte. Ganz unten
    (0.0) ist der Fader zu, das entspricht -unendlich.
    """

    value = max(0.0, min(1.0, value))

    if value <= 0.0:
        return float("-inf")

    if value >= 0.5:
        return value * 40.0 - 30.0

    if value >= 0.25:
        return value * 80.0 - 50.0

    if value >= 0.0625:
        return value * 160.0 - 70.0

    return value * 480.0 - 90.0


def db_to_fader(db: float) -> float:
    """
    Umkehrung von fader_to_db().
    """

    if db == float("-inf") or db <= MIN_DB:
        return 0.0

    db = min(MAX_DB, db)

    if db >= -10.0:
        value = (db + 30.0) / 40.0

    elif db >= -30.0:
        value = (db + 50.0) / 80.0

    elif db >= -60.0:
        value = (db + 70.0) / 160.0

    else:
        value = (db + 90.0) / 480.0

    return max(0.0, min(1.0, value))


class ChannelSpec(NamedTuple):
    """Ein Regler: wohin geschickt wird, wie er heißt, und ob er die Summe ist."""

    address: str
    label: str
    is_main: bool = False


#
# Adresse des Summenreglers - unterscheidet sich je Familie.
#
MAIN_ADDRESS = {
    FAMILY_XAIR: "/lr",
    FAMILY_X32: "/main/st",
}


def channel_addresses(
    family: str, channels: int, linked=()
) -> list[ChannelSpec]:
    """
    Liefert die Regler: Eingangskanäle und am Ende die Summe.

    `linked` enthält die Nummern der jeweils ERSTEN Kanäle gekoppelter
    Paare (die 1 steht also für das Paar 1+2). Ein gekoppeltes Paar
    ergibt nur einen Regler, beschriftet wie "1+2" - zwei getrennte
    Regler wären dort nur doppelt, weil das Pult den zweiten Kanal
    ohnehin mitzieht.

    Die Adressen bilden die Kanalzahl des Audiointerfaces *nicht*
    durchgehend ab: Beim X32 sind es echte /ch/01 bis /ch/32, die
    X-Air-Serie hat dagegen nur 16 Mono-Kanäle plus ein Aux-Rückweg-Paar
    mit eigener Adresse. Ein XR18 mit 18 USB-Kanälen ergibt dort also
    17 Kanalregler, weil der Aux-Rückweg ein Stereopaar mit einem
    gemeinsamen Fader ist - er wird als "17+18" beschriftet. Auch die
    Summe heißt je nach Familie anders. Darum eine ausdrückliche Liste
    statt einer Formel: So stehen alle diese Unterschiede an genau
    einer Stelle und sind am Pult leicht zu korrigieren.
    """

    linked = set(linked)

    count = min(channels, 16 if family == FAMILY_XAIR else 32)

    result = []
    index = 1

    while index <= count:

        if index in linked and index + 1 <= count:

            #
            # Gekoppeltes Paar: eine Adresse, Beschriftung wie beim
            # Aux-Rückweg. Geschickt wird an den ersten Kanal, den
            # zweiten zieht das Pult selbst mit.
            #
            result.append(
                ChannelSpec(f"/ch/{index:02d}", f"{index}+{index + 1}")
            )

            index += 2

        else:

            result.append(ChannelSpec(f"/ch/{index:02d}", str(index)))

            index += 1

    if family == FAMILY_XAIR and channels >= 18:
        result.append(ChannelSpec("/rtn/aux", "17+18"))

    main = MAIN_ADDRESS.get(family)

    if main:
        result.append(ChannelSpec(main, "Main", is_main=True))

    return result


def pair_addresses(
    family: str, channels: int, start: int, linked=()
) -> list[str]:
    """
    Liefert die Adressen, über die sich das Stereopaar (start,
    start+1) regeln lässt.

    Meist zwei - die beiden Kanäle sind am Pult eigenständig. Nur eine
    in zwei Fällen:

    - Die Kanäle sind am Pult gekoppelt. Dann zieht das Pult den
      Partner selbst mit; zweimal zu senden wäre überflüssig und würde
      einen absichtlichen Versatz zwischen beiden einebnen.
    - Das Paar ist von Natur aus stereo und hat nur einen Fader. Beim
      X-Air sind das die Kanäle 17+18: Die liegen auf dem
      Aux-Rückweg (/rtn/aux) und hatten nie zwei getrennte Regler.
      Genau deshalb gibt es dort auch nichts zu koppeln.

    Leere Liste, wenn das Paar außerhalb der Kanäle liegt.
    """

    specs = channel_addresses(family, channels, linked)

    #
    # Natürliches Stereopaar: Ein Regler, dessen Beschriftung beide
    # Kanäle nennt ("17+18"). Genauso sieht eine gekoppelte Zweiergruppe
    # aus - beide sind hier richtig behandelt.
    #
    beschriftung = f"{start}+{start + 1}"

    for spec in specs:
        if spec.label == beschriftung:
            return [spec.address]

    #
    # Sonst die beiden Kanäle einzeln - der Regler in der Karte muss
    # dann eben zwei Adressen bedienen.
    #
    result = []

    for nummer in (start, start + 1):

        for spec in specs:
            if spec.label == str(nummer):
                result.append(spec.address)
                break

    return result


def is_natural_pair(family: str, channels: int, start: int) -> bool:
    """
    True, wenn das Paar am Pult ohnehin nur einen Fader hat und sich
    deshalb weder koppeln noch entkoppeln lässt.

    Geprüft wird ohne jede Kopplung: Bleibt es auch dann ein einziger
    Regler, liegt es an der Bauart und nicht an einer Einstellung.
    """

    return len(pair_addresses(family, channels, start)) == 1


class ConsoleControl:
    """
    Spricht mit dem Mischpult. Hält keine dauerhafte Verbindung - jede
    Anfrage ist ein kurzer UDP-Austausch, damit ein zwischenzeitlich
    abgezogenes Kabel keinen kaputten Zustand hinterlässt.
    """

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        #
        # Einmal ermittelte Familie samt Port merken - die Erkennung
        # kostet zwei Anfragen und ändert sich im Betrieb nicht.
        #
        self._family: str | None = None
        self._port: int | None = None
        self._detected_for: str | None = None

        #
        # Gekoppelte Kanalpaare. Der Stand wird gemerkt, damit ein
        # Reglerbefehl dieselbe Kanalliste trifft, die die Oberfläche
        # gerade anzeigt - sonst könnte eine Kopplung, die zwischen
        # Anzeigen und Schieben umgelegt wird, die Nummern verschieben
        # und der Befehl landete auf dem Nachbarkanal.
        #
        self._linked: set[int] = set()

        #
        # None = noch nicht geprüft. False bei _link_supported heißt:
        # Das Pult kennt die Abfrage nicht, also gar nicht erst wieder
        # fragen.
        #
        self._link_supported = True
        self._fader_link: bool | None = None

        #
        # Ergebnis des Suchlaufs samt Zeitpunkt des letzten Versuchs.
        #
        self._discovered: str | None = None
        self._last_discovery = 0.0

        #
        # Kopplungszustand einzelner Paare, je Startkanal mit
        # Zeitstempel. Anders als _linked (das get_channels für alle
        # Paare auf einmal holt) wird hier gezielt ein Paar gefragt -
        # die Karten von Musikspieler und Bluetooth brauchen immer nur
        # ihr eigenes.
        #
        self._pair_link: dict[int, tuple[float, bool]] = {}

        #
        # Gelesene Snapshot-Liste, mit Zeitstempel: Sie zu holen
        # kostet je nach Pult bis zu hundert Abfragen.
        #
        self._snapshots: list[dict] | None = None
        self._snapshots_read = 0.0

    def _request(self, host: str, port: int, message: bytes) -> bytes | None:
        """
        Schickt eine Nachricht und wartet auf genau eine Antwort.
        Liefert None, wenn nichts kommt.
        """

        try:

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:

                sock.settimeout(TIMEOUT)
                sock.sendto(message, (host, port))

                data, _ = sock.recvfrom(4096)

                return data

        except (socket.timeout, OSError):
            return None

    def _send(self, host: str, port: int, message: bytes) -> bool:
        """Schickt eine Nachricht ohne auf Antwort zu warten."""

        try:

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(message, (host, port))

            return True

        except OSError as exc:

            self.logger.warning("OSC konnte nicht gesendet werden: %s", exc)

            return False

    def detect_reset(self) -> None:
        """
        Verwirft alles Gemerkte - Familie, Port, Kopplungen und den
        Suchlauf.

        Nötig, wenn sich die Adresse ändert: Dahinter kann ein anderes
        Pult stecken, und die Familienerkennung hängt am Host.
        """

        self._family = None
        self._port = None
        self._detected_for = None
        self._linked = set()
        self._link_supported = True
        self._fader_link = None
        self._discovered = None
        self._last_discovery = 0.0
        self._pair_link = {}
        self._snapshots = None
        self._snapshots_read = 0.0

    def discover(self, force: bool = False) -> str | None:
        """
        Sucht das Pult per Rundruf im lokalen Netz.

        Gebraucht wird das, wenn Pult und Pi zusammen an einem Router
        hängen: Dann vergibt der Router die Adressen, der Pi hat keine
        Vergabeliste, in der die Konsole stünde - und ohne Adresse
        nützt der beste Steuerweg nichts.

        Das Ergebnis wird gemerkt und höchstens alle 30 Sekunden neu
        ermittelt. Damit heilt sich ein veralteter Treffer von selbst
        (das Pult bekommt eine neue Adresse), ohne dass jede Abfrage
        der Fader-Karte einen Rundruf auslöst.

        `force` überspringt diese Wartezeit. Das ist für den Fall
        gedacht, dass jemand ausdrücklich "erneut suchen" drückt: Wer
        das tut, hat gerade etwas verändert (Kabel eingesteckt, Pult
        eingeschaltet) und soll nicht bis zu 30 Sekunden auf eine
        Antwort warten, die längst zu holen wäre.
        """

        now = time.monotonic()

        if not force and now - self._last_discovery < DISCOVERY_INTERVAL:
            return self._discovered

        self._last_discovery = now
        self._discovered = self._probe()

        if self._discovered:
            self.logger.info("Mischpult gefunden: %s", self._discovered)

        return self._discovered

    def _probe(self) -> str | None:
        """Ein Rundruf-Durchgang auf beiden Ports."""

        message = encode("/info")

        try:

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:

                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(DISCOVERY_TIMEOUT)

                for address in broadcast_addresses():

                    for port in (PORT_XAIR, PORT_X32):

                        try:
                            sock.sendto(message, (address, port))
                        except OSError:
                            #
                            # Einzelne Schnittstelle nicht bespielbar -
                            # die anderen trotzdem versuchen.
                            #
                            continue

                deadline = time.monotonic() + DISCOVERY_TIMEOUT

                while time.monotonic() < deadline:

                    try:
                        data, sender = sock.recvfrom(4096)
                    except (socket.timeout, OSError):
                        break

                    #
                    # Nur eine echte /info-Antwort zählt. Im Netz kann
                    # auf einen Rundruf auch anderes zurückkommen, und
                    # dessen Adresse als Pult zu nehmen wäre schlimmer
                    # als gar kein Treffer.
                    #
                    if decode(data)[0] == "/info":
                        return sender[0]

        except OSError as exc:
            self.logger.warning("Suchlauf fehlgeschlagen: %s", exc)

        return None

    def detect(self, host: str) -> str | None:
        """
        Ermittelt, ob ein X32 (Port 10023) oder ein X-Air (10024)
        antwortet. Das Ergebnis wird gemerkt, solange sich die IP nicht
        ändert.
        """

        if self._family is not None and self._detected_for == host:
            return self._family

        message = encode("/info")

        for port, family in ((PORT_XAIR, FAMILY_XAIR), (PORT_X32, FAMILY_X32)):

            if self._request(host, port, message) is not None:

                self._family = family
                self._port = port
                self._detected_for = host

                #
                # Anderes Pult, andere Kopplungen - alles Gemerkte gilt
                # nicht mehr.
                #
                self._linked = set()
                self._link_supported = True
                self._fader_link = None

                self.logger.info(
                    "Mischpult erkannt: %s auf %s:%d",
                    family,
                    host,
                    port,
                )

                return family

        self._family = None
        self._port = None
        self._detected_for = None
        self._linked = set()

        return None

    def _fader_follows_link(self, host: str) -> bool:
        """
        Prüft, ob Fader und Stummschaltung der Kanalkopplung überhaupt
        folgen.

        Beim X32 ist das eine eigene Einstellung: Zwei Kanäle können
        gekoppelt sein (gleicher EQ, gleiche Dynamik), ihre Fader aber
        trotzdem unabhängig bleiben. In dem Fall dürfen wir sie nicht
        zu einem Regler zusammenfassen - sonst bewegt sich sichtbar nur
        die Hälfte.
        """

        if self._fader_link is not None:
            return self._fader_link

        answer = self._request(
            host, self._port, encode("/config/linkcfg/fdrmute")
        )

        if answer is None:

            #
            # Keine Antwort heißt: Das Pult kennt die Einstellung nicht
            # (die X-Air-Serie hat sie nicht). Dann gibt es auch keine
            # Einschränkung - dort ziehen gekoppelte Kanäle immer
            # zusammen.
            #
            self._fader_link = True

        else:

            _, arguments = decode(answer)

            self._fader_link = not (arguments and arguments[0] == 0)

        return self._fader_link

    def linked_pairs(self, host: str, channels: int) -> set[int]:
        """
        Fragt am Pult ab, welche Kanalpaare gekoppelt sind.

        Zurück kommt die Nummer des jeweils ERSTEN Kanals - die 1 steht
        also für das Paar 1+2. Nur Mono-Eingänge lassen sich koppeln;
        Aux-Rückweg und Summe sind ohnehin schon stereo.
        """

        if self._port is None or not self._link_supported:
            return set()

        if not self._fader_follows_link(host):
            return set()

        limit = min(channels, 16 if self._family == FAMILY_XAIR else 32)

        pairs = set()

        for first in range(1, limit, 2):

            answer = self._request(
                host,
                self._port,
                encode(f"/config/chlink/{first}-{first + 1}"),
            )

            if answer is None:

                #
                # Antwortet schon das erste Paar nicht, kennt das Pult
                # die Adresse nicht. Dann nicht weiterfragen: Sonst
                # kostet jede Aktualisierung acht bis sechzehn
                # Zeitüberschreitungen und die Oberfläche wird zäh.
                #
                if first == 1:
                    self._link_supported = False

                break

            _, arguments = decode(answer)

            if arguments and arguments[0] == 1:
                pairs.add(first)

        return pairs

    #
    # Lesen und Schreiben laufen fuer alle Regler ueber dieselben vier
    # Bausteine. Vorher stand dieselbe Abfrage-und-Auspacken-Folge an
    # sechs Stellen; ein Tippfehler in einer davon waere nur an genau
    # einem Regler aufgefallen.
    #

    def _read(self, host: str, address: str, endung: str, typ):
        """
        Fragt einen Wert ab und packt ihn aus.

        None heisst "keine oder keine brauchbare Antwort" - der
        Aufrufer entscheidet, ob das ein Standardwert oder ein
        Abbruchgrund ist. Der Unterschied zaehlt: Beim Auslesen der
        ganzen Kanalliste ist ein stummer Kanal kein Grund
        aufzugeben, beim einzelnen Stereopaar dagegen schon.

        Eine Anfrage ohne Argumente liefert bei der X-Serie den
        aktuellen Wert zurueck.
        """

        answer = self._request(host, self._port, encode(f"{address}{endung}"))

        if answer is None:
            return None

        _, arguments = decode(answer)

        if arguments and isinstance(arguments[0], typ):
            return arguments[0]

        return None

    def _read_db(self, host: str, address: str) -> float:
        """Faderstellung in dB; MIN_DB, wenn nichts zurueckkommt."""

        wert = self._read(host, address, "/mix/fader", float)

        return MIN_DB if wert is None else fader_to_db(wert)

    def _read_muted(self, host: str, address: str) -> bool:
        """
        Stummschaltung.

        Achtung, umgekehrte Logik: "mix/on" = 1 heisst, der Kanal ist
        AN. Stumm ist also 0, nicht 1.
        """

        wert = self._read(host, address, "/mix/on", int)

        return wert == 0 if wert is not None else False

    def _read_name(self, host: str, address: str) -> str:
        """Kanalbeschriftung vom Pult; leer, wenn unbenannt."""

        wert = self._read(host, address, "/config/name", str)

        return wert.strip() if wert else ""

    # ----------------------------------------------------------------
    # Snapshots (X-Air) bzw. Szenen (X32)
    # ----------------------------------------------------------------

    def get_snapshots(self, host: str, force: bool = False) -> list[dict] | None:
        """
        Liest die Liste der gespeicherten Snapshots.

        Liefert Eintraege aus {"index", "name", "current"} - oder
        None, wenn das Pult ueberhaupt nicht antwortet.

        Zwei Dinge sind hier wichtig:

        Erstens kostet das viele Abfragen - 64 beim X-Air, 100 beim
        X32. Deshalb wird die Liste gemerkt und nur alle 60 Sekunden
        neu geholt; `force` ueberspringt das.

        Zweitens ist die Adresse fuer die Namen nicht sicher belegt
        (siehe Kommentar bei SNAPSHOT_NAME). Schweigen die ersten
        Plaetze, wird das Auslesen der Namen abgebrochen und es bleibt
        bei den Nummern. Ohne diesen Abbruch liefe jede weitere
        Abfrage in ihre eigene Zeitueberschreitung - beim X32 waeren
        das dreissig Sekunden, in denen die Oberflaeche stillsteht.
        """

        jetzt = time.monotonic()

        if (
            not force
            and self._snapshots is not None
            and jetzt - self._snapshots_read < SNAPSHOT_CACHE_SECONDS
        ):
            return self._snapshots

        family = self.detect(host)

        if family is None or self._port is None:
            return None

        aktuell = self._read(host, SNAPSHOT_CURRENT[family], "", int)

        erster = SNAPSHOT_FIRST[family]
        anzahl = SNAPSHOT_COUNT[family]
        muster = SNAPSHOT_NAME[family]

        namen_lesbar = True
        ergebnis: list[dict] = []

        for nummer in range(erster, erster + anzahl):

            name = None

            if namen_lesbar:

                name = self._read(host, muster.format(nummer), "", str)

                #
                # Nach den ersten Versuchen entscheiden: Kam auf
                # keinen einzigen eine Antwort, kennt das Pult diese
                # Adresse nicht.
                #
                if (
                    name is None
                    and len(ergebnis) + 1 >= SNAPSHOT_NAME_PROBES
                    and all(eintrag["name"] is None for eintrag in ergebnis)
                ):
                    namen_lesbar = False

            ergebnis.append({
                "index": nummer,
                "name": (name or "").strip() or None,
                "current": aktuell is not None and nummer == aktuell,
            })

        self._snapshots = ergebnis
        self._snapshots_read = jetzt

        return ergebnis

    def load_snapshot(self, host: str, index: int) -> bool:
        """
        Ruft einen gespeicherten Snapshot auf.

        Das ist der eingreifendste Befehl, den XRack ans Pult schickt:
        Er stellt in einem Zug alle Regler, Stummschaltungen und
        Klangeinstellungen um. Die Rueckfrage davor gehoert deshalb in
        die Oberflaeche - hier wird nur noch ausgefuehrt.
        """

        family = self.detect(host)

        if family is None or self._port is None:
            return False

        erster = SNAPSHOT_FIRST[family]

        if not erster <= index < erster + SNAPSHOT_COUNT[family]:
            self.logger.warning("Snapshot %s gibt es nicht.", index)
            return False

        self.logger.info("Snapshot %s wird geladen.", index)

        erfolg = self._send(
            host, self._port, encode(SNAPSHOT_LOAD[family], int(index))
        )

        #
        # Nach dem Laden stimmt nichts Gemerktes mehr: Der Snapshot
        # kann Kopplungen anders setzen, und in der gemerkten Liste
        # steht noch der alte "aktuell"-Eintrag.
        #
        if erfolg:
            self._linked = set()
            self._pair_link = {}
            self._snapshots = None
            self._snapshots_read = 0.0

        return erfolg

    def _write(self, host: str, addresses: list[str], endung: str, wert) -> bool:
        """
        Schreibt denselben Wert an alle angegebenen Adressen.

        Mehrere sind es nur bei einem ungekoppelten Stereopaar - dort
        muessen beide Kanaele einzeln bedient werden.
        """

        return all(
            self._send(host, self._port, encode(f"{address}{endung}", wert))
            for address in addresses
        )

    def get_channels(self, host: str, channels: int) -> list[dict] | None:
        """
        Liest Namen und Faderstellung aller Kanäle.

        Liefert None, wenn das Pult nicht antwortet - dann zeigt die
        Oberfläche einen Hinweis statt toter Regler.
        """

        family = self.detect(host)

        if family is None or self._port is None:
            return None

        #
        # Vor dem Auslesen die Kopplungen holen - danach steht fest,
        # wie viele Regler es überhaupt gibt.
        #
        self._linked = self.linked_pairs(host, channels)

        result = []

        for index, spec in enumerate(
            channel_addresses(family, channels, self._linked), start=1
        ):

            address = spec.address

            #
            # Ein stummer Kanal ist hier kein Abbruchgrund - die
            # uebrigen sollen trotzdem erscheinen.
            #
            db = self._read_db(host, address)
            name = self._read_name(host, address)
            muted = self._read_muted(host, address)

            result.append(
                {
                    "channel": index,
                    "label": spec.label,
                    "name": name,
                    "is_main": spec.is_main,
                    "muted": muted,
                    #
                    # None steht für "Fader zu" (-unendlich) - als JSON
                    # gibt es kein -inf.
                    #
                    "db": None if math.isinf(db) else round(db, 1),
                }
            )

        return result

    #
    # Wie lange der Kopplungszustand eines Paars gilt, bevor neu
    # gefragt wird. Waehrend eines Reglerzugs darf nicht bei jedem
    # Schritt nachgefragt werden - das waeren Dutzende Anfragen pro
    # Sekunde, nur um zu wissen, wohin gesendet wird.
    #
    PAIR_LINK_MAX_AGE = 5.0

    def _pair_linked(self, host: str, start: int) -> bool:
        """
        Fragt gezielt fuer ein Paar, ob es am Pult gekoppelt ist.
        """

        if self._port is None or not self._link_supported:
            return False

        if not self._fader_follows_link(host):
            return False

        now = time.monotonic()

        stamp, value = self._pair_link.get(start, (0.0, False))

        if now - stamp < self.PAIR_LINK_MAX_AGE:
            return value

        answer = self._request(
            host,
            self._port,
            encode(f"/config/chlink/{start}-{start + 1}"),
        )

        if answer is None:

            if start == 1:
                self._link_supported = False

            self._pair_link[start] = (now, False)

            return False

        _, arguments = decode(answer)

        value = bool(arguments and arguments[0] == 1)

        self._pair_link[start] = (now, value)

        return value

    def _pair_targets(self, host: str, channels: int, start: int) -> list[str]:
        """Die Adressen, die fuer dieses Paar zu bedienen sind."""

        family = self.detect(host)

        if family is None or self._port is None:
            return []

        linked = {start} if self._pair_linked(host, start) else set()

        return pair_addresses(family, channels, start, linked)

    def get_pair(self, host: str, channels: int, start: int) -> dict | None:
        """
        Liest Pegel und Stummschaltung eines Stereopaars.

        Gelesen wird immer vom ersten Kanal des Paars. Stehen beide
        unterschiedlich, gewinnt also der erste - die Karte zeigt einen
        Regler, und der muss einen Wert haben.
        """

        targets = self._pair_targets(host, channels, start)

        if not targets:
            return None

        family = self._family

        #
        # Anders als beim Auslesen der ganzen Liste ist hier eine
        # ausbleibende Antwort ein Abbruchgrund: Die Karte zeigt genau
        # einen Regler, und ein Regler ohne Wert waere schlimmer als
        # gar keiner. Deshalb hier der rohe Wert statt _read_db().
        #
        roh = self._read(host, targets[0], "/mix/fader", float)

        if roh is None:
            return None

        db = fader_to_db(roh)
        muted = self._read_muted(host, targets[0])

        return {
            "db": None if math.isinf(db) else round(db, 1),
            "muted": muted,
            "linked": len(targets) == 1,
            #
            # Von Natur aus stereo: Dann laesst sich nichts koppeln
            # und es darf auch nicht danach gefragt werden.
            #
            "natural": is_natural_pair(family, channels, start),
        }

    def set_pair_fader(
        self, host: str, channels: int, start: int, db: float
    ) -> bool:
        """Setzt den Pegel beider Kanäle des Paars."""

        targets = self._pair_targets(host, channels, start)

        if not targets:
            return False

        return self._write(host, targets, "/mix/fader", db_to_fader(db))

    def set_pair_mute(
        self, host: str, channels: int, start: int, muted: bool
    ) -> bool:
        """Schaltet beide Kanäle des Paars stumm oder wieder an."""

        targets = self._pair_targets(host, channels, start)

        if not targets:
            return False

        return self._write(host, targets, "/mix/on", 0 if muted else 1)

    def set_link(
        self, host: str, channels: int, start: int, linked: bool
    ) -> bool:
        """
        Koppelt ein Kanalpaar am Pult oder hebt die Kopplung auf.

        Bei natürlichen Stereopaaren (X-Air 17+18) gibt es nichts zu
        koppeln - dort wird gar nicht erst gesendet.
        """

        family = self.detect(host)

        if family is None or self._port is None:
            return False

        if is_natural_pair(family, channels, start):
            return False

        erfolg = self._send(
            host,
            self._port,
            encode(f"/config/chlink/{start}-{start + 1}", 1 if linked else 0),
        )

        if erfolg:
            #
            # Gemerkten Zustand sofort nachziehen, sonst schickte der
            # naechste Reglerzug bis zu fuenf Sekunden lang noch an die
            # alte Adressliste.
            #
            self._pair_link[start] = (time.monotonic(), linked)
            self._linked = set()

        return erfolg

    def set_fader(self, host: str, channels: int, channel: int, db: float) -> bool:
        """
        Setzt den Fader eines Kanals (1-basiert) auf den angegebenen
        dB-Wert. `db` darf -inf sein (Fader zu).
        """

        family = self.detect(host)

        if family is None or self._port is None:
            return False

        addresses = channel_addresses(family, channels, self._linked)

        if not 1 <= channel <= len(addresses):
            return False

        return self._write(
            host,
            [addresses[channel - 1].address],
            "/mix/fader",
            db_to_fader(db),
        )

    def set_mute(
        self, host: str, channels: int, channel: int, muted: bool
    ) -> bool:
        """
        Schaltet einen Kanal stumm oder wieder an.

        Die Konsole kennt kein "mute", sondern "mix/on" - der Wert ist
        also umgekehrt: 0 heißt stumm, 1 heißt an.
        """

        family = self.detect(host)

        if family is None or self._port is None:
            return False

        addresses = channel_addresses(family, channels, self._linked)

        if not 1 <= channel <= len(addresses):
            return False

        return self._write(
            host,
            [addresses[channel - 1].address],
            "/mix/on",
            0 if muted else 1,
        )
