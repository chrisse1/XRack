from dataclasses import dataclass, field
from enum import Enum

class AudioState(str, Enum):
    """Aktueller Zustand des Audio Cores."""

    CLOSED = "closed"
    OPEN = "open"
    RECORDING = "recording"
    PLAYBACK = "playback"
    
class AudioHealth(str, Enum):
    """Diagnose des Audio Cores."""

    NOT_READY = "not_ready"
    READY = "ready"

@dataclass
class AudioDevice:
    card: int
    device: int
    name: str

    channels: int = 0
    sample_rate: int = 0

    connected: bool = True

    properties: dict[str, str] = field(default_factory=dict)
    
    formats: list[str] = field(default_factory=list)
    
    sample_bits: int = 0
    
@dataclass
class DiagnosticItem:
    """
    Einzelnes Ergebnis einer Diagnoseprüfung.
    """

    name: str
    ok: bool
    message: str
