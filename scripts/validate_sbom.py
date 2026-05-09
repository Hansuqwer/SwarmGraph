"""Validate a CycloneDX JSON SBOM against its declared schema version."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cyclonedx.exception import MissingOptionalDependencyException
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator

_SCHEMA_VERSIONS = {
    "1.0": SchemaVersion.V1_0,
    "1.1": SchemaVersion.V1_1,
    "1.2": SchemaVersion.V1_2,
    "1.3": SchemaVersion.V1_3,
    "1.4": SchemaVersion.V1_4,
    "1.5": SchemaVersion.V1_5,
    "1.6": SchemaVersion.V1_6,
}


def validate_sbom(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    spec_version = str(data.get("specVersion") or "")
    schema_version = _SCHEMA_VERSIONS.get(spec_version)
    if schema_version is None:
        supported = ", ".join(sorted(_SCHEMA_VERSIONS))
        raise ValueError(
            f"unsupported CycloneDX specVersion {spec_version!r}; supported: {supported}"
        )

    validator = JsonStrictValidator(schema_version)
    try:
        errors = validator.validate_str(raw, all_errors=True)
    except MissingOptionalDependencyException as exc:
        raise RuntimeError("CycloneDX JSON validation dependencies are missing") from exc

    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"invalid CycloneDX {spec_version} SBOM {path}:\n{details}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        validate_sbom(args.path)
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
