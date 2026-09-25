"""Static interface checks for explicit sentence decision state."""

from pathlib import Path


def test_sentence_decision_buttons_show_the_persisted_selection() -> None:
    root = Path(__file__).parents[2]
    script = (root / "src/heva/app/static/review_document.js").read_text()
    styles = (root / "src/heva/app/static/review.css").read_text()

    assert "View page ${record.page} in PDF" not in script
    assert "navigatePdfEvidence(record)" in script  # Editing still opens source evidence.
    assert "item.review.status === status" in script
    assert 'button.setAttribute("aria-pressed", String(selected))' in script
    assert 'selected ? `✓ ${label}` : label' in script
    assert ".decision-button.selected" in styles
    assert ".decision-approved.selected" in styles
    assert ".decision-needs_correction.selected" in styles
    assert ".decision-excluded.selected" in styles
