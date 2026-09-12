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

import json
import subprocess
import sys
import tempfile
import types
from pathlib import Path

WURZEL = Path(__file__).resolve().parent

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

class Spieler:
    """Ein Musikspieler, der sich merkt, womit er gerufen wurde."""

    def __init__(self):
        self.playing = False
        self.paused = False
        self.wiederholen = False
        self.aufrufe = []

    def set_wiederholen(self, an):
        self.wiederholen = bool(an)

    def play_practice(self, device, path, start_channel, rate,
                      wiederholen=False):
        self.aufrufe.append({
            "pfad": Path(path),
            "start_channel": start_channel,
            "rate": rate,
            "wiederholen": wiederholen,
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
    def __init__(self, ordner, namen):
        self.writer = Schreiber(ordner)
        self.recordings = list(namen)


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
        "window.fetch = async (url, optionen) => {\n"
        "  window.__rufe.push(String(url));\n"
        "  if (optionen && optionen.method === 'POST')\n"
        "    window.__posts.push({ url: String(url),\n"
        "      body: optionen.body ? JSON.parse(optionen.body) : null });\n"
        "  if (String(url).indexOf('/api/status') === 0)\n"
        "    return { ok: true, json: async () => ("
        + json.dumps(daten) + ") };\n"
        "  if (String(url).indexOf('/api/audio/devices') === 0)\n"
        "    return { ok: true, json: async () => ([]) };\n"
        "  return { ok: true, json: async () => ({ success: true }) };\n"
        "};\n"
        "window.alert = (text) => { window.__alert = String(text); };\n"
        "window.confirm = () => true;\n"
        "</script>"
    )

    #
    # Der Vorlauf drückt Knöpfe, nachdem die Karte einmal gefüllt
    # wurde; geprüft wird danach.
    #
    nachspann = (
        "<script>setTimeout(() => { try { " + vorlauf + " }\n"
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
        kanalfeld: document.getElementById('practice-channels'),
        schleife: schalter ? schalter.checked : null,
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
    stand(player_mode="practice", practice_mixes=MIXE),
    KARTE,
    vorlauf=(
        "document.getElementById('practice-mix').value = 'Uebung-Blues_p9.w64';"
        "document.getElementById('practice-repeat').checked = true;"
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
}, (
    f"Geschickt wurde {starts[0]['body']} - das ist nicht, was in den "
    f"Feldern stand. (Ein Kanal gehört NICHT dazu: Der steht im Namen.)"
)

print("OK: Der Üben-Knopf schickt Datei und Schleife - und keinen Kanal")


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
# 17. Der Übungsmix-Dialog kehrt nicht in einen Dialog zurück,
#     den man nie geöffnet hat
#
# "Übungsmix erstellen" saß früher nur im Dialog "Alle Dateien" und
# ging beim Schließen dorthin zurück. Jetzt steht der Knopf auch in
# der Üben-Karte - von dort zurückzukehren hieße, dass sich
# unvermittelt die Dateiliste öffnet.
# ====================================================================

DIALOG = """function () {
    const offen = (id) => {
        const e = document.getElementById(id);
        return e ? e.classList.contains('show') : null;
    };

    const kanal = document.getElementById('stem-combine-start-channel');

    return {
        stems: offen('stemCombineModal'),
        dateien: offen('recordingsModal'),
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
        "document.getElementById('btn-practice-create').click();"
        "setTimeout(() => bootstrap.Modal.getOrCreateInstance("
        "document.getElementById('stemCombineModal')).hide(), 200);"
    ),
)

assert dialog["dateien"] is False, (
    "Nach dem Schließen des Übungsmix-Dialogs steht die Dateiliste "
    "offen - die hatte man von der Üben-Karte aus nie geöffnet."
)

print("OK: Der Übungsmix-Dialog kehrt dorthin zurück, wo er herkam")


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
        "document.getElementById('btn-practice-create').click();"
        "const k = document.getElementById('stem-combine-start-channel');"
        "k.value = '9';"
        "k.dispatchEvent(new Event('change'));"
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


print("Alle Tests der Üben-Karte erfolgreich.")
