import pytest

from app.target_capture import TargetSelection


def test_target_selection_normalizes_hex_and_preserves_source() -> None:
    selection = TargetSelection("roi", "#d0362b")

    assert selection.hex_color == "#D0362B"
    assert selection.provenance()["target_source"] == "roi"


def test_target_selection_rejects_region_metadata_for_non_roi_sources() -> None:
    with pytest.raises(ValueError, match="Only ROI"):
        TargetSelection("manual", "#D0362B", (1, 2, 3, 4))
