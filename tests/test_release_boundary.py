"""The OCCT adapter remains source-only until separately authorized."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_candidate_workflow_cannot_publish_or_trigger_from_a_tag() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.startswith("name: Build candidate artifacts\n")
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "tags:" not in workflow
    assert "id-token: write" not in workflow
    assert "gh-action-pypi-publish" not in workflow
    assert "python -m build --outdir dist" in workflow
    assert "python -m twine check dist/*" in workflow
    assert "actions/upload-artifact" in workflow
    assert "timeout-minutes:" not in workflow
