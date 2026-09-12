#!/usr/bin/env python3
"""
Prüft die Soundcheck-Karte im echten Browser.

Anlass ist eine Meldung vom Gerät: XRack lief ohne angeschlossene
Konsole. Oben zeigte die Audio-Karte richtig ein rotes Kreuz - die
Soundcheck-Karte darunter meldete trotzdem "bereit", und der
Aufnahmeknopf ließ sich drücken.

Warum im Browser und nicht am Python-Teil: Die Karte entsteht
vollständig im JavaScript aus dem, was /api/status liefert. Dass der
Recorder inzwischen ablehnt, sieht man ihr nicht an - ein Knopf, der
sich drücken lässt und dann nichts tut, ist schlimmer als einer, der
gesperrt ist und sagt, warum. Geprüft wird deshalb der Zustand der
Knöpfe, wie der Browser sie wirklich setzt.

Hier läuft das ECHTE xrack.js, nur die Netzwerkaufrufe sind
nachgestellt.

Ohne Browser wird übersprungen statt zu scheitern - auf dem Pi ist
keiner installiert, und dort soll die Testreihe durchlaufen.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent

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
    sys.exit(0)


from jinja2 import ChainableUndefined, Environment, FileSystemLoader  # noqa: E402

from web.i18n import get_translations  # noqa: E402


TEXTE = get_translations("de")


# --------------------------------------------------------------------
# Der Zustand, den der Server liefern wuerde
# --------------------------------------------------------------------

def stand(audio: bool, recording=False, monitoring=False,
          playback=False) -> dict:
    """
    So sieht /api/status aus.

    `audio` ist die Frage, um die es geht: gewaehltes Geraet UND
    offenes PCM-Handle (siehe Application.update_status).
    """

    if recording:
        zustand = "recording"
    elif playback:
        zustand = "playback"
    elif monitoring:
        zustand = "monitoring"
    elif not audio:
        zustand = "no_device"
    else:
        zustand = "idle"

    return {
        "audio": audio,
        "recorder": zustand,
        "recording": recording,
        "recorder_monitoring": monitoring,
        "playback_active": playback,
        "music_playing": False,
        "bluetooth_streaming": False,

        "audio_connected": audio,
        "audio_device": "XR18" if audio else "Kein Audio-Interface",
        "audio_channels": 18 if audio else 0,
        "audio_sample_rate": 48000 if audio else 0,
        "audio_sample_bits": 24,
        "audio_formats": ["S24_LE"],
        "selected_audio_device": "hw:1,0" if audio else "",

        "record_channels": 18,
        "record_sample_rate": 48000,
        "record_bits_per_sample": 24,
        "recordings": ["Soundcheck-1.w64"],
        "current_filename": "",
        "duration": 0.0,
        "mb_written": 0.0,
        "buffer_count": 0,

        "rate_plausible": None,
        "rate_measured": 0.0,
        "rate_likely": 0,
        "disk_seconds_left": 0.0,
        "disk_stopped": False,

        "cpu": 3.0, "ram": 20.0, "disk": 40.0,
        "hostname": "xrack", "uptime": "5 min",
        "usb_connected": False,

        "music_paused": False, "music_track": "", "music_track_title": "",
        "music_track_artist": "", "music_folder_mode": False,
        "music_channels": 2, "music_start_channel": 0,
        "music_position": 0.0, "music_duration": 0.0,
        "music_preferred_start_channel": 1,
        "bluetooth_device_name": "",
        "playback_filename": "", "playback_duration": 0.0,
        "playback_channels": 0,
        "recorder_levels": [],
    }


def seite_bauen(daten: dict, pruefung: str) -> str:
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

    vorspann = (
        "<script>window.I18N = " + json.dumps(TEXTE) + ";\n"
        "window.fetch = async (url) => {\n"
        "  if (String(url).indexOf('/api/status') === 0)\n"
        "    return { ok: true, json: async () => ("
        + json.dumps(daten) + ") };\n"
        "  if (String(url).indexOf('/api/audio/devices') === 0)\n"
        "    return { ok: true, json: async () => ([]) };\n"
        "  return { ok: true, json: async () => ({ success: true }) };\n"
        "};\n"
        "window.alert = () => {};\n"
        "window.confirm = () => true;\n"
        "</script>"
    )

    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"></head><body>"
        + inhalt
        + vorspann
        + "<script>" + bootstrap + "</script>"
        + "<script>" + xrack + "</script>"
        + "<div id=\"pruefergebnis\"></div>"
        + "<script>" + pruefung + "</script>"
        + "</body></html>"
    )


def ausfuehren(daten: dict, pruefung: str) -> dict:
    """
    Laedt die Seite und liefert, was das Pruefskript geschrieben hat.

    Gemessen wird an Eigenschaften (button.disabled), nicht am
    ausgegebenen HTML: Was JavaScript setzt, steht dort teils gar
    nicht.
    """

    rahmen = (
        "setTimeout(() => {\n"
        "  const ergebnis = (() => { try { return (" + pruefung + ")(); }\n"
        "    catch (e) { return { fehler: String(e) }; } })();\n"
        "  document.getElementById('pruefergebnis').textContent =\n"
        "    'ERGEBNIS' + JSON.stringify(ergebnis) + 'ENDE';\n"
        "}, 900);"
    )

    with tempfile.TemporaryDirectory() as tmp:

        datei = Path(tmp) / "seite.html"
        datei.write_text(seite_bauen(daten, rahmen), encoding="utf-8")

        lauf = subprocess.run(
            [
                str(BROWSER),
                "--no-sandbox",
                "--disable-gpu",
                "--virtual-time-budget=5000",
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

    return ergebnis


KARTE = """function () {

    const knopf = (kennung) => {
        const k = document.getElementById(kennung);
        return k ? { gesperrt: k.disabled, grund: k.title || '' } : null;
    };

    const hinweis = document.getElementById('record-device-warning');

    return {
        zustand: document.getElementById('recorder-status').textContent.trim(),
        hinweis_sichtbar: hinweis
            ? !hinweis.classList.contains('d-none') : null,
        hinweis_text: hinweis ? (hinweis.textContent || '').trim() : '',
        aufnahme: knopf('btn-recorder-toggle'),
        pegel: knopf('btn-recorder-monitor'),
        wiedergabe: knopf('btn-recorder-play')
    };
}"""


# ====================================================================
# 1. Ohne Interface: kein "bereit", und kein Knopf, der nichts tut
# ====================================================================

ohne = ausfuehren(stand(audio=False), KARTE)

assert ohne["zustand"] == TEXTE["state_no_device"], (
    f"Die Karte meldet {ohne['zustand']!r}, obwohl kein Interface offen "
    f"ist - erwartet war {TEXTE['state_no_device']!r}."
)

assert ohne["hinweis_sichtbar"], (
    "Es steht kein Hinweis in der Karte - der Nutzer sieht gesperrte "
    "Knöpfe und erfährt nicht, warum."
)

assert ohne["hinweis_text"] == TEXTE["record_no_device"], ohne["hinweis_text"]

for name in ("aufnahme", "pegel", "wiedergabe"):

    assert ohne[name] is not None, f"Den Knopf {name!r} gibt es nicht mehr."

    assert ohne[name]["gesperrt"], (
        f"Der Knopf {name!r} lässt sich ohne Interface drücken. Der "
        f"Recorder lehnt ab - für den Nutzer sieht es aus, als sei "
        f"XRack kaputt."
    )

assert ohne["aufnahme"]["grund"] == TEXTE["record_no_device"], (
    "Am Aufnahmeknopf steht kein Grund - am Tablet ist ein gesperrter "
    "Knopf ohne Begründung nur ein Knopf, der nicht geht."
)

print("OK: Ohne Interface meldet die Karte es, und die drei Knöpfe sind zu")


# ====================================================================
# 2. Mit Interface läuft alles wie vorher
#
# Der Gegenfall zählt: Eine Sperre, die immer sperrt, wäre schlimmer
# als keine.
# ====================================================================

mit = ausfuehren(stand(audio=True), KARTE)

assert mit["zustand"] == TEXTE["state_idle"], mit["zustand"]

assert not mit["hinweis_sichtbar"], (
    "Der Hinweis steht auch mit offenem Interface noch da."
)

assert not mit["aufnahme"]["gesperrt"], (
    "Der Aufnahmeknopf bleibt gesperrt, obwohl ein Interface offen ist."
)

assert not mit["pegel"]["gesperrt"], (
    "Der Pegelknopf bleibt gesperrt, obwohl ein Interface offen ist."
)

assert mit["aufnahme"]["grund"] == "", mit["aufnahme"]["grund"]

print("OK: Mit Interface steht 'bereit' da, Aufnahme und Pegel sind frei")


# ====================================================================
# 3. Eine laufende Aufnahme bleibt eine laufende Aufnahme
#
# Auch wenn das Gerät zwischendurch zufällt: Es wird noch in eine
# offene Datei geschrieben, und der Stopp-Knopf muss erreichbar
# bleiben.
# ====================================================================

laufend = ausfuehren(stand(audio=False, recording=True), KARTE)

assert laufend["zustand"] == TEXTE["state_recording"], laufend["zustand"]

assert not laufend["aufnahme"]["gesperrt"], (
    "Der Stopp-Knopf ist gesperrt, während eine Aufnahme läuft - dann "
    "lässt sie sich nicht beenden, und die Datei bleibt ohne Abschluss."
)

print("OK: Eine laufende Aufnahme lässt sich weiterhin beenden")


# ====================================================================
# 4. Beide Sprachfassungen tragen dieselben Schlüssel
#
# Ein Text, den es nur auf Deutsch gibt, fällt in der englischen
# Fassung als leere Stelle aus - und niemandem auf.
# ====================================================================

deutsch = set(get_translations("de"))
englisch = set(get_translations("en"))

assert deutsch == englisch, (
    "Die Sprachfassungen sind auseinandergelaufen:\n"
    f"  nur deutsch:  {sorted(deutsch - englisch)}\n"
    f"  nur englisch: {sorted(englisch - deutsch)}"
)

print(f"OK: Beide Sprachfassungen tragen dieselben {len(deutsch)} Schlüssel")


print("Alle Tests der Soundcheck-Karte erfolgreich.")
