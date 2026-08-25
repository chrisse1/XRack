"""
XRack application.
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
from core.console_control import ConsoleControl
from core.diagnostics import Diagnostics
from core.state_store import StateStore
from core.pin import hash_pin, verify_pin
from core.stem_combiner import combine_stems, StemCombineError
import getpass
import platform
import psutil
import re
import threading
import time

class Application:
    """Main XRack application."""

    #
    # Wie oft die Portweiterleitung abgeglichen wird (Sekunden) - siehe
    # _reconcile_port_forward(). Schnell genug, dass die Konsole nach
    # einem Neustart praktisch sofort erreichbar ist, und selten genug,
    # dass die paar nmcli-/DHCP-Aufrufe nicht ins Gewicht fallen.
    #
    PORT_FORWARD_INTERVAL = 20.0

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

    def set_record_channels(
        self,
        channels: int,
    ) -> bool:
        """
        Setzt die Anzahl der Aufnahmekanäle.
        """

        self.record_channels = channels

        if self.selected_audio_device is None:
            return False

        self.audio_core.close()

        self.audio_core.open(
            self.selected_audio_device,
            self.record_channels,
            self.mixer_sample_rate,
        )

        self.state_store.set(
            "record_channels",
            self.record_channels,
        )

        return True

    @property
    def mixer_sample_rate(self) -> int:
        """
        Vom Nutzer erklärte Samplerate des angeschlossenen Interfaces
        (siehe set_mixer_sample_rate()).
        """

        return self.config.data.audio.sample_rate

    def set_mixer_sample_rate(self, rate: int) -> bool:
        """
        Setzt die tatsächlich am Interface eingestellte Samplerate.
        XRack kann sie nicht automatisch erkennen (Mischpulte wie die
        X32/XAir-Serie melden über USB immer den vollen unterstützten
        Wertebereich, nicht ihre live konfigurierte Clock) - der
        Nutzer muss sie darum passend zur Hardware auswählen. Wirkt
        sofort, ohne Neustart.
        """

        if rate not in ALLOWED_SAMPLE_RATES:
            return False

        self.config.set_override("audio", "sample_rate", rate)

        self.config.data.audio.sample_rate = rate

        if self.selected_audio_device is not None:

            self.audio_core.close()

            self.audio_core.open(
                self.selected_audio_device,
                self.record_channels,
                rate,
            )

        return True

    def rescan_audio_devices(self) -> None:
        """
        Wird vom "Aktualisieren"-Knopf ausgelöst - erkennt neu
        angeschlossene Audiogeräte. Fragt das gerade aktiv geöffnete
        Gerät dabei nicht per arecord erneut ab (seine Eigenschaften
        ändern sich ohnehin nicht, solange es angeschlossen bleibt) -
        siehe AudioManager.scan()s skip_probe_id.
        """

        self.audio_manager.scan(
            skip_probe_id=(
                self.selected_audio_device.id
                if self.selected_audio_device is not None
                else None
            )
        )

    def select_audio_device(self, device_id: str) -> bool:
        """
        Wählt ein Audiogerät aus.
        """

        device = self.audio_manager.get_device(device_id)

        if device is None:
            self.logger.warning(
                "Audiogerät %s nicht gefunden.",
                device_id,
            )
            return False

        self.audio_core.close()

        self.selected_audio_device = device

        self.logger.info(
            "Selected Audio Device: %s (%s)",
            self.selected_audio_device.name,
            self.selected_audio_device.id,
        )

        self.state_store.set(
            "audio_device_id",
            device.id,
        )

        #
        # Kanalzahl auf das neue Gerät begrenzen
        #

        self.record_channels = min(
            self.record_channels,
            device.channels,
        )

        self.set_record_channels(
            self.record_channels,
        )

        self.logger.info(
            "Audiogerät gewechselt auf %s",
            device.description,
        )
        self.logger.info(
            "AudioCore.max_channels = %d",
            self.audio_core.max_channels,
        )

        self.logger.info(
            "Application.record_channels = %d",
            self.record_channels,
        )

        return True

    def start_recording(self) -> bool:
        """
        Startet eine Aufnahme. Lehnt ab, solange gerade eine
        Soundcheck-Wiedergabe läuft - dieselbe Datei würde sonst
        gleichzeitig gelesen und beschrieben, und während des
        Kontrollhörens einer alten Aufnahme aus Versehen eine neue
        zu starten ergibt ohnehin keinen Sinn.
        """

        if self.player.playing:
            return False

        return self.recorder.start(self.record_name_prefix)

    def start_soundcheck(self, filename: str) -> bool:
        """
        Spielt eine Aufnahme auf denselben Kanälen ab,
        auf denen sie aufgenommen wurde ("virtueller Soundcheck").
        """

        if self.selected_audio_device is None:
            return False

        if self.recorder.recording:
            return False

        if self.music_player.playing:
            return False

        path = self.recorder.writer.directory / filename

        return self.player.start(
            self.selected_audio_device,
            path,
        )

    def stop_soundcheck(self) -> None:
        """
        Stoppt eine laufende Soundcheck-Wiedergabe.
        """

        self.player.stop()

    def start_usb_copy(self, filename: str) -> tuple[bool, str]:
        """
        Startet das Kopieren einer Aufnahme ins Wurzelverzeichnis des
        USB-Sticks im Hintergrund (läuft sonst blockierend und ohne
        Fortschrittsanzeige). Der Fortschritt lässt sich über
        get_usb_copy_status() abfragen. Es läuft immer nur ein
        Kopiervorgang gleichzeitig.
        """

        recording = self.recorder.writer.directory / filename

        if not recording.exists():
            return False, "not_found"

        if not self.usb_storage.connected:
            return False, "no_usb"

        with self._usb_copy_lock:

            if self.usb_copy_state["active"]:
                return False, "busy"

            self.usb_copy_state = {
                "active": True,
                "filename": filename,
                "copied": 0,
                "total": recording.stat().st_size,
                "success": None,
                "already_exists": False,
            }

        thread = threading.Thread(
            target=self._run_usb_copy,
            args=(recording,),
            daemon=True,
        )
        thread.start()

        return True, "started"

    def _run_usb_copy(self, recording: Path) -> None:

        def on_progress(copied: int, total: int) -> None:
            with self._usb_copy_lock:
                self.usb_copy_state["copied"] = copied
                self.usb_copy_state["total"] = total

        success, already_exists = self.usb_storage.copy_file(
            recording,
            on_progress,
        )

        with self._usb_copy_lock:
            self.usb_copy_state["active"] = False
            self.usb_copy_state["success"] = success
            self.usb_copy_state["already_exists"] = already_exists

    def get_usb_copy_status(self) -> dict:
        """Liefert den aktuellen Fortschritt des USB-Kopiervorgangs."""

        with self._usb_copy_lock:
            return dict(self.usb_copy_state)

    def start_stem_combine(
        self,
        name: str,
        file_paths: list[Path],
    ) -> tuple[bool, str]:
        """
        Startet die Zusammenführung mehrerer Stereo-Stems (z.B. Click,
        eigenes Instrument, Rest der Band aus Moises) zu einem
        "Übungsmix" im Hintergrund (siehe core/stem_combiner.py) -
        `file_paths` zeigen auf bereits von der Route in ein Scratch-
        Verzeichnis kopierte Uploads, die nach Abschluss gelöscht
        werden. Reihenfolge der Liste = Kanalzuordnung (Datei 1 ->
        Kanal 1+2, ...).
        """

        name = name.strip()

        if (
            not name
            or len(name) > 40
            or "/" in name
            or "\\" in name
            or name in (".", "..")
        ):
            return False, "Ungültiger Name."

        if not 2 <= len(file_paths) <= 8:
            return False, "Es werden 2 bis 8 Dateien benötigt."

        if self.selected_audio_device is not None:

            max_channels = self.selected_audio_device.channels

            if len(file_paths) * 2 > max_channels:
                return False, (
                    f"Zu viele Dateien für das Interface "
                    f"({max_channels} Kanäle verfügbar)."
                )

        with self._stem_combine_lock:

            if self.stem_combine_state["active"]:
                return False, "Es läuft bereits eine Zusammenführung."

            self.stem_combine_state = {
                "active": True,
                "success": None,
                "error": "",
                "filename": "",
            }

        thread = threading.Thread(
            target=self._run_stem_combine,
            args=(name, file_paths),
            daemon=True,
        )
        thread.start()

        return True, "started"

    def _run_stem_combine(
        self,
        name: str,
        file_paths: list[Path],
    ) -> None:

        try:

            filename = combine_stems(
                file_paths,
                self.mixer_sample_rate,
                name,
            )

            with self._stem_combine_lock:
                self.stem_combine_state["success"] = True
                self.stem_combine_state["filename"] = filename

        except StemCombineError as exc:

            with self._stem_combine_lock:
                self.stem_combine_state["success"] = False
                self.stem_combine_state["error"] = str(exc)

        except Exception as exc:

            self.logger.exception(
                "Übungsmix fehlgeschlagen: %s",
                exc,
            )

            with self._stem_combine_lock:
                self.stem_combine_state["success"] = False
                self.stem_combine_state["error"] = "Unerwarteter Fehler."

        finally:

            with self._stem_combine_lock:
                self.stem_combine_state["active"] = False

            for path in file_paths:
                path.unlink(missing_ok=True)

            if file_paths:
                try:
                    file_paths[0].parent.rmdir()
                except OSError:
                    pass

    def get_stem_combine_status(self) -> dict:
        """Liefert den aktuellen Fortschritt der Übungsmix-Erstellung."""

        with self._stem_combine_lock:
            return dict(self.stem_combine_state)

    def get_update_info(self) -> dict:
        """
        Beschreibt fürs Einstellungen-Modal, ob ein Update bereitliegt,
        und liefert den Fortschritt eines laufenden Vorgangs gleich mit.
        """

        info = self.updater.get_available()

        info["version"] = self.config.data.application.version
        info["status"] = self.updater.get_status()

        return info

    def start_update(self) -> tuple[bool, str]:
        """
        Startet das Update von dem auf dem USB-Stick gefundenen Paket.
        Läuft im Hintergrund weiter, auch über den Neustart des
        Dienstes hinweg - der Fortschritt kommt über
        get_update_status().
        """

        if self.recorder.recording:
            return False, "Während einer Aufnahme kann nicht aktualisiert werden."

        if self.player.playing or self.music_player.playing:
            return False, "Während der Wiedergabe kann nicht aktualisiert werden."

        return self.updater.start(
            service_user=getpass.getuser(),
            port=self.config.data.server.port,
        )

    def get_update_status(self) -> dict:
        """Liefert den Fortschritt eines laufenden/letzten Updates."""

        return self.updater.get_status()

    def get_diagnostics_status(self) -> dict:
        """Zustand der Diagnose-Aufzeichnung fürs Einstellungen-Modal."""

        return self.diagnostics.get_status()

    def set_diagnostics(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet die Diagnose-Aufzeichnung an oder aus und merkt sich
        das über einen Neustart hinweg.
        """

        if enabled:
            self.diagnostics.start()
        else:
            self.diagnostics.stop()

        self.state_store.set("diagnostics_enabled", enabled)

        return True, ""

    def _console_host_and_channels(self) -> tuple[str | None, int]:
        """
        Liefert die IP des Mischpults und die Kanalzahl des Interfaces.

        Die IP kommt aus derselben Quelle wie bei der Portweiterleitung -
        sie ist nur bekannt, wenn die Konsole per Kabel am Pi hängt.
        """

        host = self.wlan_control.get_status().get("console_ip")

        channels = (
            self.selected_audio_device.channels
            if self.selected_audio_device is not None
            else 0
        )

        return host, channels

    def get_console_channels(self) -> dict:
        """
        Liefert Kanalnamen und Faderstellungen des Mischpults für die
        Fader-Karte.

        Unterscheidet zwei Fälle, damit die Oberfläche sie erklären
        kann: kein Steuerweg (Konsole nicht per Kabel erreichbar) und
        Steuerweg da, aber Pult antwortet nicht.
        """

        host, channels = self._console_host_and_channels()

        if not host or channels <= 0:
            return {
                "available": False,
                "reason": "no_connection",
                "channels": [],
            }

        result = self.console_control.get_channels(host, channels)

        if result is None:
            return {
                "available": False,
                "reason": "no_response",
                "channels": [],
            }

        return {
            "available": True,
            "reason": "",
            "channels": result,
        }

    def set_console_fader(self, channel: int, db: float | None) -> bool:
        """
        Setzt einen Kanalfader. `db` ist None, wenn der Fader ganz zu
        sein soll (-unendlich).
        """

        host, channels = self._console_host_and_channels()

        if not host or channels <= 0:
            return False

        return self.console_control.set_fader(
            host,
            channels,
            channel,
            float("-inf") if db is None else db,
        )

    def set_console_mute(self, channel: int, muted: bool) -> bool:
        """Schaltet einen Kanal am Pult stumm oder wieder an."""

        host, channels = self._console_host_and_channels()

        if not host or channels <= 0:
            return False

        return self.console_control.set_mute(host, channels, channel, muted)

    def eject_usb(self) -> tuple[bool, str]:
        """
        Hängt den USB-Stick sicher aus. Lehnt ab, solange noch ein
        Kopiervorgang läuft.
        """

        with self._usb_copy_lock:
            if self.usb_copy_state["active"]:
                return False, "busy"

        return self.usb_storage.eject()

    def play_music_folder(
        self,
        relative_path: str,
        start_channel: int,
    ) -> bool:
        """
        Spielt alle Musikdateien eines Ordners zufällig gemischt
        in Dauerschleife ab. `start_channel` ist 1-basiert
        (z.B. 17 für Kanal 17+18).
        """

        if self.selected_audio_device is None:
            return False

        if self.player.playing:
            return False

        folder = self.music_library.resolve(relative_path)

        if folder is None or not folder.is_dir():
            return False

        self.set_music_channel_preference(start_channel)

        return self.music_player.play_folder(
            self.selected_audio_device,
            folder,
            start_channel=start_channel - 1,
            rate=self.mixer_sample_rate,
        )

    def play_music_file(
        self,
        relative_path: str,
        start_channel: int,
    ) -> bool:
        """
        Spielt eine einzelne Musikdatei einmalig ab.
        """

        if self.selected_audio_device is None:
            return False

        if self.player.playing:
            return False

        path = self.music_library.resolve(relative_path)

        if path is None or not path.is_file():
            return False

        self.set_music_channel_preference(start_channel)

        return self.music_player.play_file(
            self.selected_audio_device,
            path,
            start_channel=start_channel - 1,
            rate=self.mixer_sample_rate,
        )

    def set_music_channel_preference(self, start_channel: int) -> bool:
        """
        Merkt sich den für die Musikwiedergabe gewählten Startkanal
        (1-basiert), damit das Dropdown nach einem Neustart wieder
        vorbelegt ist. Wird sowohl beim bloßen Auswählen im
        Dropdown als auch beim tatsächlichen Start einer Wiedergabe
        aufgerufen.
        """

        self.music_channel_preference = start_channel

        self.state_store.set(
            "music_channel",
            start_channel,
        )

        return True

    def set_record_name_prefix(self, prefix: str) -> bool:
        """
        Ändert das Namenspräfix für neue Aufnahmen (z.B. "Soundcheck"
        -> Dateien "Soundcheck-1.w64", "Soundcheck-2.w64", ...).
        """

        prefix = prefix.strip()

        if (
            not prefix
            or len(prefix) > 40
            or "/" in prefix
            or "\\" in prefix
            or prefix in (".", "..")
        ):
            return False

        self.record_name_prefix = prefix

        self.state_store.set(
            "record_name_prefix",
            prefix,
        )

        return True

    def stop_music(self) -> None:
        """
        Stoppt den Musikspieler.
        """

        self.music_player.stop()

    def pause_music(self) -> None:
        """
        Pausiert den Musikspieler.
        """

        self.music_player.pause()

    def resume_music(self) -> None:
        """
        Setzt den pausierten Musikspieler fort.
        """

        self.music_player.resume()

    def skip_music(self) -> None:
        """
        Springt zum nächsten Titel (Ordner-Modus).
        """

        self.music_player.skip()

    def seek_music(self, position: float) -> None:
        """
        Springt an eine Position (in Sekunden) im aktuellen Titel.
        """

        self.music_player.seek(position)

    def create_music_folder(
        self,
        relative_path: str,
        name: str,
    ) -> bool:
        """
        Legt einen neuen Ordner in der Musikbibliothek an.
        """

        return self.music_library.create_folder(
            relative_path,
            name,
        )

    def upload_music_file(
        self,
        relative_path: str,
        filename: str,
        source,
    ) -> str | None:
        """
        Speichert eine hochgeladene Musikdatei.
        """

        return self.music_library.save_upload(
            relative_path,
            filename,
            source,
        )

    def delete_music_file(self, relative_path: str) -> bool:
        """
        Löscht eine Musikdatei aus der Bibliothek.
        """

        return self.music_library.delete_file(
            relative_path
        )

    def delete_music_files(self, relative_paths: list[str]) -> list[str]:
        """
        Löscht mehrere Musikdateien auf einmal.
        """

        return self.music_library.delete_files(
            relative_paths
        )

    def start_level_check(self) -> bool:
        """
        Startet die reine Pegelprüfung (ohne aufzuzeichnen).
        """

        return self.recorder.start_monitoring()

    def stop_level_check(self) -> None:
        """
        Stoppt die reine Pegelprüfung.
        """

        self.recorder.stop_monitoring()

    def shutdown_system(self) -> bool:
        """
        Fährt den Raspberry Pi herunter.
        """

        return self.system_control.shutdown()

    def restart_service(self) -> bool:
        """
        Startet den XRack-Dienst neu (z.B. damit ein geänderter
        Port wirksam wird).
        """

        return self.system_control.restart_service()

    def set_language(self, language: str) -> bool:
        """
        Ändert die Sprache der Weboberfläche. Wirkt sofort, ohne
        Neustart - Übersetzungen werden bei jedem Seitenaufruf neu
        anhand der aktuellen Konfiguration geladen.
        """

        if language not in ("de", "en"):
            return False

        self.config.set_override("application", "language", language)

        self.config.data.application.language = language

        return True

    def set_port(self, port: int) -> bool:
        """
        Ändert den Port des Webinterfaces. Wird dauerhaft
        gespeichert, wirkt aber erst nach einem Dienst-Neustart
        (siehe restart_service()).
        """

        if not 1 <= port <= 65535:
            return False

        self.config.set_override("server", "port", port)

        self.config.data.server.port = port

        return True

    def pin_protection_enabled(self) -> bool:
        """
        Ist eine PIN zum Schutz des Einstellungen-Modals gesetzt?
        """

        return bool(self.config.data.security.pin_hash)

    def verify_settings_pin(self, pin: str) -> bool:
        """
        Prüft eine eingegebene PIN. Ist keine PIN gesetzt (z.B. vor
        dem ersten install.sh-Lauf mit dieser Funktion), gilt jede
        Eingabe als gültig - die Einstellungen sind dann ungeschützt.
        """

        pin_hash = self.config.data.security.pin_hash

        if not pin_hash:
            return True

        return verify_pin(pin, pin_hash)

    def set_settings_pin(self, current_pin: str, new_pin: str) -> tuple[bool, str]:
        """
        Ändert die PIN fürs Einstellungen-Modal. War noch keine PIN
        gesetzt, wird current_pin nicht geprüft (Erstvergabe).
        """

        if not re.fullmatch(r"\d{4}", new_pin):
            return False, "Neue PIN muss aus genau 4 Ziffern bestehen."

        if not self.verify_settings_pin(current_pin):
            return False, "Aktuelle PIN ist falsch."

        pin_hash = hash_pin(new_pin)

        self.config.set_override("security", "pin_hash", pin_hash)

        self.config.data.security.pin_hash = pin_hash

        return True, "PIN geändert."

    def get_wlan_status(self) -> dict:
        """
        Liefert den aktuellen (nicht-geheimen) WLAN-/Bridge-Status
        fürs Einstellungs-Modal.
        """

        #
        # "console_access_enabled" kommt direkt aus dem tatsächlichen
        # Zustand des Freigabe-Profils - hier ist nichts mehr
        # nachzureichen.
        #
        return self.wlan_control.get_status()

    def set_home_wifi(self, ssid: str, password: str) -> tuple[bool, str]:
        """
        Setzt SSID/Passwort der Heimnetz-WLAN-Verbindung neu.
        """

        if not 1 <= len(ssid) <= 32:
            return False, "Ungültige SSID."

        if not 8 <= len(password) <= 63:
            return False, "Passwort muss 8-63 Zeichen lang sein."

        return self.wlan_control.set_home_wifi(ssid, password)

    def set_ap_wifi(self, ssid: str, password: str) -> tuple[bool, str]:
        """
        Setzt SSID/Passwort des Access Points neu.
        """

        if not 1 <= len(ssid) <= 32:
            return False, "Ungültige SSID."

        if not 8 <= len(password) <= 63:
            return False, "Passwort muss 8-63 Zeichen lang sein."

        return self.wlan_control.set_ap_wifi(ssid, password)

    def set_bridge(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet die Ethernet+Access-Point-Bridge an oder aus.
        """

        return self.wlan_control.set_bridge(enabled)

    def set_console_access(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet "Konsole aus dem Heimnetz erreichbar machen" an oder
        aus - also die Ethernet-Freigabe zusammen mit der
        Portweiterleitung.

        Beim Einschalten wird die Weiterleitung hier bewusst *nicht*
        gesetzt: Die Konsole hat über die gerade erst hochgefahrene
        Freigabe noch keine DHCP-Lease, ihre IP ist also noch unbekannt.
        _reconcile_port_forward() holt das nach, sobald die IP auftaucht
        (genau der Fall, für den der Abgleich gebaut wurde).
        """

        if enabled:
            return self.wlan_control.set_share(True)

        #
        # Beim Ausschalten zuerst die Regel entfernen, solange die
        # Konsolen-IP noch bekannt ist, dann die Freigabe herunterfahren.
        #
        self.wlan_control.set_port_forward(False, None)
        self._port_forward_applied_ip = None

        return self.wlan_control.set_share(False)

    def _port_forward_loop(self) -> None:
        """
        Gleicht die Portweiterleitung regelmäßig ab (siehe
        _reconcile_port_forward()). Läuft als Daemon-Thread, damit ein
        Beenden von XRack nicht darauf warten muss.
        """

        while True:

            try:
                self._reconcile_port_forward()
            except Exception as exc:
                #
                # Ein Fehler hier darf den Thread nicht beenden, sonst
                # bleibt die Weiterleitung bis zum nächsten Neustart
                # ungesetzt.
                #
                self.logger.exception(
                    "Abgleich der Portweiterleitung fehlgeschlagen: %s",
                    exc,
                )

            time.sleep(self.PORT_FORWARD_INTERVAL)

    def _reconcile_port_forward(self) -> None:
        """
        Sorgt dafür, dass die tatsächlich gesetzte iptables-Regel zum
        Zustand der Freigabe und zur aktuell erkannten Konsolen-IP
        passt.

        Ob die Weiterleitung stehen soll, wird nicht separat gemerkt,
        sondern daraus abgeleitet, ob das Freigabe-Profil aktiv ist
        (der Schalter "Konsole aus dem Heimnetz erreichbar machen"
        schaltet genau dieses Profil). Dadurch können Anzeige und
        Wirklichkeit nicht auseinanderlaufen.

        Setzt die Regel nur, wenn sich die IP gegenüber der zuletzt
        gesetzten geändert hat - sonst liefe alle paar Sekunden ein
        iptables-Aufruf ohne jeden Nutzen. Das erneute Setzen selbst
        ist gefahrlos: scripts/xrack-port-forward.sh leert seine
        eigenen Ketten, bevor es neue Regeln anlegt.
        """

        #
        # Billiger Vorabtest: ein einziger nmcli-Aufruf. Den vollen
        # Status (mehrere nmcli- plus DHCP-Aufrufe) holen wir nur, wenn
        # die Freigabe wirklich läuft - so kostet der Abgleich für alle,
        # die das Feature nicht nutzen, so gut wie nichts.
        #
        active = self.wlan_control.active_connection_names()

        if SHARE_CONNECTION not in active:

            if self._port_forward_applied_ip is not None:
                #
                # Freigabe wurde ausgeschaltet (oder auf Bridge
                # gewechselt) - die Regel räumt sich hier von selbst ab.
                #
                self.wlan_control.set_port_forward(False, None)
                self._port_forward_applied_ip = None

                self.logger.info(
                    "Freigabe ist aus - Portweiterleitung entfernt."
                )

            return

        console_ip = self.wlan_control.get_status().get("console_ip")

        if not console_ip:
            #
            # Konsole (noch) nicht da - z.B. direkt nach dem Start,
            # bevor sie ihre DHCP-Lease bekommen hat. Beim Auftauchen
            # wird dann neu gesetzt.
            #
            self._port_forward_applied_ip = None
            return

        if console_ip == self._port_forward_applied_ip:
            return

        success, message = self.wlan_control.set_port_forward(True, console_ip)

        if success:

            self._port_forward_applied_ip = console_ip

            self.logger.info(
                "Portweiterleitung auf Konsole %s gesetzt.",
                console_ip,
            )

        else:

            self.logger.warning(
                "Portweiterleitung auf %s konnte nicht gesetzt werden: %s",
                console_ip,
                message,
            )

    def refresh_port_forward(self) -> None:
        """
        Baut die Portweiterleitung (falls aktiv) mit der aktuell
        erkannten Konsolen-IP neu auf - z.B. vom "Aktualisieren"-
        Knopf aufgerufen, falls sich die IP durch einen Neustart der
        Bridge/Freigabe geändert hat (siehe set_port_forward()).
        """

        #
        # Erzwingt ein Neusetzen, indem die gemerkte IP verworfen wird -
        # danach übernimmt der normale Abgleich.
        #
        self._port_forward_applied_ip = None

        self._reconcile_port_forward()

    def get_bluetooth_status(self) -> dict:
        """
        Liefert den aktuellen Bluetooth-Status fürs Webinterface.
        """

        status = self.bluetooth_control.get_status()

        status["streaming"] = self.bluetooth_player.streaming
        status["preferred_start_channel"] = self.bluetooth_channel_preference

        return status

    def _start_bluetooth_monitor(self) -> None:

        if self.selected_audio_device is None:
            return

        self.logger.info(
            "Bluetooth: Überwachung wird mit Zielkanal-Präferenz %d "
            "gestartet (1-basiert).",
            self.bluetooth_channel_preference,
        )

        self.bluetooth_player.start(
            self.selected_audio_device,
            self.bluetooth_channel_preference - 1,
            self.mixer_sample_rate,
        )

    def set_bluetooth_power(self, enabled: bool) -> tuple[bool, str]:
        """
        Schaltet den Bluetooth-Adapter (und damit das Lauschen auf
        eingehende Audiostreams) an oder aus.
        """

        success, message = self.bluetooth_control.set_power(enabled)

        if success:
            if enabled:
                self._start_bluetooth_monitor()
            else:
                self.bluetooth_player.stop()

        return success, message

    def start_bluetooth_pairing(self) -> tuple[bool, str]:
        """
        Macht XRack für ein kurzes Zeitfenster koppelbar.
        """

        return self.bluetooth_control.start_pairing()

    def forget_bluetooth_device(self, mac: str) -> tuple[bool, str]:
        """
        Entfernt ein einzelnes gekoppeltes Bluetooth-Gerät.
        """

        return self.bluetooth_control.forget_device(mac)

    def disconnect_bluetooth_device(self, mac: str) -> tuple[bool, str]:
        """
        Trennt die Verbindung zu einem gekoppelten Bluetooth-Gerät,
        ohne die Kopplung selbst aufzuheben.
        """

        return self.bluetooth_control.disconnect_device(mac)

    def set_bluetooth_channel_preference(self, start_channel: int) -> bool:
        """
        Merkt sich das für Bluetooth-Audio gewählte Ziel-Stereopaar
        (1-basiert). Läuft gerade eine Wiedergabe, wird sie kurz neu
        verbunden, damit die Änderung sofort wirkt.
        """

        self.logger.info(
            "Bluetooth: Zielkanal-Präferenz auf %d gesetzt (1-basiert).",
            start_channel,
        )

        self.bluetooth_channel_preference = start_channel

        self.state_store.set(
            "bluetooth_channel",
            start_channel,
        )

        self.bluetooth_player.set_start_channel(start_channel - 1)

        return True
