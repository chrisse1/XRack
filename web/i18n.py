"""
Übersetzungen für die Weboberfläche von XRack.

Ein einziges Wörterbuch je Sprache, das sowohl von den
Jinja-Templates (als `t`) als auch - JSON-serialisiert - vom
Frontend-JavaScript (als `window.I18N`) genutzt wird. Platzhalter in
JS-seitig genutzten Texten folgen der Form "{name}" und werden dort
per String-Ersetzung eingesetzt.
"""

DEFAULT_LANGUAGE = "de"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "de": {
        # Audio-Interface
        "audio_rescan_title": "Audiogeräte neu suchen",
        "audio_open_device": "Geöffnetes Gerät:",
        "audio_interface_fallback": "Audio Interface",

        # Soundcheck-Karte
        "soundcheck_title": "Virtueller Soundcheck",
        "status_label": "Status:",
        "record_channels_label": "Aufnahmekanäle:",
        "audio_core_label": "Audio Core",
        "audio_core_open": "Geöffnet",
        "audio_core_closed": "Geschlossen",
        "btn_recording_start": "Aufnahme starten",
        "btn_recording_stop": "Aufnahme stoppen",
        "btn_soundcheck": "Soundcheck",
        "btn_stop": "Stop",
        "btn_level_check": "Pegel testen",
        "btn_level_check_stop": "Pegel testen (Stop)",
        "btn_level_check_recording": "Pegel (läuft mit der Aufnahme)",
        "level_no_signal": 'Kein Signal - "Pegel testen" oder Aufnahme starten.',
        "label_file": "Datei",
        "label_format": "Format",
        "label_duration": "Dauer",
        "label_size": "Größe",
        "recent_recordings": "Zuletzt aufgenommen",
        "no_recordings": "Keine Aufnahmen vorhanden.",
        "btn_all_recordings": "Alle Aufnahmen...",
        "channels_option": "{n} Kanäle",

        # Musikspieler-Karte
        "music_player_title": "Musikspieler",
        "music_channels_label": "Wiedergabekanäle:",
        "btn_open_folder": "Ordner öffnen",
        "btn_pause": "Pause",
        "btn_resume": "Fortsetzen",
        "btn_skip": "Weiter",
        "label_title": "Titel",
        "label_mode": "Modus",
        "mode_folder": "Ordner (Zufall/Schleife)",
        "mode_single": "Einzeltitel",
        "status_stopped": "gestoppt",
        "status_playing": "Wiedergabe läuft",
        "status_paused": "pausiert",
        "channel_option": "Kanal {a}+{b}",

        # Recorder-Zustände (core/status.py RecorderState)
        "state_idle": "bereit",
        "state_recording": "nimmt auf",
        "state_playback": "Wiedergabe",
        "state_monitoring": "Pegel testen",

        # System-Fußzeile
        "label_host": "Host",
        "label_cpu": "CPU",
        "label_ram": "RAM",
        "label_disk": "SSD",
        "btn_shutdown": "Raspberry Pi herunterfahren",
        "btn_shutdown_progress": "Fährt herunter...",
        "shutdown_confirm": (
            "Raspberry Pi wirklich herunterfahren?\n\n"
            "Laufende Aufnahmen/Wiedergaben werden dabei beendet, und "
            "das Webinterface ist danach nicht mehr erreichbar, bis "
            "der Pi manuell wieder eingeschaltet wird."
        ),
        "shutdown_failed": (
            "Herunterfahren fehlgeschlagen. Ist die sudo-Berechtigung "
            "eingerichtet (install.sh)?"
        ),

        # Aufnahmen-Modal
        "modal_recordings_title": "Aufnahmen",
        "btn_delete_selected": "Ausgewählte löschen",
        "btn_close": "Schließen",
        "badge_selected_for_soundcheck": "Für Soundcheck ausgewählt",
        "title_choose_for_soundcheck": "Für Soundcheck auswählen",
        "title_download": "Download",
        "title_delete": "Löschen",
        "confirm_delete_file": '"{name}" wirklich löschen?',
        "confirm_delete_multi": "{count} Aufnahme(n) wirklich löschen?",
        "alert_recording_delete_failed": "Aufnahme konnte nicht gelöscht werden.",
        "alert_recordings_delete_failed": "Aufnahmen konnten nicht gelöscht werden.",

        # Musikbibliothek-Modal
        "modal_music_title": "Musikbibliothek",
        "btn_play_folder_shuffle": "Diesen Ordner zufällig abspielen",
        "btn_new_folder": "Neuer Ordner",
        "btn_upload": "Hochladen",
        "music_root_breadcrumb": "Musik",
        "no_music_files": "Keine Musikdateien gefunden.",
        "title_play_file": "Datei abspielen",
        "alert_playback_start_failed": "Wiedergabe konnte nicht gestartet werden.",
        "alert_music_delete_failed": "Datei konnte nicht gelöscht werden.",
        "prompt_new_folder_name": "Name des neuen Ordners:",
        "alert_folder_create_failed": (
            "Ordner konnte nicht angelegt werden (existiert er schon?)."
        ),
        "alert_no_files_uploaded": (
            "Es wurden keine Dateien hochgeladen (unterstütztes Format?)."
        ),
        "alert_upload_failed": "Upload fehlgeschlagen.",

        # Einstellungen-Modal
        "settings_icon_title": "Einstellungen",
        "modal_settings_title": "Einstellungen",
        "settings_language_label": "Sprache",
        "settings_port_label": "Port",
        "settings_port_hint": "Wird erst nach einem Neustart wirksam.",
        "settings_recording_label": "Aufnahmename",
        "settings_recording_hint": (
            "Aufnahmen werden fortlaufend nummeriert benannt, z.B. "
            '"Soundcheck-1", "Soundcheck-2", ...'
        ),
        "btn_save": "Speichern",
        "btn_restart_now": "Jetzt neu starten",
        "confirm_restart": (
            "XRack jetzt neu starten? Das Webinterface ist danach kurz "
            "nicht erreichbar."
        ),
        "settings_saved": "Gespeichert.",
        "settings_saved_restart_needed": (
            "Gespeichert - Neustart nötig, damit der neue Port wirksam wird."
        ),
        "settings_wlan_unavailable": (
            "NetworkManager (nmcli) nicht gefunden - WLAN-Einstellungen "
            "nicht verfügbar."
        ),
        "settings_not_configured": (
            "Noch nicht eingerichtet (install.sh mit WLAN-Setup ausführen)."
        ),
        "settings_home_wifi_title": "Heimnetz (Client)",
        "settings_ap_wifi_title": "Access Point",
        "settings_bridge_title": "Ethernet+AP-Bridge",
        "settings_bridge_hint": (
            "Verbindet ein per Kabel angeschlossenes Mischpult mit dem "
            "Access Point, damit Apps es finden."
        ),
        "settings_wifi_hint": (
            "SSID und Passwort werden beim Speichern immer beide neu "
            "gesetzt."
        ),
        "label_ssid": "Name (SSID)",
        "label_password": "Passwort",
        "label_password_confirm": "Passwort wiederholen",
        "title_toggle_password": "Passwort anzeigen/verbergen",
        "alert_password_mismatch": "Die beiden Passwörter stimmen nicht überein.",
        "confirm_home_wifi_change": (
            "Heimnetz-WLAN wirklich ändern? Falls XRack aktuell darüber "
            "erreichbar ist, kann die Verbindung kurz unterbrochen werden."
        ),
        "confirm_ap_wifi_change": (
            "Access Point wirklich ändern? Verbundene Geräte müssen sich "
            "danach neu verbinden."
        ),
        "confirm_bridge_on": (
            "Bridge einschalten? Die Verbindung kann dabei kurz "
            "unterbrochen werden."
        ),
        "confirm_bridge_off": (
            "Bridge ausschalten? Die Verbindung kann dabei kurz "
            "unterbrochen werden."
        ),
        "alert_settings_change_failed": "Änderung fehlgeschlagen: {message}",
        "alert_change_failed": "Änderung fehlgeschlagen.",
    },
    "en": {
        # Audio interface
        "audio_rescan_title": "Rescan audio devices",
        "audio_open_device": "Connected device:",
        "audio_interface_fallback": "Audio Interface",

        # Soundcheck card
        "soundcheck_title": "Virtual Soundcheck",
        "status_label": "Status:",
        "record_channels_label": "Recording channels:",
        "audio_core_label": "Audio Core",
        "audio_core_open": "Open",
        "audio_core_closed": "Closed",
        "btn_recording_start": "Start recording",
        "btn_recording_stop": "Stop recording",
        "btn_soundcheck": "Soundcheck",
        "btn_stop": "Stop",
        "btn_level_check": "Check levels",
        "btn_level_check_stop": "Check levels (stop)",
        "btn_level_check_recording": "Levels (running with recording)",
        "level_no_signal": 'No signal - start "Check levels" or start recording.',
        "label_file": "File",
        "label_format": "Format",
        "label_duration": "Duration",
        "label_size": "Size",
        "recent_recordings": "Recently recorded",
        "no_recordings": "No recordings yet.",
        "btn_all_recordings": "All recordings...",
        "channels_option": "{n} channels",

        # Music player card
        "music_player_title": "Music Player",
        "music_channels_label": "Playback channels:",
        "btn_open_folder": "Open folder",
        "btn_pause": "Pause",
        "btn_resume": "Resume",
        "btn_skip": "Skip",
        "label_title": "Title",
        "label_mode": "Mode",
        "mode_folder": "Folder (shuffle/loop)",
        "mode_single": "Single track",
        "status_stopped": "stopped",
        "status_playing": "Playing",
        "status_paused": "paused",
        "channel_option": "Channel {a}+{b}",

        # Recorder states (core/status.py RecorderState)
        "state_idle": "ready",
        "state_recording": "recording",
        "state_playback": "playback",
        "state_monitoring": "checking levels",

        # System footer
        "label_host": "Host",
        "label_cpu": "CPU",
        "label_ram": "RAM",
        "label_disk": "Storage",
        "btn_shutdown": "Shut down Raspberry Pi",
        "btn_shutdown_progress": "Shutting down...",
        "shutdown_confirm": (
            "Really shut down the Raspberry Pi?\n\n"
            "Any running recording or playback will be stopped, and "
            "the web interface will be unreachable afterwards until "
            "the Pi is switched on again manually."
        ),
        "shutdown_failed": (
            "Shutdown failed. Is the sudo permission set up "
            "(install.sh)?"
        ),

        # Recordings modal
        "modal_recordings_title": "Recordings",
        "btn_delete_selected": "Delete selected",
        "btn_close": "Close",
        "badge_selected_for_soundcheck": "Selected for soundcheck",
        "title_choose_for_soundcheck": "Select for soundcheck",
        "title_download": "Download",
        "title_delete": "Delete",
        "confirm_delete_file": 'Really delete "{name}"?',
        "confirm_delete_multi": "Really delete {count} recording(s)?",
        "alert_recording_delete_failed": "The recording could not be deleted.",
        "alert_recordings_delete_failed": "The recordings could not be deleted.",

        # Music library modal
        "modal_music_title": "Music Library",
        "btn_play_folder_shuffle": "Shuffle-play this folder",
        "btn_new_folder": "New folder",
        "btn_upload": "Upload",
        "music_root_breadcrumb": "Music",
        "no_music_files": "No music files found.",
        "title_play_file": "Play file",
        "alert_playback_start_failed": "Playback could not be started.",
        "alert_music_delete_failed": "The file could not be deleted.",
        "prompt_new_folder_name": "Name of the new folder:",
        "alert_folder_create_failed": (
            "The folder could not be created (does it already exist?)."
        ),
        "alert_no_files_uploaded": (
            "No files were uploaded (unsupported format?)."
        ),
        "alert_upload_failed": "Upload failed.",

        # Settings modal
        "settings_icon_title": "Settings",
        "modal_settings_title": "Settings",
        "settings_language_label": "Language",
        "settings_port_label": "Port",
        "settings_port_hint": "Takes effect after a restart.",
        "settings_recording_label": "Recording name",
        "settings_recording_hint": (
            'Recordings are numbered consecutively, e.g. "Soundcheck-1", '
            '"Soundcheck-2", ...'
        ),
        "btn_save": "Save",
        "btn_restart_now": "Restart now",
        "confirm_restart": (
            "Restart XRack now? The web interface will be briefly "
            "unreachable afterwards."
        ),
        "settings_saved": "Saved.",
        "settings_saved_restart_needed": (
            "Saved - a restart is needed for the new port to take effect."
        ),
        "settings_wlan_unavailable": (
            "NetworkManager (nmcli) not found - Wi-Fi settings "
            "unavailable."
        ),
        "settings_not_configured": (
            "Not set up yet (run install.sh with Wi-Fi setup)."
        ),
        "settings_home_wifi_title": "Home network (client)",
        "settings_ap_wifi_title": "Access Point",
        "settings_bridge_title": "Ethernet+AP bridge",
        "settings_bridge_hint": (
            "Connects a mixing console plugged in via Ethernet with the "
            "access point, so apps can find it."
        ),
        "settings_wifi_hint": (
            "SSID and password are always both set anew when saving."
        ),
        "label_ssid": "Name (SSID)",
        "label_password": "Password",
        "label_password_confirm": "Confirm password",
        "title_toggle_password": "Show/hide password",
        "alert_password_mismatch": "The two passwords do not match.",
        "confirm_home_wifi_change": (
            "Really change the home Wi-Fi? If XRack is currently reachable "
            "through it, the connection may briefly drop."
        ),
        "confirm_ap_wifi_change": (
            "Really change the access point? Connected devices will need "
            "to reconnect afterwards."
        ),
        "confirm_bridge_on": (
            "Turn the bridge on? The connection may briefly drop while "
            "this happens."
        ),
        "confirm_bridge_off": (
            "Turn the bridge off? The connection may briefly drop while "
            "this happens."
        ),
        "alert_settings_change_failed": "Change failed: {message}",
        "alert_change_failed": "Change failed.",
    },
}


def get_translations(language: str) -> dict[str, str]:
    """
    Liefert das Übersetzungswörterbuch für die angegebene Sprache,
    mit Deutsch als Fallback für unbekannte Sprachcodes.
    """

    return TRANSLATIONS.get(language, TRANSLATIONS[DEFAULT_LANGUAGE])
