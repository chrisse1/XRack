#!/usr/bin/env python3
"""
Der USB-Dialog im echten Browser.

Geholt wird vom Stick auf das Gerät - und das hat zwei Fallen, die
sich nur hier zeigen, nicht im Kern:

  - Die AUSWAHL hängt am Pfad. Wer ein Album anhakt, dann in einen
    Ordner geht und zurückkommt, muss seine Haken wiederfinden; und ein
    Haken in einem verlassenen Ordner gehört trotzdem mitkopiert.
    Deshalb werden VOLLE Pfade gemerkt, nicht Namen.
  - Das ZIEL steht oben und entscheidet, was verwendbar ist. Wer es
    erst am Ende wählt, hat vorher die falschen Dateien angehakt.

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
    print("ÜBERSPRUNGEN: kein Browser gefunden.")
    sys.exit(0)


from jinja2 import ChainableUndefined, Environment, FileSystemLoader  # noqa: E402

from web.i18n import get_translations  # noqa: E402

TEXTE = get_translations("de")


#
# Ein Stick, wie er wirklich aussieht: ein Album mit Unterordner, eine
# lose Datei, etwas Unbrauchbares.
#
STICK = {
    "": {
        "folders": ["Album"],
        "files": [
            {"name": "lose.mp3", "size": 5000, "usable": True},
            {"name": "notiz.txt", "size": 12, "usable": False},
        ],
    },
    "Album": {
        "folders": [],
        "files": [
            {"name": "01 Intro.mp3", "size": 1000, "usable": True},
            {"name": "02 Lied.flac", "size": 2000, "usable": True},
        ],
    },
}


def seite_bauen(pruefung: str, vorlauf: str) -> str:
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

    stile = "".join(
        f'<link rel="stylesheet" href="file://{WURZEL}/web/static/css/{name}">'
        for name in ("bootstrap.min.css", "bootstrap-icons.css", "xrack.css")
    )

    bootstrap_js = (
        WURZEL / "web/static/js/bootstrap.bundle.min.js"
    ).read_text(encoding="utf-8")

    xrack = (WURZEL / "web/static/js/xrack.js").read_text(encoding="utf-8")

    #
    # Der nachgestellte Stick antwortet auf /api/usb/browse, und der
    # Kopiervorgang ist sofort fertig - sonst wartete der Versuch auf
    # einen Fortschritt, den es hier nicht gibt.
    #
    vorspann = (
        "<script>window.I18N = " + json.dumps(TEXTE) + ";\n"
        "window.__posts = [];\n"
        "window.__stick = " + json.dumps(STICK) + ";\n"
        "window.fetch = async (url, optionen) => {\n"
        "  const u = String(url);\n"
        "  if (optionen && optionen.method === 'POST')\n"
        "    window.__posts.push({ url: u,\n"
        "      body: optionen.body ? JSON.parse(optionen.body) : null });\n"
        "  if (u.indexOf('/api/usb/browse') === 0) {\n"
        "    const pfad = decodeURIComponent(\n"
        "      (u.match(/path=([^&]*)/) || ['', ''])[1]);\n"
        "    const teil = window.__stick[pfad];\n"
        "    return { ok: true, json: async () => (teil\n"
        "      ? { available: true, path: pfad, folders: teil.folders,\n"
        "          files: teil.files }\n"
        "      : { available: false, path: '', folders: [], files: [] }) };\n"
        "  }\n"
        "  if (u.indexOf('/api/music/browse') === 0)\n"
        "    return { ok: true, json: async () => (\n"
        "      { path: '', folders: ['Proben', 'Konzerte'], files: [] }) };\n"
        "  if (u.indexOf('/api/usb/import_status') === 0)\n"
        "    return { ok: true, json: async () => ({ active: false,\n"
        "      copied: 10, total: 10, success: true, error: '',\n"
        "      report: { kopiert: 2, uebersprungen: 1,\n"
        "                fehlgeschlagen: 0 } }) };\n"
        #
        # Der Status entscheidet ueber die Sichtbarkeit des Knopfes -
        # und der Takt der Oberflaeche laeuft waehrend des Versuchs
        # weiter. Wuerde hier immer "kein Stick" stehen, versteckte
        # die naechste Runde den Knopf wieder.
        #
        "  if (u.indexOf('/api/status') === 0)\n"
        "    return { ok: true, json: async () => (\n"
        "      { usb_connected: window.__usbDa === true }) };\n"
        "  return { ok: true, json: async () => ({ success: true }) };\n"
        "};\n"
        "window.alert = (text) => { window.__alert = String(text); };\n"
        "</script>"
    )

    nachspann = (
        "<script>setTimeout(async () => { try { " + vorlauf + " }\n"
        "  catch (e) { window.__vorlauffehler = String(e); } }, 300);\n"
        "setTimeout(() => {\n"
        "  const ergebnis = (() => { try { return (" + pruefung + ")(); }\n"
        "    catch (e) { return { fehler: String(e) }; } })();\n"
        "  if (window.__vorlauffehler)\n"
        "    ergebnis.vorlauffehler = window.__vorlauffehler;\n"
        "  document.getElementById('pruefergebnis').textContent =\n"
        "    'ERGEBNIS' + JSON.stringify(ergebnis) + 'ENDE';\n"
        "}, 1400);</script>"
    )

    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        + stile
        + "</head><body>"
        + inhalt
        + vorspann
        + "<script>" + bootstrap_js + "</script>"
        + "<script>" + xrack + "</script>"
        + '<div id="pruefergebnis"></div>'
        + nachspann
        + "</body></html>"
    )


def ausfuehren(pruefung: str, vorlauf: str = "") -> dict:

    with tempfile.TemporaryDirectory() as tmp:

        datei = Path(tmp) / "seite.html"
        datei.write_text(seite_bauen(pruefung, vorlauf), encoding="utf-8")

        lauf = subprocess.run(
            [
                str(BROWSER),
                "--no-sandbox",
                "--disable-gpu",
                "--window-size=1024,900",
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
        "Das Prüfskript hat nichts geschrieben:\n" + lauf.stderr[-2000:]
    )

    ergebnis = json.loads(dom.split("ERGEBNIS", 1)[1].split("ENDE", 1)[0])

    assert "fehler" not in ergebnis, ergebnis["fehler"]
    assert "vorlauffehler" not in ergebnis, ergebnis["vorlauffehler"]

    return ergebnis


DIALOG = """function () {

    const liste = document.getElementById('usb-list');

    const zeilen = Array.from(liste.children).map((z) => {
        const haken = z.querySelector('input[type="checkbox"]');
        return {
            text: (z.textContent || '').trim(),
            haken: !!haken,
            gesperrt: haken ? haken.disabled : null,
            gewaehlt: haken ? haken.checked : null
        };
    });

    return {
        knopf_sichtbar: !document.getElementById('btn-usb-browse')
            .classList.contains('d-none'),
        pfad: document.getElementById('usb-path').textContent,
        hoch_gesperrt: document.getElementById('btn-usb-up').disabled,
        zeilen: zeilen,
        kopieren_gesperrt: document.getElementById('btn-usb-import').disabled,
        auswahl_info: window.__vorKopieren !== undefined
            ? window.__vorKopieren
            : document.getElementById('usb-selection-info').textContent,
        ordner: Array.from(
            document.getElementById('usb-target-folder').options
        ).map((o) => o.value),
        ergebnis: document.getElementById('usb-import-result').textContent,
        posts: window.__posts
    };
}"""


# ====================================================================
# 1. Der Knopf erscheint nur mit Stick
# ====================================================================

ohne = ausfuehren(
    DIALOG,
    "updateUsbEjectButton({ usb_connected: false }); await usbOeffnen();",
)

assert ohne["knopf_sichtbar"] is False, (
    "Ohne Stick steht der Knopf da - und öffnet einen leeren Dialog."
)

mit = ausfuehren(
    DIALOG,
    "window.__usbDa = true; updateUsbEjectButton({ usb_connected: true }); await usbOeffnen();",
)

assert mit["knopf_sichtbar"] is True, "Mit Stick fehlt der Knopf."

print("OK: Der Knopf erscheint nur, wenn ein Stick steckt")


# ====================================================================
# 2. Der Dialog zeigt Ordner, Dateien - und was XRack nicht kann
# ====================================================================

assert mit["pfad"] == "/", mit["pfad"]

assert mit["hoch_gesperrt"] is True, (
    "Im Hauptordner lässt sich noch weiter hinauf - wohin denn?"
)

texte = [z["text"] for z in mit["zeilen"]]

assert any("Album" in t for t in texte), texte
assert any("lose.mp3" in t for t in texte), texte

unbrauchbar = [z for z in mit["zeilen"] if "notiz.txt" in z["text"]]

assert unbrauchbar and unbrauchbar[0]["gesperrt"] is True, (
    f"Die unbrauchbare Datei lässt sich anhaken: {unbrauchbar}"
)

assert TEXTE["usb_not_usable"] in unbrauchbar[0]["text"], (
    f"Es steht nicht dabei, warum: {unbrauchbar[0]['text']!r}"
)

#
# Und die Zielordner der Bibliothek stehen zur Wahl.
#
assert mit["ordner"] == ["", "Proben", "Konzerte"], mit["ordner"]

assert mit["kopieren_gesperrt"] is True, (
    "Ohne Auswahl lässt sich kopieren - was denn?"
)

print("OK: Der Dialog zeigt den Stick, samt Ungeeignetem")


# ====================================================================
# 3. Die Auswahl übersteht einen Ordnerwechsel
#
# Wer ein Album anhakt, in einen Ordner geht und zurückkommt, muss
# seine Haken wiederfinden. Deshalb werden volle Pfade gemerkt.
# ====================================================================

gewandert = ausfuehren(
    DIALOG,
    (
        "window.__usbDa = true; updateUsbEjectButton({ usb_connected: true });"
        "await usbOeffnen();"
        #
        # Im Hauptordner die lose Datei anhaken ...
        #
        "document.querySelectorAll('#usb-list input[type=checkbox]')[1]"
        "  .click();"
        #
        # ... dann in den Ordner gehen und dort eine Datei anhaken.
        #
        "await (async () => { usbPfad = 'Album'; await usbAuflisten(); })();"
        "document.querySelectorAll('#usb-list input[type=checkbox]')[0]"
        "  .click();"
        #
        # Der Stand VOR dem Kopieren - danach ist die Auswahl leer, und
        # das ist richtig so.
        #
        "window.__vorKopieren ="
        "  document.getElementById('usb-selection-info').textContent;"
        #
        # Und dann kopieren: Erst daran zeigt sich, ob die Auswahl aus
        # dem Hauptordner noch dieselbe Datei MEINT.
        #
        "await usbHolen();"
    ),
)

assert gewandert["pfad"] == "/Album", gewandert["pfad"]

assert gewandert["hoch_gesperrt"] is False, (
    "Aus einem Unterordner führt kein Weg zurück."
)

assert TEXTE["usb_selected"].replace("{n}", "2") in gewandert["auswahl_info"], (
    f"Die Auswahl aus dem Hauptordner ging beim Wechsel verloren: "
    f"{gewandert['auswahl_info']!r}"
)

#
# Und sie meinen danach noch dieselben Dateien. Das ist der Punkt:
# Würden nur NAMEN gemerkt, ginge "01 Intro.mp3" als Datei im
# Hauptordner hinaus - dort gibt es sie nicht, und es würde
# stillschweigend nichts kopiert.
#
gewandert_geschickt = [
    p for p in gewandert["posts"] if p["url"] == "/api/usb/import"
][0]["body"]["sources"]

assert sorted(gewandert_geschickt) == ["Album/01 Intro.mp3", "lose.mp3"], (
    f"Geschickt wurde {gewandert_geschickt} - erwartet sind volle Pfade. "
    f"Ein Name allein zeigt nach dem Ordnerwechsel ins Leere."
)

print("OK: Haken überstehen den Wechsel und meinen dieselben Dateien")


# ====================================================================
# 4. Kopieren schickt volle Pfade, Ziel und Ordner
# ====================================================================

geschickt = ausfuehren(
    DIALOG,
    (
        "window.__usbDa = true; updateUsbEjectButton({ usb_connected: true });"
        "await usbOeffnen();"
        #
        # Den ganzen Ordner anhaken - rekursiv ist Absicht.
        #
        "document.querySelectorAll('#usb-list input[type=checkbox]')[0]"
        "  .click();"
        "document.getElementById('usb-target-folder').value = 'Proben';"
        "await usbHolen();"
    ),
)

anfragen = [
    p for p in geschickt["posts"] if p["url"] == "/api/usb/import"
]

assert len(anfragen) == 1, (
    f"Der Knopf schickte {len(anfragen)} Aufrufe: {geschickt['posts']}"
)

koerper = anfragen[0]["body"]

assert koerper["sources"] == ["Album"], koerper

assert koerper["target"] == "music", koerper

assert koerper["folder"] == "Proben", (
    f"Der gewählte Zielordner kam nicht mit: {koerper}"
)

#
# Und hinterher steht da, was passiert ist - gerade die
# übersprungenen: Wer nicht erfährt, dass eine Datei schon da war,
# hält es für einen Fehlschlag.
#
assert "2" in geschickt["ergebnis"] and "1" in geschickt["ergebnis"], (
    f"Der Bericht nennt die Zahlen nicht: {geschickt['ergebnis']!r}"
)

print(f"OK: Kopieren schickt volle Pfade und Ziel ({koerper})")


print("Alle Tests des USB-Dialogs erfolgreich.")
