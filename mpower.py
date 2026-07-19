#!/usr/bin/env python3
"""
Lokaler Client fuer die Ubiquiti mFi mPower Steckdosenleiste.

Die mFi-Plattform wird von Ubiquiti nicht mehr gepflegt (Cloud/Controller tot),
das Geraet selbst spricht aber weiterhin eine vollstaendige lokale HTTP-API.
Dieses Modul kapselt sie -- ohne Cloud, ohne Controller, ohne SSH.

Getestet gegen: Firmware MF.v2.1.8, mPower EU 3-fach (AR9330, Linux 2.6.32).

API-Eigenheiten (empirisch am Geraet verifiziert):
  * Login: GET / holt das Session-Cookie, dann POST /login.cgi. Der Client darf
    die AIROS_SESSIONID auch selbst wuerfeln, das Geraet uebernimmt sie.
  * Lesen: GET /mfi/sensors.cgi liefert alle Ports als JSON, inklusive Label.
  * Schalten, zwei gleichwertige Wege:
      PUT  /sensors/<port>     mit output=0|1
      POST /mfi/sensors.cgi    mit id=<port>&output=0|1
  * GEFAHR: Bei POST /mfi/sensors.cgi heisst das Feld "id". Wird der Port unter
    einem unbekannten Namen (etwa "port") geschickt, adressiert das Geraet
    keinen Port und wendet output auf ALLE Steckdosen an. Hier wird deshalb
    ausschliesslich PUT /sensors/<port> benutzt -- der Port steht im Pfad und
    kann nicht stillschweigend verlorengehen.
  * Stille Falle: POST /mfi/sensors.cgi/<port> liefert HTTP 200 und tut nichts.
  * Kein HTTPS: Die Firmware kann nur TLSv1.0 mit 512-Bit-Zertifikat. Moderne
    Python-/OpenSSL-Versionen lehnen das ab -> nur im vertrauenswuerdigen LAN.
"""

from __future__ import annotations

import argparse
import configparser
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "10.10.1.78"
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "ubnt"
CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "mpower" / "config.ini"


class MPowerError(RuntimeError):
    """Fehler bei der Kommunikation mit dem Geraet."""


@dataclass
class Outlet:
    """Zustand einer einzelnen Steckdose."""

    port: int
    relay: int
    output: int
    power: float
    current: float
    voltage: float
    powerfactor: float
    label: str = ""
    lock: int = 0
    enabled: int = 0

    @property
    def on(self) -> bool:
        return bool(self.output)

    @property
    def name(self) -> str:
        return self.label or f"Port {self.port}"

    @classmethod
    def from_json(cls, d: dict) -> "Outlet":
        return cls(
            port=int(d["port"]),
            relay=int(d.get("relay", 0)),
            output=int(d.get("output", 0)),
            power=float(d.get("power", 0.0)),
            current=float(d.get("current", 0.0)),
            voltage=float(d.get("voltage", 0.0)),
            powerfactor=float(d.get("powerfactor", 0.0)),
            label=str(d.get("label", "") or ""),
            lock=int(d.get("lock", 0)),
            enabled=int(d.get("enabled", 0)),
        )


class _Request(urllib.request.Request):
    """urllib.Request mit frei waehlbarer HTTP-Methode (fuer PUT)."""

    def __init__(self, *args, method: str = "GET", **kwargs):
        super().__init__(*args, **kwargs)
        self._method = method

    def get_method(self) -> str:  # noqa: D102
        return self._method


