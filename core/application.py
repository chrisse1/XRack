"""
XRack application.
"""

from core.configuration import Configuration
from core.log import create_logger
from core.status import SystemStatus, RecorderState
from audio.audio_manager import AudioManager
from audio.audio_core import AudioCore
from recorder.recorder import Recorder
import platform
import psutil
import time
import re

class Application:
    """Main XRack application."""

    def __init__(self) -> None:
        self.config = Configuration()
        self.config.load()

        self.logger = create_logger(
            self.config.data.logging.level
        )

        self.status = SystemStatus()
        
        self.audio_manager = AudioManager()
        
        self.audio_core = AudioCore()
        
        self.audio_manager.scan()

        self.selected_audio_device = None
        
        self.record_channels = 18
        
        self.recorder = Recorder(
            self.audio_core.backend
        )

        devices = self.audio_manager.get_devices()

        if devices:
            self.selected_audio_device = devices[0]
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

        uptime = int(psutil.boot_time())

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
        else:
            self.status.recorder = RecorderState.IDLE
            
        self.status.recording = (
            self.recorder.recording
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
