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


def kanaele(anzahl: int, usb=False) -> list[dict]:
    """
    So viele Kanalzüge, wie das Pult hätte - der letzte ist die Summe.

    Beim XR18 sind es 17 (16 Kanäle, Aux-Rückweg, Summe - der
    Rückweg zählt als einer), beim X32 33.

    `usb` ist die Stellung des Eingangsschalters, die jeder Kanal
    bekommt: False = A/D, True = USB, None = dieses Pult kennt den
    Schalter nicht (dann darf keiner erscheinen). Die Summe hat ihn
    nie.
    """

    zuege = [
        {
            "channel": nummer,
            "label": str(nummer),
            "name": f"Kanal {nummer}",
            "is_main": False,
            "muted": False,
            "db": -10.0,
            "usb": usb,
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
        "usb": None,
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


# ====================================================================
# 5. Der Eingangsschalter A/D <-> USB
#
# Er gehört zum virtuellen Soundcheck: XRack spielt die Aufnahme ins
# Pult, und der Kanal muss sie hören statt seines Mikrofons. Bisher war
# das der einzige Handgriff, für den man noch nach X-AIR-Edit wechseln
# musste.
#
# Zwei Dinge stehen hier auf dem Spiel. Erstens die Beschriftung: Auf
# dem Knopf steht der ZUSTAND ("USB" heißt "hört gerade USB"), nicht
# die Wirkung des Drucks - aus zwei Metern ist das nicht zu
# unterscheiden, und hier hängt daran, ob das Pult die Mikrofone hört.
# Zweitens, dass ein Pult OHNE diesen Schalter auch keinen angezeigt
# bekommt: Ein Knopf, der sich nicht bewegen lässt, ist schlimmer als
# keiner.
# ====================================================================

#
# Der echte Schalter traegt data-channel; der unsichtbare Platzhalter
# (fuer Zuege ohne Schalter) nicht. Beide gehoeren gemessen: der eine,
# weil er bedienbar sein muss, der andere, weil er die Zuege auf einer
# Linie haelt.
#
SCHALTER = """function () {
    const grid = document.getElementById('faders-grid');

    const knoepfe = Array.from(
        grid.querySelectorAll('.fader-usb[data-channel]')
    );

    //
    // Auf welcher Hoehe die Regler stehen. Mehr als ein Wert heisst:
    // ein Zug ist gegenueber den anderen verschoben.
    //
    const hoehen = new Set(
        Array.from(grid.querySelectorAll('.fader-input')).map(
            (regler) => Math.round(regler.getBoundingClientRect().top)
        )
    );

    return {
        anzahl: knoepfe.length,
        zellen: grid.children.length,
        platzhalter: grid.querySelectorAll('.fader-usb-platz').length,
        beschriftung: knoepfe.map((k) => k.textContent.trim()),
        farbig: knoepfe.filter(
            (k) => k.classList.contains('btn-warning')
        ).length,
        // Der Schalter der Summe - den darf es nicht geben.
        summe: !!grid.lastElementChild.querySelector('.fader-usb[data-channel]'),
        gesperrt: knoepfe.filter((k) => k.disabled).length,
        reglerhoehen: hoehen.size
    };
}"""


def zeigen_mit(anzahl: int, usb) -> str:

    return (
        "document.getElementById('faders-grid').classList.remove('d-none');\n"
        "renderFaders(" + json.dumps(kanaele(anzahl, usb)) + ");"
    )


#
# a) Alle auf A/D.
#
ergebnis = ausfuehren(SCHALTER, vorher=zeigen_mit(17, False))

assert ergebnis["anzahl"] == 16, (
    f"Erwartet 16 Schalter (16 Eingangszüge, nicht die Summe), "
    f"gefunden {ergebnis['anzahl']}: {ergebnis}"
)

assert ergebnis["summe"] is False, (
    "Die Summe hat einen Eingangsschalter bekommen - sie hat keinen "
    "Eingang, den man umschalten könnte."
)

#
# Dafür steht dort ein unsichtbarer Platzhalter, und zwar aus einem
# messbaren Grund: Ohne ihn beginnt der Summenzug eine Knopfhöhe weiter
# oben, und sein Regler steht gegenüber allen anderen versetzt.
#
assert ergebnis["platzhalter"] == 1, (
    f"Erwartet ein Platzhalter (bei der Summe), gefunden "
    f"{ergebnis['platzhalter']}."
)

assert ergebnis["reglerhoehen"] == 1, (
    f"Die Regler stehen auf {ergebnis['reglerhoehen']} verschiedenen "
    f"Höhen - ein Zug ist gegenüber den anderen verschoben."
)

assert set(ergebnis["beschriftung"]) == {TEXTE["faders_usb_off"]}, (
    f"Auf A/D stehende Kanäle sind falsch beschriftet: "
    f"{ergebnis['beschriftung']}"
)

assert ergebnis["farbig"] == 0, (
    "Auf A/D ist nichts farbig - Farbe ist für den Zustand da, den man "
    "nicht vergessen darf."
)

#
# Die Karte ist im Grundzustand gesperrt (damit ein Tablet in der Tasche
# nichts verstellt). Der Eingangsschalter gehört in dieselbe Sperre wie
# die Fader - er greift tiefer ein als jeder Regler.
#
assert ergebnis["gesperrt"] == 16, (
    f"Bei gesperrter Karte sind nur {ergebnis['gesperrt']} von 16 "
    f"Eingangsschaltern gesperrt - hier wird umgelegt, was ein Kanal "
    f"hört."
)

#
# b) Alle auf USB: andere Beschriftung, und sichtbar.
#
ergebnis = ausfuehren(SCHALTER, vorher=zeigen_mit(17, True))

assert set(ergebnis["beschriftung"]) == {TEXTE["faders_usb_on"]}, (
    f"Auf USB stehende Kanäle sind falsch beschriftet: "
    f"{ergebnis['beschriftung']}"
)

assert ergebnis["farbig"] == 16, (
    f"Nur {ergebnis['farbig']} von 16 Kanälen auf USB sind hervorgehoben. "
    f"Bleibt ein Kanal nach der Probe auf USB stehen, hört er beim "
    f"nächsten Auftritt sein Mikrofon nicht - das muss man sehen."
)

#
# c) Ein Pult, das den Schalter nicht kennt: gar kein Knopf.
#
ergebnis = ausfuehren(SCHALTER, vorher=zeigen_mit(17, None))

assert ergebnis["zellen"] == 17, ergebnis

assert ergebnis["anzahl"] == 0, (
    f"Ein Pult ohne diesen Schalter bekommt {ergebnis['anzahl']} "
    f"Schalter angezeigt - sie ließen sich nicht bewegen."
)

assert ergebnis["platzhalter"] == 0, (
    "Ohne Schalter stehen trotzdem Platzhalter da - das ist nur "
    "verschenkte Höhe."
)

print("OK: Der Eingangsschalter steht da, wo er hingehört")


# ====================================================================
# 5b. Der Knopf bleibt in seiner Zelle
#
# Er ist Breite, die es vorher nicht gab, und der engste Fall ist das
# X32: 33 Züge nebeneinander, jede Spalte knapp 3rem. Zu messen ist
# dabei NICHT die Zeilenzahl - die hängt am Mindestmaß der Spalten im
# CSS (2.75rem) und ändert sich durch einen breiteren Knopf gar nicht.
# Er ragt dann einfach über seine Spalte hinaus, in den Nachbarzug
# hinein. Genau das wird hier gemessen.
#
# (Der erste Entwurf hatte 2.9rem, und diese Prüfung in ihrer ersten
# Fassung hätte das durchgelassen.)
# ====================================================================

RAGT_HERAUS = """function () {
    const grid = document.getElementById('faders-grid');

    let ueberstand = 0;
    let geprueft = 0;

    Array.from(grid.children).forEach((zelle) => {
        const knopf = zelle.querySelector('.fader-usb');
        if (!knopf) return;

        geprueft += 1;

        const z = zelle.getBoundingClientRect();
        const k = knopf.getBoundingClientRect();

        const raus = Math.max(0, k.right - z.right, z.left - k.left);

        ueberstand = Math.max(ueberstand, Math.round(raus));
    });

    return { ueberstand: ueberstand, geprueft: geprueft };
}"""

ergebnis = ausfuehren(RAGT_HERAUS, vorher=zeigen_mit(33, True))

#
# 32 echte Schalter plus den Platzhalter der Summe - der ist genauso
# breit und darf genauso wenig herausragen.
#
assert ergebnis["geprueft"] == 33, ergebnis

assert ergebnis["ueberstand"] <= 1, (
    f"Der Eingangsschalter ragt {ergebnis['ueberstand']}px aus seinem "
    f"Kanalzug heraus - am X32 liegt er damit über dem Nachbarn."
)

#
# Und die Zeilenaufteilung bleibt, was sie war.
#
ergebnis = ausfuehren(MESSUNG, vorher=zeigen_mit(17, True))

assert ergebnis["zeilen"] == [17], (
    "Mit dem Eingangsschalter passen die XR18-Züge nicht mehr in eine "
    "Zeile: " + str(ergebnis)
)

print("OK: Der Knopf bleibt in seiner Zelle, auch am X32")


# ====================================================================
# 5c. Auf dem Handy bleibt der Regler bedienbar
#
# Der Eingangsschalter kostet Platz in der Zeile, und der war auf einem
# schmalen Gerät schon vorher knapp: Name 8rem, Mute, Regler, Zahl.
# Nachgemessen bei 400px Fensterbreite blieben dem Regler mit dem neuen
# Knopf nur noch 43px - vorher 87. Mit dem Finger ist das nichts.
#
# Deshalb gibt jetzt der NAME nach (flex: 0 1 statt 0 0) und der Regler
# hat eine Untergrenze. Ein abgeschnittener Name bleibt lesbar, die
# Nummer steht vorn; ein zu kurzer Regler ist einfach unbrauchbar.
# ====================================================================

REGLERBREITE = """function () {
    const zelle = document.getElementById('faders-grid').children[0];

    return {
        zelle: Math.round(zelle.getBoundingClientRect().width),
        regler: Math.round(
            zelle.querySelector('.fader-input').getBoundingClientRect().width
        ),
        ueberlauf: Math.round(zelle.scrollWidth - zelle.clientWidth)
    };
}"""

#
# Drei Breiten, weil die Grenze dazwischen liegt: Unter 360px bricht
# der Zug um (der Regler bekommt dann die ganze zweite Zeile), darüber
# gibt der Name nach. Beides muss stimmen - und in KEINEM Fall darf
# etwas über den Rand ragen.
#
gemessen = {}

for breite in (320, 360, 400):

    ergebnis = ausfuehren(
        REGLERBREITE, vorher=zeigen_mit(17, True), breite=breite
    )

    gemessen[breite] = ergebnis["regler"]

    assert ergebnis["regler"] >= 100, (
        f"Bei {breite}px Fensterbreite bleiben dem Fader nur "
        f"{ergebnis['regler']}px (Zelle {ergebnis['zelle']}px) - mit dem "
        f"Finger nicht zu treffen."
    )

    assert ergebnis["ueberlauf"] <= 1, (
        f"Bei {breite}px ist der Kanalzug breiter als sein Platz "
        f"({ergebnis['ueberlauf']}px zu viel) - dann ragt der Knopf über "
        f"den Rand."
    )

print(f"OK: Auf dem Handy bleibt der Fader bedienbar ({gemessen})")


# ====================================================================
# 5d. Entsperren macht ALLE Bedienelemente frei
#
# Der Fehler, den es hier zu verhindern gibt, ist am Gerät passiert:
# "Die Anzeige der A/D-USB-Knöpfe stimmt, ich bekomme den aktuellen
# Stand vom Pult. Allerdings lassen sich die Knöpfe nicht betätigen.
# Bei Klick passiert nichts."
#
# Die Ursache war eine Liste von Klassennamen im Entsperren
# (".fader-input, .fader-mute"). Der Eingangsschalter kam dazu, wurde
# gesperrt gezeichnet - die Karte ist im Grundzustand gesperrt - und
# beim Entsperren nicht mitgenommen. Er blieb für immer tot.
#
# Kein Test hat je entsperrt. Deshalb hier: Es wird wirklich
# umgeschaltet, und danach muss JEDES Bedienelement frei sein - nicht
# die drei, die heute bekannt sind, sondern alle, die im Kanalzug
# stehen.
# ====================================================================

ENTSPERREN = """function () {
    const grid = document.getElementById('faders-grid');

    const alle = () => Array.from(
        grid.querySelectorAll('button, input')
    ).filter((e) => !e.classList.contains('fader-usb-platz'));

    const vorher = alle().filter((e) => e.disabled).length;

    toggleFaderLock();

    const offen = alle().filter((e) => !e.disabled);
    const zu = alle().filter((e) => e.disabled);

    toggleFaderLock();

    const wieder = alle().filter((e) => e.disabled).length;

    return {
        gesamt: alle().length,
        vorher: vorher,
        offen: offen.length,
        wieder: wieder,
        //
        // Welche bleiben hängen? Die Klassen sagen es, ohne dass der
        // Versuch die Namen vorher kennen muss.
        //
        haengengeblieben: zu.map((e) => e.className.trim())
    };
}"""

ergebnis = ausfuehren(ENTSPERREN, vorher=zeigen_mit(17, False))

#
# 16 Schalter + 17 Mute + 17 Regler = 50; die Zahl steht hier nicht,
# damit sie nicht bei jeder Änderung am Kanalzug nachgezogen werden muss.
# Entscheidend ist, dass NICHTS übrig bleibt.
#
assert ergebnis["vorher"] == ergebnis["gesamt"], (
    f"Im Grundzustand sind nur {ergebnis['vorher']} von "
    f"{ergebnis['gesamt']} Bedienelementen gesperrt - die Karte soll "
    f"gesperrt anfangen."
)

assert ergebnis["haengengeblieben"] == [], (
    "Nach dem Entsperren sind diese Bedienelemente noch gesperrt:\n  "
    + "\n  ".join(ergebnis["haengengeblieben"])
)

assert ergebnis["offen"] == ergebnis["gesamt"], ergebnis

#
# Und wieder zu: Eine Sperre, die nur in einer Richtung wirkt, ist
# keine.
#
assert ergebnis["wieder"] == ergebnis["gesamt"], (
    f"Nach dem Sperren sind nur {ergebnis['wieder']} von "
    f"{ergebnis['gesamt']} wieder gesperrt."
)

print(
    f"OK: Entsperren macht alle {ergebnis['gesamt']} Bedienelemente frei "
    f"- und Sperren wieder zu"
)


# ====================================================================
# 5e. Und ein Klick geht wirklich ans Pult
#
# "Frei" ist nur die halbe Aussage. Am Gerät war zu sehen, dass nichts
# passiert - und das kann auch an einem fehlenden Zuhörer oder an der
# falschen Adresse liegen. Deshalb wird hier geklickt, mit
# untergeschobenem fetch: Was rausgeht, steht danach da.
# ====================================================================

KLICK = """function () {
    const grid = document.getElementById('faders-grid');

    toggleFaderLock();

    const gerufen = [];

    window.fetch = (url, optionen) => {
        gerufen.push({ url: url, body: (optionen || {}).body || '' });
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    };

    const knopf = grid.querySelector('.fader-usb[data-channel="3"]');

    const vorher = knopf.className;

    knopf.click();

    return {
        gerufen: gerufen,
        vorher: vorher,
        nachher: knopf.className,
        beschriftung: knopf.textContent.trim()
    };
}"""

ergebnis = ausfuehren(KLICK, vorher=zeigen_mit(17, False))

assert len(ergebnis["gerufen"]) == 1, (
    f"Ein Klick auf den Eingangsschalter hat {len(ergebnis['gerufen'])} "
    f"Anfragen ausgelöst statt einer: {ergebnis['gerufen']}"
)

anfrage = ergebnis["gerufen"][0]

assert anfrage["url"] == "/api/console/usb-input", anfrage

#
# Kanal und Richtung müssen stimmen: Der Kanal stand auf A/D, der Klick
# legt ihn auf USB.
#
assert '"channel":3' in anfrage["body"].replace(" ", ""), anfrage
assert '"usb":true' in anfrage["body"].replace(" ", ""), anfrage

#
# Und die Anzeige folgt sofort, ohne auf die nächste Runde zu warten.
#
assert "btn-warning" in ergebnis["nachher"], (
    f"Der Knopf zeigt den neuen Zustand nicht: {ergebnis['nachher']}"
)

assert ergebnis["beschriftung"] == TEXTE["faders_usb_on"], ergebnis

print(f"OK: Ein Klick schickt {anfrage['body']} ans Pult")


print("Alle Fader-Tests erfolgreich.")
