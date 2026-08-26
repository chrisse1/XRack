"""
Prüft, dass die auf Mixins verteilte Application vollständig ist.

Warum es diesen Test gibt: Beim Aufteilen von core/application.py in
Mixins sind die Modulkonstanten für die automatische Fader-Sperre
zunächst liegengeblieben - die Methoden wanderten, die Konstanten
nicht. Aufgefallen ist das nicht beim Importieren und auch nicht beim
Vergleich der Methodennamen (die stimmten alle), sondern erst beim
Aufruf.

Genau diese Lücke schließt der Test hier: Er sieht sich für jede
Methode an, welche *globalen* Namen sie zur Laufzeit nachschlägt, und
prüft, ob die in ihrem Modul überhaupt vorhanden sind. Attributzugriffe
(self.recorder, .start_monitoring) zählen dabei nicht mit - nur echte
freie Namen.
"""

import builtins
import dis
import inspect

from core.application import Application

# ----------------------------------------------------------------
# 1. Jede Methode muss ihre globalen Namen auflösen können
# ----------------------------------------------------------------


def globale_namen(funktion):
    """
    Die freien Namen einer Funktion - also das, was sie weder selbst
    bindet noch als Attribut anspricht.
    """

    for anweisung in dis.get_instructions(funktion):
        if anweisung.opname in ("LOAD_GLOBAL", "LOAD_NAME"):
            yield anweisung.argval


def methoden_von(klasse):
    """Liefert (Name, Funktion) für Methoden und Properties."""

    for name in sorted(dir(klasse)):

        if name.startswith("__"):
            continue

        #
        # getattr_static, damit Properties nicht ausgelöst werden -
        # sonst liefe hier echte Hardware-Logik an.
        #
        wert = inspect.getattr_static(klasse, name)

        if isinstance(wert, property):
            if wert.fget is not None:
                yield f"{name} (property)", wert.fget

        elif inspect.isfunction(wert):
            yield name, wert


fehlend = []
geprueft = 0

for bezeichnung, funktion in methoden_von(Application):

    geprueft += 1

    for name in globale_namen(funktion):

        if name in funktion.__globals__:
            continue

        if hasattr(builtins, name):
            continue

        fehlend.append(f"{bezeichnung} -> {name}")

assert geprueft >= 70, (
    f"Nur {geprueft} Methoden gefunden - da fehlt ein ganzer Mixin."
)

assert not fehlend, (
    "Diese Methoden greifen auf globale Namen zu, die es in ihrem "
    "Modul nicht gibt - beim Verschieben liegengeblieben:\n  "
    + "\n  ".join(fehlend)
)

print(f"OK: Alle {geprueft} Methoden lösen ihre globalen Namen auf")

# ----------------------------------------------------------------
# 2. Alle Mixins hängen tatsächlich an der Klasse
#
# Ein vergessenes Mixin in der Vererbungsliste fällt sonst erst auf,
# wenn jemand die betroffene Funktion benutzt.
# ----------------------------------------------------------------

ERWARTETE_MIXINS = {
    "AudioMixin",
    "AufnahmeMixin",
    "BluetoothMixin",
    "EinstellungenMixin",
    "MusikMixin",
    "NetzwerkMixin",
    "PultMixin",
    "UsbMixin",
    "WartungMixin",
}

vorhanden = {k.__name__ for k in Application.__mro__}

fehlende_mixins = ERWARTETE_MIXINS - vorhanden

assert not fehlende_mixins, (
    f"Diese Mixins hängen nicht an Application: {sorted(fehlende_mixins)}"
)

print(f"OK: Alle {len(ERWARTETE_MIXINS)} Mixins hängen an Application")

# ----------------------------------------------------------------
# 3. Kein Mixin überschreibt eine Methode eines anderen
#
# Bei Mehrfachvererbung gewinnt sonst stillschweigend das erste in der
# Liste - und die andere Fassung läuft nie wieder.
# ----------------------------------------------------------------

herkunft = {}
doppelt = []

for klasse in Application.__mro__:

    if klasse.__name__ not in ERWARTETE_MIXINS:
        continue

    for name, wert in vars(klasse).items():

        if name.startswith("__"):
            continue

        if not (inspect.isfunction(wert) or isinstance(wert, property)):
            continue

        if name in herkunft:
            doppelt.append(f"{name}: {herkunft[name]} und {klasse.__name__}")
        else:
            herkunft[name] = klasse.__name__

assert not doppelt, (
    "Dieselbe Methode steckt in mehreren Mixins - eine davon läuft nie:\n  "
    + "\n  ".join(doppelt)
)

print(f"OK: Keine Methode steckt in zwei Mixins ({len(herkunft)} verteilt)")

print("Alle Tests erfolgreich.")
