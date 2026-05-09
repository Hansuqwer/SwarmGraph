"""Create/update GitHub labels from .github/labels.yml.

Requires GITHUB_TOKEN unless --dry-run is used.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

API_VERSION = "2026-03-10"


def _request(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> int:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def sync_labels(owner: str, repo: str, manifest: Path, *, dry_run: bool) -> None:
    labels = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    if not isinstance(labels, list):
        raise ValueError(f"label manifest must be a list: {manifest}")

    token = os.environ.get("GITHUB_TOKEN")
    if not dry_run and not token:
        raise RuntimeError("GITHUB_TOKEN is required unless --dry-run is set")

    base = f"https://api.github.com/repos/{owner}/{repo}/labels"
    for label in labels:
        if not isinstance(label, dict):
            raise ValueError("label entries must be mappings")
        name = str(label["name"])
        payload = {
            "name": name,
            "color": str(label["color"]),
            "description": str(label.get("description") or "")[:100],
        }
        if dry_run:
            print(f"would sync label: {name}")
            continue

        encoded_name = urllib.parse.quote(name, safe="")
        status = _request("PATCH", f"{base}/{encoded_name}", token or "", payload)
        if status == 404:
            status = _request("POST", base, token or "", payload)
        if status not in {200, 201}:
            raise RuntimeError(f"failed syncing label {name!r}: HTTP {status}")
        print(f"synced label: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", default="Hansuqwer")
    parser.add_argument("--repo", default="SwarmGraph")
    parser.add_argument("--manifest", type=Path, default=Path(".github/labels.yml"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sync_labels(args.owner, args.repo, args.manifest, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
