"""
USB-Stick-Zugriff: Aufnahmen hinkopieren - und Dateien von dort holen.

Das eigentliche Einhängen/Aushängen passiert unabhängig von XRack
über eine udev-Regel + einen systemd-Dienst (siehe install.sh) - hier
wird nur geprüft, ob unter dem festen Mountpunkt gerade ein
Datenträger eingehängt ist, dorthin kopiert und (auf Wunsch aus dem
Webinterface) wieder ausgehängt.

Der Weg VOM Stick kam später dazu, und er hat gefehlt: Für Musik gab
es wenigstens den Upload über den Browser, für Aufnahmen gar nichts -
ein Übungsmix aus dem Backup oder von einem zweiten XRack kam nicht
wieder auf das Gerät.

Was dabei nicht passieren darf, steht in den Regeln unten: aus dem
Stick heraus lesen (".." im Pfad), eine vorhandene Datei überschreiben,
eine halbe Datei zurücklassen, oder die Karte volllaufen lassen.
"""

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Callable

_COPY_CHUNK_SIZE = 4 * 1024 * 1024

#
# Was XRack mit einer Datei anfangen kann.
#
# Die Musikbibliothek nimmt, was ffmpeg spielt (dieselbe Liste wie in
# player/music_library.py - dort wird sie beim Speichern noch einmal
# geprüft). Bei den Aufnahmen ist es XRacks eigenes Format: Was dort
# landet, wird vom Soundcheck-Spieler und vom Üben-Dekoder gelesen,
# und die lesen Wave64.
#
ENDUNGEN_MUSIK = {
    ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma",
}

ENDUNGEN_AUFNAHMEN = {".w64"}

#
# Was Betriebssysteme auf jedem Stick hinterlassen und niemand sucht.
#
VERSTECKT = {
    "System Volume Information",
    "$RECYCLE.BIN",
    "found.000",
    "lost+found",
}


