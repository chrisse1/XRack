"""
Musikspieler: Ordner und Dateien abspielen, verwalten.
"""


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
