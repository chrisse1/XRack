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

import json
import logging
import re
import time
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
# So schreibt olad die Kennung eines Anschlusses: die Nummer des
# Geraets, die Richtung (O = Ausgang, I = Eingang) und die Nummer
# des Anschlusses am Geraet, etwa "2-O-1". Genau die drei Angaben
# will auch "ola_patch -d 2 -p 1" auf der Kommandozeile.
#
PORT_MUSTER = re.compile(r"^(\d+)-([IO])-(\d+)$")

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
    # Unter diesem Namen legt XRack das Universum an, falls es noch
    # keines gibt. Ein vorhandenes behaelt seinen Namen.
    #
    UNIVERSE_NAME = "XRack"

    #
    # So lange gilt die gemerkte Auskunft, ob ein Ausgang zugeordnet
    # ist (siehe __init__).
    #
    ZUORDNUNG_GILT_S = 5.0

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

        #
        # Gemerkt, ob ein Ausgang zugeordnet ist.
        #
        # Die Lichtkarte fragt den Zustand zweimal je Sekunde ab.
        # Diese eine Auskunft aendert sich aber nur, wenn jemand sie
        # von Hand aendert - sie jedes Mal bei olad zu erfragen,
        # waere ein Dauerfeuer auf denselben Dienst, der nebenbei
        # das DMX-Bild takten soll. Nach einer Zuordnung wird der
        # Merker verworfen, damit die Karte sofort umspringt.
        #
        self._zuordnung = None
        self._zuordnung_zeit = 0.0

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

        #
        # Einmal fragen, zweimal verwenden: Laeuft der Dienst nicht,
        # braucht die Zuordnung gar nicht erst erfragt zu werden.
        #
        laeuft = self.service_running

        return {
            "service_running": laeuft,
            "adapter_present": bool(adapter),
            "adapters": adapter,
            "universe": self.UNIVERSE,
            "channels": self.CHANNELS,
            "patched": self.patched if laeuft else False,
        }

    # ----------------------------------------------------------------
    # Den Ausgang dem Universum zuordnen
    #
    # Nach der Installation kennt olad das Kabel zwar, schickt aber
    # noch nichts hinaus: Ein Anschluss muss erst einem Universum
    # zugeordnet werden ("patchen"). Auf der Kommandozeile ist das
    #
    #     ola_dev_info                        # Geraet und Port suchen
    #     ola_patch -d <Geraet> -p <Port> -u 1
    #
    # Genau diese beiden Schritte macht XRack hier selbst - ueber
    # dieselbe Web-Schnittstelle von olad, ueber die auch die
    # Kanalwerte gehen. Es braucht also weiterhin kein sudo und kein
    # Terminal.
    #
    # Ohne diesen Schritt sieht alles heil aus: Der Dienst laeuft,
    # das Kabel steckt, XRack meldet erfolgreich gesendete Bilder -
    # und es bleibt trotzdem dunkel. Deshalb steht die Zuordnung mit
    # im Zustand, damit die Oberflaeche den Fall benennen kann.
    # ----------------------------------------------------------------

    def _abfragen(self, pfad: str):
        """Eine JSON-Auskunft von olad holen. None, wenn es nicht klappt."""

        try:

            with self._opener.open(self.base_url + pfad,
                                   timeout=self.STATUS_TIMEOUT) as antwort:

                return json.loads(antwort.read().decode("utf-8", "replace"))

        except Exception as fehler:

            self.logger.warning("DMX: %s nicht abrufbar (%s)", pfad, fehler)
            return None

    def _auftrag(self, pfad: str, felder: dict) -> tuple[bool, str]:
        """Einen Auftrag an olad schicken. (Erfolg, Grund bei Fehlschlag)."""

        daten = urllib.parse.urlencode(felder).encode("utf-8")

        anfrage = urllib.request.Request(
            self.base_url + pfad,
            data=daten,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        try:

            with self._opener.open(anfrage, timeout=self.STATUS_TIMEOUT):
                return True, ""

        except Exception as fehler:

            self.logger.warning("DMX: %s fehlgeschlagen (%s)", pfad, fehler)
            return False, str(fehler)

    def _universum(self) -> dict | None:
        """
        Der Eintrag zu Universum 1 aus der Uebersicht - oder None.

        Bewusst ueber die Uebersicht aller Universen und nicht ueber
        /json/universe_info: Gibt es das Universum noch nicht,
        antwortet olad dort mit einem Fehler. Ein Fehler, der jedes
        Mal im Protokoll steht, obwohl er der Normalfall vor der
        ersten Zuordnung ist, verdeckt nur die echten.
        """

        daten = self._abfragen("/json/universe_plugin_list")

        if not isinstance(daten, dict):
            return None

        for eintrag in daten.get("universes") or []:

            if not isinstance(eintrag, dict):
                continue

            if str(eintrag.get("id")) == str(self.UNIVERSE):
                return eintrag

        return None

    def _zugeordnete(self) -> list[dict]:
        """Die Ausgaenge, die gerade in Universum 1 haengen."""

        daten = self._abfragen(f"/json/universe_info?id={self.UNIVERSE}")

        if not isinstance(daten, dict):
            return []

        return [
            eintrag for eintrag in daten.get("output_ports") or []
            if isinstance(eintrag, dict)
        ]

    @staticmethod
    def _beschriftung(eintrag: dict) -> str:
        """Wie der Anschluss in der Auswahl heissen soll."""

        teile = [
            str(eintrag.get(feld) or "").strip()
            for feld in ("device", "description")
        ]

        text = " - ".join(teil for teil in teile if teil)

        treffer = PORT_MUSTER.match(str(eintrag.get("id") or ""))

        if not text:
            text = str(eintrag.get("id") or "")

        return f"{text} (Ausgang {treffer.group(3)})" if treffer else text

    @staticmethod
    def _reihenfolge(eintrag: dict) -> tuple:
        """
        Sortierung der Auswahl.

        OLAs eingebautes Dummy-Plugin bietet Anschluesse an, die
        nirgendwohin fuehren; sie sind zum Ausprobieren gedacht.
        Verstecken waere falsch, aber obenan gehoeren sie nicht -
        sonst steht der erste Vorschlag auf einem Anschluss, an dem
        garantiert keine Lampe haengt.
        """

        blind = "dummy" in str(eintrag.get("device") or "").lower()

        treffer = PORT_MUSTER.match(str(eintrag.get("id") or ""))

        nummern = (
            (int(treffer.group(1)), int(treffer.group(3)))
            if treffer else (0, 0)
        )

        return (1 if blind else 0, nummern)

    def ports(self) -> list[dict]:
        """
        Alle DMX-Ausgaenge, die olad anbietet.

        Zusammengesetzt aus zwei Auskuenften: den noch freien
        Anschluessen und denen, die schon in Universum 1 haengen.
        Ein zugeordneter Anschluss taucht unter den freien naemlich
        nicht mehr auf - und genau der soll in der Auswahl stehen
        bleiben, damit man sieht, worauf XRack gerade sendet.

        Eingaenge bleiben draussen: Dorthin kann XRack nichts
        schicken.
        """

        gefunden: dict[str, dict] = {}

        def aufnehmen(eintrag, zugeordnet: bool):

            if not isinstance(eintrag, dict):
                return

            kennung = str(eintrag.get("id") or "")
            treffer = PORT_MUSTER.match(kennung)

            if not treffer or treffer.group(2) != "O":
                return

            gefunden[kennung] = {
                "id": kennung,
                "device": str(eintrag.get("device") or ""),
                "description": str(eintrag.get("description") or ""),
                "label": self._beschriftung(eintrag),
                "patched": zugeordnet,
            }

        frei = self._abfragen("/json/get_ports")

        for eintrag in frei if isinstance(frei, list) else []:
            aufnehmen(eintrag, False)

        if self._universum() is not None:

            for eintrag in self._zugeordnete():
                aufnehmen(eintrag, True)

        return sorted(gefunden.values(), key=self._reihenfolge)

    @property
    def patched(self) -> bool:
        """True, wenn Universum 1 mindestens einen Ausgang hat."""

        jetzt = time.monotonic()

        if (self._zuordnung is not None
                and jetzt - self._zuordnung_zeit < self.ZUORDNUNG_GILT_S):
            return self._zuordnung

        eintrag = self._universum() or {}

        try:
            anzahl = int(eintrag.get("output_ports", 0))

        except (TypeError, ValueError):
            anzahl = 0

        self._zuordnung = anzahl > 0
        self._zuordnung_zeit = jetzt

        return self._zuordnung

    def patch(self, port_id: str) -> tuple[bool, str]:
        """
        Einen Ausgang dem Universum zuordnen. (Erfolg, Meldung).

        XRack sendet in genau ein Universum, also gibt es auch genau
        einen Ausgang: Eine vorherige Zuordnung wird ersetzt. Sonst
        bliebe ein einmal falsch gewaehlter Anschluss fuer immer
        drin, und man braeuchte doch wieder ein Terminal, um ihn
        loszuwerden.
        """

        kennung = str(port_id or "").strip()
        treffer = PORT_MUSTER.match(kennung)

        if not treffer or treffer.group(2) != "O":
            return False, "Das ist keine gültige Kennung für einen DMX-Ausgang."

        eintrag = self._universum()

        felder = {
            "id": self.UNIVERSE,
            "name": self.UNIVERSE_NAME,
            "add_ports": kennung,
        }

        if eintrag is None:
            erfolg, grund = self._auftrag("/new_universe", felder)

        else:

            #
            # Den vorhandenen Namen behalten - modify_universe
            # verlangt ihn und wuerde eine von Hand vergebene
            # Bezeichnung sonst ueberschreiben.
            #
            felder["name"] = str(eintrag.get("name") or self.UNIVERSE_NAME)

            alte = [
                str(port.get("id"))
                for port in self._zugeordnete()
                if str(port.get("id")) != kennung
            ]

            if alte:
                felder["remove_ports"] = ",".join(alte)

            erfolg, grund = self._auftrag("/modify_universe", felder)

        #
        # Den Merker verwerfen, egal wie es ausging: Die Karte soll
        # den neuen Stand zeigen und nicht den von vor fuenf
        # Sekunden.
        #
        self._zuordnung = None

        if not erfolg:
            return False, f"Der Lichtdienst hat die Zuordnung abgelehnt ({grund})."

        #
        # Nachsehen statt glauben: olad beantwortet den Auftrag auch
        # dann mit 200, wenn die Zuordnung im Hintergrund scheitert
        # (etwa weil ein anderes Plugin das Kabel haelt).
        #
        if kennung not in [str(port.get("id")) for port in self._zugeordnete()]:
            return False, (
                "Der Ausgang ist nicht angekommen. Steckt das Kabel, "
                "und läuft der Lichtdienst?"
            )

        return True, ""

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
