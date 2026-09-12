"""
Das TLS-Zertifikat: sichern, einspielen, neu erzeugen.

Siehe core/tls_store.py - hier steht nur, was die Anwendung darum
herum entscheidet: wer darf das, und welche Namen gehören hinein.
"""

from core.tls_store import MINDESTKENNWORT


class ZertifikatMixin:
    """
    Das TLS-Zertifikat.

    Teil von Application - siehe core/application/__init__.py.
    """

    # ----------------------------------------------------------------
    # Wer darf
    # ----------------------------------------------------------------

    def zertifikat_erlaubt(self, pin: str) -> tuple[bool, str]:
        """
        Darf dieser Aufruf ans Zertifikat?

        Hier - und nur hier - wird die PIN auf dem Server geprüft. Bei
        den übrigen Schnittstellen tut sie das nicht: Wer im selben
        Netz steht, darf XRack bedienen, so ist es gewollt. Der
        private Schlüssel ist etwas anderes. Wer ihn hat, gibt sich
        später und woanders als dieses Rack aus - lautlos, und mit der
        PIN obendrauf, sobald jemand sie eintippt.

        Deshalb gilt hier auch: OHNE gesetzte PIN gar nicht. Sonst
        wäre der Schlüssel für jeden im Netz abholbar, und XRack hätte
        sich genau das eingehandelt, wogegen es das eingebaute
        Zertifikat nicht gibt.
        """

        if not self.pin_protection_enabled():
            return False, (
                "Dafür muss erst eine PIN vergeben werden - ohne sie könnte "
                "jeder im Netz den Schlüssel abholen."
            )

        wartezeit = self.pin_bremse.offen()

        if wartezeit > 0:
            return False, (
                f"Zu viele Fehlversuche. Bitte "
                f"{int(wartezeit // 60) + 1} Minuten warten."
            )

        if not self.verify_settings_pin(pin):

            self.pin_bremse.fehlschlag()

            return False, "Die PIN stimmt nicht."

        self.pin_bremse.erfolg()

        return True, ""

    # ----------------------------------------------------------------
    # Ansehen
    # ----------------------------------------------------------------

    def get_zertifikat(self) -> dict:
        """
        Was die Oberfläche über das Zertifikat wissen muss.

        Dazu gehört die Frage, ob der gemeinsame Name mit drinsteht:
        Tut er das nicht, fragt der Browser unter diesem Namen weiter
        nach, und die ganze Übertragung hätte ihren Zweck verfehlt.
        """

        zustand = self.tls_store.zustand()

        alias = self.mdns_alias.name

        zustand["alias"] = alias

        zustand["alias_covered"] = (
            not alias or self.tls_store.deckt_ab(f"{alias}.local")
        )

        zustand["min_password"] = MINDESTKENNWORT

        zustand["pin_required"] = not self.pin_protection_enabled()

        return zustand

    def zertifikat_datei(self) -> tuple[bytes | None, str]:
        """
        Das Zertifikat zum Herunterladen - oeffentlicher Teil, kein
        Schluessel, keine PIN.

        Kein Widerspruch zu zertifikat_erlaubt(): Dort geht es um den
        privaten Schluessel. Der oeffentliche Teil geht bei jedem
        Verbindungsaufbau an jeden heraus, der fragt - ihn
        zurueckzuhalten wuerde nichts schuetzen und nur die Einrichtung
        auf dem Tablet verhindern.

        Der Dateiname traegt den Namen des Racks: Wer die Zertifikate
        von zwei Racks im Download-Ordner hat, soll sie unterscheiden
        koennen.
        """

        daten = self.tls_store.oeffentlich()

        if daten is None:
            return None, "Es gibt kein Zertifikat zum Herunterladen."

        name = self.mdns_alias.name or self.mdns_alias.hostname()

        return daten, f"xrack-{name}.crt"

    def zertifikat_namen(self) -> list[str]:
        """
        Die Namen, unter denen dieses Rack erreichbar ist.

        Der eigene Rechnername, derselbe mit .local - und, wenn einer
        gesetzt ist, der gemeinsame Name. Genau um ihn geht es: Er ist
        der Name, unter dem alle Racks des Nutzers dasselbe Ziel
        sind.
        """

        eigener = self.mdns_alias.hostname()

        namen = [eigener, f"{eigener}.local"]

        alias = self.mdns_alias.name

        if alias:
            namen += [alias, f"{alias}.local"]

        return namen

    # ----------------------------------------------------------------
    # Ändern
    # ----------------------------------------------------------------

    def zertifikat_erneuern(self, pin: str) -> tuple[bool, str]:
        """Ein neues Zertifikat für die aktuellen Namen."""

        erlaubt, meldung = self.zertifikat_erlaubt(pin)

        if not erlaubt:
            return False, meldung

        return self.tls_store.erzeugen(self.zertifikat_namen())

    def zertifikat_sichern(self, pin: str, kennwort: str):
        """Das Zertifikat als verschlüsselte Datei."""

        erlaubt, meldung = self.zertifikat_erlaubt(pin)

        if not erlaubt:
            return None, meldung

        return self.tls_store.exportieren(kennwort)

    def zertifikat_einspielen(
        self,
        pin: str,
        kennwort: str,
        daten: bytes,
    ) -> tuple[bool, str]:
        """Ein gesichertes Zertifikat übernehmen."""

        erlaubt, meldung = self.zertifikat_erlaubt(pin)

        if not erlaubt:
            return False, meldung

        return self.tls_store.importieren(daten, kennwort)