class MPower:
    """Verbindung zu einer mFi mPower Leiste.

    Die Session wird bei Bedarf automatisch (neu) aufgebaut -- das Geraet
    wirft Sessions nach einiger Zeit weg und antwortet dann mit einem
    Redirect auf die Loginseite statt mit JSON.
    """

    def __init__(self, host: str = DEFAULT_HOST, user: str = DEFAULT_USER,
                 password: str = DEFAULT_PASSWORD, timeout: float = 10.0):
        self.host = host
        self.user = user
        self.password = password
        self.timeout = timeout
        self.base = f"http://{host}"
        self._opener: urllib.request.OpenerDirector | None = None

    # -- Session ----------------------------------------------------------

    def _login(self) -> urllib.request.OpenerDirector:
        cj = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        try:
            # Schritt 1: Session-Cookie (AIROS_SESSIONID) abholen.
            opener.open(self.base + "/", timeout=self.timeout)
            # Schritt 2: Anmelden. Antwortet mit 302 -- das ist der Normalfall.
            body = urllib.parse.urlencode({
                "username": self.user,
                "password": self.password,
                "uri": "/",
            }).encode()
            opener.open(self.base + "/login.cgi", body, timeout=self.timeout)
        except urllib.error.URLError as exc:
            raise MPowerError(f"Verbindung zu {self.host} fehlgeschlagen: {exc.reason}") from exc
        return opener

    def _ensure(self) -> urllib.request.OpenerDirector:
        if self._opener is None:
            self._opener = self._login()
        return self._opener

    # -- Lesen ------------------------------------------------------------

    def outlets(self) -> list[Outlet]:
        """Zustand aller Steckdosen lesen."""
        raw = self._get_sensors()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # Kein JSON == Session abgelaufen, Geraet liefert die Loginseite.
            self._opener = None
            payload = json.loads(self._get_sensors())
        if payload.get("status") != "success":
            raise MPowerError(f"Geraet meldete Status {payload.get('status')!r}")
        return [Outlet.from_json(s) for s in payload["sensors"]]

    def _get_sensors(self) -> str:
        opener = self._ensure()
        try:
            return opener.open(self.base + "/mfi/sensors.cgi", timeout=self.timeout).read().decode()
        except urllib.error.URLError as exc:
            raise MPowerError(f"Lesen fehlgeschlagen: {exc}") from exc

    def outlet(self, port: int) -> Outlet:
        """Zustand einer einzelnen Steckdose lesen."""
        for o in self.outlets():
            if o.port == port:
                return o
        raise MPowerError(f"Port {port} existiert nicht (verfuegbar: 1-3)")

    # -- Schalten ---------------------------------------------------------

    def set(self, port: int, on: bool, verify: bool = True) -> Outlet:
        """Eine einzelne Steckdose schalten.

        Nutzt bewusst PUT /sensors/<port>: das ist der einzige Endpoint, der
        portweise schaltet. Mit verify=True wird der Zustand danach
        zurueckgelesen -- das Geraet quittiert Schreibzugriffe nicht
        zuverlaessig, ein HTTP 200 allein beweist gar nichts.
        """
        if port not in (1, 2, 3):
            raise MPowerError(f"Ungueltiger Port {port} (erlaubt: 1-3)")

        opener = self._ensure()
        body = urllib.parse.urlencode({"output": "1" if on else "0"}).encode()
        req = _Request(f"{self.base}/sensors/{port}", data=body, method="PUT",
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):  # Session weg -> einmal neu anmelden
                self._opener = None
                self._ensure().open(req, timeout=self.timeout)
            else:
                raise MPowerError(f"Schalten von Port {port} fehlgeschlagen: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise MPowerError(f"Schalten von Port {port} fehlgeschlagen: {exc}") from exc

        if not verify:
            return self.outlet(port)

        # Das Relais braucht einen Moment, bis der Zustand zurueckgemeldet wird.
        for _ in range(5):
            time.sleep(0.4)
            o = self.outlet(port)
            if o.on == on:
                return o
        raise MPowerError(
            f"Port {port} hat nicht auf {'ein' if on else 'aus'} geschaltet "
            f"(gelesen: output={o.output}, lock={o.lock})"
        )

    def on(self, port: int) -> Outlet:
        return self.set(port, True)

    def off(self, port: int) -> Outlet:
        return self.set(port, False)

    def toggle(self, port: int) -> Outlet:
        return self.set(port, not self.outlet(port).on)


class MPowerSSH:
    """Liest Werte, die die HTTP-API nicht hergibt.

    Der Energiezaehler ist ueber HTTP nicht erreichbar -- /sensors/N/energy_sum
    antwortet mit "not a valid resource", und sensors.cgi liefert nur den
    Monatswert "thismonth". Der echte Zaehler steht in /proc/power/ und damit
    nur per SSH zur Verfuegung.

    Die Verbindung wird offengehalten: Dropbear 0.51 kann nur
    diffie-hellman-group1-sha1 mit aes128-cbc, und dieser Handshake dauert auf
    einem 2015er MIPS-SoC spuerbar. Pro Abfrage neu zu verbinden waere teuer.
    """

    # Wattstunden pro Zaehlimpuls des Messchips -- dieselbe Konstante, die auch
    # die geraeteseitigen mFi-tools verwenden (cf_count * 0.3125 == energy_sum).
    WH_PER_PULSE = 0.3125

    def __init__(self, host: str, user: str, password: str, timeout: float = 15.0):
        self.host = host
        self.user = user
        self.password = password
        self.timeout = timeout
        self._client = None

    def _connect(self):
        try:
            import paramiko
        except ImportError as exc:
            raise MPowerError("Energiezaehler braucht paramiko (pip install paramiko)") from exc

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(self.host, username=self.user, password=self.password,
                           timeout=self.timeout, look_for_keys=False, allow_agent=False)
        except Exception as exc:
            raise MPowerError(f"SSH zu {self.host} fehlgeschlagen: {exc}") from exc
        return client

    def _exec(self, command: str) -> str:
        if self._client is None:
            self._client = self._connect()
        try:
            _, stdout, _ = self._client.exec_command(command, timeout=self.timeout)
            return stdout.read().decode(errors="replace")
        except Exception:
            # Verbindung verloren -- einmal neu aufbauen, dann aufgeben.
            self.close()
            self._client = self._connect()
            _, stdout, _ = self._client.exec_command(command, timeout=self.timeout)
            return stdout.read().decode(errors="replace")

    def energy(self, ports: tuple[int, ...] = (1, 2, 3)) -> dict[int, float]:
        """Energiezaehler je Port in Wattstunden."""
        files = " ".join(f"/proc/power/energy_sum{p}" for p in ports)
        out = self._exec(f"cat {files}").split()
        if len(out) != len(ports):
            raise MPowerError(f"Unerwartete Antwort beim Lesen der Energiezaehler: {out!r}")
        result = {}
        for port, value in zip(ports, out):
            try:
                result[port] = float(value)
            except ValueError as exc:
                raise MPowerError(f"Energiewert von Port {port} unlesbar: {value!r}") from exc
        return result

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


# -- Konfiguration --------------------------------------------------------

def load_config() -> dict:
    """Zugangsdaten aus Env, Konfigdatei und Defaults zusammenfuehren."""
    cfg = {"host": DEFAULT_HOST, "user": DEFAULT_USER, "password": DEFAULT_PASSWORD}
    if CONFIG_PATH.exists():
        parser = configparser.ConfigParser()
        parser.read(CONFIG_PATH)
        if parser.has_section("mpower"):
            cfg.update({k: v for k, v in parser["mpower"].items() if k in cfg})
    for key, env in (("host", "MPOWER_HOST"), ("user", "MPOWER_USER"), ("password", "MPOWER_PW")):
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


# -- CLI ------------------------------------------------------------------

def _fmt(o: Outlet) -> str:
    state = "AN " if o.on else "AUS"
    mark = "*" if o.on and o.power > 0.5 else " "
    return (f"  {o.port}  {state}{mark} {o.power:7.2f} W  {o.current:6.3f} A  "
            f"{o.voltage:6.1f} V  pf={o.powerfactor:4.2f}  {o.name}")


def cmd_status(mp: MPower, args) -> int:
    outlets = mp.outlets()

    # Der Energiezaehler kommt nur ueber SSH -- deshalb nur auf Anforderung.
    energy: dict[int, float] = {}
    if getattr(args, "energy", False):
        ssh = MPowerSSH(mp.host, mp.user, mp.password)
        try:
            energy = ssh.energy(tuple(o.port for o in outlets))
        except MPowerError as exc:
            print(f"Warnung: Energiezaehler nicht lesbar: {exc}", file=sys.stderr)
        finally:
            ssh.close()

    if args.json:
        rows = []
        for o in outlets:
            row = dict(o.__dict__)
            if o.port in energy:
                row["energy_wh"] = energy[o.port]
            rows.append(row)
        print(json.dumps(rows, indent=2))
        return 0

    print(f"mPower @ {mp.host}")
    header = "  P  Zustand    Leistung      Strom   Spannung"
    print(header + ("     Energie          Name" if energy else "          Name"))
    for o in outlets:
        line = _fmt(o)
        if energy:
            head, _, name = line.rpartition("  ")
            line = f"{head}  {energy.get(o.port, 0.0):8.2f} Wh  {name}"
        print(line)
    total = f"  {'':3}Summe:  {sum(o.power for o in outlets):7.2f} W"
    if energy:
        total += f"{'':32}{sum(energy.values()):8.2f} Wh"
    print(total)
    return 0


def cmd_switch(mp: MPower, args) -> int:
    want = {"on": True, "off": False}.get(args.command)
    for port in args.ports:
        o = mp.toggle(port) if want is None else mp.set(port, want)
        print(f"Port {port} ({o.name}): {'AN' if o.on else 'AUS'}  {o.power:.2f} W")
    return 0


def cmd_watch(mp: MPower, args) -> int:
    try:
        while True:
            outlets = mp.outlets()
            stamp = time.strftime("%H:%M:%S")
            cells = "  ".join(
                f"P{o.port}:{'AN ' if o.on else 'AUS'}{o.power:6.1f}W" for o in outlets
            )
            print(f"\r{stamp}  {cells}  = {sum(o.power for o in outlets):6.1f} W", end="", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print()
        return 0


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    p = argparse.ArgumentParser(
        prog="mpower",
        description="Ubiquiti mFi mPower lokal steuern (ohne Cloud/Controller).",
    )
    p.add_argument("--host", default=cfg["host"], help=f"IP des Geraets (Standard: {cfg['host']})")
    p.add_argument("--user", default=cfg["user"], help="Benutzername")
    p.add_argument("--password", default=cfg["password"], help="Passwort")

    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("status", help="Zustand aller Steckdosen anzeigen")
    s.add_argument("--json", action="store_true", help="Ausgabe als JSON")
    s.add_argument("-e", "--energy", action="store_true",
                   help="Energiezaehler mitlesen (langsamer, geht nur ueber SSH)")
    s.set_defaults(func=cmd_status)

    for name, helptext in (("on", "einschalten"), ("off", "ausschalten"), ("toggle", "umschalten")):
        c = sub.add_parser(name, help=f"Steckdose(n) {helptext}")
        c.add_argument("ports", nargs="+", type=int, metavar="PORT", help="Portnummer(n) 1-3")
        c.set_defaults(func=cmd_switch)

    w = sub.add_parser("watch", help="Leistung fortlaufend beobachten")
    w.add_argument("-n", "--interval", type=float, default=2.0, help="Intervall in Sekunden")
    w.set_defaults(func=cmd_watch)

    args = p.parse_args(argv)
    mp = MPower(host=args.host, user=args.user, password=args.password)
    try:
        return args.func(mp, args)
    except MPowerError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
