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

Gemacht wird das mit "avahi-publish -a": Solange der Kindprozess
läuft, steht der Name im Netz.

Gemeldet wird dabei GENAU EINE Adresse, obwohl der Pi meist mehrere
hat (Kabel, Heimnetz-WLAN, eigener Access Point). Der Grund steht
ausführlich bei adressen() und ist am Gerät teuer bezahlt worden:
avahi-publish kennt keine Option für eine Schnittstelle und meldet
deshalb jede Adresse überall. Ein Tablet bekam so auch Adressen, die
von seinem Netz aus nicht zu erreichen sind - und wenn der Browser
eine davon erwischte, wartete er bis zur Zeitüberschreitung.

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
from pathlib import Path

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

#
# Wo der Kernel seine Routen auflistet. Überschreibbar, damit der Test
# eine nachgestellte Tabelle unterschieben kann.
#
ROUTEN_DATEI = "/proc/net/route"

#
# Die Brücke des Access Points (install.sh legt sie als "br0" an, mit
# der festen Adresse 10.42.0.1). Ihre Adresse ist nur von dort aus zu
# erreichen - siehe die Begründung bei adressen().
#
AP_BRUECKE = "br0"

#
# Adressen, die ein Gerät sich selbst gibt, wenn es keine bekommt
# (169.254.0.0/16). Besser als nichts, aber schlechter als jede echte.
#
SELBSTVERGEBEN = "169.254."


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

    def schnittstellen(self) -> dict[str, list[str]]:
        """Alle IPv4-Adressen je Schnittstelle, ohne Loopback."""

        gefunden: dict[str, list[str]] = {}

        try:
            vorhanden = psutil.net_if_addrs()
        except Exception:
            return gefunden

        for name, adressen in vorhanden.items():

            for adresse in adressen:

                if adresse.family != socket.AF_INET:
                    continue

                if not adresse.address or adresse.address.startswith("127."):
                    continue

                gefunden.setdefault(name, []).append(adresse.address)

        return gefunden

    def standard_schnittstelle(self) -> str:
        """
        Über welche Schnittstelle es nach draußen geht.

        Aus /proc/net/route, weil das ohne Werkzeug und ohne Rechte
        geht: Die Standardroute ist die Zeile mit dem Ziel 00000000.
        """

        try:
            zeilen = Path(ROUTEN_DATEI).read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""

        for zeile in zeilen[1:]:

            felder = zeile.split()

            if len(felder) < 2:
                continue

            if felder[1] == "00000000":
                return felder[0]

        return ""

    def adressen(self) -> list[str]:
        """
        Die Adresse, unter der der Zweitname gemeldet wird - genau eine.

        Hier stand bis 3.0.0-dev19 "jede Adresse des Geräts", mit der
        Begründung: Welche das Tablet erreicht, hängt am Raum. Die
        Begründung stimmt, der Schluss daraus war falsch, und das hat
        am Gerät wehgetan.

        Der Grund liegt in avahi-publish: Es kennt keine Option für
        eine Schnittstelle (nachgesehen in avahi-utils/avahi-publish.c
        - es gibt -a, -s, -H, -R, -f, -d, sonst nichts). Was es meldet,
        meldet es deshalb auf ALLEN Schnittstellen. Mit zwei Adressen
        bekam ein Tablet im Heimnetz also beide Antworten:

            xrack.local -> 192.168.1.50   (erreichbar)
            xrack.local -> 10.42.0.1      (die Brücke des Access
                                           Points - von hier aus nicht)

        Welche der Browser nimmt, entscheidet er selbst. Nimmt er die
        zweite, laufen die Pakete zum Router und verschwinden dort:
        keine Fehlermeldung, sondern eine halbe Minute Warten und dann
        "Netzwerk-Zeitüberschreitung". Am Gerät sah das so aus, wie es
        sich anfühlt - mal geht es, mal nicht, und niemand weiß warum.

        Der eigene Hostname hat dieses Problem nie gehabt: Den meldet
        avahi-daemon selbst, und der kennt seine Schnittstellen - auf
        wlan0 antwortet er mit der wlan0-Adresse, auf br0 mit der von
        br0. Genau deshalb war "x18rack.local" durchgehend erreichbar,
        während "xrack.local" sprunghaft war.

        Nachbauen lässt sich das mit avahi-publish nicht. Also wird
        eine Adresse ausgesucht, und zwar die, die von überall
        erreichbar ist:

          1. Die Schnittstelle mit der Standardroute. Sie führt ins
             Heimnetz; ein Tablet dort erreicht sie direkt, und eines
             am Access Point erreicht sie über XRack - für das ist
             XRack ja das Standard-Gateway.
          2. Sonst die Brücke des Access Points. Das ist der
             Proberaum ohne Heimnetz: Dort hängen die Tablets am
             Access Point, und nur diese Adresse gibt es.
          3. Sonst irgendeine echte Adresse (etwa die Buchse zum
             Mischpult, wenn sonst nichts da ist).
          4. Sonst eine selbstvergebene - besser als gar kein Name.

        Umgekehrt gilt der Satz nicht: Die Adresse des Access Points
        ist NUR von dort zu erreichen. Sie zu melden, solange es eine
        bessere gibt, schadet mehr, als sie nützt.
        """

        karte = self.schnittstellen()

        if not karte:
            return []

        standard = self.standard_schnittstelle()

        echte = [
            adresse
            for name, adressen in karte.items()
            if name != AP_BRUECKE
            for adresse in adressen
            if not adresse.startswith(SELBSTVERGEBEN)
        ]

        alle = [
            adresse
            for adressen in karte.values()
            for adresse in adressen
        ]

        for kandidaten in (
            [a for a in karte.get(standard, []) if a],
            karte.get(AP_BRUECKE, []),
            echte,
            alle,
        ):

            if kandidaten:
                #
                # Eine reicht, und mehr als eine ist der Fehler von
                # oben. Mehrere Adressen auf derselben Schnittstelle
                # sind ohnehin die Ausnahme.
                #
                return kandidaten[:1]

        return []

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
