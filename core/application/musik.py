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

        if self.player.playing:
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

        if self.player.playing:
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

        if self.player.playing:
            return False, (
                "Es läuft gerade ein Soundcheck - zwei Wiedergaben "
                "gleichzeitig kann das Interface nicht."
            )

        if kind_from_filename(filename) != KIND_PRACTICE:
            return False, "Das ist kein Übungsmix."

        pfad = self.recorder.writer.directory / Path(filename).name

        if not pfad.is_file():
            return False, "Der Übungsmix ist nicht da."

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
        # Zuerst die Aufnahme, dann der Ton.
        #
        # Die Reihenfolge ist nicht gleichgültig: Läuft der Mitschnitt
        # schon, wenn der erste Ton kommt, fehlt am Anfang nichts.
        # Andersherum wäre der Einsatz weg - und gerade der ist beim
        # Üben das Interessante.
        #
        # Ganz gleichzeitig geht es nicht, und es muss auch nicht: Der
        # Vorlauf von einigen Millisekunden arbeitet der Laufzeit durch
        # das Pult entgegen (XRack gibt aus, das Pult schickt zurück,
        # XRack nimmt auf). Beides zu messen wäre eine eigene Funktion
        # und gehört nicht hierher.
        #
        if mitschneiden:

            if not self.recorder.start(self.record_name_prefix):
                return False, "Die Aufnahme liess sich nicht starten."

            self.practice_recording = True

        erfolg = self.music_player.play_practice(
            self.selected_audio_device,
            pfad,
            start_channel=start_channel - 1,
            rate=self.mixer_sample_rate,
            wiederholen=wiederholen,
        )

        if not erfolg:

            #
            # Kein halber Zustand: Ohne Ton ist der Mitschnitt sinnlos,
            # und eine Aufnahme, die weiterläuft, ohne dass jemand sie
            # gestartet hat, ist schlimmer als gar keine.
            #
            if mitschneiden:
                self.recorder.stop()
                self.practice_recording = False

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

        if self.practice_recording:

            self.recorder.stop()

            self.practice_recording = False

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
