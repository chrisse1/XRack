"""
Musikspieler: Ordner und Dateien abspielen, verwalten - und Üben.
"""

import shutil
import tempfile
import threading
import time
from pathlib import Path

from core.laufzeit_messung import (
    MESSDAUER_S,
    MESSUNGEN,
    SPANNE_WARNUNG_MS,
    klick_datei,
    mittlerer_wert,
    versatz_ms,
)
from core.recording_kind import (
    KIND_PRACTICE,
    kind_from_filename,
    mix_von_take,
    start_channel_from_filename,
    take_basis,
    take_nummer,
    take_praefix,
)


class MusikMixin:
    """
    Musikspieler: Ordner und Dateien abspielen, verwalten.

    Teil von Application - siehe core/application/__init__.py.
    """

    # ----------------------------------------------------------------
    # Was sich ausschliesst - und was ausdruecklich nicht
    #
    # Die Regel dahinter ist keine Vorsicht, sondern die Hardware: Das
    # Interface nimmt EINEN Wiedergabestrom an. Ein Aufnahmestrom
    # daneben ist dagegen kein Problem - genau davon lebt XRack.
    #
    #   Aufnahme + Musik    erlaubt
    #   Aufnahme + Ueben    erlaubt   <- darum geht es beim Mitschneiden
    #   Aufnahme + Soundcheck  nein   (dieselbe Datei lesen und schreiben)
    #   Soundcheck + Musik  nein      (zwei Wiedergabestroeme)
    #   Soundcheck + Ueben  nein      (zwei Wiedergabestroeme)
    #   Musik + Ueben       nein      (ein Spieler, eine Quelle)
    #
    # Die Sperren stehen HIER und nicht nur in der Oberflaeche: Was
    # nur die Oberflaeche verhindert, verhindert sie nur, solange sie
    # stimmt - danach scheitert ALSA, und zu sehen ist ein Knopf, der
    # nichts tut. Geprueft wird die Tabelle in test_sperrmatrix.py.
    # ----------------------------------------------------------------

    def uebung_nachfuehren(self) -> None:
        """
        Merkt, wenn die Übung von selbst zu Ende gegangen ist.

        Ein Stück endet, keine Schleife - dann hört der Spieler auf,
        ohne dass jemand gestoppt hat. Bliebe XRack dabei auf "es läuft
        eine Übung" stehen, liesse sich danach nie wieder Musik
        starten; und bliebe es auf "wir schneiden mit" stehen, würde
        das nächste Stoppen eine fremde Aufnahme beenden.

        Wird bei jeder Statusabfrage gerufen (siehe
        Application.update_status).
        """

        if not self.music_player.playing:
            self.practice_active = False

        if not self.recorder.recording:
            self.practice_recording = False


    def wiedergabe_laeuft(self) -> tuple[bool, str]:
        """
        Läuft gerade eine Wiedergabe - und welche?

        Liefert (läuft, Grund). Der Grund ist für den Nutzer gedacht:
        Eine Ablehnung, die nicht sagt, was im Weg steht, ist so gut
        wie keine Auskunft.
        """

        if self.player.playing:
            return True, "Es läuft gerade ein Soundcheck."

        if self.practice_active:
            return True, "Es läuft gerade eine Übung."

        if self.music_player.playing:
            return True, "Es läuft gerade Musik."

        return False, ""

    def play_music_folder(
        self,
        relative_path: str,
        start_channel: int,
    ) -> bool:
        """
        Spielt alle Musikdateien eines Ordners zufällig gemischt
        in Dauerschleife ab. `start_channel` ist 1-basiert
        (z.B. 17 für Kanal 17+18).
        """

        if self.selected_audio_device is None:
            return False

        #
        # Ein Titelwechsel ist erlaubt (laufende Musik loest sich
        # selbst ab), eine laufende Uebung nicht: Die wuerde sonst
        # stillschweigend verschwinden - samt Mitschnitt, der
        # weiterliefe.
        #
        if self.player.playing or self.practice_active:
            return False

        folder = self.music_library.resolve(relative_path)

        if folder is None or not folder.is_dir():
            return False

        self.set_music_channel_preference(start_channel)

        return self.music_player.play_folder(
            self.selected_audio_device,
            folder,
            start_channel=start_channel - 1,
            rate=self.mixer_sample_rate,
        )


    def play_music_file(
        self,
        relative_path: str,
        start_channel: int,
    ) -> bool:
        """
        Spielt eine einzelne Musikdatei einmalig ab.
        """

        if self.selected_audio_device is None:
            return False

        if self.player.playing or self.practice_active:
            return False

        path = self.music_library.resolve(relative_path)

        if path is None or not path.is_file():
            return False

        self.set_music_channel_preference(start_channel)

        return self.music_player.play_file(
            self.selected_audio_device,
            path,
            start_channel=start_channel - 1,
            rate=self.mixer_sample_rate,
        )


    # ----------------------------------------------------------------
    # Üben
    #
    # Dieselbe Karte, dieselbe Mechanik - nur eine andere Quelle. Der
    # Musikspieler kann seit Stufe 2 auch mehrkanalige Übungsmixe
    # abspielen (siehe player/w64_decoder.py), und damit fällt der
    # Grund weg, dafür einen zweiten Spieler zu haben.
    #
    # Zwei Wiedergabeströme kann das Interface ohnehin nicht - deshalb
    # ist es EINE Karte mit Umschalter und nicht zwei nebeneinander.
    # ----------------------------------------------------------------

    def set_player_mode(self, mode: str) -> tuple[bool, str]:
        """
        Zwischen Musik und Üben umschalten.

        Nicht, solange etwas läuft: Die Karte tauscht darunter die
        Quelle aus, und mitten in der Wiedergabe umzuschalten wäre eine
        Falle - man drückt auf "Üben" und die Musik läuft weiter.
        """

        if mode not in ("music", "practice"):
            return False, "Unbekannte Betriebsart."

        if self.music_player.playing:
            return False, (
                "Erst anhalten - die Karte tauscht beim Umschalten die "
                "Quelle aus."
            )

        self.player_mode = mode

        self.state_store.set("player_mode", mode)

        return True, ""


    def practice_mixes(self) -> list[str]:
        """
        Die vorhandenen Übungsmixe.

        Erkannt werden sie am Namen, wie überall (siehe
        core/recording_kind.py) - eine eigene Verwaltungsdatei gibt es
        bewusst nicht.
        """

        return [
            name
            for name in self.recorder.recordings
            if kind_from_filename(name) == KIND_PRACTICE
        ]


    def start_practice(
        self,
        filename: str,
        wiederholen: bool = False,
        mitschneiden: bool = False,
        mitschnitt: str = "",
    ) -> tuple[bool, str]:
        """
        Einen Übungsmix abspielen.

        Auf welchen Kanälen er landet, steht im Dateinamen und wird
        nicht vor jedem Üben neu gewählt: Ein Übungsmix wird für einen
        Platz im Pult gebaut - vier Stems liegen auf 1-8, und dort
        gehören sie beim nächsten Mal wieder hin. Gesetzt wird der
        Kanal einmal beim Erstellen (siehe start_stem_combine).

        Dasselbe tut der Soundcheck-Spieler mit Aufnahmen, und aus
        demselben Grund: Die Angabe reist über USB, Download und
        Backup mit, XRack muss nirgends Buch führen (ausführlich in
        core/recording_kind.py).
        """

        if self.selected_audio_device is None:
            return False, "Kein Audiogerät gewählt."

        laeuft, grund = self.wiedergabe_laeuft()

        if laeuft:
            return False, (
                f"{grund} Zwei Wiedergaben gleichzeitig kann das "
                f"Interface nicht - erst anhalten."
            )

        if kind_from_filename(filename) != KIND_PRACTICE:
            return False, "Das ist kein Übungsmix."

        pfad = self.recorder.writer.directory / Path(filename).name

        if not pfad.is_file():
            return False, "Der Übungsmix ist nicht da."

        #
        # Ein Mitschnitt zum Mitspielen: Er liegt im selben Strom wie
        # der Mix, auf den Kanälen, auf denen er aufgenommen wurde.
        # Zwei Wiedergaben gleichzeitig kann das Interface nicht - zwei
        # Dateien in einer Wiedergabe schon.
        #
        mitschnitt_pfad = None
        mitschnitt_start = 0

        if mitschnitt:

            mitschnitt_pfad = (
                self.recorder.writer.directory / Path(mitschnitt).name
            )

            if not mitschnitt_pfad.is_file():
                return False, "Der Mitschnitt ist nicht da."

            if kind_from_filename(mitschnitt) == KIND_PRACTICE:
                return False, (
                    "Ein Übungsmix ist kein Mitschnitt - sonst lägen "
                    "zwei Mixe übereinander."
                )

            mitschnitt_start = start_channel_from_filename(
                mitschnitt_pfad.name
            ) - 1

        if mitschneiden and not self.recorder.bereit:
            return False, (
                "Zum Mitschneiden fehlt ein offenes Audiogerät."
            )

        if mitschneiden and self.recorder.recording:
            return False, "Es läuft bereits eine Aufnahme."

        #
        # Im Namen steht der erste Kanal 1-basiert ("_p9"), der
        # ChannelInserter zaehlt ab 0. Ohne Ziffer ist es Kanal 1.
        #
        start_channel = start_channel_from_filename(pfad.name)

        #
        # Die Aufnahme beginnt mit dem ERSTEN BLOCK, der zum Interface
        # geht - nicht vorher.
        #
        # Hier stand zuerst "erst die Aufnahme starten, dann den Ton",
        # mit dem Gedanken, dass dann am Anfang nichts fehlt. Der
        # Gedanke stimmt, aber er macht den Mitschnitt unbrauchbar für
        # das Zusammenhören: Zwischen beiden Aufrufen liegen das Öffnen
        # von ALSA, ein Threadstart und das Anlegen der Datei -
        # zusammen einige zehn Millisekunden, und jedes Mal
        # unterschiedlich viele. Dieser Zufall stünde im Mitschnitt und
        # liesse sich nachher durch nichts mehr herausrechnen.
        #
        # So dagegen ist der Abstand zwischen Mix und Mitschnitt für
        # jeden Lauf DERSELBE - und damit eine Grösse, die sich einmal
        # messen und danach immer anwenden lässt (practice_offset_ms).
        #
        # Was bleibt, ist die Laufzeit des Weges: XRack schreibt in den
        # ALSA-Puffer, das Pult wandelt, mischt und schickt zurück,
        # XRack liest wieder aus einem Puffer. Die ist von hier aus
        # nicht auszurechnen - sie hängt am Pult, an der Route durch
        # das Pult und an der Puffergrösse. Gemessen werden muss sie.
        #
        beim_start = None

        if mitschneiden:

            #
            # Der Mitschnitt traegt den Namen des Stuecks, zu dem er
            # entstanden ist: "Umbrella-1-Take1_s9.w64". Damit findet
            # er spaeter zu seinem Mix zurueck, ohne dass XRack Buch
            # fuehrt (siehe core/recording_kind.py).
            #
            praefix = take_praefix(filename)

            def beim_start():
                if self.recorder.start(praefix, trenner=""):
                    self.practice_recording = True
                else:
                    self.logger.error(
                        "Der Mitschnitt liess sich nicht starten - das "
                        "Üben läuft ohne ihn weiter."
                    )

        erfolg = self.music_player.play_practice(
            self.selected_audio_device,
            pfad,
            start_channel=start_channel - 1,
            rate=self.mixer_sample_rate,
            wiederholen=wiederholen,
            mitschnitt=mitschnitt_pfad,
            mitschnitt_start=mitschnitt_start,
            versatz=self.practice_offset_ms / 1000.0,
            beim_start=beim_start,
        )

        if erfolg:
            self.practice_active = True

        if not erfolg:

            #
            # Kein halber Zustand: Ohne Ton ist der Mitschnitt sinnlos,
            # und eine Aufnahme, die weiterläuft, ohne dass jemand sie
            # gestartet hat, ist schlimmer als gar keine. Gestartet
            # wurde sie hier zwar noch gar nicht (das tut der erste
            # Block), aber der Weg dorthin kann auch mitten im Start
            # abbrechen.
            #
            if mitschneiden and self.practice_recording:
                self.recorder.stop()
                self.practice_recording = False

            if mitschnitt_pfad is not None:
                return False, (
                    "Übungsmix und Mitschnitt passen nicht zusammen auf "
                    "das Interface - siehe Protokoll."
                )

            return False, "Der Übungsmix liess sich nicht öffnen."

        return True, ""


    def stop_practice(self) -> bool:
        """
        Das Üben beenden - und den Mitschnitt gleich mit.

        Nur den eigenen: Lief die Aufnahme schon vorher (von der
        Soundcheck-Karte aus), bleibt sie laufen. Etwas zu beenden, was
        man nicht angefangen hat, wäre eine böse Überraschung - die
        Datei ist dann zu, und niemand hat es angeordnet.
        """

        self.music_player.stop()

        self.practice_active = False

        if self.practice_recording:

            self.recorder.stop()

            self.practice_recording = False

        return True


    def practice_takes(self) -> dict[str, list[str]]:
        """
        Zu jedem Übungsmix seine Mitschnitte.

        Die Zuordnung steht im Dateinamen: Zum Mix "Umbrella-1_p.w64"
        gehören "Umbrella-1-Take1_s9.w64" und so fort. Gedacht ist das
        für die Auswahl "Dazu hören" - dort gehören nur die Versuche
        zum gerade gewählten Stück hin, alles andere wäre eine Liste,
        die mit jedem Üben länger wird und in der man sucht.

        Ein Mitschnitt, dessen Übungsmix gelöscht wurde, taucht hier
        nicht auf. Er ist dann wieder eine Aufnahme wie jede andere
        und über die Soundcheck-Karte erreichbar - verloren ist er
        nicht.
        """

        mixe = {take_basis(name): name for name in self.practice_mixes()}

        zuordnung: dict[str, list[str]] = {
            name: [] for name in mixe.values()
        }

        for name in self.recorder.recordings:

            basis = mix_von_take(name)

            if basis in mixe:
                zuordnung[mixe[basis]].append(name)

        for liste in zuordnung.values():
            liste.sort(key=take_nummer)

        return zuordnung


    def ist_mitschnitt(self, filename: str) -> bool:
        """
        Gehört diese Aufnahme zu einem vorhandenen Übungsmix?

        Gebraucht von den beiden Dateiverwaltungen: Was hier wahr ist,
        gehört in die der Üben-Karte und nicht in die der
        Soundcheck-Karte.
        """

        basis = mix_von_take(filename)

        if basis is None:
            return False

        return basis in {
            take_basis(name) for name in self.practice_mixes()
        }


    # ----------------------------------------------------------------
    # Die Laufzeit messen
    #
    # Gemessen wird genau das, was nachher korrigiert wird: ein
    # Uebungslauf mit einem Klick-Mix, mitgeschnitten ueber den ganz
    # normalen Weg. Steht der Klick im Mix bei einer Sekunde und im
    # Mitschnitt bei 1,08 s, ist die Laufzeit 80 ms - ohne eine
    # einzige Annahme ueber Puffer, Perioden oder Pulte.
    #
    # Begruendung ausfuehrlich in core/laufzeit_messung.py.
    # ----------------------------------------------------------------

    def laufzeit_status(self) -> dict:
        """Was die Messung gerade tut - für die Oberfläche."""

        with self._laufzeit_lock:
            return dict(self._laufzeit_stand)


    def start_laufzeit_messung(self) -> tuple[bool, str]:
        """
        Startet die Messung im Hintergrund.

        Sie dauert einige Sekunden (Klick-Mix schreiben, abspielen,
        auswerten) - zu lange für eine Anfrage, die auf Antwort
        wartet. Der Fortschritt kommt über laufzeit_status().
        """

        if self.selected_audio_device is None:
            return False, "Kein Audiogerät gewählt."

        if not self.recorder.bereit:
            return False, "Kein Audiogerät geöffnet."

        if self.recorder.recording:
            return False, "Es läuft bereits eine Aufnahme."

        laeuft, grund = self.wiedergabe_laeuft()

        if laeuft:
            return False, f"{grund} Erst anhalten."

        with self._laufzeit_lock:

            if self._laufzeit_stand["active"]:
                return False, "Es läuft bereits eine Messung."

            self._laufzeit_stand = {
                "active": True,
                "success": None,
                "ms": 0,
                "werte": [],
                "spanne": 0,
                "unsicher": False,
                "error": "",
            }

        threading.Thread(
            target=self._laufzeit_messen,
            daemon=True,
        ).start()

        return True, ""


    def _laufzeit_messen(self) -> None:
        """
        Die Messreihe - in einem eigenen Faden.

        Gemessen wird MEHRMALS. Eine einzelne Zahl ist keine Messung,
        sondern ein Wert: Erst mehrere Läufe zeigen, ob er steht.
        Kommt dreimal dasselbe heraus, ist es eine Eigenschaft der
        Anlage; streut es, ist es keine Konstante - und dann wäre es
        falsch, so zu tun, als sei sie eine.

        Aufgeräumt wird in jedem Fall: Der Klick-Mix und die
        Mitschnitte der Messung sind Wegwerfdateien. Blieben sie
        liegen, stünden sie in der Aufnahmenliste und niemand wüsste,
        wozu.
        """

        klick = None
        werte: list[int] = []

        arbeitsordner = tempfile.mkdtemp(prefix="xrack_laufzeit_")

        try:

            klick = klick_datei(
                Path(arbeitsordner),
                self.selected_audio_device.channels,
                self.mixer_sample_rate,
            )

            for _ in range(MESSUNGEN):

                wert, grund = self._ein_laufzeitlauf(klick)

                if wert < 0:
                    self._laufzeit_fertig(False, 0, grund, werte)
                    return

                werte.append(wert)

            mitte = mittlerer_wert(werte)

            self.set_practice_offset(mitte)

            self._laufzeit_fertig(True, mitte, "", werte)

        except Exception as fehler:

            self.logger.exception("Laufzeitmessung fehlgeschlagen: %s", fehler)

            self._laufzeit_fertig(False, 0, "Unerwarteter Fehler.", werte)

        finally:

            if klick is not None:
                Path(klick).unlink(missing_ok=True)

            shutil.rmtree(arbeitsordner, ignore_errors=True)


    def _ein_laufzeitlauf(self, klick: Path) -> tuple[int, str]:
        """
        Ein einzelner Durchgang: Klick abspielen, dabei mitschneiden,
        die Stelle suchen, den Mitschnitt wieder wegräumen.
        """

        mitschnitt = None

        try:

            #
            # Derselbe Weg wie beim Ueben mit Mitschnitt: Die Aufnahme
            # beginnt mit dem ersten Block, der zum Interface geht.
            # Genau daran haengt die Messung - startete sie frueher,
            # maesse man die Anlaufzeit von XRack mit.
            #
            gestartet = []

            def beim_start():
                if self.recorder.start("Laufzeitmessung"):
                    gestartet.append(self.recorder.current_filename)

            erfolg = self.music_player.play_practice(
                self.selected_audio_device,
                klick,
                start_channel=0,
                rate=self.mixer_sample_rate,
                beim_start=beim_start,
            )

            if not erfolg:
                return -1, "Der Klick liess sich nicht abspielen."

            #
            # Warten, bis der Klick-Mix durch ist - er ist wenige
            # Sekunden lang. Die Frist ist grosszuegig und nur dafuer
            # da, dass ein haengender Spieler die Messung nicht ewig
            # offen laesst.
            #
            frist = time.monotonic() + MESSDAUER_S + 10.0

            while self.music_player.playing and time.monotonic() < frist:
                time.sleep(0.05)

            self.music_player.stop()

            self.recorder.stop()

            if not gestartet:
                return -1, "Der Mitschnitt liess sich nicht starten."

            #
            # current_filename ist bereits der VOLLSTAENDIGE Pfad
            # (siehe AudioWriter.create_filename) - hier stand einmal
            # "directory / current_filename", und das ging gut, solange
            # das Verzeichnis absolut war: Ein absoluter Pfad rechts
            # gewinnt, die Verdopplung fiel nicht auf. Am Geraet ist
            # das Verzeichnis relativ ("./recordings"), und daraus
            # wurde "recordings/recordings/..." - die Messung nahm auf,
            # fand danach ihre eigene Datei nicht und meldete, der
            # Mitschnitt fehle.
            #
            mitschnitt = Path(gestartet[0])

            if not mitschnitt.is_file():
                return -1, "Der Mitschnitt der Messung fehlt."

            return versatz_ms(mitschnitt, self.mixer_sample_rate)

        finally:

            #
            # Der Mitschnitt der Messung ist eine Wegwerfdatei - auch
            # wenn unterwegs etwas schiefging.
            #
            if mitschnitt is not None:
                try:
                    Path(mitschnitt).unlink(missing_ok=True)
                except OSError:
                    pass


    def _laufzeit_fertig(self, erfolg: bool, ms: int, grund: str,
                         werte: list[int] | None = None) -> None:
        """
        Das Ergebnis festhalten - samt der EINZELWERTE.

        Die Einzelwerte gehören dazu, nicht nur der mittlere: Drei
        gleiche Zahlen sind ein Befund, drei verschiedene sind eine
        Warnung. Wer nur das Ergebnis sieht, kann beides nicht
        auseinanderhalten.
        """

        werte = list(werte or [])

        spanne = max(werte) - min(werte) if werte else 0

        with self._laufzeit_lock:
            self._laufzeit_stand = {
                "active": False,
                "success": erfolg,
                "ms": ms,
                "werte": werte,
                "spanne": spanne,
                "unsicher": spanne > SPANNE_WARNUNG_MS,
                "error": grund,
            }

        if erfolg:
            self.logger.info(
                "Laufzeit gemessen: %d ms (Läufe: %s, Spanne %d ms)",
                ms,
                ", ".join(str(w) for w in werte),
                spanne,
            )
        else:
            self.logger.warning("Laufzeitmessung ohne Ergebnis: %s", grund)


    def set_practice_offset(self, millisekunden: int) -> bool:
        """
        Wie weit der Mitschnitt beim Zusammenhören vorgezogen wird.

        Das ist die Laufzeit des ganzen Weges - XRack, Puffer, USB,
        Pult, zurück. Sie liegt bei einer Puffergrösse von 1024
        Rahmen in der Grössenordnung einiger zehn Millisekunden, aber
        eine Zahl daraus zu rechnen wäre geraten: Sie hängt am Pult, an
        der Route durch das Pult und daran, wie voll ALSA seine Puffer
        wirklich fährt.

        Deshalb ist es ein Wert, den man setzt - nach Gehör oder nach
        einer Messung. Negative Werte gibt es nicht: Der Mitschnitt
        kann dem Mix nicht vorauseilen.
        """

        self.practice_offset_ms = max(0, min(2000, int(millisekunden)))

        self.state_store.set(
            "practice_offset_ms",
            self.practice_offset_ms,
        )

        return True


    def set_practice_record(self, an: bool) -> bool:
        """Merkt sich, ob beim Üben mitgeschnitten werden soll."""

        self.practice_record = bool(an)

        self.state_store.set("practice_record", self.practice_record)

        return True


    def set_practice_repeat(self, an: bool) -> bool:
        """Die Schleife ein- oder ausschalten."""

        self.practice_repeat = bool(an)

        self.state_store.set("practice_repeat", self.practice_repeat)

        self.music_player.set_wiederholen(self.practice_repeat)

        return True


    def set_music_channel_preference(self, start_channel: int) -> bool:
        """
        Merkt sich den für die Musikwiedergabe gewählten Startkanal
        (1-basiert), damit das Dropdown nach einem Neustart wieder
        vorbelegt ist. Wird sowohl beim bloßen Auswählen im
        Dropdown als auch beim tatsächlichen Start einer Wiedergabe
        aufgerufen.
        """

        self.music_channel_preference = start_channel

        self.state_store.set(
            "music_channel",
            start_channel,
        )

        return True


    def stop_music(self) -> None:
        """
        Stoppt den Musikspieler.
        """

        self.music_player.stop()


    def pause_music(self) -> None:
        """
        Pausiert den Musikspieler.
        """

        self.music_player.pause()


    def resume_music(self) -> None:
        """
        Setzt den pausierten Musikspieler fort.
        """

        self.music_player.resume()


    def skip_music(self) -> None:
        """
        Springt zum nächsten Titel (Ordner-Modus).
        """

        self.music_player.skip()


    def seek_music(self, position: float) -> None:
        """
        Springt an eine Position (in Sekunden) im aktuellen Titel.
        """

        self.music_player.seek(position)


    def create_music_folder(
        self,
        relative_path: str,
        name: str,
    ) -> bool:
        """
        Legt einen neuen Ordner in der Musikbibliothek an.
        """

        return self.music_library.create_folder(
            relative_path,
            name,
        )


    def upload_music_file(
        self,
        relative_path: str,
        filename: str,
        source,
    ) -> str | None:
        """
        Speichert eine hochgeladene Musikdatei.
        """

        return self.music_library.save_upload(
            relative_path,
            filename,
            source,
        )


    def delete_music_file(self, relative_path: str) -> bool:
        """
        Löscht eine Musikdatei aus der Bibliothek.
        """

        return self.music_library.delete_file(
            relative_path
        )


    def delete_music_files(self, relative_paths: list[str]) -> list[str]:
        """
        Löscht mehrere Musikdateien auf einmal.
        """

        return self.music_library.delete_files(
            relative_paths
        )
