#!/usr/bin/env python3
"""Bundle the patched repo + analysis artefacts into one zip.

Usage:
    python create_release_zip.py

Output:
    swarmMain_patched_2026-05-07.zip
    (in the same directory as this script)

Includes:
    - swarmMain_patched/   (the patched repo, single top-level folder)
    - hive_analysis_project/ (the original analysis bundle, if present)
    - HIVE_PATCH_AND_COMPLETE_PROMPT.md (the executed prompt)
    - HIVE_ORCHESTRATOR_ANALYSIS_PROMPT.md (the analysis prompt)
"""
from __future__ import annotations

import datetime as _dt
import sys
import zipfile
from pathlib import Path

EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                ".git", ".venv", "venv", "node_modules", ".egg-info"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def _should_skip(p: Path) -> bool:
    if p.suffix in EXCLUDE_SUFFIXES:
        return True
    return any(part in EXCLUDE_DIRS for part in p.parts)


def _include_under(zf: zipfile.ZipFile, root: Path, arc_prefix: str = "") -> int:
    count = 0
    if not root.exists():
        return 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or _should_skip(path):
            continue
        rel = path.relative_to(root.parent if not arc_prefix else root)
        arcname = (Path(arc_prefix) / rel) if arc_prefix else rel
        zf.write(path, arcname=str(arcname))
        count += 1
    return count


def main() -> int:
    here = Path(__file__).resolve().parent
    today = _dt.date.today().isoformat()  # 2026-05-07 today
    out = here / f"swarmMain_patched_{today}.zip"

    total = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # 1) The patched tree
        patched_root = here / "swarmMain_patched"
        if patched_root.exists():
            # arcname = "swarmMain/<sub-project>/..." (rename for clarity)
            for path in sorted(patched_root.rglob("*")):
                if not path.is_file() or _should_skip(path):
                    continue
                rel = path.relative_to(patched_root)
                arcname = Path("swarmMain") / rel
                zf.write(path, arcname=str(arcname))
                total += 1

        # 2) Analysis artefacts (if present)
        analysis_root = here / "hive_analysis_project"
        if analysis_root.exists():
            for path in sorted(analysis_root.rglob("*")):
                if not path.is_file() or _should_skip(path):
                    continue
                rel = path.relative_to(analysis_root)
                arcname = Path("hive_analysis_project") / rel
                zf.write(path, arcname=str(arcname))
                total += 1

        # 3) The two orchestrator prompts (top-level reference)
        for prompt_file in ("HIVE_PATCH_AND_COMPLETE_PROMPT.md",
                            "HIVE_ORCHESTRATOR_ANALYSIS_PROMPT.md"):
            p = here / prompt_file
            if p.exists():
                zf.write(p, arcname=prompt_file)
                total += 1

    size_kb = out.stat().st_size / 1024
    print(f"✅ Wrote {out.name}")
    print(f"   {total} files, {size_kb:.1f} KB")
    print(f"   Extract with: unzip {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
