"""
Das Modell hinter der Lichtsteuerung.

Drei Begriffe, und die Reihenfolge ist wichtig:

  Vorlage  - was für eine Sorte Lampe das ist: eine geordnete Liste
             von Kanalrollen ("rot", "grün", "blau", "pan", ...).
             Einmal angelegt, für jedes Gerät desselben Modells
             wiederverwendbar.

  Lampe    - ein konkretes Gerät: eine Vorlage plus die
             DMX-Startadresse, an der es hängt, plus ein Name, unter
             dem man es wiedererkennt.

  Szene    - ein gespeicherter Zustand: für jede Lampe die Werte
             ihrer Kanäle. Gespeichert wird relativ zur Lampe, nicht
             als absolute DMX-Kanäle - zieht jemand eine Lampe auf
             eine andere Adresse um, stimmen die Szenen weiterhin.

Warum Vorlagen und nicht für jedes Gerät eine eigene Kanalliste: So
arbeitet jedes Lichtpult, und für jemanden, der Lampen kauft statt
DMX-Tabellen zu lesen, ist "wähle dein Modell" ungleich einfacher als
"trage 24 Kanäle ein". Für alles, wofür es keine Vorlage gibt, legt
man eine eigene an - das ist derselbe Weg, nur einmal von Hand.

Hier steht ausschließlich Rechnung, kein Zustand und kein Zugriff auf
Dateien oder Geräte. Das macht diesen Teil vollständig prüfbar, ohne
dass eine Lampe in der Nähe sein muss.
"""

DMX_KANAELE = 512

#
# Die Rollen, die ein Kanal haben kann.
#
# Die Liste ist bewusst überschaubar und deckt ab, was an
# Bühnenlampen üblich ist. "generic" ist der Auffangposten: ein Kanal,
# den XRack nicht deutet und den der Nutzer selbst benennt. Damit
# lässt sich auch ein Gerät einrichten, dessen Eigenheiten hier nicht
# vorgesehen sind, ohne dass am Programm etwas geändert werden muss.
#
ROLLEN = (
    "dimmer",
    "red",
    "green",
    "blue",
    "white",
    "amber",
    "uv",
    "pan",
    "pan_fine",
    "tilt",
    "tilt_fine",
    "gobo",
    "gobo_rotation",
    "color_wheel",
    "strobe",
    "shutter",

    #
    # Drehung eines Derby-/Effektspiegels und Laser-Kanaele.
    #
    # Beide gibt es an den Eurolite-Sets, und beide werden von der
    # Show angesteuert: die Drehung mit dem Bass, die Laser je nach
    # Frequenzband an oder aus (siehe light_engine._werte). Sie
    # bekommen eigene Rollen statt "generic", weil die Show sie
    # unterschiedlich behandeln muss - und weil in der Karte lesbar
    # dastehen soll, was der Regler tut.
    #
    "rotation",
    "laser",

    "generic",
)

#
# Farbkanäle - die werden beim gerechneten Dimmen skaliert.
#
FARBROLLEN = ("red", "green", "blue", "white", "amber", "uv")


