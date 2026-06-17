#!/usr/bin/env python3
"""
Synchronisiert geaenderte und untracked Dateien unter El Servador/god_kaiser_server/src/
per SFTP auf einen Raspberry Pi (ohne Git auf dem Ziel) und startet el-servador neu.

Umgebung (Pflicht):
  PI_SSH_PASSWORD   SSH-Passwort

Optional:
  PI_SSH_HOST       Default: 192.168.x.x
  PI_SSH_USER       Default: robin
  PI_REMOTE_REPO    Remote-Projektroot (z. B. /home/robin/autoone). Leer = Auto-Ermittlung.

Nutzung (Repo-Root):
  set PI_SSH_PASSWORD=...
  python scripts/deploy/sync_pi_server.py
"""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

import paramiko

SRC_PREFIX = "El Servador/god_kaiser_server/src"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def collect_src_paths(root: Path) -> list[Path]:
    try:
        out1 = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD", "--", SRC_PREFIX],
            cwd=root,
            text=True,
        )
        out2 = subprocess.check_output(
            ["git", "ls-files", "-o", "--exclude-standard", "--", SRC_PREFIX],
            cwd=root,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"git failed: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    names = {ln.strip() for ln in (out1 + out2).splitlines() if ln.strip()}
    paths = []
    for n in sorted(names):
        p = root / n.replace("/", os.sep)
        if not p.is_file():
            print(f"Skip (not a file): {p}", file=sys.stderr)
            continue
        paths.append(p)
    return paths


def ssh_run(client: paramiko.SSHClient, cmd: str) -> tuple[str, str]:
    _, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode(), stderr.read().decode()


def discover_remote_root(client: paramiko.SSHClient, home: str) -> str | None:
    candidates = [
        f"{home}/autoone",
        f"{home}/Auto-one",
        f"{home}/auto-one",
        f"{home}/AutomationOne",
    ]
    for c in candidates:
        o, _ = ssh_run(client, f"test -f {shlex.quote(c + '/docker-compose.yml')} && echo OK")
        if o.strip() == "OK":
            return c
    o, _ = ssh_run(
        client,
        f"find {shlex.quote(home)} -maxdepth 5 -name docker-compose.yml -type f 2>/dev/null | head -1",
    )
    line = o.strip().splitlines()
    if line:
        return str(Path(line[0]).parent)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="SFTP sync god_kaiser_server/src to Pi")
    parser.add_argument("--host", default=os.environ.get("PI_SSH_HOST", "192.168.x.x"))
    parser.add_argument("--user", default=os.environ.get("PI_SSH_USER", "robin"))
    parser.add_argument(
        "--remote-root",
        default=os.environ.get("PI_REMOTE_REPO", "").strip(),
        help="Remote repo root; default from env PI_REMOTE_REPO or auto-detect",
    )
    parser.add_argument("--no-restart", action="store_true", help="Do not restart el-servador")
    args = parser.parse_args()

    password = os.environ.get("PI_SSH_PASSWORD", "").strip()
    if not password:
        print("Set environment variable PI_SSH_PASSWORD", file=sys.stderr)
        raise SystemExit(1)

    root = repo_root()
    files = collect_src_paths(root)
    if not files:
        print("No changed/untracked files under", SRC_PREFIX)
        return

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.host,
        username=args.user,
        password=password,
        timeout=25,
        allow_agent=False,
        look_for_keys=False,
    )

    home_out, _ = ssh_run(client, "echo $HOME")
    home = home_out.strip()
    if not home:
        print("Remote HOME empty", file=sys.stderr)
        raise SystemExit(1)

    remote_root = args.remote_root or discover_remote_root(client, home)
    if not remote_root:
        print("Could not find remote repo (docker-compose.yml)", file=sys.stderr)
        raise SystemExit(1)

    print(f"Remote root: {remote_root}")
    print("Upload:")
    sftp = client.open_sftp()
    for local in files:
        rel = local.relative_to(root).as_posix()
        remote_path = (Path(remote_root) / rel).as_posix()
        remote_dir = str(Path(remote_path).parent)
        _, em = ssh_run(client, f"mkdir -p {shlex.quote(remote_dir)}")
        if em.strip():
            print(f"  mkdir stderr: {em}", file=sys.stderr)
        sftp.put(str(local), remote_path)
        print(f"  {rel}")
    sftp.close()

    if not args.no_restart:
        out, _ = ssh_run(
            client,
            f"cd {shlex.quote(remote_root)} && docker compose ps -q el-servador 2>/dev/null",
        )
        if out.strip():
            ro, er = ssh_run(
                client,
                f"cd {shlex.quote(remote_root)} && docker compose restart el-servador 2>&1",
            )
            print(ro or er)
        else:
            print("(el-servador container not running — no restart.)")

    client.close()
    print("Done.")


if __name__ == "__main__":
    main()
