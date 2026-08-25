"""
Diagnose-Aufzeichnung: schreibt im Hintergrund mit, wie es XRack und
dem Netzwerk geht - gedacht für Fehler, die nur sporadisch auftreten
und die man deshalb nicht "live" beobachten kann.

Anlass war ein Aussetzer der Netzwerkverbindung, der ausschließlich
während der Wiedergabe auftrat. Ein von Hand gestartetes Skript hätte
bei jedem Neustart neu gestartet werden müssen, in der Hoffnung, dass
der Fehler gerade dann auftritt.

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
# Solange nichts auffällt, genügt ein Lebenszeichen - sonst wäre die
# Datei voller identischer Zeilen.
#
HEARTBEAT = 30.0

REQUEST_TIMEOUT = 2.0


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

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

        self.logger.info("Diagnose-Aufzeichnung gestartet: %s", LOG_FILE)

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

        return {
            "enabled": self.enabled,
            "size": size,
            "path": str(LOG_FILE),
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

    def _loop(self) -> None:

        try:
            writer = self._open_writer()
        except OSError as exc:
            self.logger.warning(
                "Diagnose-Datei konnte nicht angelegt werden: %s", exc
            )
            self.enabled = False
            return

        gateway, interface = self._default_route()

        writer.info(
            "=== Aufzeichnung gestartet | host=%s | route=%s via %s ===",
            socket.gethostname(),
            interface or "?",
            gateway or "?",
        )

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

        writer.info("=== Aufzeichnung beendet ===")

    def _sample(self, writer: logging.Logger, port: int) -> None:

        gateway, interface = self._default_route()

        app = self._self_check(port)
        net = "ok" if self._ping(gateway) else "WEG"
        activity = self._activity()

        line = (
            f"xrack={app} netz={net} route={interface or '?'} "
            f"last={self._load()} temp={self._temperature()} "
            f"aktiv={activity}"
        )

        abnormal = app != "ok" or net != "ok"

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
