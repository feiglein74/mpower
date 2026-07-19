# Offene Punkte

Was beim nächsten Mal drankommen könnte. Nichts davon ist nötig, damit das
Projekt funktioniert — es sind offene Fragen, keine Fehler.

---

## 1. Fehlerkurve verfeinern (optional)

Vier Referenzpunkte gegen die Janitza UMG 96RM stehen (siehe README) — von 8,8 %
bis 176 % Stromverzerrung, von 2 W bis 42 W, induktiv wie kapazitiv. Der mPower
bleibt überall innerhalb von 2 %.

Damit ist die Ausgangsfrage beantwortet. Was noch fehlen würde, wäre reine Kür:

- **Oberes Ende des Messbereichs** — bisher nur bis 42 W getestet, das Gerät ist
  für rund 2300 W ausgelegt. Ein Heizlüfter oder Wasserkocher würde zeigen, ob es
  auch dort linear bleibt.
- **Unteres Ende** — ab welcher Leistung wird die Anzeige unbrauchbar? Kleinster
  bisher belegter Wert: 2,9 W.

**Wichtig bei jeder Wiederholung:** Direktanschluss verwenden, keinen
Stromwandler. Warum, steht im README.

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
