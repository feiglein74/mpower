# mPower — lokale Steuerung einer Ubiquiti mFi mPower

Ubiquiti hat die mFi-Plattform eingestellt: Cloud und Controller sind tot, die
Hardware läuft lokal aber unverändert weiter. Dieses Projekt steuert die
Steckdosenleiste direkt über ihre lokale HTTP-API — ohne Cloud, ohne Controller.

## Getestetes Gerät

| | |
|---|---|
| Modell | mFi mPower EU, 3 Ausgänge |
| Firmware | `MF.v2.1.8` (Build 09.02.2015) |
| Kernel | Linux 2.6.32.29, MIPS |
| SoC | Atheros **AR9330** (Hornet), MIPS 24Kc V7.4 |
| RAM | 32 MB (≈29,5 MB nutzbar) |
| Flash | 8 MB — u-boot 256K \| u-boot-env 64K \| kernel 1M \| rootfs 6,6M \| cfg 256K \| EEPROM 64K |
| Rootfs | zu 100 % belegt — auf dem Gerät ist kein Platz für eigene Software |
| Zugang | `admin` / `ubnt`, HTTP (80), SSH (22), Telnet (23) alle offen |

## Benutzung

```bash
./mpower.py status              # Zustand aller Ports
./mpower.py status --json       # maschinenlesbar
./mpower.py on 2                # Port 2 einschalten
./mpower.py off 2 3             # mehrere Ports
./mpower.py toggle 1
./mpower.py watch -n 2          # Leistung fortlaufend
```

Konfiguration über `~/.config/mpower/config.ini` oder Umgebungsvariablen
(`MPOWER_HOST`, `MPOWER_USER`, `MPOWER_PW`); Vorgabe ist `10.10.1.78`.

```ini
[mpower]
host = 10.10.1.78
user = admin
password = <geraetepasswort>

[mqtt]
host = <broker-ip>
port = 1883
user = <mqtt-benutzer>
password = <mqtt-passwort>
prefix = mpower
device_topic = mfi/mpower
```

Die Datei gehört **nicht** ins Repository (`chmod 600`).

## MQTT-Bridge und Home Assistant

`mqtt_bridge.py` pollt die Leiste und spiegelt sie nach MQTT. Home Assistant legt
die Entitäten per Autodiscovery selbst an — dort ist **keine** Konfiguration nötig,
solange die MQTT-Integration denselben Broker benutzt.

```bash
./mqtt_bridge.py --once          # einmal abfragen (Test)
./mqtt_bridge.py -n 15           # Dauerbetrieb, 15 s Intervall
./mqtt_bridge.py --no-discovery  # ohne HA-Discovery-Nachrichten
```

### Zwei Betriebsmodi

Entscheidend ist, **woher Home Assistant die Daten liest**. Das legt `--source` fest.

```bash
./mqtt_bridge.py --source device --once   # empfohlen: HA redet direkt mit dem Gerät
./mqtt_bridge.py --source bridge -n 15    # schneller, braucht diesen Dienst dauerhaft
```

| | `--source device` | `--source bridge` |
|---|---|---|
| Datenquelle | die Steckdose selbst | dieser Rechner |
| Läuft ohne Notebook | **ja** | nein |
| Dauerdienst nötig | nein — ein `--once` genügt | ja |
| Aktualisierung | 60 s (nach Schaltbefehl sofort) | 15 s |
| Entitäten | 12 (Schalter, Leistung, Spannung, Energie) | 15 (zusätzlich Strom) |
| Strom-Sensor | nein — Gerät publiziert ihn nicht | ja |

**`device` ist die robustere Wahl.** Die gerätseitigen mFi-tools können alles
Wesentliche selbst: schalten (`port<N>/relay/set` mit `1`/`0`), Zustand melden und
Energie zählen. Home Assistant spricht dann unmittelbar mit der Steckdose, und
dieses Projekt wird nach dem einmaligen Anmelden nicht mehr gebraucht.

Der Schaltweg ist verifiziert — Kommando über MQTT, Gegenprobe direkt an der
Hardware:

```
Hardware vorher : p1=1 p2=1 p3=1 | MQTT meldet: 1
nach set=0      : p1=1 p2=0 p3=1 | MQTT meldet: 0
nach set=1      : p1=1 p2=1 p3=1 | MQTT meldet: 1
```

