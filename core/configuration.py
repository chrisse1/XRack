"""
Configuration management for XRack.

Loads the YAML configuration file and validates it using Pydantic.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel


class ApplicationConfig(BaseModel):
    """Application settings."""

    name: str
    version: str
    language: str = "de"

class ServerConfig(BaseModel):
    host: str
    port: int


class RecordingConfig(BaseModel):
    directory: str


class MusicConfig(BaseModel):
    directory: str


class LoggingConfig(BaseModel):
    level: str


class AppConfig(BaseModel):
    """Complete application configuration."""

    application: ApplicationConfig
    server: ServerConfig
    recording: RecordingConfig
    music: MusicConfig
    logging: LoggingConfig


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Führt `override` rekursiv in `base` ein (z.B. lokale
    Einstellungen über die mitgelieferten Standardwerte legen).
    """

    merged = dict(base)

    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value

    return merged


class Configuration:
    """Loads and stores the application configuration."""

    def __init__(
        self,
        filename: str = "config/default.yaml",
        local_filename: str = "config/local.yaml",
    ) -> None:
        self._filename = Path(filename)
        self._local_filename = Path(local_filename)
        self._config: AppConfig | None = None

    def load(self) -> None:
        """
        Lädt die Konfiguration. `config/local.yaml` (falls vorhanden,
        z.B. von install.sh angelegt) überschreibt dabei einzelne
        Werte aus `config/default.yaml`, etwa Sprache oder Port.
        """

        with self._filename.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

        if self._local_filename.exists():

            with self._local_filename.open("r", encoding="utf-8") as file:
                local_data = yaml.safe_load(file)

            if local_data:
                data = _deep_merge(data, local_data)

        self._config = AppConfig.model_validate(data)

    @property
    def data(self) -> AppConfig:
        """Return validated configuration."""

        if self._config is None:
            raise RuntimeError("Configuration has not been loaded.")

        return self._config

    def set_override(self, section: str, key: str, value) -> None:
        """
        Schreibt einen einzelnen Wert dauerhaft nach
        `config/local.yaml`, ohne andere dort bereits gespeicherte
        Overrides zu verlieren (z.B. Sprache ändern, ohne einen
        zuvor gesetzten Port zu überschreiben).
        """

        local_data: dict = {}

        if self._local_filename.exists():

            with self._local_filename.open("r", encoding="utf-8") as file:
                local_data = yaml.safe_load(file) or {}

        local_data.setdefault(section, {})[key] = value

        with self._local_filename.open("w", encoding="utf-8") as file:
            yaml.safe_dump(local_data, file, allow_unicode=True)