#
# Mitgelieferte Vorlagen.
#
# Bewusst nur Geräte, deren Kanalbelegung eindeutig ist. Ein geratenes
# Bewegtlicht-Preset wäre schlimmer als gar keins: Wer es benutzt,
# bekommt Lampen, die sich falsch verhalten, und sucht den Fehler
# überall - nur nicht in der Vorlage, die ja mitgeliefert wurde.
# Bewegtlichter werden deshalb als eigene Vorlage angelegt, Kanal für
# Kanal aus dem Handbuch. Das ist einmal Arbeit und danach richtig.
#
EINGEBAUTE_VORLAGEN = (
    {
        "id": "dimmer",
        "name": "Dimmer (1 Kanal)",
        "channels": ["dimmer"],
        "builtin": True,
    },
    {
        "id": "rgb",
        "name": "RGB-Scheinwerfer (3 Kanäle)",
        "channels": ["red", "green", "blue"],
        "builtin": True,
    },
    {
        "id": "rgb-dimmer",
        "name": "RGB mit Dimmer (4 Kanäle)",
        "channels": ["dimmer", "red", "green", "blue"],
        "builtin": True,
    },
    {
        "id": "rgbw",
        "name": "RGBW-Scheinwerfer (4 Kanäle)",
        "channels": ["red", "green", "blue", "white"],
        "builtin": True,
    },
    {
        #
        # Der Fall, an dem das hier entwickelt wurde: eine LED-Bar mit
        # acht einzeln ansteuerbaren Segmenten, je Segment Rot, Grün,
        # Blau. Keine Dimmer-Kanäle - die Helligkeit entsteht durch
        # Herunterrechnen der Farben (siehe dimmen()).
        #
        "id": "bar-8-rgb",
        "name": "LED-Bar, 8 Segmente RGB (24 Kanäle)",
        "channels": ["red", "green", "blue"] * 8,
        "builtin": True,
    },
    {
        #
        # Eurolite LED KLS-180, 21-Kanal-Modus (Handbuch Seite 16).
        #
        # Vier Spots mit je Rot/Gruen/Blau/Weiss, davor ein Dimmer
        # und zwei Strobe-Kanaele.
        #
        # Kanal 3 ("Interne Programme") und Kanal 21 ("Programme
        # ueber DMX") bekommen mit Absicht die Rolle "generic": Die
        # Show schreibt generic nie, und damit bleiben beide auf 0.
        # Stuende dort ein Wert ueber 9, liefe das Geraet sein
        # eigenes Programm und wuerde alles ueberstimmen, was XRack
        # sendet.
        #
        "id": "eurolite-kls-180-21",
        "name": "Eurolite LED KLS-180 (21-Kanal-Modus)",
        "channels": (
            ["dimmer", "strobe", "generic", "strobe"]
            + ["red", "green", "blue", "white"] * 4
            + ["generic"]
        ),
        "builtin": True,
    },
    {
        #
        # Eurolite LED KLS-180/6, 24-Kanal-Modus.
        #
        # Sechs Spots mit je Rot/Gruen/Blau/Weiss - und sonst gar
        # nichts. Das ist der aufgeraeumteste Modus des Geraets:
        # kein Programmkanal, der das Geraet sein eigenes Ding machen
        # lassen koennte, und jeder Spot einzeln ansteuerbar. Die
        # Helligkeit entsteht durch Herunterrechnen der Farben, weil
        # es keinen Dimmerkanal gibt (siehe dimmen()).
        #
        "id": "eurolite-kls-180-6-24",
        "name": "Eurolite LED KLS-180/6 (24-Kanal-Modus)",
        "channels": ["red", "green", "blue", "white"] * 6,
        "builtin": True,
    },
    {
        #
        # Eurolite LED KLS-180/6, 29-Kanal-Modus.
        #
        # Dieselben sechs Spots, davor ein Master-Dimmer und der
        # Strobe der Spots, dahinter die beiden Bar-Kanaele und der
        # Programmkanal.
        #
        # Der Master-Dimmer ist der Grund, diesen Modus zu waehlen:
        # Mit ihm dimmt der Regler in der Oberflaeche das Geraet
        # wirklich, statt die Farbwerte herunterzurechnen - das
        # bleibt bis ganz unten sauber, weil die Farbmischung dabei
        # unangetastet bleibt.
        #
        # Kanal 29 ("Auto- und musikgesteuerte Programme") bekommt
        # mit Absicht "generic" und bleibt damit auf 0. Stuende dort
        # ein Wert ueber 9, liefe das Geraet sein eigenes Programm
        # und wuerde alles ueberstimmen, was XRack sendet. Kanal 28
        # ("Bar") ebenso - auf 0 zeigt die Bar laut Handbuch alle
        # LEDs, und das ist als ruhiger Hintergrund genau richtig.
        #
        "id": "eurolite-kls-180-6-29",
        "name": "Eurolite LED KLS-180/6 (29-Kanal-Modus)",
        "channels": (
            ["dimmer", "strobe"]
            + ["red", "green", "blue", "white"] * 6
            + ["strobe", "generic", "generic"]
        ),
        "builtin": True,
    },
    {
        #
        # Eurolite LED KLS Laser Bar PRO FX, 28-Kanal-Modus
        # (Handbuch Seite 19).
        #
        # Vier Farbeinheiten (zwei Derbys aussen, zwei Spots innen)
        # mit je Rot/Gruen/Blau und einem Strobe-Kanal, dazu die
        # Laser und die weissen/UV-Strobe-LEDs.
        #
        # Die Laser (Kanal 21/22) und die Drehung der beiden Derbys
        # (5/20) und des Lasers (23) fährt die Show mit. Die
        # Strobe-LEDs (24-28) nicht - ein Blitzlicht, das von selbst
        # angeht, will niemand.
        #
        "id": "eurolite-kls-laser-bar-pro-fx-28",
        "name": "Eurolite LED KLS Laser Bar PRO FX (28-Kanal-Modus)",
        "channels": [
            # Derby 1
            "red", "green", "blue", "strobe", "rotation",
            # Spot 2
            "red", "green", "blue", "strobe", "generic",
            # Spot 3
            "red", "green", "blue", "strobe", "generic",
            # Derby 4
            "red", "green", "blue", "strobe", "rotation",
            # Laser
            "laser", "laser", "rotation",
            # Weisse LEDs 1-4 und UV
            "shutter", "shutter", "shutter", "shutter", "shutter",
        ],
        "builtin": True,
    },
)