Die Rückmeldung kommt dabei nicht erst nach 60 s: `mqsub.sh` setzt nach jedem
Schaltbefehl `echo 5 > $tmpfile` und erzwingt damit eine sofortige Aktualisierung.

**Achtung beim Wechsel:** Läuft die Bridge im Modus `bridge` **nicht** dauerhaft,
werden Leistung, Strom und Spannung in HA `unavailable` — die Bridge meldet beim
Beenden korrekt `offline`. Entweder als Dienst starten (`mpower-mqtt.service`) oder
`--source device` verwenden.

### Entitäten

Im Modus `bridge` entstehen 15 Entitäten: pro Port ein Schalter plus Leistungs-,
Strom-, Spannungs- und Energiesensor. Im Modus `device` sind es 12 (ohne Strom).

### Woher der Energiezähler kommt

Der Energiezähler ist der einzige Wert, den die Bridge **nicht** selbst liefert —
die HTTP-API gibt ihn nicht her:

```
GET /sensors/1/energy_sum  →  {"status":"fail","error":"'energy_sum' is not a valid resource"}
```

Über HTTP gäbe es nur `thismonth` (grober Monatswert). Der echte Zähler steht in
`/proc/power/energy_sum<N>` und wäre nur per SSH erreichbar.

Statt dafür einen zweiten Transport in die Bridge zu bauen, zeigt die
Discovery-Konfiguration **direkt auf das Topic, das die gerätseitigen mFi-tools
ohnehin publizieren**:

```json
"state_topic": "mfi/mpower/port1/energy",
"availability_topic": "mfi/mpower/$online"
```

Das kostet nichts extra: keine SSH-Sitzung, keine Zusatzlast auf dem Gerät, und die
Werte sind retained — Home Assistant hat sie sofort nach einem Neustart. Die
Verfügbarkeit hängt bewusst am Gerät statt an der Bridge, denn das Gerät publiziert
auch weiter, wenn die Bridge aus ist.

