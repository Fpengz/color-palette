"""Target-capture records shared by the image and formulation workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .color import parse_hex
from .extraction import ROI


TargetSource = Literal["manual", "full_frame", "roi"]


@dataclass(frozen=True)
class TargetSelection:
    """The selected target plus the provenance needed by formulation."""

    source: TargetSource
    hex_color: str
    roi: ROI | None = None

    def __post_init__(self) -> None:
        normalized = parse_hex(self.hex_color).hex
        object.__setattr__(self, "hex_color", normalized)
        if self.source != "roi" and self.roi is not None:
            raise ValueError("Only ROI target selections may include region coordinates")

    def provenance(self) -> dict[str, object]:
        """Return stable provenance fields for a formulation result."""
        return {
            "target_source": self.source,
            "target_selection": self.hex_color,
            "roi": (
                {"x": self.roi[0], "y": self.roi[1], "width": self.roi[2], "height": self.roi[3]}
                if self.roi is not None
                else None
            ),
        }
