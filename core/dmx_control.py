"""
DMX-Ausgabe über OLA (Open Lighting Architecture).

XRack erzeugt das DMX-Signal nicht selbst. Ein DMX-Bild muss alle
23 Millisekunden neu geschrieben werden, mit einer Pause ("Break") von
mindestens 88 Mikrosekunden davor - das ist harte Echtzeit. Würde
XRack das im eigenen Prozess machen, säße es in derselben Python-
Anwendung, die gleichzeitig ALSA-Audio liest und den Webserver
bedient: Jede Aufnahme, jeder Kopiervorgang auf den USB-Stick, jeder
Seitenaufruf wäre eine mögliche Ursache für sichtbares Flackern.

Deshalb übernimmt das der Systemdienst "olad" (Paket "ola", von
install.sh eingerichtet). Er läuft als eigener Prozess mit eigener
Zeitplanung und schreibt fortlaufend das zuletzt gesetzte Bild auf
das USB-Kabel. XRack schickt ihm nur noch Kanalwerte.

Das ist dasselbe Muster wie beim WLAN (hostapd) und bei Bluetooth
(bluetoothd): Der zeitkritische Teil gehört einem ausgereiften
Systemdienst, XRack bleibt der dünne Aufsatz darüber.

Anders als dort braucht es hier keine sudo-Wrapper-Skripte: olad
läuft unter eigenem Benutzer, das USB-Kabel wird über eine
udev-Regel freigegeben (siehe install.sh), und die Verständigung
läuft über einen gewöhnlichen HTTP-Aufruf auf localhost. XRack
braucht dafür keinerlei erhöhte Rechte.
"""

import logging
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

#
# Überschreibbar, damit der Test einen nachgestellten /sys-Baum
# unterschieben kann - wie in core/network_report.py.
#
USB_DEVICES = Path("/sys/bus/usb/devices")

#
# Alle gängigen USB-DMX-Kabel dieser Preisklasse hängen an einem
# FTDI-Chip: das vorhandene Kabel mit FT232RNL ebenso wie Enttecs
# "Open DMX USB" und die meisten Nachbauten. Erkannt wird deshalb
# der Hersteller, nicht ein einzelnes Modell.
#
# Die Liste ist bewusst als Menge geschrieben und darf wachsen -
# taucht ein Kabel hier nicht auf, funktioniert die Ausgabe über
# olad trotzdem, XRack zeigt dann nur "kein Kabel erkannt" an. Das
# ist die harmlosere Richtung: lieber nichts behaupten als etwas
# Falsches.
#
FTDI_VENDOR = "0403"

FTDI_PRODUCTS = {
    "6001",  # FT232R / FT232RNL - das verbreitetste, auch Open DMX USB
    "6010",  # FT2232
    "6011",  # FT4232
    "6014",  # FT232H
    "6015",  # FT230X / FT231X
}


