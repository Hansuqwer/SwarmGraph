import shutil
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("gitleaks") is None,
    reason="gitleaks not installed",
)

_GITLEAKS_BASE_CMD = [
    "gitleaks",
    "detect",
    "--no-git",
    "--config",
    ".gitleaks.toml",
    "--redact",
]


def test_gitleaks_skips_known_fixture_path():
    result = subprocess.run(  # noqa: S603 - fixed local scanner command in regression test.
        [*_GITLEAKS_BASE_CMD, "--source", "tests/fixtures/secret_shapes"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_gitleaks_detects_planted_secret_outside_allowlist(tmp_path):
    planted = tmp_path / "firebase_options.dart"
    planted.write_text("const apiKey = 'AIzaSyFakeFakeFakeFakeFakeFakeFakeFake';\n")

    result = subprocess.run(  # noqa: S603 - fixed local scanner command in regression test.
        [*_GITLEAKS_BASE_CMD, "--source", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
