"""
Diagnose-Aufzeichnung: schreibt im Hintergrund mit, wie es XRack und
dem Netzwerk geht - gedacht für Fehler, die nur sporadisch auftreten
und die man deshalb nicht "live" beobachten kann.

Anlass war ein Aussetzer der Netzwerkverbindung, der zunächst nur
während der Wiedergabe aufzutreten schien. Ein von Hand gestartetes
Skript hätte bei jedem Neustart neu gestartet werden müssen, in der
Hoffnung, dass der Fehler gerade dann auftritt.

Was die Aufzeichnung dann wirklich gezeigt hat (Protokoll vom
12.09.2026): XRack war im Leerlauf, kühl und unbelastet - und mitten
in der Zeitreihe stand eine zweite Startzeile. Der Prozess war
ersetzt worden. Daraus sind drei Lehren in diese Datei eingebaut:

  1. Ein Neustart muss als Neustart dastehen, nicht als unscheinbare
     Kopfzeile mitten in der Datei. Dazu die Laufzeit des Systems: Sie
     trennt "nur der Dienst war weg" von "der ganze Rechner war weg".
  2. Ein Urteil erst, wenn es eines ist. "netz=WEG" stand nach EINEM
     verlorenen Ping da - auf WLAN ist das Alltag. Jetzt braucht es
     drei in Folge, und dazwischen steht ein Fragezeichen.
  3. Ein Ausfall braucht einen Anfang und ein Ende mit Dauer. Zeilen
     zu zählen ist keine Messung.

Der entscheidende Vorteil gegenüber einem externen Skript: Von hier aus
ist sichtbar, was XRack im Moment des Aussetzers *tat* - spielt es ab,
nimmt es auf, welche Datei, welches Gerät. Genau diese Zuordnung fehlt
einem Beobachter von außen.

**Die bekannte Grenze:** Ein Wächter innerhalb des überwachten
Programms kann seinen eigenen Stillstand nicht melden. Steht der ganze
Prozess, schreibt auch dieser Thread nichts. Das ist hier aber kein
blinder Fleck, sondern die Messung selbst: Der Thread prüft bei jedem
Durchlauf, wie viel Zeit seit dem letzten wirklich vergangen ist, und
schreibt eine ausdrückliche Zeile, wenn daraus eine Lücke wird. Eine
Lücke von zwölf Sekunden in einer Sekundentaktung ist ein Befund.

Was NICHT geht: Kernel-Meldungen (dmesg - USB-Resets, WLAN-Aussetzer).
Die brauchen Root-Rechte und damit einen weiteren sudoers-Eintrag, der
wiederum einen Lauf von install.sh erzwingen würde. Deshalb werden hier
genaue Zeitstempel geschrieben, damit man sie von Hand mit
`sudo dmesg -T` abgleichen kann.
"""

import logging
import logging.handlers
import os
import psutil

from audio.geraetewache import GERAETEWACHE
import signal
import socket
import ssl
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "diagnose.log"

#
# Wo die Funkdaten stehen. Als Konstanten, damit der Versuch sie
# nachstellen kann - auf diesem Rechner gibt es kein WLAN, und ohne
# Nachstellung waere der interessanteste Teil ungeprueft.
#
WIRELESS_PROC = Path("/proc/net/wireless")
NET_SYS = Path("/sys/class/net")

#
# Drei Dateien à 4 MB reichen für mehrere Tage Aufzeichnung, ohne dass
# die Platte volläuft.
#
MAX_BYTES = 4 * 1024 * 1024
BACKUP_COUNT = 3

INTERVAL = 1.0

#
# Ist mehr als das Doppelte des Takts vergangen, stand etwas - dann
# wird das ausdrücklich vermerkt.
#
GAP_THRESHOLD = 3.0

#
# ------------------------------------------------------------------
# Die Stillstands-Wache
# ------------------------------------------------------------------
#
# Der Takt oben ist eine Sekunde, die Lücke oben zählt ab drei - für
# einen Prozess, der stehen bleibt, ist das grob: Ein Einfrierer von
# anderthalb Sekunden hinterlässt damit gar nichts, obwohl er im
# Browser schon als "nicht erreichbar" ankommt.
#
# Genau davon gibt es einen Bericht vom Gerät: "Das Interface war
# wieder kurz nicht erreichbar, als ich einen Übemix starten wollte.
# Ich habe das Gefühl, es passiert immer, wenn ich eine Wiedergabe
# starten oder stoppen will." Ohne Protokoll, ohne Absturz.
#
# Deshalb eine eigene Wache mit feinem Takt. Sie tut nichts, als zu
# schlafen und zu messen, wie spät sie aufgewacht ist. Das ist der
# eine Befund, den ein Prozess über sich selbst erheben kann: Kommt
# sie zu spät, lief in dieser Zeit KEIN Python - und das trifft dann
# auch den Webserver.
#
# Der häufigste Grund dafür in XRack ist das Öffnen oder Schließen
# eines Audiogeräts: pyalsaaudio hält dabei den GIL (Quellenlage in
# audio/geraetewache.py). Genau deshalb fragt die Wache dort nach,
# was gerade lief - eine Zahl allein sagt nur, DASS es stand.
#
STILLSTAND_TAKT = 0.2
STILLSTAND_SCHWELLE = 0.5

#
# Wie viele Befunde höchstens warten, bis der Haupttakt sie schreibt.
# Mehr braucht niemand: Wer fünfzig Einfrierer in einer Sekunde hat,
# erfährt aus den ersten zehn dasselbe.
#
STILLSTAND_MERKE_MAX = 10

#
# Solange nichts auffällt, genügt ein Lebenszeichen - sonst wäre die
# Datei voller identischer Zeilen.
#
HEARTBEAT = 30.0

REQUEST_TIMEOUT = 2.0

#
# So viele verlorene Pings in Folge braucht es, bis das Netz als weg
# gilt. Ein einzelnes verlorenes ICMP-Paket ist auf WLAN Alltag, und
# manche Router beantworten ohnehin nicht jeden Ping - vorher steht
# deshalb kein Urteil da, sondern ein Fragezeichen (dieselbe Regel wie
# bei der Samplerate, siehe recorder/rate_check.py).
#
PING_VERSUCHE = 3

