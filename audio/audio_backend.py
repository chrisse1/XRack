"""
Low-Level Zugriff auf das Audio-Interface.

Diese Klasse kapselt den direkten Zugriff auf ALSA.

Zum Sampleformat, denn daran haengt die ganze Kette:

XRack rechnet durchgaengig mit S32_LE - vier Byte je Abtastwert und
2^31 als Vollausschlag. So messen die Pegel (recorder/level_meter.py),
so rechnet der Uebungsmix (core/stem_combiner.py), so hoert die
Lichtshow mit, und so steht es im Wave64-Kopf (32-Bit-Container mit
ValidBitsPerSample=24, siehe writer/w64_writer.py).

Angefordert wurde hier lange trotzdem S24_LE. Die X-Serie bietet das
ueber USB nicht an, ALSA liefert S32_LE - richtig war es also nur, weil
das Interface etwas anderes gab, als XRack verlangte. Im Protokoll
stand dafuer bei JEDEM Start eine Warnung ueber eine "andere Skala",
die nicht zutraf; und auf einem Interface, das S24_LE tatsaechlich
anbietet, waeren die Pegel 256-fach zu niedrig gewesen.

Deshalb wird jetzt das angefordert, was gebraucht wird. Kommt etwas
anderes zurueck, ist das ein Befund und keine Nebenbemerkung: Die
Meldung nennt das Format und was es bedeutet.
"""

import logging

import alsaaudio

from audio.channel_extractor import ChannelExtractor
from audio.models import AudioDevice, DiagnosticItem


#
# Das Format, mit dem die ganze Kette rechnet.
#
WUNSCHFORMAT = alsaaudio.PCM_FORMAT_S32_LE

WUNSCHFORMAT_NAME = "S32_LE"


def formatname(wert) -> str:
    """
    Aus der ALSA-Zahl den Namen machen (10 -> "S32_LE").

    In einer Meldung ist "gemeldet 10" fuer niemanden zu gebrauchen -
    genau so stand es aber im Protokoll.
    """

    for name in dir(alsaaudio):

        if not name.startswith("PCM_FORMAT_"):
            continue

        if getattr(alsaaudio, name) == wert:
            return name[len("PCM_FORMAT_"):]

    return str(wert)