def eingebaute_vorlagen() -> list[dict]:
    """Kopien der mitgelieferten Vorlagen."""

    return [
        {**vorlage, "channels": list(vorlage["channels"])}
        for vorlage in EINGEBAUTE_VORLAGEN
    ]


# --------------------------------------------------------------------
# Prüfen
# --------------------------------------------------------------------

def pruefe_vorlage(vorlage: dict) -> str:
    """
    Prüft eine Vorlage. Leerer Text heißt: in Ordnung.

    Es wird Klartext zurückgegeben und keine Ausnahme geworfen - der
    Text geht unverändert an den Nutzer, der die Vorlage gerade
    anlegt.
    """

    if not str(vorlage.get("id", "")).strip():
        return "Die Vorlage braucht eine Kennung."

    if not str(vorlage.get("name", "")).strip():
        return "Die Vorlage braucht einen Namen."

    kanaele = vorlage.get("channels")

    if not isinstance(kanaele, list) or not kanaele:
        return "Die Vorlage braucht mindestens einen Kanal."

    if len(kanaele) > DMX_KANAELE:
        return f"Eine Vorlage kann höchstens {DMX_KANAELE} Kanäle haben."

    for nummer, rolle in enumerate(kanaele, start=1):

        if rolle not in ROLLEN:
            return f"Kanal {nummer}: '{rolle}' ist keine bekannte Rolle."

    return ""


def pruefe_lampe(lampe: dict, vorlagen: dict) -> str:
    """
    Prüft eine Lampe gegen die vorhandenen Vorlagen. Leerer Text
    heißt: in Ordnung.
    """

    if not str(lampe.get("name", "")).strip():
        return "Die Lampe braucht einen Namen."

    vorlage = vorlagen.get(lampe.get("template"))

    if vorlage is None:
        return "Zu dieser Lampe gibt es keine Vorlage."

    try:
        adresse = int(lampe.get("address"))
    except (TypeError, ValueError):
        return "Die Startadresse muss eine Zahl sein."

    if adresse < 1 or adresse > DMX_KANAELE:
        return f"Die Startadresse muss zwischen 1 und {DMX_KANAELE} liegen."

    ende = adresse + len(vorlage["channels"]) - 1

    if ende > DMX_KANAELE:
        return (
            f"Die Lampe braucht {len(vorlage['channels'])} Kanäle und würde "
            f"ab Adresse {adresse} bis {ende} reichen - das Universum endet "
            f"bei {DMX_KANAELE}."
        )

    return ""


def adressbereich(lampe: dict, vorlagen: dict) -> tuple[int, int]:
    """Erster und letzter DMX-Kanal einer Lampe (1-basiert)."""

    vorlage = vorlagen[lampe["template"]]
    start = int(lampe["address"])

    return start, start + len(vorlage["channels"]) - 1


def ueberschneidungen(lampen: list[dict], vorlagen: dict) -> list[tuple[str, str]]:
    """
    Paare von Lampen, deren Adressbereiche sich überlappen.

    Das ist kein Fehler, den man verbieten müsste - manche Aufbauten
    sprechen mehrere Geräte bewusst mit derselben Adresse an, damit
    sie gleich leuchten. Es ist aber die häufigste Ursache für "eine
    Lampe macht, was eine andere tun sollte", und deshalb etwas, das
    man dem Nutzer zeigen sollte, statt es zu verschweigen.
    """

    gefunden = []

    brauchbar = [
        lampe for lampe in lampen
        if lampe.get("template") in vorlagen
    ]

    for i, eine in enumerate(brauchbar):

        start_a, ende_a = adressbereich(eine, vorlagen)

        for andere in brauchbar[i + 1:]:

            start_b, ende_b = adressbereich(andere, vorlagen)

            if start_a <= ende_b and start_b <= ende_a:
                gefunden.append((eine["id"], andere["id"]))

    return gefunden


# --------------------------------------------------------------------
# Rechnen
# --------------------------------------------------------------------

