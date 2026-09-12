#!/usr/bin/env python3
"""
Prüft, dass die Knöpfe in den Dialogen sichtbar und benutzbar sind.

Anlass ist eine Meldung vom Tablet: Beim gemeinsamen Namen für die
Web-App ließ sich der Name eintragen, aber nicht speichern - „da
fehlt ein Button".

Der Knopf war da. Er war unsichtbar: `btn-outline-light` bedeutet
weiße Schrift und weißer Rand auf durchsichtigem Grund - und die
Dialoge von XRack sind WEISS. Die Seite dahinter ist dunkel, die
Modals aber nicht: XRack setzt für sie kein dunkles Bootstrap-Thema.
Auf dem hellen Grund blieb vom Knopf nichts übrig. Das Eingabefeld
daneben war weiter zu sehen, weil ein `form-control` seinen eigenen
grauen Rand mitbringt - genau das Bild, das der Nutzer beschrieben
hat.

Nachgemessen wird deshalb der KONTRAST, nicht die Meinung: Für jeden
sichtbaren Knopf in beiden Dialogen wird die Schrift- und Randfarbe
gegen den tatsächlichen Hintergrund gerechnet. Weiß auf Weiß ergibt
1,0 - das fällt auf, ohne dass jemand hinsehen muss.

Dazu die Breite: Ein Knopf, den ein Eingabefeld daneben zu einem
Splitter zusammendrückt, ist genauso wenig zu treffen.

Ohne Browser wird übersprungen statt zu scheitern - auf dem Pi ist
keiner installiert, und dort soll die Testreihe durchlaufen.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent

#
# So breit muss ein beschrifteter Knopf mindestens bleiben. 60 Pixel
# sind weniger als eine Fingerkuppe (Apple und Google empfehlen 44) -
# wer darunter liegt, ist nicht knapp, sondern kaputt.
#
MINDESTBREITE = 60

#
# Knöpfe, auf denen nur ein Zeichen sitzt (das Auge an den
# Passwortfeldern etwa), sind mit Absicht quadratisch und klein.
# Für sie gilt die kleinere Schwelle.
#
MINDESTBREITE_ZEICHEN = 24

#
# Und so weit muss er sich vom Hintergrund abheben.
#
# Gerechnet wird das Kontrastverhältnis nach WCAG (1 bis 21). Weiß
# auf Weiß ergibt 1,0, das Grau der übrigen Knöpfe auf weißem Grund
# etwa 4,7. Die Schwelle liegt bewusst tief: Hier geht es nicht um
# Lesbarkeit im Feinen, sondern um "überhaupt zu sehen".
#
MINDESTKONTRAST = 2.5

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
    print("ÜBERSPRUNGEN: kein Browser gefunden - die Knöpfe werden nicht geprüft.")
    sys.exit(0)


from jinja2 import ChainableUndefined, Environment, FileSystemLoader  # noqa: E402

from web.i18n import get_translations  # noqa: E402


TEXTE = get_translations("de")


def seite_bauen(pruefung: str) -> str:
    """Echte Vorlage, echtes Bootstrap, echtes CSS."""

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

    #
    # Die Stylesheets werden VERKNUEPFT, nicht eingebettet: Die
    # Zeichensatz-Datei der Symbole steht in bootstrap-icons.css als
    # relativer Pfad ("../fonts/..."). Eingebettet in eine Seite im
    # Temp-Ordner ginge er ins Leere, die Symbole waeren nichts wert,
    # und die Knoepfe darum herum fielen schmaler aus als am Geraet -
    # der Versuch pruefte dann etwas, das es so nicht gibt.
    #
    stile = "".join(
        f'<link rel="stylesheet" href="file://{WURZEL}/web/static/css/{name}">'
        for name in ("bootstrap.min.css", "bootstrap-icons.css", "xrack.css")
    )

    bootstrap_js = (WURZEL / "web/static/js/bootstrap.bundle.min.js").read_text(
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
        + stile
        + "</head><body>"
        + inhalt
        + vorspann
        + "<script>" + bootstrap_js + "</script>"
        + "<script>" + xrack + "</script>"
        + '<div id="pruefergebnis"></div>'
        + "<script>" + pruefung + "</script>"
        + "</body></html>"
    )


def ausfuehren(pruefung: str, vorher: str = "", breite: int = 1024) -> dict:
    """Lädt die Seite in einem Fenster von `breite` Pixeln."""

    rahmen = (
        "setTimeout(() => { try { " + (vorher or "") + " } catch (e) {} }, 200);\n"
        "setTimeout(() => {\n"
        "  const ergebnis = (() => { try { return (" + pruefung + ")(); }\n"
        "    catch (e) { return { fehler: String(e) }; } })();\n"
        "  document.getElementById('pruefergebnis').textContent =\n"
        "    'ERGEBNIS' + JSON.stringify(ergebnis) + 'ENDE';\n"
        "}, 1200);"
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

    return ergebnis


#
# Beide Dialoge öffnen und alles aufklappen: Zugeklappt hat jedes
# Element die Breite null, und der Versuch prüfte nichts.
#
# Die WLAN-Abschnitte hängen an einer Statusabfrage, die es hier
# nicht gibt - sie werden von Hand sichtbar gemacht. Am Gerät sind
# sie sichtbar, sobald ein Funkgerät steckt, und genau dort steht
# der Knopf, um den es ging.
#
def oeffnen(dialog: str) -> str:

    return (
        "bootstrap.Modal.getOrCreateInstance("
        "document.getElementById('" + dialog + "')).show();\n"
        "document.querySelectorAll('.accordion-collapse')"
        ".forEach((teil) => teil.classList.add('show'));\n"
        "const wlan = document.getElementById('settings-wlan-sections');\n"
        "if (wlan) wlan.classList.remove('d-none');\n"
    )


#
# Gemessen wird im Fenster: tatsächliche Breite, tatsächliche Farben.
#
# Für den Kontrast wird der Hintergrund gesucht, der wirklich hinter
# dem Knopf liegt - seine eigene Fläche ist bei einem Umriss-Knopf
# durchsichtig, die Farbe kommt vom Dialog dahinter.
#
MESSUNG = """function (kennung) {

    //
    // Erst hier sichtbar machen, nicht im Vorlauf: loadSettings()
    // laeuft dazwischen noch einmal und blendet die WLAN-Abschnitte
    // wieder aus, weil die Statusabfrage im Versuch nichts liefert.
    // Am Geraet sind sie sichtbar, sobald ein Funkgeraet steckt.
    //
    const wlan_teil = document.getElementById('settings-wlan-sections');
    if (wlan_teil) wlan_teil.classList.remove('d-none');

    const dialog = document.getElementById(kennung);

    function zahlen(farbe) {
        const teile = (farbe || '').match(/[\\d.]+/g) || [];
        return teile.map(Number);
    }

    function leuchtkraft(farbe) {

        const [r, g, b] = zahlen(farbe);

        const kanal = (wert) => {
            const v = wert / 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        };

        return 0.2126 * kanal(r) + 0.7152 * kanal(g) + 0.0722 * kanal(b);
    }

    function kontrast(vorne, hinten) {
        const a = leuchtkraft(vorne);
        const b = leuchtkraft(hinten);
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    }

    function hintergrund(element) {

        let p = element;

        while (p && p !== document.documentElement) {

            const farbe = window.getComputedStyle(p).backgroundColor;
            const teile = zahlen(farbe);

            //
            // Durchsichtig? Dann zaehlt, was dahinter liegt.
            //
            if (teile.length < 4 || teile[3] > 0.1) return farbe;

            p = p.parentElement;
        }

        return 'rgb(255, 255, 255)';
    }

    const gemessen = [];

    Array.from(dialog.querySelectorAll('button, .btn')).forEach((knopf) => {

        if (knopf.offsetParent === null) return;

        const kasten = knopf.getBoundingClientRect();

        if (kasten.width === 0 && kasten.height === 0) return;

        //
        // Das Kreuz zum Schliessen ist absichtlich klein und traegt
        // seine Farbe als Bild, nicht als Schrift.
        //
        if (knopf.classList.contains('btn-close')) return;

        const stil = window.getComputedStyle(knopf);

        //
        // Bei einem gefuellten Knopf zaehlt seine eigene Flaeche als
        // Hintergrund, bei einem Umriss-Knopf der Dialog dahinter.
        //
        const eigene = zahlen(stil.backgroundColor);
        const durchsichtig = eigene.length > 3 && eigene[3] < 0.1;

        const hinten = durchsichtig
            ? hintergrund(knopf.parentElement)
            : stil.backgroundColor;

        gemessen.push({
            text: (knopf.textContent || '').trim().slice(0, 28),
            id: knopf.id || '',
            klassen: knopf.className,
            breite: Math.round(kasten.width),
            schrift: Math.round(kontrast(stil.color, hinten) * 100) / 100,
            rand: Math.round(kontrast(stil.borderTopColor, hinten) * 100) / 100,

            //
            // Die Farben auch roh - fuer den Vergleich der
            // Speichern-Knoepfe untereinander weiter unten.
            //
            grund: hinten,
            schriftfarbe: stil.color
        });
    });

    return {
        offen: dialog.classList.contains('show'),
        anzahl: gemessen.length,
        knoepfe: gemessen
    };
}"""


def knoepfe_pruefen(dialog: str, breite: int) -> dict:
    """Alle sichtbaren Knöpfe eines Dialogs messen und beurteilen."""

    ergebnis = ausfuehren(
        MESSUNG.replace("function (kennung)", "function ()")
               .replace("getElementById(kennung)", f"getElementById('{dialog}')"),
        vorher=oeffnen(dialog),
        breite=breite,
    )

    assert ergebnis["offen"], f"Der Dialog {dialog} ist gar nicht offen."

    assert ergebnis["anzahl"] >= 3, (
        f"Nur {ergebnis['anzahl']} Knöpfe in {dialog} - da war wohl nichts "
        f"aufgeklappt."
    )

    unsichtbar = [
        knopf for knopf in ergebnis["knoepfe"]
        if max(knopf["schrift"], knopf["rand"]) < MINDESTKONTRAST
    ]

    assert not unsichtbar, (
        f"Diese Knöpfe in {dialog} heben sich bei {breite} px nicht vom "
        f"Hintergrund ab (Kontrast unter {MINDESTKONTRAST}) - sie sehen "
        f"aus, als gäbe es sie nicht:\n"
        + "\n".join(
            f"  Schrift {knopf['schrift']:5.2f} / Rand {knopf['rand']:5.2f}  "
            f"{knopf['text']!r}  {knopf['klassen']}"
            for knopf in unsichtbar
        )
    )

    #
    # Beschriftete Knöpfe und reine Zeichen-Knöpfe haben verschiedene
    # Schwellen - siehe oben.
    #
    zu_schmal = [
        knopf for knopf in ergebnis["knoepfe"]
        if knopf["breite"] < (
            MINDESTBREITE if knopf["text"] else MINDESTBREITE_ZEICHEN
        )
    ]

    assert not zu_schmal, (
        f"Diese Knöpfe in {dialog} sind bei {breite} px zusammengedrückt "
        f"(unter {MINDESTBREITE} px):\n"
        + "\n".join(
            f"  {knopf['breite']:4d} px  {knopf['text']!r}"
            for knopf in zu_schmal
        )
    )

    return ergebnis


# ====================================================================
# 1. Jeder sichtbare Knopf hebt sich ab und ist breit genug
#
# Zwei Fensterbreiten, weil beides von der Breite abhängen kann: Der
# Kontrast nicht, die Breite sehr wohl.
# ====================================================================

for dialog in ("settingsModal", "lightSetupModal"):

    for breite in (1024, 768):

        ergebnis = knoepfe_pruefen(dialog, breite)

    schwaechster = min(
        ergebnis["knoepfe"],
        key=lambda knopf: max(knopf["schrift"], knopf["rand"]),
    )

    print(f"OK: {ergebnis['anzahl']} Knöpfe in {dialog} sind sichtbar und "
          f"breit genug (schwächster Kontrast: "
          f"{max(schwaechster['schrift'], schwaechster['rand']):.2f})")


# ====================================================================
# 2. Und der Knopf, um den es ging, ist wirklich da und tut etwas
#
# Die Messung oben ließe ihn auch dann durchgehen, wenn er ganz
# fehlte - deshalb hier ausdrücklich.
# ====================================================================

ergebnis = ausfuehren("""function () {

    const wlan_teil = document.getElementById('settings-wlan-sections');
    if (wlan_teil) wlan_teil.classList.remove('d-none');

    const feld = document.getElementById('settings-mdns-alias');

    const knopf = feld
        ? feld.parentElement.querySelector('button')
        : null;

    return {
        feld_da: !!feld,
        knopf_da: !!knopf,
        text: knopf ? (knopf.textContent || '').trim() : '',
        breite: knopf ? Math.round(knopf.getBoundingClientRect().width) : 0,
        ruft: knopf ? (knopf.getAttribute('onclick') || '') : '',
        funktion: typeof window.saveMdnsAlias
    };
}""", vorher=oeffnen("settingsModal"), breite=768)

assert ergebnis["feld_da"], "Das Feld für den gemeinsamen Namen fehlt."

assert ergebnis["knopf_da"], (
    "Neben dem Feld für den gemeinsamen Namen gibt es keinen Knopf - "
    "dann lässt sich der Name eintragen, aber nicht speichern."
)

assert ergebnis["text"] == TEXTE["settings_mdns_alias_save"], ergebnis

assert ergebnis["breite"] >= MINDESTBREITE, ergebnis

assert "saveMdnsAlias" in ergebnis["ruft"], ergebnis

assert ergebnis["funktion"] == "function", (
    "saveMdnsAlias gibt es nicht - der Knopf wäre da, täte aber nichts."
)

print(f"OK: Der Speichern-Knopf ist da, {ergebnis['breite']} px breit "
      f"und ruft saveMdnsAlias()")


# ====================================================================
# 3. Alle Speichern-Knöpfe sehen gleich aus
#
# Sichtbar allein genügt nicht. Der neue Knopf war nach der ersten
# Reparatur zwar zu sehen, stand aber als grauer Umriss zwischen acht
# blauen - man sucht dann trotzdem, weil er nicht aussieht wie das,
# was man sucht. Zwei weitere (Pult-Adresse, Kanalzug-Sperre) standen
# aus demselben Grund grau da, nur hatte sich daran niemand gestört.
#
# Verglichen werden die GERECHNETEN Farben, nicht die Klassennamen:
# Geprüft wird das Aussehen. Ob jemand dieselbe Wirkung über eine
# andere Schreibweise erreicht, ist dem Auge egal - und diesem Test
# auch. Deshalb steht hier auch nichts über "blau": Es zählt, dass
# alle gleich sind.
# ====================================================================

BESCHRIFTUNGEN = {
    TEXTE["btn_save"],
    TEXTE["settings_mdns_alias_save"],
}

alle = knoepfe_pruefen("settingsModal", 1024)

speichern = [
    knopf for knopf in alle["knoepfe"]
    if knopf["text"] in BESCHRIFTUNGEN
]

assert len(speichern) >= 10, (
    f"Nur {len(speichern)} Speichern-Knöpfe gefunden - da war wohl nicht "
    f"alles aufgeklappt, der Vergleich sagt dann nichts."
)

aussehen = {
    (knopf["grund"], knopf["schriftfarbe"]) for knopf in speichern
}

assert len(aussehen) == 1, (
    "Die Speichern-Knöpfe im Einstellungen-Dialog sehen verschieden aus. "
    "Einer fällt auf, und zwar als der falsche:\n"
    + "\n".join(
        f"  {knopf['schriftfarbe']:>18} auf {knopf['grund']:>18}  "
        f"{knopf['id'] or knopf['text']!r}  {knopf['klassen']}"
        for knopf in sorted(speichern, key=lambda k: k["grund"])
    )
)

grund, schriftfarbe = aussehen.pop()

print(f"OK: Alle {len(speichern)} Speichern-Knöpfe sind gleich gestaltet "
      f"({schriftfarbe} auf {grund})")


print("Alle Einstellungs-Knopf-Tests erfolgreich.")
