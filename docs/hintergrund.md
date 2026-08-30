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

## Wave64 statt WAV

Aufnahmen liegen als `.w64`. Das klassische WAV-Format kann wegen seiner
32-Bit-Größenangaben nicht über 4 GB hinaus, und diese Grenze ist bei
vielkanaligen Mitschnitten schnell erreicht: 18 Kanäle mit 48 kHz und
24 Bit sind rund 156 MB pro Minute, die 4 GB sind also nach etwa 26
Minuten voll. Wave64 rechnet mit 64 Bit und hat diese Grenze nicht.
