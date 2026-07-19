# Offene Punkte

Was beim nächsten Mal drankommen könnte. Nichts davon ist nötig, damit das
Projekt funktioniert — es sind offene Fragen, keine Fehler.

---

## 1. Referenzmessung wiederholen — Aufbau prüfen

Ein erster Versuch mit einer **Janitza UMG 96RM** lieferte widersprüchliche
Ergebnisse und wurde verworfen (Begründung im README). Die Abweichung des mPower
kehrte zwischen zwei Lasten das Vorzeichen um, und beim GaN-Netzteil verletzte
die Referenzmessung die Energieerhaltung: 14,5 W Eingang bei 20 W Ausgang wären
138 % Wirkungsgrad.

### Vor einem neuen Versuch klären

- **Stromwandler-Verhältnis** — gemessen wurden 0,13 bis 0,22 A. Ist ein Wandler
  für etwa 100 A konfiguriert, liegt das bei 0,1 % des Nennstroms; die
  Klasse-0,2-Genauigkeit gilt dort nicht.
- **Polarität des Strompfads** — `cos φ` war negativ (−0,61) bei betragsmäßig
  stimmigem Wert. Deutet auf vertauschte k/l-Anschlüsse.
- **Direktanschluss statt Wandler** wäre bei diesen Strömen vermutlich nötig.

Als Plausibilitätsprüfung eignet sich der **Wirkungsgrad**: Ein Netzteil kann
nicht mehr abgeben als es aufnimmt. Das hat den Fehler hier aufgedeckt.

### Messpunkte, sobald der Aufbau stimmt

| Last | erwarteter THD-I | Zweck |
|---|---|---|
| Glühlampe (mehrere Wattagen) | ~0 % | Linearität über die Leistung |
| Trafo-Netzteil, verschiedene Lasten | 20–77 % | Verlauf über den THD |
| GaN-/Schaltnetzteil | ~50 % | zweite verzerrte Lastart |
| Schaltnetzteil **mit** PFC | niedrig | trennt Verzerrung von Leistungshöhe |

Je Punkt zu erfassen: **P, I, cos φ, PF und THD-I** von der Referenz, dazu die
mPower-Werte. Ziel ist eine Fehlerkurve über dem THD — für dieses Gerät gibt es
bislang keine einzige veröffentlichte Genauigkeitsangabe.

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
