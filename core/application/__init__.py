"""
XRack application.

Die Klasse ist nach Bereichen auf Mixins verteilt - 74 Methoden in
einer Datei waren nicht mehr auffindbar. Bewusst Mixins und keine
Unterobjekte: So bleibt jede Aufrufstelle unveraendert
(application.set_console_fader(...) statt
application.pult.set_console_fader(...)), und der Umbau ist eine reine
Verschiebung. Ehrlicherweise verbessert das die Auffindbarkeit, nicht
die Kopplung - die Mixins teilen sich weiterhin denselben Zustand.

Hier bleibt, was die Teile zusammenhaelt: der Aufbau aller Bausteine
und der Systemstatus, den das Dashboard im Sekundentakt abfragt.
"""

from pathlib import Path

from core.configuration import Configuration, ALLOWED_SAMPLE_RATES
from core.log import create_logger
from core.status import SystemStatus, RecorderState
from audio.audio_manager import AudioManager
from audio.audio_core import AudioCore
from audio.audio_playback_backend import AudioPlaybackBackend
from recorder.recorder import Recorder
from player.player import Player
from player.music_library import MusicLibrary
from player.music_player import MusicPlayer
from player.bluetooth_player import BluetoothPlayer
from core.system_control import SystemControl
from core.wlan_control import WlanControl, SHARE_CONNECTION
from core.bluetooth_control import BluetoothControl
from core.usb_storage import UsbStorage
from core.updater import Updater
from core.console_control import ConsoleControl, MIN_DB
from core.diagnostics import Diagnostics
from core.state_store import StateStore
from core.dmx_control import DmxControl
from lighting.store import LightingStore
from core.pin import hash_pin, verify_pin
from core.stem_combiner import combine_stems, StemCombineError
import getpass
import ipaddress
import platform
import psutil
import re
import threading
import time

from core.application.audio import AudioMixin
from core.application.aufnahme import AufnahmeMixin
from core.application.bluetooth import BluetoothMixin
from core.application.einstellungen import EinstellungenMixin
from core.application.licht import LichtMixin
from core.application.musik import MusikMixin
from core.application.netzwerk import NetzwerkMixin
from core.application.pult import PultMixin
from core.application.usb import UsbMixin
from core.application.wartung import WartungMixin


