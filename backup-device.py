#!/usr/bin/env python3
"""
Sichert die Konfiguration und die mFi-tools-Installation vom Geraet.

Laedt /etc/persistent/ vollstaendig nach backup-geraet/ herunter. Binaerdateien
werden korrekt uebertragen (SFTP, mit Base64-Rueckfall -- Dropbear 0.51 bringt
nicht zwingend einen SFTP-Server mit).

Aufruf:  ./backup-device.py [--host 10.10.1.78] [--out backup-geraet]
"""

from __future__ import annotations

import argparse

import hashlib
import sys
from pathlib import Path

from mpower import load_config

QUELLE = "/etc/persistent"


def liste_dateien(ssh) -> list[str]:
    _, out, _ = ssh.exec_command(f"find {QUELLE} -type f", timeout=30)
    return [z.strip() for z in out.read().decode().splitlines() if z.strip()]


def hole_per_cat(ssh, pfad: str) -> bytes:
    """Datei per 'cat' holen und die Rohbytes uebernehmen.

    Kein base64 noetig -- BusyBox auf diesem Geraet bringt es gar nicht mit.
    Ueber einen exec-Kanal ohne PTY kommen Binaerdaten unveraendert an, solange
    man sie nicht dekodiert. Genau deshalb wird hier read() ohne decode()
    benutzt.
    """
    _, out, err = ssh.exec_command(f"cat {pfad}", timeout=120)
    daten = out.read()
    if not daten:
        fehler = err.read().decode(errors="replace").strip()
        if fehler:
            raise RuntimeError(fehler)
    return daten


def pruefsumme(ssh, pfad: str) -> str | None:
    """md5 auf dem Geraet, um die Uebertragung zu verifizieren."""
    _, out, _ = ssh.exec_command(f"md5sum {pfad}", timeout=30)
    zeile = out.read().decode(errors="replace").split()
    return zeile[0] if zeile else None


def main(argv: list[str] | None = None) -> int:
    cfg = load_config()
    p = argparse.ArgumentParser(description="Geraetekonfiguration sichern")
    p.add_argument("--host", default=cfg["host"])
    p.add_argument("--user", default=cfg["user"])
    p.add_argument("--password", default=cfg["password"])
    p.add_argument("--out", default=str(Path(__file__).parent / "backup-geraet"))
    args = p.parse_args(argv)

    try:
        import paramiko
    except ImportError:
        print("Fehlt: paramiko  ->  pip install paramiko", file=sys.stderr)
        return 1

    ziel = Path(args.out)
    ziel.mkdir(parents=True, exist_ok=True)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(args.host, username=args.user, password=args.password,
                    timeout=20, look_for_keys=False, allow_agent=False)
    except Exception as exc:
        print(f"SSH zu {args.host} fehlgeschlagen: {exc}", file=sys.stderr)
        return 1

    # SFTP bevorzugen, sonst ueber base64 -- Hauptsache, Binaerdateien bleiben heil.
    sftp = None
    try:
        sftp = ssh.open_sftp()
        weg = "SFTP"
    except Exception:
        weg = "cat (Dropbear 0.51 hat keinen SFTP-Server)"
    print(f"Verbunden mit {args.host}, Uebertragung per {weg}\n")

    dateien = liste_dateien(ssh)
    ok = fehler = 0
    for pfad in sorted(dateien):
        rel = pfad[len(QUELLE):].lstrip("/")
        lokal = ziel / rel
        lokal.parent.mkdir(parents=True, exist_ok=True)
        try:
            if sftp is not None:
                sftp.get(pfad, str(lokal))
                daten = lokal.read_bytes()
            else:
                daten = hole_per_cat(ssh, pfad)
                lokal.write_bytes(daten)
        except Exception as exc:
            print(f"  FEHLER  {rel}: {exc}")
            fehler += 1
            continue

        # Uebertragung gegen die Pruefsumme auf dem Geraet verifizieren.
        erwartet = pruefsumme(ssh, pfad)
        haben = hashlib.md5(daten).hexdigest()
        marke = "ok" if (erwartet is None or erwartet == haben) else "PRUEFSUMME!"
        if marke != "ok":
            fehler += 1
        else:
            ok += 1
        print(f"  {marke:12} {rel:42} {len(daten):>7} B")

    if sftp is not None:
        sftp.close()
    ssh.close()
    print(f"\n{ok} Dateien gesichert nach {ziel}" + (f", {fehler} fehlerhaft" if fehler else ""))
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
