"""
Prüft die neue Recorder-Logik: Pegelprüfung (Monitoring) und
Aufnahme teilen sich denselben Thread, ohne dass ALSA/echte
Hardware nötig ist.
"""

#
# Der Suchpfad zur Projektwurzel - siehe tests/_wurzel.py. Muss VOR
# allen Importen aus XRack stehen.
#
from _wurzel import WURZEL  # noqa: F401,E402


import sys
import time
import types
from pathlib import Path

#
# alsaaudio ist auf diesem Rechner nicht installiert (nur auf dem
# Pi). Recorder importiert darüber nur AudioBackend, das hier gar
# nicht benutzt wird (FakeBackend ersetzt es) - ein Fake-Modul
# genügt, damit der Import klappt.
#
fake_alsaaudio = types.ModuleType("alsaaudio")
fake_alsaaudio.PCM_FORMAT_S24_LE = 1
fake_alsaaudio.PCM_FORMAT_S32_LE = 2
fake_alsaaudio.PCM_CAPTURE = 0
fake_alsaaudio.PCM_PLAYBACK = 1
fake_alsaaudio.PCM_NORMAL = 0
sys.modules["alsaaudio"] = fake_alsaaudio

from recorder.recorder import Recorder


class FakeBackend:
    """
    Liefert endlos Blöcke - mit allen Kanälen des Interfaces.

    `channels` ist die Aufnahmebreite, `native_channels` das, was das
    Interface wirklich liefert. Am echten Backend sind das zwei
    verschiedene Dinge (siehe audio/audio_backend.py): Gelesen wird
    immer alles, geschnitten wird erst für Datei und Pegelanzeige.

    Damit sich die beiden Sichten im Test unterscheiden lassen, trägt
    jeder Kanal seine Nummer als Wert.
    """

    BYTES = 4
    RAHMEN = 32

    #
    # Wie das echte Backend: Ein Strom ist offen. Der Recorder
    # weigert sich ohne das (siehe Recorder.bereit) - zu Recht, ohne
    # Interface gibt es nichts zu lesen.
    #
    opened = True

    def __init__(self, channels=2, rate=48000, native_channels=None):

        self.channels = channels
        self.native_channels = (
            channels if native_channels is None else native_channels
        )
        self.rate = rate

        self._chunk = b"".join(
            (kanal + 1).to_bytes(self.BYTES, "little")
            for _ in range(self.RAHMEN)
            for kanal in range(self.native_channels)
        )

    def read(self):
        time.sleep(0.005)
        return self._chunk

    def aufnahmebreite(self, data: bytes) -> bytes:
        """Wie der echte Schnitt: die ersten `channels` je Rahmen."""

        if self.channels >= self.native_channels:
            return data

        rahmen = self.native_channels * self.BYTES
        breite = self.channels * self.BYTES

        return b"".join(
            data[stelle:stelle + breite]
            for stelle in range(0, len(data), rahmen)
        )


class FakeWriter:
    """Ersetzt den echten W64Writer - schreibt nirgendwohin."""

    def __init__(self):
        self.filename = None
        self.opened = False
        self.write_count = 0
        self.close_count = 0
        self.directory = Path(".")

        #
        # Was geschrieben wurde - daran laesst sich nachsehen, dass
        # die Datei nur die aufgenommenen Kanaele bekommt.
        #
        self.blocks = []

    def open(self, channels, sample_rate, bits_per_sample,
             name_prefix="Soundcheck", start_channel=1,
             trenner="-"):
        self.start_channel = start_channel
        self.filename = "fake.w64"
        self.opened = True

    def write(self, data):
        self.write_count += 1
        self.blocks.append(data)

    def close(self):
        self.opened = False
        self.close_count += 1


# ----------------------------------------------------------------
# 1. Reine Pegelprüfung, ohne dass geschrieben wird
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=4))
recorder.writer = FakeWriter()

assert recorder.start_monitoring() is True
time.sleep(0.05)

assert recorder.monitoring is True
assert recorder.recording is False
assert recorder.writer.opened is False, "Beim reinen Pegeltest darf keine Datei geöffnet werden."
assert len(recorder.levels) == 4, "Pegel-Liste muss zur Kanalzahl passen."
print("OK: Pegelprüfung läuft, ohne aufzuzeichnen")

# Doppeltes Starten soll fehlschlagen
assert recorder.start_monitoring() is False
print("OK: Pegelprüfung kann nicht doppelt gestartet werden")

