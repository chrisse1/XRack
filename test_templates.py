#!/usr/bin/env python3
"""
Prueft den Aufbau der Jinja-Vorlagen.

Anlass: Beim Umbau des Einstellungen-Menues auf Themengruppen (1.8.1)
fehlte eine schliessende </div>. Der modal-body blieb offen und
verschluckte alles Nachfolgende - darunter das PIN-Modal, das dadurch
INNERHALB des Einstellungen-Modals landete. Die PIN-Abfrage ist aber
das Tor davor: Sie wird zuerst geoeffnet, und ihr Dialog steckte damit
in einem Elternelement, das noch auf display:none stand. Auf dem
Geraet sah das so aus, dass sich der Bildschirm nur abdunkelte.

Was das nicht gefangen hat, und warum es hier steht:

  - Zaehlen von <div> gegen </div> im eingefuegten Stueck: Das war
    ausgeglichen. Die Klammerung stimmte innerhalb des Stuecks, nur
    nicht gegenueber der Umgebung.
  - Jinja-Uebersetzung: Fuer Jinja ist HTML nur Text.
  - Der Browser-Test: Er hatte bootstrap.Modal als Attrappe ohne
    Wirkung - ein kaputtes Modal konnte dort gar nicht auffallen.

Deshalb wird hier der Baum geparst und die Verschachtelung geprueft,
nicht die Anzahl der Klammern.
"""

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

VORLAGEN = Path(__file__).parent / "web" / "templates"

#
# Tags ohne schliessendes Gegenstueck.
#
LEER = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


def ohne_jinja(text: str) -> str:
    """Jinja-Ausdruecke entfernen - fuer den Aufbau zaehlt nur das HTML."""

    text = re.sub(r"\{#.*?#\}", "", text, flags=re.S)
    text = re.sub(r"\{\{.*?\}\}", "x", text, flags=re.S)
    text = re.sub(r"\{%.*?%\}", "", text, flags=re.S)

    return text


class Baum(HTMLParser):
    """Sammelt Verschachtelungsfehler statt beim ersten abzubrechen."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stapel = []
        self.befunde = []
        self.modale = []

    def _klassen(self, attrs):
        return dict(attrs).get("class", "").split()

    def handle_starttag(self, tag, attrs):

        if tag in LEER:
            return

        klassen = self._klassen(attrs)
        kennung = dict(attrs).get("id", "")

        #
        # Ein Modal darf nicht in einem anderen liegen. Genau das war
        # der Fehler: Das PIN-Modal landete im Einstellungen-Modal.
        #
        if "modal" in klassen:

            eltern_modal = next(
                (k for _, kl, k in reversed(self.stapel) if "modal" in kl),
                None,
            )

            if eltern_modal is not None:
                self.befunde.append(
                    f"Modal '{kennung or '?'}' liegt innerhalb von "
                    f"'{eltern_modal or '?'}' - dann bleibt es unsichtbar, "
                    f"solange das aeussere zu ist."
                )

            self.modale.append(kennung)

        #
        # Kopf, Rumpf und Fuss sind Geschwister in .modal-content.
        #
        for teil in ("modal-header", "modal-body", "modal-footer"):

            if teil not in klassen:
                continue

            eltern = self.stapel[-1] if self.stapel else ("?", [], "")

            if "modal-content" not in eltern[1]:
                self.befunde.append(
                    f"{teil} liegt in <{eltern[0]} class="
                    f"\"{' '.join(eltern[1])}\"> statt direkt in "
                    f"modal-content."
                )

        self.stapel.append((tag, klassen, kennung))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):

        if tag in LEER:
            return

        for i in range(len(self.stapel) - 1, -1, -1):
            if self.stapel[i][0] == tag:
                if i != len(self.stapel) - 1:
                    offen = ", ".join(t for t, _, _ in self.stapel[i + 1:])
                    self.befunde.append(
                        f"</{tag}> schliesst ueber noch offene Tags hinweg: "
                        f"{offen}"
                    )
                del self.stapel[i:]
                return

        self.befunde.append(f"</{tag}> ohne passendes oeffnendes Tag")


fehler = 0

for pfad in sorted(VORLAGEN.rglob("*.html")):

    baum = Baum()
    baum.feed(ohne_jinja(pfad.read_text(encoding="utf-8")))

    offen = [t for t, _, _ in baum.stapel]

    if offen:
        baum.befunde.append(f"nicht geschlossen: {', '.join(offen)}")

    if baum.befunde:
        fehler = 1
        print(f"FEHLER in {pfad.name}:")
        for b in baum.befunde:
            print(f"  - {b}")
    else:
        print(
            f"OK: {pfad.name} - Aufbau stimmt "
            f"({len(baum.modale)} Modale, keines verschachtelt)"
        )

if fehler:
    sys.exit(1)

print("Alle Vorlagen-Tests erfolgreich.")
