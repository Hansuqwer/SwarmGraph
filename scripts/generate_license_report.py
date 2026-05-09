"""Generate a deterministic dependency report from uv.lock."""

from __future__ import annotations

import argparse
import tomllib
from pathlib import Path
from typing import Any


def build_report(lock_path: Path) -> str:
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = data.get("package") or []
    if not isinstance(packages, list):
        raise ValueError("uv.lock package section must be a list")

    rows: list[tuple[str, str, str]] = []
    for package in packages:
        if not isinstance(package, dict):
            continue
        name = str(package.get("name") or "")
        version = str(package.get("version") or "workspace")
        source = package.get("source")
        source_label = "workspace" if isinstance(source, dict) and "editable" in source else "pypi"
        rows.append((name, version, source_label))
    rows.sort(key=lambda row: (row[0].lower(), row[1]))

    lines = [
        "SwarmGraph dependency report",
        "Generated from uv.lock; license values require upstream package metadata review.",
        "",
        "Name\tVersion\tSource",
    ]
    lines.extend(f"{name}\t{version}\t{source}" for name, version, source in rows)
    return "\n".join(lines) + "\n"


def write_report(lock_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_report(lock_path), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument("--output", type=Path, default=Path("dist/licenses.txt"))
    args = parser.parse_args()
    write_report(args.lock, args.output)


if __name__ == "__main__":
    main()
