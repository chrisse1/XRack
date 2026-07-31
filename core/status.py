"""
System status management for XRack.
"""

from enum import Enum

from pydantic import BaseModel, Field


class RecorderState(str, Enum):
    """Recorder states."""

    IDLE = "bereit"
    RECORDING = "nimmt auf"
    PLAYBACK = "Wiedergabe"


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
    record_channels: int = 18
    record_sample_rate: int = 0
    record_bits_per_sample: int = 0

    selected_audio_device: str = ""
    audio_connected: bool = False
    audio_channels: int = 0
    audio_sample_rate: int = 0
    audio_sample_bits: int = 0
    audio_formats: list[str] = []
    audio_core_open: bool = False
    buffer_count: int = 0
    bytes_written: int = 0
    mb_written: float = 0.0
    current_filename: str = ""
    duration: float = 0.0
    recordings: list[str] = []
    recording: bool = False

    playback_active: bool = False
    playback_filename: str = ""
    playback_duration: float = 0.0
    playback_channels: int = 0
