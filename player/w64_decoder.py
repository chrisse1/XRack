"""
XRacks eigene Wave64-Dateien für den Musikspieler.

Warum es diese Datei gibt - und warum nicht einfach ffmpeg:

Der Musikspieler dekodiert alles über ffmpeg (siehe
player/track_decoder.py), und genau das sollte auch für Übungsmixe
gelten: Er kann pausieren, spulen und die Position melden, der
Soundcheck-Spieler kann das alles nicht.

Nachgemessen an einer echten Datei liest ffmpeg unsere Wave64 aber
FALSCH. Der Kopf ist in Ordnung (WAVE_FORMAT_EXTENSIBLE,
32-Bit-Behälter, 24 gültige Bits, BlockAlign = Kanäle * 4) - ffmpeg
entscheidet sich trotzdem für `pcm_s24le` und liest drei Byte je Wert,
wo vier stehen. Aus zwei Sekunden werden dabei 2,67, jeder Kanal
landet auf dem falschen Platz, und zu hören wäre Rauschen.

Deshalb liest XRack seine eigenen Dateien selbst - mit dem Leser, der
das seit jeher tut (reader/w64_reader.py). Diese Klasse legt nur die
Form darüber, die der Musikspieler von einem Dekoder erwartet:
`open(path, channels, rate, start_position)`, `read(n)`, `close()`.

Die Kanalzahl und die Rate kommen dabei aus der DATEI, nicht vom
Aufrufer: Ein Übungsmix bringt mit, wie viele Spuren er hat.
"""

import logging

from pathlib import Path

from reader.w64_reader import W64Reader


#
# Diese Endungen liest XRack selbst.
#
EIGENE_ENDUNGEN = (".w64",)


def liest_xrack_selbst(pfad: Path) -> bool:
    """Ist das eine Datei, die XRack selbst liest?"""

    return Path(pfad).suffix.lower() in EIGENE_ENDUNGEN


def eckdaten(pfad: Path) -> dict:
    """
    Kanalzahl, Rate und Länge einer Wave64-Datei - ohne sie zu
    dekodieren.

    Das Gegenstück zu probe_duration()/probe_tags() aus
    player/track_decoder.py, nur ohne ffprobe: Der Kopf der Datei sagt
    es selbst, und schneller.
    """

    leser = W64Reader()

    try:
        leser.open(pfad)

        return {
            "channels": leser.channels,
            "rate": leser.sample_rate,
            "duration": leser.duration,
        }

    except (OSError, ValueError):
        return {"channels": 0, "rate": 0, "duration": 0.0}

    finally:
        leser.close()


class W64Decoder:
    """
    Ein Dekoder im Sinne des Musikspielers, der XRacks eigene Dateien
    liest.

    Er hält sich bewusst an dieselben drei Methoden wie TrackDecoder -
    der Musikspieler soll nicht wissen müssen, woher seine Blöcke
    kommen.
    """

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        self.reader = W64Reader()

        self._offen = False

    @property
    def running(self) -> bool:
        """Wie beim TrackDecoder: Läuft gerade eine Quelle?"""

        return self._offen

    @property
    def channels(self) -> int:
        return self.reader.channels

    @property
    def sample_rate(self) -> int:
        return self.reader.sample_rate

    def open(
        self,
        path: Path,
        channels: int,
        rate: int,
        start_position: float = 0.0,
    ) -> bool:
        """
        Öffnet die Datei und springt gegebenenfalls an eine Stelle.

        `channels` und `rate` nimmt diese Klasse entgegen, um zum
        TrackDecoder zu passen - maßgeblich ist aber, was in der Datei
        steht. Eine Umrechnung findet nicht statt: Ein Übungsmix wird
        so ausgegeben, wie er aufgenommen wurde.
        """

        self.close()

        try:
            self.reader.open(path)

        except (OSError, ValueError) as exc:

            self.logger.error(
                "Wave64-Datei konnte nicht geöffnet werden: %s (%s)",
                path,
                exc,
            )

            return False

        self._offen = True

        if start_position > 0:
            self.reader.seek(start_position)

        if rate and self.reader.sample_rate != rate:
            #
            # Kein Grund abzubrechen - das Interface laeuft ohnehin
            # mit der Rate des Pults. Es waere aber zu schnell oder zu
            # langsam, und das soll nicht stillschweigend passieren.
            #
            self.logger.warning(
                "Übungsmix läuft mit %d Hz, das Interface mit %d Hz - "
                "die Wiedergabe wäre zu %s.",
                self.reader.sample_rate,
                rate,
                "schnell" if self.reader.sample_rate < rate else "langsam",
            )

        return True

    def read(self, chunk_size: int) -> bytes | None:
        """Liefert None am Ende der Datei - wie der TrackDecoder."""

        if not self._offen:
            return None

        return self.reader.read(chunk_size)

    def close(self) -> None:

        if self._offen:
            self.reader.close()

        self._offen = False