class UsbStorage:
    """Kapselt den Zugriff auf den automatisch eingehängten USB-Stick."""

    MOUNT_POINT = Path("/media/xrack-usb")

    def __init__(self):
        self.logger = logging.getLogger("XRack")

    @property
    def connected(self) -> bool:
        """True, wenn gerade ein USB-Stick eingehängt ist."""

        return self.MOUNT_POINT.is_mount()

    def copy_file(
        self,
        source: Path,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[bool, bool]:
        """
        Kopiert eine Datei ins Wurzelverzeichnis des USB-Sticks.

        Liefert (erfolgreich, bereits_vorhanden). Ist dort schon eine
        gleichnamige Datei vorhanden, wird nicht erneut kopiert.
        `on_progress(kopierte_bytes, gesamt_bytes)` wird nach jedem
        gelesenen Block aufgerufen, damit das Webinterface eine
        Fortschrittsanzeige zeigen kann.
        """

        if not self.connected:
            return False, False

        target = self.MOUNT_POINT / source.name

        if target.exists():
            return True, True

        total = source.stat().st_size
        copied = 0

        try:

            with source.open("rb") as src, target.open("wb") as dst:

                while True:

                    chunk = src.read(_COPY_CHUNK_SIZE)

                    if not chunk:
                        break

                    dst.write(chunk)

                    copied += len(chunk)

                    if on_progress is not None:
                        on_progress(copied, total)

        except OSError:

            target.unlink(missing_ok=True)

            return False, False

        return True, False

    # ----------------------------------------------------------------
    # Vom Stick: nachsehen und holen
    # ----------------------------------------------------------------

    def aufloesen(self, relativ: str) -> Path | None:
        """
        Einen Pfad vom Browser sicher gegen den Stick auflösen.

        None, wenn er den Stick verlässt oder nicht existiert. Die
        Regel ist dieselbe wie in der Musikbibliothek, und sie ist hier
        genauso nötig: Was von außen kommt, darf nicht bestimmen, WO
        gelesen wird - "../../etc" wäre sonst ein Dateimanager für das
        ganze System.
        """

        if not self.connected:
            return None

        wurzel = self.MOUNT_POINT.resolve()

        kandidat = (self.MOUNT_POINT / relativ).resolve()

        if kandidat != wurzel and wurzel not in kandidat.parents:
            return None

        if not kandidat.exists():
            return None

        return kandidat

    def browse(self, relativ: str = "", endungen=None) -> dict | None:
        """
        Was in diesem Ordner des Sticks liegt.

        `endungen` sagt, was XRack damit anfangen kann. Dateien, die
        nicht dazugehören, werden trotzdem AUFGEFÜHRT - nur als nicht
        verwendbar gekennzeichnet. Wer seine Datei gar nicht sieht,
        sucht sie; wer sie ausgegraut sieht, versteht warum.

        Versteckte Dateien bleiben draußen, samt der Ordner, die
        Betriebssysteme auf jedem Stick hinterlassen: Niemand sucht
        dort etwas, und zwischen zwanzig "._Foo"-Dateien findet man
        sein Album nicht.
        """

        ordner = self.aufloesen(relativ)

        if ordner is None or not ordner.is_dir():
            return None

        ordnernamen = []
        dateien = []

        try:
            eintraege = sorted(
                ordner.iterdir(), key=lambda e: e.name.lower()
            )

        except OSError as fehler:

            self.logger.warning(
                "USB-Ordner nicht lesbar: %s (%s)", ordner, fehler
            )

            return None

        for eintrag in eintraege:

            if eintrag.name.startswith(".") or eintrag.name in VERSTECKT:
                continue

            if eintrag.is_dir():
                ordnernamen.append(eintrag.name)
                continue

            if not eintrag.is_file():
                continue

            try:
                groesse = eintrag.stat().st_size
            except OSError:
                continue

            dateien.append({
                "name": eintrag.name,
                "size": groesse,
                "usable": (
                    True if endungen is None
                    else eintrag.suffix.lower() in endungen
                ),
            })

        return {
            "path": relativ.strip("/"),
            "folders": ordnernamen,
            "files": dateien,
        }

    def groesse_von(self, relative_pfade: list[str], endungen=None) -> int:
        """
        Wie viele Bytes das Kopieren dieser Auswahl bedeutet.

        Ordner zählen mit allem, was in ihnen (und in ihren
        Unterordnern) verwendbar ist. Gebraucht wird die Summe VOR dem
        Kopieren: Eine halb kopierte Datei auf einer vollen Karte ist
        der unangenehmste Ausgang, den es hier gibt.
        """

        gesamt = 0

        for relativ in relative_pfade:

            pfad = self.aufloesen(relativ)

            if pfad is None:
                continue

            for datei in self._dateien_unter(pfad, endungen):

                try:
                    gesamt += datei.stat().st_size
                except OSError:
                    pass

        return gesamt

    def _dateien_unter(self, pfad: Path, endungen=None) -> list[Path]:
        """Alle verwendbaren Dateien - bei einem Ordner rekursiv."""

        if pfad.is_file():

            if endungen is None or pfad.suffix.lower() in endungen:
                return [pfad]

            return []

        gefunden = []

        for eintrag in sorted(pfad.rglob("*"), key=lambda e: str(e).lower()):

            if not eintrag.is_file():
                continue

            if any(
                teil.startswith(".") or teil in VERSTECKT
                for teil in eintrag.relative_to(pfad).parts
            ):
                continue

            if endungen is not None and eintrag.suffix.lower() not in endungen:
                continue

            gefunden.append(eintrag)

        return gefunden

    def hereinkopieren(
        self,
        relative_pfade: list[str],
        ziel: Path,
        endungen=None,
        flach: bool = False,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> dict:
        """
        Holt Dateien und ganze Ordner vom Stick nach `ziel`.

        Ordner wandern MIT ihrer Struktur - ein Album bleibt ein Album.
        Nur bei den Aufnahmen nicht: Dieses Verzeichnis ist flach, und
        eine Datei in einem Unterordner fände XRack dort nie wieder
        (`flach=True` legt deshalb alles nebeneinander).

        Eine gleichnamige Datei am Ziel wird ÜBERSPRUNGEN, nicht
        überschrieben - dieselbe Regel wie beim Kopieren auf den Stick.
        Was man sich mit einem Fehlgriff zerstört, ist sonst genau das,
        was man aufheben wollte.

        Liefert eine Übersicht: kopiert, übersprungen, fehlgeschlagen.
        """

        quellen: list[tuple[Path, Path]] = []

        for relativ in relative_pfade:

            pfad = self.aufloesen(relativ)

            if pfad is None:
                continue

            for datei in self._dateien_unter(pfad, endungen):

                if flach or pfad.is_file():
                    unterpfad = Path(datei.name)

                else:
                    #
                    # Der Ordner selbst gehoert mit ins Ziel, sonst
                    # landen zwei Alben mit "01 Intro.mp3"
                    # uebereinander.
                    #
                    unterpfad = Path(pfad.name) / datei.relative_to(pfad)

                quellen.append((datei, ziel / unterpfad))

        gesamt = 0

        for quelle, _ in quellen:
            try:
                gesamt += quelle.stat().st_size
            except OSError:
                pass

        bericht = {
            "kopiert": 0,
            "uebersprungen": 0,
            "fehlgeschlagen": 0,
            "bytes": gesamt,
        }

        fertig = 0

        for quelle, zieldatei in quellen:

            if zieldatei.exists():

                bericht["uebersprungen"] += 1

                try:
                    fertig += quelle.stat().st_size
                except OSError:
                    pass

                if on_progress is not None:
                    on_progress(fertig, gesamt, quelle.name)

                continue

            #
            # Vor dem try, damit der Fehlerzweig sie auf jeden Fall
            # kennt - auch wenn schon das Anlegen des Ordners scheitert.
            #
            halb = zieldatei.with_name(zieldatei.name + ".teil")

            try:

                zieldatei.parent.mkdir(parents=True, exist_ok=True)

                #
                # Erst daneben schreiben, dann umbenennen.
                #
                # Ein Abbruch mittendrin (Stick gezogen, Karte voll)
                # hinterlaesst sonst eine halbe Datei mit dem richtigen
                # Namen - und die faellt erst auf, wenn man sie
                # braucht. Das Umbenennen im selben Verzeichnis ist
                # unteilbar.
                #
                with quelle.open("rb") as ein, halb.open("wb") as aus:

                    while True:

                        stueck = ein.read(_COPY_CHUNK_SIZE)

                        if not stueck:
                            break

                        aus.write(stueck)

                        fertig += len(stueck)

                        if on_progress is not None:
                            on_progress(fertig, gesamt, quelle.name)

                halb.replace(zieldatei)

                shutil.copystat(quelle, zieldatei, follow_symlinks=False)

                bericht["kopiert"] += 1

            except OSError as fehler:

                self.logger.warning(
                    "Kopieren vom Stick fehlgeschlagen: %s (%s)",
                    quelle.name,
                    fehler,
                )

                halb.unlink(missing_ok=True)

                bericht["fehlgeschlagen"] += 1

        return bericht

    def eject(self) -> tuple[bool, str]:
        """
        Hängt den USB-Stick sicher aus, damit er entfernt werden kann.
        """

        script = Path("scripts") / "xrack-usb-unmount.sh"

        try:

            result = subprocess.run(
                ["sudo", "-n", str(script.resolve())],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:

                message = result.stderr.strip() or result.stdout.strip()

                self.logger.error(
                    "USB-Stick auswerfen fehlgeschlagen: %s",
                    message,
                )

                return False, message

            return True, ""

        except subprocess.TimeoutExpired:

            self.logger.error("USB-Stick auswerfen: Zeitüberschreitung.")

            return False, "Zeitüberschreitung."

        except Exception as exc:

            self.logger.exception(
                "USB-Stick auswerfen fehlgeschlagen: %s",
                exc,
            )

            return False, str(exc)
