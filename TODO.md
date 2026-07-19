# Offene Punkte

Was beim nächsten Mal drankommen könnte. Nichts davon ist nötig, damit das
Projekt funktioniert — es sind offene Fragen, keine Fehler.

---

## 1. Fehlerkurve über mehrere Lastarten

Der erste belastbare Messpunkt gegen die Janitza UMG 96RM steht (siehe README):
Bei einem GaN-Netzteil mit 47 % Stromverzerrung liegt der mPower **innerhalb von
2 %**. Was fehlt, ist der Verlauf über verschiedene Lastarten und Verzerrungsgrade.

**Wichtig:** Direktanschluss verwenden, keinen Wandler. Der vorhandene 30/5-A-Typ
ist für diese Ströme unbrauchbar — Details im README.

### Offene Messpunkte

| Last | erwarteter THD-I | Zweck |
|---|---|---|
| Glühlampe (mehrere Wattagen) | ~0 % | Linearität über die Leistung |
| Trafo-Netzteil, Leerlauf | ~77 % | der Extremfall — **Wiederholung nötig**, die erste Messung war mit dem untauglichen Wandler |
| Trafo-Netzteil, belastet | 20–50 % | Verlauf über den THD |
| größere ohmsche Last (1–2 kW) | ~0 % | Verhalten am oberen Ende des Messbereichs |

Je Punkt zu erfassen: **P, I, cos φ, S und THD-I** von der Janitza, dazu die
mPower-Werte. Ziel ist eine Fehlerkurve über dem THD.

### Plausibilitätsprüfungen nicht vergessen

- **Wirkungsgrad** — ein Netzteil kann nicht mehr abgeben als es aufnimmt. Daran
  ist der fehlerhafte Aufbau aufgefallen.
- **`cos φ` positiv?** Negatives Vorzeichen deutet auf vertauschte S1/S2.
- **`PF = cos φ / √(1+THD²)`** — geht das auf, ist die Referenz in sich stimmig.

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