def begrenzen(wert) -> int:
    """Auf einen gültigen DMX-Wert bringen."""

    try:
        zahl = int(wert)
    except (TypeError, ValueError):
        return 0

    return max(0, min(255, zahl))


def leere_werte(vorlage: dict) -> list[int]:
    """Alle Kanäle einer Vorlage auf 0."""

    return [0] * len(vorlage["channels"])


def dimmen(vorlage: dict, werte: list[int], helligkeit: int) -> list[int]:
    """
    Die Helligkeit einer Lampe einstellen, egal wie sie gebaut ist.

    Hat die Vorlage einen Dimmer-Kanal, wird der gesetzt - so ist es
    gemeint, und die Farbmischung bleibt unangetastet.

    Hat sie keinen, werden stattdessen die Farbkanäle heruntergerechnet.
    Das ist kein Notbehelf, sondern bei vielen LED-Geräten der einzige
    Weg: Die LED-Bar, an der das hier entstanden ist, hat im
    24-Kanal-Betrieb ausschließlich Farbkanäle. Ohne diese
    Unterscheidung müsste jede Stelle, die Helligkeit ändern will,
    selbst wissen, wie die Lampe gebaut ist - und das wäre genau die
    Sorte Wissen, die sich über das Programm verteilt und dann an
    einer Stelle fehlt.
    """

    helligkeit = begrenzen(helligkeit)

    kanaele = vorlage["channels"]
    ergebnis = list(werte[:len(kanaele)])
    ergebnis += [0] * (len(kanaele) - len(ergebnis))

    if "dimmer" in kanaele:

        for nummer, rolle in enumerate(kanaele):
            if rolle == "dimmer":
                ergebnis[nummer] = helligkeit

        return ergebnis

    for nummer, rolle in enumerate(kanaele):

        if rolle in FARBROLLEN:
            ergebnis[nummer] = begrenzen(
                ergebnis[nummer] * helligkeit // 255
            )

    return ergebnis


def hat_dimmer(vorlage: dict) -> bool:
    """True, wenn die Vorlage einen echten Dimmer-Kanal hat."""

    return "dimmer" in vorlage["channels"]


def bild(lampen: list[dict], vorlagen: dict, zustaende: dict,
         helligkeiten: dict | None = None) -> list[int]:
    """
    Aus allen Lampen ein DMX-Bild bauen.

    `zustaende` bildet Lampen-Kennung auf eine Werteliste ab, relativ
    zum ersten Kanal der Lampe. Fehlt eine Lampe darin, bleibt sie
    dunkel.

    `helligkeiten` bildet Lampen-Kennung auf 0-255 ab; fehlt ein
    Eintrag, gilt volle Helligkeit.

    Warum die Helligkeit erst hier einfließt und nicht schon in den
    gemerkten Werten steht:

    Dimmen rechnet Farbwerte herunter, und das ist nicht umkehrbar.
    Wer eine Lampe auf die Hälfte dimmt und wieder hochzieht, hätte
    sonst dauerhaft die halbe Farbe - aus 200 wird 100, und aus 100
    wird beim Hochziehen wieder nur 100. Die gemerkten Werte sind
    deshalb immer die ungedimmten; die Helligkeit ist eine eigene
    Größe und wird erst beim Senden daraufgelegt.

    Zurück kommen immer volle 512 Kanäle. Nicht belegte Kanäle stehen
    auf 0 - wer eine Lampe aus der Einrichtung entfernt, soll sie
    nicht weiterleuchten sehen, weil ihr alter Wert im Gerät
    stehengeblieben ist.
    """

    ausgabe = [0] * DMX_KANAELE
    helligkeiten = helligkeiten or {}

    for lampe in lampen:

        vorlage = vorlagen.get(lampe.get("template"))

        if vorlage is None:
            continue

        if pruefe_lampe(lampe, vorlagen):
            continue

        start = int(lampe["address"])
        werte = zustaende.get(lampe["id"]) or leere_werte(vorlage)

        #
        # Immer anwenden, auch bei voller Helligkeit: Bei einer Lampe
        # mit eigenem Dimmer-Kanal setzt das den Dimmer auf 255. Ohne
        # diesen Schritt bliebe der auf 0 stehen, und die Lampe wäre
        # dunkel, obwohl eine Farbe eingestellt ist.
        #
        werte = dimmen(vorlage, werte, helligkeiten.get(lampe["id"], 255))

        for versatz, rolle in enumerate(vorlage["channels"]):

            if versatz < len(werte):
                ausgabe[start - 1 + versatz] = begrenzen(werte[versatz])

    return ausgabe
