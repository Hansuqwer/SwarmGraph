"""Regression checks for release workflow safety."""

from pathlib import Path


def test_release_workflow_extracts_changelog_notes_safely() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = repo_root / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")

    assert 'awk -v version="$VERSION"' in text
    assert "No CHANGELOG.md section found for release version" in text
    assert "printf '%s\\n' \"$NOTES\"" in text


def test_release_workflow_attests_dist_artifacts() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = repo_root / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")

    assert "actions/attest-build-provenance@v3" in text
    assert "attestations: write" in text
    assert "id-token: write" in text
    assert "subject-path: dist/*" in text


def test_release_workflow_publishes_supply_chain_artifacts() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = repo_root / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")

    assert "python scripts/generate_sbom.py --output dist/sbom.cyclonedx.json" in text
    assert "python scripts/generate_license_report.py --output dist/licenses.txt" in text
    assert "path: dist/*" in text
    assert "files: dist/*" in text
