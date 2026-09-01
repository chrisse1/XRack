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


#
# Die Auswahl der DMX-Anschluesse, wie /api/lighting/dmx/ports sie
# liefern wuerde.
#
ANSCHLUESSE = {
    "patched": True,
    "ports": [
        {"id": "2-O-0", "device": "FT232R USB UART",
         "description": "Serial: A5", "label": "FT232R USB UART (Ausgang 0)",
         "patched": False},
        {"id": "2-O-1", "device": "FT232R USB UART",
         "description": "Serial: A5", "label": "FT232R USB UART (Ausgang 1)",
         "patched": True},
    ],
}


def seite_bauen(stand: dict, pruefung: str, ports: dict | None = None) -> str:
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
        #
        # Mitgeschrieben wird jeder Aufruf: Nur so laesst sich
        # pruefen, dass ein Knopf wirklich etwas losschickt - und
        # nicht bloss huebsch aussieht.
        #
        "window.aufrufe = [];\n"
        "window.fetch = async (url, optionen) => {\n"
        "  window.aufrufe.push([String(url),\n"
        "    optionen && optionen.body ? String(optionen.body) : '']);\n"
        "  if (String(url).indexOf('/api/lighting/status') === 0)\n"
        "    return { json: async () => (" + json.dumps(stand) + ") };\n"
        "  if (String(url).indexOf('/api/lighting/dmx/ports') === 0)\n"
        "    return { json: async () => ("
        + json.dumps(ports if ports is not None else ANSCHLUESSE) + ") };\n"
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


