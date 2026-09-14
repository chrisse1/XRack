#!/usr/bin/env python3
"""
Prüft die Karte, die zwischen Musik und Üben umschaltet.

Warum eine Karte mit Umschalter und nicht zwei Karten nebeneinander:
Zwei Wiedergabeströme kann das Interface nicht (deshalb schließen sich
Musik und Soundcheck seit jeher aus). Zwei Karten würden also etwas
anbieten, was die Hardware nicht hergibt.

Zwei Dinge werden geprüft, und beide in echt:

  1. Die Anwendungsschicht (core/application/musik.py) mit den
     wirklichen Methoden und einem wirklichen StateStore - denn der
     Zustand soll am GERÄT liegen, nicht im Browser: Was das Rack tut,
     sieht auf jedem Tablet gleich aus.

  2. Die Karte im echten Browser mit dem echten xrack.js - dass der
     Umschalter den Kopf tauscht, während der Wiedergabe gesperrt ist
     und der Üben-Knopf schickt, was in den Feldern steht.

Ohne Browser wird der zweite Teil übersprungen statt zu scheitern -
auf dem Pi ist keiner installiert, und dort soll die Testreihe
durchlaufen.
"""

#
# Der Suchpfad zur Projektwurzel - siehe tests/_wurzel.py. Muss VOR
# allen Importen aus XRack stehen.
#
from _wurzel import WURZEL  # noqa: F401,E402


import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path


sys.path.insert(0, str(WURZEL))

#
# alsaaudio gibt es auf dem Entwicklungsrechner nicht; gebraucht wird
# es hier auch nicht - geöffnet wird nichts.
#
fake_alsaaudio = types.ModuleType("alsaaudio")
for name in (
    "PCM_FORMAT_S16_LE", "PCM_FORMAT_S24_LE", "PCM_FORMAT_S32_LE",
    "PCM_CAPTURE", "PCM_PLAYBACK", "PCM_NORMAL",
):
    setattr(fake_alsaaudio, name, 0)
sys.modules.setdefault("alsaaudio", fake_alsaaudio)

from core.application.musik import MusikMixin  # noqa: E402
from core.state_store import StateStore  # noqa: E402
from core.status import SystemStatus  # noqa: E402
from web.i18n import get_translations  # noqa: E402


TEXTE = get_translations("de")


# ====================================================================
# Teil 1: Die Anwendungsschicht
#
# Echte Methoden, echter StateStore - nur die Hardware ist
# nachgestellt. Was hier durchrutscht, merkt man am Gerät.
# ====================================================================

#
# Ein gemeinsames Protokoll: Wer wann gerufen wurde. Die REIHENFOLGE
# ist beim Mitschneiden kein Schoenheitsfehler - laeuft der Ton vor
# der Aufnahme los, fehlt auf dem Mitschnitt der Einsatz.
#
PROTOKOLL: list[str] = []


class Spieler:
    """Ein Musikspieler, der sich merkt, womit er gerufen wurde."""

    def __init__(self):
        self.playing = False
        self.paused = False
        self.wiederholen = False
        self.aufrufe = []
        self.oeffnet = True

    def set_wiederholen(self, an):
        self.wiederholen = bool(an)

    def stop(self):
        PROTOKOLL.append("ton-aus")
        self.playing = False

    def play_practice(self, device, path, start_channel, rate,
                      wiederholen=False, mitschnitt=None,
                      mitschnitt_start=0, versatz=0.0, beim_start=None):

        PROTOKOLL.append("ton-an")

        if not self.oeffnet:
            return False

        #
        # Das echte Gegenstueck ruft beim ersten Block ans Interface -
        # hier sofort, denn die Attrappe hat keinen Lesethread.
        #
        if beim_start is not None:
            beim_start()

        self.aufrufe.append({
            "pfad": Path(path),
            "start_channel": start_channel,
            "rate": rate,
            "wiederholen": wiederholen,
            "mitschnitt": mitschnitt,
            "mitschnitt_start": mitschnitt_start,
            "versatz": versatz,
        })
        self.playing = True
        return True


class Soundcheck:
    """Der andere Wiedergabeweg - er darf nicht gleichzeitig laufen."""

    def __init__(self):
        self.playing = False


class Schreiber:
    def __init__(self, ordner):
        self.directory = ordner


class Aufnehmer:
    """Ein Recorder, der sich nur merkt, was mit ihm geschah."""

    def __init__(self, ordner, namen):
        self.writer = Schreiber(ordner)
        self.recordings = list(namen)
        self.bereit = True
        self.recording = False
        self.monitoring = False
        self.praefixe = []

        #
        # Das Lebenszeichen des Aufnahmestroms. Die Attrappe liefert
        # sofort - geprueft wird hier die Reihenfolge, nicht die
        # Anlaufzeit (die steht in test_laufzeit_messung.py).
        #
        self.bloecke_gelesen = 0

    def start_monitoring(self):
        #
        # Der Vorlauf, der den Aufnahmestrom in Gang bringt, bevor der
        # erste Ton hinausgeht (siehe
        # Application._aufnahmestrom_vorwaermen).
        #
        PROTOKOLL.append("strom-an")
        self.monitoring = True
        self.bloecke_gelesen += 2
        return True

    def start(self, name_prefix="Soundcheck", trenner="-"):

        PROTOKOLL.append("aufnahme-an")

        self.praefixe.append(name_prefix)

        if not self.bereit or self.recording:
            return False

        self.recording = True
        return True

    def stop(self):
        PROTOKOLL.append("aufnahme-aus")
        self.recording = False

        #
        # Wie beim echten Recorder: "Stop" beendet auch eine
        # Pegelpruefung, die daneben lief (siehe Recorder._abmelden).
        # Damit steht der Aufnahmestrom danach wieder - und der
        # naechste Lauf muss ihn erneut in Gang bringen.
        #
        self.monitoring = False


class Anwendung(MusikMixin):
    """
    Die echten Methoden aus dem Mixin auf nachgestellter Hardware.

    Nicht die ganze Application: Die zöge ALSA, Netzwerk und DMX nach
    sich. Geprüft werden soll die Entscheidungslogik, und die steht
    vollständig im Mixin.
    """

    def __init__(self, ordner: Path, namen, zustand: Path):

        self.state_store = StateStore(zustand)

        self.music_player = Spieler()
        self.player = Soundcheck()
        self.recorder = Aufnehmer(ordner, namen)

        self.selected_audio_device = "hw:1,0"
        self.mixer_sample_rate = 48000

        self.player_mode = self.state_store.get("player_mode", "music")

        self.practice_repeat = self.state_store.get(
            "practice_repeat", False
        )

        self.practice_record = self.state_store.get(
            "practice_record", False
        )

        self.practice_recording = False

        self.practice_active = False

        self.practice_offset_ms = self.state_store.get(
            "practice_offset_ms", 0
        )

        self.record_name_prefix = "Soundcheck"


