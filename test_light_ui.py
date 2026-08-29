#!/usr/bin/env python3
"""
Prueft die Lichtkarte im echten Browser.

Warum ueberhaupt ein Browser: Die Karte entsteht vollstaendig im
JavaScript aus dem, was /api/lighting/status liefert. Ob aus einer
24-Kanal-Lampe acht Farbfelder werden statt 24 Reglern, sieht man
weder der Vorlage noch dem Python-Teil an.

Hier wird mit dem ECHTEN bootstrap.bundle.min.js gearbeitet, nicht
mit einer Attrappe. Genau daran ist die Pruefung beim Umbau des
Einstellungen-Menues (1.8.2) vorbeigelaufen: Dort war bootstrap.Modal
nachgestellt und wirkungslos, ein kaputtes Modal konnte gar nicht
auffallen. Deshalb wird unten auch wirklich auf den Knopf geklickt
und nachgesehen, ob sich der Dialog oeffnet.

Ohne Browser wird der Test uebersprungen statt zu scheitern - auf dem
Pi ist keiner installiert, und dort soll die Testreihe durchlaufen.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent

#
# Der vorinstallierte Chromium der Entwicklungsumgebung.
#
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
    print("ÜBERSPRUNGEN: kein Browser gefunden - die Lichtkarte wird nicht geprüft.")
    sys.exit(0)


from jinja2 import ChainableUndefined, Environment, FileSystemLoader  # noqa: E402

from web.i18n import get_translations  # noqa: E402


TEXTE = get_translations("de")


def seite_bauen(stand: dict, pruefung: str) -> str:
    """
    Baut die fertige Seite: echte Vorlage, echtes Bootstrap, echtes
    xrack.js - nur die Netzwerkaufrufe sind nachgestellt.
    """

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
        "  if (String(url).indexOf('/api/lighting/status') === 0)\n"
        "    return { json: async () => (" + json.dumps(stand) + ") };\n"
        "  return { json: async () => ({ success: true, message: '' }) };\n"
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


def ausfuehren(stand: dict, pruefung: str, vorher: str = "") -> dict:
    """
    Laedt die Seite im Browser und liefert, was das Pruefskript in
    #pruefergebnis geschrieben hat.

    Gemessen wird an Eigenschaften (element.checked, classList), nicht
    am ausgegebenen HTML: Was JavaScript setzt, steht dort teils gar
    nicht - "checked" etwa ist eine Eigenschaft und kein Attribut. Ein
    Test, der nur das HTML liest, ginge daran vorbei.
    """

    #
    # Zwei Zeitpunkte, und der Abstand ist kein Zufall: Bootstrap
    # blendet ein Modal mit einem Uebergang ein und setzt die Klasse
    # "show" erst danach. Wer unmittelbar nach dem Klick nachsieht,
    # bekommt "zu" - und haelt das faelschlich fuer einen Fehler.
    # Deshalb wird zuerst geklickt und erst spaeter geprueft.
    #
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
        datei.write_text(seite_bauen(stand, rahmen), encoding="utf-8")

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

    roh = dom.split("ERGEBNIS", 1)[1].split("ENDE", 1)[0]

    ergebnis = json.loads(roh)

    assert "fehler" not in ergebnis, ergebnis["fehler"]

    return ergebnis


# --------------------------------------------------------------------
# Der Zustand, den der Server liefern wuerde
# --------------------------------------------------------------------

def stand(enabled=True, service=True, adapter=True, overlaps=None,
          show_running=False, show_state="music") -> dict:

    return {
        "enabled": enabled,
        "templates": [
            {
                "id": "bar-8-rgb",
                "name": "LED-Bar, 8 Segmente RGB (24 Kanäle)",
                "channels": ["red", "green", "blue"] * 8,
                "builtin": True,
            },
            {
                "id": "kopf",
                "name": "Bewegtlicht",
                "channels": ["pan", "tilt", "dimmer", "red", "green", "blue"],
                "builtin": False,
            },
        ],
        "fixtures": [
            {"id": "bar", "name": "LED-Bar links",
             "template": "bar-8-rgb", "address": 1},
        ],
        "scenes": [{"id": "s1", "name": "Pause", "values": {}}],
        "roles": ["dimmer", "red", "green", "blue", "pan", "tilt", "generic"],
        "overlaps": overlaps or [],
        "values": {"bar": [255, 0, 0] * 8},
        "brightness": {"bar": 64},
        "dmx": {"service_running": service, "adapter_present": adapter},
        "show_running": show_running,
        "show_state": show_state,
        "show_levels": {"low": 0.8, "mid": 0.4, "high": 0.1, "level": 0.5},
        "show": {
            "channel": 3,
            "sensitivity": 1.5,
            "fallback_scene": "s1",
            "silence_threshold": 0.03,
            "silence_seconds": 8.0,
            "speech_seconds": 15.0,
        },
    }


# ====================================================================
# 1. Eingeschaltet: Karte da, und aus 24 Kanälen werden 8 Segmente
# ====================================================================

ergebnis = ausfuehren(stand(), """function () {
    const karte = document.getElementById('light-card-wrapper');
    const lampen = document.getElementById('light-fixtures');

    return {
        karte_sichtbar: !karte.classList.contains('d-none'),
        farbfelder: lampen.querySelectorAll('input[type=color]').length,
        regler: lampen.querySelectorAll('input[type=range]').length,
        lampenname: lampen.textContent.indexOf('LED-Bar links') >= 0,
        szene: document.getElementById('light-scenes').textContent.indexOf('Pause') >= 0,
        helligkeit: lampen.querySelector('input[type=range]').value,
        schalter: document.getElementById('settings-light-toggle').checked,
        warnung_sichtbar: !document.getElementById('light-warning').classList.contains('d-none')
    };
}""")

assert ergebnis["karte_sichtbar"], "Die Lichtkarte bleibt versteckt."
assert ergebnis["lampenname"], "Die Lampe steht nicht in der Karte."
assert ergebnis["szene"], "Die Szene fehlt in der Karte."
assert ergebnis["schalter"] is True, "Der Schalter in den Einstellungen steht falsch."

#
# Der eigentliche Punkt: Aus 24 Kanaelen duerfen nicht 24 Regler
# werden. Acht Segmente, acht Farbfelder - und genau ein Regler fuer
# die Helligkeit der ganzen Lampe.
#
assert ergebnis["farbfelder"] == 8, (
    f"Erwartet 8 Farbfelder (ein Segment je Dreiergruppe), gefunden: "
    f"{ergebnis['farbfelder']}"
)
assert ergebnis["regler"] == 1, (
    f"Erwartet genau einen Helligkeitsregler, gefunden: {ergebnis['regler']}"
)

#
# Der Regler muss zeigen, was eingestellt ist. Vorher stand dort fest
# 255: Nach jedem Ziehen baut sich die Karte neu auf, und der Regler
# sprang zurueck auf voll - am Geraet genau so aufgefallen.
#
assert ergebnis["helligkeit"] == "64", (
    f"Der Helligkeitsregler zeigt {ergebnis['helligkeit']} statt des "
    f"eingestellten Werts 64."
)

assert not ergebnis["warnung_sichtbar"], (
    "Bei laufendem Dienst und steckendem Kabel darf keine Warnung stehen."
)

print("OK: Die Lichtkarte zeigt aus 24 Kanälen acht Segmente statt 24 Regler")
print("OK: Der Helligkeitsregler zeigt den eingestellten Wert")


# ====================================================================
# 1b. Eine Lampe mit eigenem Dimmerkanal
#
# Der Dimmerkanal wird vom Helligkeitsregler bedient. Ein zweiter
# Regler daneben, der dasselbe tut und dabei ueberschrieben wird,
# waere nur verwirrend.
# ====================================================================

mit_kopf = stand()
mit_kopf["fixtures"] = [
    {"id": "k", "name": "Bewegtlicht", "template": "kopf", "address": 40}
]
mit_kopf["values"] = {"k": [128, 200, 255, 0, 0, 255]}
mit_kopf["brightness"] = {"k": 200}

ergebnis = ausfuehren(mit_kopf, """function () {
    const lampen = document.getElementById('light-fixtures');
    const regler = lampen.querySelectorAll('input[type=range]');

    return {
        farbfelder: lampen.querySelectorAll('input[type=color]').length,
        regler: regler.length,
        beschriftungen: lampen.textContent
    };
}""")

assert ergebnis["farbfelder"] == 1, ergebnis

#
# Helligkeit + Pan + Tilt = drei. Der Dimmerkanal bekommt keinen
# eigenen Regler.
#
assert ergebnis["regler"] == 3, (
    f"Erwartet drei Regler (Helligkeit, Pan, Tilt), gefunden: "
    f"{ergebnis['regler']}"
)

assert "Pan" in ergebnis["beschriftungen"], ergebnis["beschriftungen"]
assert "Tilt" in ergebnis["beschriftungen"], ergebnis["beschriftungen"]

print("OK: Bei einer Lampe mit Dimmerkanal gibt es dafür keinen zweiten Regler")


# ====================================================================
# 2. Ausgeschaltet: keine Karte
# ====================================================================

ergebnis = ausfuehren(stand(enabled=False), """function () {
    return {
        versteckt: document.getElementById('light-card-wrapper')
                           .classList.contains('d-none'),
        schalter: document.getElementById('settings-light-toggle').checked
    };
}""")

assert ergebnis["versteckt"], (
    "Bei ausgeschalteter Lichtsteuerung darf die Karte nicht erscheinen."
)
assert ergebnis["schalter"] is False

print("OK: Ausgeschaltet ist die Karte nicht da")


# ====================================================================
# 3. Warnungen
# ====================================================================

ergebnis = ausfuehren(stand(service=False), """function () {
    const box = document.getElementById('light-warning');
    return { sichtbar: !box.classList.contains('d-none'), text: box.textContent };
}""")

assert ergebnis["sichtbar"], "Ein toter Lichtdienst muss in der Karte stehen."
assert "olad" in ergebnis["text"], ergebnis["text"]

ergebnis = ausfuehren(stand(overlaps=[["a", "b"]]), """function () {
    const box = document.getElementById('light-warning');
    return { sichtbar: !box.classList.contains('d-none'), text: box.textContent };
}""")

assert ergebnis["sichtbar"] and "Kanäle" in ergebnis["text"], ergebnis

print("OK: Fehlender Dienst und überlappende Adressen werden gemeldet")


# ====================================================================
# 4. Öffnet sich der Einrichten-Dialog wirklich?
#
# Das ist die Prüfung, an der 1.8.2 gescheitert wäre: Damals war
# bootstrap.Modal im Test eine wirkungslose Attrappe, und ein Modal,
# das im Browser gar nicht aufging, fiel niemandem auf.
# ====================================================================

ergebnis = ausfuehren(stand(), """function () {
    const dialog = document.getElementById('lightSetupModal');

    return {
        offen: dialog.classList.contains('show'),
        lampen: document.getElementById('light-fixture-list').textContent,
        vorlagen: document.getElementById('light-template-list').textContent,
        auswahl: document.getElementById('light-fixture-template').options.length
    };
}""", vorher="document.getElementById('btn-light-setup').click();")

assert ergebnis["offen"], (
    "Der Einrichten-Dialog geht nicht auf - genau der Fehler aus 1.8.2."
)
assert "LED-Bar links" in ergebnis["lampen"], ergebnis["lampen"]
assert "Bewegtlicht" in ergebnis["vorlagen"], ergebnis["vorlagen"]
assert ergebnis["auswahl"] == 2, (
    f"Die Vorlagenauswahl muss beide Vorlagen anbieten, hat aber "
    f"{ergebnis['auswahl']} Einträge."
)

print("OK: Der Einrichten-Dialog öffnet sich und ist gefüllt")


# ====================================================================
# 5. Die musikgesteuerte Show
# ====================================================================

ergebnis = ausfuehren(stand(show_running=False), """function () {
    return {
        versteckt: document.getElementById('light-show-status')
                           .classList.contains('d-none')
    };
}""")

assert ergebnis["versteckt"], (
    "Ohne laufende Show darf die Pegelanzeige nicht dastehen."
)

ergebnis = ausfuehren(stand(show_running=True), """function () {
    const anzeige = document.getElementById('light-show-status');
    const balken = document.getElementById('light-show-bands')
                           .querySelectorAll('.progress-bar');

    return {
        sichtbar: !anzeige.classList.contains('d-none'),
        zustand: document.getElementById('light-show-state').textContent,
        erfolgsfarbe: document.getElementById('light-show-state')
                              .classList.contains('text-bg-success'),
        balken: balken.length,
        breiten: Array.from(balken).map((b) => b.style.width),
        knopf_aktiv: document.getElementById('btn-light-show')
                             .classList.contains('btn-primary')
    };
}""")

assert ergebnis["sichtbar"], "Bei laufender Show fehlt die Anzeige."
assert ergebnis["zustand"] == "Musik", ergebnis["zustand"]
assert ergebnis["erfolgsfarbe"], "Bei Musik muss der Zustand hervorgehoben sein."
assert ergebnis["knopf_aktiv"], "Der Show-Knopf muss als aktiv zu erkennen sein."

#
# Drei Baender, und die Balken muessen den gemeldeten Pegeln
# entsprechen - sonst sieht man eine Anzeige, die nichts mit dem
# Signal zu tun hat.
#
assert ergebnis["balken"] == 3, ergebnis["balken"]
assert ergebnis["breiten"] == ["80%", "40%", "10%"], ergebnis["breiten"]

print("OK: Bei laufender Show zeigen die Balken die gemeldeten Pegel")

#
# Sprache: Die Show haelt sich heraus, und das soll man sehen.
#
ergebnis = ausfuehren(stand(show_running=True, show_state="speech"), """function () {
    const zustand = document.getElementById('light-show-state');
    return {
        text: zustand.textContent,
        erfolgsfarbe: zustand.classList.contains('text-bg-success')
    };
}""")

assert ergebnis["text"] == "Sprache", ergebnis["text"]
assert not ergebnis["erfolgsfarbe"], (
    "Bei Sprache darf der Zustand nicht wie 'laeuft gut' aussehen."
)

print("OK: Sprache und Stille sind von Musik zu unterscheiden")


# ====================================================================
# 6. Die Show-Einstellungen stehen im Dialog
# ====================================================================

ergebnis = ausfuehren(stand(), """function () {
    const auswahl = document.getElementById('light-show-fallback');

    return {
        kanal: document.getElementById('light-show-channel').value,
        empfindlichkeit: document.getElementById('light-show-sensitivity').value,
        stille: document.getElementById('light-show-silence-seconds').value,
        sprache: document.getElementById('light-show-speech-seconds').value,
        rueckfall: auswahl.value,
        auswahl_erste: auswahl.options[0].textContent,
        auswahl_anzahl: auswahl.options.length
    };
}""")

assert ergebnis["kanal"] == "3", ergebnis
assert ergebnis["empfindlichkeit"] == "1.5", ergebnis
assert ergebnis["stille"] == "8", ergebnis
assert ergebnis["sprache"] == "15", ergebnis

#
# Die Rueckfallszene muss auswaehlbar sein - und "Licht aus" muss es
# als ausdrueckliche Wahl geben, nicht nur als leeres Feld.
#
assert ergebnis["rueckfall"] == "s1", ergebnis
assert ergebnis["auswahl_erste"] == "Licht aus", ergebnis
assert ergebnis["auswahl_anzahl"] == 2, ergebnis

print("OK: Die Show-Einstellungen stehen im Dialog, samt Rückfallszene")


print("Alle Lichtkarten-Tests erfolgreich.")
