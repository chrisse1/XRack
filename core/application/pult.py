"""
Steuerung des Mischpults ueber OSC: Fader, Stummschaltung,
Kopplung - und die Frage, unter welcher Adresse das Pult
ueberhaupt erreichbar ist.
"""

import ipaddress

from core.console_control import MIN_DB

#
# Grenzen für die automatische Sperre der Kanalzüge. Unter fünf
# Sekunden wäre sie unbenutzbar - der Regler wäre gesperrt, bevor man
# ihn losgelassen hat. Nach oben eine Stunde; danach ist es praktisch
# "aus", und dafür gibt es den Schalter.
#
AUTOLOCK_MIN_SECONDS = 5
AUTOLOCK_MAX_SECONDS = 3600
AUTOLOCK_DEFAULT_SECONDS = 60


class PultMixin:
    """
    Steuerung des Mischpults ueber OSC: Fader, Stummschaltung,

    Teil von Application - siehe core/application/__init__.py.
    """

    def _console_host_and_channels(self) -> tuple[str | None, int, str]:
        """
        Liefert IP und Herkunft des Mischpults sowie die Kanalzahl des
        Interfaces.

        Die IP wird in fester Reihenfolge gesucht:

        1. Von Hand eingetragen - wer sie einträgt, hat einen Grund;
           das schlägt jede Automatik.
        2. Aus der DHCP-Vergabeliste des Pi. Die gibt es nur, wenn der
           Pi selbst die Adresse vergeben hat, also bei der
           Ethernet-Freigabe oder der Bridge.
        3. Per Rundruf. Das ist der Fall, für den es die anderen beiden
           nicht gibt: Pult und Pi hängen zusammen an einem Router, der
           die Adressen vergibt - dann weiß der Pi von sich aus nichts
           von der Konsole.
        """

        channels = (
            self.selected_audio_device.channels
            if self.selected_audio_device is not None
            else 0
        )

        manual = (self.state_store.get("console_ip_manual") or "").strip()

        if manual:
            return manual, channels, "manual"

        lease = self.wlan_control.get_status().get("console_ip")

        if lease:
            return lease, channels, "lease"

        return self.console_control.discover(), channels, "discovered"


    # ----------------------------------------------------------------
    # Snapshots (X-Air) bzw. Szenen (X32)
    # ----------------------------------------------------------------

    def get_console_snapshots(self, force: bool = False) -> dict:
        """
        Die gespeicherten Snapshots des Pults zur Auswahl.
        """

        host, _, _ = self._console_host_and_channels()

        if not host:
            return {"available": False, "snapshots": []}

        snapshots = self.console_control.get_snapshots(host, force=force)

        if snapshots is None:
            return {"available": False, "snapshots": []}

        #
        # Unbenutzte Plaetze weglassen - eine Auswahlliste mit 64
        # Eintraegen, von denen drei etwas bedeuten, ist keine Hilfe.
        #
        # Kennt das Pult die Namensadresse nicht, hat KEIN Platz einen
        # Namen. Dann waere die Liste leer, und die Funktion gaebe es
        # praktisch nicht - deshalb in dem Fall alle Plaetze zeigen,
        # nur eben mit Nummern statt Namen.
        #
        benannt = [eintrag for eintrag in snapshots if eintrag["name"]]

        return {
            "available": True,
            "snapshots": benannt if benannt else snapshots,
            "named": bool(benannt),
        }

    def load_console_snapshot(self, index: int) -> tuple[bool, str]:
        """
        Ruft einen Snapshot auf dem Pult auf.
        """

        host, _, _ = self._console_host_and_channels()

        if not host:
            return False, "Kein Mischpult erreichbar."

        try:
            index = int(index)
        except (TypeError, ValueError):
            return False, "Ungültige Snapshot-Nummer."

        if not self.console_control.load_snapshot(host, index):
            return False, "Der Snapshot konnte nicht geladen werden."

        return True, ""

    def get_faders_autolock(self) -> dict:
        """
        Ob und nach wie vielen Sekunden Ruhe sich die Fader-Karte
        wieder von selbst sperrt.
        """

        return {
            "enabled": bool(
                self.state_store.get("faders_autolock_enabled", True)
            ),
            "seconds": int(
                self.state_store.get(
                    "faders_autolock_seconds", AUTOLOCK_DEFAULT_SECONDS
                )
            ),
        }


    def set_faders_autolock(
        self, enabled: bool, seconds: int
    ) -> tuple[bool, str]:
        """
        Stellt die automatische Sperre ein.

        Die Sekunden werden auch dann gemerkt, wenn die Sperre gerade
        aus ist - sonst müsste man sie beim Wiedereinschalten erneut
        eingeben.
        """

        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return False, "Bitte eine Zahl in Sekunden angeben."

        if not (
            AUTOLOCK_MIN_SECONDS <= seconds <= AUTOLOCK_MAX_SECONDS
        ):
            return False, (
                f"Bitte einen Wert zwischen {AUTOLOCK_MIN_SECONDS} und "
                f"{AUTOLOCK_MAX_SECONDS} Sekunden angeben."
            )

        self.state_store.set("faders_autolock_enabled", bool(enabled))
        self.state_store.set("faders_autolock_seconds", seconds)

        self.logger.info(
            "Automatische Fader-Sperre: %s (%d s)",
            "an" if enabled else "aus",
            seconds,
        )

        return True, ""


    # ----------------------------------------------------------------
    # Stereopaar direkt aus der Musikspieler-/Bluetooth-Karte regeln
    # ----------------------------------------------------------------

    def get_console_pair(self, start: int) -> dict:
        """
        Pegel und Stummschaltung des Stereopaars, das in einer der
        beiden Karten gewählt ist.
        """

        host, channels, _ = self._console_host_and_channels()

        if not host or channels <= 0:
            return {"available": False, "start": start}

        result = self.console_control.get_pair(host, channels, start)

        if result is None:
            return {"available": False, "start": start}

        return {
            "available": True,
            "start": start,
            #
            # Ob XRack selbst gekoppelt hat - nur das bietet es später
            # wieder zum Entkoppeln an.
            #
            "linked_by_xrack": start in self._linked_by_xrack(),
            **result,
        }


    def set_console_pair_fader(self, start: int, db: float | None) -> bool:
        """Setzt den Pegel des Stereopaars."""

        host, channels, _ = self._console_host_and_channels()

        if not host or channels <= 0:
            return False

        return self.console_control.set_pair_fader(
            host,
            channels,
            start,
            MIN_DB if db is None else db,
        )


    def set_console_pair_mute(self, start: int, muted: bool) -> bool:
        """Schaltet das Stereopaar stumm oder wieder an."""

        host, channels, _ = self._console_host_and_channels()

        if not host or channels <= 0:
            return False

        return self.console_control.set_pair_mute(host, channels, start, muted)


    def _linked_by_xrack(self) -> set[int]:
        """Welche Paare XRack selbst gekoppelt hat."""

        return set(self.state_store.get("console_linked_by_xrack", []) or [])


    def set_console_pair_link(self, start: int, linked: bool) -> bool:
        """
        Koppelt ein Kanalpaar am Pult oder hebt die Kopplung auf.

        XRack merkt sich, was es selbst gekoppelt hat. Nur diese Paare
        bietet es später zum Entkoppeln an - eine Kopplung, die der
        Nutzer am Pult selbst eingerichtet hat, gehört ihm und darf
        XRack nicht ungefragt wieder auflösen.
        """

        host, channels, _ = self._console_host_and_channels()

        if not host or channels <= 0:
            return False

        if not self.console_control.set_link(host, channels, start, linked):
            return False

        gemerkt = self._linked_by_xrack()

        if linked:
            gemerkt.add(start)
        else:
            gemerkt.discard(start)

        self.state_store.set("console_linked_by_xrack", sorted(gemerkt))

        self.logger.info(
            "Kanalpaar %d+%d %s",
            start,
            start + 1,
            "gekoppelt" if linked else "entkoppelt",
        )

        return True


    def get_console_host(self) -> dict:
        """
        Welche IP für das Pult benutzt wird und woher sie stammt -
        fürs Einstellungen-Modal.

        Bewusst nicht über get_console_channels(): Das läse alle Kanäle
        aus, nur um eine Adresse anzuzeigen.
        """

        host, _, source = self._console_host_and_channels()

        return {
            "manual": (self.state_store.get("console_ip_manual") or ""),
            "host": host or "",
            "source": source if host else "",
        }


    def set_console_host(self, ip: str) -> tuple[bool, str]:
        """
        Trägt die IP des Mischpults von Hand ein. Ein leerer Wert
        schaltet zurück auf die automatische Suche.

        Gebraucht wird das als Rückfall: Manche Router lassen Rundrufe
        zwischen WLAN und Kabel nicht durch, dann findet der Suchlauf
        nichts, obwohl das Pult erreichbar ist.
        """

        ip = (ip or "").strip()

        if ip:

            try:
                ipaddress.IPv4Address(ip)
            except ValueError:
                return False, "Das ist keine gültige IPv4-Adresse."

        self.state_store.set("console_ip_manual", ip)

        #
        # Gemerkte Familie verwerfen: Eine neue Adresse kann ein
        # anderes Pult sein, und die Erkennung haengt am Host.
        #
        self.console_control.detect_reset()

        self.logger.info(
            "Pult-IP von Hand gesetzt: %s",
            ip or "(automatisch)",
        )

        return True, ""


    def get_console_channels(self) -> dict:
        """
        Liefert Kanalnamen und Faderstellungen des Mischpults für die
        Fader-Karte.

        Unterscheidet zwei Fälle, damit die Oberfläche sie erklären
        kann: kein Steuerweg (Konsole nicht per Kabel erreichbar) und
        Steuerweg da, aber Pult antwortet nicht.
        """

        host, channels, source = self._console_host_and_channels()

        if not host or channels <= 0:
            return {
                "available": False,
                "reason": "no_connection",
                "host": "",
                "host_source": "",
                "channels": [],
            }

        result = self.console_control.get_channels(host, channels)

        if result is None:
            return {
                "available": False,
                "reason": "no_response",
                "host": host,
                "host_source": source,
                "channels": [],
            }

        return {
            "available": True,
            "reason": "",
            "host": host,
            "host_source": source,
            "channels": result,
        }


    def set_console_fader(self, channel: int, db: float | None) -> bool:
        """
        Setzt einen Kanalfader. `db` ist None, wenn der Fader ganz zu
        sein soll (-unendlich).
        """

        host, channels, _ = self._console_host_and_channels()

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

        host, channels, _ = self._console_host_and_channels()

        if not host or channels <= 0:
            return False

        return self.console_control.set_mute(host, channels, channel, muted)