with tempfile.TemporaryDirectory() as tmp:

    ordner = Path(tmp)
    zustand = ordner / "state.json"

    NAMEN = [
        "Soundcheck-1_s.w64",
        "Uebung-1_p.w64",
        "Soundcheck-2_s9.w64",
        "Uebung-2_p.w64",

        #
        # Mit Kanalziffer: Dieser Mix wurde fuer die Kanaele 9ff.
        # gebaut und gehoert beim Ueben wieder dorthin.
        #
        "Uebung-3_p9.w64",

        #
        # Mitschnitte zum Ueben: Sie tragen den Namen ihres
        # Uebungsmixes und finden so zu ihm zurueck.
        #
        "Uebung-1-Take1_s9.w64",
        "Uebung-1-Take2_s9.w64",
        "Uebung-3-Take1_s.w64",

        #
        # Und einer, dessen Uebungsmix es nicht gibt - er ist damit
        # eine Aufnahme wie jede andere.
        #
        "Verwaist-Take1_s.w64",

        "Alt-ohne-Marke.w64",
    ]

    for name in NAMEN:
        (ordner / name).write_bytes(b"x")

    anwendung = Anwendung(ordner, NAMEN, zustand)

    # ----------------------------------------------------------------
    # 1. Nur Übungsmixe stehen in der Auswahl
    #
    # Erkannt am Namen, wie überall - eine eigene Verwaltungsdatei
    # gibt es bewusst nicht, damit die Zuordnung über USB, Download
    # und Backup mitreist.
    # ----------------------------------------------------------------

    mixe = anwendung.practice_mixes()

    assert mixe == [
        "Uebung-1_p.w64",
        "Uebung-2_p.w64",
        "Uebung-3_p9.w64",
    ], (
        f"In der Üben-Auswahl stehen {mixe} - dort gehören nur die "
        f"Übungsmixe hin, keine Soundchecks."
    )

    print("OK: Die Üben-Auswahl zeigt nur Übungsmixe")

    # ----------------------------------------------------------------
    # 2. Umschalten - und der Zustand liegt am Gerät
    #
    # Nicht im Browser: Was das Rack tut, soll auf jedem Tablet gleich
    # aussehen. Deshalb wird hier mit einem ECHTEN StateStore geprüft,
    # und zwar so, wie ein Neustart es täte: neu von der Platte lesen.
    # ----------------------------------------------------------------

    erfolg, meldung = anwendung.set_player_mode("practice")

    assert erfolg, meldung
    assert anwendung.player_mode == "practice"

    frisch = StateStore(zustand)

    assert frisch.get("player_mode") == "practice", (
        "Die Betriebsart steht nicht in der Zustandsdatei - nach einem "
        "Neustart stünde die Karte wieder auf Musik, und am zweiten "
        "Tablet sähe sie anders aus als am ersten."
    )

    erfolg, meldung = anwendung.set_player_mode("unfug")

    assert not erfolg, "Eine unbekannte Betriebsart wurde angenommen."

    assert anwendung.player_mode == "practice", (
        "Eine abgelehnte Betriebsart hat den Zustand trotzdem verändert."
    )

    print("OK: Die Betriebsart wird am Gerät gemerkt und geprüft")

    # ----------------------------------------------------------------
    # 3. Nicht umschalten, solange etwas läuft
    #
    # Die Karte tauscht darunter die Quelle aus. Mitten in der
    # Wiedergabe umzuschalten hieße: Man drückt auf "Üben", und die
    # Musik läuft weiter.
    # ----------------------------------------------------------------

    anwendung.music_player.playing = True

    erfolg, meldung = anwendung.set_player_mode("music")

    assert not erfolg, (
        "Die Karte ließ sich mitten in der Wiedergabe umschalten."
    )

    assert meldung, "Die Ablehnung nennt keinen Grund."

    assert anwendung.player_mode == "practice"

    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()

    print("OK: Umgeschaltet wird nur, wenn nichts läuft")

    # ----------------------------------------------------------------
    # 4. Was kein Übungsmix ist, wird nicht als einer abgespielt
    #
    # Ein Soundcheck liegt im selben Ordner und ist einen Tippfehler
    # weit entfernt. Abgespielt würde er ab dem gewählten Kanal - also
    # irgendwo.
    # ----------------------------------------------------------------

    erfolg, meldung = anwendung.start_practice("Soundcheck-1_s.w64")

    assert not erfolg and meldung, (
        "Ein Soundcheck wurde als Übungsmix abgespielt."
    )

    erfolg, meldung = anwendung.start_practice("Gibtsnicht_p.w64")

    assert not erfolg and meldung, (
        "Ein Übungsmix, den es nicht gibt, wurde angenommen."
    )

    assert anwendung.music_player.aufrufe == [], (
        "Trotz Ablehnung wurde der Spieler gerufen."
    )

    #
    # Und der Pfad muss im Aufnahmeordner bleiben: Ein Name mit ../
    # zeigte sonst aus dem Ordner heraus.
    #
    erfolg, meldung = anwendung.start_practice("../Uebung-1_p.w64")

    if erfolg:
        gerufen = anwendung.music_player.aufrufe[-1]["pfad"]
        assert gerufen.parent == ordner, (
            f"Der Übungsmix wurde außerhalb des Aufnahmeordners "
            f"gesucht: {gerufen}"
        )
        anwendung.music_player.aufrufe.clear()
        anwendung.music_player.playing = False
        anwendung.uebung_nachfuehren()

    print("OK: Nur wirkliche Übungsmixe werden abgespielt")

    # ----------------------------------------------------------------
    # 5. Zwei Wiedergaben gleichzeitig kann das Interface nicht
    #
    # Die Sperre gehört hierher und nicht nur in die Oberfläche: Sonst
    # scheitert ALSA, und was der Nutzer sieht, ist ein Knopf, der
    # nichts tut.
    # ----------------------------------------------------------------

    anwendung.player.playing = True

    erfolg, meldung = anwendung.start_practice("Uebung-1_p.w64")

    assert not erfolg and meldung, (
        "Üben startete, obwohl ein Soundcheck lief - zwei "
        "Wiedergabeströme kann das Interface nicht."
    )

    anwendung.player.playing = False

    ohne_geraet = Anwendung(ordner, NAMEN, ordner / "leer.json")
    ohne_geraet.selected_audio_device = None

    erfolg, meldung = ohne_geraet.start_practice("Uebung-1_p.w64")

    assert not erfolg and meldung, (
        "Üben startete ohne Audiogerät."
    )

    print("OK: Üben startet nicht gegen eine laufende Wiedergabe")

    # ----------------------------------------------------------------
    # 6. Auf welchen Kanälen der Mix landet, steht in seinem Namen
    #
    # Gewählt wird das einmal beim Erstellen, nicht vor jedem Üben:
    # Ein Übungsmix wird für einen Platz im Pult gebaut. Die Angabe
    # reist im Namen mit - über USB, Download und Backup -, und XRack
    # muss nirgends Buch führen.
    #
    # Der Übergang ist die heikle Stelle: Der Name zählt ab 1 (am Pult
    # steht "9"), der ChannelInserter ab 0.
    # ----------------------------------------------------------------

    erfolg, meldung = anwendung.start_practice(
        "Uebung-3_p9.w64", wiederholen=True
    )

    assert erfolg, meldung

    assert len(anwendung.music_player.aufrufe) == 1, (
        anwendung.music_player.aufrufe
    )

    ruf = anwendung.music_player.aufrufe[0]

    assert ruf["pfad"] == ordner / "Uebung-3_p9.w64", ruf["pfad"]

    assert ruf["start_channel"] == 8, (
        f"Der Spieler bekam Kanal {ruf['start_channel']} statt 8 - im "
        f"Namen steht der neunte Kanal, gezählt wird ab 0. Der Mix "
        f"landete sonst ein Paar daneben."
    )

    assert ruf["rate"] == 48000, ruf["rate"]

    assert ruf["wiederholen"] is True, (
        "Die Schleife wurde nicht durchgereicht."
    )

    #
    # Und der Gegenfall: Ohne Ziffer bleibt es Kanal 1. Alle bisher
    # erstellten Übungsmixe heissen so.
    #
    anwendung.music_player.aufrufe.clear()
    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()

    erfolg, meldung = anwendung.start_practice("Uebung-2_p.w64")

    assert erfolg, meldung

    assert anwendung.music_player.aufrufe[0]["start_channel"] == 0, (
        f"Ein Mix ohne Kanalziffer landete auf Kanal "
        f"{anwendung.music_player.aufrufe[0]['start_channel'] + 1} - "
        f"alle bisher erstellten Mixe heissen so und gehören auf 1."
    )

    print("OK: Der Kanal steht im Namen und reist richtig gezählt mit")

    # ----------------------------------------------------------------
    # 7. Die Schleife wird gemerkt und weitergegeben
    # ----------------------------------------------------------------

    anwendung.set_practice_repeat(True)

    assert anwendung.music_player.wiederholen is True, (
        "Der Schalter erreichte den Spieler nicht."
    )

    assert StateStore(zustand).get("practice_repeat") is True, (
        "Die Schleife wurde nicht am Gerät gemerkt."
    )

    anwendung.set_practice_repeat(False)

    assert anwendung.music_player.wiederholen is False
    assert StateStore(zustand).get("practice_repeat") is False

    print("OK: Die Schleife wird gemerkt und erreicht den Spieler")

    # ----------------------------------------------------------------
    # 7b. Üben + mitschneiden: die Aufnahme beginnt mit dem Ton
    #
    # Nicht vorher, und das ist der ganze Trick. Zwischen "Aufnahme
    # starten" und "der erste Ton geht hinaus" liegen das Öffnen von
    # ALSA, ein Threadstart und das Anlegen der Datei - zusammen einige
    # zehn Millisekunden, und jedes Mal unterschiedlich viele. Wer die
    # Aufnahme vorher startet, hat diesen Zufall im Mitschnitt stehen
    # und kann ihn nachher durch nichts mehr herausrechnen.
    #
    # So dagegen ist der Abstand für jeden Lauf derselbe - und damit
    # eine Grösse, die sich einmal messen und danach anwenden lässt.
    # ----------------------------------------------------------------

    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()
    anwendung.music_player.aufrufe.clear()
    PROTOKOLL.clear()

    erfolg, meldung = anwendung.start_practice(
        "Uebung-1_p.w64", mitschneiden=True
    )

    assert erfolg, meldung

    assert PROTOKOLL == ["strom-an", "ton-an", "aufnahme-an"], (
        f"Gerufen wurde in dieser Reihenfolge: {PROTOKOLL}.\n"
        f"Erwartet: erst den Aufnahmestrom in Gang bringen, dann den "
        f"Ton, dann die Aufnahme.\n"
        f"Fängt der Strom erst mit der Aufnahme an, beginnt der "
        f"Mitschnitt um eine unbekannte Spanne zu spät - der "
        f"Lesethread muss anlaufen und ALSA eine volle Periode "
        f"sammeln.\n"
        f"Und die Aufnahme gehört an den ERSTEN BLOCK des Spielers: "
        f"davor liegt eine Anlaufzeit, die jedes Mal anders ausfällt "
        f"und sich hinterher nicht herausrechnen lässt."
    )

    assert anwendung.recorder.recording, "Es wird gar nicht aufgenommen."

    assert anwendung.practice_recording is True, (
        "XRack merkt sich nicht, dass DIESER Lauf die Aufnahme "
        "gestartet hat - beim Stoppen bliebe sie laufen."
    )

    assert anwendung.recorder.praefixe == ["Uebung-1-Take"], (
        f"Der Mitschnitt heisst nach {anwendung.recorder.praefixe} - "
        f"er soll den Namen des Stücks tragen, zu dem er entstanden "
        f"ist (\"Uebung-1-Take1_s9.w64\"). Nur so findet er später "
        f"zu seinem Übungsmix zurück."
    )

    print("OK: Mitgeschnitten wird ab dem ersten Ton, nicht danach")

    # ----------------------------------------------------------------
    # 7c. Der Stop-Knopf beendet beides - aber nur das Eigene
    #
    # Lief die Aufnahme schon vorher (von der Soundcheck-Karte aus),
    # bleibt sie laufen. Etwas zu beenden, was man nicht angefangen
    # hat, wäre eine böse Überraschung: Die Datei ist dann zu, und
    # niemand hat es angeordnet.
    # ----------------------------------------------------------------

    PROTOKOLL.clear()

    anwendung.stop_practice()

    assert PROTOKOLL == ["ton-aus", "aufnahme-aus"], (
        f"Beendet wurde: {PROTOKOLL} - zum Üben gehört beides."
    )

    assert anwendung.practice_recording is False

    #
    # Der Gegenfall: eine fremde Aufnahme bleibt stehen.
    #
    anwendung.recorder.recording = True
    anwendung.practice_recording = False
    anwendung.music_player.playing = True
    PROTOKOLL.clear()

    anwendung.stop_practice()

    assert PROTOKOLL == ["ton-aus"], (
        f"Beendet wurde: {PROTOKOLL}. Diese Aufnahme hat das Üben "
        f"nicht gestartet - sie anzuhalten wäre eine Überraschung, und "
        f"zwar eine, die Ton kostet."
    )

    assert anwendung.recorder.recording is True

    anwendung.recorder.recording = False

    print("OK: Gestoppt wird nur der Mitschnitt, den das Üben startete")

    # ----------------------------------------------------------------
    # 7d. Kein halber Zustand
    #
    # Lässt sich der Übungsmix nicht öffnen, darf keine Aufnahme
    # zurückbleiben, die niemand angeordnet hat und die niemand
    # beendet.
    # ----------------------------------------------------------------

    anwendung.music_player.oeffnet = False
    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()
    PROTOKOLL.clear()

    erfolg, meldung = anwendung.start_practice(
        "Uebung-1_p.w64", mitschneiden=True
    )

    assert not erfolg and meldung, "Der Fehlschlag blieb unbemerkt."

    assert PROTOKOLL == ["strom-an", "ton-an"], (
        f"Nach dem Fehlschlag stand: {PROTOKOLL}. Kommt der Ton gar "
        f"nicht erst zustande, darf auch keine Aufnahme angefangen "
        f"haben - sie liefe sonst weiter, ohne dass jemand sie "
        f"gestartet hat."
    )

    assert anwendung.recorder.recording is False
    assert anwendung.practice_recording is False

    anwendung.music_player.oeffnet = True

    print("OK: Ein Fehlschlag lässt keine Aufnahme zurück")

    # ----------------------------------------------------------------
    # 7e. Ohne offenes Gerät wird nicht mitgeschnitten
    #
    # Und zwar VORHER abgelehnt: Sonst liefe der Übungsmix, und der
    # Mitschnitt, den man mitlaufen glaubt, gäbe es nicht.
    # ----------------------------------------------------------------

    anwendung.recorder.bereit = False
    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()
    PROTOKOLL.clear()

    erfolg, meldung = anwendung.start_practice(
        "Uebung-1_p.w64", mitschneiden=True
    )

    assert not erfolg and meldung, (
        "Üben mit Mitschnitt startete ohne offenes Gerät."
    )

    assert PROTOKOLL == [], (
        f"Es wurde trotzdem etwas gerufen: {PROTOKOLL}. Der Übungsmix "
        f"liefe dann, und der Mitschnitt, den man mitlaufen glaubt, "
        f"gäbe es nicht."
    )

    #
    # Ohne Mitschnitt geht es weiterhin - das Üben selbst braucht den
    # Recorder nicht.
    #
    erfolg, meldung = anwendung.start_practice("Uebung-1_p.w64")

    assert erfolg, (
        f"Ohne Mitschnitt lässt sich nicht mehr üben: {meldung}"
    )

    anwendung.recorder.bereit = True
    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()

    print("OK: Ohne Gerät kein Mitschnitt - und trotzdem Üben")

    # ----------------------------------------------------------------
    # 7f. Der Schalter wird am Gerät gemerkt
    # ----------------------------------------------------------------

    anwendung.set_practice_record(True)

    assert StateStore(zustand).get("practice_record") is True, (
        "Der Schalter 'Mitschneiden' wurde nicht gemerkt."
    )

    anwendung.set_practice_record(False)

    assert StateStore(zustand).get("practice_record") is False

    print("OK: Der Schalter 'Mitschneiden' wird am Gerät gemerkt")

    # ----------------------------------------------------------------
    # 7g. Den Versuch zum Mix dazulegen
    #
    # Er liegt auf den Kanälen, auf denen er aufgenommen wurde - und
    # die stehen in seinem Namen. Genau dafür reist der Startkanal
    # mit der Datei (Stufe 1).
    # ----------------------------------------------------------------

    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()
    anwendung.music_player.aufrufe.clear()

    erfolg, meldung = anwendung.start_practice(
        "Uebung-1_p.w64", mitschnitt="Uebung-1-Take2_s9.w64"
    )

    assert erfolg, meldung

    ruf = anwendung.music_player.aufrufe[0]

    assert ruf["mitschnitt"] == ordner / "Uebung-1-Take2_s9.w64", (
        f"Der Spieler bekam {ruf['mitschnitt']} als Mitschnitt."
    )

    assert ruf["mitschnitt_start"] == 8, (
        f"Der Versuch soll ab Kanal {ruf['mitschnitt_start'] + 1} "
        f"liegen - aufgenommen wurde er laut Name ab Kanal 9. Ein "
        f"Kanal daneben, und er liegt auf einer fremden Spur."
    )

    #
    # Ohne Ziffer im Namen: Kanal 1, wie bei allen alten Aufnahmen.
    #
    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()
    anwendung.music_player.aufrufe.clear()

    erfolg, meldung = anwendung.start_practice(
        "Uebung-3_p9.w64", mitschnitt="Uebung-3-Take1_s.w64"
    )

    assert erfolg, meldung

    assert anwendung.music_player.aufrufe[0]["mitschnitt_start"] == 0, (
        anwendung.music_player.aufrufe[0]["mitschnitt_start"]
    )

    print("OK: Der Versuch landet auf den Kanälen aus seinem Namen")

    # ----------------------------------------------------------------
    # 7h. Was kein Mitschnitt ist, wird nicht dazugelegt
    #
    # Zwei Übungsmixe übereinander wären Brei - und eine Datei, die es
    # nicht gibt, wäre eine stille Überraschung.
    # ----------------------------------------------------------------

    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()
    anwendung.music_player.aufrufe.clear()

    erfolg, meldung = anwendung.start_practice(
        "Uebung-1_p.w64", mitschnitt="Uebung-2_p.w64"
    )

    assert not erfolg and meldung, (
        "Ein zweiter Übungsmix wurde als Mitschnitt angenommen."
    )

    erfolg, meldung = anwendung.start_practice(
        "Uebung-1_p.w64", mitschnitt="Gibtsnicht_s.w64"
    )

    assert not erfolg and meldung, (
        "Ein Mitschnitt, den es nicht gibt, wurde angenommen."
    )

    assert anwendung.music_player.aufrufe == [], (
        "Trotz Ablehnung wurde der Spieler gerufen."
    )

    print("OK: Nur wirkliche Aufnahmen werden dazugelegt")

    # ----------------------------------------------------------------
    # 7i. Jeder Mitschnitt gehört zu SEINEM Übungsmix
    #
    # Die Zuordnung steht im Dateinamen: Zu "Uebung-1_p.w64" gehören
    # "Uebung-1-Take1_s9.w64" und so fort. In der Auswahl "Dazu hören"
    # sollen nur die Versuche zum gerade gewählten Stück stehen -
    # alles andere wäre eine Liste, die mit jedem Üben länger wird und
    # in der man sucht.
    # ----------------------------------------------------------------

    zuordnung = anwendung.practice_takes()

    assert set(zuordnung) == {
        "Uebung-1_p.w64", "Uebung-2_p.w64", "Uebung-3_p9.w64"
    }, (
        f"Die Zuordnung kennt die Mixe {sorted(zuordnung)} - erwartet "
        f"waren alle drei."
    )

    assert zuordnung["Uebung-1_p.w64"] == [
        "Uebung-1-Take1_s9.w64", "Uebung-1-Take2_s9.w64"
    ], zuordnung["Uebung-1_p.w64"]

    assert zuordnung["Uebung-3_p9.w64"] == ["Uebung-3-Take1_s.w64"], (
        f"Der Mitschnitt zu Uebung-3 fehlt oder ist beim falschen Mix: "
        f"{zuordnung}"
    )

    assert zuordnung["Uebung-2_p.w64"] == [], (
        f"Zu Uebung-2 gibt es keinen Mitschnitt - trotzdem steht dort "
        f"{zuordnung['Uebung-2_p.w64']}."
    )

    #
    # Und was zu keinem Mix gehoert, gehoert in keine dieser Listen.
    #
    alle = [name for liste in zuordnung.values() for name in liste]

    for fremd in ("Soundcheck-1_s.w64", "Verwaist-Take1_s.w64",
                  "Alt-ohne-Marke.w64"):
        assert fremd not in alle, (
            f"{fremd} steht bei einem Übungsmix, obwohl es nicht dazu "
            f"gehört."
        )

    #
    # Ein Mitschnitt, dessen Mix geloescht wurde, ist wieder eine
    # gewoehnliche Aufnahme - erreichbar ueber die Soundcheck-Karte,
    # nicht verloren.
    #
    assert anwendung.ist_mitschnitt("Uebung-1-Take1_s9.w64") is True
    assert anwendung.ist_mitschnitt("Verwaist-Take1_s.w64") is False
    assert anwendung.ist_mitschnitt("Soundcheck-1_s.w64") is False
    assert anwendung.ist_mitschnitt("Uebung-1_p.w64") is False

    print("OK: Jeder Mitschnitt steht bei seinem Übungsmix - und nur dort")

    # ----------------------------------------------------------------
    # 7j. Der Versatz wird gemerkt und erreicht den Spieler
    #
    # Er ist die Laufzeit des Weges XRack -> Pult -> XRack. Von hier
    # aus lässt sie sich nicht ausrechnen: Sie hängt am Pult, an der
    # Route durch das Pult und daran, wie voll ALSA seine Puffer
    # wirklich fährt. Also wird sie gesetzt - und muss dann auch
    # ankommen.
    # ----------------------------------------------------------------

    anwendung.set_practice_offset(80)

    assert StateStore(zustand).get("practice_offset_ms") == 80, (
        "Der Versatz wurde nicht am Gerät gemerkt - nach einem Neustart "
        "müsste man ihn neu einstellen."
    )

    anwendung.music_player.playing = False
    anwendung.uebung_nachfuehren()
    anwendung.music_player.aufrufe.clear()

    erfolg, meldung = anwendung.start_practice(
        "Uebung-1_p.w64", mitschnitt="Soundcheck-2_s9.w64"
    )

    assert erfolg, meldung

    assert anwendung.music_player.aufrufe[0]["versatz"] == 0.08, (
        f"Der Spieler bekam einen Versatz von "
        f"{anwendung.music_player.aufrufe[0]['versatz']} s statt 0,08 - "
        f"in Sekunden, denn dort wird damit gespult."
    )

    #
    # Und die Grenzen: Ein negativer Versatz wäre Hellsehen, ein
    # riesiger ein Vertipper.
    #
    anwendung.set_practice_offset(-50)
    assert anwendung.practice_offset_ms == 0, anwendung.practice_offset_ms

    anwendung.set_practice_offset(99999)
    assert anwendung.practice_offset_ms == 2000, anwendung.practice_offset_ms

    anwendung.set_practice_offset(0)

    print("OK: Der Versatz wird gemerkt, begrenzt und weitergereicht")


