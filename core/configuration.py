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


class Configuration:
    """Loads and stores the application configuration."""

    def __init__(self, filename: str = "config/default.yaml") -> None:
        self._filename = Path(filename)
        self._config: AppConfig | None = None

    def load(self) -> None:
        """Load and validate the configuration."""

        with self._filename.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file)

        self._config = AppConfig.model_validate(data)

    @property
    def data(self) -> AppConfig:
        """Return validated configuration."""

        if self._config is None:
            raise RuntimeError("Configuration has not been loaded.")

        return self._config
