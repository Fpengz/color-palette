"""Calibration capability registry and safe target-serving decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .errors import CodedError


CalibrationStatus = Literal["uncalibrated", "pending", "active"]
CapabilityState = Literal["pending", "active", "revoked"]


@dataclass(frozen=True)
class CalibrationCapability:
    """The declared scope in which one calibration artifact may be used."""

    version: str
    model_version: str
    target_sources: tuple[str, ...]
    material_scope: str
    state: CapabilityState = "pending"
    illuminants: tuple[str, ...] = ("D65",)

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.model_version.strip() or not self.material_scope.strip():
            raise ValueError("Calibration capabilities need nonblank version and scope metadata")
        if not self.target_sources or any(not source.strip() for source in self.target_sources):
            raise ValueError("Calibration capabilities need at least one target source")
        if len(set(self.target_sources)) != len(self.target_sources):
            raise ValueError("Calibration capability target sources must be unique")
        if not self.illuminants or any(not illuminant.strip() for illuminant in self.illuminants):
            raise ValueError("Calibration capabilities need at least one illuminant")

    def supports(self, source: str) -> bool:
        return source in self.target_sources


@dataclass(frozen=True)
class CapabilityDecision:
    """A source validation result that is safe to expose to callers."""

    calibration_status: CalibrationStatus
    eligible: bool
    reason_code: str
    capability_version: str | None = None


@dataclass(frozen=True)
class CalibrationRegistry:
    """Small immutable seam for selecting calibration artifacts by scope."""

    capabilities: tuple[CalibrationCapability, ...] = ()

    def __post_init__(self) -> None:
        versions = [capability.version for capability in self.capabilities]
        if len(versions) != len(set(versions)):
            raise ValueError("Calibration capability versions must be unique")

    def evaluate_target(self, source: str) -> CapabilityDecision:
        """Return whether a target source can use an active calibration."""
        if source == "hex":
            return CapabilityDecision("uncalibrated", False, "digital_target_only")

        matching = [capability for capability in self.capabilities if capability.supports(source)]
        active = [capability for capability in matching if capability.state == "active"]
        if active:
            selected = active[0]
            return CapabilityDecision("active", True, "active_calibration", selected.version)
        if matching:
            return CapabilityDecision("pending", False, "calibration_pending")
        return CapabilityDecision("pending", False, "calibration_unconfigured")

    def require_active(self, version: str, source: str) -> CalibrationCapability:
        """Reject calibrated formulation unless the requested scope is active."""
        capability = next(
            (
                candidate
                for candidate in self.capabilities
                if candidate.version == version and candidate.supports(source)
            ),
            None,
        )
        if capability is None or capability.state != "active":
            raise CodedError(
                "The requested calibration is not active for this target source",
                code="calibration_unavailable",
                calibration_version=version,
                target_source=source,
            )
        return capability


DEFAULT_CALIBRATION_REGISTRY = CalibrationRegistry()
