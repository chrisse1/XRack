"""
XRack application.
"""

from pathlib import Path

from core.configuration import Configuration
from core.log import create_logger
from core.status import SystemStatus, RecorderState
from audio.audio_manager import AudioManager
from audio.audio_core import AudioCore
from audio.audio_playback_backend import AudioPlaybackBackend
from recorder.recorder import Recorder
from player.player import Player
from player.music_library import MusicLibrary
from player.music_player import MusicPlayer
from core.system_control import SystemControl
from core.wlan_control import WlanControl
from core.state_store import StateStore
import platform
import psutil
import time

class Application:
    """Main XRack application."""

    def __init__(self) -> None:
        self.config = Configuration()
        self.config.load()

        self.logger = create_logger(
            self.config.data.logging.level
        )

        self.status = SystemStatus()

        self.state_store = StateStore(
            Path("config/state.json")
        )

        self.audio_manager = AudioManager()

        self.audio_core = AudioCore()

        self.audio_manager.scan()

        self.selected_audio_device = None

        self.record_channels = self.state_store.get(
            "record_channels",
            18,
        )

        self.music_channel_preference = self.state_store.get(
            "music_channel",
            1,
        )

        self.record_name_prefix = self.state_store.get(
            "record_name_prefix",
            "Soundcheck",
        )

        self.recorder = Recorder(
            self.audio_core.backend
        )

        self.player = Player(
            AudioPlaybackBackend()
        )

        self.music_library = MusicLibrary(
            Path(self.config.data.music.directory)
        )

        self.music_player = MusicPlayer(
            AudioPlaybackBackend(),
            self.music_library,
        )

        self.system_control = SystemControl()

        self.wlan_control = WlanControl()

        devices = self.audio_manager.get_devices()

        if devices:

            #
            # Zuletzt gewähltes Gerät wiederfinden, falls es noch
            # angeschlossen ist - sonst das erste gefundene Gerät.
            #

            saved_device_id = self.state_store.get("audio_device_id")

            initial_device = next(
                (
                    device
                    for device in devices
                    if device.id == saved_device_id
                ),
                devices[0],
            )

            self.selected_audio_device = initial_device
            self.logger.info("Initiales Audiogerät wird geöffnet...")
            self.select_audio_device(
                self.selected_audio_device.id
            )
            self.logger.info("Initiales Audiogerät geöffnet.")
            self.logger.info(
                "Ausgewähltes Gerät: %s",
                self.selected_audio_device.description,
            )
            
    def update_status(self) -> None:
        """Aktualisiert den aktuellen Systemstatus."""
        
        device = self.selected_audio_device

        if device is not None:
            self.status.audio_device = device.name
            self.status.selected_audio_device = device.id
            self.status.audio_connected = True
            self.status.audio_channels = device.channels
            self.status.audio_sample_rate = device.sample_rate
            self.status.audio_sample_bits = device.sample_bits
            self.status.audio_formats = device.formats
            self.status.audio_core_open = self.audio_core.opened
        else:
            self.status.audio_device = "Kein Audio-Interface"
            self.status.audio_connected = False
            self.status.selected_audio_device = ""
            self.status.audio_channels = 0
            self.status.audio_sample_rate = 0
            self.status.audio_sample_bits = 0
            self.status.audio_formats = []
            self.status.audio_core_open = self.audio_core.opened

        self.status.hostname = platform.node()

        self.status.cpu = round(psutil.cpu_percent(interval=0), 1)

        self.status.ram = round(psutil.virtual_memory().percent, 1)

        self.status.disk = round(psutil.disk_usage("/").percent, 1)

        self.status.uptime = str(
            int((time.time() - psutil.boot_time()) // 60)
        ) + " min"
        
        #
        # Recorder
        #

        self.status.buffer_count = self.recorder.buffer_count

        self.status.bytes_written = self.recorder.bytes_written

        self.status.mb_written = round(
            self.recorder.mb_written,
            2,
        )

        self.status.current_filename = (
            self.recorder.current_filename
        )
        
        self.status.duration = round(
            self.recorder.duration,
            1,
        )
        
        if self.recorder.recording:
            self.status.recorder = RecorderState.RECORDING
        elif self.player.playing:
            self.status.recorder = RecorderState.PLAYBACK
        elif self.recorder.monitoring:
            self.status.recorder = RecorderState.MONITORING
        else:
            self.status.recorder = RecorderState.IDLE

        self.status.recording = (
            self.recorder.recording
        )

        self.status.recorder_monitoring = (
            self.recorder.monitoring
        )

        self.status.recorder_levels = (
            self.recorder.levels
        )

        #
        # Soundcheck-Wiedergabe
        #

        self.status.playback_active = self.player.playing

        self.status.playback_filename = (
            self.player.current_filename
        )

        self.status.playback_duration = round(
            self.player.duration,
            1,
        )

        self.status.playback_channels = self.player.channels

        #
        # Musikspieler
        #

        self.status.music_playing = self.music_player.playing

        self.status.music_paused = self.music_player.paused

        self.status.music_track = self.music_player.current_track

        self.status.music_track_title = self.music_player.current_track_title

        self.status.music_track_artist = self.music_player.current_track_artist

        self.status.music_folder_mode = self.music_player.folder_mode

        self.status.music_channels = self.music_player.channels

        self.status.music_start_channel = self.music_player.start_channel

        self.status.music_preferred_start_channel = (
            self.music_channel_preference
        )

        self.status.music_position = round(
            self.music_player.track_position,
            1,
        )

        self.status.music_duration = round(
            self.music_player.track_duration,
            1,
        )

        self.status.audio = (
            self.status.audio_connected
            and self.status.audio_core_open
        )
        
        self.status.recordings = (
            self.recorder.recordings
        )
        
        self.status.record_channels = (
            self.record_channels
        )
        
        self.status.record_sample_rate = (
        self.recorder.writer.sample_rate
        )

        self.status.record_bits_per_sample = (
            self.recorder.writer.bits_per_sample
        )
                    
    def refresh(self) -> None:
        """
        Aktualisiert den Zustand der Anwendung.
        """

        self.audio_manager.scan()

        self.update_status()

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
        )

        self.state_store.set(
            "record_channels",
            self.record_channels,
        )

        return True
    
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

    def set_language(self, language: str) -> bool:
        """
        Ändert die Sprache der Weboberfläche. Wirkt sofort, ohne
        Neustart - Übersetzungen werden bei jedem Seitenaufruf neu
        anhand der aktuellen Konfiguration geladen.
        """

        if language not in ("de", "en"):
            return False

        self.config.set_override("application", "language", language)

        self.config.data.application.language = language

        return True

    def set_port(self, port: int) -> bool:
        """
        Ändert den Port des Webinterfaces. Wird dauerhaft
        gespeichert, wirkt aber erst nach einem Dienst-Neustart
        (siehe restart_service()).
        """

        if not 1 <= port <= 65535:
            return False

        self.config.set_override("server", "port", port)

        self.config.data.server.port = port

        return True

    def get_wlan_status(self) -> dict:
        """
        Liefert den aktuellen (nicht-geheimen) WLAN-/Bridge-Status
        fürs Einstellungs-Modal.
        """

        return self.wlan_control.get_status()

    def set_home_wifi(self, ssid: str, password: str) -> tuple[bool, str]:
        """
        Setzt SSID/Passwort der Heimnetz-WLAN-Verbindung neu.
        """

        if not 1 <= len(ssid) <= 32:
            return False, "Ungültige SSID."

        if not 8 <= len(password) <= 63:
            return False, "Passwort muss 8-63 Zeichen lang sein."

        return self.wlan_control.set_home_wifi(ssid, password)

    def set_ap_wifi(self, ssid: str, password: str) -> tuple[bool, str]:
        """
        Setzt SSID/Passwort des Access Points neu.
        """

        if not 1 <= len(ssid) <= 32:
            return False, "Ungültige SSID."

        if not 8 <= len(password) <= 63:
            return False, "Passwort muss 8-63 Zeichen lang sein."

        return self.wlan_control.set_ap_wifi(ssid, password)

    def set_bridge(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet die Ethernet+Access-Point-Bridge an oder aus.
        """

        return self.wlan_control.set_bridge(enabled)