# ====================================================================
# Teil 2: Die Karte im Browser
# ====================================================================

BROWSER_KANDIDATEN = (
    Path("/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"),
    Path("/opt/pw-browsers/chromium/chrome-linux/headless_shell"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
)


def browser_finden() -> Path | None:

    for kandidat in BROWSER_KANDIDATEN:
        if kandidat.exists():
            return kandidat

    return None


BROWSER = browser_finden()

if BROWSER is None:
    print("ÜBERSPRUNGEN: kein Browser gefunden - die Karte wird nicht geprüft.")
    print("Alle Tests der Üben-Karte erfolgreich.")
    sys.exit(0)


from jinja2 import ChainableUndefined, Environment, FileSystemLoader  # noqa: E402


def stand(**felder) -> dict:
    """
    So sieht /api/status aus - aus dem echten Modell gebaut.

    Aus dem Modell und nicht von Hand: Ein Feld, das XRack liefert und
    der Test nicht kennt, fiele sonst niemandem auf.
    """

    daten = json.loads(SystemStatus().model_dump_json())

    grundlage = {
        "audio": True,
        "audio_connected": True,
        "audio_device": "XR18",
        "audio_channels": 18,
        "audio_sample_rate": 48000,
        "selected_audio_device": "hw:1,0",
        "recorder": "idle",
        "hostname": "xrack",
        "uptime": "5 min",
    }

    daten.update(grundlage)
    daten.update(felder)

    return daten


def seite_bauen(daten: dict, vorlauf: str, pruefung: str) -> str:
    """Echte Vorlage, echtes Bootstrap, echtes xrack.js."""

    umgebung = Environment(
        loader=FileSystemLoader(str(WURZEL / "web" / "templates")),
        undefined=ChainableUndefined,
    )

    umgebung.globals["url_for"] = lambda *args, **kwargs: "#"

    inhalt = umgebung.get_template("index.html").render(
        t=TEXTE,
        status={},
        translations_json=json.dumps(TEXTE),
        language="de",
    )

    bootstrap = (WURZEL / "web/static/js/bootstrap.bundle.min.js").read_text(
        encoding="utf-8"
    )
    xrack = (WURZEL / "web/static/js/xrack.js").read_text(encoding="utf-8")

    #
    # Das echte Aussehen, nicht nur die Struktur: Ohne die Stilvorlagen
    # steht jedes Element untereinander, und eine Karte, aus der der
    # Positionsregler unten herausfaellt, faellt nicht auf.
    #
    stil = (
        (WURZEL / "web/static/css/bootstrap.min.css").read_text(encoding="utf-8")
        + (WURZEL / "web/static/css/xrack.css").read_text(encoding="utf-8")
    )

    #
    # Die Netzwerkaufrufe werden nachgestellt UND mitgeschrieben: Was
    # ein Knopf schickt, ist die halbe Prüfung.
    #
    vorspann = (
        "<script>window.I18N = " + json.dumps(TEXTE) + ";\n"
        "window.__posts = [];\n"
        "window.__rufe = [];\n"
        "window.__gets = [];\n"
        "window.fetch = async (url, optionen) => {\n"
        "  window.__rufe.push(String(url));\n"
        "  if (!optionen || !optionen.method || optionen.method === 'GET')\n"
        "    window.__gets.push(String(url));\n"
        "  if (optionen && optionen.method === 'POST')\n"
        "    window.__posts.push({ url: String(url),\n"
        "      body: optionen.body ? JSON.parse(optionen.body) : null });\n"
        "  if (String(url).indexOf('/api/status') === 0)\n"
        "    return { ok: true, json: async () => ("
        + json.dumps(daten) + ") };\n"
        "  if (String(url).indexOf('/api/audio/devices') === 0)\n"
        "    return { ok: true, json: async () => ([]) };\n"
        #
        # Die Zusammenfuehrung laeuft im Hintergrund; die Oberflaeche
        # fragt nach, bis sie fertig ist. Hier ist sie sofort fertig -
        # sonst wartete der Versuch bis zur Frist.
        #
        "  if (String(url).indexOf('/api/recordings/combine/status') === 0)\n"
        "    return { ok: true, json: async () => ({ active: false,\n"
        "      success: true, filename: 'Fertig-1_p.w64', error: '' }) };\n"
        "  return { ok: true, json: async () => ({ success: true }) };\n"
        "};\n"
        "window.alert = (text) => { window.__alert = String(text); };\n"
        "window.prompt = (text, vorschlag) => {\n"
        "  window.__prompt = String(text);\n"
        "  window.__vorschlag = String(vorschlag);\n"
        "  return window.__antwort === undefined\n"
        "    ? String(vorschlag) : window.__antwort; };\n"
        "window.confirm = (text) => { window.__frage = String(text);\n"
        "  return true; };\n"
        "</script>"
    )

    #
    # Der Vorlauf drückt Knöpfe, nachdem die Karte einmal gefüllt
    # wurde; geprüft wird danach.
    #
    #
    # Der Vorlauf laeuft in einer ASYNC-Funktion: Manche Knoepfe warten
    # auf eine Antwort (etwa das Zusammenfuehren von Mix und
    # Mitschnitt), und ohne "await" muesste der Versuch raten, wann er
    # messen darf.
    #
    nachspann = (
        "<script>setTimeout(async () => { try { " + vorlauf + " }\n"
        "  catch (e) { window.__vorlauffehler = String(e); } }, 500);\n"
        "setTimeout(() => {\n"
        "  const ergebnis = (() => { try { return (" + pruefung + ")(); }\n"
        "    catch (e) { return { fehler: String(e) }; } })();\n"
        "  if (window.__vorlauffehler)\n"
        "    ergebnis.vorlauffehler = window.__vorlauffehler;\n"
        "  document.getElementById('pruefergebnis').textContent =\n"
        "    'ERGEBNIS' + JSON.stringify(ergebnis) + 'ENDE';\n"
        "}, 1100);</script>"
    )

    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        + "<style>" + stil + "</style></head><body>"
        + inhalt
        + vorspann
        + "<script>" + bootstrap + "</script>"
        + "<script>" + xrack + "</script>"
        + "<div id=\"pruefergebnis\"></div>"
        + nachspann
        + "</body></html>"
    )