#
# Die XRack-Dienste neben dem Hauptdienst. Sie laufen eigenstaendig,
# und wenn einer davon im Kreis scheitert, merkt es sonst niemand.
#
NEBENDIENSTE = (
    "xrack-hostapd.service",
    "xrack-bt-agent.service",
)

#
# Wie oft nach den Nebendiensten gesehen wird. Jede Sekunde waere
# Verschwendung - ein Dienst, der scheitert, scheitert auch in einer
# Minute noch.
#
DIENSTE_INTERVALL = 60.0

#
# Was als "geht nicht" gilt.
#
# Nicht die Zahl der Neustarts: Ein Dienst, der oft gestolpert und
# dann oben geblieben ist, braucht keine Meldung - sonst gewoehnt man
# sich an die Warnung. Massgeblich ist, wie der letzte Lauf ENDETE.
# Ein normaler Start hat Result=success, auch waehrend er noch
# hochkommt; ein Dienst im Kreis hat Result=exit-code.
#
# Der Anlass: xrack-hostapd.service stand am Geraet bei 14.469
# Fehlstarts - einer alle fuenf Sekunden, einundzwanzig Stunden lang.
# Jeder Versuch zog ueber ExecStartPre eine Neuaktivierung der
# NetworkManager-Bruecke nach sich. Im Protokoll von XRack war davon
# nichts zu sehen; sichtbar war nur, dass gelegentlich das Netz
# wegblieb.
#
# "exec-condition" gehoert ausdruecklich dazu, also zum Unauffaelligen:
# So sagt systemd, dass eine ExecCondition den Start UEBERSPRUNGEN hat
# (xrack-hostapd.service tut das, wenn der USB-Stick nicht steckt -
# siehe scripts/xrack-ap-bereit.sh). Das ist der gewollte Zustand und
# kein Fehler. Stuende er hier nicht, meldete die Aufzeichnung jedem
# Betrieb ohne Stick einen Defekt - und eine Warnung, die im
# Normalfall angeht, ist bald keine mehr.
#
ERGEBNIS_OK = ("success", "exec-condition", "")

#
# Bis zu dieser Laufzeit gilt der Prozess als "gerade erst gestartet".
# Darueber schreibt die Aufzeichnung eine ausdrueckliche Zeile: Ein
# Neustart, den niemand bemerkt, ist der Fehler, den man am laengsten
# sucht.
#
JUNG_S = 60.0


