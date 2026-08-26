"""
USB-Stick: Aufnahmen kopieren und den Stick auswerfen.
"""

import threading

from pathlib import Path


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


    def eject_usb(self) -> tuple[bool, str]:
        """
        Hängt den USB-Stick sicher aus. Lehnt ab, solange noch ein
        Kopiervorgang läuft.
        """

        with self._usb_copy_lock:
            if self.usb_copy_state["active"]:
                return False, "busy"

        return self.usb_storage.eject()