def ausfuehren(daten: dict, pruefung: str, vorlauf: str = "") -> dict:
    """
    Lädt die Seite und liefert, was das Prüfskript geschrieben hat.

    Gemessen wird an Eigenschaften (button.disabled, classList), nicht
    am ausgegebenen HTML: Was JavaScript setzt, steht dort teils gar
    nicht.
    """

    with tempfile.TemporaryDirectory() as tmp:

        datei = Path(tmp) / "seite.html"

        datei.write_text(
            seite_bauen(daten, vorlauf, pruefung),
            encoding="utf-8",
        )

        lauf = subprocess.run(
            [
                str(BROWSER),
                "--no-sandbox",
                "--disable-gpu",
                #
                # Breit genug fuer das zweispaltige Raster (ab 992px):
                # Nur dort teilen sich Spieler- und Bluetooth-Karte
                # die Hoehe der Recorder-Karte, und nur dort kann der
                # Positionsregler aus der Karte fallen.
                #
                "--window-size=1400,900",
                "--virtual-time-budget=6000",
                "--dump-dom",
                f"file://{datei}",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

    dom = lauf.stdout

    assert "ERGEBNIS" in dom, (
        "Das Prüfskript hat nichts geschrieben - vermutlich ein Fehler beim "
        "Laden von xrack.js:\n" + lauf.stderr[-2000:]
    )

    ergebnis = json.loads(dom.split("ERGEBNIS", 1)[1].split("ENDE", 1)[0])

    assert "fehler" not in ergebnis, ergebnis["fehler"]

    assert "vorlauffehler" not in ergebnis, ergebnis["vorlauffehler"]

    return ergebnis


KARTE = """function () {

    const sichtbar = (id) => {
        const e = document.getElementById(id);
        return e ? !e.classList.contains('d-none') : null;
    };

    const knopf = (id) => {
        const k = document.getElementById(id);
        return k ? {
            gesperrt: k.disabled,
            grund: k.title || '',
            aktiv: k.classList.contains('active'),
            text: (k.textContent || '').trim()
        } : null;
    };

    const feld = (id) => {
        const e = document.getElementById(id);
        if (!e) return null;
        return {
            werte: Array.from(e.options || []).map((o) => o.value),
            gewaehlt: e.value,
            gesperrt: e.disabled
        };
    };

    const schalter = document.getElementById('practice-repeat');
    const aufnahme = document.getElementById('practice-record');
    const hinweis = document.getElementById('practice-hint');

    //
    // Liegt der Positionsregler noch INNERHALB der Karte? Gemessen,
    // nicht geraten: Ob etwas unten herausfaellt, sieht man dem HTML
    // nicht an.
    //
    const karte = document.getElementById('player-head-music')
        .closest('.card');
    const regler = document.getElementById('music-seek');

    const k = karte.getBoundingClientRect();
    const r = regler.getBoundingClientRect();

    return {
        titel: (document.getElementById('player-title-text')
                .textContent || '').trim(),
        kopf_musik: sichtbar('player-head-music'),
        kopf_ueben: sichtbar('player-head-practice'),
        knopf_musik: knopf('btn-mode-music'),
        knopf_ueben: knopf('btn-mode-practice'),
        mixe: feld('practice-mix'),
        takes: feld('practice-take'),
        versatz: (() => {
            const e = document.getElementById('practice-offset');
            return e ? { wert: e.value, gesperrt: e.disabled } : null;
        })(),
        kanalfeld: document.getElementById('practice-channels'),
        schleife: schalter ? schalter.checked : null,
        mitschnitt: aufnahme ? {
            an: aufnahme.checked,
            gesperrt: aufnahme.disabled,
            grund: aufnahme.title || ''
        } : null,
        transport: knopf('btn-music-stop'),
        lautstaerke: sichtbar('player-fader-music'),
        hinweis: hinweis ? (hinweis.textContent || '').trim() : '',
        ueberstand: Math.round(r.bottom - k.bottom),
        posts: window.__posts.filter(
            (p) => p.url.indexOf('/api/status') !== 0),
        regler_kanal: (typeof pairFaders !== 'undefined'
            ? pairFaders.music.start : null),
        regler: window.__rufe.filter(
            (u) => u.indexOf('/api/console/pair') === 0)
    };
}"""

MIXE = ["Uebung-Bach_p.w64", "Uebung-Blues_p9.w64"]

#
# Die Mitschnitte gehoeren zu ihrem Mix - so kommt die Zuordnung auch
# aus dem Status (siehe Application.practice_takes).
#
TAKES = {
    "Uebung-Bach_p.w64": ["Uebung-Bach-Take1_s9.w64"],
    "Uebung-Blues_p9.w64": [
        "Uebung-Blues-Take1_s.w64",
        "Uebung-Blues-Take2_s.w64",
    ],
}


# ====================================================================
# 8. Auf "Musik" zeigt die Karte den Musikspieler
#
# Der Gegenfall zählt: Ein Umschalter, der immer dasselbe zeigt, wäre
# schlimmer als keiner.
# ====================================================================

musik = ausfuehren(stand(player_mode="music", practice_mixes=MIXE), KARTE)

assert musik["kopf_musik"] is True, "Der Musikkopf fehlt auf 'Musik'."

assert musik["kopf_ueben"] is False, (
    "Der Üben-Kopf steht auch auf 'Musik' da - dann sieht man beide "
    "Quellen gleichzeitig, und die Karte verspricht etwas, was das "
    "Interface nicht kann."
)

assert musik["titel"] == TEXTE["music_player_title"], musik["titel"]

assert musik["knopf_musik"]["aktiv"] and not musik["knopf_ueben"]["aktiv"], (
    "Am Umschalter ist nicht zu sehen, wo man gerade steht."
)

assert not musik["knopf_ueben"]["gesperrt"], (
    "Es lässt sich nicht auf Üben umschalten, obwohl nichts läuft."
)

assert musik["lautstaerke"] is True, (
    "Der Schnellregler fehlt beim Musikspieler - dort gehört er hin."
)

assert musik["transport"]["text"] == TEXTE["btn_stop"], (
    f"Der Transportknopf heisst auf 'Musik' {musik['transport']['text']!r} "
    f"- dort ist und bleibt er der Stop-Knopf."
)

print("OK: Auf 'Musik' zeigt die Karte den Musikspieler")


# ====================================================================
# 9. Auf "Üben" wird der Kopf getauscht - und gefüllt
#
# Getauscht wird nur der Kopf: Transport, Angaben und Positionsregler
# sind für beide dasselbe, es ist ja derselbe Spieler.
#
# Was NICHT mitkommt, ist der Schnellregler: Ein Übungsmix liegt auf
# so vielen Kanälen, wie er Spuren hat - ein Stereoregler passt
# darauf nicht. Man verstellte den Pegel eines Paares und wunderte
# sich, warum nur ein Teil leiser wird.
# ====================================================================

ueben = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        practice_repeat=True,
    ),
    KARTE,
)