class DmxControl:
    """
    Spricht den DMX-Dienst an und sagt, ob Dienst und Kabel da sind.

    Die Klasse hält keinen Zustand über das Lichtbild - sie schickt
    nur, was ihr gegeben wird. Das Merken übernimmt olad, der das
    zuletzt gesetzte Bild von sich aus weitersendet, bis ein neues
    kommt. Eine statische Szene ist deshalb genau ein Aufruf und
    keine Dauerschleife.
    """

    BASE_URL = "http://127.0.0.1:9090"

    #
    # Ein DMX-Universum hat 512 Kanäle. Mehr Lampen als das passen
    # bräuchten ein zweites Kabel; das ist bewusst nicht vorgesehen
    # (ein Bewegtlicht belegt 8-16 Kanäle, es passen also gut 30
    # Stück hinein).
    #
    UNIVERSE = 1
    CHANNELS = 512

    #
    # Kurz gehalten: Der Aufruf geht über localhost und darf den
    # Licht-Thread nicht aufhalten. Antwortet olad nicht binnen
    # zwei Sekunden, ist ohnehin etwas grundlegend kaputt - dann
    # ist ein ausgelassenes Lichtbild die richtige Reaktion, kein
    # Warten.
    #
    SEND_TIMEOUT = 2.0
    STATUS_TIMEOUT = 3.0

    def __init__(self, base_url: str | None = None,
                 usb_devices: Path | None = None):

        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.usb_devices = usb_devices or USB_DEVICES
        self.logger = logging.getLogger("XRack")

        #
        # Ein eigener Opener ohne Proxy-Behandlung.
        #
        # urllib nimmt sonst ungefragt http_proxy aus der Umgebung -
        # und schickte den Aufruf an 127.0.0.1 dann über einen
        # Proxy, der ihn nie zustellen kann. Auf dem Pi ist meist
        # keiner gesetzt, aber es kostet nichts, das auszuschließen,
        # und der Fehler wäre von außen kaum zu erkennen.
        #
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )

    # ----------------------------------------------------------------
    # Ist überhaupt etwas da?
    # ----------------------------------------------------------------

    def adapters(self) -> list[dict]:
        """
        Alle angeschlossenen FTDI-Geräte, wie der Kernel sie sieht.

        Bewusst über /sys und nicht über olad: Der Kernel weiß es
        sicher, und die Antwort bleibt auch dann brauchbar, wenn der
        Dienst gerade nicht läuft - das ist genau der Fall, in dem
        man wissen will, ob wenigstens das Kabel steckt.

        Ein FTDI-Chip steckt allerdings auch in manchem anderen
        USB-Seriell-Kabel. Ein Treffer hier heißt deshalb "es steckt
        etwas, das ein DMX-Kabel sein könnte" - nicht "DMX
        funktioniert". Das entscheidet erst der Ausgabetest.
        """

        gefunden = []

        if not self.usb_devices.exists():
            return gefunden

        for geraet in sorted(self.usb_devices.iterdir()):

            try:
                hersteller = (geraet / "idVendor").read_text().strip().lower()
                produkt = (geraet / "idProduct").read_text().strip().lower()

            except OSError:
                continue

            if hersteller != FTDI_VENDOR or produkt not in FTDI_PRODUCTS:
                continue

            try:
                name = (geraet / "product").read_text().strip()
            except OSError:
                name = ""

            gefunden.append({
                "device": geraet.name,
                "product_id": produkt,
                "name": name,
            })

        return gefunden

    @property
    def adapter_present(self) -> bool:
        """True, wenn ein FTDI-Gerät angeschlossen ist."""

        return bool(self.adapters())

    @property
    def service_running(self) -> bool:
        """
        True, wenn olad auf localhost antwortet.

        Es zählt allein, dass überhaupt eine HTTP-Antwort kommt -
        auch ein 404 beweist, dass da ein Dienst lauscht. Damit
        hängt die Prüfung an keinem bestimmten Pfad der OLA-Web-
        Schnittstelle, der sich mit einer neuen Version ändern
        könnte.
        """

        try:

            self._opener.open(self.base_url + "/", timeout=self.STATUS_TIMEOUT)
            return True

        except urllib.error.HTTPError:
            return True

        except Exception:
            return False

    def status(self) -> dict:
        """Alles, was die Oberfläche über den Zustand wissen muss."""

        adapter = self.adapters()

        return {
            "service_running": self.service_running,
            "adapter_present": bool(adapter),
            "adapters": adapter,
            "universe": self.UNIVERSE,
            "channels": self.CHANNELS,
        }

    # ----------------------------------------------------------------
    # Senden
    # ----------------------------------------------------------------

    def send(self, values: list[int]) -> bool:
        """
        Ein Lichtbild an olad schicken. True bei Erfolg.

        Erwartet Kanalwerte ab Kanal 1, höchstens 512 Stück. Kürzere
        Listen sind erlaubt - olad lässt den Rest des Universums
        dann unangetastet.

        Werte außerhalb von 0-255 werden abgeschnitten statt
        abgewiesen: Ein Rechenfehler in der Lichtberechnung soll die
        Show nicht anhalten, sondern höchstens eine Lampe falsch
        aussteuern.
        """

        if len(values) > self.CHANNELS:
            self.logger.warning(
                "DMX: %d Werte übergeben, das Universum hat nur %d Kanäle - "
                "der Rest wird verworfen.", len(values), self.CHANNELS
            )
            values = values[:self.CHANNELS]

        begrenzt = [max(0, min(255, int(wert))) for wert in values]

        daten = urllib.parse.urlencode({
            "u": self.UNIVERSE,
            "d": ",".join(str(wert) for wert in begrenzt),
        }).encode("ascii")

        anfrage = urllib.request.Request(
            self.base_url + "/set_dmx",
            data=daten,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        try:

            with self._opener.open(anfrage, timeout=self.SEND_TIMEOUT):
                return True

        except Exception as fehler:

            #
            # Nur eine Warnung, kein Weiterreichen: Licht darf nie
            # Aufnahme oder Wiedergabe stören. Fällt der Dienst aus,
            # bleibt es dunkel - und XRack läuft weiter.
            #
            self.logger.warning("DMX: Senden fehlgeschlagen (%s)", fehler)
            return False

    def blackout(self) -> bool:
        """Alle Kanäle auf 0 - das Licht geht aus."""

        return self.send([0] * self.CHANNELS)
