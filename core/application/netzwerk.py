"""
WLAN, Bridge, Zugang zur Konsole aus dem Heimnetz und die
Portweiterleitung.
"""

import time

from core.wlan_control import SHARE_CONNECTION


class NetzwerkMixin:
    """
    WLAN, Bridge, Zugang zur Konsole aus dem Heimnetz und die

    Teil von Application - siehe core/application/__init__.py.
    """
    #
    # Wie oft die Portweiterleitung abgeglichen wird (Sekunden) - siehe
    # _reconcile_port_forward(). Schnell genug, dass die Konsole nach
    # einem Neustart praktisch sofort erreichbar ist, und selten genug,
    # dass die paar nmcli-/DHCP-Aufrufe nicht ins Gewicht fallen.
    #
    PORT_FORWARD_INTERVAL = 20.0


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
