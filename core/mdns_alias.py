"""
Ein zweiter Name im Netz.

Jedes XRack meldet sich über avahi unter seinem Hostnamen, also etwa
"x18rack.local". Das ist richtig so - man will die Geräte
unterscheiden können. Für eine gespeicherte Web-App ist es aber ein
Problem: Die startet immer genau die Adresse, unter der sie gespeichert
wurde. Wer im Proberaum ein anderes XRack stehen hat, tippt auf sein
Symbol und bekommt eine Fehlerseite - ohne Adressleiste, ohne
Möglichkeit, die Adresse zu ändern.

Deshalb kann jedes Gerät zusätzlich einen GEMEINSAMEN Namen melden,
etwa "xrack.local". Die Web-App wird einmal darunter gespeichert und
landet dann in jedem Raum auf dem Gerät, das dort steht.

Gemacht wird das mit "avahi-publish -a", einem Kindprozess je Adresse:
Solange er läuft, steht der Name im Netz. Mehrere Adressen sind der
Normalfall - der Pi hängt oft gleichzeitig am Kabel und spannt einen
Access Point auf, und das Tablet erreicht ihn je nach Raum über den
einen oder den anderen Weg.

Zwei Grenzen gehören dazu:

  - Stehen zwei XRacks mit demselben Zweitnamen im selben Netz, gibt
    es einen Namenskonflikt. avahi meldet ihn, der Kindprozess endet,
    und XRack zeigt das an. Der Name gehört dann geändert.
  - Ohne "avahi-publish" (Paket avahi-utils) geht es nicht. Fehlt es,
    sagt die Oberfläche das, statt still nichts zu tun.
"""

import logging
import re
import shutil
import socket
import subprocess
import threading
import time

import psutil


#
# Ein Name aus dem mDNS-Zeichensatz: Buchstaben, Ziffern, Bindestrich,
# nicht am Rand. Umlaute und Punkte bleiben draußen - was hier
# durchkommt, muss in jeder Adresszeile funktionieren.
#
NAME_MUSTER = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

#
# Wie oft nachgesehen wird, ob sich die Adressen geändert haben oder
# ein Kindprozess weg ist. Ein Netzwechsel (Kabel raus, Access Point
# an) ist selten, und die Prüfung kostet fast nichts.
#
WACHINTERVALL = 5.0

#
# Nach einem Namenskonflikt wird nicht sofort wieder versucht: Zwei
# XRacks, die sich im Sekundentakt um denselben Namen streiten,
# fluten nur das Netz und das Protokoll. Nach einer Minute darf es
# noch einmal - vielleicht ist das andere Gerät inzwischen weg.
#
KONFLIKT_PAUSE_S = 60.0