class AudioBackend:
    """Kommuniziert direkt mit ALSA."""

    def __init__(self):

        self.logger = logging.getLogger("XRack")

        self.device: AudioDevice | None = None

        self._pcm = None

        self._rate = 0
        self._channels = 0
        self._native_channels = 0
        self._period_size = 0
        self._format = None
        self._extractor: ChannelExtractor | None = None

    # ---------------------------------------------------------
    # Properties
    # ---------------------------------------------------------

    @property
    def opened(self) -> bool:
        """True, wenn ein PCM-Handle geöffnet ist."""
        return self._pcm is not None

    @property
    def rate(self) -> int:
        return self._rate

    @property
    def channels(self) -> int:
        """Wie viele Kanäle in die Aufnahme gehen."""
        return self._channels

    @property
    def native_channels(self) -> int:
        """
        Wie viele Kanäle das Interface wirklich liefert.

        Das ist nicht dasselbe wie `channels`: Aufgenommen wird
        vielleicht weniger (siehe open()), gelesen wird immer alles.
        Wer den vollen Strom auswertet - die Lichtshow etwa -, muss
        sich an dieser Zahl orientieren.
        """
        return self._native_channels

    @property
    def period_size(self) -> int:
        return self._period_size

    @property
    def sample_format(self):
        return self._format

    @property
    def alsa_name(self) -> str:
        """Liefert den ALSA-Gerätenamen."""

        if self.device is None:
            return ""

        return f"hw:{self.device.card},{self.device.device}"

    # ---------------------------------------------------------
    # Öffnen / Schließen
    # ---------------------------------------------------------

    def open(
        self,
        device: AudioDevice,
        channels: int | None = None,
        rate: int | None = None,
    ) -> bool:
        """
        Öffnet das Audiogerät.

        Das Interface wird IMMER mit seiner vollen, festen
        Kanalzahl (device.channels) geöffnet. Digitalmischpulte wie
        die Behringer X-Serie kennen über USB keinen Modus mit
        weniger Kanälen - fordert man dort z.B. 8 statt 18 Kanäle
        an, nimmt ALSA trotzdem alle 18 auf, meldet aber keinen
        Fehler. Ohne diese Regel verschieben sich dadurch alle
        Kanäle im Datenstrom (falsche Spur, falsche Dauer).

        Die gewünschte (kleinere) Kanalzahl wird stattdessen erst
        beim Lesen in Software aus dem Datenstrom herausgeschnitten,
        siehe `audio.channel_extractor.ChannelExtractor`.

        `rate` ist die vom Nutzer erklärte, tatsächlich am Interface
        eingestellte Samplerate (siehe
        `Application.set_mixer_sample_rate()`) - `device.sample_rate`
        selbst ist nur der von ALSA gemeldete Wertebereich und kein
        verlässlicher Hinweis auf die tatsächlich aktive Clock.
        """

        self.device = device

        self._rate = rate if rate is not None else device.sample_rate
        self._native_channels = device.channels
        self._channels = (
            channels
            if channels is not None
            else device.channels
        )
        self._period_size = 1024

        self._format = WUNSCHFORMAT

        self._extractor = ChannelExtractor(
            input_channels=self._native_channels,
            output_channels=self._channels,
        )

        try:

            self._pcm = alsaaudio.PCM(

                type=alsaaudio.PCM_CAPTURE,

                mode=alsaaudio.PCM_NORMAL,

                device=device.id,

            )

            actual_rate = self._pcm.setrate(
                self._rate
            )

            if actual_rate and actual_rate != self._rate:
                self.logger.warning(
                    "ALSA hat eine andere Samplerate akzeptiert als "
                    "angefordert: gefordert %d Hz, gemeldet %d Hz.",
                    self._rate,
                    actual_rate,
                )

            self._pcm.setchannels(
                self._native_channels
            )

            actual_format = self._pcm.setformat(
                self._format
            )

            if actual_format is not None and actual_format != self._format:

                #
                # Ein Befund, keine Nebenbemerkung: XRacks ganze Kette
                # rechnet mit S32_LE (siehe Kopf dieser Datei). Kommt
                # etwas anderes, stimmen Pegel und Aufnahmen nicht, und
                # bei einem Drei-Byte-Format (S24_3LE) verrutschen sogar
                # die Kanaele. Deshalb mit Namen, Angebot und Folge -
                # "gemeldet 10" hat im Protokoll niemandem geholfen.
                #
                self._format = actual_format

                self.logger.error(
                    "Das Interface liefert %s statt %s. XRack rechnet mit "
                    "%s (vier Byte je Wert, 2^31 Vollausschlag) - Pegel "
                    "und Aufnahmen sind damit nicht verlaesslich. Das "
                    "Geraet bietet an: %s.",
                    formatname(actual_format),
                    WUNSCHFORMAT_NAME,
                    WUNSCHFORMAT_NAME,
                    ", ".join(device.formats) or "unbekannt",
                )

            self._pcm.setperiodsize(
                self._period_size
            )

            self.logger.info(
                "ALSA geöffnet: %s | Hardware: %d Ch | Aufnahme: %d Ch | %d Hz",
                device.id,
                self._native_channels,
                self._channels,
                self._rate,
            )

            return True

        except Exception as exc:

            self.logger.exception(
                "ALSA konnte nicht geöffnet werden: %s",
                exc,
            )

            self._pcm = None

            return False

    def close(self) -> None:
        """
        Schließt das Audiogerät.
        """

        if self._pcm is not None:

            self._pcm.close()

            self._pcm = None

        self.device = None

        self.logger.info(
            "ALSA-Gerät geschlossen."
        )

    # ---------------------------------------------------------
    # Lesen
    # ---------------------------------------------------------

    def read(self) -> bytes | None:
        """
        Liest einen Audiobuffer - mit ALLEN Kanälen des Interfaces.

        Hier wurde frueher schon auf die Aufnahmebreite geschnitten.
        Das kostete die Lichtshow ihre Quellen: Sie haengt als
        Mithoerer am selben Strom, sah damit nur die ersten
        `channels` Kanaele und konnte auf einem X32 (32 Kanaele) nur
        aus 18 waehlen - so viele nimmt XRack in seiner Vorgabe auf.

        Geschnitten wird deshalb erst dort, wo es hingehoert: fuer
        die Datei und die Pegelanzeige, siehe aufnahmebreite() und
        recorder/recorder.py.
        """

        if self._pcm is None:
            return None

        length, data = self._pcm.read()

        if length <= 0:
            return None

        return data

    def aufnahmebreite(self, data: bytes) -> bytes:
        """
        Aus dem vollen Strom die Kanäle schneiden, die aufgenommen
        werden sollen.

        Sind es alle, kommt der Block unveraendert zurueck - der
        Schnitt kostet dann nichts.
        """

        if self._extractor is None:
            return data

        return self._extractor.extract(data)

    # ---------------------------------------------------------
    # Diagnose
    # ---------------------------------------------------------

    def diagnose(self) -> list[DiagnosticItem]:
        """
        Führt eine Diagnose des Audio-Backends durch.
        """

        diagnostics: list[DiagnosticItem] = []

        diagnostics.append(
            DiagnosticItem(
                name="ALSA Device",
                ok=self.device is not None,
                message=(
                    self.device.id
                    if self.device is not None
                    else "Kein Gerät ausgewählt."
                ),
            )
        )

        diagnostics.append(
            DiagnosticItem(
                name="PCM Handle",
                ok=self.opened,
                message=(
                    "PCM erfolgreich geöffnet."
                    if self.opened
                    else "PCM nicht geöffnet."
                ),
            )
        )

        #
        # Das Format gehoert in die Selbstpruefung: Steht dort etwas
        # anderes als S32_LE, sind Pegel und Aufnahmen nicht
        # verlaesslich - und im Protokoll faellt es keinem auf.
        #
        diagnostics.append(
            DiagnosticItem(
                name="Sampleformat",
                ok=(not self.opened) or self._format == WUNSCHFORMAT,
                message=(
                    formatname(self._format)
                    if self.opened
                    else "Nicht geoeffnet."
                ),
            )
        )

        diagnostics.append(
            DiagnosticItem(
                name="Backend",
                ok=self.opened,
                message=(
                    "Backend bereit."
                    if self.opened
                    else "Backend geschlossen."
                ),
            )
        )

        return diagnostics
