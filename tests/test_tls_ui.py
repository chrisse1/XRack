#!/usr/bin/env python3
"""
Prüft den Zertifikats-Teil der Einstellungen im echten Browser.

Der Python-Teil (test_tls_transfer.py) prüft, was mit dem Zertifikat
geschieht. Hier geht es um das, was nur im Browser passiert und was
man dem Quelltext nicht ansieht:

  - Ohne vergebene PIN muss der Hinweis dastehen. Sonst drückt jemand
    auf "Sichern", bekommt eine Absage und weiss nicht, warum.
  - Steht der gemeinsame Name nicht im Zertifikat, muss das auffallen.
    Sonst trägt der Nutzer es auf alle Racks und der Browser fragt
    weiterhin bei jedem - die Mühe umsonst, ohne Fehlermeldung.
  - Die PIN, mit der der Dialog geöffnet wurde, muss beim Sichern
    mitgehen. Tut sie es nicht, geht gar nichts, und der Nutzer sieht
    nur "PIN stimmt nicht".
  - Und die Namen aus dem Zertifikat werden als TEXT angezeigt. Sie
    stammen aus einer eingespielten Datei - also von woanders.

Ohne Browser wird übersprungen statt zu scheitern - auf dem Pi ist
keiner installiert, und dort soll die Testreihe durchlaufen.
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
from pathlib import Path


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
    print("ÜBERSPRUNGEN: kein Browser gefunden - der Dialog wird nicht geprüft.")
    sys.exit(0)


from jinja2 import ChainableUndefined, Environment, FileSystemLoader  # noqa: E402

from web.i18n import get_translations  # noqa: E402


TEXTE = get_translations("de")


def zustand(present=True, imported=False, alias="xrack", alias_covered=True,
            pin_required=False, names=None, installable=True) -> dict:

    return {
        "present": present,
        "imported": imported,
        "installable": installable,
        "names": names or ["rack-a", "rack-a.local", "xrack.local", "localhost"],
        "valid_until": "2035-09-12",
        "days_left": 3650,
        "alias": alias,
        "alias_covered": alias_covered,
        "min_password": 8,
        "pin_required": pin_required,
    }


def seite_bauen(tls: dict, pruefung: str) -> str:
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
    # Mitgeschrieben wird jeder Aufruf mit seinem Rumpf: Nur so laesst
    # sich pruefen, dass die PIN wirklich mitgeht.
    #
    vorspann = (
        "<script>window.I18N = " + json.dumps(TEXTE) + ";\n"
        "window.aufrufe = [];\n"
        "window.fetch = async (url, optionen) => {\n"
        "  window.aufrufe.push([String(url),\n"
        "    optionen && optionen.body ? String(optionen.body) : '']);\n"
        "  if (String(url).indexOf('/api/tls') === 0)\n"
        "    return { ok: true, headers: { get: () => 'application/json' },\n"
        "             json: async () => (" + json.dumps(tls) + ") };\n"
        #
        # Die PIN-Pruefung VOR der allgemeinen Einstellungsabfrage:
        # Ihr Pfad faengt genauso an, und die allgemeine Antwort
        # enthaelt kein "success" - der PIN-Dialog haette dann still
        # aufgegeben.
        #
        "  if (String(url).indexOf('/api/settings/pin/verify') === 0)\n"
        "    return { ok: true, json: async () => ({ success: true }) };\n"
        "  if (String(url).indexOf('/api/settings') === 0)\n"
        "    return { ok: true, json: async () => ({ wlan: {}, mdns_alias: {} }) };\n"
        "  return { ok: true, headers: { get: () => 'application/json' },\n"
        "           json: async () => ({ success: true, message: '' }) };\n"
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


def ausfuehren(tls: dict, pruefung: str, vorher: str = "") -> dict:

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
        datei.write_text(seite_bauen(tls, rahmen), encoding="utf-8")

        lauf = subprocess.run(
            [
                str(BROWSER), "--no-sandbox", "--disable-gpu",
                "--virtual-time-budget=5000", "--dump-dom",
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
# Die Einstellungen oeffnen und den Zustand einspielen - genau wie
# loadSettings() es tut.
#
OEFFNEN = (
    "bootstrap.Modal.getOrCreateInstance("
    "document.getElementById('settingsModal')).show();\n"
    "document.querySelectorAll('.accordion-collapse')"
    ".forEach((teil) => teil.classList.add('show'));\n"
)

ABLESEN = """function () {

    const warnung = document.getElementById('settings-tls-warning');

    const holen = document.getElementById('btn-tls-download');

    return {
        holen_da: !!holen,
        holen_ziel: holen ? holen.getAttribute('href') : '',
        holen_download: holen ? holen.hasAttribute('download') : false,
        zustand: (document.getElementById('settings-tls-state').textContent || '').trim(),
        warnung_sichtbar: !warnung.classList.contains('d-none'),
        warnung: (warnung.textContent || '').trim(),
        ergebnis: (document.getElementById('settings-tls-result').textContent || '').trim(),
        aufrufe: window.aufrufe
    };
}"""


# ====================================================================
# 1. Der Normalfall: Zustand steht da, keine Warnung
# ====================================================================

gut = ausfuehren(zustand(), ABLESEN, vorher=OEFFNEN + "loadTls();")

assert TEXTE["settings_tls_self"] in gut["zustand"], gut["zustand"]
assert "2035-09-12" in gut["zustand"], gut["zustand"]
assert "xrack.local" in gut["zustand"], gut["zustand"]

assert not gut["warnung_sichtbar"], (
    f"Es steht eine Warnung da, obwohl alles passt: {gut['warnung']}"
)

print("OK: Der Zustand des Zertifikats steht im Dialog")


# ====================================================================
# 2. Ohne PIN: der Hinweis, warum hier nichts geht
# ====================================================================

ohne_pin = ausfuehren(
    zustand(pin_required=True), ABLESEN, vorher=OEFFNEN + "loadTls();"
)

assert ohne_pin["warnung_sichtbar"], (
    "Ohne vergebene PIN steht kein Hinweis da - der Nutzer drückt auf "
    "'Sichern', bekommt eine Absage und weiss nicht, warum."
)

assert ohne_pin["warnung"] == TEXTE["settings_tls_pin_required"], (
    ohne_pin["warnung"]
)

print("OK: Ohne vergebene PIN sagt der Dialog, was fehlt")


# ====================================================================
# 3. Gemeinsamer Name nicht im Zertifikat - der stille Fall
# ====================================================================

daneben = ausfuehren(
    zustand(alias="anders", alias_covered=False),
    ABLESEN,
    vorher=OEFFNEN + "loadTls();",
)

assert daneben["warnung_sichtbar"], (
    "Der gemeinsame Name steht nicht im Zertifikat, und niemand sagt es - "
    "dann trägt man das Zertifikat auf alle Racks, und der Browser fragt "
    "trotzdem weiter bei jedem."
)

assert "anders" in daneben["warnung"], daneben["warnung"]

print("OK: Ein nicht abgedeckter gemeinsamer Name fällt auf")


# ====================================================================
# 4. Die PIN aus dem Dialog geht beim Sichern mit
# ====================================================================

#
# Die PIN wird NICHT von Hand gesetzt, sondern durch den echten
# PIN-Dialog geschickt. Sonst prüft der Versuch nur, dass der Export
# eine Variable mitschickt - und nicht, dass diese Variable beim
# Öffnen des Dialogs überhaupt gefüllt wird. Genau daran ist eine
# frühere Fassung dieses Tests vorbeigelaufen.
#
MIT_PIN = (
    "document.getElementById('settings-pin-input').value = '4711';\n"
    + "confirmSettingsPin();\n"
    + OEFFNEN
    + "document.getElementById('settings-tls-password').value = 'einKennwort';\n"
    + "setTimeout(() => "
    + "document.getElementById('btn-tls-export').click(), 150);\n"
)

gesichert = ausfuehren(zustand(), ABLESEN, vorher=MIT_PIN)

export = [
    ruf for ruf in gesichert["aufrufe"] if ruf[0].endswith("/api/tls/export")
]

assert export, (
    "Der Knopf 'Sichern' schickt nichts los:\n"
    + "\n".join(ruf[0] for ruf in gesichert["aufrufe"])
)

rumpf = json.loads(export[0][1])

assert rumpf["pin"] == "4711", (
    "Die PIN, mit der der Dialog geöffnet wurde, geht beim Sichern nicht "
    f"mit - dann lehnt der Server ab: {rumpf}"
)

assert rumpf["password"] == "einKennwort", rumpf

print("OK: Beim Sichern gehen PIN und Kennwort mit")


# ====================================================================
# 5. Die Namen aus dem Zertifikat werden angezeigt, nicht ausgeführt
#
# Sie stammen aus einer eingespielten Datei - also von woanders.
# ====================================================================

boese = ausfuehren(
    zustand(names=["<img src=x onerror=window.__geknackt=1>", "rack.local"]),
    """function () {
        return {
            geknackt: !!window.__geknackt,
            bilder: document.querySelectorAll('#settings-tls-state img').length,
            zustand: (document.getElementById('settings-tls-state').textContent || '').trim(),
            warnung_sichtbar: false, warnung: '', ergebnis: '', aufrufe: []
        };
    }""",
    vorher=OEFFNEN + "loadTls();",
)

assert not boese["geknackt"], (
    "Ein Name aus dem Zertifikat wurde als HTML ausgeführt - eine "
    "eingespielte Datei darf im Dialog nichts anrichten."
)

assert boese["bilder"] == 0, boese

#
# Der Name steht da - als Text. Die spitzen Klammern kommen hier
# maskiert an, weil das Ergebnis selbst durch den DOM-Auszug des
# Browsers wandert; entscheidend ist, dass der Name lesbar dasteht
# und oben kein Bild daraus geworden ist.
#
assert "img src=x" in boese["zustand"], (
    f"Der Name steht gar nicht da: {boese['zustand']}"
)

print("OK: Namen aus dem Zertifikat stehen als Text da, nicht als HTML")


# ====================================================================
# 6. Der Knopf zum Herunterladen
#
# Er holt nur den oeffentlichen Teil - deshalb ein einfacher Verweis
# ohne PIN und ohne Kennwort. Dass er wirklich auf die Route zeigt und
# ein "download" traegt, sieht man der Vorlage nicht an: Ohne
# "download" oeffnet der Browser die Datei statt sie zu speichern, und
# am Tablet passiert dann gar nichts Nuetzliches.
# ====================================================================

assert gut["holen_da"], "Der Knopf zum Herunterladen fehlt im Dialog."

assert gut["holen_ziel"] == "/api/tls/certificate", gut["holen_ziel"]

assert gut["holen_download"], (
    "Dem Verweis fehlt das download-Attribut - der Browser zeigt die "
    "Datei dann an, statt sie zu speichern."
)

print("OK: Der Download-Verweis zeigt auf die Route und speichert")


# ====================================================================
# 7. Ein Zertifikat, das sich nicht eintragen lässt, sagt es
#
# Ohne CA:TRUE nimmt Android die Datei nicht an. Ohne Hinweis waere
# der Download ein Knopf, der etwas Unbrauchbares liefert - und der
# Nutzer suchte den Fehler bei seinem Tablet.
# ====================================================================

nicht_eintragbar = ausfuehren(
    zustand(installable=False), ABLESEN, vorher=OEFFNEN + "loadTls();"
)

assert nicht_eintragbar["warnung_sichtbar"], (
    "Ein Zertifikat, das sich nicht eintragen lässt, wird stillschweigend "
    "zum Herunterladen angeboten."
)

assert nicht_eintragbar["warnung"] == TEXTE["settings_tls_not_installable"], (
    nicht_eintragbar["warnung"]
)

print("OK: Ein nicht eintragbares Zertifikat wird als solches gemeldet")


print("Alle Tests des Zertifikats-Dialogs erfolgreich.")
