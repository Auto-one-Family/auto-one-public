#!/usr/bin/env python3
"""Vergleicht lokale src-Dateien (git) mit Pi-Bind-Mount per SHA256; zeigt Docker-Status."""
from __future__ import annotations

import hashlib
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
        if p.is_file():
            paths.append(p)
    return paths


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_remote_root(client: paramiko.SSHClient, home: str) -> str | None:
    candidates = [f"{home}/autoone", f"{home}/Auto-one", f"{home}/auto-one"]
    for c in candidates:
        o, _ = ssh_run(client, f"test -f {shlex.quote(c + '/docker-compose.yml')} && echo OK")
        if o.strip() == "OK":
            return c
    o, _ = ssh_run(
        client,
        f"find {shlex.quote(home)} -maxdepth 5 -name docker-compose.yml -type f 2>/dev/null | head -1",
    )
    lines = o.strip().splitlines()
    return str(Path(lines[0]).parent) if lines else None


def ssh_run(client: paramiko.SSHClient, cmd: str) -> tuple[str, str]:
    _, stdout, stderr = client.exec_command(cmd)
    return stdout.read().decode(), stderr.read().decode()


def main() -> None:
    password = os.environ.get("PI_SSH_PASSWORD", "").strip()
    host = os.environ.get("PI_SSH_HOST", "192.168.x.x")
    user = os.environ.get("PI_SSH_USER", "robin")
    if not password:
        print("Set PI_SSH_PASSWORD for SSH check.", file=sys.stderr)
        raise SystemExit(1)

    root = repo_root()
    files = collect_src_paths(root)
    if not files:
        try:
            out = subprocess.check_output(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
                cwd=root,
                text=True,
            )
            names = [ln.strip() for ln in out.splitlines() if ln.strip().startswith(SRC_PREFIX)]
            files = [root / n.replace("/", os.sep) for n in names if (root / n.replace("/", os.sep)).is_file()]
        except subprocess.CalledProcessError:
            files = []
    if not files:
        print("No src files in working-tree diff vs HEAD and none in HEAD tree — only Docker status.")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=20, allow_agent=False, look_for_keys=False)

    home_out, _ = ssh_run(client, "echo $HOME")
    home = home_out.strip()
    remote_root = os.environ.get("PI_REMOTE_REPO", "").strip() or discover_remote_root(client, home)
    if not remote_root:
        print("Remote repo not found", file=sys.stderr)
        raise SystemExit(1)

    print(f"Remote root: {remote_root}")
    ps, _ = ssh_run(client, f"cd {shlex.quote(remote_root)} && docker compose ps el-servador 2>&1")
    print("--- docker compose ps el-servador ---")
    print(ps.strip() or "(empty)")

    cid_out, _ = ssh_run(
        client,
        f"cd {shlex.quote(remote_root)} && docker compose ps -q el-servador 2>/dev/null",
    )
    cid = cid_out.strip()
    if cid:
        fmt = "{{.Name}} started={{.State.StartedAt}} image={{.Config.Image}}"
        insp, _ = ssh_run(client, f"docker inspect -f {shlex.quote(fmt)} {shlex.quote(cid)}")
        print("--- container inspect ---")
        print(insp.strip())

    print("--- SHA256 local vs remote ---")
    mismatches = 0
    if not files:
        print("  (keine Dateien zum Vergleich — siehe Hinweis oben)")
    for local in files:
        rel = local.relative_to(root).as_posix()
        remote_path = (Path(remote_root) / rel).as_posix()
        lo = sha256_file(local)
        o, e = ssh_run(client, f"sha256sum {shlex.quote(remote_path)} 2>&1")
        parts = o.strip().split()
        ro = parts[0] if parts and len(parts[0]) == 64 else ""
        match = lo == ro
        if not match:
            mismatches += 1
        status = "OK" if match else "DIFF"
        print(f"  [{status}] {rel}")
        if not ro:
            print(f"        remote: {o.strip() or e.strip()}")
        elif not match:
            print(f"        local  {lo[:16]}…")
            print(f"        remote {ro[:16]}…")

    client.close()
    if mismatches:
        print(f"\nSummary: {mismatches} file(s) differ from local checkout.")
        raise SystemExit(2)
    if files:
        print("\nSummary: all listed files match Pi mount; container status above.")
    else:
        print("\nSummary: Docker status only (no file list to compare).")


if __name__ == "__main__":
    main()
