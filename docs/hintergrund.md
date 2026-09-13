# Hintergrund

Warum XRack an einigen Stellen so gebaut ist, wie es gebaut ist.

Dieses Dokument richtet sich an den, der an XRack weiterbaut oder einen
Fehler sucht. Zum Benutzen braucht man es nicht — dafür ist die
[README](../README.md) da.

---

## Netzwerk und Access Point

### Warum hostapd und nicht NetworkManagers Hotspot

Der Access Point läuft über **hostapd** (`xrack-hostapd.service`) auf dem
zweiten WLAN-Interface, nicht über den eingebauten Hotspot von
NetworkManager.

Dessen AP-Betriebsart stammt aus `wpa_supplicant`, das eigentlich zum
Verbinden mit fremden Netzen gebaut ist, und verliert Anmeldeversuche
gelegentlich in einem Wettlauf (`handle_assoc_cb: STA ... not found`). Für
den Nutzer sieht das aus, als sei das Passwort falsch — mal klappt es
sofort, mal erst beim zehnten Versuch. Genau diese Sorte Fehler kann man
auf einer Bühne nicht gebrauchen.

### Der Aufbau

| Teil | Aufgabe |
| --- | --- |
| `hostapd` (`xrack-hostapd.service`) | Funk und Verschlüsselung, WPA2 mit AES, 5 GHz sofern erlaubt |
| Bridge `br0` | Layer 2 — der Access Point immer, das Mischpult an eth0 zuschaltbar |
| NetworkManager | IP, DHCP und Internet-Weitergabe auf `br0` (10.42.0.1), Heimnetz-Client, Kabelverbindung |

Der Access Point hängt **dauerhaft** in der Bridge. Der Schalter „Konsole
über XRacks Access Point erreichbar machen" hängt deshalb nur noch eth0 mit
ein oder aus und rührt den Funkbetrieb nicht an. Vorher wurde dafür der
Access Point selbst umgebaut und neu gestartet, was beim Umschalten jedes
Mal einen Neustart nötig machte.

SSID und Passwort landen in `/etc/hostapd/xrack.conf` — nur für root
lesbar, denn dort steht das Passwort im Klartext. Kommt der Access Point
mit neuen Werten nicht hoch, stellt XRack die alten wieder her, statt einen
stummen Access Point zu hinterlassen. Aus demselben Grund filtert der
Netzwerk-Selbsttest diese Datei, statt sie durchzureichen.

### Welches Funkgerät wofür

`wlan0` und `wlan1` werden in der Reihenfolge vergeben, in der die Geräte
auftauchen — nicht fest je Gerät. Beim Booten kann der Stick deshalb
`wlan0` werden und das eingebaute WLAN `wlan1`. XRack gleicht die Namen vor
jedem Start des Access Points wieder mit den Rollen ab
(`scripts/xrack-wifi-bind.sh`); der NetworkManager-Eintrag für das
unverwaltete Gerät steht dafür auf der MAC-Adresse statt auf dem Namen.

Gefragt wird die Zuordnung nicht: Das eingebaute WLAN geht ins Heimnetz,
der USB-Stick spannt den Access Point auf. Der eingebaute Chip taugt als
Client, aber nur schlecht als Access Point — er bricht unter Last ein und
kann kein 5 GHz.

Vorhandene WLAN-Profile (etwa das vom Raspberry Pi Imager angelegte
`preconfigured`) werden stillgelegt, damit sie XRacks Profil nicht das
Funkgerät streitig machen. Gelöscht wird nichts.

### Kein Stick, kein Startversuch

Ein eingerichteter Access Point und ein nicht eingesteckter USB-Stick sind
kein Widerspruch: Der Stick wird nur in manchen Szenarien gebraucht, die
Einrichtung soll dafür nicht jedes Mal fallen. Bis Version 3 hatte diese
Lage aber Folgen, die niemand vermutet hätte. `xrack-hostapd.service` läuft
mit `Restart=always`, hostapd fand kein Gerät, und so stand im Journal
eines Geräts:

```
xrack-hostapd.service: Scheduled restart job, restart counter is at 14453.
nmcli connection up XRack-Bridge          (ExecStartPre)
hostapd: Main process exited, code=exited, status=1/FAILURE
```

14.469 Fehlstarts in einundzwanzig Stunden — und weil jeder Versuch über
`ExecStartPre` die NetworkManager-Brücke neu aktivierte, alle fünf Sekunden
ein Eingriff ins Netz, rund um die Uhr. Daneben im Protokoll: die
Netzaussetzer, hinter denen wir tagelang her waren.

Seither fragt die Unit erst, ob es überhaupt etwas aufzuspannen gibt
(`ExecCondition=scripts/xrack-ap-bereit.sh`, entscheidet an derselben Quelle
wie alles andere: `xrack-wifi-iface.sh`). Eine gescheiterte Bedingung lässt
systemd den Dienst **überspringen** — kein Fehlschlag, und vor allem läuft
keine der Zeilen darunter.

Damit endet auch der Fünfsekundentakt, denn einen übersprungenen Start
wiederholt systemd nicht, auch bei `Restart=always` nicht. Genau das war
aber die einzige Stelle, an der ein später eingesteckter Stick bisher
bemerkt wurde — der nächste Versuch fand ihn ja. Diese Fähigkeit hätte die
Bedingung stillschweigend mitgenommen; sie liegt deshalb jetzt bei einer
udev-Regel (`/etc/udev/rules.d/99-xrack-ap.rules`), die den Dienst bei jedem
auftauchenden Funkgerät anstößt. Ob es das richtige ist, entscheidet dann
wieder die Bedingung.

Die Aufzeichnung (`core/diagnostics.py`) wacht seither über die
Nebendienste — sie hätte das Hämmern von innen gemeldet. `exec-condition`
zählt dort ausdrücklich als unauffällig: Der übersprungene Dienst ist der
gewollte Zustand, und eine Warnung, die im Normalfall angeht, liest bald
niemand mehr.

### Name und Zertifikat

