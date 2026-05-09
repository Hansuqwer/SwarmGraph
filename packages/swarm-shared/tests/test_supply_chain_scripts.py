from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_script(name: str):
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_sbom_from_uv_lock(tmp_path: Path) -> None:
    script = _load_script("generate_sbom.py")
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        """
[[package]]
name = "demo"
version = "1.2.3"
source = { registry = "https://pypi.org/simple" }
""".strip(),
        encoding="utf-8",
    )

    output = tmp_path / "dist" / "sbom.cyclonedx.json"
    script.write_sbom(lock_path, output)

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["bomFormat"] == "CycloneDX"
    assert data["components"][0]["purl"] == "pkg:pypi/demo@1.2.3"


def test_generate_license_report_from_uv_lock(tmp_path: Path) -> None:
    script = _load_script("generate_license_report.py")
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(
        """
[[package]]
name = "demo"
version = "1.2.3"
source = { registry = "https://pypi.org/simple" }
""".strip(),
        encoding="utf-8",
    )

    output = tmp_path / "dist" / "licenses.txt"
    script.write_report(lock_path, output)

    text = output.read_text(encoding="utf-8")
    assert "SwarmGraph dependency report" in text
    assert "demo\t1.2.3\tpypi" in text