class Diagnostics:
    """
    Schreibt in festem Takt einen Zustandsschnappschuss mit - aber nur
    dann eine Zeile, wenn sie etwas aussagt.
    """

    def __init__(self, application):

        self.logger = logging.getLogger("XRack")

        #
        # Rückverweis auf die Application, um deren eigenen Zustand
        # (Wiedergabe/Aufnahme) mitschreiben zu können.
        #
        self.application = application

        self.enabled = False

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._writer: logging.Logger | None = None

        self._last_line = ""
        self._last_written = 0.0

        #
        # Befunde der Stillstands-Wache, die noch geschrieben werden
        # müssen: (Dauer, was gerade lief). Geschrieben wird im
        # Haupttakt, damit alle Dateizugriffe in einem Thread bleiben.
        #
        self._stillstaende: list[tuple[float, float, str]] = []
        self._stillstand_sperre = threading.Lock()
        self._stillstand_thread: threading.Thread | None = None
        self._stillstand_laengster = 0.0

        #
        # Was zuletzt gefunden wurde - fuer die Anzeige in den
        # Einstellungen, unabhaengig von der Aufzeichnung.
        #
        self._stillstand_verlauf: list[dict] = []

        #
        # Die Wache hat ein EIGENES Stopp-Ereignis, und sie laeuft von
        # Anfang an - auch ohne eingeschaltete Aufzeichnung.
        #
        # Der Grund steht in der Geschichte dieses Fehlers: Er tritt
        # selten auf, und wer ihn erlebt, hat die Aufzeichnung meist
        # nicht vorher eingeschaltet. Nach mehreren Stunden Suche kam
        # vom Geraet "er ist nicht aufgetaucht" - eine Falle, die man
        # vorher scharfstellen muss, faengt aber gerade den Fehler
        # nicht, den man nicht erwartet.
        #
        # Kosten: fuenfmal in der Sekunde aufwachen und eine Zahl
        # vergleichen. Das ist weniger, als die Oberflaeche fuer einen
        # einzigen Statusabruf braucht.
        #
        self._wache_stop = threading.Event()

        self._stillstand_thread = threading.Thread(
            target=self._stillstand_wachen, daemon=True
        )
        self._stillstand_thread.start()

        #
        # Fuer das Urteil ueber das Netz: wie viele Pings hintereinander
        # gefehlt haben, seit wann, und ob daraus schon ein Befund
        # geworden ist.
        #
        self._ping_fehl = 0
        self._weg_seit = 0.0
        self._weg_gemeldet = False

        #
        # Was beim BEGINN eines Ausfalls gemessen wurde - gebraucht
        # fuer den Vergleich am Ende (siehe _vergleich).
        #
        self._befund_start: dict = {}

        #
        # Der Beacon-Zaehler der Funkschnittstelle beim letzten Mal -
        # interessant ist nicht sein Wert, sondern sein Anstieg.
        #
        self._beacons = None

        #
        # Welches Signal den Prozess beendet hat - gesetzt vom
        # Handler, geschrieben in die Schlusszeile.
        #
        self._signal = None

        #
        # Wann zuletzt nach den Nebendiensten gesehen wurde, und was
        # dabei herauskam. Gemeldet wird nur, wenn es sich aendert -
        # sonst stuende dieselbe Zeile jede Minute da.
        #
        self._dienste_geprueft = 0.0
        self._dienste_stand = ""


    # ------------------------------------------------------------
    # Start/Stopp
    # ------------------------------------------------------------

    def start(self) -> None:
        """
        Startet die Aufzeichnung. Mehrfaches Starten ist wirkungslos.
        """

        if self.enabled:
            return

        self.enabled = True
        self._stop.clear()

        self._signale_abfangen()

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        self.logger.info("Diagnose-Aufzeichnung gestartet: %s", LOG_FILE)

    def _signale_abfangen(self) -> None:
        """
        Merken, WELCHES Signal XRack beendet - und es dann weiterreichen.

        Ein sauberes Herunterfahren sieht im Protokoll immer gleich aus,
        ganz gleich, wer es ausgelöst hat. Das Signal unterscheidet die
        Fälle, die dahinterstecken können:

          SIGTERM  systemd - "systemctl stop/restart", ein Update, oder
                   etwas anderes, das den Dienst anfasst.
          SIGINT   jemand sitzt an der Konsole und hat Strg-C gedrückt.
          SIGHUP   die Sitzung, aus der XRack gestartet wurde, ist weg.

        Weitergereicht wird an den vorherigen Handler - uvicorn hat
        seinen bereits gesetzt, und der beendet den Dienst ordentlich.
        Diese Stelle darf nur mitschreiben, nichts übernehmen.
        """

        for nummer in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):

            try:
                vorher = signal.getsignal(nummer)
            except (ValueError, OSError):
                continue

            def merken(sig, rahmen, vorher=vorher):

                self._signal = sig

                if callable(vorher):
                    vorher(sig, rahmen)

                elif vorher == signal.SIG_DFL:
                    #
                    # Vorgabe wiederherstellen und noch einmal
                    # schicken: Sonst haette dieses Mitschreiben das
                    # Signal verschluckt.
                    #
                    signal.signal(sig, signal.SIG_DFL)
                    os.kill(os.getpid(), sig)

            try:
                signal.signal(nummer, merken)
            except (ValueError, OSError):
                #
                # Signale lassen sich nur im Hauptfaden setzen. Wo das
                # nicht geht, fehlt eben diese eine Angabe - die
                # Aufzeichnung laeuft trotzdem.
                #
                continue

    def stop(self) -> None:
        """
        Beendet die Aufzeichnung. Die Datei bleibt erhalten, damit man
        sie danach noch herunterladen kann.
        """

        if not self.enabled:
            return

        self.enabled = False
        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

        self._close_writer()

        self.logger.info("Diagnose-Aufzeichnung beendet.")

    # ------------------------------------------------------------
    # Datei
    # ------------------------------------------------------------

    def _open_writer(self) -> logging.Logger:
        """
        Eigener Logger mit eigener Datei - bewusst getrennt vom
        normalen XRack-Log, das nach journalctl geht. So bleibt die
        Aufzeichnung am Stück lesbar und lässt sich herunterladen.
        """

        if self._writer is not None:
            return self._writer

        LOG_DIR.mkdir(exist_ok=True)

        writer = logging.getLogger("XRack.diagnose")
        writer.propagate = False
        writer.setLevel(logging.INFO)

        for handler in list(writer.handlers):
            writer.removeHandler(handler)
            handler.close()

        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

        writer.addHandler(handler)

        self._writer = writer

        return writer

    def _close_writer(self) -> None:

        if self._writer is None:
            return

        for handler in list(self._writer.handlers):
            self._writer.removeHandler(handler)
            handler.close()

        self._writer = None

    def get_status(self) -> dict:
        """Zustand und Dateigröße fürs Einstellungen-Modal."""

        size = LOG_FILE.stat().st_size if LOG_FILE.is_file() else 0

        with self._stillstand_sperre:
            verlauf = list(self._stillstand_verlauf)
            laengster = self._stillstand_laengster

        return {
            "enabled": self.enabled,
            "size": size,
            "path": str(LOG_FILE),
            #
            # Die Stillstände stehen hier unabhängig davon, ob die
            # Aufzeichnung läuft - die Wache läuft immer (siehe
            # __init__). Genau darum geht es: Wer den Fehler erlebt,
            # hatte die Aufzeichnung meist nicht vorher eingeschaltet.
            #
            "stillstaende": verlauf[::-1],
            "stillstand_laengster": round(laengster, 1),
        }

    # ------------------------------------------------------------
    # Messungen
    # ------------------------------------------------------------

    def _default_route(self) -> tuple[str, str]:
        """Liefert (Gateway, Schnittstelle) der Standardroute."""

        try:

            result = subprocess.run(
                ["ip", "route"],
                capture_output=True,
                text=True,
                timeout=2,
            )

            for line in result.stdout.splitlines():

                if not line.startswith("default"):
                    continue

                parts = line.split()

                gateway = parts[parts.index("via") + 1] if "via" in parts else ""
                interface = parts[parts.index("dev") + 1] if "dev" in parts else ""

                return gateway, interface

        except (subprocess.SubprocessError, OSError, ValueError, IndexError):
            pass

        return "", ""

    def _ping(self, host: str) -> bool:

        if not host:
            return False

        try:

            result = subprocess.run(
                ["ping", "-c", "1", "-W", "1", host],
                capture_output=True,
                timeout=3,
            )

            return result.returncode == 0

        except (subprocess.SubprocessError, OSError):
            return False

    def _ping_grund(self, host: str) -> str:
        """
        Was der Ping SELBST sagt - in seinen eigenen Worten.

        Der Unterschied ist der halbe Befund: "Destination Host
        Unreachable" heisst, dass die Adressauflösung scheitert (ARP -
        das Gegenüber antwortet nicht auf die Frage nach seiner
        MAC-Adresse). Gar keine Ausgabe heisst, dass das Paket
        hinausging und nichts zurückkam. Das eine ist ein Problem der
        Nachbarschaft, das andere eines der Strecke dahinter.

        Der Rückgabewert ist absichtlich der Rohtext: Was ping meldet,
        soll unverändert im Protokoll stehen und nicht durch eine
        Deutung ersetzt werden, die sich später als falsch erweist.
        """

        if not host:
            return "?"

        try:

            lauf = subprocess.run(
                ["ping", "-c", "1", "-W", "1", host],
                capture_output=True,
                text=True,
                timeout=3,
            )

        except (subprocess.SubprocessError, OSError) as fehler:
            return f"ping-fehler:{fehler}"

        for zeile in (lauf.stdout + lauf.stderr).splitlines():

            text = zeile.strip()

            if "Unreachable" in text or "unreachable" in text:
                return text

        return "keine-antwort"

    def _nachbar(self, gateway: str) -> str:
        """
        Was der Rechner über seinen Nachbarn weiss (ARP/NDP).

        FAILED oder INCOMPLETE heisst: Die MAC-Adresse des Gateways ist
        nicht zu ermitteln - dann liegt es nicht an der Strecke
        dahinter, sondern an der Verbindung zum Nachbarn selbst.
        REACHABLE bei gleichzeitig verlorenen Pings heisst das
        Gegenteil: Der Nachbar ist bekannt und antwortet nur nicht.
        """

        if not gateway:
            return "?"

        try:

            lauf = subprocess.run(
                ["ip", "neigh", "show", gateway],
                capture_output=True,
                text=True,
                timeout=2,
            )

        except (subprocess.SubprocessError, OSError):
            return "?"

        zeile = lauf.stdout.strip()

        if not zeile:
            return "unbekannt"

        #
        # Letztes Wort ist der Zustand (REACHABLE, STALE, FAILED, ...).
        #
        return zeile.split()[-1]

    def _gegenstelle(self, interface: str) -> str:
        """
        An WELCHEM Zugangspunkt haengt die Karte gerade (BSSID) und auf
        welcher Frequenz?

        Der Grund: In einem Netz mit mehreren Zugangspunkten oder einem
        Repeater wechselt die Karte von selbst. Der Wechsel dauert
        Sekunden, und danach muss die Gegenseite die Station erst
        wieder lernen. Von aussen sieht das aus wie ein Netzausfall bei
        bestem Empfang - genau das Bild, das sonst niemand erklaeren
        kann. Steht am Anfang und am Ende eines Ausfalls eine andere
        BSSID, ist der Fall damit entschieden.
        """

        if not interface:
            return "?"

        try:

            lauf = subprocess.run(
                ["iw", "dev", interface, "link"],
                capture_output=True,
                text=True,
                timeout=2,
            )

        except (subprocess.SubprocessError, OSError, FileNotFoundError):
            return "?"

        bssid = ""
        freq = ""

        for zeile in lauf.stdout.splitlines():

            text = zeile.strip()

            if text.startswith("Connected to"):
                bssid = text.split()[2]

            elif text.startswith("freq:"):
                freq = text.split()[1]

        if not bssid:
            return "nicht-verbunden"

        return f"{bssid}@{freq}MHz" if freq else bssid

    def _zaehler(self, interface: str) -> tuple[int, int]:
        """
        Wie viele Pakete die Schnittstelle empfangen und gesendet hat.

        Interessant ist nicht der Wert, sondern der Zuwachs waehrend
        eines Ausfalls: Steigt TX und RX nicht, geht etwas hinaus und
        nichts kommt zurueck - die Karte sendet also, niemand
        antwortet.
        """

        werte = []

        for name in ("rx_packets", "tx_packets"):

            try:
                werte.append(
                    int((NET_SYS / interface / "statistics" / name)
                        .read_text().strip())
                )
            except (OSError, ValueError):
                werte.append(-1)

        return werte[0], werte[1]

    def _konsole(self) -> str:
        """
        Ist wenigstens das Mischpult noch zu erreichen?

        Die entscheidende Trennfrage bei einem Ausfall: Das Pult haengt
        im selben Netz. Antwortet es, waehrend das Gateway schweigt,
        dann ist die eigene Funkverbindung in Ordnung und das Problem
        liegt hinter dem Zugangspunkt. Antwortet es auch nicht, ist es
        die eigene Verbindung.

        Gefragt wird nur die bereits bekannte Adresse - kein Suchlauf,
        der mitten im Ausfall ohnehin nichts faende.
        """

        try:
            adresse = self.application.console_control._discovered
        except Exception:
            return "?"

        if not adresse:
            return "unbekannt"

        return f"{adresse}:{'erreichbar' if self._ping(adresse) else 'WEG'}"

    def _befund(self, gateway: str, interface: str) -> str:
        """
        Die teuren Fragen - gestellt am Anfang und am Ende eines
        Ausfalls, nicht im Sekundentakt.

        Sie stehen hier zusammen, weil erst die KOMBINATION etwas sagt:
        Adresse da, Nachbar REACHABLE, Pult erreichbar, TX steigt, RX
        nicht - das ist ein anderes Bild als Adresse weg oder Nachbar
        FAILED, und beide sehen in der Sekundenzeile gleich aus.
        """

        rx, tx = self._zaehler(interface)

        return (
            f"adresse={self._adresse(interface)} "
            f"ps={self._stromsparen(interface)} "
            f"nachbar={self._nachbar(gateway)} "
            f"gegenstelle={self._gegenstelle(interface)} "
            f"pult={self._konsole()} "
            f"pakete=rx{rx}/tx{tx} "
            f"ping={self._ping_grund(gateway)!r}"
        )

    def _self_check(self, port: int) -> str:
        """
        Fragt die eigene Weboberfläche ab. Antwortet sie nicht, während
        der Thread selbst noch läuft, hängt die Web-Schicht - das
        unterscheidet einen App-Fehler von einem Netzproblem.
        """

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        for url in (
            f"https://127.0.0.1:{port}/api/status",
            f"http://127.0.0.1:{port}/api/status",
        ):
            try:
                with urllib.request.urlopen(
                    url, timeout=REQUEST_TIMEOUT, context=context
                ) as response:
                    if response.status == 200:
                        return "ok"
            except Exception:
                continue

        return "KEINE-ANTWORT"

    def _temperature(self) -> str:

        try:

            path = Path("/sys/class/thermal/thermal_zone0/temp")

            if path.is_file():
                return f"{int(path.read_text().strip()) / 1000:.0f}C"

        except (OSError, ValueError):
            pass

        return "?"

    def _load(self) -> str:

        try:
            with open("/proc/loadavg", "r", encoding="utf-8") as file:
                return file.read().split()[0]
        except (OSError, IndexError):
            return "?"

    def _prozess_laufzeit(self) -> float:
        """Wie lange DIESER Prozess schon laeuft, in Sekunden."""

        try:
            return max(0.0, time.time() - psutil.Process().create_time())
        except Exception:
            return -1.0

    def _system_laufzeit(self) -> float:
        """Wie lange das SYSTEM schon laeuft, in Sekunden."""

        try:
            with open("/proc/uptime", "r", encoding="utf-8") as datei:
                return float(datei.read().split()[0])
        except (OSError, ValueError, IndexError):
            return -1.0

    @staticmethod
    def _dauer(sekunden: float) -> str:
        """4h12m, 3m20s, 45s - kurz genug fuer eine Logzeile."""

        if sekunden < 0:
            return "?"

        sekunden = int(sekunden)

        if sekunden < 60:
            return f"{sekunden}s"

        if sekunden < 3600:
            return f"{sekunden // 60}m{sekunden % 60:02d}s"

        return f"{sekunden // 3600}h{(sekunden % 3600) // 60:02d}m"

    def _vorherige_lief_weiter(self) -> bool:
        """
        Endete die vorhandene Aufzeichnung OHNE Abschlusszeile?

        Dann wurde der Prozess nicht ordentlich beendet, sondern war
        einfach weg. Genau das ist im Nachhinein sonst nicht mehr zu
        sehen - die neue Aufzeichnung haengt ihre Startzeile einfach
        darunter, und der Bruch dazwischen fiel niemandem auf.
        """

        if not LOG_FILE.is_file():
            return False

        try:

            with open(LOG_FILE, "rb") as datei:

                #
                # Nur das Ende lesen. Die Datei darf 4 MB gross sein.
                #
                datei.seek(0, 2)
                datei.seek(max(0, datei.tell() - 4096))

                zeilen = [
                    zeile for zeile in datei.read().decode(
                        "utf-8", "replace"
                    ).splitlines() if zeile.strip()
                ]

        except OSError:
            return False

        if not zeilen:
            return False

        return "Aufzeichnung beendet" not in zeilen[-1]

    def _funk(self, interface: str) -> str:
        """
        Verbindungsguete, Pegel und verpasste Beacons der
        Funkschnittstelle.

        Gelesen aus /proc/net/wireless - kein Unterprozess, keine
        Rechte, kein Netz. Der Beacon-Zaehler ist der eigentliche
        Grund: Springt er, schlaeft die Karte oder verliert den
        Anschluss.
        """

        if not interface:
            return ""

        if not (NET_SYS / interface / "wireless").exists():
            return ""

        try:

            with open(WIRELESS_PROC, "r", encoding="utf-8") as datei:
                zeilen = datei.read().splitlines()

        except OSError:
            return ""

        for zeile in zeilen:

            if not zeile.strip().startswith(f"{interface}:"):
                continue

            teile = zeile.replace(".", " ").split()

            #
            # Aufbau: name status link level noise nwid crypt frag
            # retry misc beacon
            #
            if len(teile) < 11:
                return ""

            try:
                guete = int(teile[2])
                pegel = int(teile[3])
                beacons = int(teile[10])
            except ValueError:
                return ""

            zuwachs = ""

            if self._beacons is not None and beacons >= self._beacons:
                zuwachs = f"(+{beacons - self._beacons})"

            self._beacons = beacons

            return f" wlan={guete}/{pegel}dBm bcn={beacons}{zuwachs}"

        return ""

    def _dienste_pruefen(self) -> str:
        """
        Scheitert einer der XRack-Nebendienste im Kreis?

        Ein Dienst mit `Restart=always` und ohne Startgrenze versucht
        es für immer. Das ist gewollt (der Zugangspunkt soll
        wiederkommen, wenn das Funkgerät erst spät bereit ist) - aber
        wenn er NIE hochkommt, hämmert er im Fünfsekundentakt gegen
        dieselbe Wand, und jeder Versuch fasst dabei das Netz an.

        Von innen ist davon nichts zu sehen: XRack merkt nur, dass
        gelegentlich Pakete fehlen. Deshalb steht es jetzt hier.
        """

        auffaellig = []

        for dienst in NEBENDIENSTE:

            try:

                lauf = subprocess.run(
                    [
                        "systemctl", "show", dienst,
                        "-p", "NRestarts", "-p", "ActiveState",
                        "-p", "Result", "--value",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )

            except (subprocess.SubprocessError, OSError, FileNotFoundError):
                continue

            zeilen = [z.strip() for z in lauf.stdout.splitlines()]

            if len(zeilen) < 3:
                continue

            zustand, ergebnis, neustarts = zeilen[0], zeilen[1], zeilen[2]

            try:
                zahl = int(neustarts)
            except ValueError:
                zahl = 0

            #
            # Nur melden, was wirklich nicht laeuft: Der letzte Lauf
            # endete schlecht, oder der Dienst steht als gescheitert
            # da. Die Zahl der Neustarts sagt dann, wie lange das
            # schon so geht - sie loest die Meldung aber nicht aus.
            #
            if ergebnis in ERGEBNIS_OK and zustand != "failed":
                continue

            auffaellig.append(
                f"{dienst}={zustand}/{ergebnis} neustarts={zahl}"
            )

        return " ".join(auffaellig)

    def _signalname(self) -> str:
        """Der Name des Signals, das XRack beendet hat."""

        try:
            return signal.Signals(self._signal).name
        except (ValueError, TypeError):
            return str(self._signal)

    def _dienst_auskunft(self) -> str:
        """
        Was systemd über den eigenen Dienst sagt.

        Zwei Angaben, die einen ungeklärten Neustart auseinanderhalten:

          `neustarts` ist systemds Zähler der AUTOMATISCHEN Neustarts
          (Restart=on-failure). Er steigt, wenn der Dienst abgestürzt
          ist und systemd ihn wiederbelebt hat - und er steigt NICHT
          bei einem ausdrücklichen "systemctl restart". Damit trennt
          diese eine Zahl "XRack ist gefallen" von "jemand hat XRack
          neu gestartet", und das war bei den bisherigen Vorfällen
          genau die offene Frage.

          `seit` ist der Zeitpunkt, an dem der Dienst zuletzt aktiv
          wurde - damit lässt sich der Vorfall im Journal wiederfinden
          (`journalctl -u xrack.service --since ...`).

        Gefragt wird nur lesend; `systemctl show` braucht keine Rechte.
        """

        werte = []

        for eigenschaft, name in (
            ("NRestarts", "neustarts"),
            ("ActiveEnterTimestamp", "seit"),
        ):

            try:

                lauf = subprocess.run(
                    [
                        "systemctl", "show", "xrack.service",
                        "-p", eigenschaft, "--value",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )

                wert = lauf.stdout.strip()

            except (subprocess.SubprocessError, OSError, FileNotFoundError):
                wert = ""

            if wert:
                werte.append(f"{name}={wert.replace(' ', '_')}")

        return " ".join(werte)

    def _stromsparen(self, interface: str) -> str:
        """
        Steht die Stromsparfunktion der Funkschnittstelle auf "on"?

        Der Hauptverdaechtige bei Aussetzern im Leerlauf: Die Karte
        schlaeft ein, und die ersten Pakete danach fallen weg. Der
        Aufruf ist lokal (netlink), er braucht kein Netz.
        """

        if not interface:
            return "?"

        try:

            lauf = subprocess.run(
                ["iw", "dev", interface, "get", "power_save"],
                capture_output=True,
                text=True,
                timeout=2,
            )

            if lauf.returncode != 0:
                return "?"

            return "on" if "on" in lauf.stdout.lower() else "off"

        except (subprocess.SubprocessError, OSError):
            return "?"

    def _adresse(self, interface: str) -> str:
        """
        Hat die Schnittstelle noch eine IPv4-Adresse?

        Wird nur beim BEGINN eines Ausfalls gefragt, nicht im
        Sekundentakt. Sie trennt zwei ganz verschiedene Fehler: Ist die
        Adresse weg, ist es die Verbindung oder DHCP - ist sie da,
        gehen nur Pakete verloren.
        """

        if not interface:
            return "?"

        try:

            lauf = subprocess.run(
                ["ip", "-4", "-o", "addr", "show", "dev", interface],
                capture_output=True,
                text=True,
                timeout=2,
            )

            for teil in lauf.stdout.split():
                if "/" in teil and teil[0].isdigit():
                    return teil

            return "KEINE"

        except (subprocess.SubprocessError, OSError):
            return "?"

    def _activity(self) -> str:
        """
        XRacks eigener Zustand - der Grund, warum diese Aufzeichnung
        von innen läuft und nicht als externes Skript.
        """

        parts = []

        try:

            if self.application.recorder.recording:
                parts.append("aufnahme")

            if self.application.player.playing:
                parts.append(
                    f"wiedergabe:{self.application.player.current_filename}"
                )

            if self.application.music_player.playing:

                #
                # Ueben laeuft ueber denselben Spieler wie Musik -
                # im Protokoll stand deshalb "musik", auch wenn gerade
                # zu einem Uebungsmix gespielt wurde. Fuer die Zuordnung
                # eines Aussetzers ist das der Unterschied zwischen
                # "lief nebenbei" und "genau dabei".
                #
                if getattr(self.application, "practice_active", False):
                    parts.append(
                        f"ueben:{self.application.music_player.current_track}"
                    )
                else:
                    parts.append("musik")

            if self.application.bluetooth_player.streaming:
                parts.append("bluetooth")

        except Exception:
            #
            # Diagnose darf niemals das überwachte Programm stören.
            #
            return "?"

        return ",".join(parts) if parts else "leerlauf"

    # ------------------------------------------------------------
    # Schleife
    # ------------------------------------------------------------

    def _kopfzeile(self, writer: logging.Logger) -> None:
        """
        Die Kopfzeile jeder Aufzeichnung - und das Urteil darüber,
        ob XRack gerade neu gestartet wurde.

        Steht als eigene Methode, weil sie der Teil ist, der einen
        ungeklärten Neustart erklären soll: Sie gehört geprüft,
        und zwar ohne dass dafür eine ganze Messschleife laufen
        muss.
        """

        #
        # Erst nachsehen, DANN schreiben: Ob die vorherige Aufzeichnung
        # abbrach, steht am Ende der vorhandenen Datei - sobald die
        # neue Startzeile darunter haengt, ist es nicht mehr zu sehen.
        #
        abgebrochen = self._vorherige_lief_weiter()

        gateway, interface = self._default_route()

        prozess = self._prozess_laufzeit()
        system = self._system_laufzeit()

        writer.info(
            "=== Aufzeichnung gestartet | host=%s | route=%s via %s | "
            "prozess=%s system=%s ps=%s | pid=%d ppid=%d %s ===",
            socket.gethostname(),
            interface or "?",
            gateway or "?",
            self._dauer(prozess),
            self._dauer(system),
            self._stromsparen(interface),
            os.getpid(),
            os.getppid(),
            self._dienst_auskunft(),
        )

        #
        # Der Befund, der am laengsten unentdeckt bleibt: XRack wurde
        # ersetzt, und niemand hat es gemerkt. Zu sehen war das bisher
        # nur daran, dass eine zweite Startzeile mitten in der Datei
        # steht - das liest man nicht, wenn man es nicht sucht.
        #
        # Die Systemlaufzeit daneben trennt die zwei Faelle, die ganz
        # verschiedene Ursachen haben: Ist auch das SYSTEM jung, war der
        # ganze Rechner weg (Strom, Reset). Ist nur der Prozess jung,
        # war es der Dienst allein (Absturz, systemctl restart, Update).
        #
        if 0 <= prozess < JUNG_S:

            writer.warning(
                "NEUSTART: XRack laeuft erst seit %s (System seit %s) - %s",
                self._dauer(prozess),
                self._dauer(system),
                "die vorherige Aufzeichnung brach ohne Abschluss ab, der "
                "Prozess wurde also nicht ordentlich beendet."
                if abgebrochen
                else "die vorherige Aufzeichnung wurde ordentlich beendet.",
            )

        #
        # Gleich beim Start nachsehen: Ein Nebendienst, der im Kreis
        # scheitert, tut das meist schon seit Stunden.
        #
        dienste = self._dienste_pruefen()

        #
        # Nur den Stand merken, nicht die Zeit: Die Uhr gehoert der
        # Messschleife, und sie liest sie ohnehin einmal je Durchlauf.
        # Ein zweiter Griff danach waere nicht falsch, aber er macht
        # den Ablauf schwerer nachzustellen - und ein Waechter, der
        # sich nicht nachstellen laesst, ist kein Waechter.
        #
        self._dienste_stand = dienste

        if dienste:
            writer.warning("DIENST SCHEITERT: %s", dienste)

        if abgebrochen and not (0 <= prozess < JUNG_S):

            writer.warning(
                "ABBRUCH: Die vorherige Aufzeichnung endete ohne "
                "Abschlusszeile, der Prozess laeuft aber schon %s - die "
                "Aufzeichnung wurde also mitten im Betrieb neu gestartet.",
                self._dauer(prozess),
            )


    def _stillstand_wachen(self) -> None:
        """
        Schlafen und messen, wie spät man aufwacht.

        Mehr ist es nicht - und mehr darf es auch nicht sein: Was diese
        Wache selbst an Arbeit täte, verfälschte ihre Messung. Sie
        schreibt deshalb nichts in die Datei, sondern legt ihre Befunde
        ab; der Haupttakt nimmt sie mit.

        Die Nachfrage bei der Gerätewache steht bewusst UNMITTELBAR nach
        dem Aufwachen: Ein Öffnen, das zwei Sekunden gedauert hat, ist
        eine Sekunde später schon nicht mehr "laufend", und dann wäre
        der Zusammenhang verloren.
        """

        while not self._wache_stop.is_set():

            vorher = time.monotonic()
            bloecke_vorher = GERAETEWACHE.bloecke

            self._wache_stop.wait(STILLSTAND_TAKT)

            verspaetung = time.monotonic() - vorher - STILLSTAND_TAKT

            if verspaetung < STILLSTAND_SCHWELLE:
                continue

            self._stillstand_merken(
                verspaetung, GERAETEWACHE.bloecke - bloecke_vorher
            )

    def _stillstand_merken(
        self, verspaetung: float, bloecke: int = 0
    ) -> None:
        """Einen Befund ablegen, samt dem, was gerade lief."""

        was = GERAETEWACHE.laufend()

        if was is None:
            #
            # Schon vorbei? Dann war es vielleicht das Öffnen, das
            # gerade fertig geworden ist - aber nur, wenn es zeitlich
            # überhaupt passt.
            #
            was = GERAETEWACHE.letzte(nicht_aelter_als=verspaetung + 1.0)

        befund = f"{was or 'nichts am Audiogerät'}{self._tonurteil(verspaetung, bloecke)}"

        #
        # Die Uhrzeit gehört zum Befund, nicht zur Zeile: Geschrieben
        # wird er erst im nächsten Takt der Aufzeichnung, und wenn die
        # gerade aus ist, womöglich erst Stunden später.
        #
        zeit = time.time()

        with self._stillstand_sperre:

            if verspaetung > self._stillstand_laengster:
                self._stillstand_laengster = verspaetung

            if len(self._stillstaende) < STILLSTAND_MERKE_MAX:
                self._stillstaende.append((zeit, verspaetung, befund))

            #
            # Der Verlauf ist unabhängig von der Aufzeichnung: Er steht
            # in den Einstellungen, damit man nach einem Vorfall
            # nachsehen kann, ohne vorher etwas eingeschaltet zu haben.
            #
            self._stillstand_verlauf.append({
                "zeit": zeit,
                "dauer": round(verspaetung, 1),
                "befund": befund,
            })

            del self._stillstand_verlauf[:-STILLSTAND_MERKE_MAX]

    def _tonurteil(self, verspaetung: float, bloecke: int) -> str:
        """
        Ist während des Stillstands Ton geflossen?

        Das ist die Frage, die den Verdacht entscheidet. Vom Gerät kam:
        "Läuft eine Wiedergabe, wenn der Fehler auftritt, läuft sie auch
        unbeirrt weiter." Wäre der GIL blockiert, könnte der
        Wiedergabe-Thread keinen Block mehr schreiben - der ALSA-Puffer
        wäre nach knapp hundert Millisekunden leer, und man hörte es.

        Deshalb zählt die Gerätewache jeden geschriebenen Block. Was
        hier steht, ist gemessen und nicht geschlossen:

          "Ton lief weiter"  -> Python lief. Dann ist es KEIN
                                GIL-Stillstand, und die Ursache liegt
                                woanders (Webserver, Sperren, System).
          "Ton stand still"  -> Auch die Wiedergabe kam nicht dran -
                                der ganze Prozess stand.
          nichts             -> Es lief gar keine Wiedergabe; die Frage
                                ist dann gegenstandslos.
        """

        tonzeit = GERAETEWACHE.tonzeit(bloecke)

        if tonzeit is None or (bloecke == 0 and verspaetung < 1.0):
            #
            # Ohne bekannte Blockdauer, oder ganz ohne Wiedergabe: Dazu
            # laesst sich nichts sagen. Lieber nichts als ein Urteil
            # ueber eine Wiedergabe, die es nicht gab.
            #
            return ""

        anteil = tonzeit / verspaetung if verspaetung > 0 else 0.0

        if anteil >= 0.5:
            return (
                f" | Ton lief weiter ({bloecke} Blöcke = {tonzeit:.1f} s) "
                f"- Python lief also, es ist KEIN GIL-Stillstand"
            )

        return (
            f" | Ton stand ebenfalls ({bloecke} Blöcke = {tonzeit:.1f} s "
            f"von {verspaetung:.1f} s) - der ganze Prozess stand"
        )

    def _stillstand_melden(self, writer: logging.Logger) -> None:
        """Die abgelegten Befunde schreiben."""

        with self._stillstand_sperre:

            befunde = self._stillstaende
            self._stillstaende = []

        for zeit, verspaetung, was in befunde:

            writer.warning(
                "STILLSTAND um %s: %.1f s lang lief kein Python - der "
                "Webserver war in dieser Zeit nicht erreichbar. Dabei "
                "lief: %s",
                datetime.fromtimestamp(zeit).strftime("%H:%M:%S"),
                verspaetung,
                was,
            )

    def _loop(self) -> None:

        try:
            writer = self._open_writer()
        except OSError as exc:
            self.logger.warning(
                "Diagnose-Datei konnte nicht angelegt werden: %s", exc
            )
            self.enabled = False
            return

        self._kopfzeile(writer)

        port = 8080

        try:
            port = self.application.config.data.server.port
        except Exception:
            pass

        last_tick = time.monotonic()

        while not self._stop.is_set():

            now = time.monotonic()
            elapsed = now - last_tick

            #
            # Lücke = der Prozess stand. Das ist genau der Befund, den
            # ein Wächter im Inneren sonst nicht liefern könnte.
            #
            if elapsed > GAP_THRESHOLD:
                writer.warning(
                    "LÜCKE: %.1f s ohne Messung - Prozess oder System stand.",
                    elapsed,
                )
                self._last_line = ""

            last_tick = now

            self._stillstand_melden(writer)

            self._dienste_melden(writer, now)

            try:
                self._sample(writer, port)
            except Exception as exc:
                #
                # Ein Fehler in der Diagnose darf die Diagnose nicht
                # beenden - sonst fehlt gerade dann etwas, wenn es
                # interessant wird.
                #
                writer.warning("Messung fehlgeschlagen: %s", exc)

            self._stop.wait(INTERVAL)

        #
        # Die Befunde, die noch warten, gehören noch in die Datei - sonst
        # fehlt gerade der letzte, und der ist oft der interessante.
        #
        self._stillstand_melden(writer)

        writer.info(
            "=== Aufzeichnung beendet%s%s%s ===",
            f" | signal={self._signalname()}" if self._signal else "",
            (
                f" | längster Stillstand={self._stillstand_laengster:.1f}s"
                if self._stillstand_laengster else ""
            ),
            (
                f" | längste Gerätearbeit: {GERAETEWACHE.laengste()}"
                if GERAETEWACHE.laengste() else ""
            ),
        )

    def _netz(self, writer: logging.Logger, gateway: str,
              interface: str) -> tuple[str, bool]:
        """
        Das Urteil ueber das Netz - und ein Wort dazu, ob es auffaellig
        ist.

        Ein einzelner verlorener Ping ist kein Ausfall. Erst ab
        PING_VERSUCHE Fehlschlaegen in Folge steht hier ein Befund;
        davor ein Fragezeichen mit der Zahl der Versuche. Kommt das
        Netz zurueck, schreibt diese Stelle die Zeile, die den Fall
        abschliesst - mit der Dauer, die sonst niemand zaehlen kann.
        """

        if not gateway:
            #
            # Ohne Standardroute gibt es nichts zu pingen. Das ist kein
            # Funkloch, sondern ein fehlendes Profil - und hiess bisher
            # trotzdem "WEG".
            #
            return "KEIN-GATEWAY", True

        if self._ping(gateway):

            if self._weg_gemeldet:

                writer.warning(
                    "netz=WIEDER-DA nach %.1f s (%d Versuche)%s%s",
                    max(0.0, time.monotonic() - self._weg_seit),
                    self._ping_fehl,
                    self._funk(interface),
                    self._vergleich(interface),
                )

            self._ping_fehl = 0
            self._weg_gemeldet = False

            return "ok", False

        self._ping_fehl += 1

        if self._ping_fehl < PING_VERSUCHE:
            return f"?({self._ping_fehl})", True

        if not self._weg_gemeldet:

            #
            # Der Beginn des Ausfalls - hier lohnen die zwei teureren
            # Fragen, die im Sekundentakt zu viel waeren.
            #
            self._weg_gemeldet = True
            self._weg_seit = time.monotonic() - self._ping_fehl

            #
            # Der Anfang des Ausfalls - hier lohnen die teureren
            # Fragen, die im Sekundentakt zu viel waeren. Gemerkt wird
            # das Ergebnis, damit es sich am Ende vergleichen laesst:
            # Ein Wechsel des Zugangspunkts sieht man nur so.
            #
            self._befund_start = {
                "gegenstelle": self._gegenstelle(interface),
                "zaehler": self._zaehler(interface),
            }

            writer.warning(
                "netz=AUSFALL beginnt: %d Pings in Folge verloren, %s",
                self._ping_fehl,
                self._befund(gateway, interface),
            )

        return f"WEG({self._ping_fehl})", True

    def _vergleich(self, interface: str) -> str:
        """
        Was sich waehrend des Ausfalls veraendert hat.

        Zwei Fragen, die sich nur mit dem Anfang beantworten lassen:

          1. Haengt die Karte noch am selben Zugangspunkt? Ein anderer
             heisst, dass sie gewechselt hat - und dann ist der
             "Netzausfall" ein Wechsel gewesen, kein Ausfall.
          2. Sind waehrenddessen Pakete hinausgegangen und keine
             zurueckgekommen? Dann hat die Karte gesendet und niemand
             geantwortet - die eigene Seite war also nicht stumm.
        """

        if not self._befund_start:
            return ""

        teile = []

        jetzt = self._gegenstelle(interface)

        vorher = self._befund_start.get("gegenstelle", "?")

        if jetzt != vorher:
            teile.append(
                f" GEGENSTELLE-GEWECHSELT: {vorher} -> {jetzt} "
                f"(der Ausfall war ein Wechsel des Zugangspunkts)"
            )
        else:
            teile.append(f" gegenstelle=unveraendert:{jetzt}")

        rx_alt, tx_alt = self._befund_start.get("zaehler", (-1, -1))

        rx_neu, tx_neu = self._zaehler(interface)

        if min(rx_alt, tx_alt, rx_neu, tx_neu) >= 0:
            teile.append(
                f" pakete=+rx{rx_neu - rx_alt}/+tx{tx_neu - tx_alt}"
            )

        self._befund_start = {}

        return "".join(teile)

    def _dienste_melden(self, writer: logging.Logger, jetzt: float) -> None:
        """
        Die Nebendienste im Auge behalten - höchstens einmal je
        Minute, und nur, wenn sich etwas ändert.

        Ein Dienst, der im Kreis scheitert, tut das stundenlang. Die
        Meldung soll einmal dastehen und nicht tausendmal; wird sie
        zur Meldung "wieder in Ordnung", steht auch das da.
        """

        if jetzt - self._dienste_geprueft < DIENSTE_INTERVALL:
            return

        self._dienste_geprueft = jetzt

        stand = self._dienste_pruefen()

        if stand == self._dienste_stand:
            return

        self._dienste_stand = stand

        if stand:
            writer.warning("DIENST SCHEITERT: %s", stand)
        else:
            writer.info("Nebendienste wieder unauffaellig.")

    def _sample(self, writer: logging.Logger, port: int) -> None:

        gateway, interface = self._default_route()

        app = self._self_check(port)
        net, netz_auffaellig = self._netz(writer, gateway, interface)
        activity = self._activity()

        ziel = f"{interface or '?'}"

        if gateway:
            ziel += f">{gateway}"

        line = (
            f"xrack={app} netz={net} route={ziel} "
            f"last={self._load()} temp={self._temperature()} "
            f"aktiv={activity}{self._funk(interface)}"
        )

        abnormal = app != "ok" or netz_auffaellig

        #
        # Nur schreiben, wenn die Zeile etwas aussagt: bei
        # Auffälligkeiten, bei einer Änderung gegenüber der letzten
        # Zeile, oder als Lebenszeichen. Sonst stünde hier jede Sekunde
        # dasselbe.
        #
        changed = line != self._last_line
        due = (time.monotonic() - self._last_written) >= HEARTBEAT

        if not (abnormal or changed or due):
            return

        if abnormal:
            writer.warning(line)
        else:
            writer.info(line)

        self._last_line = line
        self._last_written = time.monotonic()