assert ueben["kopf_ueben"] is True, "Der Üben-Kopf fehlt auf 'Üben'."

assert ueben["kopf_musik"] is False, (
    "Der Musikkopf steht auch auf 'Üben' noch da."
)

assert ueben["titel"] == TEXTE["practice_title"], ueben["titel"]

assert ueben["mixe"]["werte"] == MIXE, (
    f"In der Auswahl stehen {ueben['mixe']['werte']} statt {MIXE}."
)

assert ueben["schleife"] is True, (
    "Der Schleifenschalter steht auf aus, obwohl er am Gerät an ist."
)

assert ueben["lautstaerke"] is False, (
    "Der Schnellregler steht auch beim Üben da. Er regelt ein einziges "
    "Stereopaar - beim Übungsmix wäre das ein Achtel des Tons, und "
    "warum es nicht leiser wird, sieht man dem Regler nicht an."
)

assert ueben["kanalfeld"] is None, (
    "In der Üben-Karte steht wieder ein Kanalfeld. Auf welchen Kanälen "
    "ein Mix liegt, steht in seinem Namen - ein Feld daneben kann dem "
    "nur widersprechen."
)

print("OK: Auf 'Üben' steht der Üben-Kopf da, ohne Regler und ohne Kanalfeld")


# ====================================================================
# 10. Die Karte liest vor, wo der Mix landet
#
# Nicht wählen, nur anzeigen: Das Feld von früher bot Stereopaare an
# ("Kanal 1+2"), während ein Übungsmix acht Kanäle belegen kann - es
# hat also gelogen. Der Name weiss es besser.
# ====================================================================

assert ueben["hinweis"] == TEXTE["practice_hint"].replace("{a}", "1"), (
    f"Zu 'Uebung-Bach_p.w64' steht da {ueben['hinweis']!r} - ohne "
    f"Ziffer im Namen ist es Kanal 1."
)

gewaehlt = ausfuehren(
    stand(player_mode="practice", practice_mixes=MIXE),
    KARTE,
    vorlauf=(
        "const f = document.getElementById('practice-mix');"
        "f.value = 'Uebung-Blues_p9.w64';"
        "f.dispatchEvent(new Event('change'));"
    ),
)

assert gewaehlt["hinweis"] == TEXTE["practice_hint"].replace("{a}", "9"), (
    f"Zu 'Uebung-Blues_p9.w64' steht da {gewaehlt['hinweis']!r} - im "
    f"Namen steht Kanal 9."
)

print("OK: Die Karte liest den Kanal aus dem Namen vor")


# ====================================================================
# 11. Gestartet wird mit dem Transportknopf
#
# Ein eigener Startknopf stand vorher oben in der Karte - das ist
# zweierlei Bedienung für eine Sache. XRack macht es überall so: EIN
# Knopf startet und stoppt.
# ====================================================================

assert ueben["transport"]["text"] == TEXTE["btn_practice"], (
    f"Der Transportknopf heisst beim Üben {ueben['transport']['text']!r} "
    f"- solange nichts läuft, ist er der Startknopf."
)

assert not ueben["transport"]["gesperrt"], (
    "Der Startknopf ist gesperrt, obwohl ein Mix da und alles frei ist."
)

leer = ausfuehren(stand(player_mode="practice", practice_mixes=[]), KARTE)

assert leer["transport"]["gesperrt"], (
    "Ohne einen einzigen Übungsmix lässt sich 'Üben' drücken - der "
    "Knopf tut dann nichts, und das ist schlimmer als ein gesperrter."
)

assert leer["hinweis"] == TEXTE["practice_none"], leer["hinweis"]

laeuft_mix = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        music_playing=True,
        music_track="Uebung-Bach_p.w64",
    ),
    KARTE,
)

assert laeuft_mix["transport"]["text"] == TEXTE["btn_stop"], (
    f"Während das Üben läuft, heisst der Knopf "
    f"{laeuft_mix['transport']['text']!r} - dann muss er Stop heissen, "
    f"sonst gibt es keinen Weg zurück."
)

assert not laeuft_mix["transport"]["gesperrt"], (
    "Der Stop-Knopf ist während des Übens gesperrt - dann lässt es "
    "sich nicht beenden."
)

print("OK: Ein Knopf startet und stoppt das Üben")


# ====================================================================
# 12. Während der Wiedergabe ist der Umschalter zu
#
# Die Karte tauscht beim Umschalten ihre Quelle aus. Ein Umschalten
# mitten in der Wiedergabe wäre eine Falle - man drückt auf "Musik",
# und der Übungsmix läuft weiter. Der Server lehnt es ebenfalls ab
# (siehe Teil 1); hier steht der sichtbare Teil derselben Regel.
# ====================================================================

for name in ("knopf_musik", "knopf_ueben"):

    assert laeuft_mix[name]["gesperrt"], (
        f"Der Umschalter ({name}) lässt sich während der Wiedergabe "
        f"drücken - der Server lehnt ab, und für den Nutzer sieht es "
        f"aus, als sei XRack kaputt."
    )

    assert laeuft_mix[name]["grund"] == TEXTE["practice_busy"], (
        f"Am gesperrten Umschalter steht kein Grund: "
        f"{laeuft_mix[name]['grund']!r}"
    )

pausiert = ausfuehren(
    stand(player_mode="practice", practice_mixes=MIXE, music_paused=True),
    KARTE,
)