class MdnsAlias:
    """
    Veröffentlicht einen zweiten Namen für dieses Gerät.

    Der Name wird gemerkt und bei jeder Adressänderung neu
    veröffentlicht; ohne Namen tut die Klasse nichts.
    """

    def __init__(self, logger=None):

        self.logger = logger or logging.getLogger("XRack")

        self.name = ""

        self._prozesse: list[subprocess.Popen] = []
        self._adressen: list[str] = []
        self._fehler = ""

        #
        # Frühestens dann wieder versuchen (siehe KONFLIKT_PAUSE_S).
        #
        self._pause_bis = 0.0

        self._sperre = threading.Lock()

        self._laeuft = True

        self._wache = threading.Thread(target=self._wachen, daemon=True)
        self._wache.start()

    # ----------------------------------------------------------------
    # Auskunft
    # ----------------------------------------------------------------

    @property
    def verfuegbar(self) -> bool:
        """Gibt es avahi-publish überhaupt?"""

        return shutil.which("avahi-publish") is not None

    def hostname(self) -> str:
        """Der eigene Name - unter dem meldet avahi sich schon selbst."""

        return socket.gethostname().split(".")[0]

    def status(self) -> dict:

        with self._sperre:

            return {
                "name": self.name,
                "published": bool(self._prozesse),
                "addresses": list(self._adressen),
                "error": self._fehler,
                "available": self.verfuegbar,
                "hostname": self.hostname(),
            }

    # ----------------------------------------------------------------
    # Einstellen
    # ----------------------------------------------------------------

    def pruefen(self, name: str) -> str:
        """
        Sagt, was an einem Namen nicht stimmt - oder "" bei einem
        brauchbaren.
        """

        name = (name or "").strip().lower()

        if not name:
            return ""

        if name.endswith(".local"):
            name = name[: -len(".local")]

        if not NAME_MUSTER.match(name):
            return (
                "Der Name darf nur Buchstaben, Ziffern und Bindestriche "
                "enthalten und nicht mit einem Bindestrich beginnen oder "
                "enden."
            )

        if name == self.hostname().lower():
            return (
                "Das ist schon der eigene Name des Geräts - als "
                "gemeinsamer Name taugt er nicht, weil ihn dann jedes "
                "XRack anders hätte."
            )

        return ""

    def setzen(self, name: str) -> tuple[bool, str]:
        """
        Den Zweitnamen setzen (leer = keiner) und sofort
        veröffentlichen.
        """

        name = (name or "").strip().lower()

        if name.endswith(".local"):
            name = name[: -len(".local")]

        fehler = self.pruefen(name)

        if fehler:
            return False, fehler

        if name and not self.verfuegbar:
            return False, (
                "avahi-publish fehlt - ohne das Paket 'avahi-utils' "
                "lässt sich kein zweiter Name melden."
            )

        with self._sperre:

            self.name = name
            self._fehler = ""
            self._pause_bis = 0.0

            self._stoppen()

            if name:
                self._starten()

        return True, ""

    # ----------------------------------------------------------------
    # Veröffentlichen
    # ----------------------------------------------------------------

    def adressen(self) -> list[str]:
        """
        Alle IPv4-Adressen dieses Geräts, ohne Loopback.

        Veröffentlicht wird JEDE davon: Welche das Tablet erreicht,
        hängt am Raum - über den Access Point ist es eine andere als
        über das Kabel, und beide gleichzeitig gibt es auch.
        """

        gefunden = []

        try:
            schnittstellen = psutil.net_if_addrs()
        except Exception:
            return gefunden

        for adressen in schnittstellen.values():

            for adresse in adressen:

                if adresse.family != socket.AF_INET:
                    continue

                if not adresse.address or adresse.address.startswith("127."):
                    continue

                if adresse.address not in gefunden:
                    gefunden.append(adresse.address)

        return gefunden

    def _starten(self) -> None:
        """Je Adresse einen avahi-publish - Sperre gehalten."""

        self._adressen = self.adressen()

        if not self._adressen:

            self._fehler = (
                "Das Gerät hat gerade keine Netzwerkadresse - der Name "
                "wird gemeldet, sobald es wieder im Netz ist."
            )

            return

        for adresse in self._adressen:

            try:

                prozess = subprocess.Popen(
                    [
                        "avahi-publish",
                        "-a",
                        #
                        # Kein Rückwärtseintrag: Die Adresse gehört
                        # weiterhin dem eigenen Hostnamen, und zwei
                        # Namen für dieselbe Adresse wären ein
                        # Streitfall ohne Nutzen.
                        #
                        "-R",
                        f"{self.name}.local",
                        adresse,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )

            except OSError as ausnahme:

                self._fehler = f"avahi-publish ließ sich nicht starten: {ausnahme}"
                self.logger.warning("%s", self._fehler)

                return

            self._prozesse.append(prozess)

        self.logger.info(
            "Zweiter Name im Netz: %s.local (%s)",
            self.name,
            ", ".join(self._adressen),
        )

    def _stoppen(self) -> None:
        """Alle Kindprozesse beenden - Sperre gehalten."""

        for prozess in self._prozesse:

            try:
                prozess.terminate()
                prozess.wait(timeout=2)
            except Exception:
                #
                # Reagiert er nicht, hilft nur der harte Weg. Ein
                # haengender avahi-publish wuerde den Namen sonst
                # weiter belegen.
                #
                try:
                    prozess.kill()
                except Exception:
                    pass

        self._prozesse = []
        self._adressen = []

    def stop(self) -> None:
        """Alles beenden - beim Herunterfahren."""

        self._laeuft = False

        with self._sperre:
            self._stoppen()

    # ----------------------------------------------------------------
    # Die Wache
    # ----------------------------------------------------------------

    def _wachen(self) -> None:
        """
        Hält den Namen am Leben.

        Zwei Dinge können passieren: Das Gerät bekommt eine andere
        Adresse (Kabel umgesteckt, Access Point an), oder avahi meldet
        einen Namenskonflikt und der Kindprozess endet. Beides fällt
        hier auf.
        """

        while self._laeuft:

            time.sleep(WACHINTERVALL)

            with self._sperre:

                if not self.name:
                    continue

                jetzt = time.monotonic()

                #
                # Ein beendeter Kindprozess ist kein Zufall: avahi
                # beendet ihn bei einem Namenskonflikt. Was er dabei
                # gesagt hat, gehoert in die Oberflaeche.
                #
                beendet = [p for p in self._prozesse if p.poll() is not None]

                if beendet:

                    meldung = ""

                    for prozess in beendet:

                        try:
                            gelesen = (prozess.stdout.read() or "").strip()
                        except Exception:
                            gelesen = ""

                        if gelesen:
                            meldung = gelesen
                            break

                    self._fehler = meldung or (
                        f"Der Name '{self.name}.local' konnte nicht "
                        f"gemeldet werden - steht ein zweites XRack mit "
                        f"demselben Namen im Netz?"
                    )

                    self.logger.warning(
                        "Zweiter Name '%s.local' aufgegeben: %s",
                        self.name,
                        self._fehler,
                    )

                    self._stoppen()

                    self._pause_bis = jetzt + KONFLIKT_PAUSE_S

                    continue

                #
                # Nichts laeuft: Entweder gab es gerade einen Konflikt,
                # oder das Geraet hatte keine Adresse. Beides kann
                # vorbeigehen - nach der Pause wird es noch einmal
                # versucht.
                #
                if not self._prozesse:

                    if jetzt >= self._pause_bis:
                        self._starten()

                    continue

                #
                # Laeuft es eine Runde lang, war der Anlauf gut - eine
                # alte Meldung darf dann weg.
                #
                self._fehler = ""

                #
                # Adressen gewechselt: neu veroeffentlichen. Ohne das
                # zeigte der Name nach einem Netzwechsel auf eine
                # Adresse, die es nicht mehr gibt - und das ist
                # schlimmer als gar kein Name.
                #
                if self.adressen() != self._adressen:

                    self.logger.info(
                        "Adressen haben sich geändert - '%s.local' wird "
                        "neu gemeldet.",
                        self.name,
                    )

                    self._stoppen()
                    self._starten()
