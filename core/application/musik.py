"""
Musikspieler: Ordner und Dateien abspielen, verwalten - und Üben.
"""

from pathlib import Path

from core.recording_kind import (
    KIND_PRACTICE,
    kind_from_filename,
    start_channel_from_filename,
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

            def beim_start():
                if self.recorder.start(self.record_name_prefix):
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


    def practice_takes(self) -> list[str]:
        """
        Die Aufnahmen, die sich zum Übungsmix dazulegen lassen.

        Alles ausser Übungsmixen: Ein Mitschnitt ist eine Aufnahme wie
        jede andere (so entschieden, damit es keine dritte Art gibt) -
        erkennbar ist er ohnehin am Kanal, auf dem er liegt.
        """

        return [
            name
            for name in self.recorder.recordings
            if kind_from_filename(name) != KIND_PRACTICE
        ]


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
