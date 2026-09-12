"""
Übungsmix und Mitschnitt in EINEM Wiedergabestrom.

Warum es das gibt: Beim Üben will man den eigenen Versuch gegen den
Mix hören. Das Interface gibt aber nur EINEN Strom her - zwei
Wiedergaben gleichzeitig kann es nicht (deshalb schließen sich Musik
und Soundcheck seit jeher aus).

Nichts hindert XRack jedoch daran, in diesen einen Strom ZWEI Dateien
zu legen: den Übungsmix auf seine Kanäle, den Mitschnitt auf seine.
Genau das tut diese Klasse.

Warum nicht stattdessen eine neue Datei schreiben: Eine Wave64 ist
verschachtelt gespeichert - Rahmen für Rahmen stehen die Kanäle
nebeneinander. Eine zusätzliche Spur verbreitert JEDEN Rahmen, die
Datei müsste also vollständig neu geschrieben werden. Eine Stunde
Übungsmix mit acht Kanälen sind 5,5 GB; für zwei zusätzliche Spuren
wären 5,5 GB zu lesen und 6,9 GB zu schreiben. Für "mal eben den
letzten Versuch anhören" ist das der falsche Weg.

Die Ausgabe hat die volle Kanalzahl des Interfaces. Das ist Absicht:
Damit ist der ChannelInserter im Backend ein Durchreicher (siehe
audio/channel_inserter.py), und es bleibt bei EINER Schleife über die
Rahmen statt zweien. Auf dem Pi ist das der heißeste Punkt im
Lesethread.

Nach außen sieht die Klasse aus wie jeder andere Dekoder des
Musikspielers: open(path, channels, rate, start_position), read(n),
close().
"""

import logging

from pathlib import Path

from reader.w64_reader import W64Reader


BYTES_PER_SAMPLE = 4


class Quelle:
    """Eine Datei und der Kanal, ab dem sie ausgegeben wird."""

    def __init__(self, pfad: Path, start_channel: int):

        self.pfad = Path(pfad)

        #
        # 0-basiert, wie ueberall unterhalb der Oberflaeche.
        #
        self.start_channel = start_channel

        self.leser = W64Reader()

        self.kanaele = 0

        self.rahmen_bytes = 0

        self.byte_versatz = 0

        #
        # Ist diese Quelle zu Ende? Der Mitschnitt darf kuerzer sein
        # als der Mix - dann ist es ab dort still, und der Mix laeuft
        # weiter.
        #
        self.zuende = False


