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

import threading

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

        stand["show_running"] = self.light_engine.running
        stand["show_state"] = self.light_engine.zustand
        stand["show_levels"] = {
            name: round(float(self.light_engine.stand.get(name, 0.0)), 3)
            for name in ("low", "mid", "high", "level")
        }

        #
        # Ob ueberhaupt noch Audio hereinkommt. Ohne diese Auskunft
        # steht in der Karte "Show laeuft", waehrend der Lesethread
        # laengst weg ist - und man sucht den Fehler bei der Musik.
        #
        stand["show_stream"] = self.light_engine.strom_da
        stand["show_blocks"] = self.light_engine.bloecke

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

            #
            # Erst die Show anhalten, dann ausschalten: Sonst
            # schriebe ihr Thread noch ein Lichtbild, nachdem das
            # Blackout schon durch ist - und die Lampen blieben an.
            #
            self.stop_light_show()

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
    # Die musikgesteuerte Show
    # ----------------------------------------------------------------

    def set_light_show_settings(self, werte: dict) -> tuple[bool, str]:
        """
        Einstellungen der Show ändern.

        Läuft die Show gerade, wird sie neu gestartet - Empfindlichkeit
        und Kanalpaar stecken in der Analyse und lassen sich nicht
        unterwegs umstellen, ohne dass der Filterzustand unsinnig
        wird.
        """

        erfolg, meldung = self.lighting_store.set_show_einstellungen(werte)

        if erfolg and self.light_engine.running:

            self.stop_light_show()
            self.start_light_show()

        return erfolg, meldung

    def start_light_show(self) -> tuple[bool, str]:
        """Die musikgesteuerte Show starten."""

        if not self.lighting_store.enabled:
            return False, "Die Lichtsteuerung ist ausgeschaltet."

        if self.light_engine.running:
            return True, ""

        if self.selected_audio_device is None:
            return False, (
                "Kein Audiogerät gewählt - ohne Eingang gibt es nichts zu "
                "hören."
            )

        einstellungen = self.lighting_store.show_einstellungen()

        kanaele = self.recorder.backend.channels

        #
        # Der Nutzer gibt den linken Kanal 1-basiert an; der rechte
        # ist der daneben. Liegt das Paar ausserhalb dessen, was das
        # Interface hat, wird abgewiesen statt still danebenzugreifen.
        #
        links = int(einstellungen.get("channel", 1)) - 1
        rechts = links + 1

        if links < 0 or rechts >= kanaele:
            return False, (
                f"Das Interface hat {kanaele} Kanäle - das Paar "
                f"{links + 1}+{rechts + 1} gibt es dort nicht."
            )

        #
        # Den Audiostrom offen halten, ohne als Pegelprüfung zu
        # gelten (siehe recorder/recorder.py).
        #
        self.recorder.add_consumer(self.light_engine.block_empfangen)
        self.recorder.start_analysis()

        self.light_engine.start(
            rate=self.recorder.backend.rate,
            channels=kanaele,
            links=links,
            rechts=rechts,
            einstellungen=einstellungen,
        )

        return True, ""

    def stop_light_show(self) -> tuple[bool, str]:
        """Die Show anhalten und den Audiostrom wieder freigeben."""

        if not self.light_engine.running:
            return True, ""

        self.light_engine.stop()

        self.recorder.remove_consumer(self.light_engine.block_empfangen)
        self.recorder.stop_analysis()

        return True, ""

    # ----------------------------------------------------------------
    # Rueckrufe aus dem Show-Thread
    # ----------------------------------------------------------------

    def licht_show_bild(self, werte: dict) -> None:
        """
        Ein von der Show berechnetes Lichtbild uebernehmen.

        Laeuft im Show-Thread, nicht im Webserver - deshalb die
        Sperre: Sonst koennten Show und Bedienung gleichzeitig senden,
        und was auf dem Kabel landet, waere eine Mischung aus beidem.
        """

        with self._light_lock:

            self.light_values = werte

            self._licht_senden()

    def licht_rueckfall(self, zustand: str) -> None:
        """
        Keine Musik mehr: auf die eingestellte Szene umschalten.

        Ist keine hinterlegt, geht das Licht aus. Das ist die
        ehrlichere Vorgabe - Licht, das bei einer Ansage einfach
        weiterzuckt, ist schlimmer als Dunkelheit.
        """

        einstellungen = self.lighting_store.show_einstellungen()

        kennung = einstellungen.get("fallback_scene") or ""

        self.logger.info(
            "Lichtshow: %s erkannt, Rückfall auf %s.",
            zustand,
            f"Szene {kennung}" if kennung else "Blackout",
        )

        with self._light_lock:

            if kennung and self.lighting_store.szene(kennung):

                szene = self.lighting_store.szene(kennung)

                self.light_values = {
                    lampe: list(liste)
                    for lampe, liste in (szene.get("values") or {}).items()
                }
                self.light_brightness = dict(szene.get("brightness") or {})

            else:
                self.light_values = {}
                self.light_brightness = {}

            self._licht_senden()

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
