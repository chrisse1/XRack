# Umbau: Üben als eigene Karte (Version 3.0)

Dieses Dokument gehoert zum Zweig `v3-ueben` und wird mit dem Umbau
fortgeschrieben. Es steht im Projekt und nicht in einem Chatverlauf,
weil der Umbau ueber mehrere Sitzungen laeuft: Wer hier weiterarbeitet
- ich beim naechsten Mal oder jemand anderes -, soll den Stand und vor
allem die BEGRUENDUNGEN vorfinden, nicht nur das Ergebnis.

**Stand:** Stufe 1 gebaut (3.0.0-dev1) - das Aufnahmefenster steht,
Stufen 2 bis 5 stehen aus.

**Versionen:** Auf diesem Zweig 3.0.0-dev1, -dev2 ... je Stufe. Wer
so eine Fassung auf dem Geraet hat, sieht am Namen, dass es eine
Vorschau ist. Beim Zusammenfuehren nach `main` wird daraus 3.0.0.

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

**Vorbehalt, der am Gerät geprüft werden muss:** Dass ffmpeg XRacks
selbst geschriebene W64-Dateien mehrkanalig liest. Für Stereo-Stems
tut es das (der Übungsmix entsteht ja aus ffmpeg-Material), für die
fertige Mehrkanaldatei ist es unbelegt. Das ist der erste Handgriff
in Stufe 2 — geht es nicht, bleibt der Soundcheck-Spieler die Quelle
und bekommt Pause und Spulen selbst.

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

### Stufe 3b — Mitschneiden und Zusammenhören

- Knopf **„Üben + mitschneiden"**: startet Übungsmix und Aufnahme in
  einem Zug (Aufnahmefenster aus Stufe 1 - beim Üben typisch zwei
  Kanäle ab dem Kanal des eigenen Instruments).
- In der Üben-Karte ein zweites Auswahlfeld: **Mitschnitt**. Ist einer
  gewählt, legt der Spieler beide Dateien in denselben Strom
  (`ChannelInserter` mit zwei Quellen).
- Wiederholen: ein Schalter „ganzes Stück wiederholen". Im
  Musikspieler ist das die vorhandene Schleife über die Titelliste,
  angewandt auf einen Titel - deshalb billig.

### Stufe 5 (später) — Aus Versuch und Mix eine Datei

`combine_stems` lernt Quellen mit eigener Kanalzahl und schreibt aus
Übungsmix + Mitschnitt einen neuen Übungsmix zum Mitnehmen.

### Stufe 4 — Die Soundcheck-Karte wird wieder eine Sache

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