def ausfuehren(stand: dict, pruefung: str, vorher: str = "",
               ports: dict | None = None) -> dict:
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
        datei.write_text(seite_bauen(stand, rahmen, ports), encoding="utf-8")

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
          show_running=False, show_state="music", patched=True) -> dict:

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
             "template": "bar-8-rgb", "address": 1, "last_address": 24,
             "kind": "background"},
        ],
        "scenes": [{"id": "s1", "name": "Pause", "values": {}}],
        "roles": ["dimmer", "red", "green", "blue", "pan", "tilt", "generic"],
        "overlaps": overlaps or [],
        "values": {"bar": [255, 0, 0] * 8},
        "brightness": {"bar": 64},
        "dmx": {"service_running": service, "adapter_present": adapter,
                "patched": patched},

        #
        # Wie viele Kanaele das Interface hat - daraus baut die
        # Oberflaeche die Auswahl des Kanalpaars.
        #
        "input_channels": 8,
        "show_running": show_running,
        "show_state": show_state,
        "show_stream": show_running,
        "show_blocks": 100 if show_running else 0,
        "show_levels": {"low": 0.8, "mid": 0.4, "high": 0.1, "level": 0.5},
        "show": {
            "channel": 3,
            "effect_mode": "pulse",
            "pulse_seconds": 0.5,
            "pulse_base": 0.2,
            "color_invert": False,
            "invert_beats": 8,
            "snare_strobe": False,
            "snare_sense": 0.5,
            "snare_power": 0.8,
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
assert ergebnis["balken"] == 4, ergebnis["balken"]
#
# Die drei Baender sind schon auf 0-1 normiert und werden linear
# gezeigt. Der Gesamtpegel ist ein echter Pegel und gehoert auf die
# dB-Skala: 0,5 sind -6 dBFS, auf -60..0 dBFS abgebildet also 90 %.
#
assert ergebnis["breiten"] == ["80%", "40%", "10%", "90%"], ergebnis["breiten"]

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

assert ergebnis["kanal"] == "3+4", ergebnis
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


# ====================================================================
# 7. Show laeuft, aber es kommt kein Audio
#
# Das ist ein anderer Fehler als "die Erkennung meint Sprache", und
# er muss auch anders dastehen. Vorher stand in der Karte "Show
# laeuft", waehrend in Wirklichkeit nichts mehr hereinkam - und man
# sucht dann bei der Musik statt beim Eingang.
# ====================================================================

ohne_strom = stand(show_running=True)
ohne_strom["show_stream"] = False
ohne_strom["show_blocks"] = 0

ergebnis = ausfuehren(ohne_strom, """function () {
    const box = document.getElementById('light-warning');
    return { sichtbar: !box.classList.contains('d-none'), text: box.textContent };
}""")

assert ergebnis["sichtbar"], "Fehlendes Audio muss in der Karte stehen."
assert "kein Audio" in ergebnis["text"], ergebnis["text"]

print("OK: Läuft die Show ohne ankommendes Audio, steht das in der Karte")


# ====================================================================
# 8. Ein leiser, aber normaler Ausspielweg muss sichtbar sein
#
# Genau daran ist es am Gerät gescheitert: Der Balken war linear
# skaliert. Ein Ausspielweg bei -42 dBFS - völlig normal, wenn der
# Kanal nicht auf 0 dB steht - ergab damit 0,8 Prozent, also optisch
# nichts. Der Nutzer sah einen Balken, der "gar nicht ausschlug", und
# die Stille-Erkennung hielt laufende Musik für Stille.
# ====================================================================

leise = stand(show_running=True)
leise["show_levels"] = {"low": 0.5, "mid": 0.3, "high": 0.2, "level": 0.008}

ergebnis = ausfuehren(leise, """function () {
    const balken = document.getElementById('light-show-bands')
                           .querySelectorAll('.progress-bar');
    return { gesamt: balken[balken.length - 1].style.width };
}""")

prozent = float(ergebnis["gesamt"].rstrip("%"))

#
# -42 dBFS auf der Skala -60..0 sind rund 30 Prozent. Entscheidend
# ist nicht die genaue Zahl, sondern dass man etwas SIEHT.
#
assert 20 < prozent < 45, (
    f"Ein Signal bei -42 dBFS muss deutlich sichtbar sein, zeigt aber "
    f"{prozent} Prozent."
)

print(f"OK: Ein leiser Ausspielweg (-42 dBFS) ist mit {prozent:.0f} % sichtbar")


# ====================================================================
# 9. Die Stille-Schwelle steht in dB im Dialog
# ====================================================================

in_db = stand()
in_db["show"] = {**in_db["show"], "silence_threshold": 0.002}

ergebnis = ausfuehren(in_db, """function () {
    return {
        regler: document.getElementById('light-show-silence-threshold').value,
        beschriftung: document.getElementById(
            'light-show-silence-threshold-value').textContent
    };
}""")

#
# 0.002 sind rund -54 dBFS.
#
assert ergebnis["regler"] == "-54", ergebnis
assert "dBFS" in ergebnis["beschriftung"], ergebnis

print("OK: Die Stille-Schwelle steht in dBFS - derselben Skala wie am Pult")


# ====================================================================
# 10. Der belegte Kanalbereich steht da, wo man ihn braucht
#
# Nur die Startadresse zu zeigen, heisst: Wer die naechste Lampe
# daneben setzen will, muss Startadresse plus Kanalzahl im Kopf
# rechnen. Bei einem 29-Kanal-Geraet macht man das genau einmal
# falsch.
# ====================================================================

ergebnis = ausfuehren(stand(), """function () {
    return {
        karte: document.getElementById('light-fixtures').textContent,
        liste: document.getElementById('light-fixture-list').textContent
    };
}""")

for wo in ("karte", "liste"):
    assert "DMX 1–24" in ergebnis[wo], (
        f"In der {wo} fehlt der Endkanal: {ergebnis[wo][:200]}"
    )

print("OK: Karte und Liste zeigen den belegten Bereich, nicht nur den Start")


#
# Und beim Eintippen einer neuen Lampe, bevor sie angelegt ist -
# genau dann braucht man die Rechnung ja.
#
ergebnis = ausfuehren(stand(), """function () {
    return { hinweis: document.getElementById(
        'light-fixture-range').textContent };
}""", vorher="""
    const vorlage = document.getElementById('light-fixture-template');
    const adresse = document.getElementById('light-fixture-address');
    vorlage.value = 'bar-8-rgb';
    adresse.value = '100';
    adresse.dispatchEvent(new Event('input'));
""")

assert "100" in ergebnis["hinweis"] and "123" in ergebnis["hinweis"], (
    f"Der Hinweis unter dem Adressfeld rechnet nicht: {ergebnis['hinweis']!r}"
)

print("OK: Beim Anlegen steht schon beim Tippen da, was belegt würde")


# ====================================================================
# 11. Die Lampenliste ist einklappbar
#
# Aus jeder Lampe werden mehrere Regler. Bei einem ganzen Rig
# scrollt man sonst an den Szenen und der Show vorbei, nur um die
# Karte zu ueberblicken.
# ====================================================================

ergebnis = ausfuehren(stand(), """function () {
    const koerper = document.getElementById('light-fixtures-body');

    return {
        offen: koerper.classList.contains('show'),
        zahl: document.getElementById('light-fixtures-count').textContent,
        inhalt: document.getElementById('light-fixtures').textContent
    };
}""")

assert ergebnis["offen"], "Die Liste ist von Haus aus zugeklappt."
assert ergebnis["zahl"] == "1", ergebnis
assert "LED-Bar links" in ergebnis["inhalt"], ergebnis

print("OK: Die Lampenliste ist aufgeklappt und nennt die Anzahl")


#
# Eingeklappt darf die Zahl nicht verschwinden - sonst waere nicht
# zu sehen, ob dort unten ueberhaupt etwas ist.
#
ergebnis = ausfuehren(stand(), """function () {
    const koerper = document.getElementById('light-fixtures-body');

    return {
        offen: koerper.classList.contains('show'),
        zahl: document.getElementById('light-fixtures-count').textContent,
        pfeil: document.getElementById('light-fixtures-chevron').className
    };
}""", vorher="document.getElementById('btn-light-fixtures-toggle').click();")

assert not ergebnis["offen"], "Der Knopf klappt die Liste nicht zu."
assert ergebnis["zahl"] == "1", ergebnis
assert "chevron-right" in ergebnis["pfeil"], ergebnis

print("OK: Zugeklappt bleibt die Anzahl stehen, der Pfeil dreht sich")


# ====================================================================
# 12. Eingeklappt wird nicht neu gezeichnet, und ein Regler wird
#     einem nicht unterm Finger weggezogen
#
# Der Neuaufbau wirft die Regler weg und erzeugt sie neu. Waehrend
# der Show passiert das zweimal pro Sekunde - wer gerade zieht,
# verliert den Regler mitten in der Bewegung.
# ====================================================================

ergebnis = ausfuehren(stand(show_running=True), """function () {
    return {
        gleich: window.__merker ===
            document.querySelector('#light-fixtures input[type=range]')
    };
}""", vorher="""
    const regler = document.querySelector('#light-fixtures input[type=range]');
    window.__merker = regler;
    regler.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    renderLighting(lightState);
""")

assert ergebnis["gleich"], (
    "Der Regler wurde beim Neuzeichnen ersetzt, obwohl gerade jemand "
    "darauf gedrückt hat."
)

print("OK: Wer einen Regler anfasst, behält ihn auch während der Show")


#
# Und eingeklappt wird gar nicht erst gezeichnet.
#
ergebnis = ausfuehren(stand(show_running=True), """function () {
    return { gleich: window.__merker ===
        document.querySelector('#light-fixtures input[type=range]') };
}""", vorher="""
    document.getElementById('light-fixtures-body').classList.remove('show');
    window.__merker = document.querySelector('#light-fixtures input[type=range]');
    renderLighting(lightState);
""")

assert ergebnis["gleich"], "Eingeklappt wird trotzdem neu gezeichnet."

print("OK: Eingeklappt wird die Liste nicht mehr neu aufgebaut")


#
# Kommt aber eine Lampe dazu, muss neu gezeichnet werden - auch
# eingeklappt und auch mitten im Ziehen. Sonst zeigt die Liste beim
# Aufklappen etwas, das es nicht mehr gibt.
#
#
# Wichtig ist die Reihenfolge: Erst EINMAL zeichnen (dabei merkt
# sich die Karte den Fingerabdruck), dann die Lampe dazunehmen.
# Prueft man es andersherum, zeichnet ohnehin der erste Aufruf
# alles - und der Test beweist nichts.
#
ergebnis = ausfuehren(stand(), """function () {
    return { inhalt: document.getElementById('light-fixtures').textContent };
}""", vorher="""
    const regler = document.querySelector('#light-fixtures input[type=range]');
    regler.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    document.getElementById('light-fixtures-body').classList.remove('show');

    const neu = JSON.parse(JSON.stringify(lightState));
    neu.fixtures.push({
        id: 'kopf1', name: 'Bewegtlicht', template: 'kopf',
        address: 100, last_address: 105
    });

    renderLighting(neu);
""")

assert "Bewegtlicht" in ergebnis["inhalt"], (
    "Eine neue Lampe taucht nicht auf: " + ergebnis["inhalt"][:200]
)

print("OK: Eine neue Lampe erscheint trotzdem sofort")


# ====================================================================
# 13. Die Art einer Lampe steht in der Karte und ist änderbar
#
# Vor allem "ausgenommen" muss sichtbar sein: Sonst wundert man sich,
# warum genau diese eine Lampe bei der Show nicht mitmacht, und sucht
# den Fehler im Gerät.
# ====================================================================

ergebnis = ausfuehren(stand(), """function () {
    const zeile = document.querySelector('#light-fixture-list select');

    return {
        karte: document.getElementById('light-fixtures').textContent,
        zeilenwert: zeile ? zeile.value : null,
        zeilenarten: zeile
            ? Array.from(zeile.options).map((o) => o.value) : [],
        anlegen: Array.from(
            document.getElementById('light-fixture-kind').options
        ).map((o) => o.value)
    };
}""", vorher="document.getElementById('btn-light-setup').click();")

assert TEXTE["light_kind_background"] in ergebnis["karte"], (
    "Die Art fehlt in der Karte: " + ergebnis["karte"][:200]
)

#
# Beide Felder müssen DIESELBEN Arten anbieten. Sie standen einmal an
# zwei Stellen im Code, und beim Anlegen der zweiten Hintergrundgruppe
# wurde prompt eine davon vergessen - genau das fällt hier auf.
#
assert ergebnis["anlegen"] == ergebnis["zeilenarten"], ergebnis
assert ergebnis["anlegen"] == [
    "effect", "background", "background2", "static",
], ergebnis

#
# Und die Zeile der vorhandenen Lampe zeigt DEREN Art vorausgewählt -
# nicht stumpf die erste. Sonst verstellte ein unbedachter Klick die
# Lampe, statt sie zu lassen, wie sie ist.
#
assert ergebnis["zeilenwert"] == "background", ergebnis

print("OK: Die Art steht in der Karte und ist an der Lampe vorausgewählt")


#
# Der Regler für die Trägheit zeigt seinen Wert in Sekunden an.
#
traege = stand()
traege["show"] = {**traege["show"], "background_seconds": 9}

ergebnis = ausfuehren(traege, """function () {
    return {
        regler: document.getElementById('light-show-background-seconds').value,
        beschriftung: document.getElementById(
            'light-show-background-seconds-value').textContent
    };
}""")

assert ergebnis["regler"] == "9", ergebnis
assert "9 s" in ergebnis["beschriftung"], ergebnis

print("OK: Die Trägheit des Hintergrundlichts steht in Sekunden im Dialog")


# ====================================================================
# 14. Der Hinweis, wenn die Blende die Standzeit überholt
#
# Dauert die Blende länger als die halbe Standzeit, kommt keine Farbe
# mehr rein an - es steht dauerhaft ein Mittelton da. Das ist genau
# der Effekt, wegen dem der Farbwechsel überhaupt gebaut wurde, und
# er lässt sich mit zwei Reglern versehentlich wiederherstellen.
# ====================================================================

gut = stand()
gut["show"] = {**gut["show"], "background_seconds": 2, "background_beats": 16}

ergebnis = ausfuehren(gut, """function () {
    const hinweis = document.getElementById('light-show-background-warning');
    return {
        versteckt: hinweis.classList.contains('d-none'),
        takte: document.getElementById(
            'light-show-background-beats-value').textContent
    };
}""")

assert ergebnis["versteckt"], (
    "Bei brauchbaren Werten darf kein Hinweis stehen: " + str(ergebnis)
)
assert "16" in ergebnis["takte"], ergebnis

schlecht = stand()
schlecht["show"] = {**schlecht["show"],
                    "background_seconds": 12, "background_beats": 4}

ergebnis = ausfuehren(schlecht, """function () {
    const hinweis = document.getElementById('light-show-background-warning');
    return {
        versteckt: hinweis.classList.contains('d-none'),
        text: hinweis.textContent
    };
}""")

assert not ergebnis["versteckt"], (
    "12 s Blende bei 4 Schlägen Standzeit muss gemeldet werden."
)
assert "Mittelton" in ergebnis["text"], ergebnis

print("OK: Eine zu lange Blende wird gemeldet, brauchbare Werte nicht")


# ====================================================================
# 15. Der Regler für die Blende
# ====================================================================

blende = stand()
blende["show"] = {**blende["show"], "fade_seconds": 3.5}

ergebnis = ausfuehren(blende, """function () {
    return {
        regler: document.getElementById('light-show-fade-seconds').value,
        beschriftung: document.getElementById(
            'light-show-fade-seconds-value').textContent
    };
}""")

assert ergebnis["regler"] == "3.5", ergebnis
assert "3.5 s" in ergebnis["beschriftung"], ergebnis

print("OK: Die Ausblendzeit steht in Sekunden im Dialog")


# ====================================================================
# 16. Die Auswahlfelder im Einrichten-Dialog bleiben offen
#
# Am Geraet gemeldet: "Die Dropdowns unter Lampen im Einstellungen
# Modal bleiben nicht offen. Man kann also bei bereits angelegten
# Lichtern den Modus nicht mehr aendern."
#
# Der Dialog wurde bei JEDEM Statusabruf neu aufgebaut, waehrend der
# Show also zweimal pro Sekunde. Ein geoeffnetes Auswahlfeld wurde
# dabei mitsamt seinem DOM-Knoten weggeworfen.
#
# Geprueft wird am KNOTEN, nicht am sichtbaren Inhalt: Der saehe nach
# einem Neuaufbau genauso aus, und genau daran waere der Test
# vorbeigelaufen.
# ====================================================================

ergebnis = ausfuehren(stand(show_running=True), """function () {
    return {
        gleich: window.__merker ===
            document.querySelector('#light-fixture-list select'),
        gefunden: !!document.querySelector('#light-fixture-list select')
    };
}""", vorher="""
    document.getElementById('btn-light-setup').click();
    window.__merker = document.querySelector('#light-fixture-list select');
    renderLighting(lightState);
    renderLighting(lightState);
""")

assert ergebnis["gefunden"], "Die Lampenzeile hat gar kein Auswahlfeld."
assert ergebnis["gleich"], (
    "Das Auswahlfeld wurde beim Neuzeichnen ersetzt - ein geöffnetes "
    "Dropdown klappt damit zu."
)

print("OK: Das Auswahlfeld in der Lampenliste überlebt das Neuzeichnen")


#
# Aendert sich aber die Art einer Lampe, MUSS neu gezeichnet werden -
# sonst bliebe die Rueckmeldung aus, und man wuesste nicht, ob die
# Aenderung angekommen ist.
#
ergebnis = ausfuehren(stand(), """function () {
    const feld = document.querySelector('#light-fixture-list select');
    return { wert: feld ? feld.value : null };
}""", vorher="""
    //
    // Ohne den Dialog zu oeffnen: Das Oeffnen stoesst selbst einen
    // Statusabruf an, der asynchron mit dem urspruenglichen Zustand
    // zurueckkommt und das geaenderte Bild wieder ueberschreiben
    // wuerde. Die Liste steht ohnehin im DOM.
    //
    renderLighting(lightState);

    const neu = JSON.parse(JSON.stringify(lightState));
    neu.fixtures[0].kind = 'static';
    renderLighting(neu);
""")

assert ergebnis["wert"] == "static", (
    f"Nach einer Änderung wird nicht neu gezeichnet: {ergebnis}"
)

print("OK: Eine geänderte Art wird sofort im Feld angezeigt")


# ====================================================================
# 17. Die Quelle der Lichtshow als Auswahl, Überschriften, drei
#     Farbblöcke
# ====================================================================

ergebnis = ausfuehren(stand(), """function () {
    const kanal = document.getElementById('light-show-channel');

    return {
        art: kanal.tagName,
        gruppen: Array.from(kanal.querySelectorAll('optgroup')).map(
            (g) => g.label),
        paare: Array.from(
            kanal.querySelectorAll('optgroup:nth-of-type(1) option')
        ).map((o) => o.value),
        einzeln: Array.from(
            kanal.querySelectorAll('optgroup:nth-of-type(2) option')
        ).map((o) => o.value),
        texte: Array.from(kanal.options).map((o) => o.textContent),
        gewaehlt: kanal.value,
        text: document.getElementById('lightSetupModal').textContent,
        farben: document.querySelectorAll(
            '#lightSetupModal input[type=color]').length
    };
}""")

#
# Acht Kanaele ergeben genau vier Paare - keine krummen Reste, und
# der letzte ist 7+8 - und acht einzelne Kanaele.
#
assert ergebnis["art"] == "SELECT", (
    "Die Quelle ist noch ein Eingabefeld: " + ergebnis["art"]
)

assert ergebnis["gruppen"] == [
    TEXTE["light_show_channel_pairs"],
    TEXTE["light_show_channel_single"],
], ergebnis["gruppen"]

assert ergebnis["paare"] == ["1+2", "3+4", "5+6", "7+8"], ergebnis["paare"]

assert ergebnis["einzeln"] == ["1", "2", "3", "4", "5", "6", "7", "8"], (
    ergebnis["einzeln"]
)

assert ergebnis["texte"][0] == TEXTE["channel_option"].replace(
    "{a}", "1").replace("{b}", "2"), ergebnis["texte"]
assert ergebnis["texte"][3] == TEXTE["channel_option"].replace(
    "{a}", "7").replace("{b}", "8"), ergebnis["texte"]
assert ergebnis["texte"][-1] == TEXTE["channel_option_mono"].replace(
    "{n}", "8"), ergebnis["texte"]

#
# Und der gespeicherte Wert ist vorgewaehlt - im Attrappenzustand
# steht Kanal 3 ohne Mono, also das Paar 3+4.
#
assert ergebnis["gewaehlt"] == "3+4", ergebnis["gewaehlt"]

print("OK: Die Quelle wird ausgewählt statt eingetippt - Paare und Einzelkanäle")

#
# Aus demselben Durchlauf geholt und weiter unten geprueft: Der
# Dialog wird hier nur einmal geladen.
#
dialog = ergebnis


#
# Steht in der Ablage ein einzelner Kanal, zeigt die Auswahl genau
# den an - und nicht das Paar, das zufaellig dieselbe Zahl traegt.
#
mono_stand = stand()
mono_stand["show"]["channel_mono"] = True

ergebnis = ausfuehren(mono_stand, """function () {
    const kanal = document.getElementById('light-show-channel');
    return { gewaehlt: kanal.value, text: kanal.selectedOptions[0].textContent };
}""")

assert ergebnis["gewaehlt"] == "3", (
    "Ein gespeicherter Einzelkanal wird nicht angezeigt: " + str(ergebnis)
)

assert ergebnis["text"] == TEXTE["channel_option_mono"].replace("{n}", "3"), (
    ergebnis["text"]
)

print("OK: Ein gespeicherter Einzelkanal steht auch in der Auswahl")


#
# Und beim Speichern wird die Kodierung wieder zerlegt: "5" ist der
# einzelne Kanal 5, "5+6" das Paar ab 5. Beide Angaben muessen
# zusammen passen - eine allein reicht nicht.
#
for wert, kanal, mono in (("5", 5, True), ("5+6", 5, False)):

    ergebnis = ausfuehren(stand(), """function () {
        const gesendet = window.aufrufe.filter(
            a => a[0].indexOf('/api/lighting/show/settings') === 0
        );

        return {
            anzahl: gesendet.length,
            koerper: gesendet.length ? gesendet[gesendet.length - 1][1] : ''
        };
    }""", vorher="""
        document.getElementById('light-show-channel').value = '""" + wert + """';
        saveLightShowSettings();
    """)

    assert ergebnis["anzahl"] >= 1, ergebnis

    koerper = ergebnis["koerper"].replace(" ", "")

    assert f'"channel":{kanal}' in koerper, (
        f"Aus '{wert}' wird nicht Kanal {kanal}: {koerper}"
    )

    assert f'"channel_mono":{str(mono).lower()}' in koerper, (
        f"Aus '{wert}' wird nicht channel_mono={mono}: {koerper}"
    )

print("OK: Die Auswahl wird beim Speichern richtig herum zerlegt")


#
# Die Sperre gegen das Neuaufbauen: Ein Auswahlfeld, das sich
# zweimal je Sekunde neu aufbaut, klappt beim Anklicken zu - und
# spraenge nebenbei auf den gespeicherten Wert zurueck, waehrend man
# gerade einen anderen sucht.
#
ergebnis = ausfuehren(stand(), """function () {
    return { wert: document.getElementById('light-show-channel').value };
}""", vorher="""
    //
    // Mit dem Finger drauf: Ein Feld, in dem gerade jemand waehlt,
    // laesst renderLighting() in Ruhe. Was es dann noch umwerfen
    // koennte, ist einzig ein Neuaufbau der Liste - und genau der
    // wird hier geprueft.
    //
    const feld = document.getElementById('light-show-channel');
    feld.focus();
    feld.value = '6';
    renderLighting(lightState);
""")

assert ergebnis["wert"] == "6", (
    "Die Auswahl wird bei jedem Statusabruf neu aufgebaut und springt "
    "zurück: " + str(ergebnis)
)

print("OK: Die Auswahl baut sich nicht bei jedem Statusabruf neu auf")

#
# Die beiden Ueberschriften ueber den Anlege-Feldern.
#
for schluessel in ("light_fixture_new", "light_template_new"):
    assert TEXTE[schluessel] in dialog["text"], (
        f"Die Überschrift '{TEXTE[schluessel]}' fehlt im Dialog."
    )

print("OK: Über den Anlege-Feldern stehen Überschriften")

#
# Drei Farbsaetze zu je drei Waehlern.
#
assert dialog["farben"] == 9, (
    f"Es sind nicht neun Farbwähler, sondern {dialog['farben']}."
)

print("OK: Es gibt neun Farbwähler in drei Blöcken")


#
# Und die drei Ueberschriften der Farbbloecke benennen, wofuer sie
# gelten - das war der Anlass: "Farben der Frequenzbereiche" galt
# stillschweigend fuer Effektlicht UND Hintergrund 1.
#
ergebnis = ausfuehren(stand(), """function () {
    return { text: document.getElementById('lightSetupModal').textContent };
}""")

for schluessel in ("light_show_colors", "light_show_colors_1",
                   "light_show_colors_2"):
    assert TEXTE[schluessel] in ergebnis["text"], (
        f"Die Überschrift '{TEXTE[schluessel]}' fehlt."
    )

print("OK: Jeder Farbblock sagt, für welche Lampenart er gilt")


# ====================================================================
# 18. Der dBFS-Hinweis steht unter den Pegelbalken
#
# Er stand als Textschluessel im Programm, aber in keiner Vorlage.
# Ohne ihn haelt man 0.02 fuer "ein bisschen" statt fuer -34 dBFS und
# wundert sich, warum die Show bei normal laufender Musik auf die
# Rueckfallszene springt - genau das ist am Geraet passiert.
# ====================================================================

ergebnis = ausfuehren(stand(show_running=True), """function () {
    return { text: document.getElementById('light-show-status').textContent };
}""")

assert TEXTE["light_show_level_hint"] in ergebnis["text"], (
    "Der dBFS-Hinweis fehlt unter den Pegelbalken: " + ergebnis["text"][:200]
)

print("OK: Unter den Pegelbalken steht, dass die Skala dBFS ist")


# ====================================================================
# 19. Der DMX-Ausgang laesst sich aus den Einstellungen zuordnen
#
# Ohne Zuordnung sieht von aussen alles heil aus: Dienst laeuft,
# Kabel steckt, XRack meldet gesendete Bilder - und es bleibt dunkel.
# Das muss in der Karte stehen, und der Schritt muss ohne Terminal
# nachzuholen sein.
# ====================================================================

ergebnis = ausfuehren(stand(patched=False), """function () {
    const box = document.getElementById('light-warning');
    return { sichtbar: !box.classList.contains('d-none'), text: box.textContent };
}""")

assert ergebnis["sichtbar"], "Ein fehlender DMX-Ausgang muss in der Karte stehen."
assert "DMX-Ausgang" in ergebnis["text"], ergebnis["text"]

print("OK: Ist kein DMX-Ausgang zugeordnet, steht das in der Lichtkarte")


#
# Und jetzt der Weg dorthin: Einstellungen oeffnen, Auswahl fuellen.
#
ergebnis = ausfuehren(
    stand(patched=False),
    """function () {
        const auswahl = document.getElementById('settings-light-port');
        const zustand = document.getElementById('settings-light-port-state');

        return {
            anzahl: auswahl.options.length,
            gewaehlt: auswahl.value,
            erster: auswahl.options[0] ? auswahl.options[0].textContent : '',
            zustand: zustand.textContent,
            knopf_aus: document.getElementById('btn-light-port-patch').disabled
        };
    }""",
    vorher=(
        "bootstrap.Modal.getOrCreateInstance("
        "document.getElementById('settingsModal')).show();"
    ),
)

assert ergebnis["anzahl"] == 2, ergebnis
assert ergebnis["erster"] == "FT232R USB UART (Ausgang 0)", ergebnis

#
# Vorgewaehlt gehoert der Anschluss, auf den XRack schon sendet -
# sonst zeigt die Auswahl auf etwas anderes als die Wirklichkeit,
# und ein unbedachter Klick auf "Zuordnen" legt das Kabel um.
#
assert ergebnis["gewaehlt"] == "2-O-1", ergebnis
assert "Ausgang 1" in ergebnis["zustand"], ergebnis
assert ergebnis["knopf_aus"] is False, ergebnis

print("OK: Die Einstellungen zeigen die Anschlüsse und den zugeordneten")


#
# Der Knopf muss auch wirklich etwas losschicken.
#
ergebnis = ausfuehren(
    stand(patched=False),
    """function () {
        const patch = window.aufrufe.filter(
            a => a[0].indexOf('/api/lighting/dmx/patch') === 0
        );

        return { anzahl: patch.length, koerper: patch.length ? patch[0][1] : '' };
    }""",
    vorher=(
        "bootstrap.Modal.getOrCreateInstance("
        "document.getElementById('settingsModal')).show();"
        "setTimeout(() => "
        "document.getElementById('btn-light-port-patch').click(), 400);"
    ),
)

assert ergebnis["anzahl"] >= 1, "Der Knopf hat nichts losgeschickt."
assert '"port"' in ergebnis["koerper"], ergebnis
assert "2-O-1" in ergebnis["koerper"], ergebnis

print("OK: \"Zuordnen\" schickt den gewählten Anschluss zum Server")


#
# Bietet olad gar nichts an, darf der Knopf nicht klickbar sein -
# sonst schickt man ins Leere und bekommt eine Fehlermeldung, die
# nichts erklaert.
#
ergebnis = ausfuehren(
    stand(patched=False),
    """function () {
        return {
            anzahl: document.getElementById('settings-light-port').options.length,
            knopf_aus: document.getElementById('btn-light-port-patch').disabled,
            zustand: document.getElementById('settings-light-port-state').textContent
        };
    }""",
    vorher=(
        "bootstrap.Modal.getOrCreateInstance("
        "document.getElementById('settingsModal')).show();"
    ),
    ports={"patched": False, "ports": []},
)

assert ergebnis["anzahl"] == 0, ergebnis
assert ergebnis["knopf_aus"] is True, ergebnis
assert ergebnis["zustand"] == TEXTE["light_output_none"], ergebnis

print("OK: Ohne angebotene Anschlüsse bleibt der Knopf gesperrt")


# ====================================================================
# 20. Das Bild der Show laesst sich umschalten
#
# Der zweite Modus nuetzt nichts, wenn man nicht an ihn herankommt -
# und die Auswahl nuetzt nichts, wenn sie beim Umstellen nichts
# losschickt.
# ====================================================================

ergebnis = ausfuehren(stand(), """function () {
    const feld = document.getElementById('light-show-effect-mode');

    return {
        art: feld.tagName,
        werte: Array.from(feld.options).map((o) => o.value),
        texte: Array.from(feld.options).map((o) => o.textContent.trim()),
        gewaehlt: feld.value
    };
}""")

assert ergebnis["art"] == "SELECT", ergebnis
assert ergebnis["werte"] == ["runner", "pulse"], ergebnis

assert ergebnis["texte"] == [
    TEXTE["light_show_effect_mode_runner"],
    TEXTE["light_show_effect_mode_pulse"],
], ergebnis

#
# Der gespeicherte Modus muss auch dastehen. Zeigte die Auswahl
# stumm den ersten Eintrag, glaubte man, es sei Lauflicht
# eingestellt - waehrend die Show pulst.
#
assert ergebnis["gewaehlt"] == "pulse", ergebnis

print("OK: Das Bild der Show steht als Auswahl im Dialog")


ergebnis = ausfuehren(stand(), """function () {
    const gesendet = window.aufrufe.filter(
        a => a[0].indexOf('/api/lighting/show/settings') === 0
    );

    return {
        anzahl: gesendet.length,
        koerper: gesendet.length ? gesendet[gesendet.length - 1][1] : ''
    };
}""", vorher="""
    const feld = document.getElementById('light-show-effect-mode');
    feld.value = 'runner';
    feld.dispatchEvent(new Event('change'));
""")

assert ergebnis["anzahl"] >= 1, "Das Umstellen hat nichts losgeschickt."
assert '"effect_mode":"runner"' in ergebnis["koerper"].replace(" ", ""), (
    ergebnis["koerper"]
)

print("OK: Ein umgestelltes Bild wird sofort gespeichert")


# ====================================================================
# 21. Die zwei Schrauben am Puls
#
# Sie stehen nur da, wenn der Puls auch gewaehlt ist - im Lauflicht
# waeren es zwei Regler ohne Wirkung, und wer an ihnen dreht, sucht
# den Fehler danach bei den Lampen.
# ====================================================================

pulsstand = stand()
lauflichtstand = stand()
lauflichtstand["show"] = {**lauflichtstand["show"], "effect_mode": "runner"}

pruefung = """function () {
    const block = document.getElementById('light-show-pulse-options');

    return {
        sichtbar: !block.classList.contains('d-none'),
        nachleuchten: document.getElementById('light-show-pulse-seconds').value,
        boden: document.getElementById('light-show-pulse-base').value,
        nachtext: document.getElementById(
            'light-show-pulse-seconds-value').textContent,
        bodentext: document.getElementById(
            'light-show-pulse-base-value').textContent
    };
}"""

ergebnis = ausfuehren(pulsstand, pruefung)

assert ergebnis["sichtbar"], "Beim Puls müssen die beiden Regler dastehen."

#
# Und sie muessen den gespeicherten Stand zeigen. Stuenden sie stumm
# auf ihrem Anfangswert, glaubte man, es sei etwas anderes
# eingestellt, als die Show faehrt.
#
assert float(ergebnis["nachleuchten"]) == 0.5, ergebnis
assert float(ergebnis["boden"]) == 0.2, ergebnis

assert ergebnis["nachtext"] == "0.5 s", ergebnis
assert ergebnis["bodentext"] == "20 %", ergebnis

print("OK: Beim Puls stehen Nachleuchten und Grundhelligkeit im Dialog")


ergebnis = ausfuehren(lauflichtstand, pruefung)

assert not ergebnis["sichtbar"], (
    "Im Lauflicht dürfen die Puls-Regler nicht dastehen."
)

print("OK: Im Lauflicht sind sie weg")


#
# Umgestellt wird der Block sofort sichtbar - nicht erst, wenn der
# gespeicherte Stand vom Server zurueckkommt.
#
# Gemessen wird UNMITTELBAR nach dem Umstellen und in einem Merker
# abgelegt. Spaeter nachzusehen ginge daneben: Das Umstellen stoesst
# ein Speichern an, darauf folgt ein Statusabruf, und der bringt hier
# den nachgestellten - also unveraenderten - Stand zurueck.
#
ergebnis = ausfuehren(lauflichtstand, """function () {
    return { sichtbar: window.__sofort };
}""", vorher="""
    const feld = document.getElementById('light-show-effect-mode');
    feld.value = 'pulse';
    feld.dispatchEvent(new Event('change'));

    window.__sofort = !document.getElementById(
        'light-show-pulse-options').classList.contains('d-none');
""")

assert ergebnis["sichtbar"], (
    "Nach dem Umstellen auf Puls müssen die Regler sofort erscheinen."
)

print("OK: Beim Umstellen erscheinen sie sofort")


#
# Und ein verschobener Regler muss ankommen.
#
ergebnis = ausfuehren(pulsstand, """function () {
    const gesendet = window.aufrufe.filter(
        a => a[0].indexOf('/api/lighting/show/settings') === 0
    );

    return {
        anzahl: gesendet.length,
        koerper: gesendet.length ? gesendet[gesendet.length - 1][1] : ''
    };
}""", vorher="""
    const boden = document.getElementById('light-show-pulse-base');
    boden.value = '0.6';
    boden.dispatchEvent(new Event('change'));
""")

assert ergebnis["anzahl"] >= 1, "Der Regler hat nichts losgeschickt."

assert '"pulse_base":0.6' in ergebnis["koerper"].replace(" ", ""), (
    ergebnis["koerper"]
)

print("OK: Ein verschobener Regler wird sofort gespeichert")


# ====================================================================
# 22. Der Blitz auf die Snare
#
# Aus als Vorgabe - und die zwei Regler stehen erst da, wenn er an
# ist.
# ====================================================================

pruefung = """function () {
    const schalter = document.getElementById('light-show-snare-strobe');
    const block = document.getElementById('light-show-snare-options');

    return {
        an: schalter.checked,
        sichtbar: !block.classList.contains('d-none'),
        schwelle: document.getElementById('light-show-snare-sense').value,
        staerke: document.getElementById('light-show-snare-power').value,
        schwellentext: document.getElementById(
            'light-show-snare-sense-value').textContent,
        staerketext: document.getElementById(
            'light-show-snare-power-value').textContent
    };
}"""

ergebnis = ausfuehren(stand(), pruefung)

assert ergebnis["an"] is False, "Der Blitz muss ausgeschaltet dastehen."
assert not ergebnis["sichtbar"], "Ausgeschaltet gehören die Regler weg."

print("OK: Der Blitz steht aus im Dialog, ohne Regler")


mit_blitz = stand()
mit_blitz["show"] = {**mit_blitz["show"], "snare_strobe": True,
                     "snare_sense": 0.7, "snare_power": 0.6}

ergebnis = ausfuehren(mit_blitz, pruefung)

assert ergebnis["an"] is True, ergebnis
assert ergebnis["sichtbar"], "Eingeschaltet müssen die Regler dastehen."
assert float(ergebnis["schwelle"]) == 0.7, ergebnis
assert float(ergebnis["staerke"]) == 0.6, ergebnis
assert ergebnis["schwellentext"] == "70 %", ergebnis
assert ergebnis["staerketext"] == "60 %", ergebnis

print("OK: Eingeschaltet stehen Schwelle und Stärke mit ihrem Wert da")


#
# Umgelegt erscheinen die Regler sofort - gemessen unmittelbar nach
# dem Klick, aus demselben Grund wie beim Puls-Modus.
#
ergebnis = ausfuehren(stand(), """function () {
    return { sichtbar: window.__sofort, gesendet: window.__gesendet };
}""", vorher="""
    const schalter = document.getElementById('light-show-snare-strobe');
    schalter.checked = true;
    schalter.dispatchEvent(new Event('change'));

    window.__sofort = !document.getElementById(
        'light-show-snare-options').classList.contains('d-none');

    window.__gesendet = window.aufrufe.filter(
        a => a[0].indexOf('/api/lighting/show/settings') === 0
    ).map(a => a[1]).join('|');
""")

assert ergebnis["sichtbar"], (
    "Nach dem Einschalten müssen die Regler sofort erscheinen."
)

assert '"snare_strobe":true' in ergebnis["gesendet"].replace(" ", ""), (
    ergebnis["gesendet"]
)

print("OK: Eingeschaltet erscheinen sie sofort und werden gespeichert")


#
# Und die beiden Regler darunter muessen ihren Wert mitschicken.
#
ergebnis = ausfuehren(mit_blitz, """function () {
    const gesendet = window.aufrufe.filter(
        a => a[0].indexOf('/api/lighting/show/settings') === 0
    );

    return { koerper: gesendet.length ? gesendet[gesendet.length - 1][1] : '' };
}""", vorher="""
    const regler = document.getElementById('light-show-snare-sense');
    regler.value = '0.85';
    regler.dispatchEvent(new Event('change'));
""")

koerper = ergebnis["koerper"].replace(" ", "")

assert '"snare_sense":0.85' in koerper, koerper

print("OK: Ein verschobener Empfindlichkeitsregler wird gespeichert")


# ====================================================================
# 23. Die Farbumkehr
#
# Aus als Vorgabe, und der Regler fuer die Schlaege steht erst da,
# wenn sie an ist.
# ====================================================================

pruefung = """function () {
    const schalter = document.getElementById('light-show-color-invert');
    const block = document.getElementById('light-show-invert-options');

    return {
        an: schalter.checked,
        sichtbar: !block.classList.contains('d-none'),
        schlaege: document.getElementById('light-show-invert-beats').value,
        text: document.getElementById('light-show-invert-beats-value').textContent
    };
}"""

ergebnis = ausfuehren(stand(), pruefung)

assert ergebnis["an"] is False, "Die Umkehr muss ausgeschaltet dastehen."
assert not ergebnis["sichtbar"], "Ausgeschaltet gehört der Regler weg."

print("OK: Die Farbumkehr steht aus im Dialog, ohne Regler")


mit_umkehr = stand()
mit_umkehr["show"] = {**mit_umkehr["show"], "color_invert": True,
                      "invert_beats": 12}

ergebnis = ausfuehren(mit_umkehr, pruefung)

assert ergebnis["an"] is True, ergebnis
assert ergebnis["sichtbar"], "Eingeschaltet muss der Regler dastehen."
assert ergebnis["schlaege"] == "12", ergebnis

assert ergebnis["text"] == TEXTE["light_show_beats_unit"].replace("{n}", "12"), (
    ergebnis["text"]
)

print("OK: Eingeschaltet steht der Regler mit seinem Wert da")


#
# Umgelegt erscheint der Regler sofort, und beides wird gespeichert.
#
ergebnis = ausfuehren(stand(), """function () {
    return { sichtbar: window.__sofort, gesendet: window.__gesendet };
}""", vorher="""
    const schalter = document.getElementById('light-show-color-invert');
    schalter.checked = true;
    schalter.dispatchEvent(new Event('change'));

    window.__sofort = !document.getElementById(
        'light-show-invert-options').classList.contains('d-none');

    const regler = document.getElementById('light-show-invert-beats');
    regler.value = '24';
    regler.dispatchEvent(new Event('change'));

    window.__gesendet = window.aufrufe.filter(
        a => a[0].indexOf('/api/lighting/show/settings') === 0
    ).map(a => a[1]).join('|');
""")

assert ergebnis["sichtbar"], (
    "Nach dem Einschalten muss der Regler sofort erscheinen."
)

gesendet = ergebnis["gesendet"].replace(" ", "")

assert '"color_invert":true' in gesendet, gesendet
assert '"invert_beats":24' in gesendet, gesendet

print("OK: Umkehr und Schlagzahl werden sofort gespeichert")


print("Alle Lichtkarten-Tests erfolgreich.")
