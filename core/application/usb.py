"""
USB-Stick: Aufnahmen kopieren und den Stick auswerfen.
"""

import shutil
import threading

from pathlib import Path

from core.usb_storage import ENDUNGEN_AUFNAHMEN, ENDUNGEN_MUSIK


class UsbMixin:
    """
    USB-Stick: Aufnahmen kopieren und den Stick auswerfen.

    Teil von Application - siehe core/application/__init__.py.
    """

    def start_usb_copy(self, filename: str) -> tuple[bool, str]:
        """
        Startet das Kopieren einer Aufnahme ins Wurzelverzeichnis des
        USB-Sticks im Hintergrund (läuft sonst blockierend und ohne
        Fortschrittsanzeige). Der Fortschritt lässt sich über
        get_usb_copy_status() abfragen. Es läuft immer nur ein
        Kopiervorgang gleichzeitig.
        """

        recording = self.recorder.writer.directory / filename

        if not recording.exists():
            return False, "not_found"

        if not self.usb_storage.connected:
            return False, "no_usb"

        with self._usb_copy_lock:

            if self.usb_copy_state["active"]:
                return False, "busy"

            self.usb_copy_state = {
                "active": True,
                "filename": filename,
                "copied": 0,
                "total": recording.stat().st_size,
                "success": None,
                "already_exists": False,
            }

        thread = threading.Thread(
            target=self._run_usb_copy,
            args=(recording,),
            daemon=True,
        )
        thread.start()

        return True, "started"


    def _run_usb_copy(self, recording: Path) -> None:

        def on_progress(copied: int, total: int) -> None:
            with self._usb_copy_lock:
                self.usb_copy_state["copied"] = copied
                self.usb_copy_state["total"] = total

        success, already_exists = self.usb_storage.copy_file(
            recording,
            on_progress,
        )

        with self._usb_copy_lock:
            self.usb_copy_state["active"] = False
            self.usb_copy_state["success"] = success
            self.usb_copy_state["already_exists"] = already_exists


    def get_usb_copy_status(self) -> dict:
        """Liefert den aktuellen Fortschritt des USB-Kopiervorgangs."""

        with self._usb_copy_lock:
            return dict(self.usb_copy_state)


    # ----------------------------------------------------------------
    # Vom Stick auf das Gerät
    # ----------------------------------------------------------------

    #
    # Wohin kopiert werden darf, und was dort hineingehört.
    #
    # Zwei Ziele, und sie sind verschieden: Die Musikbibliothek hat
    # Ordner, das Aufnahmeverzeichnis ist flach. Eine Datei in einem
    # Unterordner von "recordings" fände XRack nie wieder - deshalb
    # wandert dorthin alles nebeneinander.
    #
    ZIELE = ("music", "recordings")

    def usb_browse(self, pfad: str = "", ziel: str = "music") -> dict | None:
        """
        Was auf dem Stick liegt - gefiltert nach dem gewählten Ziel.

        Das Ziel entscheidet, was verwendbar ist: In die
        Musikbibliothek gehört, was ffmpeg spielt, in die Aufnahmen
        XRacks eigenes Wave64. Unbrauchbares wird trotzdem aufgeführt,
        nur gekennzeichnet (siehe UsbStorage.browse).
        """

        return self.usb_storage.browse(
            pfad,
            endungen=(
                ENDUNGEN_AUFNAHMEN if ziel == "recordings"
                else ENDUNGEN_MUSIK
            ),
        )

    def start_usb_import(
        self,
        quellen: list[str],
        ziel: str,
        ordner: str = "",
    ) -> tuple[bool, str]:
        """
        Holt Dateien und Ordner vom Stick auf das Gerät.

        Läuft im Hintergrund: Ein Album sind schnell ein paar hundert
        Megabyte, und auf einer SD-Karte dauert das. Der Fortschritt
        lässt sich über get_usb_import_status() abfragen.
        """

        if not quellen:
            return False, "Nichts ausgewählt."

        if ziel not in self.ZIELE:
            return False, "Unbekanntes Ziel."

        if not self.usb_storage.connected:
            return False, "Kein USB-Stick angeschlossen."

        if ziel == "recordings":
            zielordner = Path(self.recorder.writer.directory)
            zielordner.mkdir(parents=True, exist_ok=True)
            endungen = ENDUNGEN_AUFNAHMEN
            flach = True

        else:

            zielordner = self.music_library.resolve(ordner)

            if zielordner is None or not zielordner.is_dir():
                return False, "Der Zielordner gibt es nicht."

            endungen = ENDUNGEN_MUSIK
            flach = False

        #
        # Platz prüfen, BEVOR etwas kopiert wird.
        #
        # Eine halb kopierte Datei auf einer vollen Karte ist der
        # unangenehmste Ausgang: Sie sieht aus wie eine ganze. Der
        # Zuschlag von zehn Prozent ist kein Aberglaube, sondern
        # Abstand - eine Karte, die exakt bis zum letzten Byte
        # vollläuft, bringt auch die Aufnahme zum Stehen.
        #
        gebraucht = self.usb_storage.groesse_von(quellen, endungen)

        frei = self._freier_platz(zielordner)

        if frei and gebraucht * 1.1 > frei:
            return False, (
                f"Zu wenig Platz: {gebraucht // (1024 * 1024)} MB werden "
                f"gebraucht, {frei // (1024 * 1024)} MB sind frei."
            )

        with self._usb_import_lock:

            if self.usb_import_state["active"]:
                return False, "Es läuft bereits ein Kopiervorgang."

            self.usb_import_state = {
                "active": True,
                "file": "",
                "copied": 0,
                "total": gebraucht,
                "success": None,
                "error": "",
                "report": None,
            }

        thread = threading.Thread(
            target=self._run_usb_import,
            args=(quellen, zielordner, endungen, flach),
            daemon=True,
        )
        thread.start()

        return True, "started"


    def _freier_platz(self, ordner: Path) -> int:
        """Freier Platz am Zielort, in Byte (0 = unbekannt)."""

        try:
            stand = shutil.disk_usage(ordner)

        except OSError:
            return 0

        return stand.free


    def _run_usb_import(
        self,
        quellen: list[str],
        ziel: Path,
        endungen,
        flach: bool,
    ) -> None:

        def fortschritt(kopiert: int, gesamt: int, name: str) -> None:

            with self._usb_import_lock:
                self.usb_import_state["copied"] = kopiert
                self.usb_import_state["total"] = gesamt
                self.usb_import_state["file"] = name

        try:

            bericht = self.usb_storage.hereinkopieren(
                quellen,
                ziel,
                endungen=endungen,
                flach=flach,
                on_progress=fortschritt,
            )

            with self._usb_import_lock:
                self.usb_import_state["success"] = (
                    bericht["fehlgeschlagen"] == 0
                )
                self.usb_import_state["report"] = bericht

                if bericht["fehlgeschlagen"]:
                    self.usb_import_state["error"] = (
                        f"{bericht['fehlgeschlagen']} Datei(en) konnten "
                        f"nicht kopiert werden."
                    )

            self.logger.info(
                "Vom USB-Stick geholt: %d kopiert, %d übersprungen, "
                "%d fehlgeschlagen (Ziel: %s)",
                bericht["kopiert"],
                bericht["uebersprungen"],
                bericht["fehlgeschlagen"],
                ziel,
            )

        except Exception as fehler:

            self.logger.exception(
                "Kopieren vom USB-Stick fehlgeschlagen: %s", fehler
            )

            with self._usb_import_lock:
                self.usb_import_state["success"] = False
                self.usb_import_state["error"] = "Unerwarteter Fehler."

        finally:

            with self._usb_import_lock:
                self.usb_import_state["active"] = False


    def get_usb_import_status(self) -> dict:
        """Fortschritt und Ergebnis des Holens vom Stick."""

        with self._usb_import_lock:
            return dict(self.usb_import_state)


    def eject_usb(self) -> tuple[bool, str]:
        """
        Hängt den USB-Stick sicher aus. Lehnt ab, solange noch ein
        Kopiervorgang läuft.
        """

        with self._usb_copy_lock:
            if self.usb_copy_state["active"]:
                return False, "busy"

        #
        # Auch in die andere Richtung: Ein Stick, der mitten im Holen
        # ausgehaengt wird, hinterlaesst halbe Dateien auf dem Geraet.
        #
        with self._usb_import_lock:
            if self.usb_import_state["active"]:
                return False, "busy"

        return self.usb_storage.eject()
