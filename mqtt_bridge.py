#!/usr/bin/env python3
"""
MQTT-Bridge fuer die Ubiquiti mFi mPower, mit Home-Assistant-Autodiscovery.

Pollt die Leiste ueber ihre lokale HTTP-API und spiegelt den Zustand nach MQTT.
Home Assistant legt die Steckdosen dadurch von selbst als Schalter samt
Leistungs-, Strom- und Spannungssensoren an -- in HA ist keine Konfiguration
noetig, solange dort dieselbe MQTT-Integration aktiv ist.

Topics (Praefix konfigurierbar, Vorgabe "mpower"):

    mpower/<geraet>/availability          online | offline  (LWT)
    mpower/<geraet>/port<N>/state         ON | OFF
    mpower/<geraet>/port<N>/set           ON | OFF   <- Kommandos hierher
    mpower/<geraet>/port<N>/power         Watt
    mpower/<geraet>/port<N>/current       Ampere
    mpower/<geraet>/port<N>/voltage       Volt

Aufruf:  ./mqtt_bridge.py [--interval 15] [--once] [--no-discovery]
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import signal
import sys
import time
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("Fehlt: paho-mqtt  ->  pip install paho-mqtt")

from mpower import CONFIG_PATH, MPower, MPowerError, Outlet, load_config

DISCOVERY_PREFIX = "homeassistant"

# Vorsichtig gewaehlt: das Geraet ist ein 2015er MIPS-SoC mit 32 MB RAM. Ob
# schnelles Polling es tatsaechlich stoert, ist nicht belegt -- aber die
# gepflegten Fremdprojekte fahren durchweg traege (MQTT-Tools: 60 s).
DEFAULT_INTERVAL = 15.0


def load_mqtt_config() -> dict:
    """MQTT-Zugangsdaten aus Konfigdatei und Umgebung lesen."""
    cfg = {
        "host": "10.0.0.171",
        "port": "1883",
        "user": "",
        "password": "",
        "prefix": "mpower",
        "discovery": "yes",
        # Topic-Baum der geraeteseitigen mFi-tools (Homie 2.1.0). Liefert den
        # Energiezaehler, den die HTTP-API nicht hergibt.
        "device_topic": "mfi/mpower",
    }
    if CONFIG_PATH.exists():
        parser = configparser.ConfigParser()
        parser.read(CONFIG_PATH)
        if parser.has_section("mqtt"):
            cfg.update({k: v for k, v in parser["mqtt"].items() if k in cfg})
    for key, env in (
        ("host", "MQTT_HOST"), ("port", "MQTT_PORT"), ("user", "MQTT_USER"),
        ("password", "MQTT_PW"), ("prefix", "MQTT_PREFIX"),
    ):
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


class Bridge:
    def __init__(self, mp: MPower, mqtt_cfg: dict, interval: float = DEFAULT_INTERVAL,
                 discovery: bool = True, device_topic: str = "", source: str = "bridge"):
        self.mp = mp
        self.cfg = mqtt_cfg
        self.interval = interval
        self.discovery = discovery
        # Topic-Baum der geraeteseitigen mFi-tools; leer = kein Energiesensor.
        self.device_topic = device_topic.rstrip("/")
        # "bridge": HA liest von dieser Bridge (schneller, mit Strom-Sensor).
        # "device": HA redet direkt mit dem Geraet (laeuft auch ohne Notebook).
        self.source = source
        self.running = True

        # Stabile Geraetekennung aus der IP -- ueberlebt Neustarts und
        # Label-Aenderungen, anders als die Sensor-IDs der Firmware.
        self.node = "mpower_" + mp.host.replace(".", "_")
        self.prefix = f"{mqtt_cfg['prefix']}/{self.node}"
        self.avail_topic = f"{self.prefix}/availability"

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id=f"{self.node}_bridge")
        if mqtt_cfg.get("user"):
            self.client.username_pw_set(mqtt_cfg["user"], mqtt_cfg["password"])
        self.client.will_set(self.avail_topic, "offline", retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self._last: dict[int, str] = {}
        self.connected = False
        self.connect_error: str | None = None

    # -- MQTT-Callbacks ---------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            self.connect_error = str(rc)
            return
        self.connected = True
        self.connect_error = None
        print(f"MQTT verbunden mit {self.cfg['host']}:{self.cfg['port']}")
        client.publish(self.avail_topic, "online", retain=True)
        for port in (1, 2, 3):
            client.subscribe(f"{self.prefix}/port{port}/set")

    def _on_message(self, client, userdata, msg):
        try:
            port = int(msg.topic.rsplit("/", 2)[-2].removeprefix("port"))
        except (ValueError, IndexError):
            return
        payload = msg.payload.decode(errors="replace").strip().upper()
        if payload not in ("ON", "OFF"):
            print(f"Unbekanntes Kommando auf {msg.topic}: {payload!r}", file=sys.stderr)
            return
        print(f"Kommando: Port {port} -> {payload}")
        try:
            outlet = self.mp.set(port, payload == "ON")
            self._publish_outlet(outlet)
        except MPowerError as exc:
            print(f"Schalten fehlgeschlagen: {exc}", file=sys.stderr)

    # -- Home-Assistant-Autodiscovery -------------------------------------

    def _device_block(self) -> dict:
        return {
            "identifiers": [self.node],
            "name": f"mFi mPower ({self.mp.host})",
            "manufacturer": "Ubiquiti",
            "model": "mFi mPower EU (3 Ports)",
            "sw_version": "MF.v2.1.8",
            "configuration_url": f"http://{self.mp.host}/",
        }

    def publish_discovery(self, outlets: list[Outlet]) -> None:
        """Entitaeten bei Home Assistant anmelden (retained).

        Im Modus "device" zeigen Zustands- und Kommandotopics direkt auf die
        geraeteseitigen mFi-tools. Home Assistant redet dann unmittelbar mit der
        Steckdose, und diese Bridge wird nach dem Anmelden nicht mehr gebraucht.
        """
        dev = self._device_block()
        device_mode = self.source == "device"

        for o in outlets:
            base = f"{self.prefix}/port{o.port}"
            dbase = f"{self.device_topic}/port{o.port}"
            uid = f"{self.node}_port{o.port}"

            if device_mode:
                switch = {
                    "state_topic": f"{dbase}/relay",
                    "command_topic": f"{dbase}/relay/set",
                    "payload_on": "1",
                    "payload_off": "0",
                    "availability_topic": f"{self.device_topic}/$online",
                    "payload_available": "true",
                    "payload_not_available": "false",
                }
            else:
                switch = {
                    "state_topic": f"{base}/state",
                    "command_topic": f"{base}/set",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "availability_topic": self.avail_topic,
                }

            self.client.publish(
                f"{DISCOVERY_PREFIX}/switch/{self.node}/port{o.port}/config",
                json.dumps({
                    "name": o.name,
                    "unique_id": uid,
                    "device": dev,
                    "icon": "mdi:power-socket-de",
                    **switch,
                }), retain=True)

            # Energiezaehler: Den liefert die HTTP-API nicht
            # (/sensors/N/energy_sum -> "not a valid resource"). Statt ihn per
            # SSH nachzuladen, zeigen wir Home Assistant direkt auf das Topic,
            # das die geraeteseitigen mFi-tools ohnehin schon publizieren --
            # retained, alle 60 s, ohne Zusatzlast. Die Verfuegbarkeit haengt
            # deshalb am Geraet, nicht an dieser Bridge.
            if self.device_topic:
                self.client.publish(
                    f"{DISCOVERY_PREFIX}/sensor/{self.node}/port{o.port}_energy/config",
                    json.dumps({
                        "name": f"{o.name} Energie",
                        "unique_id": f"{uid}_energy",
                        "state_topic": f"{self.device_topic}/port{o.port}/energy",
                        "unit_of_measurement": "Wh",
                        "device_class": "energy",
                        "state_class": "total_increasing",
                        "availability_topic": f"{self.device_topic}/$online",
                        "payload_available": "true",
                        "payload_not_available": "false",
                        "device": dev,
                    }), retain=True)

            for key, label, unit, dclass in (
                ("power", "Leistung", "W", "power"),
                ("current", "Strom", "A", "current"),
                ("voltage", "Spannung", "V", "voltage"),
            ):
                if device_mode:
                    # Die mFi-tools publizieren relay, energy, power, voltage
                    # und lock -- aber keinen Strom. Im Geraete-Modus entfaellt
                    # dieser Sensor, statt eine tote Entitaet anzulegen.
                    if key == "current":
                        self.client.publish(
                            f"{DISCOVERY_PREFIX}/sensor/{self.node}/port{o.port}_current/config",
                            "", retain=True)  # vorhandene Entitaet entfernen
                        continue
                    src = {
                        "state_topic": f"{dbase}/{key}",
                        "availability_topic": f"{self.device_topic}/$online",
                        "payload_available": "true",
                        "payload_not_available": "false",
                    }
                else:
                    src = {
                        "state_topic": f"{base}/{key}",
                        "availability_topic": self.avail_topic,
                    }

                self.client.publish(
                    f"{DISCOVERY_PREFIX}/sensor/{self.node}/port{o.port}_{key}/config",
                    json.dumps({
                        "name": f"{o.name} {label}",
                        "unique_id": f"{uid}_{key}",
                        "unit_of_measurement": unit,
                        "device_class": dclass,
                        "state_class": "measurement",
                        "device": dev,
                        **src,
                    }), retain=True)

        quelle = "Gerät (mFi-tools)" if device_mode else "Bridge"
        print(f"Autodiscovery fuer {len(outlets)} Ports veroeffentlicht — Datenquelle: {quelle}")

    # -- Zustand spiegeln --------------------------------------------------

    def _publish_outlet(self, o: Outlet) -> None:
        base = f"{self.prefix}/port{o.port}"
        state = "ON" if o.on else "OFF"
        self.client.publish(f"{base}/state", state, retain=True)
        self.client.publish(f"{base}/power", f"{o.power:.2f}")
        self.client.publish(f"{base}/current", f"{o.current:.3f}")
        self.client.publish(f"{base}/voltage", f"{o.voltage:.1f}")
        if self._last.get(o.port) != state:
            print(f"Port {o.port} ({o.name}): {state}  {o.power:.2f} W")
            self._last[o.port] = state

    def poll_once(self) -> bool:
        try:
            outlets = self.mp.outlets()
        except MPowerError as exc:
            print(f"Abfrage fehlgeschlagen: {exc}", file=sys.stderr)
            self.client.publish(self.avail_topic, "offline", retain=True)
            return False
        self.client.publish(self.avail_topic, "online", retain=True)
        for o in outlets:
            self._publish_outlet(o)
        return True

    # -- Hauptschleife -----------------------------------------------------

    def stop(self, *_):
        self.running = False

    def run(self, once: bool = False) -> int:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        try:
            self.client.connect(self.cfg["host"], int(self.cfg["port"]), keepalive=60)
        except Exception as exc:
            print(f"MQTT-Verbindung zu {self.cfg['host']} fehlgeschlagen: {exc}", file=sys.stderr)
            return 1
        self.client.loop_start()

        # Auf die Broker-Antwort warten. Ohne diesen Riegel wuerde die Bridge
        # bei falschen Zugangsdaten munter weiterlaufen und Nachrichten ins
        # Leere schreiben -- sieht nach Betrieb aus, ist aber keiner.
        for _ in range(50):
            if self.connected or self.connect_error:
                break
            time.sleep(0.1)
        if not self.connected:
            reason = self.connect_error or "keine Antwort vom Broker"
            print(f"MQTT-Anmeldung fehlgeschlagen: {reason}", file=sys.stderr)
            if "not authorized" in reason.lower():
                print("  -> Benutzer/Passwort pruefen (Abschnitt [mqtt] in "
                      f"{CONFIG_PATH} oder MQTT_USER/MQTT_PW)", file=sys.stderr)
            self.client.loop_stop()
            self.client.disconnect()
            return 1

        if self.discovery:
            try:
                self.publish_discovery(self.mp.outlets())
            except MPowerError as exc:
                print(f"Autodiscovery uebersprungen: {exc}", file=sys.stderr)

        try:
            while self.running:
                self.poll_once()
                if once:
                    break
                # In kleinen Schritten schlafen, damit Strg-C sofort wirkt.
                for _ in range(int(self.interval * 10)):
                    if not self.running:
                        break
                    time.sleep(0.1)
        finally:
            self.client.publish(self.avail_topic, "offline", retain=True)
            time.sleep(0.3)
            self.client.loop_stop()
            self.client.disconnect()
            print("Bridge beendet")
        return 0


def main(argv: list[str] | None = None) -> int:
    dev = load_config()
    mq = load_mqtt_config()

    p = argparse.ArgumentParser(description="mFi mPower <-> MQTT (mit HA-Autodiscovery)")
    p.add_argument("--host", default=dev["host"], help="IP der Steckdosenleiste")
    p.add_argument("--broker", default=mq["host"], help="MQTT-Broker")
    p.add_argument("--broker-port", type=int, default=int(mq["port"]))
    p.add_argument("--mqtt-user", default=mq["user"])
    p.add_argument("--mqtt-password", default=mq["password"])
    p.add_argument("--prefix", default=mq["prefix"], help="Topic-Praefix")
    p.add_argument("-n", "--interval", type=float, default=DEFAULT_INTERVAL,
                   help=f"Abfrageintervall in Sekunden (Vorgabe: {DEFAULT_INTERVAL:g})")
    p.add_argument("--once", action="store_true", help="einmal abfragen und beenden")
    p.add_argument("--no-discovery", action="store_true",
                   help="keine HA-Discovery-Nachrichten senden")
    p.add_argument("--device-topic", default=mq["device_topic"],
                   help="Topic-Baum der geraeteseitigen mFi-tools, liefert den "
                        "Energiezaehler (leer = kein Energiesensor)")
    p.add_argument("--source", choices=("bridge", "device"), default="bridge",
                   help="Woher Home Assistant die Daten liest. 'bridge': schneller "
                        "und mit Strom-Sensor, braucht aber diesen laufenden Dienst. "
                        "'device': HA redet direkt mit der Steckdose, laeuft auch "
                        "ohne diesen Rechner -- dann genuegt ein Aufruf mit --once.")
    args = p.parse_args(argv)

    mp = MPower(host=args.host, user=dev["user"], password=dev["password"])
    cfg = {
        "host": args.broker, "port": str(args.broker_port),
        "user": args.mqtt_user, "password": args.mqtt_password,
        "prefix": args.prefix,
    }
    bridge = Bridge(mp, cfg, interval=args.interval, discovery=not args.no_discovery,
                    device_topic=args.device_topic, source=args.source)
    if args.source == "device" and not args.once:
        print("Hinweis: Im Geraete-Modus liest Home Assistant direkt vom Geraet. "
              "Ein Dauerlauf dieser Bridge ist dafuer nicht noetig (--once genuegt).")
    return bridge.run(once=args.once)


if __name__ == "__main__":
    sys.exit(main())
