"""
XRack application.
"""

from core.configuration import Configuration
from core.log import create_logger
from core.status import SystemStatus
from audio.audio_manager import AudioManager
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
        
        self.audio = AudioManager()
        
    def update_status(self) -> None:
        """Aktualisiert den aktuellen Systemstatus."""
        
        self.audio.scan()
        device = self.audio.get_default_device()

        if device is not None:
            self.status.audio_device = device.name
            self.status.audio_connected = True
        else:
            self.status.audio_device = "Kein Audio-Interface"
            self.status.audio_connected = False

        self.status.hostname = platform.node()

        self.status.cpu = round(psutil.cpu_percent(interval=0), 1)

        self.status.ram = round(psutil.virtual_memory().percent, 1)

        self.status.disk = round(psutil.disk_usage("/").percent, 1)

        uptime = int(psutil.boot_time())

        self.status.uptime = str(
            int((time.time() - psutil.boot_time()) // 60)
        ) + " min"