assert pausiert["knopf_musik"]["gesperrt"], (
    "Im Pausenzustand lässt sich umschalten - die Quelle ist noch "
    "offen, und die Pause gehört zu einem Stück, das noch läuft."
)

print("OK: Umgeschaltet wird nur, wenn wirklich nichts läuft")


# ====================================================================
# 13. Der Üben-Knopf schickt, was in den Feldern steht
#
# Ein Wert, der zwischen Feld und Aufruf verlorengeht, fällt sonst
# erst am Pult auf.
# ====================================================================

geschickt = ausfuehren(
    stand(player_mode="practice", practice_mixes=MIXE, practice_takes=TAKES),
    KARTE,
    vorlauf=(
        #
        # Erst das Stueck, DANN der Versuch: Die Liste der Versuche
        # haengt am gewaehlten Stueck und wird erst dabei aufgebaut.
        #
        "const m = document.getElementById('practice-mix');"
        "m.value = 'Uebung-Blues_p9.w64';"
        "m.dispatchEvent(new Event('change'));"
        "document.getElementById('practice-repeat').checked = true;"
        "document.getElementById('practice-record').checked = true;"
        "document.getElementById('practice-take').value ="
        "  'Uebung-Blues-Take2_s.w64';"
        "document.getElementById('btn-music-stop').click();"
    ),
)

starts = [p for p in geschickt["posts"] if p["url"] == "/api/practice/start"]

assert len(starts) == 1, (
    f"Der Üben-Knopf schickte {len(starts)} Aufrufe an "
    f"/api/practice/start: {geschickt['posts']}"
)

assert starts[0]["body"] == {
    "filename": "Uebung-Blues_p9.w64",
    "repeat": True,
    "record": True,
    "take": "Uebung-Blues-Take2_s.w64",
}, (
    f"Geschickt wurde {starts[0]['body']} - das ist nicht, was in den "
    f"Feldern stand. (Ein Kanal gehört NICHT dazu: Der steht im Namen.)"
)

print("OK: Der Üben-Knopf schickt Datei und Schleife - und keinen Kanal")


# ====================================================================
# 13b. Mitschneiden: der Schalter und was er nach sich zieht
#
# Aufgenommen wird das Fenster aus der Soundcheck-Karte. Welche Kanäle
# das sind, muss dranstehen: Ein Mitschnitt, von dem man nicht weiss,
# was darauf ist, ist keiner.
# ====================================================================

mit_aufnahme = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        practice_record=True,
        record_start_channel=9,
        record_channels=2,
    ),
    KARTE,
)

assert mit_aufnahme["mitschnitt"]["an"] is True, (
    "Der Schalter steht auf aus, obwohl er am Gerät an ist."
)

assert not mit_aufnahme["mitschnitt"]["gesperrt"], (
    "Der Schalter ist gesperrt, obwohl ein Interface offen ist."
)

erwartet = " · ".join((
    TEXTE["practice_hint"].replace("{a}", "1"),
    TEXTE["practice_record_hint"].replace("{a}", "9").replace("{b}", "10"),
))

assert mit_aufnahme["hinweis"] == erwartet, (
    f"Im Hinweis steht {mit_aufnahme['hinweis']!r} - dort gehört hin, "
    f"welche Kanäle mitgeschnitten werden: {erwartet!r}"
)

#
# Und ohne Interface: zu, mit Begründung. Ein Schalter, der sich
# umlegen lässt und nichts bewirkt, ist schlimmer als ein gesperrter.
#
ohne_geraet = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        audio=False,
        audio_channels=0,
        recorder="no_device",
    ),
    KARTE,
)

assert ohne_geraet["mitschnitt"]["gesperrt"], (
    "Ohne Interface lässt sich 'Mitschneiden' einschalten - dann liefe "
    "der Übungsmix, und den Mitschnitt gäbe es nicht."
)

assert ohne_geraet["mitschnitt"]["grund"] == TEXTE[
    "practice_record_no_device"
], ohne_geraet["mitschnitt"]["grund"]

print("OK: Der Mitschnitt-Schalter sagt, was er aufnimmt - und wann nicht")


# ====================================================================
# 13d. "Dazu hören": die Auswahl der Versuche
#
# Angeboten wird jede Aufnahme, aber kein Übungsmix - zwei Mixe
# übereinander wären Brei. Und obenan steht "nichts": Der Normalfall
# ist, ohne Versuch zu üben.
# ====================================================================

dazu = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        practice_takes=TAKES,
    ),
    KARTE,
)

assert dazu["takes"]["werte"] == [""] + TAKES[MIXE[0]], (
    f"In der Auswahl stehen {dazu['takes']['werte']} - erwartet waren "
    f"'nichts' und danach die Versuche zum ERSTEN Stück."
)

#
# Und beim Wechsel des Stuecks wechselt die Liste mit. Das ist der
# Kern der Sache: Ein Versuch zu einem anderen Stueck ergibt beim
# Zusammenhoeren nur Unsinn.
#
gewechselt = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        practice_takes=TAKES,
    ),
    KARTE,
    vorlauf=(
        "const m = document.getElementById('practice-mix');"
        "m.value = 'Uebung-Blues_p9.w64';"
        "m.dispatchEvent(new Event('change'));"
    ),
)

assert gewechselt["takes"]["werte"] == [""] + TAKES["Uebung-Blues_p9.w64"], (
    f"Nach dem Wechsel des Stücks stehen in der Auswahl "
    f"{gewechselt['takes']['werte']} - dort gehören die Versuche zum "
    f"NEUEN Stück hin."
)

assert dazu["takes"]["gewaehlt"] == "", (
    "Vorbelegt ist ein Versuch - der Normalfall ist, ohne zu üben."
)

#
# Ist einer gewählt, sagt die Karte es: Sonst übt man gegen einen
# Versuch, von dem man nichts weiss.
#
gewaehlt = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        practice_takes=TAKES,
    ),
    KARTE,
    vorlauf=(
        "const f = document.getElementById('practice-take');"
        "f.value = 'Uebung-Bach-Take1_s9.w64';"
        "f.dispatchEvent(new Event('change'));"
    ),
)

assert TEXTE["practice_take_hint"].replace(
    "{name}", TEXTE["practice_take_short"].replace("{nr}", "1")
) in gewaehlt["hinweis"], (
    f"Im Hinweis steht {gewaehlt['hinweis']!r} - dort gehört hin, "
    f"welcher Versuch mitläuft."
)

print("OK: Die Auswahl 'Dazu hören' bietet Aufnahmen an, keine Mixe")


# ====================================================================
# 13e. Der Versatz steht in der Karte und geht ans Gerät
#
# Er ist die Laufzeit durch das Pult. Ausrechnen lässt sie sich nicht,
# also stellt man sie ein - nach Gehör oder nach einer Messung. Dann
# muss der Wert aber auch dastehen und ankommen.
# ====================================================================

mit_versatz = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        practice_takes=TAKES,
        practice_offset_ms=85,
    ),
    KARTE,
    vorlauf=(
        "const f = document.getElementById('practice-take');"
        "f.value = 'Uebung-Bach-Take1_s9.w64';"
        "f.dispatchEvent(new Event('change'));"
    ),
)

assert mit_versatz["versatz"]["wert"] == "85", (
    f"Im Versatzfeld steht {mit_versatz['versatz']['wert']!r} statt 85."
)

assert TEXTE["practice_offset_hint"].replace(
    "{ms}", "85"
) in mit_versatz["hinweis"], (
    f"Im Hinweis fehlt der Versatz: {mit_versatz['hinweis']!r}"
)

geschickter_versatz = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        practice_takes=TAKES,
    ),
    KARTE,
    vorlauf=(
        "const f = document.getElementById('practice-offset');"
        "f.value = '120';"
        "f.dispatchEvent(new Event('change'));"
    ),
)

versaetze = [
    p for p in geschickter_versatz["posts"]
    if p["url"] == "/api/practice/offset"
]

assert versaetze and versaetze[0]["body"] == {"offset_ms": 120}, (
    f"Der Versatz wurde nicht ans Gerät geschickt: "
    f"{geschickter_versatz['posts']}"
)

print("OK: Der Versatz steht in der Karte und geht ans Gerät")


# ====================================================================
# 13f. Der Messknopf fragt vorher, was am Pult nötig ist
#
# XRack kann die Schleife im Pult nicht selbst herstellen, und eine
# Messung ohne sie findet nichts. Wer den Knopf drückt, muss vorher
# wissen, was er einrichten muss - sonst bekommt er nur eine
# Fehlermeldung und weiss nicht, warum.
# ====================================================================

MESSUNG = """function () {
    return {
        gefragt: window.__frage || '',
        posts: window.__posts.filter(
            (p) => p.url.indexOf('/api/status') !== 0),
        //
        // Nur die ABFRAGEN, nicht der Start: Beide gehen an dieselbe
        // Adresse, der Start aber als POST.
        //
        abfragen: window.__gets.filter(
            (u) => u.indexOf('/api/practice/latency') === 0)
    };
}"""

gemessen = ausfuehren(
    stand(player_mode="practice", practice_mixes=MIXE, practice_takes=TAKES),
    MESSUNG,
    vorlauf="document.getElementById('btn-practice-latency').click();",
)

assert gemessen["gefragt"] == TEXTE["practice_latency_confirm"], (
    f"Vor der Messung wurde nicht erklärt, was am Pult nötig ist: "
    f"{gemessen['gefragt']!r}"
)

messungen = [
    p for p in gemessen["posts"] if p["url"] == "/api/practice/latency"
]

assert messungen, (
    f"Der Messknopf hat die Messung nicht gestartet: {gemessen['posts']}"
)

assert gemessen["abfragen"], (
    "Nach dem Start wurde nicht nachgefragt, wie es steht - die "
    "Messung dauert Sekunden, das Ergebnis kommt nicht mit der "
    "Antwort auf den Start."
)

