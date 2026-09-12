"""
XRack Recorder.
"""

import logging
import shutil
import threading

from audio.audio_backend import AudioBackend
from recorder.level_meter import LevelMeter
from recorder.rate_check import RateCheck, BYTES_JE_WERT
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

    #
    # Der Speicherplatz.
    #
    # Am X32 schreibt XRack rund 22 GB je Stunde (32 Kanaele, 4 Byte,
    # 48 kHz) - eine Karte ist da schneller voll, als man denkt.
    # Laeuft sie waehrend einer Aufnahme wirklich voll, bricht das
    # Schreiben mitten drin ab, und der Dateikopf bekommt seine
    # Groessen nicht mehr nachgetragen: unlesbar statt kurz.
    #
    # Deshalb wird vorher aufgehoert. Eine beendete Aufnahme ist zu
    # retten, eine abgebrochene nicht.
    #
    PLATZ_WARNUNG_S = 15 * 60.0
    PLATZ_STOPP_S = 30.0

    #
    # So oft wird nachgesehen. Je Block waere Unfug - das sind
    # fuenfzig Mal in der Sekunde, und der freie Platz aendert sich
    # nicht so schnell.
    #
    PLATZ_INTERVALL_S = 2.0

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

        #
        # Misst die tatsaechliche Samplerate mit (siehe
        # recorder/rate_check.py).
        #
        self.rate_check: RateCheck | None = None

        #
        # Wie lange der freie Platz noch reicht, in Sekunden. Wird
        # waehrend der Aufnahme fortgeschrieben.
        #
        self.restzeit = 0.0

        #
        # Wurde die Aufnahme wegen Speichermangels beendet? Die
        # Anwendung sieht das in ihrem Statuslauf und raeumt dann
        # richtig auf - der Lesethread darf sich nicht selbst
        # anhalten (er wuerde auf sich selbst warten).
        #
        self.platz_stopp = False

        self._platz_geprueft = 0.0

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
    def bereit(self) -> bool:
        """
        Ist ein Strom offen, aus dem gelesen werden kann?

        Gefragt wird nach dem PCM-Handle, nicht nach der Geräteliste:
        Der Recorder liest aus dem Handle. Ein Gerät kann gewählt
        sein, während das Öffnen gescheitert ist (siehe
        audio/audio_backend.py) - dann ist nichts zu holen, obwohl
        oben ein Gerätename steht.

        Ohne diese Frage lief Folgendes: Der Lesethread startete,
        read() lieferte sofort None, die Schleife drehte leer bei
        voller Last, und im Aufnahmeverzeichnis lag eine Datei mit
        einem Kopf über 0 Kanäle und 0 Hz - während die Oberfläche
        "nimmt auf" meldete.
        """

        return self.backend.opened

    @property
    def levels(self) -> list[float]:
        """
        Aktuelle Pegel je Kanal (0.0 - 1.0+, leer wenn inaktiv).
        """

        if self.meter is None:
            return []

        return self.meter.levels

    def start(self, name_prefix: str = "Soundcheck",
              trenner: str = "-") -> bool:
        """
        Startet die Aufnahme. Läuft bereits eine reine
        Pegelprüfung, wird sie nahtlos zur Aufnahme erweitert.
        `name_prefix` bestimmt den Dateinamen ("<Präfix>-<Nummer>").

        `trenner` steht zwischen Präfix und Nummer. Für Mitschnitte
        beim Üben ist er leer - dort trägt das Präfix schon einen
        Bindestrich ("Umbrella-1-Take" + "1"), siehe
        core/recording_kind.py.
        """

        if self.recording:
            return False

        #
        # Ohne offenen Strom gibt es nichts aufzunehmen. Die Prüfung
        # steht VOR dem Öffnen der Datei - sonst läge die unbrauchbare
        # Aufnahme schon im Verzeichnis, mit Nummer und Eintrag in der
        # Liste.
        #
        if not self.bereit:

            self.logger.warning(
                "Aufnahme nicht gestartet: Es ist kein Audiogerät "
                "geöffnet."
            )

            return False

        #
        # Gar nicht erst anfangen, wenn der Platz schon jetzt nicht
        # reicht: Eine Datei, die im selben Atemzug wieder
        # geschlossen wird, hilft niemandem - und im
        # Aufnahmeverzeichnis laege eine leere Aufnahme mehr.
        #
        rest = self.platz_restzeit()

        if 0.0 < rest <= self.PLATZ_STOPP_S:

            self.logger.warning(
                "Aufnahme nicht gestartet: Der Speicher reicht nur noch "
                "fuer %.0f Sekunden.",
                rest,
            )

            self.restzeit = rest
            self.platz_stopp = True

            return False

        self._buffer_count = 0
        self._bytes_written = 0
        self._start_time = monotonic()

        #
        # Ein neuer Anlauf: Der Grund der letzten Bremse gilt nicht
        # mehr, und der Platz wird sofort neu geprueft.
        #
        self.platz_stopp = False
        self._platz_geprueft = 0.0

        #
        # Der erste aufgenommene Kanal wandert in den Dateinamen: Ohne
        # ihn landet die Aufnahme beim virtuellen Soundcheck wieder auf
        # Kanal 1, also auf den falschen Wegen des Pults (siehe
        # core/recording_kind.py).
        #
        self.writer.open(
            channels=self.backend.channels,
            sample_rate=self.backend.rate,
            bits_per_sample=24,
            name_prefix=name_prefix,
            start_channel=getattr(self.backend, "start_channel", 0) + 1,
            trenner=trenner,
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

    def _abmelden(self) -> None:
        """
        Die Aufnahme aus den Gruenden austragen und die Dauer merken.

        Steht getrennt, weil es zwei Wege hierher gibt: den Knopf
        (stop) und die Speicherbremse (platz_aufraeumen). Beide
        muessen dasselbe tun, sonst bliebe nach der Bremse ein
        Lesethread stehen, den niemand mehr braucht.
        """

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

    def stop(self) -> None:
        """
        Stoppt die Aufnahme (und damit auch die Pegelmessung
        vollständig).
        """

        if not self.recording:
            return

        self._abmelden()

        self.writer.close()

        self.logger.info(
            "Recorder gestoppt."
        )

    def platz_aufraeumen(self) -> bool:
        """
        Nach der Speicherbremse ordentlich abmelden.

        Der Lesethread hat das Schreiben beendet und die Datei
        geschlossen - abmelden darf er sich aber nicht selbst, er
        wuerde auf sich selbst warten. Das erledigt die Anwendung in
        ihrem Statuslauf.

        Liefert True, wenn wirklich etwas aufzuraeumen war.
        """

        if not self.platz_stopp:
            return False

        self._abmelden()

        self.logger.warning(
            "Recorder wegen Speichermangels beendet: %s",
            self._current_filename,
        )

        return True

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

        #
        # Ohne offenen Strom bliebe die Anzeige leer, während der
        # Lesethread leer dreht.
        #
        if not self.bereit:

            self.logger.warning(
                "Pegelprüfung nicht gestartet: Es ist kein Audiogerät "
                "geöffnet."
            )

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

    def start_analysis(self) -> bool:
        """
        Den Strom offen halten, ohne aufzunehmen oder Pegel zu
        zeigen - fuer die musikgesteuerte Lichtshow.

        Liefert False, wenn kein Gerät offen ist. Der Aufrufer muss
        das auswerten: Eine Show, die nie einen Block sieht, stünde
        sonst als "läuft" da.
        """

        if not self.bereit:

            self.logger.warning(
                "Mithören nicht gestartet: Es ist kein Audiogerät "
                "geöffnet."
            )

            return False

        self._ensure_thread_running(self.GRUND_LICHT)

        return True

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

    # ----------------------------------------------------------------
    # Speicherplatz
    # ----------------------------------------------------------------

    def datenrate(self) -> int:
        """
        Wie viele Byte je Sekunde eine Aufnahme schreibt.

        Gerechnet wird mit der AUFNAHMEbreite, nicht mit der des
        Interfaces: Geschrieben wird nur, was aufgenommen werden soll
        (siehe _worker).
        """

        return self.backend.channels * BYTES_JE_WERT * self.backend.rate

    def freier_platz(self) -> int:
        """Freier Platz im Aufnahmeverzeichnis, in Byte."""

        ordner = getattr(self.writer, "directory", None)

        if ordner is None:
            return 0

        #
        # Das Verzeichnis wird erst beim Oeffnen der Datei angelegt.
        # Vorher zaehlt der naechste vorhandene Elternordner - er
        # liegt auf demselben Dateisystem.
        #
        pfad = ordner

        while not pfad.exists() and pfad != pfad.parent:
            pfad = pfad.parent

        try:
            return shutil.disk_usage(pfad).free
        except OSError:
            return 0

    def platz_restzeit(self) -> float:
        """
        Wie lange der freie Platz noch reicht, in Sekunden.

        0.0, wenn es nichts zu rechnen gibt (kein offenes Geraet).
        """

        rate = self.datenrate()

        if rate <= 0:
            return 0.0

        return self.freier_platz() / rate

    def _platz_pruefen(self, jetzt: float) -> None:
        """
        Waehrend der Aufnahme den Platz im Auge behalten - laeuft im
        Lesethread und muss deshalb kurz sein.
        """

        if jetzt - self._platz_geprueft < self.PLATZ_INTERVALL_S:
            return

        self._platz_geprueft = jetzt

        self.restzeit = self.platz_restzeit()

        if not self._write_to_file:
            return

        if self.restzeit > self.PLATZ_STOPP_S:
            return

        #
        # Schluss - aber ordentlich: Datei schliessen, damit der Kopf
        # seine Groessen bekommt. Das Abmelden erledigt die Anwendung
        # (siehe platz_stopp), denn dieser Faden darf sich nicht
        # selbst anhalten.
        #
        self.logger.warning(
            "Recorder: Speicher fast voll (%.0f s Rest) - Aufnahme wird "
            "beendet.",
            self.restzeit,
        )

        self._write_to_file = False

        self.writer.close()

        self.platz_stopp = True

    def _ensure_thread_running(self, grund: str) -> None:

        self._gruende.add(grund)

        if self._active:
            return

        self.meter = LevelMeter(
            channels=self.backend.channels
        )

        #
        # Gemessen wird am ungeschnittenen Strom - dort steht die
        # Rahmenbreite des Interfaces, und nur mit ihr geht die
        # Rechnung auf.
        #
        self.rate_check = RateCheck(
            channels=self.backend.native_channels or self.backend.channels,
            erwartet=self.backend.rate,
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

            #
            # Zwei Sichten auf denselben Block:
            #
            #   data          alle Kanaele, die das Interface liefert
            #   aufnahme      nur die, die aufgenommen werden sollen
            #
            # Datei und Pegelanzeige bekommen den Schnitt - dort ist
            # er die Absicht des Nutzers. Die Mithoerer bekommen den
            # vollen Strom: Die Lichtshow soll auf einen Kanal hoeren
            # duerfen, den niemand aufnimmt (ein AUX-Weg fuers Licht
            # etwa), und auf einem X32 sind das die Kanaele jenseits
            # der 18, die XRack als Vorgabe aufnimmt.
            #
            aufnahme = self.backend.aufnahmebreite(data)

            jetzt = monotonic()

            if self.rate_check is not None:
                self.rate_check.block(len(data), jetzt)

            self._platz_pruefen(jetzt)

            if self.meter is not None:
                self.meter.update(aufnahme)

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

            self.writer.write(aufnahme)

            self._buffer_count += 1

            #
            # Gezaehlt wird, was WIRKLICH in der Datei landet. Seit
            # der Lesethread den vollen Strom bekommt (siehe oben),
            # waere len(data) zu viel: Bei 18 von 32 Kanaelen haette
            # die Anzeige fast das Doppelte gemeldet - und die
            # Restzeit-Rechnung haette dazu nicht gepasst.
            #
            self._bytes_written += len(aufnahme)

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
