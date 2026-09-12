"""
Eine Bremse gegen das Durchprobieren der PIN.

Nötig geworden mit der Zertifikatsübertragung. Die übrigen
Schnittstellen von XRack sind bewusst ohne Anmeldung erreichbar - wer
im selben Netz steht, darf das Rack bedienen. Beim privaten Schlüssel
ist das anders: Wer ihn hat, kann sich später und woanders als dieses
Rack ausgeben, lautlos, und bekommt die PIN mitgeliefert, sobald
jemand sie eintippt.

Geschützt wird das mit der PIN - und eine PIN aus vier Ziffern ist
ohne Bremse in Minuten durchprobiert (10000 Versuche). Mit ihr dauert
dasselbe Wochen, und das reicht für ein Gerät im Proberaum-WLAN.

Gezählt wird im Arbeitsspeicher. Ein Neustart setzt die Bremse zurück
- wer den auslösen kann, steht ohnehin am Gerät.
"""

from time import monotonic


#
# So viele Fehlversuche sind Vertippen. Danach wird gewartet.
#
VERSUCHE = 5

#
# Und zwar so lange. Fünf Minuten je fünf Versuche heisst: 10000
# Möglichkeiten brauchen im Mittel rund drei Tage Dauerbeschuss.
#
SPERRE_S = 300.0


class PinBremse:
    """Zählt Fehlversuche und sperrt eine Weile."""

    def __init__(self, versuche: int = VERSUCHE, sperre: float = SPERRE_S):

        self.versuche = versuche
        self.sperre = sperre

        self._fehl = 0
        self._bis = 0.0

    def offen(self, jetzt: float | None = None) -> float:
        """
        Wie lange noch gesperrt ist, in Sekunden - 0.0, wenn frei.
        """

        jetzt = monotonic() if jetzt is None else jetzt

        return max(0.0, self._bis - jetzt)

    def fehlschlag(self, jetzt: float | None = None) -> None:

        jetzt = monotonic() if jetzt is None else jetzt

        self._fehl += 1

        if self._fehl >= self.versuche:

            self._bis = jetzt + self.sperre

            #
            # Zurück auf null, damit nach der Sperre wieder ein voller
            # Satz Versuche zählt - sonst sperrte jeder weitere
            # Fehlversuch sofort erneut, und ein Vertippen nach der
            # Wartezeit wäre eine zweite Wartezeit.
            #
            self._fehl = 0

    def erfolg(self) -> None:
        """Richtige PIN - alles vergessen."""

        self._fehl = 0
        self._bis = 0.0
