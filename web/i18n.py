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
        "btn_usb_eject": "USB-Stick auswerfen",
        "confirm_usb_eject": "USB-Stick jetzt auswerfen?",
        "alert_usb_eject_success": "USB-Stick kann jetzt entfernt werden.",
        "alert_usb_eject_failed": "USB-Stick konnte nicht ausgeworfen werden.",
        "alert_usb_eject_busy": "Es läuft noch ein Kopiervorgang - bitte warten.",

        # Soundcheck-Karte
        "soundcheck_title": "Soundcheck & Üben",
        "status_label": "Status:",
        "record_channels_label": "Aufnahmekanäle:",
        "btn_recording_start": "Aufnahme starten",
        "btn_recording_stop": "Aufnahme stoppen",
        "btn_soundcheck": "Soundcheck",
        "btn_practice": "Üben",
        "badge_kind_soundcheck": "Soundcheck",
        "badge_kind_practice": "Übungsmix",
        "btn_stop": "Stop",
        "btn_level_check": "Pegel testen",
        "btn_level_check_stop": "Pegel testen (Stop)",
        "btn_level_check_recording": "Pegel (läuft mit der Aufnahme)",
        "level_no_signal": 'Kein Signal - "Pegel testen" oder Aufnahme starten.',
        "label_file": "Datei",
        "label_format": "Format",
        "label_duration": "Dauer",
        "label_size": "Größe",
        "recent_recordings": "Letzte Dateien",
        "no_recordings": "Keine Aufnahmen vorhanden.",
        "btn_all_recordings": "Alle Dateien...",
        "channels_option": "{n} Kanäle",

        # Musikspieler-Karte
        "music_player_title": "Musikspieler",
        "music_channels_label": "Wiedergabekanäle:",
        "btn_open_folder": "Musik öffnen",
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
        "connection_lost_title": "Verbindung unterbrochen",
        "connection_lost_message": (
            "Keine Verbindung zu XRack - versuche automatisch erneut "
            "zu verbinden..."
        ),

        # Aufnahmen-Modal
        "modal_recordings_title": "Alle Dateien",
        "section_soundchecks": "Soundchecks",
        "section_practice_mixes": "Übungsmixe",
        "btn_delete_selected": "Ausgewählte löschen",
        "btn_close": "Schließen",
        "badge_selected_for_soundcheck": "Für Wiedergabe ausgewählt",
        "title_choose_for_soundcheck": "Für Wiedergabe auswählen",
        "title_download": "Download",
        "title_delete": "Löschen",
        "confirm_delete_file": '"{name}" wirklich löschen?',
        "confirm_delete_multi": "{count} Aufnahme(n) wirklich löschen?",

        # Übungsmix-Modal (mehrere Stereo-Stems zu einer Aufnahme kombinieren)
        "btn_stem_combine_open": "Übungsmix erstellen",
        "modal_stem_combine_title": "Übungsmix erstellen",
        "stem_combine_hint": (
            "Kombiniert mehrere Stereo-Dateien (z.B. Click, eigenes "
            "Instrument, Rest der Band) zu einer Aufnahme - Datei 1 "
            "landet auf Kanal 1+2, Datei 2 auf Kanal 3+4 usw."
        ),
        "stem_combine_name_label": "Name",
        "stem_combine_name_placeholder": "z.B. Songtitel",
        "stem_combine_channel_label": "Kanal {a}+{b}:",
        "btn_stem_combine_add_file": "Weitere Datei",
        "btn_stem_combine_create": "Übungsmix erstellen",
        "stem_combine_in_progress": "Übungsmix wird erstellt...",
        "stem_combine_name_required": "Bitte einen Namen eingeben.",
        "stem_combine_files_required": "Bitte mindestens 2 Dateien auswählen.",
        "stem_combine_failed": "Übungsmix konnte nicht erstellt werden.",
        "alert_recording_delete_failed": "Aufnahme konnte nicht gelöscht werden.",
        "alert_recordings_delete_failed": "Aufnahmen konnten nicht gelöscht werden.",
        "title_copy_to_usb": "Auf USB-Stick kopieren",
        "alert_usb_copy_success": "Auf den USB-Stick kopiert.",
        "alert_usb_copy_already_exists": "War schon auf dem USB-Stick vorhanden.",
        "alert_usb_copy_failed": "Kopieren auf den USB-Stick fehlgeschlagen.",
        "alert_usb_copy_busy": "Es läuft schon ein Kopiervorgang - bitte warten.",
        "alert_usb_copy_no_usb": "Kein USB-Stick angeschlossen.",

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
        "btn_select_all": "Alle auswählen",
        "confirm_delete_music_multi": "{count} Datei(en) wirklich löschen?",
        "alert_music_files_delete_failed": "Dateien konnten nicht gelöscht werden.",

        # Einstellungen-Modal
        "settings_icon_title": "Einstellungen",
        "modal_settings_title": "Einstellungen",
        "settings_language_label": "Sprache",
        "settings_sample_rate_label": "Mischpult-Samplerate",
        "settings_sample_rate_hint": (
            "Die tatsächlich am Mischpult/Interface eingestellte "
            "Samplerate - XRack kann sie nicht automatisch erkennen. "
            "Falsch eingestellt klingt Musik/Aufnahme zu schnell oder "
            "zu langsam."
        ),
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
        "settings_ap_access_title": (
            "Konsole über XRacks Access Point erreichbar machen"
        ),
        "settings_bridge_hint": (
            "Verbindet ein per Kabel angeschlossenes Mischpult mit "
            "XRacks eigenem Access Point - die Apps verbinden sich "
            "dafür mit dem WLAN von XRack."
        ),
        "settings_console_access_title": (
            "Konsole aus dem Heimnetz erreichbar machen"
        ),
        "settings_console_access_hint": (
            "Die per Kabel angeschlossene Konsole wird über XRacks "
            "eigene IP im Heimnetz ansprechbar (UDP 10023 für X32-Edit, "
            "UDP 10024 für X-AIR-Edit/Mixing Station). Schließt sich "
            "mit dem Access-Point-Weg darüber aus."
        ),
        "settings_console_access_waiting": (
            "Warte auf die Konsole - ist sie per Kabel angeschlossen "
            "und eingeschaltet?"
        ),
        "settings_app_ip_label": "In der Steuerungs-App eintragen:",
        "settings_console_ip_label": "Konsole am Pi:",
        "settings_console_host_label": "IP des Mischpults",
        "settings_console_host_placeholder": "automatisch",
        "settings_console_host_hint": (
            "Leer lassen, wenn das Pult am Pi hängt oder im Netz "
            "gefunden wird. Eintragen, wenn Pult und Pi zusammen an "
            "einem Router hängen und die Kanalzüge trotzdem keine "
            "Verbindung melden - manche Router lassen den Suchlauf "
            "nicht durch."
        ),
        "settings_console_host_invalid": "Das ist keine gültige IPv4-Adresse.",
        "settings_console_host_manual": "Wird benutzt: {ip} (von Hand eingetragen)",
        "settings_console_host_lease": "Wird benutzt: {ip} (am Pi angemeldet)",
        "settings_console_host_discovered": "Wird benutzt: {ip} (im Netz gefunden)",
        "settings_console_host_none": "Kein Mischpult gefunden.",
        "settings_faders_autolock_title": "Kanalzüge automatisch sperren",
        "settings_faders_autolock_unit": "Sekunden",
        "settings_faders_autolock_hint": (
            "Die Kanalzüge sperren sich wieder, wenn so lange keiner "
            "angefasst wurde. Jede Berührung setzt die Zeit zurück, "
            "mitten im Ziehen schnappt die Sperre also nicht zu."
        ),
        "settings_faders_autolock_saved": "Gespeichert.",
        "pair_link_confirm": (
            "Kanäle {a} und {b} am Pult koppeln?\n\n"
            "Gekoppelt gehen sie am Pult gemeinsam auf und ab. Der "
            "Regler hier funktioniert auch ohne Kopplung - er schickt "
            "den Wert dann eben an beide Kanäle."
        ),
        "pair_unlink_confirm": (
            "Kanäle {a} und {b} wieder entkoppeln?\n\n"
            "Sie bleiben sonst am Pult gekoppelt, auch wenn hier jetzt "
            "ein anderes Paar gewählt ist."
        ),

        # Update aus dem Internet oder über USB-Stick
        "settings_update_title": "Update",
        "settings_update_version_label": "Installierte Version:",
        "settings_update_hint": (
            "Aus dem Internet holt XRack den aktuellen Stand selbst. "
            "Ohne Internet: ZIP-Datei von GitHub herunterladen, ins "
            "Wurzelverzeichnis eines USB-Sticks legen und den Stick "
            "anstecken. In beiden Fällen bleiben Aufnahmen, Musik und "
            "alle Einstellungen erhalten - und falls danach etwas nicht "
            "läuft, holt XRack den vorherigen Stand automatisch zurück."
        ),
        "btn_settings_update_online": "Aus dem Internet",
        "settings_update_confirm_online": (
            "XRack jetzt aus dem Internet aktualisieren?\n\n"
            "Der aktuelle Stand wird von GitHub geladen. Der Dienst "
            "startet dabei neu, die Weboberfläche ist kurz nicht "
            "erreichbar. Aufnahmen, Musik und Einstellungen bleiben "
            "erhalten."
        ),
        "settings_update_step_laden": "Update wird heruntergeladen...",
        "settings_update_no_usb": "Kein USB-Stick angeschlossen.",
        "settings_update_no_package": (
            "Keine ZIP-Datei im Wurzelverzeichnis des Sticks gefunden."
        ),
        "settings_update_found": "Gefunden: {name} ({size})",
        "btn_settings_update": "Update starten",
        "settings_update_confirm": (
            "XRack jetzt aus \"{name}\" aktualisieren?\n\n"
            "Der Dienst startet dabei neu, die Weboberfläche ist kurz "
            "nicht erreichbar. Aufnahmen, Musik und Einstellungen "
            "bleiben erhalten."
        ),
        "settings_update_running": "Update läuft - bitte nicht ausschalten!",
        "settings_update_reconnecting": (
            "Dienst startet neu - warte auf die Weboberfläche..."
        ),
        "settings_update_step_start": "Update wird vorbereitet...",
        "settings_update_step_pruefen": "ZIP-Datei wird geprüft...",
        "settings_update_step_sichern": "Aktueller Stand wird gesichert...",
        "settings_update_step_uebertragen": "Neue Dateien werden übertragen...",
        "settings_update_step_pakete": "Abhängigkeiten werden installiert...",
        "settings_update_step_neustart": "Dienst wird neu gestartet...",
        "settings_update_step_rueckfall": "Alter Stand wird zurückgeholt...",
        "settings_update_failed": "Update fehlgeschlagen.",

        # Diagnose-Aufzeichnung
        "settings_diagnostics_title": "Diagnose-Aufzeichnung",
        "settings_diagnostics_label": "Aufzeichnung läuft mit",
        "settings_diagnostics_hint": (
            "Schreibt im Hintergrund mit, wie es XRack und dem Netzwerk "
            "geht - gedacht für Fehler, die nur sporadisch auftreten. "
            "Bleibt über einen Neustart hinweg eingeschaltet. Die Datei "
            "wird automatisch begrenzt und überschreibt sich, wenn sie "
            "zu groß wird."
        ),
        "btn_diagnostics_download": "Aufzeichnung herunterladen",
        "settings_diagnostics_empty": "Noch nichts aufgezeichnet.",

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
        "confirm_console_access_on": (
            "Konsole aus dem Heimnetz erreichbar machen? Die Verbindung "
            "kann dabei kurz unterbrochen werden."
        ),
        "confirm_console_access_off": (
            "Konsole aus dem Heimnetz nicht mehr erreichbar machen? Die "
            "Verbindung kann dabei kurz unterbrochen werden."
        ),
        "alert_settings_change_failed": "Änderung fehlgeschlagen: {message}",
        "alert_change_failed": "Änderung fehlgeschlagen.",

        # PIN-Schutz fürs Einstellungen-Modal
        "modal_settings_pin_title": "PIN erforderlich",
        "settings_pin_prompt_label": (
            "Bitte PIN eingeben, um die Einstellungen zu öffnen:"
        ),
        "settings_pin_wrong": "Falsche PIN.",
        "btn_confirm": "Bestätigen",
        "settings_pin_label": "Einstellungen-PIN",
        "settings_pin_current_placeholder": "Aktuelle PIN",
        "settings_pin_new_placeholder": "Neue PIN",
        "settings_pin_new_confirm_placeholder": "Neue PIN (Wiederholung)",
        "settings_pin_hint": (
            "4-stellige PIN, schützt das Einstellungen-Modal vor "
            "unbefugtem Zugriff."
        ),
        "alert_settings_pin_invalid": "PIN muss aus genau 4 Ziffern bestehen.",
        "alert_settings_pin_mismatch": "Die beiden PINs stimmen nicht überein.",

        # Bluetooth-Karte
        # Kanalfader der Konsole
        "faders_title": "Kanalfader",
        "faders_unlock": "Fader entsperren",
        "faders_lock": "Fader sperren",
        "faders_locked_hint": (
            "Die Fader sind gesperrt - zum Ändern oben auf das Schloss "
            "tippen."
        ),
        "faders_mute": "Stumm schalten",
        #
        # Beide Meldungen beschreiben dieselbe Lage und beginnen
        # deshalb gleich - nur der zweite Satz sagt, woran es liegt.
        # Vorher lasen sie sich wie zwei verschiedene Fehler, was beim
        # Vergleich zweier Geräte unnötig verwirrt.
        #
        "faders_no_connection": (
            "Keine Verbindung zur Konsole. Es ist noch kein Zugangsweg "
            "aktiv - die Fadersteuerung läuft über Netzwerk, nicht über "
            "das USB-Audiokabel. In den Einstellungen einen der beiden "
            "Wege einschalten."
        ),
        "faders_no_response": (
            "Keine Verbindung zur Konsole. Der Zugangsweg steht, aber "
            "unter {ip} antwortet nichts. Ist die Konsole eingeschaltet "
            "und das Kabel gesteckt?"
        ),

        "bluetooth_title": "Bluetooth",
        "bluetooth_channels_label": "Zielkanäle:",
        "bluetooth_power_label": "Bluetooth",
        "bluetooth_status_off": "aus",
        "bluetooth_status_ready": "bereit",
        "bluetooth_status_pairing": "koppelbar...",
        "bluetooth_status_connected": "verbunden mit {name}",
        "bluetooth_unavailable": (
            "Bluetooth (BlueZ) nicht gefunden - Funktion nicht "
            "verfügbar."
        ),
        "btn_bluetooth_pair": "Koppeln",
        "btn_bluetooth_devices": "Geräte",
        "bluetooth_paired_title": "Gekoppelte Geräte",
        "bluetooth_no_paired_devices": "Keine Geräte gekoppelt.",
        "badge_bluetooth_connected": "Verbunden",
        "title_bluetooth_disconnect_device": "Verbindung trennen",
        "confirm_bluetooth_disconnect_device": '"{name}" wirklich trennen?',
        "title_bluetooth_forget_device": "Gerät vergessen",
        "confirm_bluetooth_forget_device": '"{name}" wirklich vergessen?',
        "alert_bluetooth_pairing_started": (
            "Koppelbar für 2 Minuten - jetzt am Handy/Tablet verbinden."
        ),
    },
    "en": {
        # Audio interface
        "audio_rescan_title": "Rescan audio devices",
        "audio_open_device": "Connected device:",
        "audio_interface_fallback": "Audio Interface",
        "btn_usb_eject": "Eject USB drive",
        "confirm_usb_eject": "Eject the USB drive now?",
        "alert_usb_eject_success": "The USB drive can now be removed.",
        "alert_usb_eject_failed": "The USB drive could not be ejected.",
        "alert_usb_eject_busy": "A copy is still in progress - please wait.",

        # Soundcheck card
        "soundcheck_title": "Soundcheck & Practice",
        "status_label": "Status:",
        "record_channels_label": "Recording channels:",
        "btn_recording_start": "Start recording",
        "btn_recording_stop": "Stop recording",
        "btn_soundcheck": "Soundcheck",
        "btn_practice": "Practice",
        "badge_kind_soundcheck": "Soundcheck",
        "badge_kind_practice": "Practice mix",
        "btn_stop": "Stop",
        "btn_level_check": "Check levels",
        "btn_level_check_stop": "Check levels (stop)",
        "btn_level_check_recording": "Levels (running with recording)",
        "level_no_signal": 'No signal - start "Check levels" or start recording.',
        "label_file": "File",
        "label_format": "Format",
        "label_duration": "Duration",
        "label_size": "Size",
        "recent_recordings": "Recent files",
        "no_recordings": "No recordings yet.",
        "btn_all_recordings": "All files...",
        "channels_option": "{n} channels",

        # Music player card
        "music_player_title": "Music Player",
        "music_channels_label": "Playback channels:",
        "btn_open_folder": "Open music",
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
        "connection_lost_title": "Connection lost",
        "connection_lost_message": (
            "No connection to XRack - trying to reconnect "
            "automatically..."
        ),

        # Recordings modal
        "modal_recordings_title": "All files",
        "section_soundchecks": "Soundchecks",
        "section_practice_mixes": "Practice mixes",
        "btn_delete_selected": "Delete selected",
        "btn_close": "Close",
        "badge_selected_for_soundcheck": "Selected for playback",
        "title_choose_for_soundcheck": "Select for playback",
        "title_download": "Download",
        "title_delete": "Delete",
        "confirm_delete_file": 'Really delete "{name}"?',
        "confirm_delete_multi": "Really delete {count} recording(s)?",

        # Stem combine modal (combine multiple stereo stems into one recording)
        "btn_stem_combine_open": "Create practice mix",
        "modal_stem_combine_title": "Create practice mix",
        "stem_combine_hint": (
            "Combines multiple stereo files (e.g. click, your own "
            "instrument, rest of the band) into one recording - file 1 "
            "lands on channel 1+2, file 2 on channel 3+4, and so on."
        ),
        "stem_combine_name_label": "Name",
        "stem_combine_name_placeholder": "e.g. song title",
        "stem_combine_channel_label": "Channel {a}+{b}:",
        "btn_stem_combine_add_file": "Add another file",
        "btn_stem_combine_create": "Create practice mix",
        "stem_combine_in_progress": "Creating practice mix...",
        "stem_combine_name_required": "Please enter a name.",
        "stem_combine_files_required": "Please select at least 2 files.",
        "stem_combine_failed": "Practice mix could not be created.",
        "alert_recording_delete_failed": "The recording could not be deleted.",
        "alert_recordings_delete_failed": "The recordings could not be deleted.",
        "title_copy_to_usb": "Copy to USB drive",
        "alert_usb_copy_success": "Copied to the USB drive.",
        "alert_usb_copy_already_exists": "Was already on the USB drive.",
        "alert_usb_copy_failed": "Copying to the USB drive failed.",
        "alert_usb_copy_busy": "A copy is already in progress - please wait.",
        "alert_usb_copy_no_usb": "No USB drive connected.",

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
        "btn_select_all": "Select all",
        "confirm_delete_music_multi": "Really delete {count} file(s)?",
        "alert_music_files_delete_failed": "The files could not be deleted.",

        # Settings modal
        "settings_icon_title": "Settings",
        "modal_settings_title": "Settings",
        "settings_language_label": "Language",
        "settings_sample_rate_label": "Mixer sample rate",
        "settings_sample_rate_hint": (
            "The sample rate actually set on the console/interface - "
            "XRack cannot detect it automatically. If set wrong, "
            "music/recordings will sound too fast or too slow."
        ),
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
        "settings_ap_access_title": (
            "Make console reachable via XRack's access point"
        ),
        "settings_bridge_hint": (
            "Connects a mixing console plugged in via Ethernet with "
            "XRack's own access point - apps connect to XRack's Wi-Fi "
            "to reach it."
        ),
        "settings_console_access_title": (
            "Make console reachable from home network"
        ),
        "settings_console_access_hint": (
            "The console plugged in via Ethernet becomes reachable "
            "through XRack's own home network IP (UDP 10023 for "
            "X32-Edit, UDP 10024 for X-AIR-Edit/Mixing Station). "
            "Mutually exclusive with the access point route above."
        ),
        "settings_console_access_waiting": (
            "Waiting for the console - is it plugged in and switched on?"
        ),
        "settings_app_ip_label": "Enter this in your control app:",
        "settings_console_ip_label": "Console at the Pi:",
        "settings_console_host_label": "Mixer IP address",
        "settings_console_host_placeholder": "automatic",
        "settings_console_host_hint": (
            "Leave empty if the console is attached to the Pi or gets "
            "found on the network. Fill it in if console and Pi are "
            "both on a router and the channel strips still report no "
            "connection - some routers do not pass the search through."
        ),
        "settings_console_host_invalid": "That is not a valid IPv4 address.",
        "settings_console_host_manual": "In use: {ip} (entered by hand)",
        "settings_console_host_lease": "In use: {ip} (registered at the Pi)",
        "settings_console_host_discovered": "In use: {ip} (found on the network)",
        "settings_console_host_none": "No mixer found.",
        "settings_faders_autolock_title": "Lock channel strips automatically",
        "settings_faders_autolock_unit": "seconds",
        "settings_faders_autolock_hint": (
            "The channel strips lock again once none has been touched "
            "for that long. Every touch resets the timer, so the lock "
            "never snaps shut mid-drag."
        ),
        "settings_faders_autolock_saved": "Saved.",
        "pair_link_confirm": (
            "Link channels {a} and {b} on the console?\n\n"
            "Once linked they move together on the console. The fader "
            "here works without linking too - it simply sends the value "
            "to both channels."
        ),
        "pair_unlink_confirm": (
            "Unlink channels {a} and {b} again?\n\n"
            "Otherwise they stay linked on the console even though a "
            "different pair is selected here now."
        ),

        # Update from the internet or via USB stick
        "settings_update_title": "Update",
        "settings_update_version_label": "Installed version:",
        "settings_update_hint": (
            "From the internet, XRack fetches the current version "
            "itself. Without internet: download the ZIP from GitHub, "
            "put it in the root folder of a USB stick and plug the "
            "stick in. Either way, recordings, music and all settings "
            "are kept - and if something does not work afterwards, "
            "XRack automatically restores the previous version."
        ),
        "btn_settings_update_online": "From the internet",
        "settings_update_confirm_online": (
            "Update XRack from the internet now?\n\n"
            "The current version will be downloaded from GitHub. The "
            "service will restart, so the web interface will be briefly "
            "unavailable. Recordings, music and settings are kept."
        ),
        "settings_update_step_laden": "Downloading update...",
        "settings_update_no_usb": "No USB stick connected.",
        "settings_update_no_package": (
            "No ZIP file found in the root folder of the stick."
        ),
        "settings_update_found": "Found: {name} ({size})",
        "btn_settings_update": "Start update",
        "settings_update_confirm": (
            "Update XRack from \"{name}\" now?\n\n"
            "The service will restart, so the web interface will be "
            "briefly unavailable. Recordings, music and settings are "
            "kept."
        ),
        "settings_update_running": "Update running - do not power off!",
        "settings_update_reconnecting": (
            "Service is restarting - waiting for the web interface..."
        ),
        "settings_update_step_start": "Preparing update...",
        "settings_update_step_pruefen": "Checking ZIP file...",
        "settings_update_step_sichern": "Backing up current version...",
        "settings_update_step_uebertragen": "Copying new files...",
        "settings_update_step_pakete": "Installing dependencies...",
        "settings_update_step_neustart": "Restarting service...",
        "settings_update_step_rueckfall": "Restoring previous version...",
        "settings_update_failed": "Update failed.",

        # Diagnostic recording
        "settings_diagnostics_title": "Diagnostic recording",
        "settings_diagnostics_label": "Recording is running",
        "settings_diagnostics_hint": (
            "Records in the background how XRack and the network are "
            "doing - meant for problems that only show up now and then. "
            "Stays on across a restart. The file size is capped and "
            "older entries are overwritten once it gets too large."
        ),
        "btn_diagnostics_download": "Download recording",
        "settings_diagnostics_empty": "Nothing recorded yet.",

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
        "confirm_console_access_on": (
            "Make the console reachable from the home network? The "
            "connection may briefly drop while this happens."
        ),
        "confirm_console_access_off": (
            "Stop making the console reachable from the home network? "
            "The connection may briefly drop while this happens."
        ),
        "alert_settings_change_failed": "Change failed: {message}",
        "alert_change_failed": "Change failed.",

        # PIN protection for the settings modal
        "modal_settings_pin_title": "PIN required",
        "settings_pin_prompt_label": "Enter PIN to open settings:",
        "settings_pin_wrong": "Incorrect PIN.",
        "btn_confirm": "Confirm",
        "settings_pin_label": "Settings PIN",
        "settings_pin_current_placeholder": "Current PIN",
        "settings_pin_new_placeholder": "New PIN",
        "settings_pin_new_confirm_placeholder": "New PIN (repeat)",
        "settings_pin_hint": (
            "4-digit PIN, protects the settings modal from unauthorized "
            "access."
        ),
        "alert_settings_pin_invalid": "PIN must be exactly 4 digits.",
        "alert_settings_pin_mismatch": "The two PINs don't match.",

        # Bluetooth card
        # Console channel faders
        "faders_title": "Channel faders",
        "faders_unlock": "Unlock faders",
        "faders_lock": "Lock faders",
        "faders_locked_hint": (
            "The faders are locked - tap the padlock above to change "
            "them."
        ),
        "faders_mute": "Mute",
        "faders_no_connection": (
            "No connection to the console. No access route is enabled "
            "yet - fader control runs over the network, not the USB "
            "audio cable. Enable one of the two routes in the settings."
        ),
        "faders_no_response": (
            "No connection to the console. The access route is up, but "
            "nothing answers at {ip}. Is the console switched on and "
            "the cable plugged in?"
        ),

        "bluetooth_title": "Bluetooth",
        "bluetooth_channels_label": "Target channels:",
        "bluetooth_power_label": "Bluetooth",
        "bluetooth_status_off": "off",
        "bluetooth_status_ready": "ready",
        "bluetooth_status_pairing": "pairing mode...",
        "bluetooth_status_connected": "connected to {name}",
        "bluetooth_unavailable": (
            "Bluetooth (BlueZ) not found - feature not available."
        ),
        "btn_bluetooth_pair": "Pair",
        "btn_bluetooth_devices": "Devices",
        "bluetooth_paired_title": "Paired devices",
        "bluetooth_no_paired_devices": "No devices paired.",
        "badge_bluetooth_connected": "Connected",
        "title_bluetooth_disconnect_device": "Disconnect",
        "confirm_bluetooth_disconnect_device": 'Really disconnect "{name}"?',
        "title_bluetooth_forget_device": "Forget device",
        "confirm_bluetooth_forget_device": 'Really forget "{name}"?',
        "alert_bluetooth_pairing_started": (
            "Pairing mode for 2 minutes - connect from your phone/tablet now."
        ),
    },
}


def get_translations(language: str) -> dict[str, str]:
    """
    Liefert das Übersetzungswörterbuch für die angegebene Sprache,
    mit Deutsch als Fallback für unbekannte Sprachcodes.
    """

    return TRANSLATIONS.get(language, TRANSLATIONS[DEFAULT_LANGUAGE])