XRack installiert `avahi-daemon` mit, damit `<hostname>.local` im Netz
auflösbar ist, und schickt den Hostnamen im DHCP-Antrag mit, damit auch der
Router ihn lernt (bei einer FRITZ!Box etwa als `xrack` bzw.
`xrack.fritz.box`). Ob ein `.local`-Name ankommt, hängt am **anfragenden**
Gerät: Windows und iOS können mDNS, ältere Android-Versionen nicht. Die IP
funktioniert immer.

Das TLS-Zertifikat ist selbstsigniert. Ein vom Browser automatisch
akzeptiertes Zertifikat ist für ein Gerät, das oft komplett offline über
den eigenen Access Point läuft, nicht zu bekommen — es gibt keinen Weg, es
ausstellen zu lassen.

---

## Das Mischpult finden

XRack sucht die Konsole in dieser Reihenfolge: von Hand eingetragene IP,
dann die eigene DHCP-Vergabeliste (wenn das Pult am Pi hängt), dann per
OSC-Rundruf im Netz — so wie X32-Edit und X-AIR-Edit ihre Pulte auch
finden. Damit ist der Fall abgedeckt, dass Pult und Pi zusammen an einem
Router hängen. Lässt ein Router den Rundruf nicht durch, hilft nur die IP
von Hand.

**Warum der Lupen-Knopf die Netzwerkbuchse kurz trennt:** Das Pult fragt
erst dann wieder per DHCP nach einer Adresse, wenn die Verbindung
tatsächlich weg war. Wird es nachträglich eingesteckt oder neu gestartet,
während XRack schon läuft, behält es seine alte — unter Umständen aus einem
ganz anderen Netz.

Getrennt wird nur, wenn eine der beiden Kabel-Betriebsarten läuft. Hängen
Pult und Pi zusammen an einem Router, ist die Netzwerkbuchse die Leitung
dorthin — XRack würde sich sonst beim Suchen die eigene Verbindung
abschneiden.

**Snapshot-Namen:** Die Adressen zum Laden sind belegt (X-Air
`/-snap/load`, X32 `/-action/goscene`). Für die *Namen* der einzelnen
Plätze gab es keine Quelle; dort ist der übliche Aufbau eingebaut, der sich
am XR18 im Betrieb bestätigt hat — für den X32 ist er ungeprüft. Antwortet
ein Pult nicht darauf, zeigt die Auswahl statt Namen einfach die Nummern.
Die Liste wird nicht laufend abgefragt (das kostet je nach Pult bis zu
hundert Abfragen), sondern beim Laden der Seite, beim Entsperren der Karte
und nach einem geladenen Snapshot.

### Der Eingang eines Kanals: A/D oder USB

Die Pultsteuerung macht bewusst nur Lautstärke — kein EQ, keine Sends,
kein Routing. Eine Ausnahme gibt es: den Schalter, der einem Kanal statt
seines Vorverstärkers den USB-Rückweg auflegt
(`/ch/NN/preamp/rtnsw`, 1 = USB).

Er gehört dazu, weil der virtuelle Soundcheck ohne ihn halb ist: XRack
spielt die Aufnahme ins Pult, aber die Kanäle hören weiter ihre
Mikrofone. Genau dieser Handgriff war der letzte, für den man noch nach
X-AIR-Edit wechseln musste.

**Die Adresse ist nicht geraten und nicht nur nachgelesen.** Sie stammt
aus einer Bibliothek (`onyx-and-iris/xair-api-python`, `shared.py`:
`usbinput` → `rtnsw`) — und eine Bibliothek ist keine Hardware. Deshalb
gibt es `scripts/xrack-pult-fragen.py`: Es fragt das Pult selbst, nur
lesend (jede OSC-Anfrage ohne Argumente liefert den aktuellen Wert
zurück), und darf mitten in einer Probe laufen. An einem XR18 kam
zurück:

| Adresse | Antwort | |
|---|---|---|
| `/ch/01/mix/fader` | `0.373` | Gegenkontrolle: das Pult antwortet |
| `/ch/01/config/name` | `'Drums'` | Gegenkontrolle: auch auf Text |
| `/ch/01/preamp/rtnsw` | `1` | der Schalter, **je Kanal** |
| `/ch/03/preamp/rtnsw` | `1` | |
| `/ch/01/preamp/rtntrim` | `0.5` | linear 0…1, also 0 dB |
| `/rtn/aux/preamp/rtnsw` | `1` | der Aux-Rückweg hat ihn **auch** |
| `/ch/01/config/source` | — | Gegenkontrolle: nicht alles wird beantwortet |

