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
        #
        # Wie viele Kanaele das Interface hat - fuer die Auswahl des
        # Kanalpaars in den Einstellungen. Dieselbe Quelle, aus der
        # start_light_show() prueft, ob das gewaehlte Paar ueberhaupt
        # existiert.
        #
        stand["input_channels"] = self.recorder.backend.channels

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

            self._blende_abbrechen()

            self.light_values = {}
            self.light_brightness = {}
            self.dmx_control.blackout()

        return True, ""

    # ----------------------------------------------------------------
    # Der DMX-Ausgang
    #
    # Einmal nach der Installation muss der Anschluss des Kabels dem
    # Universum zugeordnet werden. Das ging bisher nur im Terminal
    # (ola_dev_info, ola_patch) - hier ist derselbe Schritt fuer die
    # Einstellungen verpackt.
    # ----------------------------------------------------------------

    def get_dmx_ports(self) -> dict:
        """Die Auswahl fuer die Einstellungen: was olad anbietet."""

        return {
            "ports": self.dmx_control.ports(),
            "patched": self.dmx_control.patched,
        }

    def patch_dmx_port(self, port: str) -> tuple[bool, str]:
        """Einen Ausgang zuordnen und gleich das aktuelle Bild senden."""

        erfolg, meldung = self.dmx_control.patch(port)

        if not erfolg:
            return False, meldung

        #
        # Ohne das bliebe es nach der Zuordnung dunkel, bis jemand
        # etwas anfasst: olad kennt den neuen Ausgang, hat aber noch
        # kein Bild fuer ihn.
        #
        gesendet, grund = self._licht_senden()

        if not gesendet:

            #
            # Die Zuordnung selbst hat geklappt - das ist nachgesehen
            # worden. Nur das erste Bild kam nicht durch, was
            # bedeutet, dass olad zwischen den beiden Aufrufen weg
            # ist. Als Fehlschlag zu melden waere falsch (man wuerde
            # ein zweites Mal zuordnen), stillschweigen aber auch:
            # Deshalb ins Protokoll. In der Lichtkarte steht dann
            # ohnehin, dass der Dienst nicht antwortet.
            #
            self.logger.warning("DMX: Zuordnung stand, Bild nicht: %s", grund)

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

            #
            # Auch den Glättungszustand der Show wegräumen. Bliebe er
            # stehen, käme eine später gleich benannte Lampe mit der
            # Farbe der alten zurück.
            #
            for schluessel in [
                s for s in self.light_engine._hintergrund
                if s.split(":", 1)[0] == kennung
            ]:
                self.light_engine._hintergrund.pop(schluessel, None)

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
        """
        Alles aus - sofort.

        Das ist der Knopf für den Fall, dass etwas schiefgeht. Er darf
        nie durch die Blende laufen: Zwei Sekunden, bis es dunkel
        wird, sind hier zwei Sekunden zu viel.
        """

        self._blende_abbrechen()

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

        #
        # Von Hand aufgerufen gilt eine Szene sofort. Ein Knopf, der
        # zwei Sekunden braucht, fühlt sich kaputt an.
        #
        self._blende_abbrechen()

        #
        # Laeuft die Show, ueberschreibt sie die Farbwerte ohnehin im
        # naechsten Bild. Dann soll auch die Helligkeit der Szene
        # nicht haengenbleiben.
        #
        if self.light_engine.running:
            self._show_uebernahme = True

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
        """
        Die musikgesteuerte Show starten.

        Was vorher an Helligkeit eingestellt war - etwa aus einer von
        Hand aufgerufenen Szene -, gilt fuer die Show nicht: Ihr
        erstes Bild dreht die Lampen, die sie faehrt, wieder auf.
        """

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

        self._show_uebernahme = True

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

        #
        # Hatte die Show die Strobe-Kanaele? Dann muss sie sie
        # zurueckgeben - siehe _strobe_freigeben().
        #
        blitz = bool(self.light_engine.einstellungen.get("snare_strobe"))

        self.light_engine.stop()

        self.recorder.remove_consumer(self.light_engine.block_empfangen)
        self.recorder.stop_analysis()

        if blitz:
            self._strobe_freigeben()

        return True, ""

    def _strobe_freigeben(self) -> None:
        """
        Die Strobe-Kanaele auf 0 setzen, die die Show gefahren hat.

        Waehrend der Blitz laeuft, schreibt die Show zwischen zwei
        Blitzen ausdruecklich 0 - hoert sie mittendrin auf, tut sie
        das nicht mehr. Und weil jedes Lichtbild bei dem beginnt, was
        zuletzt drin stand, bliebe der Blitzwert dann fuer immer
        stehen: Die Lampe blitzt weiter, obwohl die Show laengst aus
        ist.

        Ein Blitz dauert 80 ms und kommt mehrmals je Sekunde - beim
        Anhalten mitten in einem zu landen ist also kein Sonderfall,
        sondern passiert regelmaessig.

        Angefasst wird nur, was die Show auch gefahren hat: Lampen,
        die vom Blitz ausgenommen sind (Hintergrund und die
        ausgenommenen), koennen einen von Hand gestellten Strobe-Wert
        tragen, und der geht niemanden etwas an.
        """

        vorlagen = self.lighting_store.vorlagen()

        with self._light_lock:

            geaendert = False

            for lampe in self.lighting_store.lampen():

                art = lampe.get("kind", fixtures.ART_VORGABE)

                if art == "static" or art in fixtures.HINTERGRUND_ARTEN:
                    continue

                vorlage = vorlagen.get(lampe.get("template"))
                werte = self.light_values.get(lampe["id"])

                if vorlage is None or not werte:
                    continue

                for index, rolle in enumerate(vorlage["channels"]):

                    if rolle == "strobe" and index < len(werte) and werte[index]:
                        werte[index] = 0
                        geaendert = True

        #
        # Gesendet wird ausserhalb der Sperre: _licht_senden() nimmt
        # sie an anderer Stelle selbst, und die Sperre ist nicht
        # wiedereintrittsfaehig.
        #
        if geaendert:
            self._licht_senden()

    # ----------------------------------------------------------------
    # Die Blende in die Rueckfallszene
    #
    # Am Songende hart auf die Szene umzuschalten ist ein sichtbarer
    # Sprung, und zwar genau in dem Moment, in dem es ruhig werden
    # soll. Deshalb wird hinein geblendet.
    #
    # Der Rueckweg bleibt hart: Die Show setzt mit dem ersten Takt des
    # naechsten Songs sofort ein. Die beiden Richtungen sind nicht
    # symmetrisch - ein Einsatz, der zwei Sekunden nachzieht, wirkt
    # schlapp, ein Ausklang, der nachzieht, wirkt richtig.
    # ----------------------------------------------------------------

    #
    # Fehlt eine Lampe in light_brightness, gilt sie als voll
    # aufgedreht - so liest es fixtures.bild(). Beim Mischen muss
    # dasselbe gelten: Wer einen fehlenden Eintrag als 0 nimmt, dimmt
    # die Lampe waehrend der Blende auf null herunter und wieder hoch.
    #
    VOLLE_HELLIGKEIT = 255

    def _blende_abbrechen(self) -> None:
        """
        Eine laufende Blende verwerfen.
        
        Immer dann, wenn etwas anderes das Licht übernimmt - die Show,
        ein Blackout, eine von Hand aufgerufene Szene. Ohne das zöge
        der nächste Tick das Licht wieder Richtung Szene, obwohl längst
        etwas anderes gilt.
        """

        self._blende_rest = 0.0

    def _blende_starten(self, ziel_werte: dict, ziel_helligkeit: dict,
                        dauer: float) -> None:
        """Den aktuellen Stand einfrieren und die Blende aufziehen."""

        self._blende_von = {
            lampe: list(werte) for lampe, werte in self.light_values.items()
        }
        self._blende_helligkeit_von = dict(self.light_brightness)

        self._blende_ziel = ziel_werte
        self._blende_helligkeit_ziel = ziel_helligkeit

        self._blende_dauer = max(0.0, float(dauer))
        self._blende_rest = self._blende_dauer

    def _blende_mischen(self, anteil: float) -> None:
        """
        light_values und light_brightness auf den Zwischenstand
        setzen. anteil 0 = Ausgangsstand, 1 = Ziel.
        """

        lampen = set(self._blende_von) | set(self._blende_ziel)

        werte = {}

        for lampe in lampen:

            von = self._blende_von.get(lampe, [])
            nach = self._blende_ziel.get(lampe, [])

            anzahl = max(len(von), len(nach))

            werte[lampe] = [
                round(
                    (von[i] if i < len(von) else 0) * (1.0 - anteil)
                    + (nach[i] if i < len(nach) else 0) * anteil
                )
                for i in range(anzahl)
            ]

        self.light_values = werte

        helle = set(self._blende_helligkeit_von) | set(self._blende_helligkeit_ziel)

        self.light_brightness = {
            lampe: round(
                self._blende_helligkeit_von.get(lampe, self.VOLLE_HELLIGKEIT)
                * (1.0 - anteil)
                + self._blende_helligkeit_ziel.get(lampe, self.VOLLE_HELLIGKEIT)
                * anteil
            )
            for lampe in helle
        }

    def licht_rueckfall_halten(self, dauer: float) -> None:
        """
        Die Blende weiterziehen. Wird bei JEDEM Block gerufen, solange
        keine Musik erkannt wird.

        Bei jedem Block und nicht nur beim Übergang: Ein einzelner
        Aufruf könnte nur springen, und genau das soll ja weg.
        """

        if self._blende_rest <= 0.0:
            return

        with self._light_lock:

            #
            # Zwischen der Prüfung oben und der Sperre kann die Show
            # die Blende abgebrochen haben. Dann ist hier nichts mehr
            # zu tun.
            #
            if self._blende_rest <= 0.0:
                return

            self._blende_rest = max(0.0, self._blende_rest - float(dauer))

            anteil = (
                1.0 if self._blende_dauer <= 0.0
                else 1.0 - self._blende_rest / self._blende_dauer
            )

            self._blende_mischen(anteil)

            self._licht_senden()

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

            #
            # Die Show hat wieder das Sagen. Eine noch laufende Blende
            # muss weg - sonst zöge der nächste Tick das Licht wieder
            # Richtung Szene, obwohl die Musik längst läuft.
            #
            self._blende_abbrechen()

            #
            # Hatte gerade etwas anderes das Licht in der Hand - der
            # Rueckfall, eine Szene, ein frischer Start -, dann steht
            # in light_brightness noch DEREN Helligkeit.
            #
            # Am Geraet sah das so aus: Wer die Rueckfallszene mit
            # heruntergezogenen Reglern angelegt hatte, bekam
            # anschliessend eine Show, die dauerhaft gedimmt lief. Die
            # Farbwerte stimmten, die Helligkeit darunter nicht.
            #
            # Zurueckgesetzt wird nur beim Uebernehmen, nicht bei
            # jedem Bild: Sonst waere der Helligkeitsregler in der
            # Karte waehrend der Show wirkungslos und spraenge nach
            # jedem Ziehen auf voll zurueck - genau der Fehler, der in
            # 1.13 schon einmal behoben wurde.
            #
            if self._show_uebernahme:

                self._show_uebernahme = False

                ausgenommen = {
                    lampe["id"]
                    for lampe in self.lighting_store.lampen()
                    if lampe.get("kind") == "static"
                }

                #
                # Eintrag weg heisst volle Helligkeit - so liest es
                # fixtures.bild(). Es muss also nichts auf 255 gesetzt
                # werden.
                #
                self.light_brightness = {
                    lampe: wert
                    for lampe, wert in self.light_brightness.items()
                    if lampe in ausgenommen
                }

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

        #
        # Lampen, die von der Show ausgenommen sind, bleiben auch hier
        # stehen.
        #
        # Der Rückfall gehört zur Show, und die Regel soll in einem
        # Satz erklärbar bleiben: Diese Lampen fasst die Show nie an.
        # Eine Ausnahme ausgerechnet bei der Ansage wäre genau die
        # Sorte Sonderfall, die man später nicht mehr erklären kann.
        #
        ausgenommen = {
            lampe["id"]
            for lampe in self.lighting_store.lampen()
            if lampe.get("kind") == "static"
        }

        dauer = float(einstellungen.get("fade_seconds", 0.0) or 0.0)

        with self._light_lock:

            bewahrt = {
                lampe: list(werte)
                for lampe, werte in self.light_values.items()
                if lampe in ausgenommen
            }
            bewahrte_helligkeit = {
                lampe: wert
                for lampe, wert in self.light_brightness.items()
                if lampe in ausgenommen
            }

            if kennung and self.lighting_store.szene(kennung):

                szene = self.lighting_store.szene(kennung)

                ziel = {
                    lampe: list(liste)
                    for lampe, liste in (szene.get("values") or {}).items()
                    if lampe not in ausgenommen
                }
                ziel_helligkeit = {
                    lampe: wert
                    for lampe, wert in (szene.get("brightness") or {}).items()
                    if lampe not in ausgenommen
                }

            else:
                ziel = {}
                ziel_helligkeit = {}

            ziel.update(bewahrt)
            ziel_helligkeit.update(bewahrte_helligkeit)

            self._blende_starten(ziel, ziel_helligkeit, dauer)

            #
            # Kommt die Musik zurueck, soll die Show nicht mit der
            # Helligkeit dieser Szene weiterlaufen.
            #
            self._show_uebernahme = True

            #
            # Den ersten Schritt gleich hier: Ist die Blende auf 0
            # gestellt, steht das Ziel damit sofort - und das
            # Verhalten ist genau das alte, harte Umschalten.
            #
            self._blende_mischen(1.0 if dauer <= 0.0 else 0.0)

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
