"""
Aufnehmen, Soundcheck, Pegelkontrolle und das Zusammenlegen
von Stereodateien zum Uebungsmix.
"""

import threading

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
    ) -> bool:
        """
        Setzt die Anzahl der Aufnahmekanäle.
        """

        self.record_channels = channels

        if self.selected_audio_device is None:
            return False

        self.audio_core.close()

        self.audio_core.open(
            self.selected_audio_device,
            self.record_channels,
            self.mixer_sample_rate,
        )

        self.state_store.set(
            "record_channels",
            self.record_channels,
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
        Spielt eine Aufnahme auf denselben Kanälen ab,
        auf denen sie aufgenommen wurde ("virtueller Soundcheck").
        """

        if self.selected_audio_device is None:
            return False

        if self.recorder.recording:
            return False

        if self.music_player.playing:
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
    ) -> tuple[bool, str]:
        """
        Startet die Zusammenführung mehrerer Stereo-Stems (z.B. Click,
        eigenes Instrument, Rest der Band aus Moises) zu einem
        "Übungsmix" im Hintergrund (siehe core/stem_combiner.py) -
        `file_paths` zeigen auf bereits von der Route in ein Scratch-
        Verzeichnis kopierte Uploads, die nach Abschluss gelöscht
        werden. Reihenfolge der Liste = Kanalzuordnung (Datei 1 ->
        Kanal 1+2, ...).
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

        if self.selected_audio_device is not None:

            max_channels = self.selected_audio_device.channels

            if len(file_paths) * 2 > max_channels:
                return False, (
                    f"Zu viele Dateien für das Interface "
                    f"({max_channels} Kanäle verfügbar)."
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
            args=(name, file_paths),
            daemon=True,
        )
        thread.start()

        return True, "started"


    def _run_stem_combine(
        self,
        name: str,
        file_paths: list[Path],
    ) -> None:

        try:

            filename = combine_stems(
                file_paths,
                self.mixer_sample_rate,
                name,
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
