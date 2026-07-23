from dataclasses import dataclass


@dataclass
class AudioDevice:
    card: int
    device: int
    name: str

    channels: int = 0
    sample_rate: int = 0

    connected: bool = True
