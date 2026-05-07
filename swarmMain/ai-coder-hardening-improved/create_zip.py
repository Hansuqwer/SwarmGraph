#!/usr/bin/env python3
"""
Packages the ai-coder-hardening-improved project into a zip archive.
Run from the workspace root: python ai-coder-hardening-improved/create_zip.py
"""

import zipfile
import os
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT = ROOT.parent / "ai-coder-hardening-improved.zip"

INCLUDE = [
    "README.md",
    "ANALYSIS_AND_REVIEW.md",
    "RESEARCH.md",
    "IMPROVEMENTS_PROMPT.md",
    "REPORT.html",
    "pyproject.toml",
    "src/__init__.py",
    "src/ai_coder/__init__.py",
    "src/ai_coder/workflow/__init__.py",
    "src/ai_coder/workflow/state.py",
    "src/ai_coder/workflow/checkpoints.py",
    "src/ai_coder/workflow/nodes.py",
    "src/ai_coder/memory/__init__.py",
    "src/ai_coder/memory/lesson.py",
    "tests/__init__.py",
    "tests/test_workflow_state_hardening.py",
    "tests/test_memo_lesson_hardening.py",
    "tests/test_checkpoint_atomic_write.py",
    "tests/test_fail_closed_comprehensive.py",
]

with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for rel in INCLUDE:
        src = ROOT / rel
        if src.exists():
            arcname = f"ai-coder-hardening-improved/{rel}"
            zf.write(src, arcname)
            print(f"  + {arcname}")
        else:
            print(f"  ! MISSING: {rel}")

print(f"\n✅ Zip created: {OUTPUT}")
print(f"   Size: {OUTPUT.stat().st_size / 1024:.1f} KB")
