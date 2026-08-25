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
MAX_DB = 10.0


def pad(data: bytes) -> bytes:
    """
    Füllt auf ein Vielfaches von 4 Byte auf - OSC verlangt das für
    Strings und Blobs.
    """

    return data + b"\x00" * (4 - len(data) % 4)


def encode(address: str, *arguments) -> bytes:
    """
    Baut eine OSC-Nachricht. Unterstützt Float und String als Argumente
    - mehr braucht es für Fader und Kanalnamen nicht.
    """

    message = pad(address.encode("ascii") + b"\x00")

    tags = ","
    values = b""

    for argument in arguments:

        if isinstance(argument, float):
            tags += "f"
            values += struct.pack(">f", argument)

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


def channel_addresses(family: str, channels: int) -> list[tuple[str, str]]:
    """
    Liefert (OSC-Adresse, Beschriftung) der Eingangskanäle.

    Die Adressen bilden die Kanalzahl des Audiointerfaces *nicht*
    durchgehend ab: Beim X32 sind es echte /ch/01 bis /ch/32, die
    X-Air-Serie hat dagegen nur 16 Mono-Kanäle plus ein Aux-Rückweg-Paar
    mit eigener Adresse. Ein XR18 mit 18 USB-Kanälen ergibt dort also
    17 Regler, weil der Aux-Rückweg ein Stereopaar mit einem
    gemeinsamen Fader ist - er wird als "17+18" beschriftet. Darum eine
    ausdrückliche Liste statt einer Formel: So steht dieser Unterschied
    an genau einer Stelle und ist am Pult leicht zu korrigieren.
    """

    if family == FAMILY_XAIR:

        result = [
            (f"/ch/{index:02d}", str(index))
            for index in range(1, min(channels, 16) + 1)
        ]

        if channels >= 18:
            result.append(("/rtn/aux", "17+18"))

        return result

    return [
        (f"/ch/{index:02d}", str(index))
        for index in range(1, min(channels, 32) + 1)
    ]


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

        return None

    def get_channels(self, host: str, channels: int) -> list[dict] | None:
        """
        Liest Namen und Faderstellung aller Kanäle.

        Liefert None, wenn das Pult nicht antwortet - dann zeigt die
        Oberfläche einen Hinweis statt toter Regler.
        """

        family = self.detect(host)

        if family is None or self._port is None:
            return None

        result = []

        for index, (address, label) in enumerate(
            channel_addresses(family, channels), start=1
        ):

            name = ""
            db = MIN_DB

            #
            # Eine Anfrage ohne Argumente liefert den aktuellen Wert
            # zurück - so ist es bei der X-Serie vorgesehen.
            #
            answer = self._request(
                host, self._port, encode(f"{address}/mix/fader")
            )

            if answer is not None:

                _, arguments = decode(answer)

                if arguments and isinstance(arguments[0], float):
                    db = fader_to_db(arguments[0])

            answer = self._request(
                host, self._port, encode(f"{address}/config/name")
            )

            if answer is not None:

                _, arguments = decode(answer)

                if arguments and isinstance(arguments[0], str):
                    name = arguments[0].strip()

            result.append(
                {
                    "channel": index,
                    "label": label,
                    "name": name,
                    #
                    # None steht für "Fader zu" (-unendlich) - als JSON
                    # gibt es kein -inf.
                    #
                    "db": None if math.isinf(db) else round(db, 1),
                }
            )

        return result

    def set_fader(self, host: str, channels: int, channel: int, db: float) -> bool:
        """
        Setzt den Fader eines Kanals (1-basiert) auf den angegebenen
        dB-Wert. `db` darf -inf sein (Fader zu).
        """

        family = self.detect(host)

        if family is None or self._port is None:
            return False

        addresses = channel_addresses(family, channels)

        if not 1 <= channel <= len(addresses):
            return False

        address = addresses[channel - 1][0]

        return self._send(
            host,
            self._port,
            encode(f"{address}/mix/fader", db_to_fader(db)),
        )