class UebenDecoder:
    """
    Legt eine oder zwei Wave64-Dateien in einen Strom vollständiger
    Interface-Rahmen.

    Gelesen wird mit XRacks eigenem Leser, nicht mit ffmpeg - das
    liest unsere Wave64 falsch (ausführlich in player/w64_decoder.py).
    """

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        self.quellen: list[Quelle] = []

        self.breite = 0

        self._start_channel = 0

        self._mitschnitt: Path | None = None

        self._mitschnitt_start = 0

        self._offen = False

    @property
    def running(self) -> bool:
        """Wie beim TrackDecoder: Läuft gerade eine Quelle?"""

        return self._offen

    @property
    def channels(self) -> int:
        return self.breite

    def einrichten(
        self,
        breite: int,
        start_channel: int,
        mitschnitt: Path | None = None,
        mitschnitt_start: int = 0,
    ) -> None:
        """
        Sagt, wie breit die Ausgabe ist und wo die Quellen liegen.

        Getrennt von open(), weil der Musikspieler den Dekoder mit
        genau drei Methoden bedient - die Angaben zur zweiten Quelle
        passen in keine davon.
        """

        self.breite = breite

        self._start_channel = start_channel

        self._mitschnitt = Path(mitschnitt) if mitschnitt else None

        self._mitschnitt_start = mitschnitt_start

    def passt(self, pfad: Path) -> bool:
        """
        Passen beide Quellen in die Breite?

        Gefragt wird VOR dem Abspielen: Eine Quelle, die über den Rand
        ragt, würde entweder abgeschnitten (halbes Stereopaar) oder
        in den nächsten Rahmen schreiben - dann wäre nicht eine Spur
        still, sondern alles verschoben.
        """

        for quelle, start in self._gewuenschte_quellen(pfad):

            kanaele = self._kanaele_von(quelle)

            if not kanaele:
                return False

            if start < 0 or start + kanaele > self.breite:

                self.logger.error(
                    "%s braucht die Kanäle %d-%d, das Interface hat %d.",
                    Path(quelle).name,
                    start + 1,
                    start + kanaele,
                    self.breite,
                )

                return False

        return True

    def open(
        self,
        path: Path,
        channels: int,
        rate: int,
        start_position: float = 0.0,
    ) -> bool:
        """
        Öffnet beide Quellen und springt an dieselbe Stelle.

        Dieselbe Stelle für beide: Mitschnitt und Mix wurden zusammen
        gestartet (siehe Application.start_practice), sie laufen also
        von Anfang an synchron.
        """

        self.close()

        self.quellen = []

        for datei, start in self._gewuenschte_quellen(path):

            quelle = Quelle(datei, start)

            try:
                quelle.leser.open(datei)

            except (OSError, ValueError) as exc:

                self.logger.error(
                    "Wave64-Datei konnte nicht geöffnet werden: %s (%s)",
                    datei,
                    exc,
                )

                self.close()

                return False

            quelle.kanaele = quelle.leser.channels

            quelle.rahmen_bytes = quelle.leser.frame_bytes

            quelle.byte_versatz = quelle.start_channel * BYTES_PER_SAMPLE

            if start_position > 0:
                quelle.leser.seek(start_position)

            self.quellen.append(quelle)

        if not self.quellen:
            return False

        self._offen = True

        return True

    def read(self, chunk_size: int) -> bytes | None:
        """
        Liefert einen Block fertiger Interface-Rahmen.

        None, sobald der ÜBUNGSMIX zu Ende ist - er gibt die Länge
        vor. Ein kürzerer Mitschnitt wird ab seinem Ende still, ein
        längerer endet mit dem Mix: Man übt zum Stück, nicht umgekehrt.
        """

        if not self._offen or not self.quellen:
            return None

        aus_rahmen = self.breite * BYTES_PER_SAMPLE

        rahmen = chunk_size // aus_rahmen

        if rahmen <= 0:
            return None

        blöcke = []

        for quelle in self.quellen:

            daten = (
                None
                if quelle.zuende
                else quelle.leser.read(rahmen * quelle.rahmen_bytes)
            )

            if not daten:
                quelle.zuende = True
                daten = b""

            blöcke.append(daten)

        #
        # Die erste Quelle ist der Mix. Ist er zu Ende, ist das Stueck
        # zu Ende - alles andere waere ein Nachspiel aus einem
        # Mitschnitt, den niemand hoeren will.
        #
        if not blöcke[0]:
            return None

        #
        # Nur so viele Rahmen, wie der Mix wirklich geliefert hat.
        #
        rahmen = min(rahmen, len(blöcke[0]) // self.quellen[0].rahmen_bytes)

        if rahmen <= 0:
            return None

        #
        # bytearray ist mit Nullen gefuellt - alle nicht belegten
        # Kanaele sind damit still, ohne dass etwas geschrieben wird.
        #
        aus = bytearray(rahmen * aus_rahmen)

        for quelle, daten in zip(self.quellen, blöcke):

            if not daten:
                continue

            quell_rahmen = quelle.rahmen_bytes

            #
            # Der Mitschnitt kann mitten im Block enden. Dann wird nur
            # so weit eingesetzt, wie Daten da sind - der Rest bleibt
            # still.
            #
            vorhanden = min(rahmen, len(daten) // quell_rahmen)

            versatz = quelle.byte_versatz

            for nummer in range(vorhanden):

                ziel = nummer * aus_rahmen + versatz
                quell = nummer * quell_rahmen

                aus[ziel:ziel + quell_rahmen] = (
                    daten[quell:quell + quell_rahmen]
                )

        return bytes(aus)

    def close(self) -> None:

        for quelle in self.quellen:
            quelle.leser.close()

        self.quellen = []

        self._offen = False

    # ----------------------------------------------------------------
    # Innereien
    # ----------------------------------------------------------------

    def _gewuenschte_quellen(self, pfad: Path) -> list[tuple[Path, int]]:
        """Der Mix zuerst, dann - wenn gewählt - der Mitschnitt."""

        quellen = [(Path(pfad), self._start_channel)]

        if self._mitschnitt is not None:
            quellen.append((self._mitschnitt, self._mitschnitt_start))

        return quellen

    def _kanaele_von(self, pfad: Path) -> int:
        """Wie viele Kanäle die Datei hat - aus ihrem Kopf."""

        leser = W64Reader()

        try:
            leser.open(pfad)
            return leser.channels

        except (OSError, ValueError):
            return 0

        finally:
            leser.close()
