#!/usr/bin/env python3
"""
Prüft die Aufteilung der Kanalzüge im echten Browser.

Anlass ist ein Bericht vom X32: Die Kanalzüge brachen ab einem
bestimmten Kanal in eine zweite Zeile um - die erste randvoll, die
zweite halb leer. Am XR18 fiel das nie auf, dort passen alle
siebzehn Züge nebeneinander, und das soll auch so bleiben.

Gemessen wird deshalb dort, wo es zählt: an der Lage der Zellen im
Fenster. Wie viele Spalten das CSS zulässt, hängt an Fensterbreite,
Schriftgröße und Zoom - eine Zusicherung über Pixelwerte wäre
deshalb wertlos. Die Zusicherung lautet stattdessen: Keine Zeile
trägt mehr als einen Zug mehr als eine andere.

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
    print("ÜBERSPRUNGEN: kein Browser gefunden - die Fader werden nicht geprüft.")
    sys.exit(0)


from jinja2 import ChainableUndefined, Environment, FileSystemLoader  # noqa: E402

from web.i18n import get_translations  # noqa: E402


TEXTE = get_translations("de")


def kanaele(anzahl: int) -> list[dict]:
    """
    So viele Kanalzüge, wie das Pult hätte - der letzte ist die Summe.

    Beim XR18 sind es 17 (16 Kanäle, Aux-Rückweg, Summe - der
    Rückweg zählt als einer), beim X32 33.
    """

    zuege = [
        {
            "channel": nummer,
            "label": str(nummer),
            "name": f"Kanal {nummer}",
            "is_main": False,
            "muted": False,
            "db": -10.0,
        }
        for nummer in range(1, anzahl)
    ]

    zuege.append({
        "channel": anzahl,
        "label": "Main",
        "name": "",
        "is_main": True,
        "muted": False,
        "db": 0.0,
    })

    return zuege


def seite_bauen(pruefung: str) -> str:
    """Echte Vorlage, echtes CSS, echtes xrack.js."""

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

    bootstrap = (WURZEL / "web/static/css/bootstrap.min.css").read_text(
        encoding="utf-8"
    )
    eigen = (WURZEL / "web/static/css/xrack.css").read_text(encoding="utf-8")

    js_bootstrap = (WURZEL / "web/static/js/bootstrap.bundle.min.js").read_text(
        encoding="utf-8"
    )
    xrack = (WURZEL / "web/static/js/xrack.js").read_text(encoding="utf-8")

    vorspann = (
        "<script>window.I18N = " + json.dumps(TEXTE) + ";\n"
        "window.fetch = async () => ({ json: async () => ({}) });\n"
        "window.alert = () => {};\n"
        "</script>"
    )

    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        + "<style>" + bootstrap + "</style>"
        + "<style>" + eigen + "</style>"
        + "</head><body>"
        + inhalt
        + vorspann
        + "<script>" + js_bootstrap + "</script>"
        + "<script>" + xrack + "</script>"
        + '<div id="pruefergebnis"></div>'
        + "<script>" + pruefung + "</script>"
        + "</body></html>"
    )


def ausfuehren(pruefung: str, vorher: str = "",
               breite: int = 1600) -> dict:
    """Lädt die Seite in einem Fenster von `breite` Pixeln."""

    rahmen = (
        "setTimeout(() => { try { " + (vorher or "") + " } catch (e) {} }, 200);\n"
        "setTimeout(() => {\n"
        "  const ergebnis = (() => { try { return (" + pruefung + ")(); }\n"
        "    catch (e) { return { fehler: String(e) }; } })();\n"
        "  document.getElementById('pruefergebnis').textContent =\n"
        "    'ERGEBNIS' + JSON.stringify(ergebnis) + 'ENDE';\n"
        "}, 900);"
    )

    with tempfile.TemporaryDirectory() as tmp:

        datei = Path(tmp) / "seite.html"
        datei.write_text(seite_bauen(rahmen), encoding="utf-8")

        lauf = subprocess.run(
            [
                str(BROWSER),
                "--no-sandbox",
                "--disable-gpu",
                f"--window-size={breite},900",
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


#
# Die Messung: Zellen nach ihrer Höhe im Fenster gruppieren. Was auf
# derselben Höhe steht, steht in derselben Zeile - das ist unabhängig
# davon, wie das CSS die Aufteilung erreicht.
#
MESSUNG = """function () {
    const grid = document.getElementById('faders-grid');
    const zellen = Array.from(grid.children);

    const zeilen = {};

    zellen.forEach((zelle) => {
        const oben = Math.round(zelle.getBoundingClientRect().top);
        zeilen[oben] = (zeilen[oben] || 0) + 1;
    });

    return {
        anzahl: zellen.length,
        sichtbar: !grid.classList.contains('d-none'),
        zeilen: Object.keys(zeilen)
            .map(Number)
            .sort((a, b) => a - b)
            .map((oben) => zeilen[oben]),
        spalten: window.getComputedStyle(grid).gridTemplateColumns
    };
}"""


def zeigen(anzahl: int) -> str:
    """Die Kanalzug-Karte mit so vielen Zügen aufbauen."""

    return (
        "document.getElementById('faders-grid').classList.remove('d-none');\n"
        "renderFaders(" + json.dumps(kanaele(anzahl)) + ");"
    )


# ====================================================================
# 1. XR18: siebzehn Züge, eine Zeile - und das bleibt so
# ====================================================================

ergebnis = ausfuehren(MESSUNG, vorher=zeigen(17))

assert ergebnis["anzahl"] == 17, ergebnis

assert ergebnis["zeilen"] == [17], (
    "Am XR18 passen alle Kanalzüge nebeneinander - das war gut so und "
    "muss so bleiben: " + str(ergebnis)
)

print("OK: Beim XR18 stehen alle 17 Züge in einer Zeile")


# ====================================================================
# 2. X32: dreiunddreißig Züge, gleichmäßig auf die Zeilen
#
# Vom Gerät gemeldet: Die erste Zeile randvoll, die zweite mit dem
# Rest. Das ist nicht nur unruhig anzusehen - jeder Regler in der
# vollen Zeile ist dabei schmaler, als er sein müsste.
# ====================================================================

ergebnis = ausfuehren(MESSUNG, vorher=zeigen(33))

assert ergebnis["anzahl"] == 33, ergebnis

zeilen = ergebnis["zeilen"]

assert len(zeilen) >= 2, (
    "Für diesen Versuch müssen die Züge umbrechen - sonst prüft er "
    "nichts: " + str(ergebnis)
)

assert max(zeilen) - min(zeilen) <= 1, (
    f"Die Zeilen sind ungleich besetzt ({zeilen}) - genau das war die "
    f"Meldung vom X32: {ergebnis}"
)

assert sum(zeilen) == 33, zeilen

print(f"OK: Beim X32 verteilen sich die 33 Züge gleichmäßig ({zeilen})")


# ====================================================================
# 3. Auch in einem schmaleren Fenster
#
# Wie viele Züge nebeneinander passen, hängt am Fenster - und damit
# auch, wie viele Zeilen es werden. Eine Zusicherung über feste
# Spaltenzahlen wäre deshalb wertlos; zugesichert ist die
# Gleichverteilung, und zwar bei jeder Breite.
# ====================================================================

ergebnis = ausfuehren(MESSUNG, vorher=zeigen(33), breite=1100)

zeilen = ergebnis["zeilen"]

assert sum(zeilen) == 33, zeilen

assert max(zeilen) - min(zeilen) <= 1, (
    f"Im schmalen Fenster sind die Zeilen ungleich besetzt: {zeilen}"
)

print(f"OK: Auch im schmalen Fenster bleibt es gleichmäßig ({zeilen})")


# ====================================================================
# 4. Auf dem Handy bleibt es beim Stapel
#
# Unter 992px stellt das CSS die Züge als waagerechte Zeilen
# untereinander - ein Zug je Zeile. Die Aufteilung darf da nicht
# hineinregieren.
# ====================================================================

ergebnis = ausfuehren(MESSUNG, vorher=zeigen(33), breite=500)

assert ergebnis["zeilen"] == [1] * 33, (
    "Auf schmalen Geräten gehört jeder Zug in seine eigene Zeile: "
    + str(ergebnis["zeilen"])
)

assert "px" not in ergebnis["spalten"] or ergebnis["spalten"] == "none", (
    "Auf dem Handy darf keine Spaltenaufteilung gesetzt sein: "
    + str(ergebnis["spalten"])
)

print("OK: Auf schmalen Geräten steht weiter ein Zug je Zeile")


print("Alle Fader-Tests erfolgreich.")
