# Offene Punkte

Was beim nächsten Mal drankommen könnte. Nichts davon ist nötig, damit das
Projekt funktioniert — es sind offene Fragen, keine Fehler.

---

## 1. Fehlerkurve über Leistung und THD

Der erste Messpunkt gegen die Janitza UMG 96RM steht (siehe README): Bei einem
Trafo-Netzteil im Leerlauf mit 77,4 % Stromverzerrung liest der mPower **20,7 %
zu niedrig**, bei einer ohmschen Glühlampe dagegen nur 1,5 %. Die Genauigkeit
hängt also stark an der Lastart.

Was fehlt, ist die Kurve dazwischen. Ein Messpunkt bei einer Lastart erlaubt
keine Aussage darüber, ab welchem Verzerrungsgrad es kritisch wird.

### Sinnvolle Messpunkte

| Last | erwarteter THD | Zweck |
|---|---|---|
| Glühlampe (mehrere Wattagen) | ~0 % | Linearität über die Leistung |
| Trafo-Netzteil, verschiedene Lasten | 20–77 % | Verlauf über den THD |
| Schaltnetzteil ohne PFC | hoch | zweite verzerrte Lastart |
| Schaltnetzteil **mit** PFC | niedrig | trennt Verzerrung von Leistungshöhe |

Je Punkt zu erfassen: **P, I, cos φ, PF und THD-I** von der Janitza, dazu die
mPower-Werte. Daraus ließe sich eine Fehlerkurve über dem THD zeichnen — und die
wäre für dieses Gerät wirklich neu.

### Offene Frage aus der ersten Messung

Der mPower liest den **Strom zu hoch** (+14,9 %) und die **Leistung zu niedrig**
(−20,7 %). Warum in beide Richtungen, ist unklar. Eine Erklärung bräuchte
Kenntnis darüber, bis zur wievielten Harmonischen der PL7223 rechnet — steht im
Datenblatt unter NDA.

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
