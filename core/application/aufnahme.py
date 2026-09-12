"""
Aufnehmen, Soundcheck, Pegelkontrolle und das Zusammenlegen
von Stereodateien zum Uebungsmix.
"""

import threading

from core.recording_kind import KIND_PRACTICE, kind_from_filename
from core.stem_combiner import combine_stems, StemCombineError
from pathlib import Path


class AufnahmeMixin:
    """
    Aufnehmen, Soundcheck, Pegelkontrolle und das Zusammenlegen

    Teil von Application - siehe core/application/__init__.py.
    """

    def set_record_channels(
        self,
        channels: int,
        manuell: bool = False,
    ) -> bool:
        """
        Setzt die Anzahl der Aufnahmekanäle.

        `manuell` unterscheidet die Wahl des Nutzers von der
        Nachführung beim Gerätewechsel. Nur eine Wahl von Hand wird
        als solche gemerkt - danach fasst XRack die Zahl nicht mehr
        von sich aus an (siehe select_audio_device).
        """

        self.record_channels = channels

        if manuell:
            self.state_store.set("record_channels_manual", True)

        return self._aufnahmefenster_anwenden()


    def set_record_start_channel(self, start_channel: int) -> bool:
        """
        Setzt den ersten aufgenommenen Kanal (1-basiert).

        Aufgenommen wird ein Fenster, nicht immer der Anfang: Am X32
        braucht man vielleicht nur die Kanäle 17-24, und beim Üben nur
        das eigene Instrument.
        """

        self.record_start_channel = max(1, int(start_channel))

        return self._aufnahmefenster_anwenden()


    def _aufnahmefenster_anwenden(self) -> bool:
        """
        Das Fenster (erster Kanal, Anzahl) auf das Interface anwenden
        und merken.

        Beides zusammen, weil beides dasselbe Öffnen braucht - und
        weil ein halb angewandtes Fenster hiesse, dass die Anzeige
        etwas anderes sagt als die Aufnahme tut.
        """

        if self.selected_audio_device is None:
            return False

        #
        # Das Fenster muss ins Interface passen. Ist es zu weit rechts,
        # wird es hierher gezogen statt daneben zu greifen.
        #
        vorhanden = self.selected_audio_device.channels

        self.record_start_channel = max(
            1, min(self.record_start_channel, vorhanden)
        )

        self.audio_core.close()

        self.audio_core.open(
            self.selected_audio_device,
            self.record_channels,
            self.mixer_sample_rate,
            start_channel=self.record_start_channel - 1,
        )

        self.state_store.set(
            "record_channels",
            self.record_channels,
        )

        self.state_store.set(
            "record_start_channel",
            self.record_start_channel,
        )

        return True


    def start_recording(self) -> bool:
        """
        Startet eine Aufnahme. Lehnt ab, solange gerade eine
        Soundcheck-Wiedergabe läuft - dieselbe Datei würde sonst
        gleichzeitig gelesen und beschrieben, und während des
        Kontrollhörens einer alten Aufnahme aus Versehen eine neue
        zu starten ergibt ohnehin keinen Sinn.
        """

        if self.player.playing:
            return False

        return self.recorder.start(self.record_name_prefix)


    def start_soundcheck(self, filename: str) -> bool:
        """
        Spielt eine AUFNAHME auf denselben Kanälen ab, auf denen sie
        aufgenommen wurde ("virtueller Soundcheck").

        Nur Aufnahmen: Übungsmixe laufen über die Üben-Karte, und zwar
        über den Musikspieler - der kann anhalten, spulen und
        wiederholen, und genau das braucht man zum Üben. Hier liefen
        sie lange auch, weil es historisch derselbe Knopf war; damit
        gab es den Weg zweimal, und einer davon konnte weniger.

        Während einer Aufnahme nicht: Dieselbe Datei würde gelesen und
        beschrieben. Während Musik oder einer Übung auch nicht - das
        Interface nimmt einen Wiedergabestrom.
        """

        if self.selected_audio_device is None:
            return False

        if self.recorder.recording:
            return False

        if self.music_player.playing:
            return False

        if kind_from_filename(filename) == KIND_PRACTICE:

            self.logger.warning(
                "Übungsmix nicht über den Soundcheck: %s - dafür gibt "
                "es die Üben-Karte.",
                filename,
            )

            return False

        path = self.recorder.writer.directory / filename

        return self.player.start(
            self.selected_audio_device,
            path,
        )


    def stop_soundcheck(self) -> None:
        """
        Stoppt eine laufende Soundcheck-Wiedergabe.
        """

        self.player.stop()


    def start_level_check(self) -> bool:
        """
        Startet die reine Pegelprüfung (ohne aufzuzeichnen).
        """

        return self.recorder.start_monitoring()


    def stop_level_check(self) -> None:
        """
        Stoppt die reine Pegelprüfung.
        """

        self.recorder.stop_monitoring()


    def set_record_name_prefix(self, prefix: str) -> bool:
        """
        Ändert das Namenspräfix für neue Aufnahmen (z.B. "Soundcheck"
        -> Dateien "Soundcheck-1.w64", "Soundcheck-2.w64", ...).
        """

        prefix = prefix.strip()

        if (
            not prefix
            or len(prefix) > 40
            or "/" in prefix
            or "\\" in prefix
            or prefix in (".", "..")
        ):
            return False

        self.record_name_prefix = prefix

        self.state_store.set(
            "record_name_prefix",
            prefix,
        )

        return True


    def start_stem_combine(
        self,
        name: str,
        file_paths: list[Path],
        start_channel: int = 1,
    ) -> tuple[bool, str]:
        """
        Startet die Zusammenführung mehrerer Stereo-Stems (z.B. Click,
        eigenes Instrument, Rest der Band aus Moises) zu einem
        "Übungsmix" im Hintergrund (siehe core/stem_combiner.py) -
        `file_paths` zeigen auf bereits von der Route in ein Scratch-
        Verzeichnis kopierte Uploads, die nach Abschluss gelöscht
        werden. Reihenfolge der Liste = Kanalzuordnung (Datei 1 ->
        Kanal 1+2, ...).

        `start_channel` (1-basiert) sagt, ab welchem Kanal des
        Interfaces der Mix später liegen soll. Er wandert in den
        Dateinamen und wird beim Üben von dort gelesen - gewählt wird
        er einmal hier und nicht vor jedem Üben neu.
        """

        name = name.strip()

        if (
            not name
            or len(name) > 40
            or "/" in name
            or "\\" in name
            or name in (".", "..")
        ):
            return False, "Ungültiger Name."

        if not 2 <= len(file_paths) <= 8:
            return False, "Es werden 2 bis 8 Dateien benötigt."

        #
        # Nur ungerade Startkanaele: Jeder Stem ist ein Stereopaar.
        # Faenge der Mix auf einem geraden Kanal an, laege jedes Paar
        # quer ueber zwei Paare des Pults - links und rechts kaemen
        # aus verschiedenen Zuegen.
        #
        start_channel = int(start_channel)

        if start_channel < 1 or start_channel % 2 == 0:
            return False, "Der erste Kanal muss ungerade sein."

        if self.selected_audio_device is not None:

            max_channels = self.selected_audio_device.channels

            #
            # Gemessen wird ab dem ersten Kanal, nicht ab 1: Vier Stems
            # ab Kanal 13 brauchen bis Kanal 20. Was darueber
            # hinausragt, waere beim Ueben still - und niemand saehe,
            # warum.
            #
            if start_channel - 1 + len(file_paths) * 2 > max_channels:
                return False, (
                    f"Zu viele Dateien für das Interface ab Kanal "
                    f"{start_channel} ({max_channels} Kanäle verfügbar)."
                )

        with self._stem_combine_lock:

            if self.stem_combine_state["active"]:
                return False, "Es läuft bereits eine Zusammenführung."

            self.stem_combine_state = {
                "active": True,
                "success": None,
                "error": "",
                "filename": "",
            }

        thread = threading.Thread(
            target=self._run_stem_combine,
            args=(name, file_paths, start_channel),
            daemon=True,
        )
        thread.start()

        return True, "started"


    def _run_stem_combine(
        self,
        name: str,
        file_paths: list[Path],
        start_channel: int = 1,
    ) -> None:

        try:

            filename = combine_stems(
                file_paths,
                self.mixer_sample_rate,
                name,
                start_channel=start_channel,
            )

            with self._stem_combine_lock:
                self.stem_combine_state["success"] = True
                self.stem_combine_state["filename"] = filename

        except StemCombineError as exc:

            with self._stem_combine_lock:
                self.stem_combine_state["success"] = False
                self.stem_combine_state["error"] = str(exc)

        except Exception as exc:

            self.logger.exception(
                "Übungsmix fehlgeschlagen: %s",
                exc,
            )

            with self._stem_combine_lock:
                self.stem_combine_state["success"] = False
                self.stem_combine_state["error"] = "Unerwarteter Fehler."

        finally:

            with self._stem_combine_lock:
                self.stem_combine_state["active"] = False

            for path in file_paths:
                path.unlink(missing_ok=True)

            if file_paths:
                try:
                    file_paths[0].parent.rmdir()
                except OSError:
                    pass


    def get_stem_combine_status(self) -> dict:
        """Liefert den aktuellen Fortschritt der Übungsmix-Erstellung."""

        with self._stem_combine_lock:
            return dict(self.stem_combine_state)
