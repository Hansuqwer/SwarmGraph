#!/usr/bin/env python3
"""Bundle the entire hive_analysis_project/ folder into one zip.

Usage:
    cd ..                                 # parent folder of hive_analysis_project/
    python hive_analysis_project/create_zip.py
    # produces: hive_analysis_project_2026-05-07.zip in the parent directory.

Or run from inside the folder:
    cd hive_analysis_project
    python create_zip.py                  # writes ../hive_analysis_project_<date>.zip
"""
from __future__ import annotations

import datetime as _dt
import sys
import zipfile
from pathlib import Path

PROJECT_NAME = "hive_analysis_project"


def find_project_root() -> Path:
    """Locate the hive_analysis_project/ folder relative to this script."""
    here = Path(__file__).resolve().parent
    if here.name == PROJECT_NAME:
        return here
    candidate = here / PROJECT_NAME
    if candidate.is_dir():
        return candidate
    raise FileNotFoundError(
        f"Cannot find {PROJECT_NAME}/ relative to {here}"
    )


def build_zip(project_root: Path, output_path: Path) -> int:
    """Walk project_root and write every file into output_path. Returns file count."""
    count = 0
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(project_root.rglob("*")):
            if path.is_file():
                # arcname relative to the project root, prefixed with the project name
                # so the archive extracts to a single folder.
                arcname = Path(PROJECT_NAME) / path.relative_to(project_root)
                zf.write(path, arcname=str(arcname))
                count += 1
    return count


def main() -> int:
    try:
        project_root = find_project_root()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    today = _dt.date.today().isoformat()  # YYYY-MM-DD (will be 2026-05-07 today)
    output_path = project_root.parent / f"{PROJECT_NAME}_{today}.zip"

    count = build_zip(project_root, output_path)

    size_kb = output_path.stat().st_size / 1024
    print(f"✅ Wrote {output_path}")
    print(f"   {count} files, {size_kb:.1f} KB")
    print(f"   Extract with: unzip {output_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