**Voraussetzung:** Die gerätseitigen mFi-tools müssen laufen und auf denselben
Broker zeigen (siehe „Änderungen am Gerät"). Ohne sie bleibt der Energiesensor
`unavailable` — alles andere funktioniert weiter. Abschalten mit
`--device-topic ""`.

Genauer als über MQTT geht es per SSH, dann aber nur auf Abruf:

```bash
./mpower.py status --energy      # liest /proc/power/energy_sum<N> via SSH
```

Der Unterschied: Das Gerät rundet auf ganze Wattstunden (`11`), SSH liefert den
vollen Wert (`10.94`). Die Umrechnung ist `cf_count<N> × 0,3125 Wh`.

| Topic | Inhalt |
|---|---|
| `mpower/<node>/availability` | `online` / `offline` (LWT) |
| `mpower/<node>/port<N>/state` | `ON` / `OFF` (retained) |
| `mpower/<node>/port<N>/set` | Kommandos hierher |
| `mpower/<node>/port<N>/power` | Watt |
| `mpower/<node>/port<N>/current` | Ampere |
| `mpower/<node>/port<N>/voltage` | Volt |

`<node>` ist `mpower_<ip_mit_unterstrichen>`, also `mpower_10_10_1_78`.

Als Dauerdienst: siehe `mpower-mqtt.service` (systemd-Benutzerdienst, kein root).

### Abfrageintervall

Vorgabe sind 15 s. Ob schnelleres Polling dem 2015er-SoC schadet, ist **nicht
belegt** — es gibt keinen reproduzierbaren Bericht dazu. Die gepflegten
Fremdprojekte fahren aber durchweg träge (die MQTT-Tools mit 60 s), daher der
konservative Start. Wer es eiliger braucht, dreht mit `-n 5` runter und beobachtet,
ob das Gerät stabil bleibt.

## Änderungen am Gerät

Am Gerät wurde Konfiguration verändert. Sicherungen aller Originaldateien liegen in
`backup-geraet/`.

### Was geändert wurde

**1. Controller-Suche abgeschaltet** — `/etc/persistent/cfg/mgmt`

Das Gerät suchte alle ~19 s einen mFi-Controller, den es nicht mehr gibt, und
blinkte deswegen. Der Syslog war voll mit:

```
ace_reporter.reporter_connected(): connect(http://10.0.0.89:6080/inform)
    failed with errors: 0 148 - No route to host
ace_reporter.reporter_fail(): [STATE] entering SELFRUN!!!!
```

Entfernt wurden beide Einträge:

```
mgmt.servers.1.url=http://10.0.0.89:6080/inform     (Host existiert nicht mehr)
mgmt.servers.2.url=http://mfi:6080/inform           (Name nicht auflösbar)
```

Ergebnis: `/proc/led/freq` fiel von `1` auf `0` — das Blinken hörte auf.

**Nicht vollständig gelöst:** `mcad` versucht weiterhin `http://mfi:6080/inform`.
Diese Adresse ist offenbar fest eingebaut und kommt nicht aus der Konfiguration.
Der Versuch scheitert aber harmlos an der Namensauflösung, ohne Timeout-Spam.
`mcad` selbst lässt sich nicht dauerhaft beenden — es steht in `/etc/inittab` als
`null::respawn:/bin/mcad` und wird von init sofort neu gestartet. Deshalb wurde die
Konfiguration entschärft statt gegen `respawn` anzukämpfen.

**2. Vorhandene MQTT-Installation umgebogen** — `/etc/persistent/mqtt/client/mqtt.cfg`

Auf dem Gerät lagen bereits die
[mFi-tools](https://github.com/maletazul/mFi-tools) und publizierten seit
Ewigkeiten an einen Broker, den es nicht mehr gibt (`10.0.0.220`).

```diff
- mqtthost=10.0.0.220
- #mqttusername=username
- #mqttpassword=password
+ mqtthost=<dein-broker>
+ mqttusername=<dein-mqtt-benutzer>
+ mqttpassword=<dein-mqtt-passwort>
  refresh=60
  topic=mfi/mpower
```

### Änderungen dauerhaft machen

`/etc` liegt im RAM. Ohne Commit ins Flash ist nach dem nächsten Stromausfall alles
weg. Der Befehl heißt in der interaktiven Shell `save`, das ist aber nur ein Alias
(`/etc/profile`) und greift über SSH nicht:

```bash
cfgmtd -w -p /etc/          # das ist, was 'save' wirklich tut
```

Erfolgsmeldung sieht so aus (schreibt Active- **und** Backup-Slot):

```
Found Backup1 on[1] ...
Storing Active[1] ... [%0][%63][%100]
Active->Backup[2] ... [%0][%63][%100]
```

### Sicherung des Geräts

`backup-device.py` lädt `/etc/persistent/` vollständig herunter (566 Dateien,
jede gegen `md5sum` auf dem Gerät verifiziert):

```bash
./backup-device.py
```

Die Übertragung läuft per `cat` über einen SSH-`exec`-Kanal — Dropbear 0.51 hat
keinen SFTP-Server, und BusyBox bringt kein `base64` mit. Ohne PTY kommen Rohbytes
unverfälscht durch, solange man sie nicht dekodiert; deshalb bleiben auch die
MIPS-Binaries (`mosquitto_pub`, `libmosquitto.so.1`) heil.

Nebenbefund: Unter `data/` liegen ~548 Dateien Verbrauchshistorie, tageweise ab
August 2020.

### Nicht im Repository

Zwei Dateien der Sicherung enthalten Geheimnisse und sind per `.gitignore`
ausgeschlossen. **Sie liegen lokal vor und werden für ein Rollback gebraucht** —
wer das Repository klont, hat sie nicht:

| Datei | Inhalt | Vorlage im Repo |
|---|---|---|
| `backup-geraet/cfg/mgmt` | `mgmt.authkey`, `mgmt.cloud_pass` | `cfg/mgmt.beispiel` |
| `backup-geraet/mqtt/client/mqtt.cfg` | Broker-Passwort | `mqtt/client/mqtt.cfg.beispiel` |

### Rückgängig machen

```bash
# Originaldateien aus backup-geraet/ zurückspielen, dann ins Flash schreiben:
cfgmtd -w -p /etc/
```

### LED direkt steuern

Unabhängig von der Controller-Suche lässt sich die LED direkt schalten:

```bash
cat /proc/led/status   # 0=AUS  1=BLAU  2=GELB  3=BEIDE  4=WECHSELND
                       # 99=DAUERHAFT AUS (zum Entsperren auf 0 setzen)
cat /proc/led/freq     # Blinkfrequenz in Mal pro Sekunde, 0 = kein Blinken
echo 0 > /proc/led/status
```

Die mFi-tools bringen dafür `client/led.cfg` mit (`afterboot`, `relay_on`,
`relay_off`) — die LED kann also dem Relaiszustand folgen.

### Neustart-Test: bestanden

Durch Aus- und Wiedereinstecken verifiziert — **alle Änderungen haben überlebt**:

| | Ergebnis |
|---|---|
| `cfg/mgmt` | Controller-Adressen weiterhin entfernt ✅ |
| `mqtt.cfg` | Broker und Zugangsdaten erhalten ✅ |
| LED | `freq=0`, kein Blinken ✅ |
| MQTT-Client | per `rc.poststart` selbstständig gestartet ✅ |
| Relais | alle drei kamen wieder **eingeschaltet** hoch |

Damit ist `cfgmtd -w -p /etc/` als Persistenzweg bestätigt.

**Wichtig für die Erwartungshaltung:** Der MQTT-Client braucht nach dem
Einschalten **rund vier Minuten**, bis er publiziert — trotz `sleep 10` in
`rc.poststart`. Der Rest der Zeit geht für den Bootvorgang und die
WLAN-Anmeldung drauf. Wer direkt nach dem Einstecken nachsieht, findet in Home
Assistant `$online = false` und eingefrorene Werte aus der letzten Sitzung
(retained). Das ist kein Fehler, sondern nur Geduldssache.

Ebenfalls beachten: Die Relais gehen nach Stromausfall **auf EIN**. Für
angeschlossene Geräte, die nicht selbsttätig wieder anlaufen sollen, ist das
relevant.

## Zwei MQTT-Wege

Nach dem Umbiegen laufen **zwei unabhängige** Wege auf denselben Broker. Sie
kollidieren nicht — verschiedene Topic-Bäume, verschiedene Zwecke.

| | Gerät (mFi-tools) | Bridge (`mqtt_bridge.py`) |
|---|---|---|
| Läuft auf | der Steckdose selbst | der Kali-Box |
| Topic | `mfi/mpower/…` | `mpower/mpower_10_10_1_78/…` |
| Konvention | Homie 2.1.0 | HA-Autodiscovery |
| Intervall | 60 s | 15 s |
| HA-Erkennung | manuell einrichten | **automatisch** |
| Energiezähler | **ja** (`energy`) | nein |
| Braucht Notebook | nein | ja |

Die gerätseitige Variante ist robuster (läuft auch ohne eingeschaltetes Notebook)
und liefert zusätzlich den Energiezähler. Die Bridge ist bequemer, weil Home
Assistant die Entitäten von selbst anlegt. Wer nur eine will: die gerätseitige
behalten und in HA manuell einbinden, oder die Bridge um `energy_sum` erweitern.

## Die HTTP-API

Alles hier wurde am Gerät nachgemessen, nicht aus Dokumentation übernommen —
eine offizielle Doku existiert nicht.

| Zweck | Aufruf |
|---|---|
| Session | `GET /` → Cookie `AIROS_SESSIONID` |
| Login | `POST /login.cgi` mit `username`, `password`, `uri` → 302 |
| Logout | `GET /logout.cgi` |
| Lesen | `GET /mfi/sensors.cgi` → JSON, alle Ports |
| Schalten | `PUT /sensors/<port>` mit `output=0\|1` |
| Schalten (alt.) | `POST /mfi/sensors.cgi` mit `id=<port>&output=0\|1` |

Antwort von `sensors.cgi`:

```json
{"sensors":[{"port":1,"id":"536fa6c3a0f781599afa565d","label":"Notebook",
  "model":"Outlet","output":1,"power":10.49,"enabled":1,"current":0.112,
  "voltage":230.85,"powerfactor":0.404,"relay":1,"lock":0,"thismonth":0}],
 "status":"success"}
```

`relay` ist der physische Relaiszustand, `output` der befohlene — im Normalbetrieb
identisch. Labels werden **mitgeliefert**, sofern am Gerät gesetzt.

### Fallstricke

Drei Dinge, die hier Zeit gekostet haben:

1. **`POST /mfi/sensors.cgi` erwartet den Port als `id`.** Schickt man ihn unter
   einem anderen Namen (etwa `port`), erkennt das Gerät keinen Zielport und wendet
   `output` auf **alle** Steckdosen an. So haben wir versehentlich die ganze Leiste
   abgeschaltet. `mpower.py` benutzt deshalb `PUT /sensors/<port>`, wo der Port im
   Pfad steht und nicht stillschweigend verlorengehen kann.
2. **`POST /mfi/sensors.cgi/<port>` liefert HTTP 200 und tut nichts.** Ein
   Erfolgsstatus beweist bei diesem Gerät gar nichts — nach jedem Schreibzugriff
   zurücklesen. `MPower.set()` macht das automatisch.
3. **Abgelaufene Sessions liefern HTML statt JSON**, nicht etwa 401. Der Client
   erkennt das am JSON-Parsefehler und meldet sich einmal neu an.

### Kein HTTPS

Die Firmware bringt OpenSSL 1.0.0g (2012) mit: nur TLSv1.0, selbstsigniertes
512-Bit-Zertifikat. Modernes Python/OpenSSL lehnt das ab. Genau daran ist auch die
`mfi`-Integration in Home Assistant gestorben. Also: **nur unverschlüsseltes HTTP
im vertrauenswürdigen LAN.**

## SSH als Rückfallebene

SSH funktioniert, braucht aber Legacy-Krypto — Dropbear 0.51 von 2008 kann nur
`diffie-hellman-group1-sha1`, `ssh-rsa` und `aes128-cbc`:

```bash
ssh -o KexAlgorithms=+diffie-hellman-group1-sha1 \
    -o HostKeyAlgorithms=+ssh-rsa \
    -o Ciphers=+aes128-cbc,3des-cbc \
    admin@10.10.1.78
```

Darüber liegt in `/proc/power/` je Port: `relayN` (schreibbar), `outputN`,
`active_pwrN`, `i_rmsN`, `v_rmsN`, `pfN`, `energy_sumN`, `cf_countN`, `lockN`,
`enabledN`, `meter_ic_verN`. Schalten geht direkt:

```bash
echo 0 > /proc/power/relay3
```

Statische Konfiguration (Labels, Board-Infos) liegt in `/etc/persistent/cfg/` und
ist nur über SSH erreichbar — Änderungen brauchen anschließend `save`.

## Alternative Firmware: nicht empfohlen

**Mainline-OpenWrt unterstützt die mPower-Serie nicht.** Im aktuellen Baum gibt es
keine Treffer für `mfi`/`mpower` unter `target/linux/ath79/`, kein passendes DTS
und keinen Eintrag in der Table of Hardware. Der
[archivierte OpenWrt-Thread](https://forum.archive.openwrt.org/viewtopic.php?id=71307)
enthält nur Reverse-Engineering-Notizen (Relais-Mux über zwei 74x138, SPI-Kommandos,
PL7223-Messchip) — kein lauffähiger Port, Energiemessung nie implementiert.

Da das Gerät keine herausgeführte serielle Konsole hat, wäre ein fehlgeschlagener
Flash-Versuch ein Totalverlust. Der übliche Weg der Community ist stattdessen:
Stock-Firmware behalten und eigene Skripte nach `/etc/persistent/` legen
(überlebt Neustarts via `save`).

## Verwandte Projekte

- [pasbec/mfi-mpower](https://github.com/pasbec/mfi-mpower) — die einzige aktiv
  gepflegte Library (Python, async). Ist in v2.0.0 bewusst von HTTP auf **reines
  SSH** umgestiegen.
- [pasbec/home-assistant-mfi-mpower](https://github.com/pasbec/home-assistant-mfi-mpower)
  — HA-Integration via HACS, aktiv gepflegt.
- [maletazul/mFi-tools](https://github.com/maletazul/mFi-tools) — MQTT-Bridge, läuft
  auf dem Gerät selbst.
- [chorankates/h4ck (ubiquiti/mfi)](https://github.com/chorankates/h4ck/tree/master/ubiquiti/mfi)
  — Reverse-Engineering-Notizen.
- [TinkerTry: Outlet-Namen ohne Controller setzen](https://tinkertry.com/how-to-configure-ubiquiti-mpower-pro-outlet-names-without-mfi-controller)

Die eingebaute HA-Integration `mfi` ist **unbrauchbar**: Sie spricht nicht mit der
Leiste, sondern mit der alten Controller-Software (Port 6080/6443), ist seit HA
2022.7 defekt, und
[Issue #120042](https://github.com/home-assistant/core/issues/120042) wurde als
"not planned" geschlossen.

Weitere Quellen und Recherchenotizen: [QUELLEN.md](QUELLEN.md).

## Lizenz

MIT — siehe [LICENSE](LICENSE). Die unter `backup-geraet/mqtt/` gesicherten
Dateien stammen aus der Gerätefirmware bzw. den
[mFi-tools](https://github.com/maletazul/mFi-tools) und stehen unter den
Bedingungen ihrer jeweiligen Urheber.
