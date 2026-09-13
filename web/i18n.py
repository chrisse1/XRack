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
        #
        # Nur noch Soundcheck: Das Ueben hat seit 3.0 eine eigene
        # Karte, und der Name hier meinte zuletzt etwas, was hier
        # nicht mehr stattfindet.
        #
        "soundcheck_title": "Soundcheck",
        "status_label": "Status:",
        "record_channels_label": "Aufnahmekanäle:",

        #
        # Das Aufnahmefenster: "Aufnahme ab Kanal [9] , [4] Kanäle"
        #
        "record_window_label": "Aufnahme ab Kanal",
        "record_window_count": "Anzahl:",
        "record_space_basis": "{channels} Ch ab {start} · {gb} GB/h",
        "record_space_left": "Verbleibend: {time}",
        "record_space_warning": (
            "Der Speicher reicht nur noch für {time}. Bei {gb} GB je Stunde "
            "ist die Karte bald voll - XRack beendet eine laufende Aufnahme "
            "rechtzeitig, damit die Datei lesbar bleibt."
        ),
        "record_space_stopped": (
            "Die Aufnahme wurde beendet, weil der Speicher fast voll war. "
            "Die Datei ist vollständig geschlossen und lesbar."
        ),
        "record_rate_warning": (
            "Die eingestellte Samplerate stimmt vermutlich nicht: "
            "eingestellt {expected} Hz, am Interface gemessen etwa "
            "{likely} Hz. Aufnahmen wären in dieser Einstellung zu schnell "
            "oder zu langsam - bitte in den Einstellungen ändern."
        ),
        "record_rate_dropouts": (
            "Es kommen etwa {measured} Hz an, eingestellt sind {expected} Hz. "
            "Das passt zu keiner üblichen Samplerate und deutet auf "
            "Aussetzer beim Lesen hin (Kabel, USB-Anschluss, Last)."
        ),
        "record_no_device": (
            "Es ist kein Audio-Interface geöffnet - ohne Soundkarte gibt es "
            "nichts aufzunehmen und nichts zu hören. Pult anschließen, "
            "einschalten und oben auf ↻ drücken."
        ),
        "btn_recording_start": "Aufnahme starten",
        "btn_recording_stop": "Aufnahme stoppen",
        "btn_soundcheck": "Soundcheck",
        "btn_practice": "Üben",

        #
        # Die Karte, die zwischen Musik und Üben umschaltet.
        #
        "mode_music": "Musik",
        "mode_practice": "Üben",
        "practice_title": "Üben",
        "practice_mix_label": "Übungsmix:",
        "practice_repeat": "Wiederholen",
        "practice_none": (
            "Noch kein Übungsmix da. \"Übungsmix erstellen\" legt aus "
            "zwei bis acht Stereodateien einen an - jede Datei landet "
            "auf einem eigenen Kanalpaar, damit sich beim Üben jede "
            "Spur einzeln regeln lässt."
        ),
        "practice_busy": (
            "Erst anhalten: Beim Umschalten tauscht die Karte ihre "
            "Quelle aus."
        ),
        "practice_hint": "Liegt ab Kanal {a}",
        "practice_record": "Mitschneiden",
        "title_choose_for_practice": "Zum Üben auswählen",
        "btn_practice_files": "Dateien",
        "modal_practice_files_title": "Übungsmixe und Mitschnitte",
        "practice_no_files": (
            "Noch kein Übungsmix da. \"Übungsmix erstellen\" legt aus "
            "zwei bis acht Stereodateien einen an."
        ),
        "practice_take_short": "Versuch {nr}",
        "practice_no_takes": "noch kein Mitschnitt",
        "title_listen_along": "Zum Dazuhören auswählen",
        "practice_take_label": "Dazu hören:",
        "practice_offset_label": "Versatz:",
        "practice_offset_hint": "Versatz {ms} ms",
        "practice_latency_measure": "messen",
        "practice_latency_confirm": (
            "XRack spielt gleich einen kurzen Klick auf allen "
            "Wiedergabekanälen und nimmt dabei auf.\n\n"
            "Damit etwas zu messen ist, muss der Klick am Pult auf "
            "einen Kanal zurückkommen, der gerade aufgenommen wird - "
            "derselbe Weg, den der Übungsmix beim Üben nimmt. Auf "
            "diesem Kanal sollte es sonst still sein.\n\n"
            "Die Messung dauert etwa fünf Sekunden. Jetzt starten?"
        ),
        "practice_latency_running": "Messung läuft …",
        "practice_latency_done": (
            "Gemessen: {ms} ms\n\nEinzelne Läufe: {werte} ms"
        ),
        "practice_latency_unsure": (
            "Gemessen: {ms} ms\n\nEinzelne Läufe: {werte} ms\n\n"
            "Die Läufe gehen um {spanne} ms auseinander - das ist keine "
            "feste Grösse der Anlage. Ein fester Versatz gleicht sie "
            "dann auch nicht aus. Bitte noch einmal messen, bei Ruhe "
            "auf dem aufgenommenen Kanal."
        ),
        "practice_latency_zero": (
            "Gemessen: {ms} ms\n\nEinzelne Läufe: {werte} ms\n\n"
            "Fast null ist ungewöhnlich: Der Weg über USB und Pult "
            "braucht Zeit. Bitte noch einmal messen. Bleibt es dabei, "
            "kommt der Klick vermutlich nicht über das Pult zurück, "
            "sondern auf einem kürzeren Weg."
        ),
        "practice_take_none": "nichts",
        #
        # Stufe 5: aus Mix und Mitschnitt eine Datei. Zum Anhören
        # braucht es das nicht - zum Mitnehmen schon.
        #
        "practice_merge": "Zusammenführen",
        "practice_merge_name": (
            "Name für den neuen Übungsmix aus Mix und Mitschnitt:"
        ),
        "practice_merge_done": "Fertig: {name}",
        "practice_merge_failed": "Zusammenführen fehlgeschlagen.",
        "practice_take_hint": "mit {name}",
        "practice_record_hint": "Mitschnitt: Kanal {a}-{b}",
        "practice_record_no_device": (
            "Zum Mitschneiden fehlt ein offenes Audiogerät."
        ),
        "stem_combine_start_channel_label": "Erster Kanal:",
        "stem_combine_start_channel_hint": (
            "Ab hier liegt der Mix später beim Üben - jede Datei auf "
            "einem eigenen Kanalpaar. Die Angabe steht danach im "
            "Dateinamen und muss beim Üben nicht neu gewählt werden."
        ),
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
        "btn_all_recordings": "Aufnahmen...",
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
        "channel_option_mono": "Kanal {n}",

        # Recorder-Zustände (core/status.py RecorderState)
        "state_idle": "bereit",
        "state_no_device": "kein Interface",
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
        "modal_recordings_title": "Aufnahmen",
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
        # Einstellungen-Modal: die fuenf Themengruppen
        "settings_group_console": "Mischpult",
        "settings_group_network": "Netzwerk",
        "settings_group_recording": "Aufnahme",
        "settings_group_device": "Gerät",
        "settings_group_maintenance": "Wartung",
        "settings_icon_title": "Einstellungen",
        "modal_settings_title": "Einstellungen",
        "settings_language_label": "Sprache",
        "settings_sample_rate_label": "Mischpult-Samplerate",
        "settings_sample_rate_hint": "Muss zur Einstellung am Mischpult passen - sonst klingt alles zu schnell oder zu langsam.",
        "settings_port_label": "Port",
        "settings_port_hint": "Wird erst nach einem Neustart wirksam.",
        "settings_recording_label": "Aufnahmename",
        "settings_recording_hint": "Aufnahmen werden fortlaufend nummeriert.",
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
        "settings_ap_no_hardware": "Kein USB-WLAN-Stick erkannt.",
        "confirm_update_downgrade": (
            "Das Paket enthält Version {package}, installiert ist "
            "{installed}.\n\nDas wäre ein Rückschritt - neuere "
            "Funktionen und Korrekturen gingen dabei verloren. Wirklich "
            "fortfahren?"
        ),
        "settings_wifi_country_title": "WLAN-Land",
        "settings_wifi_country_hint": "Gilt für beide Funkgeräte. Ohne Angabe bleibt WLAN gesperrt.",
        "settings_wifi_country_none": "Noch nicht gesetzt",
        "settings_wifi_country_save": "Land speichern",
        "alert_wifi_country_saved": "WLAN-Land gespeichert.",
        "alert_wifi_country_failed": "WLAN-Land konnte nicht gesetzt werden: {message}",
        "settings_home_wifi_title": "WLAN-Client",
        "settings_ap_wifi_title": "Access Point",
        "settings_lan_mode_title": "Mischpult im selben Netzwerk (LAN)",
        "settings_lan_mode_hint": (
            "Pult und XRack hängen am selben Router. Access Point und "
            "WLAN-Verbindung laufen weiter."
        ),
        "confirm_lan_mode": (
            "In den LAN-Modus wechseln? Der gerade aktive Zugangsweg zum "
            "Mischpult wird dabei abgeschaltet."
        ),
        "settings_ap_access_title": (
            "Konsole über XRacks Access Point erreichbar machen"
        ),
        "settings_bridge_hint": "Das Pult an der Netzwerkbuchse wird über den Access Point erreichbar.",
        "settings_console_access_title": (
            "Konsole aus dem Heimnetz erreichbar machen"
        ),
        "settings_console_access_hint": "Das Pult an der Netzwerkbuchse wird aus dem Heimnetz erreichbar - für X32-Edit, X-AIR-Edit und Mixing Station.",
        "settings_mdns_alias_title": "Gemeinsamer Name für die Web-App",
        "settings_mdns_alias_placeholder": "z.B. xrack",
        "settings_mdns_alias_save": "Speichern",
        "settings_mdns_alias_hint": (
            "Zusätzlich zum eigenen Namen meldet sich dieses XRack unter "
            "dem gemeinsamen Namen im Netz. Trägt man ihn auf jedem Gerät "
            "gleich ein, findet dieselbe gespeicherte Web-App in jedem "
            "Raum das XRack, das dort steht. Leer lassen schaltet es ab. "
            "Zwei XRacks mit demselben Namen dürfen nicht gleichzeitig im "
            "selben Netz stehen."
        ),
        "settings_mdns_alias_own": "Eigener Name: {host}.local",
        "settings_mdns_alias_published": "Im Netz gemeldet als {name} ({addresses})",
        "settings_mdns_alias_off": "Kein gemeinsamer Name gesetzt.",
        "settings_mdns_alias_missing": (
            "avahi-publish fehlt (Paket avahi-utils) - install.sh erneut "
            "laufen lassen."
        ),
        #
        # Das Zertifikat. Es steht direkt unter dem gemeinsamen Namen,
        # weil es nur zusammen mit ihm etwas bringt: ein Name, ein
        # Zertifikat, eine Rueckfrage im Browser.
        #
        "settings_tls_title": "Zertifikat (HTTPS)",
        "settings_tls_hint": (
            "Das Zertifikat wird auf diesem Gerät erzeugt, deshalb fragt "
            "der Browser beim ersten Besuch nach. Wer mehrere XRacks hat, "
            "sichert es hier einmal und spielt es auf den anderen ein - "
            "zusammen mit demselben gemeinsamen Namen fragt der Browser "
            "dann nur noch einmal für alle. Die Datei ist mit dem Kennwort "
            "verschlüsselt; sie enthält den privaten Schlüssel und gehört "
            "in keine fremden Hände."
        ),
        "settings_tls_self": "Auf diesem Gerät erzeugt",
        "settings_tls_imported": "Übertragen",
        "settings_tls_valid": "gültig bis {date} ({days} Tage)",
        "settings_tls_names": "gilt für: {names}",
        "settings_tls_none": (
            "Kein Zertifikat vorhanden - XRack läuft unverschlüsselt."
        ),
        "settings_tls_alias_missing": (
            "Das Zertifikat gilt nicht für den gemeinsamen Namen "
            "\"{name}.local\" - unter diesem Namen fragt der Browser "
            "weiter nach. \"Neu erzeugen\" nimmt ihn auf; danach muss das "
            "Zertifikat erneut auf die anderen Racks."
        ),
        "settings_tls_pin_required": (
            "Für das Zertifikat muss erst eine PIN vergeben werden - ohne "
            "sie könnte jeder im Netz den privaten Schlüssel abholen."
        ),
        #
        # Die zweite Stufe: Das Zertifikat aufs Gerät legen, dann
        # fragt der Browser dort gar nicht mehr. Diese Datei enthält
        # nur den öffentlichen Teil - kein Kennwort, keine PIN.
        #
        "settings_tls_download": "Zertifikat herunterladen",
        "settings_tls_download_hint": (
            "Damit der Browser gar nicht mehr fragt: Datei herunterladen "
            "und auf dem Gerät in den Zertifikatsspeicher legen (Android: "
            "Einstellungen → Sicherheit → Zertifikat installieren → "
            "CA-Zertifikat; iPhone/iPad: Profil installieren, danach unter "
            "Zertifikatsvertrauenseinstellungen freigeben). Die Datei "
            "enthält nur den öffentlichen Teil - kein Kennwort nötig."
        ),
        "settings_tls_not_installable": (
            "Dieses Zertifikat lässt sich auf einem Gerät nicht als "
            "Zertifizierungsstelle eintragen. \"Neu erzeugen\" erstellt "
            "eines, das sich eintragen lässt."
        ),
        "settings_tls_password": "Kennwort für die Datei",
        "settings_tls_export": "Sichern",
        "settings_tls_import": "Einspielen",
        "settings_tls_renew": "Neu erzeugen",
        "settings_tls_exported": (
            "Gesichert. Ohne das Kennwort ist die Datei wertlos - mit ihm "
            "kann sich jemand als dieses XRack ausgeben."
        ),
        "settings_tls_imported_ok": (
            "Eingespielt. Es gilt nach einem Neustart des Dienstes."
        ),
        "settings_tls_renewed": (
            "Neues Zertifikat erzeugt. Es gilt nach einem Neustart des "
            "Dienstes, und der Browser fragt danach einmal erneut."
        ),
        "confirm_tls_renew": (
            "Neues Zertifikat erzeugen? Das alte gilt danach nicht mehr: "
            "Der Browser fragt an jedem Gerät erneut nach, und auf andere "
            "Racks übertragene Zertifikate passen nicht mehr dazu."
        ),
        "faders_snapshot_label": "Snapshot",
        "faders_snapshot_load": "Laden",
        "faders_snapshot_unnamed": "Snapshot {n}",
        "confirm_snapshot_load": (
            "Snapshot \"{name}\" wirklich laden? Das stellt am Mischpult "
            "alle Regler, Stummschaltungen und Klangeinstellungen um."
        ),
        "alert_snapshot_loaded": "Snapshot \"{name}\" wurde geladen.",
        "alert_snapshot_failed": "Snapshot konnte nicht geladen werden: {message}",
        "faders_search": "Mischpult erneut suchen",
        "alert_console_search_found": "Mischpult gefunden: {ip}",
        "alert_console_search_none": (
            "Kein Mischpult gefunden. Prüfe, ob es eingeschaltet und "
            "angeschlossen ist - im Einstellungen-Menü lässt sich die "
            "IP auch von Hand eintragen."
        ),
        "alert_console_search_failed": "Suche fehlgeschlagen.",
        "settings_console_access_waiting": (
            "Warte auf die Konsole - ist sie per Kabel angeschlossen "
            "und eingeschaltet?"
        ),
        "settings_app_ip_label": "In der Steuerungs-App eintragen:",
        "settings_console_ip_label": "Konsole am Pi:",
        "settings_console_host_label": "IP des Mischpults",
        "settings_console_host_placeholder": "automatisch",
        "settings_console_host_hint": "Nur nötig, wenn der Router den Suchlauf blockiert. Leer = automatisch.",
        "settings_console_host_invalid": "Das ist keine gültige IPv4-Adresse.",
        "settings_console_host_manual": "Wird benutzt: {ip} (von Hand eingetragen)",
        "settings_console_host_lease": "Wird benutzt: {ip} (am Pi angemeldet)",
        "settings_console_host_discovered": "Wird benutzt: {ip} (im Netz gefunden)",
        "settings_console_host_none": "Kein Mischpult gefunden.",
        "settings_faders_autolock_title": "Kanalzüge automatisch sperren",
        "settings_faders_autolock_unit": "Sekunden",
        "settings_faders_autolock_hint": "5 bis 3600 Sekunden.",
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
        "settings_update_hint": "ZIP von GitHub auf einen USB-Stick legen, oder direkt aus dem Internet laden.",
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
        "settings_selftest_title": "Netzwerk-Selbsttest",
        "settings_selftest_run": "Selbsttest ausführen",
        "settings_selftest_copy": "Kopieren",
        "settings_selftest_hint": (
            "Prüft Funkgeräte, Access Point, Heimnetz und Mischpult auf einmal."
        ),
        "alert_selftest_copied": "In die Zwischenablage kopiert.",
        "alert_selftest_failed": "Selbsttest konnte nicht ausgeführt werden.",
        "settings_diagnostics_title": "Diagnose-Aufzeichnung",
        "settings_diagnostics_label": "Aufzeichnung läuft mit",
        "settings_diagnostics_hint": "Schreibt Zustand und Netzwerk für die Fehlersuche mit.",
        "btn_diagnostics_download": "Aufzeichnung herunterladen",
        "settings_diagnostics_empty": "Noch nichts aufgezeichnet.",
        #
        # Die gemessenen Stillstände stehen unabhängig vom Schalter da:
        # Die Wache läuft immer (siehe core/diagnostics.py).
        #
        "settings_stillstand_titel": "Gemessene Stillstände:",
        "settings_stillstand_keiner": (
            "Keine Stillstände gemessen - der Prozess lief durchgehend."
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
        # Der Eingang eines Kanals. "A/D" ist die Beschriftung am Pult
        # selbst (Analog-Digital-Wandler) - dieselben Worte wie in
        # X-AIR Edit, damit man nicht uebersetzen muss, waehrend man
        # sucht.
        #
        "faders_usb_off": "A/D",
        "faders_usb_on": "USB",
        "faders_usb_title": (
            "Eingang des Kanals: A/D = Mikrofon/Instrument am Pult, "
            "USB = das, was XRack abspielt (virtueller Soundcheck). "
            "Achtung: Auf USB hört der Kanal sein Mikrofon nicht."
        ),
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

        # Licht (DMX)
        "light_title": "Licht",
        "light_settings_group": "Licht",
        "light_enable": "Lichtsteuerung verwenden",
        "light_enable_hint": (
            "Steuert DMX-Lampen über ein USB-DMX-Kabel. Ohne Kabel "
            "nicht nötig."
        ),
        "light_output_title": "DMX-Ausgang",
        "light_output_hint": (
            "Einmalig nach der Installation: Hier steht, an welchen "
            "Anschluss XRack sendet. XRack nutzt genau einen - wird "
            "ein anderer gewählt, ersetzt er den bisherigen."
        ),
        "light_output_assign": "Zuordnen",
        "light_output_none": (
            "Kein Ausgang gefunden. Läuft der Lichtdienst, und steckt "
            "das DMX-Kabel?"
        ),
        "light_output_patched": "Zugeordnet: {name}",
        "light_output_unpatched": "Noch kein Ausgang zugeordnet.",
        "light_output_done": "Zugeordnet.",
        "light_setup": "Einrichten",
        "light_blackout": "Alles aus",
        "light_no_fixtures": (
            "Noch keine Lampen eingerichtet - über \"Einrichten\" anlegen."
        ),
        "light_service_missing": (
            "Der Lichtdienst antwortet nicht. Läuft olad?"
        ),
        "light_adapter_missing": "Kein DMX-Kabel erkannt.",
        "light_unpatched": (
            "Es ist noch kein DMX-Ausgang zugeordnet - die Lampen "
            "bleiben dunkel. In den Einstellungen unter \"Licht\"."
        ),
        "light_overlap_warning": (
            "Achtung: Zwei Lampen belegen dieselben Kanäle. Das ist "
            "erlaubt, aber selten gewollt."
        ),
        "light_brightness": "Helligkeit",
        "light_segment": "Segment {n}",

        # Licht: Einrichten
        "light_setup_title": "Licht einrichten",
        "light_export": "Einrichtung sichern",
        "light_import_confirm": (
            "Die gesicherte Einrichtung einspielen? Vorlagen, Lampen und "
            "Szenen dieses Geräts werden dabei ersetzt, und das Licht geht "
            "aus."
        ),
        "light_import_failed": "Die Einrichtung ließ sich nicht einspielen.",
        "light_import": "Einrichtung einspielen",
        "light_transfer_hint": (
            "Nimmt Vorlagen, Lampen, Szenen und Show-Einstellungen mit - "
            "zum Übertragen auf ein zweites XRack. WLAN, PIN, Gerätename "
            "und Pult-Adresse bleiben, wo sie sind. Einspielen ersetzt die "
            "vorhandene Einrichtung."
        ),
        "light_fixtures_title": "Lampen",
        "light_fixture_new": "Lampe aus Vorlage erstellen",
        "light_templates_title": "Gerätevorlagen",
        "light_template_new": "Eigene Vorlage erstellen",
        "light_name": "Name",
        "light_template": "Vorlage",
        "light_address": "Startadresse",
        "light_kind": "Art",
        "light_kind_effect": "Effektlicht",
        "light_kind_background": "Hintergrundlicht 1",
        "light_kind_background2": "Hintergrundlicht 2",
        "light_kind_static": "Von der Show ausgenommen",
        "light_kind_hint": (
            "Effektlicht folgt dem Takt. Die beiden Hintergrundgruppen "
            "wechseln die Farbe langsam, jede mit eigenen Farben und "
            "gegeneinander versetzt. Ausgenommene Lampen behalten, was "
            "von Hand oder über eine Szene eingestellt ist."
        ),
        "light_address_range": "DMX {von}–{bis}",
        "light_address_occupies": "Belegt DMX {von}–{bis}.",
        "light_channels_count": "{n} Kanäle",
        "light_template_name": "Name der Vorlage",
        "light_template_pattern": "Kanäle (Muster)",
        "light_template_repeat": "Wiederholungen",
        "light_template_repeat_hint": (
            "Für Geräte mit mehreren gleichen Segmenten: Muster einmal "
            "angeben, Anzahl der Segmente eintragen."
        ),
        "light_template_add_channel": "Kanal",
        "light_template_builtin": "mitgeliefert",
        "confirm_light_fixture_delete": "Lampe \"{name}\" wirklich löschen?",
        "confirm_light_template_delete": "Vorlage \"{name}\" wirklich löschen?",
        "confirm_light_scene_delete": "Szene \"{name}\" wirklich löschen?",

        # Licht: Szenen
        "light_scenes_title": "Szenen",
        "light_no_scenes": (
            "Noch keine Szene gespeichert. Lampen einstellen, dann "
            "speichern."
        ),
        "light_scene_save": "Aktuellen Stand speichern",
        "light_scene_name_prompt": "Name der Szene:",

        # Licht: Kanalrollen
        "light_role_dimmer": "Dimmer",
        "light_role_red": "Rot",
        "light_role_green": "Grün",
        "light_role_blue": "Blau",
        "light_role_white": "Weiß",
        "light_role_amber": "Amber",
        "light_role_uv": "UV",
        "light_role_pan": "Pan (drehen)",
        "light_role_pan_fine": "Pan fein",
        "light_role_tilt": "Tilt (neigen)",
        "light_role_tilt_fine": "Tilt fein",
        "light_role_gobo": "Gobo",
        "light_role_gobo_rotation": "Gobo-Drehung",
        "light_role_color_wheel": "Farbrad",
        "light_role_strobe": "Strobe",
        "light_role_shutter": "Shutter",
        "light_role_rotation": "Drehung",
        "light_role_laser": "Laser",
        "light_role_generic": "Sonstiger Kanal",

        # Licht: musikgesteuerte Show
        "light_show_title": "Musikshow",
        "light_show_start": "Show starten",
        "light_show_stop": "Show anhalten",
        "light_show_settings": "Show-Einstellungen",
        "light_show_channel": "Quelle der Lichtshow",
        "light_show_channel_hint": (
            "Worauf die Lichtshow hört. Ein Kanalpaar ist der einfache "
            "Weg; ein einzelner Kanal spart einen USB-Kanal und erlaubt "
            "einen eigenen Mix nur fürs Licht - etwa ein AUX-Bus mit "
            "betonter Bassdrum und ohne Gesang. Achtung: Derselbe Kanal "
            "ist einzeln doppelt so laut wie als Hälfte eines Paares - "
            "die Stille-Schwelle darunter gehört dann nachgeprüft."
        ),
        "light_show_channel_pairs": "Kanalpaar",
        "light_show_channel_single": "Einzelner Kanal",
        "light_show_sensitivity": "Empfindlichkeit",
        "light_show_background_seconds": "Hintergrund: Trägheit",
        "light_show_effect_mode": "Effektlicht: Bild",
        "light_show_effect_mode_runner": "Wandernder Punkt",
        "light_show_effect_mode_pulse": "Puls im Takt",
        "light_show_effect_mode_hint": (
            "Wandernder Punkt: ein Segment nach dem anderen leuchtet "
            "auf. Puls: alle Segmente atmen gemeinsam im Takt. Das "
            "Hintergrundlicht bleibt in beiden Fällen ein Wash."
        ),
        "light_show_pulse_seconds": "Puls: Nachleuchten",
        "light_show_pulse_base": "Puls: Grundhelligkeit",
        "light_show_pulse_hint": (
            "Wie lange ein Schlag nachleuchtet und wie hell es "
            "zwischen zwei Schlägen bleibt. 0 % heißt: dazwischen "
            "ganz aus."
        ),
        "light_show_color_invert": "Farben umkehren",
        "light_show_color_invert_hint": (
            "Kehrt die Reihenfolge der Bandfarben auf den "
            "Effektlichtern um: Aus Rot-Grün-Blau wird Blau-Grün-Rot "
            "und nach denselben Schlägen wieder zurück. Helligkeit "
            "und Bewegung bleiben, wie sie sind; das Hintergrundlicht "
            "ist nicht betroffen."
        ),
        "light_show_invert_beats": "Farben umkehren: alle",
        "light_show_snare_strobe": "Blitz",
        "light_show_snare_hint": (
            "Blitzt die Strobe-Kanäle der Effektlichter auf besonders "
            "laute Schläge. Solange das aus ist, fasst die Show die "
            "Strobe-Kanäle gar nicht an - ist es an, gehören sie ihr, "
            "und ein von Hand eingestellter Wert wird überschrieben."
        ),
        "light_show_snare_sense": "Blitz: Empfindlichkeit",
        "light_show_snare_power": "Blitz: Stärke",
        "light_show_snare_options_hint": (
            "Höher heißt MEHR Blitze - bei 50 % kommen die kräftigen "
            "Schläge durch, weiter oben auch der laufende Takt. Was "
            "die Stärke am Gerät bewirkt - Helligkeit oder "
            "Blitzgeschwindigkeit -, steht in der Kanaltabelle des "
            "Geräts; ausprobieren."
        ),
        "light_show_background_beats": "Hintergrund: Farbwechsel",
        "light_show_fade_seconds": "Ausblenden in die Szene",
        "light_show_beats_unit": "{n} Schläge",
        "light_show_background_warning": (
            "Die Blende ist länger als die halbe Standzeit - die Farben "
            "kommen nicht mehr rein an, sondern mischen sich zu einem "
            "Mittelton. Trägheit verkürzen oder Farbwechsel verlängern."
        ),
        "light_show_colors": "Farben: Effektlicht",
        "light_show_colors_1": "Farben: Hintergrundlicht 1",
        "light_show_colors_2": "Farben: Hintergrundlicht 2",
        "light_show_colors_1_hint": (
            "Nur für Lampen der Gruppe \"Hintergrundlicht 1\"."
        ),
        "light_show_colors_2_hint": (
            "Nur für Lampen der Gruppe \"Hintergrundlicht 2\". Sie läuft um eine Farbe versetzt, damit immer zwei verschiedene Farben auf der Bühne stehen."
        ),
        "light_show_color_low": "Tiefe Töne",
        "light_show_color_mid": "Mitten",
        "light_show_color_high": "Höhen",
        "light_show_colors_hint": (
            "Die drei Farben werden nach Lautstärke der Bereiche "
            "gemischt. Geschmackssache - probier es aus."
        ),
        "light_show_fallback": "Szene bei Sprache oder Stille",
        "light_show_fallback_none": "Licht aus",
        "light_show_fallback_hint": (
            "Läuft keine Musik mehr, schaltet XRack hierauf um."
        ),
        "light_show_silence_threshold": "Ab wann gilt es als still",
        "light_show_level_hint": (
            "Der Balken \"Gesamt\" und die Schwelle sind in dBFS - dieselbe Skala wie am Pult."
        ),
        "light_show_silence_seconds": "Wartezeit bis Stille (Sekunden)",
        "light_show_speech_seconds": "Wartezeit bis Sprache (0 = aus)",
        "light_show_tuning_hint": (
            "Diese Werte hängen vom Signal ab, das bei dir ankommt - "
            "vor Ort ausprobieren."
        ),
        "light_show_state_music": "Musik",
        "light_show_state_speech": "Sprache",
        "light_show_state_silence": "Stille",
        "light_show_band_low": "Tief",
        "light_show_band_mid": "Mitte",
        "light_show_band_high": "Hoch",
        "light_show_band_level": "Gesamt",
        "light_show_no_stream": (
            "Es kommt kein Audio an. Ist das richtige Kanalpaar gewählt, "
            "und liegt dort ein Signal?"
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
        "soundcheck_title": "Soundcheck",
        "status_label": "Status:",
        "record_channels_label": "Recording channels:",
        "record_window_label": "Record from channel",
        "record_window_count": "Count:",
        "record_space_basis": "{channels} ch from {start} · {gb} GB/h",
        "record_space_left": "Remaining: {time}",
        "record_space_warning": (
            "Only {time} of recording space left. At {gb} GB per hour the "
            "card fills up quickly - XRack ends a running recording in time "
            "so the file stays readable."
        ),
        "record_space_stopped": (
            "The recording was ended because the card was nearly full. The "
            "file is properly closed and readable."
        ),
        "record_rate_warning": (
            "The sample rate setting is probably wrong: set to {expected} Hz, "
            "measured about {likely} Hz at the interface. Recordings would "
            "come out too fast or too slow - please change it in the "
            "settings."
        ),
        "record_rate_dropouts": (
            "About {measured} Hz are coming in, {expected} Hz are set. That "
            "matches no usual sample rate and points to dropouts while "
            "reading (cable, USB port, load)."
        ),
        "record_no_device": (
            "No audio interface is open - without a sound card there is "
            "nothing to record and nothing to hear. Connect the console, "
            "switch it on and press ↻ above."
        ),
        "btn_recording_start": "Start recording",
        "btn_recording_stop": "Stop recording",
        "btn_soundcheck": "Soundcheck",
        "btn_practice": "Practice",
        "mode_music": "Music",
        "mode_practice": "Practice",
        "practice_title": "Practice",
        "practice_mix_label": "Practice mix:",
        "practice_repeat": "Repeat",
        "practice_none": (
            "No practice mix yet. \"Create practice mix\" builds one "
            "from two to eight stereo files - each file lands on its "
            "own channel pair so every part can be set separately "
            "while practising."
        ),
        "practice_busy": (
            "Stop first: switching swaps the card's source."
        ),
        "practice_hint": "Starts at channel {a}",
        "practice_record": "Record along",
        "title_choose_for_practice": "Select for practising",
        "btn_practice_files": "Files",
        "modal_practice_files_title": "Practice mixes and takes",
        "practice_no_files": (
            "No practice mix yet. \"Create practice mix\" builds one "
            "from two to eight stereo files."
        ),
        "practice_take_short": "Take {nr}",
        "practice_no_takes": "no take yet",
        "title_listen_along": "Select to play along",
        "practice_take_label": "Play along with:",
        "practice_offset_label": "Offset:",
        "practice_offset_hint": "offset {ms} ms",
        "practice_latency_measure": "measure",
        "practice_latency_confirm": (
            "XRack will play a short click on all playback channels "
            "and record at the same time.\n\n"
            "For anything to be measured, the click has to come back "
            "at the console on a channel that is being recorded - the "
            "same path the practice mix takes. That channel should be "
            "quiet otherwise.\n\n"
            "The measurement takes about five seconds. Start now?"
        ),
        "practice_latency_running": "measuring …",
        "practice_latency_done": (
            "Measured: {ms} ms\n\nIndividual runs: {werte} ms"
        ),
        "practice_latency_unsure": (
            "Measured: {ms} ms\n\nIndividual runs: {werte} ms\n\n"
            "The runs differ by {spanne} ms - that is not a fixed "
            "property of the setup, and a fixed offset will not "
            "compensate for it. Please measure again, with the "
            "recorded channel quiet."
        ),
        "practice_latency_zero": (
            "Measured: {ms} ms\n\nIndividual runs: {werte} ms\n\n"
            "Almost zero is unusual: the path through USB and console "
            "takes time. Please measure again. If it stays at zero, "
            "the click is probably not coming back through the "
            "console but by a shorter route."
        ),
        "practice_take_none": "nothing",
        "practice_merge": "Merge",
        "practice_merge_name": (
            "Name for the new practice mix from mix and take:"
        ),
        "practice_merge_done": "Done: {name}",
        "practice_merge_failed": "Merging failed.",
        "practice_take_hint": "with {name}",
        "practice_record_hint": "Recording: channels {a}-{b}",
        "practice_record_no_device": (
            "Recording along needs an open audio device."
        ),
        "stem_combine_start_channel_label": "First channel:",
        "stem_combine_start_channel_hint": (
            "This is where the mix will sit while practising - each "
            "file on its own channel pair. The setting then lives in "
            "the file name and need not be chosen again."
        ),
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
        "btn_all_recordings": "Recordings...",
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
        "channel_option_mono": "Channel {n}",

        # Recorder states (core/status.py RecorderState)
        "state_idle": "ready",
        "state_no_device": "no interface",
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
        "modal_recordings_title": "Recordings",
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
        # Settings modal: the five topic groups
        "settings_group_console": "Mixing console",
        "settings_group_network": "Network",
        "settings_group_recording": "Recording",
        "settings_group_device": "Device",
        "settings_group_maintenance": "Maintenance",
        "settings_icon_title": "Settings",
        "modal_settings_title": "Settings",
        "settings_language_label": "Language",
        "settings_sample_rate_label": "Mixer sample rate",
        "settings_sample_rate_hint": "Must match the setting on the console - otherwise everything plays too fast or too slow.",
        "settings_port_label": "Port",
        "settings_port_hint": "Takes effect after a restart.",
        "settings_recording_label": "Recording name",
        "settings_recording_hint": "Recordings are numbered consecutively.",
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
        "settings_ap_no_hardware": "No USB Wi-Fi adapter detected.",
        "confirm_update_downgrade": (
            "The package contains version {package}, installed is "
            "{installed}.\n\nThis would be a downgrade - newer features "
            "and fixes would be lost. Continue anyway?"
        ),
        "settings_wifi_country_title": "Wi-Fi country",
        "settings_wifi_country_hint": "Applies to both radios. Without it Wi-Fi stays blocked.",
        "settings_wifi_country_none": "Not set yet",
        "settings_wifi_country_save": "Save country",
        "alert_wifi_country_saved": "Wi-Fi country saved.",
        "alert_wifi_country_failed": "Could not set the Wi-Fi country: {message}",
        "settings_home_wifi_title": "Wi-Fi client",
        "settings_ap_wifi_title": "Access Point",
        "settings_lan_mode_title": "Console on the same network (LAN)",
        "settings_lan_mode_hint": (
            "Console and XRack are on the same router. Access point and "
            "Wi-Fi connection keep running."
        ),
        "confirm_lan_mode": (
            "Switch to LAN mode? The currently active route to the console "
            "will be turned off."
        ),
        "settings_ap_access_title": (
            "Make console reachable via XRack's access point"
        ),
        "settings_bridge_hint": "The console on the Ethernet port becomes reachable via the access point.",
        "settings_console_access_title": (
            "Make console reachable from home network"
        ),
        "settings_console_access_hint": "The console on the Ethernet port becomes reachable from the home network - for X32-Edit, X-AIR-Edit and Mixing Station.",
        "settings_mdns_alias_title": "Shared name for the web app",
        "settings_mdns_alias_placeholder": "e.g. xrack",
        "settings_mdns_alias_save": "Save",
        "settings_mdns_alias_hint": (
            "On top of its own name, this XRack announces itself under the "
            "shared name. Set the same name on every unit and one saved "
            "web app finds whichever XRack is in the room. Leave empty to "
            "switch it off. Two XRacks with the same name must not be on "
            "the same network at once."
        ),
        "settings_mdns_alias_own": "Own name: {host}.local",
        "settings_mdns_alias_published": "Announced as {name} ({addresses})",
        "settings_mdns_alias_off": "No shared name set.",
        "settings_mdns_alias_missing": (
            "avahi-publish is missing (package avahi-utils) - run install.sh "
            "again."
        ),
        "settings_tls_title": "Certificate (HTTPS)",
        "settings_tls_hint": (
            "The certificate is created on this unit, which is why the "
            "browser asks on the first visit. With several XRacks, save it "
            "here once and load it onto the others - together with the same "
            "shared name the browser then asks once for all of them. The "
            "file is encrypted with the password; it contains the private "
            "key and belongs in no one else's hands."
        ),
        "settings_tls_self": "Created on this unit",
        "settings_tls_imported": "Transferred",
        "settings_tls_valid": "valid until {date} ({days} days)",
        "settings_tls_names": "valid for: {names}",
        "settings_tls_none": (
            "No certificate present - XRack is running unencrypted."
        ),
        "settings_tls_alias_missing": (
            "The certificate does not cover the shared name "
            "\"{name}.local\" - under that name the browser keeps asking. "
            "\"Create new\" includes it; after that the certificate has to "
            "go to the other racks again."
        ),
        "settings_tls_pin_required": (
            "A PIN has to be set before the certificate can be handled - "
            "without one, anybody on the network could fetch the private "
            "key."
        ),
        "settings_tls_download": "Download certificate",
        "settings_tls_download_hint": (
            "To stop the browser asking at all: download the file and add "
            "it to the device's certificate store (Android: Settings → "
            "Security → Install a certificate → CA certificate; "
            "iPhone/iPad: install the profile, then enable it under "
            "Certificate Trust Settings). The file holds only the public "
            "part - no password needed."
        ),
        "settings_tls_not_installable": (
            "This certificate cannot be added to a device as a certificate "
            "authority. \"Create new\" makes one that can."
        ),
        "settings_tls_password": "Password for the file",
        "settings_tls_export": "Save",
        "settings_tls_import": "Load",
        "settings_tls_renew": "Create new",
        "settings_tls_exported": (
            "Saved. Without the password the file is worthless - with it, "
            "someone can impersonate this XRack."
        ),
        "settings_tls_imported_ok": (
            "Loaded. It takes effect after the service restarts."
        ),
        "settings_tls_renewed": (
            "New certificate created. It takes effect after the service "
            "restarts, and the browser will ask once more afterwards."
        ),
        "confirm_tls_renew": (
            "Create a new certificate? The old one stops being valid: the "
            "browser will ask again on every device, and certificates "
            "transferred to other racks will no longer match."
        ),
        "faders_snapshot_label": "Snapshot",
        "faders_snapshot_load": "Load",
        "faders_snapshot_unnamed": "Snapshot {n}",
        "confirm_snapshot_load": (
            "Really load snapshot \"{name}\"? This changes every fader, "
            "mute and sound setting on the mixer."
        ),
        "alert_snapshot_loaded": "Snapshot \"{name}\" loaded.",
        "alert_snapshot_failed": "Could not load the snapshot: {message}",
        "faders_search": "Search for mixer again",
        "alert_console_search_found": "Mixer found: {ip}",
        "alert_console_search_none": (
            "No mixer found. Check that it is switched on and connected - "
            "you can also enter the IP by hand in the settings menu."
        ),
        "alert_console_search_failed": "Search failed.",
        "settings_console_access_waiting": (
            "Waiting for the console - is it plugged in and switched on?"
        ),
        "settings_app_ip_label": "Enter this in your control app:",
        "settings_console_ip_label": "Console at the Pi:",
        "settings_console_host_label": "Mixer IP address",
        "settings_console_host_placeholder": "automatic",
        "settings_console_host_hint": "Only needed if the router blocks the search. Empty = automatic.",
        "settings_console_host_invalid": "That is not a valid IPv4 address.",
        "settings_console_host_manual": "In use: {ip} (entered by hand)",
        "settings_console_host_lease": "In use: {ip} (registered at the Pi)",
        "settings_console_host_discovered": "In use: {ip} (found on the network)",
        "settings_console_host_none": "No mixer found.",
        "settings_faders_autolock_title": "Lock channel strips automatically",
        "settings_faders_autolock_unit": "seconds",
        "settings_faders_autolock_hint": "5 to 3600 seconds.",
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
        "settings_update_hint": "Put a ZIP from GitHub on a USB stick, or load it straight from the internet.",
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
        "settings_selftest_title": "Network self-test",
        "settings_selftest_run": "Run self-test",
        "settings_selftest_copy": "Copy",
        "settings_selftest_hint": (
            "Checks radios, access point, home network and console at once."
        ),
        "alert_selftest_copied": "Copied to the clipboard.",
        "alert_selftest_failed": "Could not run the self-test.",
        "settings_diagnostics_title": "Diagnostic recording",
        "settings_diagnostics_label": "Recording is running",
        "settings_diagnostics_hint": "Records state and network for troubleshooting.",
        "btn_diagnostics_download": "Download recording",
        "settings_diagnostics_empty": "Nothing recorded yet.",
        "settings_stillstand_titel": "Measured stalls:",
        "settings_stillstand_keiner": (
            "No stalls measured - the process kept running."
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
        "faders_usb_off": "A/D",
        "faders_usb_on": "USB",
        "faders_usb_title": (
            "Channel input: A/D = mic/instrument on the console, "
            "USB = whatever XRack plays back (virtual soundcheck). "
            "Careful: on USB the channel does not hear its microphone."
        ),
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

        # Lighting (DMX)
        "light_title": "Lighting",
        "light_settings_group": "Lighting",
        "light_enable": "Use lighting control",
        "light_enable_hint": (
            "Controls DMX fixtures through a USB-to-DMX cable. Not "
            "needed without one."
        ),
        "light_output_title": "DMX output",
        "light_output_hint": (
            "Once after installation: this is the port XRack sends "
            "to. XRack uses exactly one - picking another replaces "
            "the current one."
        ),
        "light_output_assign": "Assign",
        "light_output_none": (
            "No output found. Is the lighting service running and the "
            "DMX cable plugged in?"
        ),
        "light_output_patched": "Assigned: {name}",
        "light_output_unpatched": "No output assigned yet.",
        "light_output_done": "Assigned.",
        "light_setup": "Set up",
        "light_blackout": "All off",
        "light_no_fixtures": (
            "No fixtures set up yet - add them under \"Set up\"."
        ),
        "light_service_missing": (
            "The lighting service is not responding. Is olad running?"
        ),
        "light_adapter_missing": "No DMX cable detected.",
        "light_unpatched": (
            "No DMX output assigned yet - the fixtures stay dark. "
            "Under \"Lighting\" in the settings."
        ),
        "light_overlap_warning": (
            "Careful: two fixtures use the same channels. That is "
            "allowed, but rarely intended."
        ),
        "light_brightness": "Brightness",
        "light_segment": "Segment {n}",

        # Lighting: setup
        "light_setup_title": "Set up lighting",
        "light_export": "Save setup",
        "light_import_confirm": (
            "Load the saved setup? Templates, fixtures and scenes on this "
            "unit will be replaced, and the lights go out."
        ),
        "light_import_failed": "The setup could not be loaded.",
        "light_import": "Load setup",
        "light_transfer_hint": (
            "Takes templates, fixtures, scenes and show settings with it - "
            "for moving to a second XRack. Wi-Fi, PIN, device name and "
            "console address stay where they are. Loading replaces the "
            "current setup."
        ),
        "light_fixtures_title": "Fixtures",
        "light_fixture_new": "Create a fixture from a template",
        "light_templates_title": "Fixture types",
        "light_template_new": "Create your own template",
        "light_name": "Name",
        "light_template": "Type",
        "light_address": "Start address",
        "light_kind": "Kind",
        "light_kind_effect": "Effect light",
        "light_kind_background": "Background light 1",
        "light_kind_background2": "Background light 2",
        "light_kind_static": "Left out of the show",
        "light_kind_hint": (
            "Effect lights follow the beat. The two background groups "
            "change colour slowly, each with its own colours and offset "
            "against each other. Fixtures left out keep whatever was set "
            "by hand or from a scene."
        ),
        "light_address_range": "DMX {von}–{bis}",
        "light_address_occupies": "Occupies DMX {von}–{bis}.",
        "light_channels_count": "{n} channels",
        "light_template_name": "Type name",
        "light_template_pattern": "Channels (pattern)",
        "light_template_repeat": "Repeats",
        "light_template_repeat_hint": (
            "For devices with several identical segments: give the "
            "pattern once, enter the number of segments."
        ),
        "light_template_add_channel": "Channel",
        "light_template_builtin": "built in",
        "confirm_light_fixture_delete": "Really delete fixture \"{name}\"?",
        "confirm_light_template_delete": "Really delete type \"{name}\"?",
        "confirm_light_scene_delete": "Really delete scene \"{name}\"?",

        # Lighting: scenes
        "light_scenes_title": "Scenes",
        "light_no_scenes": (
            "No scene saved yet. Set the fixtures, then save."
        ),
        "light_scene_save": "Save current state",
        "light_scene_name_prompt": "Scene name:",

        # Lighting: channel roles
        "light_role_dimmer": "Dimmer",
        "light_role_red": "Red",
        "light_role_green": "Green",
        "light_role_blue": "Blue",
        "light_role_white": "White",
        "light_role_amber": "Amber",
        "light_role_uv": "UV",
        "light_role_pan": "Pan",
        "light_role_pan_fine": "Pan fine",
        "light_role_tilt": "Tilt",
        "light_role_tilt_fine": "Tilt fine",
        "light_role_gobo": "Gobo",
        "light_role_gobo_rotation": "Gobo rotation",
        "light_role_color_wheel": "Colour wheel",
        "light_role_strobe": "Strobe",
        "light_role_shutter": "Shutter",
        "light_role_rotation": "Rotation",
        "light_role_laser": "Laser",
        "light_role_generic": "Other channel",

        # Lighting: music-driven show
        "light_show_title": "Music show",
        "light_show_start": "Start show",
        "light_show_stop": "Stop show",
        "light_show_settings": "Show settings",
        "light_show_channel": "Light show source",
        "light_show_channel_hint": (
            "What the light show listens to. A channel pair is the "
            "simple way; a single channel saves a USB channel and "
            "allows a mix just for the lighting - an aux bus with the "
            "kick up front and no vocals, say. Careful: the same "
            "channel on its own is twice as loud as one half of a pair "
            "- check the silence threshold below afterwards."
        ),
        "light_show_channel_pairs": "Channel pair",
        "light_show_channel_single": "Single channel",
        "light_show_sensitivity": "Sensitivity",
        "light_show_background_seconds": "Background: inertia",
        "light_show_effect_mode": "Effect light: look",
        "light_show_effect_mode_runner": "Moving point",
        "light_show_effect_mode_pulse": "Pulse on the beat",
        "light_show_effect_mode_hint": (
            "Moving point: one segment after another lights up. "
            "Pulse: all segments breathe together on the beat. The "
            "background light stays a wash either way."
        ),
        "light_show_pulse_seconds": "Pulse: afterglow",
        "light_show_pulse_base": "Pulse: base brightness",
        "light_show_pulse_hint": (
            "How long a beat glows on, and how bright it stays "
            "between two beats. 0 % means: fully dark in between."
        ),
        "light_show_color_invert": "Reverse colours",
        "light_show_color_invert_hint": (
            "Reverses the order of the band colours across the effect "
            "lights: red-green-blue becomes blue-green-red, and back "
            "again after the same number of beats. Brightness and "
            "movement stay as they are; the background light is not "
            "affected."
        ),
        "light_show_invert_beats": "Reverse colours: every",
        "light_show_snare_strobe": "Flash",
        "light_show_snare_hint": (
            "Flashes the strobe channels of the effect lights on "
            "particularly loud hits. While this is off the show does "
            "not touch strobe channels at all - while it is on they "
            "belong to the show, and a value set by hand is overwritten."
        ),
        "light_show_snare_sense": "Flash: sensitivity",
        "light_show_snare_power": "Flash: strength",
        "light_show_snare_options_hint": (
            "Higher means MORE flashes - at 50 % the strong hits come "
            "through, further up the running beat does too. What the "
            "strength does on your fixture - brightness or strobe speed "
            "- is in its channel table; try it out."
        ),
        "light_show_background_beats": "Background: colour change",
        "light_show_fade_seconds": "Fade into the scene",
        "light_show_beats_unit": "every {n} beats",
        "light_show_background_warning": (
            "The fade is longer than half the hold time - the colours no "
            "longer arrive and blur into a mid tone. Shorten the inertia "
            "or lengthen the colour change."
        ),
        "light_show_colors": "Colours: effect light",
        "light_show_colors_1": "Colours: background light 1",
        "light_show_colors_2": "Colours: background light 2",
        "light_show_colors_1_hint": (
            "Only for fixtures in the \"Background light 1\" group."
        ),
        "light_show_colors_2_hint": (
            "Only for fixtures in the \"Background light 2\" group. It runs one colour offset so two different colours are always on stage."
        ),
        "light_show_color_low": "Lows",
        "light_show_color_mid": "Mids",
        "light_show_color_high": "Highs",
        "light_show_colors_hint": (
            "The three colours are mixed by how loud each band is. "
            "A matter of taste - try it out."
        ),
        "light_show_fallback": "Scene for speech or silence",
        "light_show_fallback_none": "Lights off",
        "light_show_fallback_hint": (
            "When the music stops, XRack switches to this."
        ),
        "light_show_silence_threshold": "Level counted as silence",
        "light_show_level_hint": (
            "The \"Total\" bar and the threshold are in dBFS - the same scale as on the mixer."
        ),
        "light_show_silence_seconds": "Wait before silence (seconds)",
        "light_show_speech_seconds": "Wait before speech (0 = off)",
        "light_show_tuning_hint": (
            "These depend on the signal that reaches you - try them out "
            "on site."
        ),
        "light_show_state_music": "Music",
        "light_show_state_speech": "Speech",
        "light_show_state_silence": "Silence",
        "light_show_band_low": "Low",
        "light_show_band_mid": "Mid",
        "light_show_band_high": "High",
        "light_show_band_level": "Total",
        "light_show_no_stream": (
            "No audio is arriving. Is the right channel pair selected, and "
            "is there a signal on it?"
        ),
    },
}


def get_translations(language: str) -> dict[str, str]:
    """
    Liefert das Übersetzungswörterbuch für die angegebene Sprache,
    mit Deutsch als Fallback für unbekannte Sprachcodes.
    """

    return TRANSLATIONS.get(language, TRANSLATIONS[DEFAULT_LANGUAGE])
