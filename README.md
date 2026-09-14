# XRack

*[English](#english) | [Deutsch](#deutsch)*

Aufnehmen, üben, abspielen, Musik, Pult-Fernbedienung und Licht — für
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

- Raspberry Pi 5 or 4
- **Raspberry Pi OS based on Debian 13 ("Trixie")** — that is what XRack
  is built and tested on. The installer relies on the package versions
  of that release (NetworkManager, hostapd, avahi, OLA); older Debian
  releases are untested.
- a Behringer X-series console (tested: XAir XR18 and X32)
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

Running several XRacks? Settings → *Certificate (HTTPS)* saves the
certificate to an encrypted file and loads it onto the other units.
Together with the same shared name, all of them are one destination with
one certificate for the browser — so it asks once, not once per rack. The
file contains the private key: it is encrypted with a password of your
choosing, XRack only hands it out once a PIN is set, and it ships with no
certificate of its own. A certificate shipped with the software would put
its private key in everyone's hands.

To get rid of the question entirely, *Download certificate* in the same
place gives you the certificate on its own — public part only, no
password, nothing secret. Add that file to the device's certificate store
and it stops warning:

- **Android:** Settings → Security → Encryption & credentials → Install a
  certificate → CA certificate
- **iPhone/iPad:** open the file, install the profile, then switch it on
  under Settings → General → About → Certificate Trust Settings
- **Windows/macOS:** import it among the trusted root certificates
- **Firefox** keeps its own store: Settings → Certificates → Authorities
  → Import

Whether a device then accepts it without any warning is up to the device —
Apple in particular has its own rules about how long a TLS certificate may
be valid, and XRack issues its own for ten years. That part is untested
here, so try it and see rather than expecting a guarantee.

At the end the installer says whether lighting could be set up. If it
failed, the reason is right there — and it can be caught up on its own,
without the whole installer:

```bash
./install.sh --dmx
```

**Three ways to wire it up**, switchable in the settings:

1. XRack and console both on a router, over cable
2. XRack opens its own Wi-Fi network, console on a cable to the Pi
   (needs the USB Wi-Fi adapter)
3. XRack joins an existing Wi-Fi network, console on a cable to the Pi

### What XRack can do

#### Recording and playback

- **Two watchdogs for the recording** — XRack measures the sample rate
  that actually arrives and speaks up when it does not match the
  setting (otherwise the recording turns out too fast or too slow, and
  there is no way to notice: over USB the X-series always reports its
  whole range). And the free space stands in the card as remaining
  time: 32 channels at 48 kHz are about 22 GB an hour. When it gets
  tight the recording is **ended** in time instead of cut off — a
  closed file is readable, an interrupted one is not.
- **Virtual soundcheck** — record every channel straight off the desk,
  then play it back on exactly the same channels. The band can soundcheck
  without playing.
- **A recording window** — how many channels, and from which one on.
  Eight channels from channel 17 on an X32 are eight tracks, not
  twenty-four with sixteen empty ones. The starting channel travels
  with the file, in its name, so the virtual soundcheck puts the
  recording back where it came from; files without it start at channel
  1 as before.
- **Practice mix** — combine several stereo files (a click track, your own
  instrument, the rest of the band) into one multichannel recording. File
  one lands on channels 1+2, file two on 3+4, and so on. At the desk you
  then dial in exactly what you want to hear. The parts may come from
  your computer or already be sitting in XRack's music library.
- **Files in and out** — upload `.w64` files through the web interface,
  copy any recording onto a plugged-in USB stick with one button, and
  browse a stick in the interface to copy *from* it: single files or a
  whole folder with everything underneath — music into the library,
  recordings to the recordings. Whether the space is there, XRack says
  beforehand.

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

#### Practising

Practising has its own card since XRack 3.0 — and it shares the music
player's place, with a switch at the top between **Music** and
**Practice**. Not side by side: the console takes exactly one playback
stream, so two cards would offer something the hardware cannot do.

- **Play a practice mix** with everything the music player has and the
  soundcheck never did: pause, seek, a position slider, and *Repeat*
  for the passage that is not sitting yet.
- **Record along** — one switch, and starting the mix starts the
  recording with it. Which channels it records is the recording window
  from above (two channels from your own instrument's channel is the
  usual case), and because both begin in the same moment there is no
  drift to correct.
- **Hear your own take against the mix** — pick a take in the practice
  card and XRack lays both files into the same stream: the mix on its
  channels, the take on its own. Nothing is rewritten, every attempt
  can be heard against the mix, and a bad one is simply deleted.
- **The way through the console** costs a few milliseconds, so the take
  sits a little behind the mix. XRack measures that instead of guessing:
  a click goes out, the same channel comes back, and where the peak
  lands is the offset. On the test rig it was 10 to 19 ms. The measured
  value can be kept and is applied when listening back.
- **Make one file out of it** — when an attempt sits, mix and take are
  written into a new practice mix to take with you.

Recording while practising is expressly allowed — one playback stream,
one recording stream, which is exactly what the console can do.
Practice, music and soundcheck exclude each other, and XRack holds that
where it belongs rather than only in the interface.

#### Working the console

- **Channel strips** — the desk's own faders and mutes with their channel
  names, plus the master. Locked until you open the padlock, and they lock
  themselves again after a while (you set whether and after how long).
  While locked, not a single packet goes onto the network.
- **A/D or USB per channel** — the channel strips carry the input
  switch the desk has: the analogue input, or the channel coming back
  out of XRack over USB. That is the one the virtual soundcheck needs,
  and until now it meant reaching for the console. Linked channels
  switch as a pair, and the aux return (17+18) has it too. X-Air only —
  the X32 does this differently, and XRack does not guess at a command
  it has not seen a console answer.
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

- **Shared name for the web app** — saving the interface as an app on a
  tablet also saves the address it was running under. With more than one
  XRack the same icon leads nowhere in the next room, and an app has no
  address bar to change it in. So every unit can announce a shared name
  on top of its own: set `xrack` everywhere and one saved app finds
  whichever XRack is in the room. The unit's own name stays as it is.
  Two units with the same shared name must not be on the same network at
  once; XRack reports the clash in the settings.

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
- **Save and load the setup** — templates, fixtures, scenes and show
  settings as a file, for moving to a second XRack. Wi-Fi, PIN, device
  name and console address stay where they are; a faulty file is
  refused with a reason instead of wrecking the setup you have.
- **Music-driven light show** — XRack listens to the desk and makes
  light out of it. The source is either a channel pair or a **single
  channel**, and the single channel is the interesting one: on an AUX
  bus you can build a mix just for the light — bass drum and snare up
  front, the vocal out — and it costs one USB channel instead of two.
  The one you save is free for recording. Every channel the interface
  offers can be picked, including ones that are not being recorded:
  the show listens to the full stream, and how many channels go into
  the file is a separate question. Each fixture has a *kind*:

  | Kind | What it does |
  | --- | --- |
  | Effect light | every segment gets its own frequency band, derbys spin, lasers follow the music — on top of that one of two looks (below) |
  | Background light 1 and 2 | one colour at a time, changing every few beats and fading across; each group has its own colours and they run offset from each other |
  | Left out of the show | keeps whatever you set by hand or from a scene |

  Each of the three groups has its own set of three colours. When the
  music stops, XRack fades into a scene you choose (or to black); when it
  starts again the show comes straight back in.

  The effect light comes in two looks, switched in one place for the
  whole show:

  | Look | What it does |
  | --- | --- |
  | Moving point | one segment lights up fully and moves on with every bass hit, the others stay at a base level |
  | Pulse on the beat | all segments breathe together: on every beat they go to full and fall back until the next one. Each keeps its own colour, so you still see which band is doing what — and it works on a single RGB par, which the moving point cannot. How long a beat glows on and how bright it stays in between are both sliders |

  The background light is a wash in both cases.

  On top of that the **colour order can reverse**: every few beats it
  runs the other way across the segments — red-green-blue becomes
  blue-green-red and back. Brightness and movement stay as they are;
  only the mapping flips.

  On top of that the show can flash the strobe channels on
  particularly loud hits — usually the snare. It is off until you
  switch it on: nobody wants a strobe that starts by itself. How loud
  much gets through and how hard the flash lands are two sliders. The
  middle of the sensitivity is set so the strong hits flash; further
  up the running beat comes through too, further down only the
  biggest accents.

  One thing to keep in mind when switching to a single channel: the
  same signal comes in twice as loud as it would as one half of a pair
  whose neighbour is silent (6 dB). The bands do not care — they are
  measured against the running peak — but the silence threshold works
  on the absolute level, so it may need a nudge.

  Shutter, gobo and the white channel are never driven automatically —
  they stay yours, and what you set by hand stays put while the show
  runs. The same holds for the strobe channels as long as the flash is
  off.

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
  It also measures when the process itself stops answering, and notes
  whether the sound kept running through that stretch — which tells a
  blocked interpreter apart from a web server that hung on its own. No
  amount of thinking about it could; counting can.

### Trying it without hardware

There is an emulator for the mixer: `scripts/xair-emulator.py` answers
on port 10024 like an XR18 — faders, mutes, channel names, links,
snapshots. Started by hand, on the Pi or on any computer with Python:

```bash
python3 scripts/xair-emulator.py
```

Then enter `127.0.0.1` as the console address in the settings (or
press the magnifier in the channel-strip card — the broadcast reaches
a program on the same machine too). Everything you change in XRack
shows up in the emulator's terminal.

With `--audio` it also plays 18 channels of test signal into an ALSA
loopback, which XRack then records like an interface — kick, snare,
hi-hat, bass, guitar, voice, and the light mix on 17+18. The kernel
module has to be loaded once:

```bash
sudo modprobe snd-aloop
python3 scripts/xair-emulator.py --audio
```

The same program stands in for the console in the test suite, so it
cannot quietly drift away from what XRack expects. `--x32` makes it
answer as an X32 instead.

### The test suite

The tests live in `tests/` and run without hardware — no ALSA, no
console, no network. Each file is a standalone program that prints what
it checked:

```bash
python3 tests/alle.py            # all of them
python3 tests/alle.py wlan usb   # only files matching these words
python3 tests/test_extractor.py  # a single one
```

They need no pytest and no extra packages: on the Pi nothing is
installed beyond what XRack itself uses, and the suite has to run there
too. Checks that need a browser (the ones measuring the real layout)
skip themselves when none is present, and the runner says so rather
than reporting a false "ok".

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

- Raspberry Pi 5 oder 4
- **Raspberry Pi OS auf Debian-13-Basis ("Trixie")** — darauf ist XRack
  entwickelt und geprüft. Der Installer verlässt sich auf die
  Paketstände dieser Fassung (NetworkManager, hostapd, avahi, OLA);
  ältere Debian-Stände sind ungeprüft.
- ein Mischpult der X-Serie (getestet: XAir XR18 und X32)
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

Wer mehrere XRacks betreibt: Einstellungen → *Zertifikat (HTTPS)* sichert
das Zertifikat in eine verschlüsselte Datei und spielt es auf den anderen
Geräten ein. Zusammen mit demselben gemeinsamen Namen sind sie für den
Browser ein Ziel mit einem Zertifikat — er fragt einmal statt einmal je
Rack. In der Datei steckt der private Schlüssel: Sie ist mit einem selbst
gewählten Kennwort verschlüsselt, XRack gibt sie nur heraus, wenn eine
PIN vergeben ist, und ein eigenes Zertifikat liefert XRack bewusst nicht
mit. Ein mitgeliefertes läge mit seinem privaten Schlüssel in aller
Hände.

Damit die Frage ganz verschwindet, gibt *Zertifikat herunterladen* an
derselben Stelle das Zertifikat allein heraus — nur den öffentlichen
Teil, ohne Kennwort, ohne etwas Geheimes. Diese Datei legt man auf dem
Gerät in den Zertifikatsspeicher, und die Warnung bleibt weg:

- **Android:** Einstellungen → Sicherheit → Verschlüsselung &
  Anmeldedaten → Zertifikat installieren → CA-Zertifikat
- **iPhone/iPad:** Datei öffnen, Profil installieren, danach unter
  Einstellungen → Allgemein → Info →
  Zertifikatsvertrauenseinstellungen freigeben
- **Windows/macOS:** unter den vertrauenswürdigen Stammzertifikaten
  importieren
- **Firefox** bringt seinen eigenen Speicher mit: Einstellungen →
  Zertifikate → Zertifizierungsstellen → Importieren

Ob das Gerät danach wirklich ohne jede Warnung arbeitet, hängt am Gerät —
Apple stellt eigene Anforderungen an die Laufzeit von TLS-Zertifikaten,
und XRack stellt seine auf zehn Jahre aus. Das ist hier nicht geprüft:
ausprobieren, nicht darauf verlassen.

Am Ende sagt der Installer, ob die Lichtsteuerung eingerichtet werden
konnte. Ist sie ausgefallen, steht der Grund dabei — nachholen lässt
sie sich einzeln, ohne den ganzen Installer:

```bash
./install.sh --dmx
```

**Drei Betriebsarten**, umschaltbar in den Einstellungen:

1. XRack und Pult hängen per Kabel am selben Router
2. XRack spannt ein eigenes WLAN auf, das Pult hängt per Kabel am Pi
   (dafür wird der WLAN-Stick gebraucht)
3. XRack verbindet sich mit einem vorhandenen WLAN, das Pult hängt per
   Kabel am Pi

### Was XRack kann

#### Aufnehmen und abspielen

- **Zwei Wächter für die Aufnahme** — XRack misst die tatsächlich
  ankommende Samplerate und meldet sich, wenn sie nicht zur Einstellung
  passt (sonst wäre die Aufnahme hinterher zu schnell oder zu langsam;
  erkennen lässt sie sich nicht, die X-Serie meldet über USB immer den
  ganzen Bereich). Und der freie Platz steht als Restzeit in der Karte:
  32 Kanäle bei 48 kHz sind rund 22 GB je Stunde. Wird es knapp, wird
  die Aufnahme rechtzeitig **beendet** statt abgebrochen — eine
  geschlossene Datei ist lesbar, eine abgebrochene nicht.
- **Virtueller Soundcheck** — alle Kanäle direkt vom Pult aufnehmen und
  danach auf genau denselben Kanälen wieder abspielen. Die Band kann
  soundchecken, ohne zu spielen.
- **Ein Aufnahmefenster** — wie viele Kanäle, und ab welchem. Acht
  Kanäle ab Kanal 17 am X32 sind acht Spuren und nicht vierundzwanzig
  mit sechzehn leeren. Der Startkanal reist im Dateinamen mit, damit
  der virtuelle Soundcheck die Aufnahme dorthin zurücklegt, wo sie
  herkam; Dateien ohne ihn beginnen wie bisher bei Kanal 1.
- **Übungsmix** — mehrere Stereo-Dateien (Click, das eigene Instrument,
  der Rest der Band) zu einer Mehrkanal-Aufnahme zusammenfassen. Datei 1
  landet auf Kanal 1+2, Datei 2 auf 3+4 und so weiter. Am Pult stellt man
  sich damit ein, was man beim Üben hören will. Die Teile dürfen vom
  Rechner kommen oder schon in XRacks Musikbibliothek liegen.
- **Dateien hinein und hinaus** — `.w64`-Dateien über die Weboberfläche
  hochladen, jede Aufnahme mit einem Knopf auf einen angesteckten
  USB-Stick kopieren, und den Stick in der Oberfläche durchsehen, um
  *von* ihm zu kopieren: einzelne Dateien oder einen ganzen Ordner mit
  allem, was darunter liegt — Musik in die Bibliothek, Aufnahmen zu den
  Aufnahmen. Ob der Platz reicht, sagt XRack vorher.

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

#### Üben

Üben ist seit XRack 3.0 eine eigene Karte — und sie teilt sich den
Platz mit dem Musikspieler, oben ein Umschalter zwischen **Musik** und
**Üben**. Nicht nebeneinander: Das Pult nimmt genau einen
Wiedergabestrom, zwei Karten würden also etwas anbieten, was die
Hardware nicht kann.

- **Einen Übungsmix abspielen**, mit allem, was der Musikspieler kann
  und der Soundcheck nie konnte: anhalten, spulen, ein Positionsregler
  und *Wiederholen* für die Stelle, die noch nicht sitzt.
- **Mitschneiden** — ein Schalter, und mit dem Mix startet auch die
  Aufnahme. Welche Kanäle sie mitnimmt, ist das Aufnahmefenster von
  oben (zwei Kanäle ab dem Kanal des eigenen Instruments ist der
  Normalfall), und weil beides im selben Moment beginnt, gibt es keinen
  Versatz zu korrigieren.
- **Den eigenen Versuch gegen den Mix hören** — in der Üben-Karte einen
  Mitschnitt wählen, und XRack legt beide Dateien in denselben Strom:
  den Mix auf seine Kanäle, den Mitschnitt auf seine. Nichts wird neu
  geschrieben, jeder Versuch lässt sich gegen den Mix anhören, und ein
  missratener ist einfach gelöscht.
- **Der Weg durch das Pult** kostet einige Millisekunden, der
  Mitschnitt liegt also ein Stück hinter dem Mix. XRack misst das,
  statt zu raten: Ein Klick geht hinaus, derselbe Kanal kommt zurück,
  und wo der Ausschlag landet, ist der Versatz. Am Testgerät waren es
  10 bis 19 ms. Der gemessene Wert lässt sich merken und wird beim
  Zusammenhören angewandt.
- **Eine Datei daraus machen** — wenn ein Versuch sitzt, werden Mix und
  Mitschnitt zu einem neuen Übungsmix zum Mitnehmen geschrieben.

Aufnehmen während des Übens ist ausdrücklich erlaubt — ein
Wiedergabe-, ein Aufnahmestrom, genau das kann das Pult. Üben, Musik
und Soundcheck schließen einander aus, und XRack hält das dort fest, wo
es hingehört, nicht nur in der Oberfläche.

#### Das Pult bedienen

- **Kanalzüge** — die Fader und Stummschaltungen des Pults samt seiner
  Kanalbeschriftungen, dazu der Summenregler. Gesperrt, bis man das
  Schloss öffnet, und sie sperren sich von selbst wieder (ob überhaupt
  und nach wie vielen Sekunden, stellt man ein). Im gesperrten Zustand
  geht kein einziges Paket ins Netz.
- **A/D oder USB je Kanal** — die Kanalzüge tragen den
  Eingangsschalter, den das Pult auch hat: den analogen Eingang, oder
  den Kanal, der über USB aus XRack zurückkommt. Genau den braucht der
  virtuelle Soundcheck, und bisher musste man dafür ans Pult greifen.
  Verkoppelte Kanäle schalten als Paar, und der Aux-Rückweg (17+18) hat
  ihn auch. Nur an der X-Air-Serie — das X32 macht das anders, und
  XRack rät nicht bei einem Befehl, auf den es noch kein Pult hat
  antworten sehen.
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

- **Gemeinsamer Name für die Web-App** — wer die Oberfläche auf dem
  Tablet als App speichert, speichert damit auch die Adresse, unter der
  sie lief. Bei mehreren XRacks führt dasselbe Symbol im nächsten
  Proberaum ins Leere, und eine App hat keine Adresszeile, in der man
  das ändern könnte. Deshalb kann jedes Gerät zusätzlich zu seinem
  eigenen Namen einen gemeinsamen melden — trägt man überall `xrack`
  ein, findet dieselbe App in jedem Raum das XRack, das dort steht. Der
  eigene Name bleibt daneben bestehen. Zwei Geräte mit demselben
  gemeinsamen Namen dürfen nicht gleichzeitig im selben Netz stehen;
  XRack meldet den Konflikt in den Einstellungen.

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
- **Einrichtung sichern und einspielen** — Vorlagen, Lampen, Szenen und
  Show-Einstellungen als Datei, zum Übertragen auf ein zweites XRack.
  WLAN, PIN, Gerätename und Pult-Adresse bleiben, wo sie sind; eine
  fehlerhafte Datei wird begründet abgelehnt, statt die vorhandene
  Einrichtung zu zerlegen.
- **Musikgesteuerte Lichtshow** — XRack hört auf das Pult und macht
  daraus Licht. Als Quelle lässt sich ein Kanalpaar wählen oder ein
  **einzelner Kanal** — und der einzelne ist der spannende Fall: Auf
  einem AUX-Bus kann man einen eigenen Mix nur fürs Licht bauen,
  Bassdrum und Snare vorn, die Stimme heraus. Das kostet dann einen
  USB-Kanal statt zweier, und der gesparte steht für Aufnahmen bereit.
  Zur Wahl stehen dabei alle Kanäle, die das Interface liefert — auch
  solche, die gar nicht aufgenommen werden. Die Show hört am vollen
  Strom mit; wie viele Kanäle in die Datei gehen, ist eine andere
  Frage. Jede Lampe hat dabei eine *Art*:

  | Art | Was sie tut |
  | --- | --- |
  | Effektlicht | jedes Segment bekommt sein eigenes Frequenzband, Derbys drehen sich, Laser gehen mit der Musik an — dazu eines von zwei Bildern (siehe unten) |
  | Hintergrundlicht 1 und 2 | eine Farbe nach der anderen, alle paar Schläge gewechselt und weich übergeblendet; jede Gruppe hat eigene Farben, und die beiden laufen gegeneinander versetzt |
  | Von der Show ausgenommen | behält, was von Hand oder über eine Szene eingestellt ist |

  Jede der drei Gruppen hat ihren eigenen Satz von drei Farben. Hört die
  Musik auf, blendet XRack in eine gewählte Szene (oder ins Dunkle);
  fängt sie wieder an, setzt die Show sofort ein.

  Das Effektlicht kann zwei Bilder fahren, umgeschaltet an einer Stelle
  für die ganze Show:

  | Bild | Was es tut |
  | --- | --- |
  | Wandernder Punkt | ein Segment leuchtet voll und rückt bei jedem Bassschlag weiter, die übrigen bleiben auf Grundhelligkeit |
  | Puls im Takt | alle Segmente atmen gemeinsam: bei jedem Schlag gehen sie auf voll und fallen bis zum nächsten zurück. Jedes behält seine Farbe, man sieht also weiter, welches Band was macht — und es wirkt auch auf einem einzelnen RGB-Strahler, den der wandernde Punkt nicht erreicht. Nachleuchten und Grundhelligkeit lassen sich einstellen |

  Das Hintergrundlicht bleibt in beiden Fällen ein Wash.

  Dazu lässt sich die **Farbreihenfolge umkehren**: Alle paar Schläge
  läuft sie andersherum über die Segmente — aus Rot-Grün-Blau wird
  Blau-Grün-Rot und wieder zurück. Helligkeit und Bewegung bleiben,
  wie sie sind; es kippt allein die Zuordnung.

  Dazu kann die Show auf besonders laute Schläge — meist die Snare —
  die Strobe-Kanäle blitzen lassen. Das ist ausgeschaltet, bis du es
  einschaltest: Ein Blitzlicht, das von selbst angeht, will niemand.
  Wie viel durchkommt und wie kräftig der Blitz ausfällt, sind zwei
  Regler. Die Mitte der Empfindlichkeit ist so gelegt, dass die
  kräftigen Schläge blitzen; weiter oben kommt auch der laufende Takt
  durch, weiter unten nur noch die dicksten Einsätze.

  Eins gehört beim Umstellen auf einen einzelnen Kanal mitgedacht:
  Dasselbe Signal kommt dort doppelt so laut an wie als Hälfte eines
  Paares, dessen Nachbar still ist (6 dB). Den Bändern macht das
  nichts — sie messen sich an der laufenden Spitze —, die
  Stille-Schwelle arbeitet aber auf dem absoluten Pegel und will
  vielleicht nachgezogen werden.

  Shutter, Gobo und der Weiß-Kanal werden nie von selbst angesteuert —
  die gehören dir, und was du von Hand einstellst, bleibt auch während
  der Show stehen. Für die Strobe-Kanäle gilt dasselbe, solange der
  Blitz aus ist.

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
  Gemessen wird dabei auch, wann der Prozess selbst nicht mehr
  antwortet — und dazu vermerkt, ob in dieser Zeit Ton geflossen ist.
  Das unterscheidet einen blockierten Interpreter von einem Webserver,
  der für sich hängt. Durch Nachdenken war das nicht zu entscheiden,
  durch Zählen schon.

### Ohne Hardware ausprobieren

Für das Pult gibt es einen Emulator: `scripts/xair-emulator.py`
antwortet auf Port 10024 wie ein XR18 — Fader, Stummschaltungen,
Kanalnamen, Kopplungen, Snapshots. Von Hand gestartet, auf dem Pi oder
auf jedem Rechner mit Python:

```bash
python3 scripts/xair-emulator.py
```

Danach in den Einstellungen `127.0.0.1` als Pult-Adresse eintragen
(oder in der Kanalzug-Karte die Lupe drücken — der Rundruf erreicht
auch ein Programm auf demselben Rechner). Was man in XRack ändert,
steht im Terminal des Emulators.

Mit `--audio` spielt er zusätzlich 18 Kanäle Testsignal in ein
ALSA-Loopback, das XRack wie ein Interface aufnimmt: Bassdrum, Snare,
HiHat, Bass, Gitarre, Gesang — und auf 17+18 den Lichtmix, mit dem
sich die Lichtshow samt Blitz auf die Snare ohne Band prüfen lässt.
Das Kernelmodul muss einmalig geladen sein:

```bash
sudo modprobe snd-aloop
python3 scripts/xair-emulator.py --audio
```

Dasselbe Programm steht in der Testreihe an der Stelle des Pults — es
kann also nicht still von dem abweichen, was XRack erwartet. Mit
`--x32` antwortet es als X32.

### Die Testreihe

Die Tests liegen in `tests/` und laufen ohne Hardware — ohne ALSA, ohne
Pult, ohne Netz. Jede Datei ist ein eigenständiges Programm, das
ausgibt, was es geprüft hat:

```bash
python3 tests/alle.py            # alle
python3 tests/alle.py wlan usb   # nur, was zu diesen Wörtern passt
python3 tests/test_extractor.py  # eine einzelne
```

Kein pytest, keine zusätzlichen Pakete: Auf dem Pi ist nichts
installiert außer dem, was XRack selbst braucht, und dort soll die
Reihe auch laufen. Prüfungen, die einen Browser brauchen (die, die das
echte Layout messen), überspringen sich ohne einen — und der Läufer
schreibt das hin, statt ein falsches „ok" zu melden.

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