recorder.stop_monitoring()
assert recorder.monitoring is False
assert recorder.writer.close_count == 0, "stop_monitoring() darf die (nie geöffnete) Datei nicht schließen."
print("OK: Pegelprüfung stoppt sauber, ohne die Datei anzufassen")

# ----------------------------------------------------------------
# 2. Pegelprüfung -> nahtloser Übergang in echte Aufnahme
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=2))
recorder.writer = FakeWriter()

assert recorder.start_monitoring() is True
time.sleep(0.02)
thread_during_monitoring = recorder._thread

assert recorder.start() is True, "Aufnahme sollte während laufender Pegelprüfung startbar sein."
assert recorder.recording is True
assert recorder.writer.opened is True
assert recorder._thread is thread_during_monitoring, (
    "Der Aufnahme-Thread sollte beim Wechsel von Pegelprüfung zu "
    "Aufnahme NICHT neu gestartet werden."
)
print("OK: Übergang von Pegelprüfung zu Aufnahme ohne Thread-Neustart")

time.sleep(0.05)
assert recorder.writer.write_count > 0, "Es sollte in die Datei geschrieben worden sein."

recorder.stop()
assert recorder.recording is False
assert recorder.monitoring is False
assert recorder.writer.close_count == 1
print("OK: stop() beendet Aufnahme UND Pegelprüfung, Datei wird geschlossen")

# ----------------------------------------------------------------
# 3. Aufnahme direkt starten (ohne vorherige Pegelprüfung)
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=8))
recorder.writer = FakeWriter()

assert recorder.start() is True
assert recorder.recording is True
assert recorder.monitoring is True
assert len(recorder.levels) == 8
time.sleep(0.03)
assert recorder.writer.write_count > 0

recorder.stop()
assert recorder.writer.close_count == 1
print("OK: Direktes Starten der Aufnahme funktioniert weiterhin wie zuvor")

# ----------------------------------------------------------------
# 4. stop_monitoring() waehrend einer echten Aufnahme ist ein No-Op
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=2))
recorder.writer = FakeWriter()

recorder.start()
recorder.stop_monitoring()  # sollte NICHT die Aufnahme abwuergen
assert recorder.recording is True, "stop_monitoring() darf eine laufende Aufnahme nicht beenden."
recorder.stop()
print("OK: stop_monitoring() waehrend einer Aufnahme ist wirkungslos (stop() ist dafuer zustaendig)")

# ----------------------------------------------------------------
# 5. Die Lichtsteuerung als dritter Interessent am selben Strom
#
# ALSA erlaubt nur einen Leser. Die musikgesteuerte Lichtshow muss
# aber mithoeren, auch wenn niemand aufnimmt oder Pegel prueft.
# Deshalb merkt sich der Recorder, WER ihn braucht, statt nur "laeuft
# ja/nein".
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=2))
recorder.writer = FakeWriter()

recorder.start_analysis()
time.sleep(0.02)

assert recorder.stream_active is True, "Das Licht muss den Strom oeffnen koennen."

#
# Aber es prueft niemand Pegel - die Oberflaeche darf das nicht
# behaupten.
#
assert recorder.monitoring is False, (
    "Wenn nur das Licht mithoert, laeuft keine Pegelpruefung."
)

print("OK: Das Licht haelt den Strom offen, ohne als Pegelpruefung zu gelten")

#
# Und die Pegelpruefung muss trotzdem startbar sein. Eine Pruefung
# auf "Thread laeuft" haette hier False geliefert - der Knopf im
# Webinterface haette einfach nichts getan.
#
assert recorder.start_monitoring() is True, (
    "Bei laufender Lichtshow muss sich die Pegelpruefung starten lassen."
)
assert recorder.monitoring is True

recorder.stop_monitoring()

assert recorder.monitoring is False
assert recorder.stream_active is True, (
    "Das Beenden der Pegelpruefung darf die Lichtshow nicht abwuergen."
)

print("OK: Pegelprüfung lässt sich neben der Lichtshow starten und beenden")

#
# Aufnahme dazu, dann Stop: Die Aufnahme endet, das Licht hoert
# weiter mit.
#
assert recorder.start() is True
time.sleep(0.03)
assert recorder.recording is True

recorder.stop()

assert recorder.recording is False
assert recorder.writer.close_count == 1
assert recorder.stream_active is True, (
    "Stop der Aufnahme darf die Lichtshow nicht mitnehmen."
)

print("OK: Stop der Aufnahme lässt die Lichtshow weiterlaufen")

#
# Meldet sich das Licht ab und will sonst niemand etwas, ist Schluss.
#
recorder.stop_analysis()

