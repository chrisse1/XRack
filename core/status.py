"""
System status management for XRack.
"""

from enum import Enum

from pydantic import BaseModel


class RecorderState(str, Enum):
    """
    Recorder states. Die Werte sind sprachneutrale Token - das
    Frontend übersetzt sie anhand der aktiven Sprache (siehe
    web/i18n.py).
    """

    IDLE = "idle"
    RECORDING = "recording"
    PLAYBACK = "playback"
    MONITORING = "monitoring"

    #
    # Kein Audiogerät offen. Eigener Zustand, weil IDLE als "bereit"
    # angezeigt wird - und bereit ist XRack dann gerade nicht. Die
    # Karte meldete das lange trotzdem, samt Knopf, der eine Aufnahme
    # ohne Soundkarte startete.
    #
    NO_DEVICE = "no_device"


class SystemStatus(BaseModel):
    """Current XRack system status."""

    audio: bool = False
    recorder: RecorderState = RecorderState.IDLE
    cpu: float = 0.0
    ram: float = 0.0
    disk: float = 0.0
    hostname: str = ""
    uptime: str = ""
    audio_device: str = "Kein Audio-Interface"
    record_channels: int = 18

    #
    # Der erste aufgenommene Kanal (1-basiert). Aufgenommen wird ein
    # Fenster, nicht immer der Anfang.
    #
    record_start_channel: int = 1
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
    recorder_monitoring: bool = False
    recorder_levels: list[float] = []

    #
    # Stimmt die eingestellte Samplerate mit der gemessenen ueberein?
    # None heisst "noch kein Urteil" - siehe recorder/rate_check.py.
    #
    rate_plausible: bool | None = None
    rate_measured: float = 0.0
    rate_likely: int = 0

    #
    # Wie lange der freie Platz noch reicht (Sekunden) und ob eine
    # Aufnahme deswegen beendet wurde.
    #
    disk_seconds_left: float = 0.0
    disk_stopped: bool = False

    playback_active: bool = False
    playback_filename: str = ""
    playback_duration: float = 0.0
    playback_channels: int = 0

    music_playing: bool = False
    music_paused: bool = False
    music_track: str = ""
    music_track_title: str = ""
    music_track_artist: str = ""
    music_folder_mode: bool = False
    music_channels: int = 2
    music_start_channel: int = 0
    music_position: float = 0.0
    music_duration: float = 0.0
    music_preferred_start_channel: int = 1

    #
    # Die Karte zeigt entweder den Musikspieler oder das Ueben.
    #
    player_mode: str = "music"
    practice_repeat: bool = False

    #
    # practice_record ist der SCHALTER (soll mitgeschnitten werden),
    # practice_recording der ZUSTAND (dieser Uebungslauf nimmt gerade
    # auf). Zwei Dinge, die leicht zusammenfallen - und dann wuerde
    # der Schalter beim Stoppen umspringen.
    #
    practice_record: bool = False
    practice_recording: bool = False

    #
    # Die Aufnahmen, die sich zum Uebungsmix dazulegen lassen.
    #
    practice_takes: list[str] = []
    practice_mixes: list[str] = []

    bluetooth_streaming: bool = False
    bluetooth_device_name: str = ""

    usb_connected: bool = False
