"""
Update, Diagnose-Aufzeichnung, Herunterfahren und Neustart.
"""

import getpass


class WartungMixin:
    """
    Update, Diagnose-Aufzeichnung, Herunterfahren und Neustart.

    Teil von Application - siehe core/application/__init__.py.
    """

    def get_update_info(self) -> dict:
        """
        Beschreibt fürs Einstellungen-Modal, ob ein Update bereitliegt,
        und liefert den Fortschritt eines laufenden Vorgangs gleich mit.
        """

        info = self.updater.get_available()

        info["version"] = self.config.data.application.version

        #
        # Über get_update_status(), nicht direkt über den Updater -
        # sonst käme ein längst quittiertes Ergebnis hier wieder durch.
        #
        info["status"] = self.get_update_status()

        return info


    def start_update(
        self, source: str = "usb", allow_downgrade: bool = False
    ) -> tuple[bool, str]:
        """
        Startet das Update - entweder aus dem Internet ("github") oder
        von dem auf dem USB-Stick gefundenen Paket ("usb").

        Läuft im Hintergrund weiter, auch über den Neustart des
        Dienstes hinweg - der Fortschritt kommt über
        get_update_status().
        """

        if source not in ("usb", "github"):
            return False, "Unbekannte Update-Quelle."

        if self.recorder.recording:
            return False, "Während einer Aufnahme kann nicht aktualisiert werden."

        if self.player.playing or self.music_player.playing:
            return False, "Während der Wiedergabe kann nicht aktualisiert werden."

        return self.updater.start(
            service_user=getpass.getuser(),
            port=self.config.data.server.port,
            source=source,
            repository=self.config.data.update.repository,
            branch=self.config.data.update.branch,
            allow_downgrade=allow_downgrade,
        )


    def get_update_status(self) -> dict:
        """
        Liefert den Fortschritt eines laufenden/letzten Updates.

        Ein bereits quittiertes Ergebnis wird zu "idle": Die
        Statusdatei liegt in /var/tmp und bleibt liegen, sonst stünde
        "Update erfolgreich" auch Tage später noch im Modal.
        """

        status = self.updater.get_status()

        if status.get("state") in ("idle", "running", "rolling_back"):
            return status

        if status.get("updated_at") and status["updated_at"] == self.state_store.get(
            "update_result_seen"
        ):
            return {
                "state": "idle",
                "step": "",
                "message": "",
                "needs_install_script": False,
                "needs_dependencies": False,
            }

        return status


    def acknowledge_update(self) -> bool:
        """
        Merkt sich, dass das Ergebnis des letzten Updates gesehen wurde.

        Warum über den eigenen Zustand und nicht durch Löschen der
        Statusdatei: Die schreibt das Update-Skript als root nach
        /var/tmp; der Dienst selbst darf sie gar nicht löschen. Ein
        gemerkter Zeitstempel kommt ohne zusätzliche sudo-Rechte aus
        und lässt ein späteres Update trotzdem wieder anzeigen, weil
        dessen Zeitstempel ein anderer ist.
        """

        status = self.updater.get_status()

        if status.get("state") in ("idle", "running", "rolling_back"):
            return False

        stamp = status.get("updated_at")

        if not stamp:
            return False

        self.state_store.set("update_result_seen", stamp)

        return True


    def get_diagnostics_status(self) -> dict:
        """Zustand der Diagnose-Aufzeichnung fürs Einstellungen-Modal."""

        return self.diagnostics.get_status()


    def set_diagnostics(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet die Diagnose-Aufzeichnung an oder aus und merkt sich
        das über einen Neustart hinweg.
        """

        if enabled:
            self.diagnostics.start()
        else:
            self.diagnostics.stop()

        self.state_store.set("diagnostics_enabled", enabled)

        return True, ""


    def shutdown_system(self) -> bool:
        """
        Fährt den Raspberry Pi herunter.
        """

        return self.system_control.shutdown()


    def restart_service(self) -> bool:
        """
        Startet den XRack-Dienst neu (z.B. damit ein geänderter
        Port wirksam wird).
        """

        return self.system_control.restart_service()