print("OK: Der Messknopf erklärt sich, startet und fragt nach")


# ====================================================================
# 13c. Beim Üben beendet der Stop-Knopf beides
#
# Nicht /api/music/stop: Das hielte den Ton an und liesse den
# Mitschnitt weiterlaufen - eine Aufnahme, die niemand mehr beendet.
# ====================================================================

beendet = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=MIXE,
        music_playing=True,
        practice_recording=True,
    ),
    KARTE,
    vorlauf="document.getElementById('btn-music-stop').click();",
)

adressen = [p["url"] for p in beendet["posts"]]

assert "/api/practice/stop" in adressen, (
    f"Der Stop-Knopf rief {adressen} - beim Üben gehört der Aufruf an "
    f"/api/practice/stop, sonst läuft der Mitschnitt weiter."
)

assert "/api/music/stop" not in adressen, (
    f"Der Stop-Knopf rief zusätzlich /api/music/stop: {adressen}"
)

#
# Der Gegenfall: Beim Musikspieler bleibt es beim alten Weg.
#
musik_beendet = ausfuehren(
    stand(player_mode="music", practice_mixes=MIXE, music_playing=True),
    KARTE,
    vorlauf="document.getElementById('btn-music-stop').click();",
)

assert "/api/music/stop" in [
    p["url"] for p in musik_beendet["posts"]
], musik_beendet["posts"]

print("OK: Beim Üben beendet der Stop-Knopf auch den Mitschnitt")


# ====================================================================
# 14. Der Umschalter schickt die Betriebsart ans Gerät
#
# Und nicht in den Browserspeicher: Was das Rack tut, soll auf jedem
# Tablet gleich aussehen.
# ====================================================================

umgeschaltet = ausfuehren(
    stand(player_mode="music", practice_mixes=MIXE),
    KARTE,
    vorlauf="document.getElementById('btn-mode-practice').click();",
)

moden = [p for p in umgeschaltet["posts"] if p["url"] == "/api/player/mode"]

assert moden and moden[0]["body"] == {"mode": "practice"}, (
    f"Der Umschalter schickte {moden} - erwartet war ein Aufruf an "
    f"/api/player/mode mit 'practice'."
)

print("OK: Der Umschalter schickt die Betriebsart ans Gerät")


# ====================================================================
# 15. Beim Üben wird kein Kanalpaar abgefragt
#
# Der Regler ist versteckt - dann hat er auch nichts zu holen. Sonst
# liefe im Hintergrund eine Abfrage je Sekunde für etwas, das niemand
# sieht.
# ====================================================================

#
# Gemessen am Zustand des Reglers, nicht an den Netzaufrufen: Das
# Bluetooth-Feld hat einen eigenen Schnellregler, der holt sein Paar
# weiterhin - die Adresse allein sagt also nicht, wer gefragt hat.
#
assert ueben["regler_kanal"] is None, (
    f"Der Schnellregler des Spielers steht beim Üben auf Kanal "
    f"{ueben['regler_kanal']}, obwohl er versteckt ist - dann läuft "
    f"im Hintergrund eine Abfrage je Sekunde für etwas, das niemand "
    f"sieht."
)

assert musik["regler_kanal"] == 1, (
    f"Beim Musikspieler steht der Schnellregler auf "
    f"{musik['regler_kanal']} statt auf dem Paar der Musik."
)

print("OK: Beim Üben fragt der versteckte Regler nichts ab")


# ====================================================================
# 16. Der Positionsregler bleibt in der Karte
#
# Er hing eine Fassung lang UNTERHALB der Karte in der Luft: Ab dem
# zweispaltigen Raster bekamen Spieler- und Bluetooth-Karte feste 2/3
# und 1/3 der Höhe (flex-basis: 0), egal wie viel darin stand. Zwei
# Zeilen mehr im Üben-Kopf, und der Inhalt lief unten heraus - ohne
# Rahmen, ohne Fehlermeldung.
#
# Gemessen wird deshalb, nicht angesehen: Die Unterkante des Reglers
# muss über der Unterkante der Karte liegen.
# ====================================================================

for bezeichnung, ergebnis in (
    ("Musik", musik),
    ("Üben", ueben),
    ("Üben, ohne Mix", leer),
):

    assert ergebnis["ueberstand"] < 0, (
        f"{bezeichnung}: Der Positionsregler steht "
        f"{ergebnis['ueberstand']} px UNTER der Karte - er hängt also "
        f"ausserhalb in der Luft."
    )

print("OK: Der Positionsregler bleibt in allen Fällen in der Karte")


# ====================================================================
# 17. "Übungsmix erstellen" kehrt in die Dateiverwaltung zurück
#
# Der Knopf sitzt dort, wo die Übungsmixe stehen - ein Übungsmix ist
# eine Datei, und Dateien macht man in der Dateiverwaltung.
# Geschlossen führt der Weg dorthin zurück: Der nächste Griff gilt
# fast immer dem eben erzeugten Mix.
# ====================================================================

DIALOG = """function () {
    const offen = (id) => {
        const e = document.getElementById(id);
        return e ? e.classList.contains('show') : null;
    };

    const kanal = document.getElementById('stem-combine-start-channel');
    const titel = document.getElementById('recordingsModalTitle');

    return {
        stems: offen('stemCombineModal'),
        dateien: offen('recordingsModal'),
        titel: titel ? titel.textContent.trim() : '',
        kanalwerte: kanal
            ? Array.from(kanal.options).map((o) => o.value) : null,
        spuren: Array.from(
            document.querySelectorAll('#stem-combine-files label')
        ).map((l) => (l.textContent || '').trim())
    };
}"""

dialog = ausfuehren(
    stand(player_mode="practice", practice_mixes=MIXE),
    DIALOG,
    vorlauf=(
        "document.getElementById('btn-practice-files').click();"
        "setTimeout(() => {"
        "  document.getElementById('btn-open-stem-combine').click();"
        "  setTimeout(() => bootstrap.Modal.getOrCreateInstance("
        "    document.getElementById('stemCombineModal')).hide(), 200);"
        "}, 200);"
    ),
)

assert dialog["dateien"] is True, (
    "Nach dem Schliessen des Übungsmix-Dialogs steht die "
    "Dateiverwaltung nicht wieder offen - von dort kam man, und dort "
    "steht der eben erzeugte Mix."
)

assert dialog["titel"] == TEXTE["modal_practice_files_title"], (
    f"Der Dialog kehrt in die falsche Betriebsart zurück: "
    f"{dialog['titel']!r}"
)

print("OK: Der Übungsmix-Dialog kehrt in die Dateiverwaltung zurück")


# ====================================================================
# 18. Im Erstellen-Dialog wird der erste Kanal gewählt
#
# Hier gehört die Wahl hin und nicht in die Üben-Karte: Ein Übungsmix
# wird für einen Platz im Pult gebaut, und dorthin gehört er beim
# nächsten Mal wieder.
#
# Die Beschriftung der Dateizeilen muss mitgehen. Stünde dort weiter
# "Kanal 1+2", während der Mix ab Kanal 9 liegt, wäre der Dialog eine
# Anleitung zum Falschladen.
# ====================================================================

erstellen = ausfuehren(
    stand(player_mode="practice", practice_mixes=MIXE, audio_channels=18),
    DIALOG,
    vorlauf=(
        "document.getElementById('btn-practice-files').click();"
        "setTimeout(() => {"
        "  document.getElementById('btn-open-stem-combine').click();"
        "  const k = document.getElementById('stem-combine-start-channel');"
        "  k.value = '9';"
        "  k.dispatchEvent(new Event('change'));"
        "}, 250);"
    ),
)

assert erstellen["kanalwerte"] == [
    "1", "3", "5", "7", "9", "11", "13", "15", "17"
], (
    f"Angeboten werden {erstellen['kanalwerte']} - erwartet waren nur "
    f"ungerade Kanäle: Jeder Stem ist ein Stereopaar, ab einem geraden "
    f"Kanal läge jedes Paar quer über zwei Paare des Pults."
)

erwartet = [
    TEXTE["stem_combine_channel_label"]
    .replace("{a}", str(a)).replace("{b}", str(a + 1))
    for a in (9, 11)
]

assert erstellen["spuren"] == erwartet, (
    f"Die Dateizeilen heissen {erstellen['spuren']} statt {erwartet} - "
    f"ab Kanal 9 liegt die erste Datei auf 9+10, nicht auf 1+2."
)

print("OK: Der Erstellen-Dialog wählt den Kanal und beschriftet danach")


# ====================================================================
# 19. In "Alle Dateien" führt der Übungsmix zum Üben
#
# Derselbe Griff wie früher, nur ans richtige Ziel: Der Knopf hiess
# "für den Soundcheck auswählen" und spielte den Mix dann über den
# Soundcheck-Spieler ab - der kann weder anhalten noch spulen. Zum
# Üben ist genau das nötig.
# ====================================================================

#
# Ein Dialog, zwei Betriebsarten: Von der Soundcheck-Karte aus die
# Aufnahmen, von der Üben-Karte aus die Übungsmixe samt ihren
# Mitschnitten. Was in der einen steht, hat in der anderen nichts zu
# suchen - sonst sucht man jedes Mal in einer Liste, die zur Hälfte
# aus dem Falschen besteht.
#