assert recorder.stream_active is False, (
    "Ohne Interessenten muss der Thread wirklich aufhoeren."
)
assert recorder._thread is None

print("OK: Geht der letzte Interessent, hört der Thread auf")


# ----------------------------------------------------------------
# 6. Mithoerer bekommen die Bloecke - und koennen nichts kaputtmachen
# ----------------------------------------------------------------

recorder = Recorder(FakeBackend(channels=2))
recorder.writer = FakeWriter()

gesehen = []

recorder.add_consumer(lambda block: gesehen.append(len(block)))
recorder.start_analysis()

time.sleep(0.05)

assert len(gesehen) > 0, "Der Mithoerer hat keine Bloecke bekommen."

print("OK: Ein Mithörer bekommt die gelesenen Blöcke")

#
# Und jetzt der Fall, der zaehlt: Ein Mithoerer wirft. Die Aufnahme
# darf davon nichts merken - eine kaputte Lichtshow mitten in einem
# Konzert waere sonst eine abgebrochene Aufnahme.
#
def kaputt(block):
    raise RuntimeError("absichtlich kaputt")

recorder.add_consumer(kaputt)

recorder.start()

vorher = recorder.writer.write_count

time.sleep(0.05)

assert recorder.recording is True, (
    "Ein werfender Mithoerer hat die Aufnahme beendet."
)
assert recorder.writer.write_count > vorher, (
    "Nach dem Fehler eines Mithoerers wurde nicht weitergeschrieben."
)
assert kaputt not in recorder._verbraucher, (
    "Ein werfender Mithoerer muss abgemeldet werden, sonst wirft er ewig weiter."
)

recorder.stop()
recorder.stop_analysis()

print("OK: Ein werfender Mithörer wird abgemeldet, die Aufnahme läuft weiter")


# ----------------------------------------------------------------
# 7. Mithoerer bekommen ALLE Kanaele, die Datei nur die aufgenommenen
#
# Am X32 im Proberaum aufgefallen: In der Lichtshow standen nur 18
# Kanaele zur Auswahl statt der 32, die das Pult liefert. 18 ist die
# Vorgabe fuer die AUFNAHME - und der Schnitt darauf passierte
# frueher schon beim Lesen. Die Lichtshow haengt als Mithoerer am
# selben Strom und sah deshalb nur den Ausschnitt.
#
# Geschnitten wird jetzt erst fuer Datei und Pegelanzeige. Die
# Lichtshow darf damit auf einen Kanal hoeren, den niemand aufnimmt -
# etwa einen AUX-Weg, auf dem ein eigener Mix fuers Licht liegt.
# ----------------------------------------------------------------

backend = FakeBackend(channels=4, native_channels=10)

recorder = Recorder(backend)
recorder.writer = FakeWriter()

bloecke = []

recorder.add_consumer(bloecke.append)
recorder.start()

time.sleep(0.05)

recorder.stop()
recorder.stop_analysis()

assert bloecke, "Der Mithoerer hat keine Bloecke bekommen."

#
# Der Mithoerer sieht die volle Rahmenbreite ...
#
assert len(bloecke[0]) == 10 * 4 * FakeBackend.RAHMEN, (
    "Der Mithoerer bekommt einen geschnittenen Block - dann kann die "
    f"Lichtshow die oberen Kanaele nicht hoeren: {len(bloecke[0])}"
)

#
# ... und darin wirklich die oberen Kanaele: Jeder Kanal traegt seine
# Nummer, der zehnte muss also eine 10 liefern.
#
zehnter = int.from_bytes(bloecke[0][9 * 4:10 * 4], "little")

assert zehnter == 10, (
    f"Der zehnte Kanal fehlt im Block des Mithoerers: {zehnter}"
)

#
# In die Datei geht dagegen nur, was aufgenommen werden soll.
#
assert recorder.writer.write_count > 0, "Es wurde nichts geschrieben."

geschrieben = recorder.writer.blocks[0]

assert len(geschrieben) == 4 * 4 * FakeBackend.RAHMEN, (
    "Die Datei bekommt mehr Kanaele als eingestellt - die Aufnahme "
    f"waere breiter als angesagt: {len(geschrieben)}"
)

#
# Und zwar die ersten vier, nicht irgendwelche.
#
erster_rahmen = [
    int.from_bytes(geschrieben[i * 4:(i + 1) * 4], "little")
    for i in range(4)
]

assert erster_rahmen == [1, 2, 3, 4], erster_rahmen

print("OK: Mithörer hören alle Kanäle, die Datei bekommt nur die aufgenommenen")


print("Alle Tests erfolgreich.")
