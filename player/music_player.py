"""
XRack Musikspieler.
"""

import logging
import threading
from pathlib import Path
from time import monotonic

import alsaaudio

from audio.audio_playback_backend import AudioPlaybackBackend
from audio.models import AudioDevice
from player.music_library import MusicLibrary
from player.track_decoder import TrackDecoder, probe_duration, probe_tags
from player.w64_decoder import (
    W64Decoder,
    eckdaten,
    liest_xrack_selbst,
)

CHANNELS = 2
CHUNK_FRAMES = 1024


class MusicPlayer:
    """
    Spielt Musikdateien auf frei wählbaren Kanälen ab - entweder
    einzeln oder als zufällig gemischte Endlosschleife über einen
    Ordner.
    """

    def __init__(
        self,
        backend: AudioPlaybackBackend,
        library: MusicLibrary,
    ):

        self.logger = logging.getLogger("XRack")

        self.backend = backend

        self.library = library

        self.decoder = TrackDecoder()

        #
        # XRacks eigene Dateien liest XRack selbst: ffmpeg liest unsere
        # Wave64 falsch (siehe player/w64_decoder.py). Welcher der
        # beiden gerade zustaendig ist, entscheidet _decoder_fuer().
        #
        self.eigener_decoder = W64Decoder()

        self._aktiver_decoder = self.decoder

        self._playing = False

        self._paused = False

        self._pause_event = threading.Event()
        self._pause_event.set()

        #
        # Eine Pause ist angefordert und vom Lesethread noch nicht
        # bearbeitet. Das ist etwas anderes als self._paused, und genau
        # daran hing ein Fehler - siehe _play_track().
        #
        self._pause_angefordert = False

        self._resume_position = 0.0

        self._thread: threading.Thread | None = None

        self._folder_mode = False

        #
        # Beim Ueben spielt man dieselbe Stelle immer wieder - dafuer
        # laeuft der Titel in der Schleife.
        #
        self._wiederholen = False

        self._playlist: list[Path] = []

        self._index = 0

        self._current_track = ""
        self._current_track_title = ""
        self._current_track_artist = ""

        self._skip_requested = False

        self._seek_target: float | None = None

        self._track_duration = 0.0
        self._track_offset = 0.0

        #
        # None heisst: Die Uhr des Titels laeuft noch nicht.
        #
        # Hier stand monotonic() - die Uhr lief also ab dem ERZEUGEN
        # des Spielers. Zwischen "Abspielen" und dem Moment, in dem der
        # Lesethread den Titel wirklich beginnt (und die Uhr neu
        # stellt), wurde deshalb die Laufzeit des Spielers als Position
        # gemeldet. Auf einem belasteten Pi sind das schnell
        # Zehntelsekunden, nach einer Stunde Betrieb eine Stunde: Wer
        # in diesem Moment pausiert, merkt sich eine Stelle, die es im
        # Stueck nicht gibt - und beim Fortsetzen ist der Titel zu
        # Ende, bevor er anfing.
        #
        self._track_start_time: float | None = None

        self._channels = CHANNELS
        self._start_channel = 0
        self._rate = 0

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def folder_mode(self) -> bool:
        return self._folder_mode

    @property
    def wiederholen(self) -> bool:
        """Laeuft der Titel in der Schleife?"""

        return self._wiederholen

    def set_wiederholen(self, an: bool) -> None:
        """
        Die Schleife waehrend der Wiedergabe ein- oder ausschalten.

        Wirkt am Ende des Titels - mitten im Stueck umzuschalten soll
        nichts abschneiden.
        """

        self._wiederholen = bool(an)

    @property
    def current_track(self) -> str:
        return self._current_track

    @property
    def current_track_title(self) -> str:
        return self._current_track_title

    @property
    def current_track_artist(self) -> str:
        return self._current_track_artist

    @property
    def channels(self) -> int:
        return self._channels

    @property
    def start_channel(self) -> int:
        return self._start_channel

    @property
    def track_duration(self) -> float:
        return self._track_duration

    @property
    def track_position(self) -> float:
        """
        Verstrichene Zeit im aktuellen Titel (Sekunden).
        """

        if not self.playing:
            return 0.0

        if self.paused:
            return self._resume_position

        #
        # Die Uhr laeuft noch nicht: Der Lesethread hat den Titel noch
        # nicht begonnen. Dann ist die Position genau der Offset -
        # nicht irgendeine Zeit, die woanders herkommt.
        #
        if self._track_start_time is None:
            return self._track_offset

        return (
            self._track_offset +
            (monotonic() - self._track_start_time)
        )

    def play_folder(
        self,
        device: AudioDevice,
        folder: Path,
        start_channel: int,
        rate: int,
    ) -> bool:
        """
        Spielt alle Musikdateien eines Ordners in zufälliger
        Reihenfolge in Dauerschleife ab. Löst eine bereits laufende
        Musikwiedergabe ab (Titel-/Ordnerwechsel).
        """

        if self.playing:
            self.stop()

        playlist = self.library.build_shuffled_playlist(folder)

        if not playlist:
            return False

        return self._start(
            device,
            playlist,
            folder_mode=True,
            start_channel=start_channel,
            rate=rate,
        )

    def _decoder_fuer(self, track: Path):
        """
        Wer diesen Titel liest.

        Alles Ueblliche geht ueber ffmpeg; XRacks eigene Wave64-Dateien
        liest XRack selbst, weil ffmpeg sie falsch liest (drei Byte je
        Wert statt vier - siehe player/w64_decoder.py).
        """

        if liest_xrack_selbst(track):
            return self.eigener_decoder

        return self.decoder

    def play_file(
        self,
        device: AudioDevice,
        path: Path,
        start_channel: int,
        rate: int,
    ) -> bool:
        """
        Spielt eine einzelne Datei einmalig ab. Löst eine bereits
        laufende Musikwiedergabe ab (Titel-/Ordnerwechsel).
        """

        if self.playing:
            self.stop()

        if not path.exists():
            return False

        return self._start(
            device,
            [path],
            folder_mode=False,
            start_channel=start_channel,
            rate=rate,
        )

    def play_practice(
        self,
        device: AudioDevice,
        path: Path,
        start_channel: int,
        rate: int,
        wiederholen: bool = False,
    ) -> bool:
        """
        Einen Übungsmix abspielen.

        Der Unterschied zu play_file() ist die Kanalzahl: Ein
        Übungsmix bringt sie selbst mit (vier Stems sind acht Kanäle),
        während Musik immer Stereo ist. Gelesen wird die Datei von
        XRack selbst - ffmpeg liest unsere Wave64 falsch, siehe
        player/w64_decoder.py.
        """

        if self.playing:
            self.stop()

        if not path.exists():
            return False

        daten = eckdaten(path)

        if not daten["channels"]:
            self.logger.error(
                "Übungsmix konnte nicht gelesen werden: %s", path
            )
            return False

        return self._start(
            device,
            [path],
            folder_mode=False,
            start_channel=start_channel,
            rate=rate,
            channels=daten["channels"],
            wiederholen=wiederholen,
        )

    #
    # Wie lange stop() hoechstens auf das Ende des Worker-Threads
    # wartet, und wie lange ein neuer Start auf einen alten Thread
    # wartet.
    #
    # Warum ueberhaupt eine Grenze: Der Worker liest vor jedem Titel
    # die Metadaten (probe_tags/probe_duration in
    # player/track_decoder.py) - zwei ffprobe-Aufrufe mit je zehn
    # Sekunden eigener Zeitgrenze. Steckt er gerade darin, kann er
    # nicht sofort anhalten. Frueher wartete stop() unbegrenzt mit;
    # der Stop-Knopf wirkte dann bis zu zwanzig Sekunden tot.
    #
    # Das Warten ist beim Stoppen falsch und beim Starten richtig:
    # Anhalten soll sofort wirken, und dass der Thread ein paar
    # Sekunden spaeter zu Ende laeuft, stoert niemanden - _playing
    # steht ja bereits auf False, er schreibt nichts mehr ans
    # Audiogeraet. Einen neuen Titel zu beginnen muss dagegen warten,
    # sonst liefen zwei Worker auf demselben Geraet.
    #
    # Eine halbe Sekunde reicht dem Normalfall reichlich: Steckt der
    # Worker in der Leseschleife, endet er in Millisekunden. Laenger
    # zu warten hilft nur dem Fall, den wir gerade nicht mehr abwarten
    # wollen.
    STOP_JOIN_TIMEOUT = 0.5
    START_JOIN_TIMEOUT = 25.0

    def stop(self) -> None:
        """
        Stoppt die Wiedergabe.

        Kehrt zurueck, sobald feststeht, dass nichts mehr abgespielt
        wird - nicht erst, wenn der Worker-Thread auch wirklich zu
        Ende ist (siehe STOP_JOIN_TIMEOUT).
        """

        if not self.playing:
            return

        self._playing = False

        #
        # Eine pausierte Wiedergabe wartet im Worker-Thread auf
        # das Event - ohne das Aufwecken hier würde stop() dort
        # ewig hängen bleiben (join() wartet auf den Thread).
        #
        self._paused = False

        #
        # Eine noch nicht abgeholte Pausen-Anforderung gilt nicht mehr:
        # Gestoppt ist gestoppt, und der Lesethread soll nicht an einer
        # gemerkten Stelle weitermachen wollen.
        #
        self._pause_angefordert = False

        self._pause_event.set()

        self._aktiver_decoder.close()

        if self._thread is None:
            return

        self._thread.join(timeout=self.STOP_JOIN_TIMEOUT)

        if self._thread.is_alive():

            #
            # Der Thread haengt noch in einer Metadaten-Abfrage. Er
            # endet von selbst, sobald sie zurueckkommt. Die Referenz
            # bleibt stehen, damit ein neuer Start ihn abwarten kann.
            #
            self.logger.info(
                "Musikspieler: Wiedergabe beendet, der Lese-Thread "
                "laeuft noch kurz nach (vermutlich eine "
                "Metadaten-Abfrage)."
            )

            return

        self._thread = None

    def _warte_auf_alten_thread(self) -> bool:
        """
        Wartet, bis ein noch laufender Worker-Thread zu Ende ist.

        Wird vor jedem Start gebraucht: Zwei Worker auf demselben
        Audiogeraet wuerden sich gegenseitig die Ausgabe zerschneiden.
        Liefert False, wenn der alte Thread nicht rechtzeitig endet -
        dann wird nicht gestartet, statt das Risiko einzugehen.
        """

        if self._thread is None or not self._thread.is_alive():
            self._thread = None
            return True

        self._thread.join(timeout=self.START_JOIN_TIMEOUT)

        if self._thread.is_alive():

            self.logger.error(
                "Musikspieler: Der vorherige Lese-Thread laeuft nach "
                "%.0f s immer noch - es wird nichts Neues gestartet.",
                self.START_JOIN_TIMEOUT,
            )

            return False

        self._thread = None

        return True

    def pause(self) -> None:
        """
        Pausiert die Wiedergabe. Das Audiogerät bleibt geöffnet
        (reserviert), damit sofort fortgesetzt werden kann - ein
        gleichzeitiger Soundcheck ist währenddessen nicht möglich.
        """

        if not self.playing or self.paused:
            return

        self._resume_position = self.track_position

        self._paused = True

        #
        # Die Anforderung bleibt stehen, bis der Lesethread sie
        # gesehen hat - auch wenn inzwischen schon wieder
        # fortgesetzt wurde.
        #
        self._pause_angefordert = True

        self._pause_event.clear()

        self._aktiver_decoder.close()

    def resume(self) -> None:
        """
        Setzt eine pausierte Wiedergabe fort.
        """

        if not self.playing or not self.paused:
            return

        self._paused = False

        self._pause_event.set()

    def skip(self) -> None:
        """
        Springt zum nächsten Titel (nur im Ordner-Modus sinnvoll).
        """

        if not self.playing:
            return

        self._skip_requested = True

        self._wake_if_paused()

        self._aktiver_decoder.close()

    def seek(self, position: float) -> None:
        """
        Springt an eine Position (Sekunden) im aktuellen Titel.
        """

        if not self.playing:
            return

        self._seek_target = max(0.0, position)

        self._wake_if_paused()

        self._aktiver_decoder.close()

    def _wake_if_paused(self) -> None:
        """
        Weckt eine pausierte Wiedergabe auf (z.B. für Spulen/Weiter,
        während pausiert ist).
        """

        if self._paused:
            self._paused = False
            self._pause_event.set()

    def _start(
        self,
        device: AudioDevice,
        playlist: list[Path],
        folder_mode: bool,
        start_channel: int,
        rate: int,
        channels: int | None = None,
        wiederholen: bool = False,
    ) -> bool:

        self._playlist = playlist
        self._index = 0
        self._folder_mode = folder_mode
        self._wiederholen = wiederholen

        #
        # Musik ist Stereo; ein Uebungsmix bringt seine Kanalzahl
        # selbst mit (vier Stems sind acht Kanaele).
        #
        self._channels = channels or CHANNELS
        self._start_channel = start_channel
        self._rate = rate

        self._paused = False
        self._pause_event.set()

        #
        # Die Uhr des vorigen Titels gilt nicht mehr, und die neue
        # stellt der Lesethread, wenn er wirklich beginnt.
        #
        self._track_offset = 0.0
        self._track_start_time = None

        if not self.backend.open(
            device,
            channels=self._channels,
            rate=self._rate,
            start_channel=self._start_channel,
            sample_format=alsaaudio.PCM_FORMAT_S32_LE,
        ):
            return False

        #
        # Erst sicherstellen, dass kein alter Worker mehr laeuft -
        # stop() wartet darauf bewusst nicht mehr (siehe dort).
        #
        if not self._warte_auf_alten_thread():
            self.backend.close()
            return False

        self._playing = True

        self._thread = threading.Thread(
            target=self._worker,
            daemon=True,
        )

        self._thread.start()

        self.logger.info(
            "Musikspieler gestartet: %s (%d Titel, Modus=%s)",
            playlist[0].name,
            len(playlist),
            "Ordner" if folder_mode else "Einzeltitel",
        )

        return True

    def _worker(self) -> None:

        chunk_bytes = (
            CHUNK_FRAMES *
            self._channels *
            AudioPlaybackBackend.BYTES_PER_SAMPLE
        )

        consecutive_failures = 0

        while self._playing:

            if self._index >= len(self._playlist):

                if self._folder_mode:
                    self._playlist = self.library.build_shuffled_playlist(
                        self._playlist[0].parent
                    )
                    self._index = 0

                    if not self._playlist:
                        break

                elif self._wiederholen:
                    #
                    # Beim Ueben spielt man dieselbe Stelle immer
                    # wieder. Dieselbe Schleife wie beim Ordner, nur
                    # auf einen Titel angewandt.
                    #
                    self._index = 0

                else:
                    break

            track = self._playlist[self._index]

            self._current_track = track.name

            #
            # Zwischen der Pruefung oben und hier kann stop() gelaufen
            # sein. Dann diesen Titel gar nicht erst einlesen - die
            # beiden ffprobe-Aufrufe kosten sonst bis zu zwanzig
            # Sekunden fuer nichts, und genau die haengen den Thread
            # ueber das Ende der Wiedergabe hinaus.
            #
            if not self._playing:
                break

            #
            # Eigene Dateien beantworten das aus ihrem Kopf - schneller
            # als zwei ffprobe-Aufrufe, und richtig: ffprobe rechnet
            # bei unseren Wave64-Dateien mit drei Byte je Wert.
            #
            if liest_xrack_selbst(track):

                self._current_track_title = track.stem
                self._current_track_artist = ""
                self._track_duration = eckdaten(track)["duration"]

            else:

                tags = probe_tags(track)
                self._current_track_title = tags["title"]
                self._current_track_artist = tags["artist"]

                self._track_duration = probe_duration(track)

            if self._play_track(track, chunk_bytes):
                consecutive_failures = 0
            else:
                consecutive_failures += 1

                if consecutive_failures >= 3:
                    self.logger.error(
                        "Musikspieler: zu viele Dateien konnten nicht "
                        "dekodiert werden, Wiedergabe wird gestoppt."
                    )
                    break

            self._index += 1

        self._playing = False

        self._current_track = ""
        self._current_track_title = ""
        self._current_track_artist = ""

        self.backend.close()

        self.logger.info(
            "Musikspieler gestoppt."
        )

    def _play_track(self, track: Path, chunk_bytes: int) -> bool:
        """
        Spielt einen einzelnen Titel ab und dekodiert ihn bei Bedarf
        (Spulen) erneut ab einer neuen Position. Liefert False, wenn
        die Datei nicht geöffnet werden konnte.
        """

        position = 0.0

        opened_at_least_once = False

        while self._playing:

            self._skip_requested = False
            self._seek_target = None

            self._track_offset = position

            self._aktiver_decoder = self._decoder_fuer(track)

            if not self._aktiver_decoder.open(
                track,
                channels=self._channels,
                rate=self._rate,
                start_position=position,
            ):
                return opened_at_least_once

            #
            # Die Uhr laeuft erst JETZT - nach dem Oeffnen, nicht davor.
            #
            # decoder.open() startet ffmpeg, und das braucht seine Zeit.
            # Stand die Uhr davor, zaehlte diese Anlaufzeit als
            # gespielte Zeit mit: Die Anzeige lief dem Ton voraus, und
            # eine Pause in dieser Spanne merkte sich eine Stelle, an
            # der noch nichts gespielt war.
            #
            self._track_start_time = monotonic()

            opened_at_least_once = True

            while (
                self._playing
                and not self._skip_requested
                and self._seek_target is None
                and not self._paused
            ):

                data = self._aktiver_decoder.read(chunk_bytes)

                if data is None:
                    break

                self.backend.write(data)

            #
            # War eine Pause im Spiel? Gefragt wird nach der
            # ANFORDERUNG, nicht nach dem augenblicklichen Zustand.
            #
            # Der Unterschied ist ein Fehler, der zweimal zugeschlagen
            # hat. Frueher stand hier self._paused, gelesen nach dem
            # Schliessen des Dekoders: Kam das Fortsetzen waehrend des
            # Schliessens (close() wartet bis zu zwei Sekunden auf
            # ffmpeg), stand dort schon wieder False - die
            # Pausen-Behandlung fiel aus, und _play_track lief auf das
            # break am Ende: naechster Titel statt Weiterspielen.
            #
            # Das Lesen wanderte daraufhin vor das close(). Damit war
            # der Fall geschlossen, aber nicht der Fehler: Kommen
            # Pause UND Fortsetzen, waehrend der Lesethread gerade
            # nicht dran ist - auf einem belasteten Pi sind das
            # schnell zwei Zehntelsekunden -, steht hier wieder False.
            # Der Titel fing dann von vorne an, mitten im Stueck. Im
            # Versuch unter Last war das in einem von sechs Laeufen zu
            # sehen (_track_offset 0.0 statt der gemerkten Stelle).
            #
            # Eine Anforderung dagegen bleibt stehen, bis dieser Faden
            # sie abholt. Sie kann nicht verloren gehen, egal wie die
            # Zeiten fallen.
            #
            war_pausiert = self._pause_angefordert or self._paused

            self._pause_angefordert = False

            self._aktiver_decoder.close()

            if self._playing and war_pausiert:

                self._pause_event.wait()

                if not self._playing:
                    break

                if self._skip_requested:
                    break

                position = (
                    self._seek_target
                    if self._seek_target is not None
                    else self._resume_position
                )
                continue

            if self._playing and self._seek_target is not None:
                position = self._seek_target
                continue

            break

        return opened_at_least_once
