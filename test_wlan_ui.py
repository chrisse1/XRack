#!/usr/bin/env python3
"""
Prueft die WLAN-Maske im echten Browser.

Anlass ist ein Fehler vom Geraet: Der Pi war ohne WLAN eingerichtet
worden, in der Oberflaeche wurde es nachgetragen - und es kam

    Error: Connection activation failed: Connection 'XRack-Home' is
    not available on device wlan0 because device is not available

In der Auswahl STAND Deutschland. Gespeichert war die Funkregion aber
nie: Sie hat ihren eigenen Knopf. Ohne gesetzte Region bleibt das
Funkgeraet auf Raspberry Pi OS per rfkill gesperrt, und
NetworkManager meldet das mit einem Satz, der alles Moegliche
bedeuten kann, nur nicht das, woran es liegt.

Geprueft wird deshalb die Verdrahtung: Was in der Maske steht, muss
auch beim Server ankommen. Genau das war die Luecke - die
Zusicherung darunter (dass die Region mitgereicht wird) steht in
test_network_toggles.py, aber niemand hat nachgesehen, ob die
Oberflaeche sie ueberhaupt mitschickt.

Ohne Browser wird uebersprungen statt zu scheitern - auf dem Pi ist
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
    print("ÜBERSPRUNGEN: kein Browser gefunden - die WLAN-Maske wird nicht geprüft.")
    sys.exit(0)


from jinja2 import ChainableUndefined, Environment, FileSystemLoader  # noqa: E402

from web.i18n import get_translations  # noqa: E402


TEXTE = get_translations("de")


def seite_bauen(pruefung: str) -> str:
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
        "window.aufrufe = [];\n"
        "window.fetch = async (url, optionen) => {\n"
        "  window.aufrufe.push([String(url),\n"
        "    optionen && optionen.body ? String(optionen.body) : '']);\n"
        "  return { json: async () => ({ success: true, message: '' }) };\n"
        "};\n"
        #
        # Die WLAN-Maske fragt vor dem Speichern nach - sonst kaeme
        # der Aufruf gar nicht erst los.
        #
        "window.alert = () => {};\n"
        "window.confirm = () => true;\n"
        "</script>"
    )

    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body>'
        + inhalt
        + vorspann
        + "<script>" + bootstrap + "</script>"
        + "<script>" + xrack + "</script>"
        + '<div id="pruefergebnis"></div>'
        + "<script>" + pruefung + "</script>"
        + "</body></html>"
    )


def ausfuehren(pruefung: str, vorher: str = "") -> dict:
    """Laedt die Seite im Browser und liefert das Pruefergebnis."""

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


# ====================================================================
# 1. Die Funkregion fährt beim Speichern der Heimnetz-Daten mit
# ====================================================================

ergebnis = ausfuehren("""function () {
    const gesendet = window.aufrufe.filter(
        a => a[0].indexOf('/api/settings/wifi/home') === 0
    );

    return {
        anzahl: gesendet.length,
        koerper: gesendet.length ? gesendet[0][1] : ''
    };
}""", vorher="""
    baueLaenderListe();

    document.getElementById('settings-wifi-country').value = 'DE';
    document.getElementById('settings-home-ssid').value = 'Bandbus';
    document.getElementById('settings-home-password').value = 'geheim123';
    document.getElementById('settings-home-password-confirm').value = 'geheim123';

    saveHomeWifi();
""")

assert ergebnis["anzahl"] == 1, ergebnis

koerper = ergebnis["koerper"].replace(" ", "")

assert '"ssid":"Bandbus"' in koerper, koerper
assert '"password":"geheim123"' in koerper, koerper

assert '"country":"DE"' in koerper, (
    "Die gewählte Funkregion wird nicht mitgeschickt - genau daran ist es "
    "am Gerät gescheitert: " + koerper
)

print("OK: Die Heimnetz-Maske schickt die gewählte Funkregion mit")


# ====================================================================
# 2. Dasselbe beim Access Point
# ====================================================================

ergebnis = ausfuehren("""function () {
    const gesendet = window.aufrufe.filter(
        a => a[0].indexOf('/api/settings/wifi/ap') === 0
    );

    return {
        anzahl: gesendet.length,
        koerper: gesendet.length ? gesendet[0][1] : ''
    };
}""", vorher="""
    baueLaenderListe();

    document.getElementById('settings-wifi-country').value = 'AT';
    document.getElementById('settings-ap-ssid').value = 'XRack';
    document.getElementById('settings-ap-password').value = 'geheim123';
    document.getElementById('settings-ap-password-confirm').value = 'geheim123';

    saveApWifi();
""")

assert ergebnis["anzahl"] == 1, ergebnis

koerper = ergebnis["koerper"].replace(" ", "")

assert '"country":"AT"' in koerper, koerper

print("OK: Auch die Access-Point-Maske schickt sie mit")


# ====================================================================
# 3. Ohne gewählte Region bleibt das Feld leer - und nicht bei einem
#    Land, das nur zufällig obenan steht
#
# Der Server entscheidet dann anhand der wirklich gesetzten Region.
# Stünde hier ein Land, das niemand gewählt hat, würde er es setzen -
# und zwar ein falsches.
# ====================================================================

ergebnis = ausfuehren("""function () {
    const feld = document.getElementById('settings-wifi-country');
    const gesendet = window.aufrufe.filter(
        a => a[0].indexOf('/api/settings/wifi/home') === 0
    );

    return {
        erste_option: feld.options[0] ? feld.options[0].value : null,
        gewaehlt: feld.value,
        koerper: gesendet.length ? gesendet[0][1] : ''
    };
}""", vorher="""
    baueLaenderListe();

    document.getElementById('settings-home-ssid').value = 'Bandbus';
    document.getElementById('settings-home-password').value = 'geheim123';
    document.getElementById('settings-home-password-confirm').value = 'geheim123';

    saveHomeWifi();
""")

assert ergebnis["erste_option"] == "", (
    "Ganz oben in der Länderliste muss 'nicht gesetzt' stehen, sonst zeigt "
    "die Auswahl ein Land an, das niemand gewählt hat: " + str(ergebnis)
)

assert ergebnis["gewaehlt"] == "", ergebnis

assert '"country": ""' in ergebnis["koerper"] \
    or '"country":""' in ergebnis["koerper"].replace(" ", ""), ergebnis["koerper"]

print("OK: Ohne Wahl bleibt die Region leer - der Server entscheidet")


print("Alle WLAN-Masken-Tests erfolgreich.")
