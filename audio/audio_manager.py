import re
import subprocess

from audio.models import AudioDevice


class AudioManager:
    DEVICE_PATTERN = re.compile(
    r"(?:Karte|card)\s+(\d+):.*?\[(.*?)\],\s+(?:Gerät|device)\s+(\d+):",
    re.IGNORECASE,
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

            self.devices.append(
                AudioDevice(
                    card=int(match.group(1)),
                    device=int(match.group(3)),
                    name=match.group(2),
                )
            )

    def get_devices(self) -> list[AudioDevice]:
        return self.devices

    def get_default_device(self) -> AudioDevice | None:
        if self.devices:
            return self.devices[0]

        return None
