# Umbau: Üben als eigene Karte (Version 3.0)

Dieses Dokument begleitete den Umbau auf dem Zweig `v3-ueben`. Es steht
im Projekt und nicht in einem Chatverlauf, weil der Umbau über mehrere
Sitzungen lief: Wer hier weiterarbeitet - ich beim nächsten Mal oder
jemand anderes -, soll den Stand und vor allem die BEGRÜNDUNGEN
vorfinden, nicht nur das Ergebnis.

**Stand: fertig.** Alles unten Beschriebene ist gebaut, am Gerät
abgenommen und in 3.0.0 nach `main` gegangen; der Zweig `v3-ueben` ist
danach gelöscht worden. Gebaut sind die Stufen 1 bis 5, die Messung der
Laufzeit durch das Pult (10 bis 19 ms am Testgerät), die getrennte
Dateiverwaltung und die Sperrmatrix als Tabelle im Versuch.

Dazu kam, was im Plan unten noch nicht steht, weil es sich erst beim
Testen ergab:

- der Eingangsschalter A/D ↔ USB in den Kanalzügen (X-Air), vorher am
  Pult selbst erfragt statt einer Bibliothek geglaubt,
- das Kopieren VOM USB-Stick, rekursiv, mit Ordnerwahl im Dialog,
- Stems, die schon auf dem Gerät liegen dürfen,
- die Stillstands-Wache, die misst, wann der Prozess nicht mehr
  antwortet, und dazu vermerkt, ob Ton geflossen ist,
- der Umzug der Testreihe nach `tests/`.

