"""
XRack Recorder.
"""

import logging
import threading

from audio.audio_backend import AudioBackend
from recorder.level_meter import LevelMeter
from writer.audio_writer import AudioWriter
from writer.w64_writer import W64Writer
from time import monotonic
from pathlib import Path

class Recorder:
    """
    Verwaltet Audioaufnahmen und die reine Pegelmessung.

    Beide teilen sich denselben Aufnahme-Thread (ALSA erlaubt kein
    gleichzeitiges Lesen von zwei Stellen aus): "Pegel testen"
    startet den Thread ohne in eine Datei zu schreiben, eine echte
    Aufnahme schaltet das Schreiben zusätzlich dazu - nahtlos, ohne
    den Thread neu zu starten, falls bereits pegelgeprüft wird.

    Seit der Lichtsteuerung gibt es einen dritten Interessenten an
    demselben Strom: Die musikgesteuerte Show muss mithören, auch
    wenn niemand aufnimmt oder Pegel prüft. Deshalb merkt sich der
    Recorder nicht mehr nur "läuft ja/nein", sondern WER ihn braucht.
    Der Thread läuft, solange mindestens einer ihn braucht, und hört
    auf, wenn der letzte geht. Ein einzelnes Flag hätte hier
    zwangsläufig einen Fall falsch entschieden - etwa "Pegelprüfung
    beenden" mitten in einer laufenden Lichtshow.
    """

    #
    # Die Gruende, aus denen der Aufnahme-Thread laufen kann.
    #
    GRUND_PEGEL = "pegel"
    GRUND_AUFNAHME = "aufnahme"
    GRUND_LICHT = "licht"

    def __init__(
        self,
        backend: AudioBackend,
    ):

        self.logger = logging.getLogger(
            "XRack"
        )

        self.backend = backend

        self._active = False

        self._gruende: set[str] = set()

        #
        # Wer sonst noch jeden gelesenen Block sehen will (derzeit die
        # Lichtsteuerung). Was hier haengt, laeuft IM Lesethread und
        # muss deshalb sehr kurz sein - siehe _worker().
        #
        self._verbraucher: list = []

        self._write_to_file = False

        self._thread: threading.Thread | None = None

        self.writer: AudioWriter = W64Writer()

        self.meter: LevelMeter | None = None

        self._buffer_count = 0

        self._bytes_written = 0

        self._start_time = None

        self._current_filename = ""

        self._last_duration = 0.0

    @property
    def recording(self) -> bool:
        """
        True während einer echten Aufnahme (Datei wird geschrieben).
        """

        return self._active and self._write_to_file

    @property
    def monitoring(self) -> bool:
        """
        True bei Pegelprüfung oder Aufnahme.

        Bewusst NICHT "der Thread läuft": Hält ihn allein die
        Lichtsteuerung am Leben, prüft niemand Pegel - und die
        Oberfläche darf dann auch nicht behaupten, es liefe eine
        Pegelprüfung.
        """

        return bool(
            self._gruende & {self.GRUND_PEGEL, self.GRUND_AUFNAHME}
        )

    @property
    def stream_active(self) -> bool:
        """True, wenn überhaupt vom Interface gelesen wird."""

        return self._active

    @property
    def levels(self) -> list[float]:
        """
        Aktuelle Pegel je Kanal (0.0 - 1.0+, leer wenn inaktiv).
        """

        if self.meter is None:
            return []

        return self.meter.levels

    def start(self, name_prefix: str = "Soundcheck") -> bool:
        """
        Startet die Aufnahme. Läuft bereits eine reine
        Pegelprüfung, wird sie nahtlos zur Aufnahme erweitert.
        `name_prefix` bestimmt den Dateinamen ("<Präfix>-<Nummer>").
        """

        if self.recording:
            return False

        self._buffer_count = 0
        self._bytes_written = 0
        self._start_time = monotonic()

        self.writer.open(
            channels=self.backend.channels,
            sample_rate=self.backend.rate,
            bits_per_sample=24,
            name_prefix=name_prefix,
        )

        self._current_filename = self.writer.filename

        self._write_to_file = True

        self.logger.info(
            "Aufnahmedatei: %s",
            self._current_filename,
        )

        self._ensure_thread_running(self.GRUND_AUFNAHME)

        self.logger.info(
            "Recorder gestartet."
        )

        return True

    def stop(self) -> None:
        """
        Stoppt die Aufnahme (und damit auch die Pegelmessung
        vollständig).
        """

        if not self.recording:
            return

        #
        # Dauer der Aufnahme merken
        #
        if self._start_time is not None:
            self._last_duration = (
                monotonic() - self._start_time
            )

        self._start_time = None

        #
        # Beide Gruende abmelden, nicht nur die Aufnahme: "Stop" im
        # Recorder beendet auch eine Pegelpruefung, die vorher lief -
        # so war es immer, und daran soll sich nichts aendern. Nur
        # die Lichtsteuerung behaelt den Strom, falls sie ihn hat.
        #
        self._stop_thread(self.GRUND_AUFNAHME)
        self._stop_thread(self.GRUND_PEGEL)

        self.writer.close()

        self.logger.info(
            "Recorder gestoppt."
        )

    def start_monitoring(self) -> bool:
        """
        Startet die reine Pegelprüfung, ohne aufzuzeichnen.
        """

        #
        # Waehrend einer Aufnahme oder einer laufenden Pegelpruefung
        # gibt es nichts zu starten. Haelt dagegen nur die
        # Lichtsteuerung den Strom offen, darf die Pegelpruefung
        # dazukommen - fruehere Fassungen haben hier auf "Thread
        # laeuft" geprueft und haetten das verweigert.
        #
        if self.monitoring:
            return False

        self._write_to_file = False

        self._ensure_thread_running(self.GRUND_PEGEL)

        self.logger.info(
            "Pegelprüfung gestartet."
        )

        return True

    def stop_monitoring(self) -> None:
        """
        Stoppt die reine Pegelprüfung (nicht während einer echten
        Aufnahme aufrufen - dafür ist stop() da).
        """

        if self.GRUND_PEGEL not in self._gruende or self._write_to_file:
            return

        self._stop_thread(self.GRUND_PEGEL)

        self.logger.info(
            "Pegelprüfung gestoppt."
        )

    # ----------------------------------------------------------------
    # Mithoeren fuer die Lichtsteuerung
    # ----------------------------------------------------------------

    def start_analysis(self) -> None:
        """
        Den Strom offen halten, ohne aufzunehmen oder Pegel zu
        zeigen - fuer die musikgesteuerte Lichtshow.
        """

        self._ensure_thread_running(self.GRUND_LICHT)

    def stop_analysis(self) -> None:
        """Das Mithoeren wieder abmelden."""

        self._stop_thread(self.GRUND_LICHT)

    def add_consumer(self, verbraucher) -> None:
        """
        Einen Mithoerer anmelden, der jeden gelesenen Block bekommt.

        Achtung: Er laeuft IM Lesethread. Alles, was dort laenger
        dauert, verzoegert das naechste Lesen von ALSA und riskiert
        einen Ueberlauf - also verlorene Audiodaten mitten in einer
        Aufnahme. Wer hier etwas anmeldet, darf nur weiterreichen,
        nicht rechnen.
        """

        if verbraucher not in self._verbraucher:
            self._verbraucher.append(verbraucher)

    def remove_consumer(self, verbraucher) -> None:

        if verbraucher in self._verbraucher:
            self._verbraucher.remove(verbraucher)

    def _ensure_thread_running(self, grund: str) -> None:

        self._gruende.add(grund)

        if self._active:
            return

        self.meter = LevelMeter(
            channels=self.backend.channels
        )

        self._active = True

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
        )

        self._thread.start()

    def _stop_thread(self, grund: str) -> None:
        """
        Einen Grund abmelden. Erst wenn keiner mehr uebrig ist, wird
        wirklich aufgehoert.
        """

        self._gruende.discard(grund)

        if grund == self.GRUND_AUFNAHME:
            self._write_to_file = False

        #
        # Braucht noch jemand den Strom, laeuft er weiter.
        #
        if self._gruende:
            return

        self._active = False

        self._write_to_file = False

        if self._thread is not None:

            self._thread.join()

            self._thread = None

        self.meter = None

    def _worker(self) -> None:
        """
        Hauptschleife: liest kontinuierlich vom Audio-Interface,
        aktualisiert die Pegel und schreibt bei aktiver Aufnahme
        zusätzlich in die Datei.
        """

        self.logger.info(
            "Recorder-Thread gestartet."
        )

        while self._active:

            try:
                data = self.backend.read()
            except Exception as exc:
                #
                # Ohne diesen Fang würde eine unerwartete ALSA-
                # Ausnahme (z.B. ein kurzer "No such device"-Aussetzer,
                # wie er durch eine gleichzeitige Geräteabfrage per
                # arecord bei manchen USB-Interfaces auftreten kann)
                # den Thread abstürzen lassen, OHNE self._active auf
                # False zurückzusetzen - monitoring/recording blieben
                # dann für immer "True" hängen und blockierten jede
                # weitere Aufnahme/Pegelprüfung/Samplerate-Prüfung bis
                # zum nächsten Neustart von XRack.
                #
                self.logger.error(
                    "Recorder-Thread: Lesefehler vom Audio-Interface, "
                    "wird beendet: %s",
                    exc,
                )
                self._active = False

                #
                # Die Gruende muessen mit weg.
                #
                # Ohne das bleibt "pegel"/"licht" stehen, obwohl der
                # Thread tot ist: monitoring meldet weiter True, die
                # Lichtshow haelt sich fuer laufend, und niemand
                # bekommt gesagt, dass keine Bloecke mehr kommen. Es
                # sieht aus, als sei das Programm einmal gelaufen und
                # habe dann aufgehoert - genau so.
                #
                self._gruende.clear()

                self._write_to_file = False
                self.meter = None
                if self.writer is not None:
                    self.writer.close()
                break

            if data is None:

                continue

            if self.meter is not None:
                self.meter.update(data)

            #
            # Mithoerer bedienen. Wirft einer, wird er abgemeldet
            # statt den Thread mitzureissen: Eine kaputte Lichtshow
            # darf keine laufende Aufnahme beenden.
            #
            for verbraucher in list(self._verbraucher):

                try:
                    verbraucher(data)

                except Exception as exc:

                    self.logger.error(
                        "Recorder: Mithoerer wirft, wird abgemeldet: %s", exc
                    )

                    self.remove_consumer(verbraucher)

            if not self._write_to_file:
                continue

            self.writer.write(data)

            self._buffer_count += 1

            self._bytes_written += len(data)

            if self._buffer_count % 100 == 0:

                self.logger.info(
                    "Recorder: %d Buffer | %.2f MB",
                    self._buffer_count,
                    self.mb_written,
                )

    @property
    def buffer_count(self) -> int:
        return self._buffer_count

    @property
    def bytes_written(self) -> int:
        return self._bytes_written
        
    @property
    def duration(self) -> float:
        """
        Dauer der aktuellen bzw. letzten Aufnahme.
        """

        if self.recording:
            return monotonic() - self._start_time

        return self._last_duration
        
    @property
    def mb_written(self) -> float:

        return self._bytes_written / 1024 / 1024



    @property
    def current_filename(self) -> str:
        """
        Name der aktuell aufgenommenen bzw. zuletzt aufgenommenen Datei.
        """

        return self._current_filename
        
    @property
    def recordings(self) -> list[str]:
        """
        Liefert alle vorhandenen Aufnahmen.
        """

        recording_path = Path("recordings")

        if not recording_path.exists():
            return []

        return sorted(
            [
                file.name
                for file in recording_path.glob("*.w64")
            ],
            reverse=True,
        )
