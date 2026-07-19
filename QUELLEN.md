# UniFi mFi mPower — Custom Firmware & Reverse Engineering

Recherche-Notizen zur Ubiquiti mFi mPower (3-fach-Steckdose) und was die Community
bereits an Zerlegung, Root-Zugang und alternativer Firmware gemacht hat.

Stand: 2026-07-19

---

## Kurz-Einordnung

- Die „3-fach"-Steckdose ist die **mFi mPower** (3 Ausgänge). Daneben gibt es
  **mPower mini** (1 Ausgang) und **mPower Pro** (6/8 Ausgänge).
- Alle laufen auf einem Atheros-SoC mit einem OpenWrt-ähnlichen Linux **ab Werk**.
  (Am eigenen Gerät nachgemessen: **AR9330 „Hornet"**, nicht AR9331 — die beiden
  sind nah verwandt, aber `/proc/cpuinfo` sagt eindeutig AR9330.)
- Ubiquiti mFi ist EOL. Cloud-/Controller-Support bröckelt, aber die Hardware läuft
  lokal per SSH weiter.

## Wichtigste Erkenntnisse

- **Root-Zugang out of the box.** SSH direkt aufs Gerät (Standard `ubnt`/`ubnt`),
  ohne Flashen.
- **Steuerung über sysfs / proc.** Relais schalten z. B. mit
  `echo 1 > /proc/power/relay1`. Unter `/proc/power/` liegen auch Messwerte
  (Volt / Ampere / Watt).
- **Fertige Tools statt kompletter Neu-Firmware.** Python-Lib, MQTT-Bridge,
  Home-Assistant-Anbindung, diverse Skript-Sammlungen → Gerät läuft rein lokal.
- **Vollständiges Mainline-OpenWrt: eher nicht.** Alte Foren-Wünsche existieren,
  aber die mPower-Serie ist nie sauber in mainline OpenWrt gelandet. Gängige Praxis:
  Stock-Linux behalten + Autostart-Skript, kein Flashen nötig.

---

## Quellen

### Custom Code / Reverse Engineering

- **shmuelie/mfi-custom-code** — Custom-Code für Ubiquiti mFi-Geräte
  https://github.com/shmuelie/mfi-custom-code

- **chorankates/h4ck — ubiquiti/mfi** — Reverse-Engineering-Notizen
  https://github.com/chorankates/h4ck/tree/master/ubiquiti/mfi
  (README: https://github.com/chorankates/h4ck/blob/master/ubiquiti/mfi/README.md)

### Steuerung / Tools / Libraries

- **mfi-mpower (PyPI)** — Python-Lib zum Steuern ohne Controller
  https://pypi.org/project/mfi-mpower/

- **maletazul/mFi-tools** — mFi-Geräte via MQTT betreiben
  https://github.com/maletazul/mFi-tools

- **Home Automation: Ubiquiti mFi** — HA-Integrationsnotizen
  https://ha.ivanfm.com/hardware/ubiquiti-mfi.html

### Community / Firmware-Diskussion

- **Alternative Firmware for mPower** (UI Community)
  https://community.ui.com/questions/Alternative-Firmware-for-Mpower/9bf56c81-3c8c-4425-acb5-4bfbd4dc0fde

- **Open source OpenWRT firmware for mFi mPower series** (UI Community)
  https://community.ui.com/questions/Open-source-OpenWRT-firmware-for-mFi-mPower-series-Updates/3b5ecdcb-ce9c-4d42-b125-11960110d8f8

### HowTos / Hintergrund

- **HowTo: Ubiquiti mFi mPower** (LinITX Blog)
  https://blog.linitx.com/ubiquiti-mfi-mpower/

- **How to configure Ubiquiti mPower PRO outlet names without an mFi controller** (TinkerTry)
  https://tinkertry.com/how-to-configure-ubiquiti-mpower-pro-outlet-names-without-mfi-controller

- **mFi mPower US — Quick Start Guide (PDF)**
  https://dl.ubnt.com/guides/mfi/mFi_mPower_US_QSG.pdf

---

## Stand der offenen Fragen

Alle Punkte dieser Notizen sind inzwischen am realen Gerät geklärt. Die
Ergebnisse stehen ausführlich in [README.md](README.md).

- [x] **Genaues Modell** — mFi mPower EU, 3 Ausgänge, Firmware `MF.v2.1.8`,
      AR9330, 32 MB RAM, 8 MB Flash (rootfs zu 100 % belegt).
- [x] **Ziel festgelegt** — lokal ohne Cloud, angebunden an Home Assistant über
      MQTT. Kein eigenes Firmware-Image.
- [x] **SSH-Zugang und `/proc/power/`** — funktioniert, braucht aber Legacy-Krypto
      (Dropbear 0.51: nur `diffie-hellman-group1-sha1`, `ssh-rsa`, `aes128-cbc`).
      Benutzer ist `admin`, nicht `ubnt`. Layout verifiziert.
- [x] **Autostart statt Flashen** — bestätigt als richtiger Weg. Mainline-OpenWrt
      unterstützt die mPower-Serie nicht (keine Treffer im `ath79`-Baum, kein DTS,
      kein ToH-Eintrag). Ohne serielle Konsole wäre ein Fehlversuch endgültig.

### Zusätzlich herausgefunden

- Die **HTTP-API** kann alles außer dem Energiezähler und ist die bequemere Basis
  als SSH. Geschaltet wird über `PUT /sensors/<port>`.
- Auf dem Gerät waren die **mFi-tools bereits installiert** und publizierten an
  einen längst abgeschalteten Broker. Umbiegen genügte — sie können schalten,
  melden und zählen, ganz ohne fremden Rechner.
- Das **LED-Blinken** war die Suche nach dem verschwundenen mFi-Controller. Nach
  Entfernen der toten Adressen aus `cfg/mgmt` hört es auf.