Was der Plan unten anders vorsah als das Gebaute, steht bei der
jeweiligen Stufe. Die Versionsangabe ganz unten („2.11.0 bis 2.14.0")
ist von der Wirklichkeit überholt worden: Der Umbau lief als
3.0.0-dev1 bis -dev32 und wurde als 3.0.0 zusammengeführt.

---


## Warum

Heute ist „Üben" ein Anhängsel der Soundcheck-Karte: Ein Übungsmix
(`_p`) liegt in derselben Liste wie die Aufnahmen, und der
Wiedergabeknopf heißt je nach Auswahl „Soundcheck" oder „Üben".
Angelegt wird so ein Mix im Dialog „Alle Dateien". Das ist gewachsen,
nicht entworfen.

Das Ziel: Üben wird eine eigene Sache mit eigener Karte — und weil
sie dasselbe tut wie der Musikspieler (eine Datei auf bestimmten
Kanälen abspielen, mit Transport und Positionsregler), teilt sie sich
dessen Platz. Dazu die Möglichkeit, das Geübte mitzuschneiden, wofür
die Aufnahme einen Kanalbereich braucht statt immer „die ersten N".

## Was heute da ist — und was davon trägt

**Zwei Abspielwege, die sich unterscheiden wie Tag und Nacht:**

| | Soundcheck (`player/player.py`) | Musik (`player/music_player.py`) |
|---|---|---|
| Quelle | W64 über eigenen Reader | alles über ffmpeg |
| Kanäle | die des Files, ab Kanal 1 | Stereo, ab wählbarem Kanal |
| Pause | **nein** | ja |
| Spulen | **nein** | ja |
| Position/Dauer | nur Dauer | beides |
| Ordner, Zufall, Überspringen | nein | ja |

Zum Üben braucht man genau das, was der Musikspieler hat und der
Soundcheck-Spieler nicht: anhalten, zurückspulen, eine Stelle
wiederholen.

**Drei Sperren, die heute gelten** (`core/application/aufnahme.py`,
`musik.py`):

- Aufnahme ⊘ Soundcheck-Wiedergabe
- Soundcheck-Wiedergabe ⊘ Musik
- Musik ⊘ Soundcheck-Wiedergabe
- **Aufnahme + Musik ist erlaubt** — und läuft am Gerät.

Das Letzte ist der Beweis, dass das Vorhaben trägt: Aufnehmen und
Abspielen gleichzeitig geht auf dem XR18, ein Aufnahme- und ein
Wiedergabestrom nebeneinander. Was *nicht* geht, sind zwei
Wiedergabeströme auf demselben Gerät — deshalb schließen sich Musik
und Soundcheck aus. **Genau deshalb ist „eine Karte mit Umschalter"
richtig und zwei Karten nebeneinander falsch:** Zwei Karten würden
etwas anbieten, was die Hardware nicht kann.

**Die Aufnahme schneidet immer ab Kanal 1**
(`audio/channel_extractor.py`). Das Gegenstück für die Wiedergabe
kann es schon: `ChannelInserter` kennt `start_channel`.

## Die Entscheidung, an der alles hängt

**Übungsmixe werden künftig vom Musikspieler abgespielt, nicht vom
Soundcheck-Spieler.**

Der Grund ist nicht Bequemlichkeit, sondern Wartung: Pause und
Position sind heikel (zwei echte Fehler in 2.10.1 saßen genau dort).
Ein zweiter Spieler mit Pause und Spulen hieße, dieselben Fehler ein
zweites Mal zu machen und ein zweites Mal zu finden.

Machbar ist es, weil `TrackDecoder.open()` die Kanalzahl schon als
Parameter hat (`-ac`) — sie steht nur überall auf der Konstanten
`CHANNELS = 2`. ffmpeg dekodiert eine 8-Kanal-W64 genauso wie ein
MP3, und `ChannelInserter` legt das Ergebnis ab dem gewünschten Kanal
auf.

**Der Vorbehalt hat sich bestaetigt - ffmpeg kann es NICHT.**
Nachgemessen an einer echten Datei: Der Kopf ist in Ordnung
(WAVE_FORMAT_EXTENSIBLE, 32-Bit-Behaelter, 24 gueltige Bits,
BlockAlign = Kanaele * 4), ffmpeg entscheidet sich trotzdem fuer
`pcm_s24le` und liest drei Byte je Wert, wo vier stehen. Aus zwei
Sekunden werden 2,67, jeder Kanal landet woanders, zu hoeren waere
Rauschen.

Geloest anders als geplant, und besser: XRack liest seine eigenen
Dateien selbst (player/w64_decoder.py legt die Dekoder-Form ueber den
vorhandenen, bewaehrten reader/w64_reader.py). Der Musikspieler
entscheidet je Datei, wer liest - alles Uebliche ffmpeg, `.w64` XRack
selbst. Pause, Spulen und Position kommen weiterhin vom Musikspieler.

Dabei kam heraus, dass XRacks eigener Leser fast in dieselbe Falle
getappt waere: Er las ValidBitsPerSample (24) und uebersprang
BlockAlign. Fuer das blosse Durchreichen von Bloecken fiel das nie
auf; sobald daraus eine Laenge oder ein Sprung gerechnet wird, kaeme
alles um ein Drittel daneben. Jetzt liest er BlockAlign.

## Vier Stufen

Jede Stufe ist für sich brauchbar und für sich zu testen. Nach jeder
kann das Gerät im Proberaum stehen.

### Stufe 1 — Das Aufnahmefenster: „ab Kanal X, N Kanäle"

Unabhängig vom Rest nützlich: Am X32 nimmt man damit die Kanäle 17–24
auf, ohne 16 leere Spuren mitzuschleppen.

- `ChannelExtractor` bekommt `start_channel` (Gegenstück zum
  `ChannelInserter`).
- Ein zweites Auswahlfeld in der Soundcheck-Karte, daneben das
  vorhandene für die Anzahl. Gemerkt in `config/state.json` wie
  `record_channels`.
- Die Pegelanzeige folgt dem Fenster (sie hängt an derselben Breite).
- **Der Haken, der mitgedacht werden muss:** Eine Aufnahme ab Kanal 9
  muss beim virtuellen Soundcheck wieder auf Kanal 9 landen, nicht
  auf 1. Der Startkanal muss also mit der Datei reisen.

  Vorschlag: im Dateinamen, wie schon die Art der Datei
  (`core/recording_kind.py` begründet das ausführlich — die Zuordnung
  reist über USB, Download und Backup mit). Aus `Probe-3_s.w64` wird
  bei einem Fenster ab Kanal 9 `Probe-3_s9.w64`; ohne Ziffer gilt
  wie bisher Kanal 1, alte Dateien bleiben gültig.
- `Player.start()` bekommt den Startkanal und reicht ihn an den
  `ChannelInserter` durch.

### Stufe 2 — Der Musikspieler lernt Mehrkanal

Noch ohne Umbau der Oberfläche: Der „Üben"-Knopf in der
Soundcheck-Karte spielt den Übungsmix ab jetzt über den Musikspieler.

- `probe_channels()` neben `probe_duration()` in
  `player/track_decoder.py`.
- `MusicPlayer` nimmt die Kanalzahl der Datei statt der Konstanten;
  Stereo bleibt der Normalfall.
- Damit kann ein Übungsmix pausiert, gespult und ab einem wählbaren
  Kanal ausgegeben werden.

### Stufe 3 — Die Karte mit dem Umschalter

- Im Kopf der Karte ein Umschalter **Musik | Üben** (zwei Knöpfe, ein
  Zustand). Der Körper darunter wird getauscht; der Rahmen, der
  Transport und der Schnellregler bleiben, was sie sind.
- Gesperrt, solange etwas läuft — ein Umschalten mitten in der
  Wiedergabe wäre eine Falle.
- Der Zustand wird am **Gerät** gemerkt (`state.json`), nicht im
  Browser: Was das Rack tut, soll auf jedem Tablet gleich aussehen.
- Die Üben-Seite bringt mit: Auswahl des Übungsmixes (die `_p`-Dateien
  aus `recordings/`), Startkanal, Transport, Position — und den Knopf
  „Übungsmix erstellen", der heute im Dialog „Alle Dateien" versteckt
  ist.

**Gebaut (3.0.0-dev3).** Was dabei zur Sprache kam und nicht im
Entwurf stand:

- **Der Schnellregler folgt der Quelle, die die Karte zeigt.** Er
  hing am Feld der Musik. Beim Üben regelte man damit ein Paar, aus
  dem gar nichts kommt — und schlimmer: Beim Wechsel des Üben-Kanals
  vergleicht `handlePairChange()` gegen dieses Paar, XRack böte also
  an, am Pult die FALSCHE Kopplung zu lösen. Sichtbar wird der
  Unterschied nur im Ruhezustand; läuft erst etwas, folgt auch das
  Musikfeld dem laufenden Kanal. Genau dort wird es deshalb geprüft
  (`test_ueben_karte.py`, Abschnitt 15).

- **Der Üben-Kanal wird beim Wählen gemerkt**, nicht erst beim
  Starten — eigene Einstellung neben der für Musik (`/api/practice/channel`),
  denn ein Übungsmix belegt mehrere Kanäle und liegt selten dort, wo
  die Musik liegt.

- **„Übungsmix erstellen" kehrt dorthin zurück, wo es herkam.** Der
  Dialog saß bisher nur im Fenster „Alle Dateien" und öffnete es beim
  Schließen wieder. Von der Üben-Karte aus hieße das: Es geht
  unvermittelt die Dateiliste auf, die man nie geöffnet hat.

- **Die Sperre steht an zwei Stellen** — im Browser (die Knöpfe sind
  zu, mit Grund im Tooltip) und in `Application.set_player_mode()`.
  Die zweite ist die verbindliche: Was nur die Oberfläche verhindert,
  verhindert sie nur, solange sie stimmt.

**Nachgebessert nach dem ersten Blick auf das Gerät (3.0.0-dev4).**
Vier Dinge, die erst an der fertigen Karte auffielen:

- **Das Kanalfeld in der Üben-Karte ist weg.** Es bot Stereopaare an
  („Kanal 1+2"), während ein Übungsmix acht Kanäle belegen kann — es
  hat also gelogen. Und es stellte vor jedem Üben neu zur Wahl, was
  einmal feststeht: Ein Mix wird für einen Platz im Pult gebaut.
  Gewählt wird der erste Kanal jetzt beim **Erstellen**, er wandert in
  den Dateinamen (`Probe-1_p9.w64`) und wird beim Üben von dort
  gelesen — dieselbe Regel wie bei Aufnahmen, mit derselben
  Begründung. Die Dateizeilen im Erstellen-Dialog folgen der Wahl,
  sonst stünde dort weiter „Kanal 1+2" über einer Datei, die auf 9+10
  landet.

- **Gestartet wird mit dem Transportknopf.** Der eigene Startknopf
  oben in der Karte war zweierlei Bedienung für eine Sache. Solange
  nichts läuft, heißt der Stop-Knopf „Üben"; läuft etwas, heißt er
  „Stop" — wie der eine Knopf in der Soundcheck-Karte.

- **Der Schnellregler ist beim Üben ausgeblendet.** Er regelt EIN
  Stereopaar. Beim Übungsmix wäre das ein Achtel des Tons, und warum
  der Rest nicht leiser wird, sieht man dem Regler nicht an. Geregelt
  wird beim Üben am Pult, Spur für Spur — das ist ja der Sinn.

- **Der Positionsregler hing unterhalb der Karte in der Luft.** Nicht
  die Üben-Karte war schuld, sondern eine Regel, die seit jeher so
  stand: Ab dem zweispaltigen Raster bekamen Spieler- und
  Bluetooth-Karte feste 2/3 und 1/3 der Höhe (`flex-basis: 0`,
  `min-height: 0`), gleich wie viel darin stand. Passte es nicht, lief
  der Inhalt unten heraus — ohne Rahmen, ohne Fehlermeldung. Zwei
  Zeilen mehr im Üben-Kopf haben es sichtbar gemacht. Jetzt ist die
  Inhaltshöhe die Untergrenze (`flex-basis: auto`, `min-height: 100%`
  am Stapel); der überschüssige Platz wird weiterhin 2:1 verteilt.
  Gemessen wird das seither im Browser (`test_ueben_karte.py`,
  Abschnitt 16) — mit den echten Stilvorlagen, denn ohne sie fällt so
  etwas in keinem Test auf.

Was noch offen ist: Die Soundcheck-Karte spielt Übungsmixe weiterhin
selbst ab. Es gibt den Weg also zweimal — das räumt Stufe 4 auf.

### Die Dateiverwaltung: getrennt, und die Versuche beim Stück (dev11)

Übungsmixe und Mitschnitte sind aus der Dateiverwaltung der
Soundcheck-Karte verschwunden; die Üben-Karte hat ihre eigene.

**Es ist aber derselbe Dialog**, nur in einer anderen Betriebsart
(`dateienModus`). Hochladen, Herunterladen, auf USB kopieren,
Löschen, mehrere auf einmal löschen — das ist zweimal dieselbe
Verwaltung. Zweimal gebaut hiesse, jede künftige Änderung zweimal zu
machen und beim zweiten Mal die eine Hälfte zu vergessen.

**Die Zuordnung steht im Dateinamen** — aus denselben Gründen wie das
Kürzel und der Startkanal: Sie reist über USB, Download und Backup
mit, und XRack führt nirgends Buch. Zum Übungsmix `Umbrella-1_p.w64`
heissen die Versuche `Umbrella-1-Take1_s9.w64`, `-Take2` und so fort.
Der Name trägt damit vier Dinge, und keines verdeckt das andere:
Stück, Nummer des Versuchs, Art (`_s`) und erster Kanal (`9`).

Damit `Take-1` nicht wie ein Abzug aussieht, ist der Trenner vor der
laufenden Nummer wählbar (`AudioWriter.create_filename(trenner=...)`);
für Mitschnitte ist er leer, das Präfix trägt den Bindestrich schon.

**„Dazu hören" zeigt nur die Versuche zum gewählten Stück.** Alles
andere wäre eine Liste, die mit jedem Üben länger wird und in der man
sucht — und ein Versuch zu einem anderen Stück ergibt beim
Zusammenhören ohnehin nur Unsinn.

Zwei Entscheidungen dabei:

- **Mitschnitte fehlen auch in der Soundcheck-Liste.** Sie sind
  Aufnahmen und heissen auch so, ergeben aber nur neben ihrem Mix
  einen Sinn; nach ein paar Übungsabenden wären sie dort die Mehrheit,
  und der Soundcheck fände sich zwischen ihnen nicht wieder.
- **Ein Versuch ohne Mix ist wieder eine gewöhnliche Aufnahme.** Wird
  ein Übungsmix gelöscht, tauchen seine Versuche in der
  Soundcheck-Verwaltung auf — erreichbar, löschbar, nicht verloren.

„Übungsmix erstellen" sitzt jetzt in dieser Verwaltung: Ein Übungsmix
ist eine Datei, und Dateien macht man in der Dateiverwaltung.

### Stufe 3b — Mitschneiden und Zusammenhören

**Teil 1 gebaut (3.0.0-dev5): mitschneiden.**

Kein eigener Knopf „Üben + mitschneiden", sondern ein **Schalter**
neben „Wiederholen" — gestartet wird weiter mit dem einen
Transportknopf. Zwei Startknöpfe für dieselbe Sache wären genau das,
was in dev4 schon einmal weggeräumt wurde.

Was daran nicht beliebig ist:

- **Erst die Aufnahme, dann der Ton.** Läuft der Mitschnitt schon,
  wenn der erste Ton kommt, fehlt am Anfang nichts; andersherum wäre
  der Einsatz weg — und gerade der ist beim Üben das Interessante.
  Ganz gleichzeitig geht es nicht und muss es nicht: Der Vorlauf von
  Millisekunden arbeitet der Laufzeit durchs Pult entgegen.
- **Gestoppt wird nur das Eigene.** Lief die Aufnahme schon vorher
  (von der Soundcheck-Karte aus), bleibt sie laufen. Dafür merkt sich
  XRack, ob DIESER Übungslauf sie gestartet hat.
- **Kein halber Zustand.** Lässt sich der Übungsmix nicht öffnen, wird
  die begonnene Aufnahme wieder beendet — sonst liefe sie weiter, ohne
  dass jemand sie gestartet hat.
- **Ohne offenes Gerät wird vorher abgelehnt**, nicht unterwegs: Sonst
  liefe der Mix, und den Mitschnitt, den man mitlaufen glaubt, gäbe es
  nicht.
- Aufgenommen wird das **Aufnahmefenster aus der Soundcheck-Karte**
  (Stufe 1). Welche Kanäle das sind, steht in der Üben-Karte daneben —
  ein Mitschnitt, von dem man nicht weiss, was darauf ist, ist keiner.

**Teil 2 gebaut (3.0.0-dev6): zusammenhören.**

Ein zweites Auswahlfeld „Dazu hören" in der Üben-Karte. Ist ein
Versuch gewählt, legt XRack beide Dateien in EINEN Wiedergabestrom —
den Mix auf seine Kanäle, den Versuch auf seine. Mehr als einen Strom
gibt das Interface nicht her; zwei Dateien in einem Strom sind kein
Problem.

- **Der Versuch liegt auf den Kanälen, auf denen er aufgenommen
  wurde** — sie stehen in seinem Namen (`_s9`). Genau dafür reist der
  Startkanal seit Stufe 1 mit der Datei.
- **Die Ausgabe hat die volle Kanalzahl des Interfaces.** Damit ist
  der `ChannelInserter` im Backend ein Durchreicher, und es bleibt bei
  EINER Schleife über die Rahmen statt zweier — auf dem Pi ist das der
  heißeste Punkt im Lesethread. Ohne Versuch bleibt der Weg von Stufe 2
  unverändert (Backend setzt ein, `UebenDecoder` ist nicht beteiligt).
- **Der Mix gibt die Länge vor.** Ein kürzerer Versuch wird ab seinem
  Ende still, ein längerer endet mit dem Mix: Man übt zum Stück, nicht
  umgekehrt.
- **Ein Sprung bewegt beide.** Sonst liefe der Versuch nach dem Spulen
  gegen eine andere Stelle, und das Üben wäre wertlos.
- **Was über den Rand des Interfaces ragt, wird vorher abgelehnt** —
  nicht unterwegs abgeschnitten: Ein halbes Stereopaar ist kein
  Stereo, und in den nächsten Rahmen zu schreiben hiesse, dass ab dort
  alles verschoben ist.

Geprüft wird mit echten Dateien (`test_ueben_mitschnitt.py`): jeder
Kanal trägt seinen eigenen Wert, eine Verschiebung um einen einzigen
Kanal fällt sofort auf.

### Der Gleichlauf: was sich rechnen lässt und was nicht (3.0.0-dev9)

Der Versuch hinkt dem Mix hinterher. Die Verzögerung hat zwei Teile,
und nur einer davon ist eine Zahl, die man ausrechnen kann.

**Teil 1: die Anlaufzeit in XRack — beseitigt, nicht ausgerechnet.**
Zwischen „Aufnahme starten" und „der erste Ton geht hinaus" liegen das
Öffnen von ALSA, ein Threadstart und das Anlegen der Datei: zusammen
einige zehn Millisekunden, und **jedes Mal unterschiedlich viele**.
Dieser Zufall stand bisher im Mitschnitt und liess sich nachher durch
nichts mehr herausrechnen — ein fester Korrekturwert wäre an ihm
gescheitert. Jetzt beginnt die Aufnahme mit dem ERSTEN BLOCK, der zum
Interface geht (`MusicPlayer._beim_ersten_block`). Damit ist der Teil
weg, statt geschätzt zu sein.

**Teil 2: die Laufzeit des Weges — messbar, nicht berechenbar.**
XRack schreibt in den ALSA-Puffer, das Pult wandelt, mischt und
schickt zurück, XRack liest wieder aus einem Puffer. Was davon
feststeht:

- Die Periodengrösse ist 1024 Rahmen — bei 48 kHz 21,3 ms je Periode.
  Verzögert wird aber nicht um eine Periode, sondern um so viel, wie
  der Puffer gerade trägt, und ALSA beginnt erst zu spielen, wenn er
  voll genug ist. Wie voll, sagt ALSA nur auf Nachfrage, und
  pyalsaaudio reicht diese Frage nicht durch.
- Dazu die Strecke durch USB und durch das Pult: Wandlung, Mischung,
  Routing. Sie hängt am Pultmodell, an der Samplerate und daran,
  welchen Weg das Signal im Pult nimmt. XRack kann sie nicht wissen.

Eine Zahl daraus zu rechnen hiesse raten. Deshalb ist es ein **Wert,
den man setzt** (`practice_offset_ms`, gemerkt in `state.json`, Feld
in der Üben-Karte): nach Gehör einstellbar, später aus einer Messung
zu füllen. Angewandt wird er beim Zusammenhören — steht der Mix an
Stelle p, wird der Mitschnitt ab p+Versatz gelesen. Nur der
Mitschnitt, und nie negativ: Vorauseilen wäre Hellsehen.

**Die Messung (gebaut, 3.0.0-dev10).** Weil Teil 1 fest ist, ist
Teil 2 eine Konstante der Anlage — einmal messen genügt. Gemessen wird
genau das, was nachher korrigiert wird: ein Übungslauf mit einem
Klick-Mix, mitgeschnitten über den ganz normalen Weg. Steht der Klick
im Mix bei einer Sekunde und im Mitschnitt bei 1,08 s, ist die
Laufzeit 80 ms — ohne eine einzige Annahme über Puffer, Perioden oder
Pulte (`core/laufzeit_messung.py`).

Drei Entscheidungen, die dabei etwas kosten würden, wenn man sie
anders träfe:

- **Der Klick geht auf ALLE Ausgabekanäle.** XRack weiss nicht,
  welchen Weg das Pult zurückführt — so ist es egal, und es genügt
  der Weg, der zum Üben ohnehin eingerichtet ist.
- **Scharfer Anfang, weiches Ende.** Gesucht wird die erste Stelle
  über der Schwelle. Mit einem sanften Einschwingen fände man sie ein
  paar Abtastwerte später — jedes Mal gleich viel, aber jedes Mal zu
  spät.
- **Die erste Flanke zählt, nicht die lauteste Stelle.** Was danach
  kommt, ist Nachhall und Nachregeln des Weges; die Laufzeit ist der
  Anfang.
- **Kein Klick ist ein Befund, kein Messwert.** Ist der Weg im Pult
  nicht geschlossen, kommt eine Begründung statt einer Zahl. Eine Zahl
  auszugeben wäre das Schlimmste: Sie würde stillschweigend falsch
  korrigieren.

Voraussetzung bleibt die Schleife im Pult. Die kann XRack nicht selbst
herstellen — deshalb fragt der Knopf vorher und sagt, was einzurichten
ist.

**Was die ersten Messungen am Gerät gezeigt haben (dev14/dev15).**
Zehn Messungen, je drei Läufe. Die Hälfte scheiterte mit „Der Klick
steht vor seiner eigenen Zeit"; die übrigen sahen so aus:

    0, 70, 69   0, 85, 84   0, 0, 73   1, 0, 85   0, 88, 71

Das Muster ist eindeutig: **der erste Lauf fast immer 0, die
folgenden 70 bis 88 ms.** Dahinter stecken ZWEI Fehler, die
gegeneinander wirken — und beide verschieben den Beginn des
Mitschnitts:

- **Der Strom steht still.** Sein erster Block kostet Zeit: Der
  Lesefaden muss anlaufen, ALSA den Strom in Gang bringen und eine
  volle Periode sammeln. Der Mitschnitt beginnt zu **spät**, die
  Messung fällt zu klein aus — 0 ms, und wenn es noch später wird,
  steht der Klick vor seiner eigenen Zeit und die Messung lehnt ab.
- **Der Strom läuft, wird aber nicht gelesen.** Dann füllt ALSA
  seinen Ring weiter, und der erste Block ist der älteste darin: Der
  Mitschnitt beginnt zu **früh**, die Messung fällt zu gross aus.
  Genau das waren die 70 bis 88 ms in den Läufen zwei und drei —
  ungefähr ein Puffer.

Beide Fehler verschwinden, wenn der Faden schon liest, bevor der
erste Ton hinausgeht. Dann steht die Zahl: **10 bis 19 ms** über zehn
Messungen am XR18 — USB hin, Pult, USB zurück.

Damit ist auch die Ausgangsfrage beantwortet, und zwar anders als
gedacht: Die 1024 Samples des Wiedergabepuffers stecken **nicht** in
dieser Zahl, und das ist richtig so. Die Stelle im Klick-Mix bildet
sich fest auf die Zeit seit dem Beginn der Wiedergabe ab — das Gerät
holt sich die Rahmen im Takt der Samplerate. Der Puffer sagt nur, wie
lange ein geschriebener Rahmen noch wartet, nicht, wann Sekunde eins
des Stücks erklingt.

**Die Folge (dev15):** Vor dem ersten Ton bringt XRack den
Aufnahmestrom in Gang und wartet, bis er wirklich liefert — nicht
eine feste Zeit lang, sondern bis Blöcke ankommen
(`Recorder.bloecke_gelesen` als Lebenszeichen). Das gilt für die
Messung UND fürs Mitschneiden beim Üben; beide müssen denselben Weg
gehen, sonst passt der gemessene Versatz nicht zu dem, was er
ausgleichen soll. Übrig bleibt als Unschärfe die Lage innerhalb einer
Periode, gut 21 ms bei 48 kHz — und genau dort liegt seither auch die
Schwelle, ab der XRack eine Messreihe als unsicher meldet.

Gemessen wird **dreimal**, mit Anzeige der Einzelwerte: Drei gleiche
Zahlen sind eine Eigenschaft der Anlage, drei verschiedene eine
Warnung. Genommen wird der mittlere Wert, nicht der Durchschnitt — ein
Ausreisser zöge den Durchschnitt mit sich.

- Knopf **„Üben + mitschneiden"**: startet Übungsmix und Aufnahme in
  einem Zug (Aufnahmefenster aus Stufe 1 - beim Üben typisch zwei
  Kanäle ab dem Kanal des eigenen Instruments).
- In der Üben-Karte ein zweites Auswahlfeld: **Mitschnitt**. Ist einer
  gewählt, legt der Spieler beide Dateien in denselben Strom
  (`ChannelInserter` mit zwei Quellen).
- Wiederholen: ein Schalter „ganzes Stück wiederholen". Im
  Musikspieler ist das die vorhandene Schleife über die Titelliste,
  angewandt auf einen Titel - deshalb billig.

### Stufe 5 — Aus Versuch und Mix eine Datei

**Gebaut (3.0.0-dev29).**

Zum Anhören braucht es das nicht: Beim Üben legt XRack Mix und
Mitschnitt in denselben Wiedergabestrom, ohne etwas zu schreiben — und
das ist für „mal eben den letzten Versuch hören" der richtige Weg
(nichts zu warten, ein missratener Versuch ist einfach gelöscht).

Sitzt ein Versuch aber, will man ihn mitnehmen: auf den Stick, ins
Backup, auf ein anderes XRack. Dafür muss aus zweien eine Datei werden,
und das tut `uebungsmix_mit_take()` in `core/stem_combiner.py`. Heraus
kommt wieder ein Übungsmix (`_p`), der sich abspielen lässt wie jeder
andere.

Drei Dinge müssen dabei stimmen, sonst klingt die neue Datei anders als
das, was man beim Üben gehört hat — und jedes davon ist im Versuch
festgenagelt:

1. **Die Kanäle.** Jede Quelle behält die Kanäle, auf denen sie lag.
   Wo sie liegt, steht in ihrem Namen (`Umbrella-1_p` ab Kanal 1,
   `Umbrella-1-Take1_s9` ab Kanal 9) — dieselbe Quelle wie beim Üben,
   keine zweite Wahrheit daneben. Dazwischen bleibt es still.
2. **Der Versatz.** Der Mitschnitt hinkt dem Mix um die Laufzeit durch
   das Pult hinterher. Beim Üben wird er vorgezogen; hier geschieht
   dasselbe, mit demselben gemessenen Wert (`practice_offset_ms`).
   Sonst wäre die Datei um diese Millisekunden verschoben — und genau
   dafür wurde die Messung gebaut.
3. **Die Länge.** Sie richtet sich nach dem Mix. Eine Aufnahme, die
   nach dem Ende noch weiterlief, verlängert die Datei nicht; ein
   kürzerer Mitschnitt wird mit Stille aufgefüllt.

Gelesen wird mit XRacks eigenem `W64Reader`, nicht über ffmpeg: Beide
Quellen sind XRacks eigene Wave64-Dateien, und ffmpeg liest deren Kopf
nicht zuverlässig (es rät `pcm_s24le`, wo 32-Bit-Behälter mit 24
gültigen Bits stehen).

In der Oberfläche steht der Knopf neben der Auswahl des Mitschnitts —
dort, wo man ihn gerade angehört hat. Er geht nur mit gewähltem
Mitschnitt und nicht, während etwas läuft. Der Name wird
vorgeschlagen (`Umbrella-1 + Versuch 2`), denn genau daran erkennt man
die Datei später auf dem Stick wieder.

### Stufe 4 — Die Soundcheck-Karte wird wieder eine Sache

**Gebaut (3.0.0-dev7).**

- **Der Knopf heisst wieder „Soundcheck" und meint nur das.** Er hiess
  „Üben", wenn ein Übungsmix ausgewählt war, und spielte ihn über den
  Soundcheck-Spieler ab — der kann weder anhalten noch spulen noch
  wiederholen. Damit gab es den Weg zweimal, und der eine konnte
  weniger. `start_soundcheck()` lehnt Übungsmixe jetzt ab.
- **In „Alle Dateien" führt der Übungsmix zum Üben.** Derselbe Griff
  am selben Platz, nur ans richtige Ziel: Er schaltet die Karte auf
  Üben, wählt den Mix vor und schliesst den Dialog.
- **Die Sperrmatrix steht als Tabelle im Test**
  (`test_sperrmatrix.py`), 17 Kombinationen mit Begründung. Eine
  Tabelle ohne Begründung ist beim nächsten Umbau nur ein Hindernis,
  das man wegräumt — und genau diese eine Zeile darf nicht
  wegfallen:

  > **Üben + Aufnahme ist erlaubt.** Ein Aufnahmestrom neben einem
  > Wiedergabestrom, das kann das Interface. Wer hier
  > „sicherheitshalber" sperrt, nimmt das Mitschneiden wieder weg.

- **Neu dabei:** `practice_active` — läuft gerade eine Übung? Der
  Musikspieler allein sagt das nicht, er spielt auch Musik. Daran
  hängt, dass Musik eine laufende Übung nicht stillschweigend ablöst
  (samt Mitschnitt, der weiterliefe). Endet ein Stück von selbst,
  führt `uebung_nachfuehren()` den Zustand nach — sonst liesse sich
  danach nie wieder Musik starten.

- Der Wiedergabeknopf heißt wieder „Soundcheck" und meint nur das.
- Die Liste zeigt weiterhin nur Aufnahmen (tut sie schon).
- Die Sperren werden neu geschrieben: **Üben + Aufnahme ist
  ausdrücklich erlaubt** (ein Wiedergabe-, ein Aufnahmestrom), Üben ⊘
  Musik ⊘ Soundcheck bleiben.

## Entschieden (deine Antworten)

- Der Startkanal reist **mit der Datei** (im Dateinamen, wie die Art).
- „Übungsmix erstellen" wandert auf die Üben-Karte.
- Schleife: nur wenn billig — **ist sie**, siehe unten: ganzes Stück
  wiederholen kostet im Musikspieler fast nichts. A/B-Marken bleiben
  draußen.
- Mitgeschnitten wird **nur das eigene Instrument**, und es soll
  **zusammen mit dem Übungsmix** wiedergegeben werden.

## Der Mitschnitt zum Mitspielen

### Nachträglich Spuren in die vorhandene .w64 schreiben: nein

Nicht aus Bequemlichkeit, sondern weil das Format es nicht hergibt.
Eine W64 ist verschachtelt gespeichert: Rahmen für Rahmen stehen die
Kanäle nebeneinander (`[K1 K2 ... Kn][K1 K2 ... Kn]...`). Eine
zusätzliche Spur verbreitert **jeden einzelnen Rahmen** - die Datei
muss vollständig neu geschrieben werden, nicht angehängt.

Was das heißt: Eine Stunde Übungsmix mit acht Kanälen sind 5,5 GB.
Für zwei zusätzliche Spuren wären 5,5 GB zu lesen und 6,9 GB zu
schreiben, der Platz muss doppelt da sein, und auf einer SD-Karte
dauert das Minuten. Für „mal eben den letzten Versuch anhören" ist das
der falsche Weg.

### Stattdessen: beim Abspielen zusammenführen

Es geht nur **ein** Wiedergabestrom - aber nichts hindert XRack, in
diesen einen Strom **zwei Dateien** zu legen: den Übungsmix auf seine
Kanäle, den Mitschnitt auf seine. Genau das tut `ChannelInserter`
schon heute für eine Quelle; er braucht eine zweite.

Das ist der Antwort auf deine Frage am nächsten: Nichts wird neu
geschrieben, jeder Versuch lässt sich gegen den Mix anhören, und ein
missratener Versuch ist einfach gelöscht.

### Der Haken heißt Gleichlauf

Damit der Mitschnitt zum Mix passt, muss XRack wissen, **wann** er
begonnen hat. Der einfachste und ehrlichste Weg ist, das Problem gar
nicht erst entstehen zu lassen:

**Ein Knopf „Üben + mitschneiden"** startet beides zusammen, von vorn.
Dann ist der Versatz bauartbedingt null, und es muss nirgends etwas
gemerkt werden. Wer mitten im Stück aufnehmen will, spult vorher - der
Mitschnitt beginnt dann dort, und beim Abhören wird er an derselben
Stelle eingesetzt.

**Was bleibt, ist die Laufzeit durchs Pult:** XRack gibt aus, das Pult
schickt zurück, XRack nimmt auf - das sind einige Millisekunden Puffer
plus die Wandlung im Pult. Beim Zusammenhören liegt der Mitschnitt
also ein Stück hinter dem Mix. Wie viel, lässt sich messen (ein Klick
ausgeben, denselben Kanal aufnehmen, den Ausschlag suchen) - das wäre
eine eigene kleine Funktion und gehört nicht in diesen Umbau. Für den
Anfang: ein Versatz in Millisekunden, den man in der Üben-Karte
einstellen und merken kann.

### Und später doch eine Datei daraus

Wenn ein Versuch sitzt, soll er mitnehmbar sein: `combine_stems`
schreibt aus Mix + Mitschnitt einen neuen Übungsmix - dieselbe
geprüfte Funktion, die heute schon Stems zusammenlegt. Sie kennt
bisher nur Stereo-Quellen und müsste je Quelle eine eigene Kanalzahl
lernen. Das ist Stufe 5 und kann warten, bis das Zusammenhören steht.

## Was ich vorher von dir wissen muss

1. **Der Versatz durchs Pult:** Soll die Üben-Karte ein Feld dafür
   bekommen (in Millisekunden, gemerkt), oder fangen wir ohne an und
   sehen erst, ob es überhaupt stört? Ich wäre für „erst hören, dann
   bauen" - vielleicht ist es bei 1024 Rahmen Puffer unauffällig.
2. **Der Mitschnitt in der Liste:** Er ist eine Aufnahme wie jede
   andere (`_s`) und taucht damit in der Soundcheck-Karte auf. Soll
   er das, oder gehört er zur Üben-Karte? Ich neige zu: Er bleibt eine
   Aufnahme - eine dritte Art würde die Sache nur verkomplizieren, und
   über den Startkanal ist er ohnehin erkennbar.

## Was dabei schiefgehen kann

- **Zwei Wiedergabeströme.** Sobald Üben und Musik doch einmal
  gleichzeitig starten können, schlägt ALSA fehl. Die Sperren gehören
  deshalb in die Anwendungsschicht und in einen Test, nicht nur in
  die Oberfläche.
- **ffmpeg und die eigene W64.** Siehe Vorbehalt oben — erster
  Handgriff in Stufe 2, mit einer echten Datei vom Gerät.
- **Der Extraktor läuft je Rahmen durch Python.** Mit Versatz wird die
  Schleife nicht teurer, aber sie bleibt der heißeste Punkt im
  Lesethread. Vor und nach der Änderung messen.
- **Alte Aufnahmen.** Jede Änderung am Dateinamen muss rückwärts
  gelten: ohne Ziffer = Kanal 1. Dafür gibt es in
  `test_recording_kind.py` schon ein Gerüst.

## Verifikation je Stufe

- **Stufe 1:** Ein erzeugter Strom mit bekannten Werten je Kanal
  (das Muster steht in `test_extractor.py`) — geschnitten ab Kanal 9
  müssen genau die Kanäle 9..12 herauskommen. Dazu: Dateiname hin und
  zurück, alte Namen unverändert, und der Rundlauf
  Aufnahme → Soundcheck landet wieder auf demselben Kanal.
- **Stufe 2:** Ein mehrkanaliger Übungsmix wird geöffnet, die
  Kanalzahl stimmt, Pause und Spulen verhalten sich wie bei Musik
  (die Attrappen aus `test_music_player_pause.py` tragen das schon).
- **Stufe 3:** Die Karte im echten Browser (Muster:
  `test_recorder_ui.py`): Umschalten tauscht den Körper, ist während
  der Wiedergabe gesperrt, und der Zustand übersteht ein Neuladen.
- **Stufe 4:** Die Sperrmatrix als Tabelle im Test — jede erlaubte
  Kombination erlaubt, jede verbotene verboten. Besonders: Üben +
  Aufnahme muss **gehen**.

## Umfang

Stufe 1 ist ein Tag, Stufe 2 ein halber, Stufe 3 der größte Brocken
(Oberfläche, Texte, Zustand), Stufe 4 Aufräumen. Versionen: 2.11.0 bis
2.14.0, jede für sich auf `dev` und nach deinem Test auf `main`.
