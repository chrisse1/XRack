"""
Bluetooth-Zuspielung vom Handy.
"""


class BluetoothMixin:
    """
    Bluetooth-Zuspielung vom Handy.

    Teil von Application - siehe core/application/__init__.py.
    """

    def get_bluetooth_status(self) -> dict:
        """
        Liefert den aktuellen Bluetooth-Status fürs Webinterface.
        """

        status = self.bluetooth_control.get_status()

        status["streaming"] = self.bluetooth_player.streaming
        status["preferred_start_channel"] = self.bluetooth_channel_preference

        return status


    def _start_bluetooth_monitor(self) -> None:

        if self.selected_audio_device is None:
            return

        self.logger.info(
            "Bluetooth: Überwachung wird mit Zielkanal-Präferenz %d "
            "gestartet (1-basiert).",
            self.bluetooth_channel_preference,
        )

        self.bluetooth_player.start(
            self.selected_audio_device,
            self.bluetooth_channel_preference - 1,
            self.mixer_sample_rate,
        )


    def set_bluetooth_power(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet den Bluetooth-Adapter (und damit das Lauschen auf
        eingehende Audiostreams) an oder aus.
        """

        success, message = self.bluetooth_control.set_power(enabled)

        if success:
            if enabled:
                self._start_bluetooth_monitor()
            else:
                self.bluetooth_player.stop()

        return success, message


    def start_bluetooth_pairing(self) -> tuple[bool, str]:
        """
        Macht XRack für ein kurzes Zeitfenster koppelbar.
        """

        return self.bluetooth_control.start_pairing()


    def forget_bluetooth_device(self, mac: str) -> tuple[bool, str]:
        """
        Entfernt ein einzelnes gekoppeltes Bluetooth-Gerät.
        """

        return self.bluetooth_control.forget_device(mac)


    def disconnect_bluetooth_device(self, mac: str) -> tuple[bool, str]:
        """
        Trennt die Verbindung zu einem gekoppelten Bluetooth-Gerät,
        ohne die Kopplung selbst aufzuheben.
        """

        return self.bluetooth_control.disconnect_device(mac)


    def set_bluetooth_channel_preference(self, start_channel: int) -> bool:
        """
        Merkt sich das für Bluetooth-Audio gewählte Ziel-Stereopaar
        (1-basiert). Läuft gerade eine Wiedergabe, wird sie kurz neu
        verbunden, damit die Änderung sofort wirkt.
        """

        self.logger.info(
            "Bluetooth: Zielkanal-Präferenz auf %d gesetzt (1-basiert).",
            start_channel,
        )

        self.bluetooth_channel_preference = start_channel

        self.state_store.set(
            "bluetooth_channel",
            start_channel,
        )

        self.bluetooth_player.set_start_channel(start_channel - 1)

        return True
