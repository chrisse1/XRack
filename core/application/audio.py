"""
Audiointerface: Auswahl, Erkennung, Samplerate des Pults.
"""

from core.configuration import ALLOWED_SAMPLE_RATES


class AudioMixin:
    """
    Audiointerface: Auswahl, Erkennung, Samplerate des Pults.

    Teil von Application - siehe core/application/__init__.py.
    """

    @property
    def mixer_sample_rate(self) -> int:
        """
        Vom Nutzer erklärte Samplerate des angeschlossenen Interfaces
        (siehe set_mixer_sample_rate()).
        """

        return self.config.data.audio.sample_rate


    def set_mixer_sample_rate(self, rate: int) -> bool:
        """
        Setzt die tatsächlich am Interface eingestellte Samplerate.
        XRack kann sie nicht automatisch erkennen (Mischpulte wie die
        X32/XAir-Serie melden über USB immer den vollen unterstützten
        Wertebereich, nicht ihre live konfigurierte Clock) - der
        Nutzer muss sie darum passend zur Hardware auswählen. Wirkt
        sofort, ohne Neustart.
        """

        if rate not in ALLOWED_SAMPLE_RATES:
            return False

        self.config.set_override("audio", "sample_rate", rate)

        self.config.data.audio.sample_rate = rate

        if self.selected_audio_device is not None:

            self.audio_core.close()

            self.audio_core.open(
                self.selected_audio_device,
                self.record_channels,
                rate,
            )

        return True


    def rescan_audio_devices(self) -> None:
        """
        Wird vom "Aktualisieren"-Knopf ausgelöst - erkennt neu
        angeschlossene Audiogeräte. Fragt das gerade aktiv geöffnete
        Gerät dabei nicht per arecord erneut ab (seine Eigenschaften
        ändern sich ohnehin nicht, solange es angeschlossen bleibt) -
        siehe AudioManager.scan()s skip_probe_id.
        """

        self.audio_manager.scan(
            skip_probe_id=(
                self.selected_audio_device.id
                if self.selected_audio_device is not None
                else None
            )
        )


    def select_audio_device(self, device_id: str) -> bool:
        """
        Wählt ein Audiogerät aus.
        """

        device = self.audio_manager.get_device(device_id)

        if device is None:
            self.logger.warning(
                "Audiogerät %s nicht gefunden.",
                device_id,
            )
            return False

        self.audio_core.close()

        self.selected_audio_device = device

        self.logger.info(
            "Selected Audio Device: %s (%s)",
            self.selected_audio_device.name,
            self.selected_audio_device.id,
        )

        self.state_store.set(
            "audio_device_id",
            device.id,
        )

        #
        # Kanalzahl auf das neue Gerät begrenzen
        #

        self.record_channels = min(
            self.record_channels,
            device.channels,
        )

        self.set_record_channels(
            self.record_channels,
        )

        self.logger.info(
            "Audiogerät gewechselt auf %s",
            device.description,
        )
        self.logger.info(
            "AudioCore.max_channels = %d",
            self.audio_core.max_channels,
        )

        self.logger.info(
            "Application.record_channels = %d",
            self.record_channels,
        )

        return True
