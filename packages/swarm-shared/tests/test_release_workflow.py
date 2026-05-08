"""Regression checks for release workflow safety."""

from pathlib import Path


def test_release_workflow_extracts_changelog_notes_safely() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow = repo_root / ".github" / "workflows" / "release.yml"
    text = workflow.read_text(encoding="utf-8")

    assert 'awk -v version="$VERSION"' in text
    assert "No CHANGELOG.md section found for release version" in text
    assert "printf '%s\\n' \"$NOTES\"" in text
