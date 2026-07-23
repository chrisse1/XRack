from dataclasses import dataclass, field


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
