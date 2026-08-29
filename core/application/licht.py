"""
Lichtsteuerung: Lampen einrichten, von Hand stellen, Szenen ablegen.

Teil von Application - siehe core/application/__init__.py.

Der aktuelle Lichtzustand (welche Lampe leuchtet gerade wie) liegt
bewusst nur im Arbeitsspeicher. Gespeichert wird, was der Nutzer
angelegt hat: Vorlagen, Lampen, Szenen. Nach einem Neustart ist es
dunkel, bis jemand eine Szene aufruft - was beim Hochfahren von
selbst angehendes Licht ist das Letzte, was man auf einer Bühne
gebrauchen kann.

Nichts hier darf Aufnahme oder Wiedergabe stören. Fehlt der Dienst
oder das Kabel, bleibt es dunkel und XRack läuft weiter.
"""

from lighting import fixtures


class LichtMixin:
    """Lichtsteuerung über DMX."""

    # ----------------------------------------------------------------
    # Zustand
    # ----------------------------------------------------------------

    def get_lighting_status(self) -> dict:
        """Alles, was die Lichtkarte zum Anzeigen braucht."""

        stand = self.lighting_store.uebersicht()

        stand["values"] = self.light_values
        stand["brightness"] = self.light_brightness
        stand["dmx"] = self.dmx_control.status()

        return stand

    def set_lighting_enabled(self, enabled: bool) -> tuple[bool, str]:
        """
        Die Lichtsteuerung ein- oder ausschalten.

        Beim Ausschalten geht das Licht aus. Alles andere wäre eine
        böse Überraschung: Die Karte verschwindet, die Lampen blieben
        an, und niemand käme mehr an sie heran.
        """

        self.lighting_store.set_enabled(enabled)

        if not enabled:
            self.light_values = {}
            self.light_brightness = {}
            self.dmx_control.blackout()

        return True, ""

    # ----------------------------------------------------------------
    # Einrichtung
    # ----------------------------------------------------------------

    def save_light_template(self, vorlage: dict) -> tuple[bool, str]:

        return self.lighting_store.vorlage_speichern(vorlage)

    def delete_light_template(self, kennung: str) -> tuple[bool, str]:

        return self.lighting_store.vorlage_loeschen(kennung)

    def save_light_fixture(self, lampe: dict) -> tuple[bool, str]:

        erfolg, meldung = self.lighting_store.lampe_speichern(lampe)

        #
        # Eine geänderte Adresse verschiebt die Lampe im Bild - was
        # auf der alten Adresse stand, muss weg.
        #
        if erfolg:
            self._licht_senden()

        return erfolg, meldung

    def delete_light_fixture(self, kennung: str) -> tuple[bool, str]:

        erfolg, meldung = self.lighting_store.lampe_loeschen(kennung)

        if erfolg:

            self.light_values.pop(kennung, None)
            self.light_brightness.pop(kennung, None)
            self._licht_senden()

        return erfolg, meldung

    # ----------------------------------------------------------------
    # Von Hand stellen
    # ----------------------------------------------------------------

    def set_light_fixture_values(self, kennung: str,
                                 werte: list[int]) -> tuple[bool, str]:
        """
        Die Kanäle einer Lampe setzen, relativ zu ihrem ersten Kanal.
        """

        vorlagen = self.lighting_store.vorlagen()

        lampe = next(
            (l for l in self.lighting_store.lampen() if l["id"] == kennung),
            None,
        )

        if lampe is None:
            return False, "Diese Lampe gibt es nicht."

        vorlage = vorlagen.get(lampe["template"])

        if vorlage is None:
            return False, "Zu dieser Lampe gibt es keine Vorlage."

        anzahl = len(vorlage["channels"])

        gestutzt = [fixtures.begrenzen(wert) for wert in werte[:anzahl]]
        gestutzt += [0] * (anzahl - len(gestutzt))

        self.light_values[kennung] = gestutzt

        return self._licht_senden()

    def set_light_fixture_brightness(self, kennung: str,
                                     helligkeit: int) -> tuple[bool, str]:
        """
        Die Helligkeit einer Lampe ändern, ohne ihre Farbe zu
        verlieren.

        Gemerkt wird die Helligkeit getrennt von den Farbwerten und
        erst beim Senden daraufgelegt (siehe fixtures.bild).

        Anders herum wäre es kaputt, und zwar auf eine Art, die man
        erst spät merkt: Dimmen rechnet Farbwerte herunter, und das
        ist nicht umkehrbar. Wer eine Lampe halb herunterzieht und
        wieder hoch, hätte dauerhaft die halbe Farbe. Genauso konnte
        die Oberfläche den eingestellten Wert nicht wieder anzeigen,
        weil er nirgends stand - der Regler sprang zurück auf voll.
        """

        lampe = next(
            (l for l in self.lighting_store.lampen() if l["id"] == kennung),
            None,
        )

        if lampe is None:
            return False, "Diese Lampe gibt es nicht."

        self.light_brightness[kennung] = fixtures.begrenzen(helligkeit)

        return self._licht_senden()

    def light_blackout(self) -> tuple[bool, str]:
        """Alles aus."""

        self.light_values = {}
        self.light_brightness = {}

        return self._licht_senden()

    # ----------------------------------------------------------------
    # Szenen
    # ----------------------------------------------------------------

    def save_light_scene(self, name: str,
                         kennung: str = "") -> tuple[bool, str]:
        """Den aktuellen Stand als Szene ablegen."""

        erfolg, meldung, _ = self.lighting_store.szene_speichern(
            name, self.light_values, kennung, self.light_brightness
        )

        return erfolg, meldung

    def activate_light_scene(self, kennung: str) -> tuple[bool, str]:
        """Eine gespeicherte Szene aufrufen."""

        szene = self.lighting_store.szene(kennung)

        if szene is None:
            return False, "Diese Szene gibt es nicht."

        self.light_values = {
            lampe: list(werte)
            for lampe, werte in (szene.get("values") or {}).items()
        }

        #
        # Szenen aus einer älteren Fassung kennen die Helligkeit noch
        # nicht. Dann gilt volle Helligkeit - das ist der Zustand, in
        # dem sie damals gespeichert wurden.
        #
        self.light_brightness = dict(szene.get("brightness") or {})

        return self._licht_senden()

    def delete_light_scene(self, kennung: str) -> tuple[bool, str]:

        return self.lighting_store.szene_loeschen(kennung)

    # ----------------------------------------------------------------
    # Ausgabe
    # ----------------------------------------------------------------

    def _licht_senden(self) -> tuple[bool, str]:
        """
        Den aktuellen Stand ans Licht schicken.

        Ist die Lichtsteuerung aus, passiert nichts - dann soll auch
        nichts leuchten. Antwortet der Dienst nicht, wird das gemeldet
        und sonst nichts: Licht darf Aufnahme und Wiedergabe nie
        stören.
        """

        if not self.lighting_store.enabled:
            return True, ""

        werte = fixtures.bild(
            self.lighting_store.lampen(),
            self.lighting_store.vorlagen(),
            self.light_values,
            self.light_brightness,
        )

        if not self.dmx_control.send(werte):
            return False, (
                "Der Lichtdienst antwortet nicht. Läuft olad, und ist das "
                "DMX-Kabel angeschlossen?"
            )

        return True, ""
