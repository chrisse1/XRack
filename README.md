# XRack

*[English](#english) | [Deutsch](#deutsch)*

Aufnehmen, abspielen, Musik, Pult-Fernbedienung und Licht — für
Behringer-Mischpulte der X-Serie, auf einem Raspberry Pi, bedient über
den Browser.

### Demo

https://github.com/user-attachments/assets/2ce5bc1c-d05e-409c-8a5c-fde638b21ed6

<a id="english"></a>

## English

XRack turns a Raspberry Pi into a recorder, player and lighting desk for
**Behringer X-series mixing consoles** (XAir, X32 and compatible). Plug
the console in over USB, open the web interface from any phone, tablet or
laptop, and you have every channel of the desk to record and play back —
no screen or keyboard on the Pi.

It is built for the stage: everything is reachable in one or two taps,
nothing needs a terminal, and features that are not set up simply do not
appear.

### What you need

- Raspberry Pi 5
- a Behringer X-series console (tested: XAir XR18)
- the USB cable between the two
- *optional:* a MediaTek MT7612U USB Wi-Fi adapter, if XRack should open
  its own Wi-Fi network
- *optional:* a USB-to-DMX cable with an FTDI chip, for the lighting
  features

### Installation

```bash
git clone https://github.com/chrisse1/XRack.git
cd XRack
./install.sh
```

The installer is meant for a freshly set up Raspberry Pi. It installs
everything needed and sets up a service that starts XRack on boot. It
asks for the interface language, the port, the hostname and a four-digit
PIN that protects the settings, and it optionally sets up Wi-Fi and
Bluetooth — the questions explain themselves as you go.

Afterwards the web interface is at `https://<hostname>.local:<port>`,
by default `https://xrack.local:8080`. The certificate is self-signed, so
the browser shows a warning once ("Advanced" → "Proceed"); it remembers
the exception afterwards.

**Three ways to wire it up**, switchable in the settings:

1. XRack and console both on a router, over cable
2. XRack opens its own Wi-Fi network, console on a cable to the Pi
   (needs the USB Wi-Fi adapter)
3. XRack joins an existing Wi-Fi network, console on a cable to the Pi

### What XRack can do

#### Recording and playback

- **Virtual soundcheck** — record every channel straight off the desk,
  then play it back on exactly the same channels. The band can soundcheck
  without playing.
- **Practice mix** — combine several stereo files (a click track, your own
  instrument, the rest of the band) into one multichannel recording. File
  one lands on channels 1+2, file two on 3+4, and so on. At the desk you
  then dial in exactly what you want to hear.
- **Upload and copy** — add `.w64` files through the web interface, and
  copy any recording to a plugged-in USB stick with one button.

Recordings are Wave64 (`.w64`), which does not have the 4 GB limit of
plain WAV — with 18 channels that is reached after about 26 minutes.

#### Music and breaks

- **Music player** — shuffle a whole folder on a loop for break music, or
  play a single track, on any stereo pair you choose. Shows title and
  artist where the file carries them.
- **Bluetooth audio** — pair a phone from the dashboard and put its audio
  on a channel pair. Off after every restart, on purpose: Bluetooth is
  only so-so for live use.

Both cards have their own level control and mute for the pair they use,
so you do not have to scroll to the channel strips.

#### Working the console

- **Channel strips** — the desk's own faders and mutes with their channel
  names, plus the master. Locked until you open the padlock, and they lock
  themselves again after a while (you set whether and after how long).
  While locked, not a single packet goes onto the network.
- **Snapshots** — recall the snapshots (X32: scenes) stored in the
  console. This is the most far-reaching command XRack sends, so it sits
  behind the same lock and asks first.
- **Reach the console from your home network** — one switch, and the
  console hanging off the Pi is reachable from your network through
  XRack's own address. X32-Edit, X-AIR-Edit and Mixing Station work
  without replugging anything; the address to type in is right under the
  switch.

XRack finds the console by itself. If a router blocks the discovery
broadcast, enter the IP in the settings; the magnifier button in the
channel strip card searches again.

#### Lighting

Everything below is behind one switch under *Settings → Lighting* —
without DMX you never see it.

- **Fixtures** — a *template* describes what each channel of a fixture
  does (red, green, blue, dimmer, pan, tilt, gobo, strobe …). A *fixture*
  is then just template + start address + name. Templates ship for a plain
  dimmer, RGB, RGB+dimmer, RGBW, an 8-segment LED bar and three Eurolite
  sets (KLS-180, KLS-180/6 in two modes, KLS Laser Bar PRO FX). Anything
  else you enter channel by channel from its manual — a guessed preset
  would be worse than none.
- **Scenes** — save what is currently lit and recall it with one button.
  Scenes are stored relative to the fixture, so moving a fixture to a
  different start address does not invalidate them.
- **Music-driven light show** — XRack listens to a channel pair from the
  desk and makes light out of it. Each fixture has a *kind*:

  | Kind | What it does |
  | --- | --- |
  | Effect light | every segment gets its own frequency band, a bright spot moves on each bass hit, derbys spin, lasers follow the music |
  | Background light 1 and 2 | one colour at a time, changing every few beats and fading across; each group has its own colours and they run offset from each other |
  | Left out of the show | keeps whatever you set by hand or from a scene |

  Each of the three groups has its own set of three colours. When the
  music stops, XRack fades into a scene you choose (or to black); when it
  starts again the show comes straight back in.

  Strobe, shutter, gobo and the white channel are never driven
  automatically — they stay yours, and what you set by hand stays put
  while the show runs.

After installing, the DMX output has to be assigned once — under
*Settings → Lighting*, pick the port your cable is on and press
*Assign*. Until then the fixtures stay dark even though service and
cable are fine; XRack says so in the lighting card. The assignment
survives restarts.

#### Looking after it

- **Update** — one button fetches the current version from GitHub, the
  other takes a release ZIP off a USB stick (the way that works without
  internet). Recordings, music and all settings survive, and if the
  interface does not come back, XRack restores the previous version by
  itself. A ZIP older than what is installed is refused.
- **Network self-test** — one button under *Maintenance* that checks radio
  hardware, access point, home network and console in one go and says what
  does not fit together. The output can be copied and passed on; the Wi-Fi
  password is not in it.
- **Diagnostic recording** — a switch that logs in the background how XRack
  and the network are doing, for faults that only show up now and then. It
  survives a restart and the log downloads straight from the settings.

### When something is stuck

If the web interface does not come up, the update also runs from a
terminal — the same path the button takes:

```bash
sudo ~/XRack/scripts/xrack-update.py ~/XRack pi 8080 \
     --repository chrisse1/XRack --branch main
```

The port has to be the one actually configured (`config/local.yaml`),
otherwise the updater thinks the restart failed and rolls back.

```bash
sudo systemctl status xrack          # is XRack running?
journalctl -u xrack -f               # follow the log
sudo systemctl status xrack-hostapd  # is the access point up?
iw dev                               # which adapter is doing what?
```

### Background

Why some things are built the way they are — access point, console
discovery, updates, DMX — is written down separately in
[docs/hintergrund.md](docs/hintergrund.md) (German).

### License

XRack is licensed under the
[GNU General Public License v3.0](LICENSE).

<a id="deutsch"></a>

## Deutsch

XRack macht aus einem Raspberry Pi einen Recorder, Zuspieler und ein
Lichtpult für **Behringer-Mischpulte der X-Serie** (XAir, X32 und
kompatible). Pult per USB anschließen, Weboberfläche am Handy, Tablet
oder Rechner öffnen — und alle Kanäle des Pults stehen zum Aufnehmen und
Abspielen bereit. Bildschirm oder Tastatur am Pi braucht es nicht.

Gebaut ist es für die Bühne: Alles ist mit ein, zwei Griffen erreichbar,
nichts verlangt eine Kommandozeile, und was nicht eingerichtet ist,
taucht auch nicht auf.

### Was man braucht

- Raspberry Pi 5
- ein Mischpult der X-Serie (getestet: XAir XR18)
- das USB-Kabel dazwischen
- *optional:* ein MediaTek-MT7612U-WLAN-Stick, wenn XRack ein eigenes
  WLAN aufspannen soll
- *optional:* ein USB-DMX-Kabel mit FTDI-Chip, für das Licht

### Installation

```bash
git clone https://github.com/chrisse1/XRack.git
cd XRack
./install.sh
```

Der Installer ist für einen frisch aufgesetzten Raspberry Pi gedacht. Er
installiert alles Nötige und richtet einen Dienst ein, der XRack beim
Einschalten startet. Gefragt werden Sprache, Port, Hostname und eine
vierstellige PIN, die die Einstellungen schützt; WLAN und Bluetooth
richtet er auf Wunsch gleich mit ein — die Abfragen erklären sich beim
Durchlaufen von selbst.

Danach ist die Weboberfläche unter `https://<hostname>.local:<port>`
erreichbar, standardmäßig `https://xrack.local:8080`. Das Zertifikat ist
selbstsigniert, der Browser zeigt deshalb einmalig eine Warnung
("Erweitert" → "Trotzdem fortfahren") und merkt sich die Ausnahme.

**Drei Betriebsarten**, umschaltbar in den Einstellungen:

1. XRack und Pult hängen per Kabel am selben Router
2. XRack spannt ein eigenes WLAN auf, das Pult hängt per Kabel am Pi
   (dafür wird der WLAN-Stick gebraucht)
3. XRack verbindet sich mit einem vorhandenen WLAN, das Pult hängt per
   Kabel am Pi

### Was XRack kann

#### Aufnehmen und abspielen

- **Virtueller Soundcheck** — alle Kanäle direkt vom Pult aufnehmen und
  danach auf genau denselben Kanälen wieder abspielen. Die Band kann
  soundchecken, ohne zu spielen.
- **Übungsmix** — mehrere Stereo-Dateien (Click, das eigene Instrument,
  der Rest der Band) zu einer Mehrkanal-Aufnahme zusammenfassen. Datei 1
  landet auf Kanal 1+2, Datei 2 auf 3+4 und so weiter. Am Pult stellt man
  sich damit ein, was man beim Üben hören will.
- **Hochladen und kopieren** — `.w64`-Dateien über die Weboberfläche in
  die Liste laden, und jede Aufnahme mit einem Knopf auf einen
  angesteckten USB-Stick kopieren.

Aufnahmen liegen als Wave64 (`.w64`). Dieses Format hat die 4-GB-Grenze
von gewöhnlichem WAV nicht — die wäre bei 18 Kanälen nach rund 26
Minuten erreicht.

#### Musik und Pausen

- **Musikplayer** — einen ganzen Ordner zufällig in Dauerschleife
  abspielen (Pausenmusik) oder einen einzelnen Titel, auf einem frei
  wählbaren Kanalpaar. Titel und Interpret zeigt er, wenn die Datei sie
  mitbringt.
- **Bluetooth-Audio** — Handy oder Tablet direkt vom Dashboard aus
  koppeln und dessen Ton auf ein Kanalpaar legen. Nach jedem Neustart
  aus, mit Absicht: Bluetooth ist für den Live-Einsatz nur bedingt
  geeignet.

Beide Karten haben einen eigenen Regler samt Stummschaltung für ihr
Kanalpaar — fürs Lautermachen muss man also nicht zu den Kanalzügen
scrollen.

#### Das Pult bedienen

- **Kanalzüge** — die Fader und Stummschaltungen des Pults samt seiner
  Kanalbeschriftungen, dazu der Summenregler. Gesperrt, bis man das
  Schloss öffnet, und sie sperren sich von selbst wieder (ob überhaupt
  und nach wie vielen Sekunden, stellt man ein). Im gesperrten Zustand
  geht kein einziges Paket ins Netz.
- **Snapshots** — die im Pult gespeicherten Snapshots (beim X32: Szenen)
  aufrufen. Das ist der eingreifendste Befehl, den XRack ans Pult
  schickt: Er hängt an derselben Sperre und fragt vorher nach.
- **Konsole aus dem Heimnetz erreichbar machen** — ein Schalter, und das
  am Pi hängende Pult ist aus dem Heimnetz über XRacks Adresse
  ansprechbar. X32-Edit, X-AIR-Edit oder Mixing Station funktionieren
  damit, ohne etwas umzustecken; die Adresse für die App steht direkt
  unter dem Schalter.

Das Pult findet XRack selbst. Lässt ein Router die Suche nicht durch,
trägt man die IP in den Einstellungen ein; der Lupen-Knopf in der
Kanalzug-Karte sucht erneut.

#### Licht

Alles Folgende steckt hinter einem Schalter unter *Einstellungen →
Licht* — wer kein DMX hat, sieht es gar nicht erst.

- **Lampen einrichten** — eine *Gerätevorlage* beschreibt, welcher Kanal
  einer Lampe was macht (Rot, Grün, Blau, Dimmer, Pan, Tilt, Gobo,
  Strobe …). Eine *Lampe* ist dann nur noch Vorlage + Startadresse +
  Name. Mitgeliefert sind Vorlagen für Dimmer, RGB, RGB+Dimmer, RGBW,
  eine 8-Segment-LED-Bar und drei Eurolite-Sets (KLS-180, KLS-180/6 in
  zwei Modi, KLS Laser Bar PRO FX). Alles andere trägt man Kanal für
  Kanal aus dem Handbuch ein — ein geratenes Preset wäre schlimmer als
  keins.
- **Szenen** — den aktuellen Stand speichern und per Knopfdruck wieder
  aufrufen. Szenen liegen relativ zur Lampe: Wer eine Lampe später auf
  eine andere Startadresse zieht, muss seine Szenen nicht neu bauen.
- **Musikgesteuerte Lichtshow** — XRack hört auf ein Kanalpaar vom Pult
  und macht daraus Licht. Jede Lampe hat dabei eine *Art*:

  | Art | Was sie tut |
  | --- | --- |
  | Effektlicht | jedes Segment bekommt sein eigenes Frequenzband, auf jedem Bassschlag wandert ein heller Punkt weiter, Derbys drehen sich, Laser gehen mit der Musik an |
  | Hintergrundlicht 1 und 2 | eine Farbe nach der anderen, alle paar Schläge gewechselt und weich übergeblendet; jede Gruppe hat eigene Farben, und die beiden laufen gegeneinander versetzt |
  | Von der Show ausgenommen | behält, was von Hand oder über eine Szene eingestellt ist |

  Jede der drei Gruppen hat ihren eigenen Satz von drei Farben. Hört die
  Musik auf, blendet XRack in eine gewählte Szene (oder ins Dunkle);
  fängt sie wieder an, setzt die Show sofort ein.

  Strobe, Shutter, Gobo und der Weiß-Kanal werden nie von selbst
  angesteuert — die gehören dir, und was du von Hand einstellst, bleibt
  auch während der Show stehen.

Nach der Installation muss der DMX-Ausgang einmal zugeordnet werden:
in den *Einstellungen* unter *Licht* den Anschluss auswählen, an dem
das Kabel hängt, und auf *Zuordnen* drücken. Bis dahin bleiben die
Lampen dunkel, obwohl Dienst und Kabel in Ordnung sind — die
Lichtkarte sagt das auch. Die Zuordnung übersteht Neustarts.

#### Pflege

- **Update** — der eine Knopf holt den aktuellen Stand von GitHub, der
  andere spielt eine Release-ZIP vom angesteckten USB-Stick ein (der Weg,
  der ohne Internet funktioniert). Aufnahmen, Musik und alle
  Einstellungen bleiben erhalten, und falls die Weboberfläche danach
  nicht zurückkommt, stellt XRack den vorherigen Stand selbst wieder
  her. Eine ZIP mit einer älteren Version als der installierten wird
  abgelehnt.
- **Netzwerk-Selbsttest** — ein Knopf unter *Wartung*, der Funkgeräte,
  Access Point, Heimnetz und Mischpult in einem Durchgang prüft und
  benennt, was nicht zusammenpasst. Die Ausgabe lässt sich kopieren und
  weitergeben; das WLAN-Passwort steht nicht darin.
- **Diagnose-Aufzeichnung** — ein Schalter, der im Hintergrund
  mitschreibt, wie es XRack und dem Netzwerk geht. Gedacht für Fehler,
  die nur sporadisch auftreten: Der Schalter übersteht einen Neustart,
  und die Aufzeichnung lädt man direkt aus den Einstellungen herunter.

### Wenn etwas klemmt

Kommt die Weboberfläche nicht hoch, lässt sich das Update auch von der
Kommandozeile einspielen — derselbe Weg, den der Knopf nimmt:

```bash
sudo ~/XRack/scripts/xrack-update.py ~/XRack pi 8080 \
     --repository chrisse1/XRack --branch main
```

Der Port muss der tatsächlich eingestellte sein (`config/local.yaml`),
sonst hält der Updater den Neustart für gescheitert und rollt zurück.

```bash
sudo systemctl status xrack          # läuft XRack?
journalctl -u xrack -f               # Live mitlesen
sudo systemctl status xrack-hostapd  # läuft der Access Point?
iw dev                               # welches Funkgerät macht was?
```

### Hintergrund

Warum einiges so gebaut ist, wie es gebaut ist — Access Point,
Pultsuche, Update, DMX —, steht getrennt in
[docs/hintergrund.md](docs/hintergrund.md).

### Lizenz

XRack steht unter der
[GNU General Public License v3.0](LICENSE).
