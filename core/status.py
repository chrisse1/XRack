"""
System status management for XRack.
"""

from enum import Enum

from pydantic import BaseModel


class RecorderState(str, Enum):
    """Recorder states."""

    IDLE = "idle"
    RECORDING = "recording"
    PLAYBACK = "playback"


class PlayerState(str, Enum):
    """Music player states."""

    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"


class SystemStatus(BaseModel):
    """Current XRack system status."""

    audio: bool = False
    recorder: RecorderState = RecorderState.IDLE
    player: PlayerState = PlayerState.IDLE
    device: str | None = None
    cpu: float = 0.0
    ram: float = 0.0
    disk: float = 0.0
    hostname: str = ""
    uptime: str = ""
    audio_device: str = "Kein Audio-Interface"
    audio_connected: bool = False