DATEIEN = ["""
    //
    // Die echte Anzeigefunktion mit einer Liste, wie sie der Server
    // liefert.
    //
    const liste = [
        { filename: 'Uebung-Bach_p.w64', kind: 'practice', channels: 8,
          sample_rate: 48000, bits_per_sample: 24, duration: 60, size: 1 },
        { filename: 'Uebung-Bach-Take1_s9.w64', kind: 'soundcheck',
          channels: 2, sample_rate: 48000, bits_per_sample: 24,
          duration: 60, size: 1 },
        { filename: 'Soundcheck-7_s9.w64', kind: 'soundcheck', channels: 2,
          sample_rate: 48000, bits_per_sample: 24, duration: 60, size: 1 }
    ];
""", """
    const aktionen = (name) => Array.from(
        document.querySelectorAll(
            `#recordingsList [data-filename="${name}"]`)
    ).map((k) => k.dataset.action);

    const eingerueckt = (name) => {
        const k = document.querySelector(
            `#recordingsList [data-filename="${name}"]`);
        const karte = k ? k.closest('.card') : null;
        return karte ? karte.classList.contains('ms-4') : null;
    };

    return {
        mix: aktionen('Uebung-Bach_p.w64'),
        take: aktionen('Uebung-Bach-Take1_s9.w64'),
        aufnahme: aktionen('Soundcheck-7_s9.w64'),
        take_eingerueckt: eingerueckt('Uebung-Bach-Take1_s9.w64'),
        titel: document.getElementById('recordingsModalTitle')
                   .textContent.trim()
    };
"""]

UEBEN_LISTE = (
    "function () {"
    + DATEIEN[0]
    + "dateienModus = 'practice'; renderRecordings(liste);"
    + DATEIEN[1]
    + "}"
)

SOUNDCHECK_LISTE = (
    "function () {"
    + DATEIEN[0]
    + "dateienModus = 'soundcheck'; renderRecordings(liste);"
    + DATEIEN[1]
    + "}"
)

ZUORDNUNG = {"Uebung-Bach_p.w64": ["Uebung-Bach-Take1_s9.w64"]}

ueben_liste = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=["Uebung-Bach_p.w64"],
        practice_takes=ZUORDNUNG,
    ),
    UEBEN_LISTE,
)

assert "practice" in ueben_liste["mix"], (
    f"Am Übungsmix stehen die Aktionen {ueben_liste['mix']} - dort "
    f"gehört 'zum Üben auswählen' hin."
)

assert "choose" not in ueben_liste["mix"], (
    f"Am Übungsmix steht weiterhin 'für den Soundcheck auswählen': "
    f"{ueben_liste['mix']}. Damit gäbe es den Weg zweimal, und der "
    f"über den Soundcheck kann weder anhalten noch spulen."
)

assert "listen" in ueben_liste["take"], (
    f"Am Mitschnitt stehen die Aktionen {ueben_liste['take']} - dort "
    f"gehört 'zum Dazuhören auswählen' hin."
)

assert ueben_liste["take_eingerueckt"] is True, (
    "Der Mitschnitt steht nicht eingerückt unter seinem Übungsmix - "
    "dass er dazugehört, müsste man am Namen ablesen."
)

assert ueben_liste["aufnahme"] == [], (
    f"In der Üben-Verwaltung steht eine gewöhnliche Aufnahme: "
    f"{ueben_liste['aufnahme']}"
)

print("OK: Die Üben-Verwaltung zeigt Mixe mit ihren Mitschnitten")


# ====================================================================
# 19b. Und die Soundcheck-Verwaltung zeigt weder das eine noch das
#      andere
#
# Der Gegenfall zählt: Eine Verwaltung, die weiterhin alles zeigt,
# wäre keine Trennung.
# ====================================================================

soundcheck_liste = ausfuehren(
    stand(
        player_mode="practice",
        practice_mixes=["Uebung-Bach_p.w64"],
        practice_takes=ZUORDNUNG,
    ),
    SOUNDCHECK_LISTE,
)

assert "choose" in soundcheck_liste["aufnahme"], (
    f"An der Aufnahme fehlt 'für den Soundcheck auswählen': "
    f"{soundcheck_liste['aufnahme']}"
)

assert soundcheck_liste["mix"] == [], (
    f"Der Übungsmix steht weiterhin in der Soundcheck-Verwaltung: "
    f"{soundcheck_liste['mix']}"
)

assert soundcheck_liste["take"] == [], (
    f"Der Mitschnitt steht in der Soundcheck-Verwaltung: "
    f"{soundcheck_liste['take']}. Nach ein paar Übungsabenden wären "
    f"die Versuche dort die Mehrheit, und der Soundcheck fände sich "
    f"zwischen ihnen nicht wieder."
)

print("OK: Die Soundcheck-Verwaltung zeigt weder Mixe noch Mitschnitte")


# ====================================================================
# 20. Und der Griff landet wirklich in der Üben-Karte
#
# Umschalten, Dialog zu, Mix vorgewählt - sonst stünde man vor einer
# Karte und müsste die Datei noch einmal suchen.
# ====================================================================

ZIEL = """function () {
    const auswahl = document.getElementById('practice-mix');
    return {
        gewaehlt: auswahl ? auswahl.value : null,
        posts: window.__posts.filter(
            (p) => p.url.indexOf('/api/status') !== 0),
        dateien: document.getElementById('recordingsModal')
            .classList.contains('show')
    };
}"""

ziel = ausfuehren(
    stand(player_mode="music", practice_mixes=MIXE),
    ZIEL,
    vorlauf="waehleUebungsmix('Uebung-Blues_p9.w64');",
)

moden = [p for p in ziel["posts"] if p["url"] == "/api/player/mode"]

assert moden and moden[0]["body"] == {"mode": "practice"}, (
    f"Der Griff schaltete nicht auf Üben um: {ziel['posts']}"
)

assert ziel["gewaehlt"] == "Uebung-Blues_p9.w64", (
    f"In der Üben-Karte steht {ziel['gewaehlt']!r} - vorgewählt sein "
    f"muss der Mix, den man gerade angetippt hat."
)

assert ziel["dateien"] is False, (
    "Der Dialog 'Alle Dateien' steht noch offen - man sieht die Karte "
    "gar nicht, in der es weitergeht."
)

print("OK: Der Griff schaltet um, wählt vor und schliesst den Dialog")


# ====================================================================
# Stufe 5: aus Mix und Mitschnitt eine Datei
#
# Zum Anhören braucht es das nicht - dafür legt XRack beides in
# denselben Wiedergabestrom, ohne etwas zu schreiben. Sitzt ein Versuch
# aber, will man ihn mitnehmen: auf den Stick, ins Backup, auf ein
# anderes XRack.
#
# Der Knopf gehört deshalb neben die Auswahl des Mitschnitts, und er
# darf nur dann gehen, wenn einer gewählt ist.
# ====================================================================

ZUSAMMEN = """function () {

    const knopf = document.getElementById('btn-practice-merge');

    return {
        da: !!knopf,
        gesperrt: knopf ? knopf.disabled : null,
        frage: window.__prompt || '',
        vorschlag: window.__vorschlag || '',
        alarm: window.__alert || '',
        posts: window.__posts.filter(
            (p) => p.url.indexOf('/api/status') !== 0)
    };
}"""

#
# a) Ohne gewählten Mitschnitt gibt es nichts zusammenzuführen.
#
ohne = ausfuehren(
    stand(player_mode="practice", practice_mixes=MIXE, practice_takes=TAKES),
    ZUSAMMEN,
)

assert ohne["da"] is True, "Der Knopf zum Zusammenführen fehlt."

assert ohne["gesperrt"] is True, (
    "Ohne gewählten Mitschnitt lässt sich zusammenführen - was denn?"
)

#
# b) Mit Mitschnitt: Der Knopf geht, fragt nach einem Namen und
#    schickt beide Dateien.
#
zusammen = ausfuehren(
    stand(player_mode="practice", practice_mixes=MIXE, practice_takes=TAKES),
    ZUSAMMEN,
    vorlauf=(
        "const m = document.getElementById('practice-mix');"
        "m.value = 'Uebung-Blues_p9.w64';"
        "m.dispatchEvent(new Event('change'));"
        "document.getElementById('practice-take').value ="
        "  'Uebung-Blues-Take2_s.w64';"
        #
        # Der Knopf wird beim Auffrischen freigegeben - also erst
        # auffrischen lassen, dann druecken.
        #
        "await updateStatus();"
        "document.getElementById('btn-practice-merge').click();"
    ),
)

fuehrungen = [
    p for p in zusammen["posts"]
    if p["url"] == "/api/recordings/combine-take"
]

assert len(fuehrungen) == 1, (
    f"Der Knopf schickte {len(fuehrungen)} Aufrufe an "
    f"/api/recordings/combine-take: {zusammen['posts']}"
)

geschickt = fuehrungen[0]["body"]

assert geschickt["mix"] == "Uebung-Blues_p9.w64", geschickt

assert geschickt["take"] == "Uebung-Blues-Take2_s.w64", (
    f"Geschickt wurde der Mitschnitt {geschickt['take']!r} - gewählt "
    f"war ein anderer."
)

#
# Der Name wird VORGESCHLAGEN, nicht erfragt-und-vergessen: Er nennt
# Stück und Versuch, denn genau daran erkennt man die Datei später auf
# dem Stick wieder.
#
assert "Uebung-Blues" in zusammen["vorschlag"], (
    f"Der Namensvorschlag nennt das Stück nicht: "
    f"{zusammen['vorschlag']!r}"
)

assert "2" in zusammen["vorschlag"], (
    f"Der Namensvorschlag nennt den Versuch nicht: "
    f"{zusammen['vorschlag']!r}"
)

assert geschickt["name"] == zusammen["vorschlag"], (
    f"Geschickt wurde {geschickt['name']!r}, im Feld stand "
    f"{zusammen['vorschlag']!r}."
)

#
# Und am Ende steht da, wie die neue Datei heißt - sonst sucht man sie
# in der Liste.
#
assert "Fertig-1_p.w64" in zusammen["alarm"], (
    f"Nach dem Zusammenführen steht kein Ergebnis da: "
    f"{zusammen['alarm']!r}"
)

print("OK: Mix und Mitschnitt lassen sich zu einer Datei zusammenführen")


print("Alle Tests der Üben-Karte erfolgreich.")
