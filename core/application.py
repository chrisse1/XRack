"""
XRack application.
"""

from core.configuration import Configuration
from core.log import create_logger
from core.status import SystemStatus
from audio.audio_manager import AudioManager
from audio.audio_core import AudioCore
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

        devices = self.audio_manager.get_devices()

        if devices:
            self.selected_audio_device = devices[0]

            self.select_audio_device(
                self.selected_audio_device.id
            )
            
            self.logger.info(
                "Ausgewähltes Gerät: %s",
                self.selected_audio_device.description,
            )
        
    def update_status(self) -> None:
        """Aktualisiert den aktuellen Systemstatus."""
        
        self.audio_manager.scan()
        device = self.selected_audio_device

        if device is not None:
            self.status.audio_device = device.name
            self.status.audio_connected = True
            self.status.audio_channels = device.channels
            self.status.audio_sample_rate = device.sample_rate
            self.status.audio_sample_bits = device.sample_bits
            self.status.audio_formats = device.formats
            self.status.audio_core_open = self.audio_core.opened
        else:
            self.status.audio_device = "Kein Audio-Interface"
            self.status.audio_connected = False

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
        
    def refresh(self) -> None:
        """
        Aktualisiert den Zustand der Anwendung.
        """

        self.audio_manager.scan()

        self.update_status()
        
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

        self.audio_core.open(device)

        self.logger.info(
            "Audiogerät gewechselt auf %s",
            device.description,
        )

        return True
