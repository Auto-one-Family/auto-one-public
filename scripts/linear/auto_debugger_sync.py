#!/usr/bin/env python3
"""
Linear GraphQL helper for auto-debugger — Python 3.10+ stdlib only.

Env: LINEAR_API_KEY (required). Optional: LINEAR_TEAM overrides config team.

Rate limiting: small sleep between consecutive mutations (0.35s).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

MUTATION_SLEEP_S = 0.35


def load_minimal_yaml(path: Path) -> Dict[str, Any]:
    """Subset parser for .claude/config/linear-auto-debugger.yaml (scalars + labels: block)."""
    root: Dict[str, Any] = {}
    labels: Optional[Dict[str, str]] = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if line.startswith("  ") and labels is not None:
            m = re.match(r"^\s+([a-zA-Z0-9_]+):\s*(.*)$", line)
            if m:
                k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
                labels[k] = v
            continue
        m = re.match(r"^([a-zA-Z0-9_]+):\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
        if k == "labels" and v == "":
            labels = {}
            root["labels"] = labels
        else:
            labels = None
            root[k] = v
    return root


def graphql(api_url: str, token: str, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=body,
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {e.code}: {detail}") from e
    if payload.get("errors"):
        raise SystemExit(f"GraphQL errors: {json.dumps(payload['errors'], indent=2)}")
    return payload.get("data") or {}


def _teams(api_url: str, token: str) -> List[Dict[str, Any]]:
    q = """
    query Teams {
      teams {
        nodes {
          id
          name
          key
        }
      }
    }
    """
    data = graphql(api_url, token, q)
    return list(data.get("teams", {}).get("nodes") or [])


def resolve_team_id(cfg: Dict[str, Any], api_url: str, token: str) -> str:
    want = (os.environ.get("LINEAR_TEAM") or cfg.get("team") or "").strip()
    if not want:
        raise SystemExit("team missing: set in linear-auto-debugger.yaml or LINEAR_TEAM")
    teams = _teams(api_url, token)
    want_l = want.lower()
    for t in teams:
        if t.get("id", "").lower() == want_l:
            return t["id"]
        if (t.get("key") or "").lower() == want_l:
            return t["id"]
        if (t.get("name") or "").lower() == want_l:
            return t["id"]
    keys = ", ".join(f"{t.get('name')}({t.get('key')})" for t in teams[:12])
    raise SystemExit(f"Team not found: {want!r}. Known: {keys or 'none'}")


def issue_search(
    api_url: str, token: str, query: str, first: int = 15, team_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    q = """
    query IssueSearch($query: String!, $first: Int!) {
      issueSearch(query: $query, first: $first) {
        nodes {
          id
          identifier
          title
          url
        }
      }
    }
    """
    try:
        data = graphql(api_url, token, q, {"query": query, "first": first})
        nodes = data.get("issueSearch", {}).get("nodes") or []
        if nodes:
            return nodes
    except SystemExit:
        pass
    # Fallback: filter by title contains (optional team)
    if team_id:
        q2 = """
        query IssuesFilter($first: Int!, $term: String!, $teamId: ID!) {
          issues(
            first: $first
            filter: {
              team: { id: { eq: $teamId } }
              title: { containsIgnoreCase: $term }
            }
          ) {
            nodes {
              id
              identifier
              title
              url
            }
          }
        }
        """
        data = graphql(api_url, token, q2, {"first": first, "term": query, "teamId": team_id})
    else:
        q2 = """
        query IssuesFilter($first: Int!, $term: String!) {
          issues(
            first: $first
            filter: { title: { containsIgnoreCase: $term } }
          ) {
            nodes {
              id
              identifier
              title
              url
            }
          }
        }
        """
        data = graphql(api_url, token, q2, {"first": first, "term": query})
    return list(data.get("issues", {}).get("nodes") or [])


def workspace_label_map(api_url: str, token: str) -> Dict[str, str]:
    """name(lower) -> id"""
    q = """
    query Labels {
      issueLabels(first: 250) {
        nodes {
          id
          name
        }
      }
    }
    """
    data = graphql(api_url, token, q)
    out: Dict[str, str] = {}
    for n in data.get("issueLabels", {}).get("nodes") or []:
        name = (n.get("name") or "").strip().lower()
        if name and n.get("id"):
            out[name] = n["id"]
    return out


def resolve_label_ids(cfg: Dict[str, Any], api_url: str, token: str) -> List[str]:
    labels_cfg = cfg.get("labels") or {}
    if not isinstance(labels_cfg, dict):
        return []
    wmap = workspace_label_map(api_url, token)
    ids: List[str] = []
    for _k, name in labels_cfg.items():
        lid = wmap.get(str(name).strip().lower())
        if lid:
            ids.append(lid)
    return ids


def issue_create(
    api_url: str,
    token: str,
    team_id: str,
    title: str,
    description: str,
    parent_id: Optional[str] = None,
    label_ids: Optional[List[str]] = None,
    project_id: Optional[str] = None,
) -> Dict[str, Any]:
    input_obj: Dict[str, Any] = {
        "teamId": team_id,
        "title": title,
        "description": description or "",
    }
    if parent_id:
        input_obj["parentId"] = parent_id
    if label_ids:
        input_obj["labelIds"] = label_ids
    if project_id:
        input_obj["projectId"] = project_id
    q = """
    mutation Create($input: IssueCreateInput!) {
      issueCreate(input: $input) {
        success
        issue {
          id
          identifier
          url
        }
      }
    }
    """
    data = graphql(api_url, token, q, {"input": input_obj})
    ic = data.get("issueCreate") or {}
    if not ic.get("success"):
        raise SystemExit(f"issueCreate failed: {json.dumps(ic)}")
    issue = ic.get("issue") or {}
    time.sleep(MUTATION_SLEEP_S)
    return issue


def comment_create(api_url: str, token: str, issue_id: str, body: str) -> None:
    q = """
    mutation Comment($input: CommentCreateInput!) {
      commentCreate(input: $input) {
        success
        comment { id }
      }
    }
    """
    data = graphql(
        api_url,
        token,
        q,
        {"input": {"issueId": issue_id, "body": body}},
    )
    cc = data.get("commentCreate") or {}
    if not cc.get("success"):
        raise SystemExit(f"commentCreate failed: {json.dumps(cc)}")
    time.sleep(MUTATION_SLEEP_S)


def load_config(path: Path) -> Dict[str, Any]:
    return load_minimal_yaml(path)


def manifest_path(artifact_dir: Path) -> Path:
    return artifact_dir / "LINEAR-SYNC-MANIFEST.json"


def read_manifest(artifact_dir: Path) -> Dict[str, Any]:
    p = manifest_path(artifact_dir)
    if not p.is_file():
        return {
            "run_id": "",
            "parent": None,
            "children": {},
            "comment_sha256": {},
        }
    return json.loads(p.read_text(encoding="utf-8"))


def write_manifest(artifact_dir: Path, data: Dict[str, Any]) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    manifest_path(artifact_dir).write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def body_from_file(path: Optional[Path]) -> str:
    if not path:
        return ""
    return path.read_text(encoding="utf-8")


def resolve_issue_uuid(api_url: str, token: str, issue_ref: str) -> str:
    if re.match(r"^[0-9a-f-]{36}$", issue_ref, re.I):
        return issue_ref
    data = graphql(api_url, token, "query I($id: String!) { issue(id: $id) { id } }", {"id": issue_ref})
    issue = data.get("issue") or {}
    uid = issue.get("id")
    if not uid:
        raise SystemExit(f"Issue not found: {issue_ref!r}")
    return uid


def cmd_teams(cfg_path: Path) -> None:
    cfg = load_config(cfg_path)
    token = os.environ.get("LINEAR_API_KEY", "").strip()
    if not token:
        raise SystemExit("LINEAR_API_KEY missing")
    api_url = (cfg.get("linear_api_url") or "https://api.linear.app/graphql").strip()
    for t in _teams(api_url, token):
        print(f"{t.get('key')}\t{t.get('name')}\t{t.get('id')}")


def cmd_search(cfg_path: Path, query: str) -> None:
    cfg = load_config(cfg_path)
    token = os.environ.get("LINEAR_API_KEY", "").strip()
    if not token:
        raise SystemExit("LINEAR_API_KEY missing")
    api_url = (cfg.get("linear_api_url") or "https://api.linear.app/graphql").strip()
    team_id: Optional[str] = None
    try:
        team_id = resolve_team_id(cfg, api_url, token)
    except SystemExit:
        team_id = None
    for n in issue_search(api_url, token, query, team_id=team_id):
        print(f"{n.get('identifier')}\t{n.get('title')}\t{n.get('url')}")


def cmd_comment(cfg_path: Path, issue_ref: str, body_file: Path) -> None:
    cfg = load_config(cfg_path)
    token = os.environ.get("LINEAR_API_KEY", "").strip()
    if not token:
        raise SystemExit("LINEAR_API_KEY missing")
    api_url = (cfg.get("linear_api_url") or "https://api.linear.app/graphql").strip()
    uid = resolve_issue_uuid(api_url, token, issue_ref)
    body = body_from_file(body_file)
    comment_create(api_url, token, uid, body)
    print(f"Comment created on {issue_ref} ({uid})")


def cmd_parent_ensure(cfg_path: Path, artifact_dir: Path, title: str, body_file: Path, run_id: str) -> None:
    cfg = load_config(cfg_path)
    token = os.environ.get("LINEAR_API_KEY", "").strip()
    if not token:
        raise SystemExit("LINEAR_API_KEY missing")
    api_url = (cfg.get("linear_api_url") or "https://api.linear.app/graphql").strip()
    team_id = resolve_team_id(cfg, api_url, token)
    manifest = read_manifest(artifact_dir)
    manifest["run_id"] = run_id or manifest.get("run_id") or artifact_dir.name
    if manifest.get("parent"):
        print(f"Parent already in manifest: {manifest['parent'].get('identifier')}")
        return
    label_ids = resolve_label_ids(cfg, api_url, token)
    parent_epic = (cfg.get("parent_epic_id") or "").strip() or None
    body = body_from_file(body_file)
    issue = issue_create(
        api_url,
        token,
        team_id,
        title,
        body,
        parent_id=parent_epic,
        label_ids=label_ids or None,
    )
    manifest["parent"] = issue
    write_manifest(artifact_dir, manifest)
    print(json.dumps(issue, indent=2))


def cmd_child_ensure(
    cfg_path: Path,
    artifact_dir: Path,
    slug: str,
    title: str,
    body_file: Path,
) -> None:
    cfg = load_config(cfg_path)
    token = os.environ.get("LINEAR_API_KEY", "").strip()
    if not token:
        raise SystemExit("LINEAR_API_KEY missing")
    api_url = (cfg.get("linear_api_url") or "https://api.linear.app/graphql").strip()
    team_id = resolve_team_id(cfg, api_url, token)
    manifest = read_manifest(artifact_dir)
    parent = manifest.get("parent")
    if not parent or not parent.get("id"):
        raise SystemExit("manifest has no parent; run parent-ensure first")
    ch = manifest.setdefault("children", {})
    if slug in ch:
        print(f"Child {slug} already in manifest: {ch[slug].get('identifier')}")
        return
    label_ids = resolve_label_ids(cfg, api_url, token)
    body = body_from_file(body_file)
    issue = issue_create(
        api_url,
        token,
        team_id,
        title,
        body,
        parent_id=parent["id"],
        label_ids=label_ids or None,
    )
    ch[slug] = issue
    write_manifest(artifact_dir, manifest)
    print(json.dumps(issue, indent=2))


def cmd_comment_idempotent(
    cfg_path: Path, artifact_dir: Path, issue_ref: str, body_file: Path, key: str
) -> None:
    """Skip comment if sha256(body) unchanged for key."""
    cfg = load_config(cfg_path)
    token = os.environ.get("LINEAR_API_KEY", "").strip()
    if not token:
        raise SystemExit("LINEAR_API_KEY missing")
    api_url = (cfg.get("linear_api_url") or "https://api.linear.app/graphql").strip()
    body = body_from_file(body_file)
    h = hashlib.sha256(body.encode("utf-8")).hexdigest()
    manifest = read_manifest(artifact_dir)
    hashes = manifest.setdefault("comment_sha256", {})
    if hashes.get(key) == h:
        print(f"Skip comment {key} (unchanged hash)")
        return
    uid = resolve_issue_uuid(api_url, token, issue_ref)
    comment_create(api_url, token, uid, body)
    hashes[key] = h
    write_manifest(artifact_dir, manifest)
    print(f"Comment {key} posted (hash recorded)")


def main() -> None:
    p = argparse.ArgumentParser(description="Linear sync helper for auto-debugger")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_config(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--config",
            type=Path,
            default=Path(".claude/config/linear-auto-debugger.yaml"),
            help="Path to linear-auto-debugger.yaml",
        )

    sp = sub.add_parser("teams", help="List teams (key, name, id)")
    add_config(sp)

    sp = sub.add_parser("search", help="Search issues (dedup)")
    add_config(sp)
    sp.add_argument("--query", required=True)

    sp = sub.add_parser("comment", help="Post comment on issue (id or AUT-123)")
    add_config(sp)
    sp.add_argument("--issue", required=True)
    sp.add_argument("--body-file", type=Path, required=True)

    sp = sub.add_parser("parent-ensure", help="Create parent issue if not in manifest")
    add_config(sp)
    sp.add_argument("--artifact-dir", type=Path, required=True)
    sp.add_argument("--run-id", default="")
    sp.add_argument("--title", required=True)
    sp.add_argument("--body-file", type=Path, required=True)

    sp = sub.add_parser("child-ensure", help="Create child issue under manifest parent")
    add_config(sp)
    sp.add_argument("--artifact-dir", type=Path, required=True)
    sp.add_argument("--slug", required=True, help="e.g. PKG-01")
    sp.add_argument("--title", required=True)
    sp.add_argument("--body-file", type=Path, required=True)

    sp = sub.add_parser("comment-idempotent", help="Post comment if body hash changed")
    add_config(sp)
    sp.add_argument("--artifact-dir", type=Path, required=True)
    sp.add_argument("--issue", required=True)
    sp.add_argument("--body-file", type=Path, required=True)
    sp.add_argument("--key", required=True, help="e.g. phase-A or verify-plan")

    args = p.parse_args()
    cfg_path: Path = args.config

    if args.cmd == "teams":
        cmd_teams(cfg_path)
    elif args.cmd == "search":
        cmd_search(cfg_path, args.query)
    elif args.cmd == "comment":
        cmd_comment(cfg_path, args.issue, args.body_file)
    elif args.cmd == "parent-ensure":
        cmd_parent_ensure(cfg_path, args.artifact_dir, args.title, args.body_file, args.run_id)
    elif args.cmd == "child-ensure":
        cmd_child_ensure(cfg_path, args.artifact_dir, args.slug, args.title, args.body_file)
    elif args.cmd == "comment-idempotent":
        cmd_comment_idempotent(cfg_path, args.artifact_dir, args.issue, args.body_file, args.key)
    else:
        raise SystemExit(f"Unknown command: {args.cmd}")


if __name__ == "__main__":
    main()