Zwei Gegenkontrollen gehören zu so einer Messung, sonst beweist sie
nichts: oben Adressen, die XRack schon benutzt (antworten die nicht, ist
das Pult unerreichbar, und jedes „keine Antwort" darunter sagt nichts),
unten eine, die es nicht geben sollte (antwortet sie doch, antwortet das
Pult auf alles).

Der Aux-Rückweg war vorher als „ungeprüft" ausgeschlossen. Die Nachfrage
hat es geklärt, und es ist plausibel: Genau dieser Kanalzug nimmt
entweder die Cinch-Buchsen oder USB. Die Summe bleibt draußen — ob sie
antwortet, ist ungefragt, aber einen Eingang zum Umlegen hat sie nicht.

Drei Dinge, die dabei entschieden sind:

**Nur die X-Air-Serie.** Dort ist es ein Umschalter mit zwei Stellungen.
Der X32 wählt stattdessen je Kanal eine *Quelle* aus einer Liste (Local,
AES50, Card) — für die Adresse dazu gibt es keine belegte Quelle, nur
Erinnerung. Deshalb zeigt die Karte den Schalter dort nicht: Ein
geratener Schalter, der beim Umlegen die falsche Quelle setzt, wäre
schlimmer als keiner.

**Ein gekoppeltes Paar wird auf beiden Kanälen umgelegt.** Beim Fader
genügt der erste Kanal, den zweiten zieht das Pult mit. Ob die Kopplung
auch den Vorverstärker umfasst, ist ungeprüft — und ein halb umgelegtes
Paar wäre der unangenehmste Fall: eine Seite hört die Aufnahme, die
andere den Raum. Zwei OSC-Befehle kosten nichts. (Der Aux-Rückweg ist
davon nicht betroffen: Er *ist* ein Paar, unter einer einzigen Adresse.)

**Einmal fragen, dann wissen.** Antwortet ein Pult auf die Adresse nicht
(ältere Firmware, X32), läuft jede Abfrage in den Zeitablauf von 0,3 s.
Bei achtzehn Kanälen wären das über fünf Sekunden — bei *jedem*
Auffrischen der Karte. XRack merkt sich deshalb nach der ersten Abfrage,
dass dieses Pult den Schalter nicht kennt, und die Karte zeigt dann gar
keinen an.

Und weil er scharf ist — ein Kanal auf USB hört sein Mikrofon nicht mehr
—, ist USB die einzige farbige Stellung. Steht am Ende der Probe noch
irgendwo Farbe in der Karte, ist ein Kanal noch auf der Aufnahme.

**Im Kanalzug** steht der Eingangsschalter zwischen Kanalnummer und
Kanalname — also dort, wo der Kanal bezeichnet wird — und der Mute-Knopf
unten unter der dB-Anzeige, am anderen Ende. Nebeneinander waren sie so dicht, dass man mit dem Finger leicht
den falschen traf, und die beiden tun sehr verschiedene Dinge. Züge ohne
Schalter (die Summe) bekommen an dessen Stelle einen unsichtbaren
Platzhalter: denselben Knopf, nur nicht zu sehen. Ohne ihn stünden ihre
Regler eine Knopfhöhe höher als alle anderen — gemessen 15px.

**Die Sperre der Karte greift über eine Klasse** (`fader-bedienung`), nicht
über eine Liste von Klassennamen. Dort stand eine
(`".fader-input, .fader-mute"`), und sie hat genau den Fehler gemacht, für
den Listen anfällig sind: Der neue Eingangsschalter wurde gesperrt
gezeichnet — die Karte beginnt gesperrt — und beim Entsperren nicht
mitgenommen. Am Gerät sah das so aus: *„Die Anzeige stimmt, aber bei
Klick passiert nichts."* Kein Test hatte je entsperrt; jetzt tut einer es
und prüft, dass **nichts** gesperrt zurückbleibt — ohne die Namen der
Elemente zu kennen.

---

## Der Emulator

`scripts/xair-emulator.py` stellt ein XR18 nach: Es antwortet auf Port
10024 wie ein Pult und spielt mit `--audio` 18 Kanäle Testsignal in ein
ALSA-Loopback. Zwei Entscheidungen daran sind erklärungsbedürftig.

### Warum er seinen eigenen OSC-Kodierer hat

Naheliegend wäre, `encode()` und `decode()` aus
`core/console_control.py` zu benutzen — dieselben zwanzig Zeilen noch
einmal zu schreiben, sieht nach vergeudeter Mühe aus.

Es ist das Gegenteil. Ein Emulator, der den Kodierer der Gegenseite
benutzt, kann dessen Fehler nicht finden: Beide wären sich immer
einig, auch wenn beide falsch lägen. Genau so ein Fehler steckte
schon einmal drin — die Auffüllung hängte vier überzählige Nullen an
jede Adresse, deren Länge beim Teilen durch vier den Rest 3 lässt.
Das Typ-Tag stand dann vier Byte zu spät, und der Empfänger las eine
Nachricht *ohne Argumente*. Aufgefallen ist es nur, weil zufällig
keine der benutzten Adressen diese Länge hatte.

Mit zwei getrennten Implementierungen ist daraus eine Prüfung
geworden: Jede Seite dekodiert, was die andere gebaut hat, für jede
Adresslänge von 1 bis 40 (`test_xair_emulator.py`). Das kostet
sechzig Zeilen und ersetzt die Gegenprobe, die es vorher nicht geben
konnte.

Nebenbei läuft das Programm dadurch auf jedem Rechner mit Python,
auch ohne installiertes XRack.

### Warum die Testreihe gegen ihn läuft

Ein Emulator, der nur nebenherliegt, veraltet still: XRack fragt
irgendwann etwas Neues, der Emulator antwortet nicht mehr richtig,
und gemerkt wird es erst, wenn jemand ihm vertraut hat.

Deshalb steht er in `test_console_control.py` an der Stelle, an der
vorher eine eigene Attrappe stand — die vollständige Testreihe für
den Pultverkehr, knapp anderthalbtausend Zeilen, läuft gegen dieses
Programm. Bleibt sie grün, verhält er sich in allem, was XRack von
einem Pult erwartet, wie das Pult. Und was nur als importierte Klasse
funktionierte, fiele auf: Der Emulator wird zusätzlich als
Unterprozess gestartet und über einen echten `ConsoleControl`
angesprochen.

Der X32-Modus (`--x32`) ist derselbe Gedanke, einen Schritt weiter:
Diese Zweige hat vorher *nichts* geprüft, weil es kein X32 zum
Nachsehen gibt.

### Warum das Audio über snd-aloop läuft

XRack findet seine Interfaces über `arecord -l` und öffnet
`hw:Karte,Gerät` — ein Testinterface muss also eine echte Soundkarte
sein, kein Umweg innerhalb von XRack. Das liefert das Kernelmodul
`snd-aloop`: Was hineingespielt wird, kommt auf der anderen Seite als
Aufnahme heraus. XRack merkt keinen Unterschied, und an XRack musste
dafür nichts geändert werden — der Emulator ist Werkzeug daneben,
nicht Teil des Programms.

Die Belegung der Kanäle ist kein Zufall: Kanal 1 bis 7 tragen
Schlagzeug, Bass, Gitarre und Gesang, die Kanäle 8 bis 16 je so viele
kurze Pieptöne, wie ihre Nummer sagt (so lässt sich in einer Aufnahme
nachsehen, ob jede Spur dort gelandet ist, wo sie hingehört), und
17+18 den Lichtmix — Schlagzeug vorn, keine Stimme. Das ist der
AUX-Weg, für den es die Einzelkanal-Quelle der Lichtshow gibt, und
damit lässt sich die Show samt Blitz auf die Snare ohne Band prüfen.

---

## Warum die Samplerate gemessen und nicht geglaubt wird

XRack kann die Samplerate nicht erkennen. Mischpulte der X-Serie melden
über USB immer den ganzen unterstützten Bereich, nicht ihre laufende
Clock — deshalb stellt man sie von Hand ein. Steht sie falsch, läuft
trotzdem alles: Pegel, Aufnahme, Lichtshow. Auffallen tut es beim
Abhören, wenn die Aufnahme zu schnell oder zu langsam ist, und dann ist
der Abend vorbei.

Messen lässt es sich aber. Die Blöcke kommen im Takt der
*tatsächlichen* Clock — Rahmen je Sekunde Wanduhr ist die wahre Rate,
ganz gleich, was eingestellt ist. Drei Dinge machen daraus eine
brauchbare Auskunft statt eines Fehlalarms:

- **Der erste Block zählt nicht mit.** In ihm steckt der Rückstau aus
  dem ALSA-Puffer seit dem Öffnen. Er würde die Messung gerade am
  Anfang nach oben ziehen — dort, wo noch nichts mittelt.
- **Unter drei Sekunden gibt es kein Urteil**, sondern `None`. Ein
  „stimmt nicht" nach einer halben Sekunde wäre schlimmer als
  Schweigen: Man würde eine richtige Einstellung ändern.
- **Passt die Messung zu keiner üblichen Rate**, wird keine geraten.
  47000 Hz sind kein Einstellungsfehler, sondern Aussetzer beim Lesen —
  und dann ist „stell auf 48000" der falsche Rat.

Gemessen wird nur, umgestellt wird nichts. Die Rate ist eine Angabe
über die Hardware, und die gehört dem Nutzer; XRack sagt ihm, dass
etwas nicht zusammenpasst.

Beim Speicherplatz ist die Überlegung dieselbe, nur mit Eingriff: Läuft
die Karte mitten in einer Aufnahme voll, bricht das Schreiben ab, und
der Wave64-Kopf bekommt seine Größen nicht mehr nachgetragen — die
Datei ist unlesbar. Deshalb hört XRack vorher auf und schließt die
Datei ordentlich. Eine beendete Aufnahme ist zu retten, eine
abgebrochene nicht.

Der Lesethread hält sich dabei **nicht selbst an**: Er würde auf sich
selbst warten (`Thread.join()` auf den eigenen Faden). Er beendet nur
das Schreiben, schließt die Datei und setzt eine Marke; abgemeldet wird
im Statuslauf der Anwendung, also im Hauptfaden.

---

## Der gemeinsame Name im Netz

Wer die Oberfläche auf dem Tablet als App speichert, speichert damit
auch die Adresse: `https://x18rack.local:8080`. Im nächsten Proberaum
steht ein anderes XRack, das Symbol führt ins Leere — und eine
gespeicherte Web-App hat keine Adresszeile, in der man das ändern
könnte.

### Warum das nicht im Browser abgefangen wird

Das Naheliegende wäre eine Rückfrage in der App: „Nicht erreichbar —
andere Adresse?" Nur läuft dafür kein einziger Befehl. Antwortet der
Rechner nicht, kommt die Seite gar nicht erst an; was der Nutzer
sieht, ist die Fehlerseite des Browsers, nicht XRack.

Der einzige Weg, im Fehlerfall trotzdem eigenen Code auszuführen, ist
ein **Service Worker** mit einer zwischengespeicherten
Ausweichseite. Der ist hier gesperrt: Ein Service Worker verlangt
einen „sicheren Kontext", und dazu zählt eine HTTPS-Verbindung mit
einem Zertifikat, dem der Browser nicht traut, ausdrücklich nicht —
auch dann nicht, wenn man die Warnung einmal weggeklickt hat. XRack
liefert ein selbstsigniertes Zertifikat aus (siehe
`generate_tls_certificate` in `install.sh`), und das soll so bleiben.

### Der Weg über den Namen

Also andersherum: Nicht die App lernt mehrere Adressen, sondern die
Geräte teilen sich einen Namen. Jedes XRack meldet über avahi
zusätzlich zu seinem Hostnamen einen **gemeinsamen Zweitnamen**
(`core/mdns_alias.py`). Trägt man auf jedem Gerät `xrack` ein, findet
dieselbe gespeicherte App in jedem Raum das Gerät, das dort steht.

Gemacht wird das mit `avahi-publish -a`: Solange der Kindprozess läuft,
steht der Name im Netz.

Gemeldet wird dabei **genau eine** Adresse, obwohl der Pi meist
mehrere hat. Zuerst war es jede — die Begründung klang zwingend: Je
nach Raum erreicht das Tablet den Pi über das Kabel oder über den
Access Point. Am Gerät kam davon zurück: *„gelegentlich erreichbar,
dann meldete der Browser eine Netzwerk-Zeitüberschreitung."*

Der Grund steckt in `avahi-publish`: Es kennt keine Option für eine
Schnittstelle (nachgesehen in `avahi-utils/avahi-publish.c`) und
meldet deshalb jede Adresse auf **allen**. Ein Tablet im Heimnetz bekam
damit zwei Antworten — die richtige und die `10.42.0.1` der
Access-Point-Brücke, die von dort niemand erreicht. Welche der Browser
nimmt, entscheidet er selbst; nimmt er die zweite, laufen die Pakete
zum Router und verschwinden dort: keine Fehlermeldung, sondern eine
halbe Minute Warten.

Der eigene Hostname hatte das Problem nie. Den meldet `avahi-daemon`
selbst, und der kennt seine Schnittstellen — auf `wlan0` antwortet er
mit der `wlan0`-Adresse, auf `br0` mit der von `br0`. Genau deshalb war
`x18rack.local` durchgehend erreichbar, während `xrack.local`
sprunghaft war.

Nachbauen lässt sich das mit `avahi-publish` nicht, also wird
ausgewählt — und zwar die Adresse, die von **überall** erreichbar ist:
die der Schnittstelle mit der Standardroute. Ein Tablet im Heimnetz
erreicht sie direkt, eines am Access Point über XRack, denn für das ist
XRack das Gateway. Gibt es keine Standardroute (Proberaum ohne
Heimnetz), gilt die Brücke des Access Points; dann hängen die Tablets
ohnehin dort. Umgekehrt gilt der Satz nicht: Die Adresse des Access
Points ist nur von dort zu erreichen.

Zwei Dinge hält eine Wache im Auge: Wechselt die Adresse (Kabel raus,
Access Point an), wird der Name neu gemeldet — ein Eintrag auf eine
Adresse, die es nicht mehr gibt, ist schlimmer als gar keiner. Und
endet ein Kindprozess, war es ein **Namenskonflikt**: Dann stehen zwei
XRacks mit demselben Zweitnamen im selben Netz. Das erscheint in den
Einstellungen, und danach ist erst einmal eine Minute Ruhe — zwei
Geräte, die sich im Sekundentakt um denselben Namen streiten, fluten
nur das Netz.

Was avahi im echten Netz daraus macht, kann nur ein Versuch am Gerät
zeigen. Die Testreihe (`test_mdns_alias.py`) prüft die Seite, die XRack
gehört: dass für jede Adresse gemeldet wird, dass ein Adresswechsel
nachgezogen wird, dass ein Konflikt gemeldet statt verschwiegen wird
und dass ein fehlendes `avahi-publish` (Paket `avahi-utils`) als
solches dasteht.

---

## Der Installer und `set -eE`

`install.sh` läuft unter `set -eE` mit einer ERR-Falle: Bricht ein
Schritt ab, endet der Lauf mit einer Meldung, statt weiterzumachen und
am Ende ein halb eingerichtetes Gerät zu hinterlassen. Das ist richtig
so — es hat aber zwei Fallen, und beide haben schon zugeschlagen.
Beide sahen von außen gleich aus: Der Lauf endete mitten in der
Netzwerkkonfiguration, und alles danach (Bluetooth, USB-Automount,
DMX, sudo-Regeln, der Dienst) fiel aus.

**Falle 1: die Zuweisung aus einer Kommandosubstitution.**

```bash
XRACK_HOME_VORHANDEN="$(aktuelle_home_ssid)"
```

Der Rückgabewert der Substitution wird der der ganzen Anweisung. Gibt
es das Profil `XRack-Home` nicht, endet `nmcli` mit Code 10 — und
`set -e` beendet den Installer. „Kein Profil vorhanden" ist aber eine
*Antwort*, keine Störung. Deshalb endet jeder solche Helfer heute auf
`|| true` (`aktuelle_home_ssid`, `aktuelle_ap_ssid`), mit einem
Kommentar, der genau das sagt.

**Falle 2: die Prüfkette, die einen Befehl startet.**

```bash
[ "$(lower "${ANTWORT}")" = "j" ] || [ "$(lower "${ANTWORT}")" = "y" ] \
    && configure_access_point
```

Sagt der Nutzer „nein", sind beide Prüfungen falsch, der Befehl läuft
nicht — und die Kette endet mit Code 1. Hier ist die Feinheit, die das
so tückisch macht: **Die Kette für sich bricht nicht ab.** `set -e`
nimmt fehlschlagende Glieder einer AND-OR-Liste ausdrücklich aus:

```
$ bash -c 'set -e; [ x = j ] || [ x = y ] && echo ja; echo weiter'
weiter
```

Der Rückgabewert einer *Funktion* ist nicht ausgenommen — und ein `if`
liefert den seines ausgeführten Zweigs. Steht die Kette also am Ende
einer Funktion oder eines Zweigs, wird ihre 1 zum Rückgabewert der
Funktion, und der Aufruf in der Hauptfolge bringt den Lauf um:

```
$ bash -c 'set -eE; trap "echo TRAP" ERR
           f() { [ x = j ] || [ x = y ] && echo ja; }; f; echo "nach f"'
TRAP
```

Ob eine solche Zeile am Ende steht, sieht man ihr nicht an — sie kann
durch eine spätere Änderung dorthin geraten. Deshalb steht die Regel
heute als Zusicherung in `test_install_settings.py`: Eine Prüfung mit
`&&` darf den Ablauf steuern (`return`, `continue`, `break`, `exit`)
oder eine weitere Prüfung sein. Soll ein **Befehl** laufen, gehört er
in ein `if` — dessen Bedingung darf gefahrlos falsch sein.

Dazu gehört die dritte Regel, die aus beiden folgt: `configure_wifi`
endet auf einem ausdrücklichen `return 0`. Die Funktion besteht aus
Fragen, und keine Antwort darauf ist ein Fehler. Was dort wirklich
schiefgehen kann — Bridge, Freigabeprofil, Kabelprofil —, meldet jeder
Helfer selbst mit einer Warnung.

**Warum das erst beim zweiten Lauf auffiel:** Der Zweig mit der Kette
gibt es nur, wenn schon ein Access Point eingerichtet *ist*; beim
Erstlauf läuft der andere Zweig mit einem sauberen `if`. Getroffen hat
es damit genau den Fall, für den der Updater den Lauf verlangt — den
zweiten. Geprüft wird er heute in einer Pseudo-Konsole
(`test_wlan_setup.py`), weil der Fehler nur im interaktiven Zweig
steckt: `configure_wifi` legt ohne Terminal gar nicht los.

---

## Update und Rückfall

Beide Wege — aus dem Internet und vom USB-Stick — laufen durch denselben
Ablauf, es gelten also dieselben Zusicherungen. Kommt die Weboberfläche
nach dem Update nicht zurück, stellt der Updater den vorherigen Stand
selbsttätig wieder her.

**Der Port ist dabei entscheidend.** Der Updater prüft nach dem Neustart,
ob XRack wieder antwortet — auf dem Port, der ihm mitgegeben wurde. Stimmt
der nicht mit dem tatsächlich eingestellten überein (`config/local.yaml`),
hält er den Neustart für gescheitert und rollt zurück, obwohl alles in
Ordnung ist.

**Git-Arbeitskopie:** Ist das Installationsverzeichnis eine
Git-Arbeitskopie, zieht XRack sie nach dem Update aus dem Internet gleich
mit nach — `git pull` funktioniert danach ohne Zutun weiter. Das passiert
nur, wenn derselbe Branch ausgecheckt ist, aus dem das Update kam: Wer auf
einem Entwicklungszweig sitzt und aus `main` aktualisiert, soll seinen
Zweig nicht hinter seinem Rücken gewechselt bekommen — dort nennt die
Erfolgsmeldung stattdessen den passenden Befehl. Beim Weg über den
USB-Stick bleibt es ebenfalls beim Hinweis, weil dort unbekannt ist,
welchem Stand die mitgebrachte ZIP entspricht.

Nutzerdaten sind davon nicht betroffen: Aufnahmen, Musik, PIN,
Einstellungen und `.venv` stehen in der `.gitignore` und werden von git gar
nicht verfolgt.

---

## Licht und OLA

### Warum ein eigener Systemdienst

Das DMX-Signal erzeugt XRack nicht selbst. Das macht **OLA** (Open Lighting
Architecture) als eigener Dienst, den die Installation einrichtet.

Ein DMX-Bild braucht rund alle 23 Millisekunden eine neue Sendung, und zwar
zuverlässig. Im selben Prozess, der Audio aufnimmt und den Webserver
bedient, wäre jede Aufnahme eine mögliche Ursache für Flackern. Es ist
dasselbe Muster wie beim WLAN (`hostapd`) und bei Bluetooth
(`bluetoothd`): Ein ausgereifter, extern gepflegter Dienst übernimmt die
zeitkritische Hardwarearbeit, XRack bleibt ein dünner Aufsatz darauf und
spricht ihn über einen HTTP-Aufruf auf `127.0.0.1` an.

Licht stört Aufnahme und Wiedergabe deshalb nie: Fehlt der Dienst oder das
Kabel, läuft XRack einfach ohne Licht weiter.

### Plugins, die sich streiten

Vier OLA-Plugins erkennen dieselbe Hardware: `ftdidmx`, `usbserial`,
`opendmx` und `stageprofi`. Bleiben mehrere aktiv, streiten sie sich um das
Kabel. `install.sh` schaltet deshalb `ftdidmx` ein und die anderen drei
aus.

`stageprofi` stand dort zuerst nicht drin, und genau das fiel am Gerät auf:
Es griff sich `/dev/ttyUSB0` im Sekundentakt, fragte an, bekam keine
Antwort, gab wieder frei — endlos. In der Zeit kam `ftdidmx` nicht an das
Kabel heran, und es blieb dunkel.

### Die eigene systemd-Unit

Das Debian-Paket bringt je nach Stand nur ein SysV-Startskript mit, das
systemd einpackt. Eine Ergänzung („drop-in") hängt ihre Optionen dann an
den Aufruf des Startskripts an, das sie schlicht ignoriert — eingerichtet
sieht es aus, gewirkt hat es nicht. `install.sh` schreibt in diesem Fall
eine eigene Unit nach `/etc/systemd/system`, die `olad` direkt startet und
seine Weboberfläche auf `127.0.0.1` festnagelt.

Diese eigene Unit muss danach **selbst** eingeschaltet werden. Das ist
zuerst untergegangen: Das `enable` weiter oben galt der Unit, die es zu
diesem Zeitpunkt gab. Bis zum nächsten Neustart lief alles, weil der alte
Daemon noch lief — nach dem Hochfahren stand der Dienst auf `disabled`, und
das Licht blieb aus.

### Die Zuordnung zum Universum

Ein eingerichtetes Plugin sendet noch nichts. Der Anschluss des
Kabels muss erst einem Universum zugeordnet werden — auf der
Kommandozeile `ola_patch -d <Gerät> -p <Port> -u 1`, nachdem
`ola_dev_info` die beiden Nummern verraten hat.

Das ist der Schritt, den man vergisst, weil von außen alles heil
aussieht: Der Dienst läuft, das Kabel steckt, XRack meldet
erfolgreich gesendete Bilder — und es bleibt dunkel. Deshalb steht
die Zuordnung mit im Zustandsbericht, und die Lichtkarte benennt den
Fall.

Erledigen lässt er sich in den Einstellungen unter *Licht*. XRack
spricht dafür dieselbe Web-Schnittstelle von olad an, über die auch
die Kanalwerte gehen (`/json/get_ports`, `/new_universe`,
`/modify_universe`) — kein Aufruf von `ola_patch`, kein sudo, kein
Wrapper-Skript. Nach dem Auftrag wird nachgesehen, ob der Anschluss
wirklich im Universum steht: olad antwortet auch dann mit „ok", wenn
die Zuordnung im Hintergrund scheitert, etwa weil ein anderes Plugin
das Kabel hält.

XRack sendet in genau ein Universum, also gibt es genau einen
Ausgang: Eine neue Zuordnung ersetzt die vorherige. Sonst bliebe ein
einmal falsch gewählter Anschluss für immer drin, und man bräuchte
doch wieder ein Terminal, um ihn loszuwerden.

### Kabel

Angesteuert werden USB-DMX-Kabel mit FTDI-Chip (FT232R und Verwandte) —
das verbreitetste und günstigste Genre, dazu gehören Enttecs „Open DMX
USB" und die üblichen Nachbauten.

Die praktische Unbekannte bei billigen Kabeln ist nicht die Software,
sondern die galvanische Trennung zur DMX-Seite. Ohne Optokoppler hängt der
Pi elektrisch an den Lampen. Bei Störungen, die sich nicht durch Software
erklären lassen, ist das der erste Verdacht — noch vor der Kabellänge, die
bei DMX (RS-485, bis 1000 m) selten das Problem ist.

---

## Die Lichtshow

### Ein Kanal oder zwei — und warum das kein Sparzwang ist

Die Show hört auf eine Quelle, und die ist wählbar: ein Kanalpaar
(beide Kanäle gemittelt) oder ein einzelner Kanal. Technisch ist das
ein kleiner Unterschied — `_mono()` in `lighting/analysis.py` mittelt
dann nicht, sondern liest nur. Praktisch ist es der Grund, warum es
die Wahl überhaupt gibt.

Ein Kanalpaar ist normalerweise die Summe, also das, was auch aus den
Boxen kommt. Für eine Lichtshow ist das nicht unbedingt das beste
Signal: Die Stimme steht dort vorn, und die Show tanzt dann auf dem
Gesang statt auf dem Schlagzeug. Am Pult lässt sich stattdessen ein
**AUX-Bus** mit einem eigenen Mix fürs Licht bauen — Bassdrum und
Snare betont, die Stimme heraus. Ein AUX-Weg ist mono, und ein
zweiter Kanal dafür wäre reine Verschwendung: Er trüge dasselbe
Signal noch einmal. Der gesparte USB-Kanal steht für eine Spur mehr
in der Aufnahme bereit.

Ein Punkt gehört mitgedacht: Derselbe Kanal kommt als Mono doppelt so
laut an wie als Hälfte eines Paares, dessen Nachbar still ist — 6 dB,
der Mittelwert von *x* und 0 ist *x*/2. Den Bändern ist das egal, sie
messen sich an der laufenden Spitze. Die **Stille-Schwelle** aber
arbeitet auf dem absoluten Pegel; wer von einem halb belegten Paar auf
Mono umstellt, muss sie unter Umständen nachziehen.

Damit das überhaupt geht, hört die Show am **ungeschnittenen** Strom
mit. Der Recorder liest das Interface immer mit allen Kanälen (anders
geht es bei der X-Serie ohnehin nicht) und schneidet erst für Datei
und Pegelanzeige auf die eingestellte Aufnahmebreite. Vorher fiel der
Schnitt schon beim Lesen — und die Lichtshow hing als Mithörer daran:
Am X32 standen ihr 18 Kanäle zur Auswahl statt der 32, die das Pult
liefert. 18 ist die Vorgabe für die *Aufnahme* und hat mit der
Lichtquelle nichts zu tun. Wer nur acht Spuren aufnimmt, soll das
Licht trotzdem von Kanal 12 holen dürfen — genau das ist der AUX-Fall.

In der Oberfläche ist das **eine** Auswahl mit zwei Gruppen, nicht
eine Auswahl plus ein Schalter daneben. Der Grund steht in der
jüngeren Vergangenheit: Die WLAN-Funkregion hatte ihren eigenen
Speicherknopf neben dem Formular, stand sichtbar richtig da und war
nie gespeichert — mit einer Fehlermeldung am Ende, die alles Mögliche
bedeuten konnte. Eine Entscheidung, ein Bedienelement, ein
Speicherweg.

---

### Warum der Puls eine Hüllkurve ist und kein An/Aus

Im zweiten Show-Modus atmen alle Segmente gemeinsam im Takt. Der
naheliegende Weg wäre, sie auf den Schlag anzuschalten und danach
wieder aus — das sieht aber aus wie ein Stroboskop mit Taktgefühl,
nicht wie Musik.

Stattdessen läuft eine Hüllkurve: hart auf 1 beim Schlag, dann
derselbe Ein-Pol-Abfall, mit dem auch die Bänder in `analysis.py`
zurückgehen (0,25 s). Hart hoch ist Absicht — ein Puls, der erst
anschwillt, kommt hinter dem Schlag her, und dann sieht das Licht aus,
als hinke es der Musik hinterher.

Unten bleibt ein Boden stehen, vorgegeben mit demselben Wert wie beim
wandernden Punkt (`GRUNDHELLIGKEIT`). Dort heißt er „wie hell ist ein
Segment, das gerade nicht dran ist", hier „wie hell zwischen zwei
Schlägen" — es ist dieselbe Frage. Der Boden multipliziert dabei den
Bandpegel und addiert nichts dazu: Bei Stille bleibt es deshalb
dunkel, statt ein Grundleuchten stehen zu lassen, das man nicht mehr
los wird.

Beide Zahlen sind Vorgaben, keine Festlegungen: Nachleuchten und
Grundhelligkeit stehen als Regler in den Einstellungen, sobald der
Puls gewählt ist. Ob 0,25 s und 35 % passen, entscheidet sich an den
Lampen und am Musikgeschmack — auf einer Bar zu hartem Techno will man
etwas anderes als bei ruhiger Musik. Der Boden darf dabei bis auf 0
(zwischen den Schlägen ganz aus), aber nicht bis 1: Dort gäbe es
überhaupt keinen Puls mehr, und ein Regler, der genau den Effekt
abschaltet, den er einstellen soll, hört vorher auf.

Das Hintergrundlicht bekommt vom Puls nichts mit. Es hat sein eigenes
Bild — eine Farbe, über mehrere Schläge weich übergeblendet —, und ein
Wash, der im Takt zuckt, ist kein Wash mehr.

---

### Die Farbumkehr

Welches Segment welches Frequenzband bekommt, steht sonst über das
ganze Stück still: Segment 1 der Bass, Segment 2 die Mitten, Segment 3
die Höhen, dann von vorn. Die Bewegung kommt allein vom wandernden
Punkt oder vom Puls.

Zugeschaltet kippt diese Zuordnung alle paar Schläge — gezählt wie der
Farbwechsel des Hintergrundlichts, mit demselben Notnagel über die
Uhr, falls die Erkennung keinen Takt findet. Umgekehrt heißt dabei
wörtlich das: `stelle = len(BAENDER) - 1 - stelle`. Aus Rot-Grün-Blau
wird Blau-Grün-Rot.

Zwei Dinge fallen dabei von selbst richtig aus. Es wirkt in **beiden**
Show-Bildern, weil Lauflicht und Puls durch dieselbe Stelle laufen und
sich nur in der Helligkeit unterscheiden. Und eine Lampe mit nur einer
Farbgruppe bleibt unberührt — sie bekommt die Mischung aller drei
Bänder, und die ist symmetrisch.

Das Hintergrundlicht hat gar keine Reihenfolge über die Segmente: Es
zeigt eine Farbe nach der anderen aus einem gemeinsamen Zähler.

---

### Was „Snare" hier heißt

Der Blitz hängt an einer Erkennung, die keine ist: XRack erkennt
keine Snare, sondern einen **scharfen, lauten Einsatz im Mittenband,
der Höhen mitbringt**. In den allermeisten Stücken ist das die Snare;
es kann auch ein Clap sein oder ein hart angeschlagener Akkord.

Vier Bedingungen müssen zusammenkommen, und jede sortiert etwas
Bestimmtes aus. Die Zahlen daneben sind an künstlichen Signalen
gemessen:

| Bedingung | Sortiert aus | Gemessen |
| --- | --- | --- |
| Ausschlag über dem eigenen Mittel | gehaltene Töne | ein Sägezahn meldet ohne sie zwanzig Blitze in vier Sekunden, mit ihr keinen |
| laut, gemessen an der laufenden Spitze | alles Beiläufige | — |
| Höhen müssen da sein | den Kick | beim Kick lagen sie bei 0,04 der Spitze, bei der Snare bei 0,65 |
| Mitten gegen Höhen | die Hi-Hat | Verhältnis 0,3 bei der Hi-Hat, 1,3 bei der Snare |

Dazu eine **Anlaufzeit** von einer Sekunde, in der gar nichts
gemeldet wird. Der gleitende Mittelwert startet bei null und die
laufende Spitze an ihrem Mindestwert — in den ersten Augenblicken ist
deshalb jeder Wert ein Vielfaches von fast nichts, und alle vier
Bedingungen sind nebenbei erfüllt. An einem völlig gleichbleibenden
Ton ohne eine einzige Transiente meldete die Erkennung Snares bei
0,000 s, 0,171 s und 0,341 s. Weil jede Änderung in den Einstellungen
die Show neu startet, bekam man beim Drehen am Regler jedes Mal eine
Salve Blitze — und hätte sie für die Wirkung der Einstellung
gehalten.

Die ersten beiden hängen am Regler *Empfindlichkeit*, die letzten
beiden stehen fest: Die sagen „ist das überhaupt eine Snare" und
nicht „wie viel davon".

**Dass beide am selben Regler hängen, ist eine Korrektur.** Zuerst
bewegte er nur die Schwelle, der Ausschlag stand fest bei 2,5. Am
Gerät zeigte sich, dass genau der bremst: Es blitzte am Anfang eines
Songs und wenn in einer ruhigen Stelle etwas Lautes passierte, aber
nicht im laufenden Groove. Der Grund steckt in der Rechnung — im
Groove hebt die Snare ihr eigenes Bezugsmittel mit an und kommt nicht
mehr um das 2,5-fache darüber; nach einer leisen Stelle ist das
Mittel niedrig, da ragt sie heraus. Wer nur die Schwelle
herunterdreht, kommt daran nicht heran.

Der Verlauf ist quadratisch, und die Mitte des Reglers trifft genau
die beiden Zahlen, die am Gerät gefallen haben (Schwelle 0,2,
Ausschlag 2,5). Die feine Abstufung liegt damit dort, wo tatsächlich
eingestellt wird.

Ohne die dritte Bedingung meldete ein Signal aus **lauter Kicks ohne
jede Snare** acht von acht Malen eine Snare — die steile Flanke des
Kicks lässt auch die Mitten ausschlagen. Das Blitzlicht hätte auf der
Bassdrum gezuckt.

Der schwierigste Fall bleibt Kick und Hi-Hat auf demselben Achtel:
Der Kick liefert den Rumpf, die Hi-Hat die Höhen, zusammen sieht das
aus wie eine Snare, und keine der beiden festen Bedingungen greift.
Mit drei Bändern lässt sich das nicht sauber trennen — dagegen hilft
nur, die Empfindlichkeit herunterzudrehen.

### Warum die Show den Strobe-Kanal dann besitzt

Solange der Blitz aus ist, fasst die Show Strobe-Kanäle nicht an; ein
von Hand gestellter Wert bleibt stehen. Ist er an, schreibt sie
zwischen den Blitzen ausdrücklich 0 — und überschreibt damit, was von
Hand dort stand.

Das ist kein Versehen, sondern nötig: Jedes Lichtbild beginnt bei
dem, was zuletzt drin stand. Würde die Show den Kanal nach dem Blitz
einfach „in Ruhe lassen", bliebe der Blitzwert stehen, und das Strobe
liefe durch, bis jemand die Show anhält.

Genau deshalb **gibt die Show die Kanäle beim Anhalten auch wieder
zurück** und setzt sie einmal auf 0. Hört sie mitten in einem Blitz
auf — und ein Blitz dauert 80 ms bei mehreren je Sekunde, das ist
kein Sonderfall —, bliebe der Wert sonst stehen und die Lampe würde
weiterblitzen, obwohl die Show längst aus ist. Angefasst wird dabei
nur, was die Show auch gefahren hat: Hintergrundlicht und
ausgenommene Lampen behalten ihren Wert.

---

## Wave64 statt WAV

Aufnahmen liegen als `.w64`. Das klassische WAV-Format kann wegen seiner
32-Bit-Größenangaben nicht über 4 GB hinaus, und diese Grenze ist bei
vielkanaligen Mitschnitten schnell erreicht: 18 Kanäle mit 48 kHz und
24 Bit sind rund 156 MB pro Minute, die 4 GB sind also nach etwa 26
Minuten voll. Wave64 rechnet mit 64 Bit und hat diese Grenze nicht.