class Application(
    AudioMixin,
    AufnahmeMixin,
    BluetoothMixin,
    EinstellungenMixin,
    LichtMixin,
    MusikMixin,
    NetzwerkMixin,
    PultMixin,
    UsbMixin,
    WartungMixin,
):
    """Main XRack application."""

    def __init__(self) -> None:
        self.config = Configuration()
        self.config.load()

        self.logger = create_logger(
            self.config.data.logging.level
        )

        self.status = SystemStatus()

        self.state_store = StateStore(
            Path("config/state.json")
        )

        self.audio_manager = AudioManager()

        self.audio_core = AudioCore()

        self.audio_manager.scan()

        self.selected_audio_device = None

        self.record_channels = self.state_store.get(
            "record_channels",
            18,
        )

        self.music_channel_preference = self.state_store.get(
            "music_channel",
            1,
        )

        self.record_name_prefix = self.state_store.get(
            "record_name_prefix",
            "Soundcheck",
        )

        self.bluetooth_channel_preference = self.state_store.get(
            "bluetooth_channel",
            1,
        )

        #
        # Die Konsolen-IP, für die zuletzt erfolgreich eine
        # Weiterleitungsregel gesetzt wurde - siehe
        # _reconcile_port_forward(). None bedeutet "aktuell keine Regel
        # gesetzt".
        #
        # Ob überhaupt weitergeleitet werden soll, wird bewusst nicht
        # gemerkt, sondern aus dem Zustand des Freigabe-Profils
        # abgeleitet - so können Anzeige und Wirklichkeit nicht
        # auseinanderlaufen. Ein früher hier gespeicherter Schlüssel
        # "port_forward_enabled" in config/state.json wird dadurch
        # gegenstandslos und einfach ignoriert.
        #
        self._port_forward_applied_ip: str | None = None

        self.recorder = Recorder(
            self.audio_core.backend
        )

        self.player = Player(
            AudioPlaybackBackend()
        )

        self.music_library = MusicLibrary(
            Path(self.config.data.music.directory)
        )

        self.music_player = MusicPlayer(
            AudioPlaybackBackend(),
            self.music_library,
        )

        self.system_control = SystemControl()

        self.wlan_control = WlanControl()

        self.bluetooth_control = BluetoothControl()

        self.usb_storage = UsbStorage()

        self.updater = Updater(self.usb_storage)

        self.console_control = ConsoleControl()

        self.dmx_control = DmxControl()

        self.lighting_store = LightingStore(self.state_store)

        #
        # Der aktuelle Lichtzustand: Lampen-Kennung -> Kanalwerte,
        # relativ zum ersten Kanal der Lampe. Nur im Arbeitsspeicher -
        # nach einem Neustart ist es dunkel, bis jemand eine Szene
        # aufruft.
        #
        self.light_values: dict = {}

        #
        # Die Helligkeit je Lampe, getrennt von den Farbwerten: Dimmen
        # ist nicht umkehrbar, deshalb bleiben die gemerkten Werte
        # ungedimmt und die Helligkeit kommt erst beim Senden dazu.
        #
        self.light_brightness: dict = {}

        self._usb_copy_lock = threading.Lock()

        self.usb_copy_state = {
            "active": False,
            "filename": "",
            "copied": 0,
            "total": 0,
            "success": None,
            "already_exists": False,
        }

        self._stem_combine_lock = threading.Lock()

        self.stem_combine_state = {
            "active": False,
            "success": None,
            "error": "",
            "filename": "",
        }

        self.bluetooth_player = BluetoothPlayer(
            AudioPlaybackBackend(),
            self.bluetooth_control,
        )

        devices = self.audio_manager.get_devices()

        if devices:

            #
            # Zuletzt gewähltes Gerät wiederfinden, falls es noch
            # angeschlossen ist - sonst das erste gefundene Gerät.
            #

            saved_device_id = self.state_store.get("audio_device_id")

            initial_device = next(
                (
                    device
                    for device in devices
                    if device.id == saved_device_id
                ),
                devices[0],
            )

            self.selected_audio_device = initial_device
            self.logger.info("Initiales Audiogerät wird geöffnet...")
            self.select_audio_device(
                self.selected_audio_device.id
            )
            self.logger.info("Initiales Audiogerät geöffnet.")
            self.logger.info(
                "Ausgewähltes Gerät: %s",
                self.selected_audio_device.description,
            )

        #
        # Bluetooth ist eine bewusst optionale Funktion (für den
        # Live-Einsatz nur bedingt geeignet) - deshalb bei jedem
        # Systemstart immer aus, unabhängig vom Zustand vor einem
        # Neustart. Manche Systeme (BlueZ-"AutoEnable") schalten den
        # Adapter beim Booten von selbst wieder ein - das hier stellt
        # sicher, dass der Zustand im Webinterface ("Aus") und der
        # tatsächliche Adapter-Zustand übereinstimmen. Wer Bluetooth
        # nutzen möchte, schaltet es im Dashboard bewusst wieder ein.
        #

        if self.bluetooth_control.available:
            self.bluetooth_control.set_power(False)

        #
        # iptables-Regeln überleben keinen Neustart, die gemerkte
        # Einstellung dagegen schon. Ein einmaliger Versuch beim Start
        # reicht aber nicht: Die Konsole hat über die gerade erst
        # hochgefahrene Freigabe noch keine DHCP-Lease, die Konsolen-IP
        # ist also noch unbekannt. Darum gleicht ein Hintergrund-Thread
        # den gewünschten mit dem tatsächlich gesetzten Zustand ab und
        # holt die Regel nach, sobald die IP auftaucht - und erneuert
        # sie, falls die Konsole später eine andere Adresse bekommt.
        #
        self._port_forward_thread = threading.Thread(
            target=self._port_forward_loop,
            daemon=True,
        )
        self._port_forward_thread.start()

        #
        # Die systemd-Unit des Access Points auf den Stand des Codes
        # bringen.
        #
        # Sie wird sonst nur beim Anlegen des Access Points
        # geschrieben. Ein Update bringt zwar den neuen Text mit,
        # fasst die Datei in /etc aber nicht an - neue
        # ExecStartPre-Zeilen erreichen ein laufendes Geraet also nie.
        #
        # Genau hier ist der richtige Ort: nach einem Update laeuft
        # dieser Code neu, waehrend der Updater selbst noch der alte
        # war (xrack-update.py startet sich vor dem Kopieren neu).
        #
        # Darf folgenlos scheitern - ohne Access Point gibt es nichts
        # zu tun, und ein Fehlschlag soll den Start nicht aufhalten.
        #
        try:
            self.wlan_control.ensure_hostapd_unit()
        except Exception as exc:
            self.logger.warning(
                "Access-Point-Unit konnte nicht geprüft werden: %s", exc
            )

        #
        # Diagnose-Aufzeichnung. Erst hier angelegt, weil sie auf
        # Recorder/Player zugreift, um deren Zustand mitzuschreiben.
        # Der Schalter ist absichtlich persistiert: Der Fehler, für den
        # sie gebaut wurde, tritt sporadisch auf - müsste man sie nach
        # jedem Neustart neu einschalten, wäre sie nutzlos.
        #
        self.diagnostics = Diagnostics(self)

        if self.state_store.get("diagnostics_enabled", False):
            self.diagnostics.start()


    def update_status(self) -> None:
        """Aktualisiert den aktuellen Systemstatus."""
        
        device = self.selected_audio_device

        if device is not None:
            self.status.audio_device = device.name
            self.status.selected_audio_device = device.id
            self.status.audio_connected = True
            self.status.audio_channels = device.channels
            self.status.audio_sample_rate = self.mixer_sample_rate
            self.status.audio_sample_bits = device.sample_bits
            self.status.audio_formats = device.formats
            self.status.audio_core_open = self.audio_core.opened
        else:
            self.status.audio_device = "Kein Audio-Interface"
            self.status.audio_connected = False
            self.status.selected_audio_device = ""
            self.status.audio_channels = 0
            self.status.audio_sample_rate = 0
            self.status.audio_sample_bits = 0
            self.status.audio_formats = []
            self.status.audio_core_open = self.audio_core.opened

        self.status.hostname = platform.node()

        self.status.cpu = round(psutil.cpu_percent(interval=0), 1)

        self.status.ram = round(psutil.virtual_memory().percent, 1)

        self.status.disk = round(psutil.disk_usage("/").percent, 1)

        self.status.uptime = str(
            int((time.time() - psutil.boot_time()) // 60)
        ) + " min"
        
        #
        # Recorder
        #

        self.status.buffer_count = self.recorder.buffer_count

        self.status.bytes_written = self.recorder.bytes_written

        self.status.mb_written = round(
            self.recorder.mb_written,
            2,
        )

        self.status.current_filename = (
            self.recorder.current_filename
        )
        
        self.status.duration = round(
            self.recorder.duration,
            1,
        )
        
        if self.recorder.recording:
            self.status.recorder = RecorderState.RECORDING
        elif self.player.playing:
            self.status.recorder = RecorderState.PLAYBACK
        elif self.recorder.monitoring:
            self.status.recorder = RecorderState.MONITORING
        else:
            self.status.recorder = RecorderState.IDLE

        self.status.recording = (
            self.recorder.recording
        )

        self.status.recorder_monitoring = (
            self.recorder.monitoring
        )

        self.status.recorder_levels = (
            self.recorder.levels
        )

        #
        # Soundcheck-Wiedergabe
        #

        self.status.playback_active = self.player.playing

        self.status.playback_filename = (
            self.player.current_filename
        )

        self.status.playback_duration = round(
            self.player.duration,
            1,
        )

        self.status.playback_channels = self.player.channels

        #
        # Musikspieler
        #

        self.status.music_playing = self.music_player.playing

        self.status.music_paused = self.music_player.paused

        self.status.music_track = self.music_player.current_track

        self.status.music_track_title = self.music_player.current_track_title

        self.status.music_track_artist = self.music_player.current_track_artist

        self.status.music_folder_mode = self.music_player.folder_mode

        self.status.music_channels = self.music_player.channels

        self.status.music_start_channel = self.music_player.start_channel

        self.status.music_preferred_start_channel = (
            self.music_channel_preference
        )

        #
        # Bluetooth (Status-Werte ohne bluetoothctl-Aufruf - reine
        # Python-Eigenschaften des Überwachungs-Threads, deshalb
        # unbedenklich im schnellen 1s-Statuspolling).
        #

        self.status.bluetooth_streaming = self.bluetooth_player.streaming

        self.status.bluetooth_device_name = (
            self.bluetooth_player.connected_device_name
        )

        self.status.music_position = round(
            self.music_player.track_position,
            1,
        )

        self.status.music_duration = round(
            self.music_player.track_duration,
            1,
        )

        self.status.audio = (
            self.status.audio_connected
            and self.status.audio_core_open
        )

        self.status.usb_connected = self.usb_storage.connected
        
        self.status.recordings = (
            self.recorder.recordings
        )
        
        self.status.record_channels = (
            self.record_channels
        )
        
        self.status.record_sample_rate = (
        self.recorder.writer.sample_rate
        )

        self.status.record_bits_per_sample = (
            self.recorder.writer.bits_per_sample
        )

                    
    def refresh(self) -> None:
        """
        Aktualisiert den Zustand der Anwendung.
        """

        self.audio_manager.scan()

        self.update_status()
