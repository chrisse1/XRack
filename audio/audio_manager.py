import re
import subprocess

from audio.models import AudioDevice


class AudioManager:
    DEVICE_PATTERN = re.compile(
    r"(?:Karte|card)\s+(\d+):.*?\[(.*?)\],\s+(?:Gerät|device)\s+(\d+):",
    re.IGNORECASE,
    )
    
    IGNORE_PREFIXES = (
        "Warning:",
        "arecord:",
        "Available formats",
        "»HW Params«",
        "-",
    )

    def __init__(self):
        self.devices: list[AudioDevice] = []

    def scan(self) -> None:
        """
        Scan the system for available audio devices.
        """

        self.devices.clear()

        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
        )

        for line in result.stdout.splitlines():

            match = self.DEVICE_PATTERN.search(line)

            if match is None:
                continue

            device = AudioDevice(
                card=int(match.group(1)),
                device=int(match.group(3)),
                name=match.group(2),
            )

            self.probe_device(device)

            self.devices.append(device)
            
    def _parse_formats(self, value: str) -> list[str]:
        """
        Parse supported sample formats.
        """

        return value.split()
            
    def probe_device(self, device: AudioDevice) -> None:
        """
        Read additional information about an audio device.
        """

        result = subprocess.run(
            [
                "arecord",
                "--dump-hw-params",
                "-D",
                f"hw:{device.card},{device.device}",
            ],
            capture_output=True,
            text=True,
        )

        output = result.stdout + "\n" + result.stderr

        for line in output.splitlines():

            line = line.strip()

            if ":" not in line:
                continue

            if line.startswith(self.IGNORE_PREFIXES):
                continue

            key, value = line.split(":", 1)

            device.properties[key.strip()] = value.strip()

        # Erst nach dem Einlesen aller Eigenschaften
        if "CHANNELS" in device.properties:
            device.channels = self._parse_max_value(
                device.properties["CHANNELS"]
            )
        
        if "RATE" in device.properties:
            device.sample_rate = self._parse_max_value(
                device.properties["RATE"]
            )
            
        if "FORMAT" in device.properties:
            device.formats = self._parse_formats(
                device.properties["FORMAT"]
            )
            
        if "SAMPLE_BITS" in device.properties:
            device.sample_bits = self._parse_max_value(
                device.properties["SAMPLE_BITS"]
            )
                                
    def _parse_max_value(self, value: str) -> int:
        """
        Parse an ALSA value and return the maximum numeric value.

        Examples:
            "2"          -> 2
            "[1 18]"     -> 18
            "[44100 48000]" -> 48000
        """

        value = value.strip()

        if value.startswith("[") and value.endswith("]"):
            values = [int(v) for v in value[1:-1].split()]
            return max(values)

        return int(value)

    def get_devices(self) -> list[AudioDevice]:
        return self.devices

    def get_default_device(self) -> AudioDevice | None:
        if self.devices:
            return self.devices[0]

        return None
