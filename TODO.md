# Offene Punkte

Was beim nächsten Mal drankommen könnte. Nichts davon ist nötig, damit das
Projekt funktioniert — es sind offene Fragen, keine Fehler.

---

## 1. Referenzmessung mit der Janitza

**Das lohnendste Vorhaben.** Für den mFi mPower existiert *keine einzige*
veröffentlichte Genauigkeitsangabe: Das PL7223-Datenblatt steht unter NDA, die
Produktbroschüre nennt keine Toleranz, und Ubiquitis mFi-Datenblatt führt
„Energy Monitoring" nur als Feature. Eine gegen ein Klasse-0,2-Gerät
referenzierte Messung wäre die erste belastbare Zahl zu diesem Gerät überhaupt.

### Was bisher offen ist

Der Quervergleich mit einem Shelly 4PM ergab (siehe README):

| Last | mPower | Shelly | Differenz |
|---|---|---|---|
| Trafo-Labornetzteil, Leerlauf | 14,30 W | 15,70 W | −8,9 % |
| Trafo-Labornetzteil, 1 A / 12 V | 33,28 W | 34,90 W | −4,6 % |
| Glühlampe 40 W (ohmsch) | 39,62 W | — | −1,5 % gegen Nennwert |

Bei ohmscher Last stimmen beide fast überein, bei verzerrten Lasten läuft es
auseinander. Vermutung: Die Messchips rechnen **Oberwellen unterschiedlich in
die Wirkleistung** ein. Ohne Referenzgerät ist nicht entscheidbar, welches näher
an der Wahrheit liegt.

### Messplan

Janitza in Reihe, mPower und Shelly parallel dazu ablesen.

| | |
|---|---|
| **Lasten** | Glühlampe (ohmsch, PF ≈ 1) · Trafo-Netzteil leer · Trafo-Netzteil belastet · ein Schaltnetzteil (stark verzerrt) |
| **Größen** | Wirkleistung · Effektivstrom · **THD des Stroms** · echter PF (`P/S`) **und** cos φ getrennt |

Der THD ist der eigentliche Erkenntnisgewinn: Damit lässt sich vorhersagen, wie
weit zwei Messgeräte auseinanderliegen *müssen*, je nachdem bis zur wievielten
Harmonischen sie rechnen. Das beantwortet das „warum", nicht nur das „wer".

Wichtig: `cos φ` und `P/S` **getrennt** erfassen. Der mPower meldet den echten
Leistungsfaktor, der Shelly offenbar den Verschiebungsfaktor — das hat beim
letzten Mal für scheinbare Widersprüche gesorgt (siehe README).

---

## 2. Kleinere offene Fragen

### `ntpclient` startet ~93× pro Stunde neu

Gemessen: 15 Neustarts in 9 min 43 s, in Bündeln von zwei bis drei alle rund
2,5 Minuten. **Ursache unbekannt.** Zwei Hypothesen sind bereits widerlegt:

- *Wechselnde Pool-Adressen* — nein: Bei einem nicht antwortenden Server bleibt
  `ntpclient` hängen, statt sich zu beenden.
- *Internetlatenz* — nein: Die Umstellung auf einen lokalen chrony (5 ms statt
  Internet) änderte die Rate nicht (~100/h).

Nächster Ansatz wäre die Aufrufweise `-c 0 -l` aus der inittab-Zeile. Die Uhr
läuft sekundengenau, es ist also rein kosmetisch.

### Empfindlichkeitsgrenze bei kleinen Lasten

Nicht ermittelt. Belegt ist nur, dass 2,9 W sauber gemeldet werden. Offen: Ab
welcher Leistung meldet das Gerät null? Interessant für Standby-Verbraucher.
Messbar mit einer regelbaren Last oder mehreren kleinen Verbrauchern.

### Energie-Auflösung über MQTT erhöhen

`mqpub.sh` rundet den Energiezähler auf ganze Wattstunden (`printf "%.0f"`),
obwohl der Chip 0,3125 Wh je Impuls auflöst. Ein 5-W-Verbraucher braucht dadurch
12 Minuten je Zählschritt. Änderung wäre einzeilig (`%.1f`), **aber**: Ob sie
einen Neustart übersteht, ist offen — `vpower_cfg` wird von der Firmware
ebenfalls zurückgesetzt, trotz `cfgmtd`.

### Log-Spam von `mcad`

Rund 40 Einträge pro Stunde, weil `mcad` weiterhin den fest einkompilierten
Namen `mfi` sucht. Harmlos, das Log rotiert bei 200 KB. Ein Eintrag `mfi` →
`127.0.0.1` in `/etc/hosts` würde die Versuche sofort scheitern lassen statt
über die Namensauflösung. Ungetestet, und die Persistenz von `/etc/hosts` wäre
zu prüfen.

---

## 3. Bewusst nicht verfolgt

**Alternative Firmware.** Mainline-OpenWrt unterstützt die mPower-Serie nicht —
keine Treffer im `ath79`-Baum, kein DTS, kein ToH-Eintrag. Der archivierte
Forenthread enthält nur Reverse-Engineering-Notizen ohne lauffähigen Port. Ohne
herausgeführte serielle Konsole wäre ein Fehlversuch ein Totalverlust.
Begründung im README.
