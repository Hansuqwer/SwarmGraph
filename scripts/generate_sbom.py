"""Generate a minimal CycloneDX JSON SBOM from uv.lock."""

from __future__ import annotations

import argparse
import json
import tomllib
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any


def _component_from_package(package: dict[str, Any]) -> dict[str, Any]:
    name = str(package["name"])
    version = str(package.get("version") or "0")
    component: dict[str, Any] = {
        "type": "library",
        "name": name,
        "version": version,
        "bom-ref": f"pkg:pypi/{name}@{version}",
        "purl": f"pkg:pypi/{name}@{version}",
    }
    source = package.get("source")
    if isinstance(source, dict) and "editable" in source:
        component["type"] = "application"
        component["bom-ref"] = name
        component.pop("purl", None)
    return component


def build_sbom(lock_path: Path) -> dict[str, Any]:
    data = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = data.get("package") or []
    if not isinstance(packages, list):
        raise ValueError("uv.lock package section must be a list")

    components = [
        _component_from_package(package) for package in packages if isinstance(package, dict)
    ]
    components.sort(key=lambda item: (item["name"].lower(), item.get("version") or ""))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(),
            "component": {
                "type": "application",
                "name": "swarmgraph",
                "version": "0.8.0",
            },
            "tools": [
                {
                    "vendor": "SwarmGraph",
                    "name": "scripts/generate_sbom.py",
                }
            ],
        },
        "components": components,
    }


def write_sbom(lock_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(build_sbom(lock_path), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument("--output", type=Path, default=Path("dist/sbom.cyclonedx.json"))
    args = parser.parse_args()
    write_sbom(args.lock, args.output)


if __name__ == "__main__":
    main()
