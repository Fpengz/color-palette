import pytest

from app.capabilities import CalibrationCapability, CalibrationRegistry
from app.data_contract import TargetMeasurement


def test_registry_distinguishes_digital_targets_from_pending_calibration() -> None:
    registry = CalibrationRegistry()

    assert registry.evaluate_target("hex").calibration_status == "uncalibrated"
    decision = registry.evaluate_target("spectrophotometer")
    assert decision.calibration_status == "pending"
    assert decision.reason_code == "calibration_unconfigured"
    assert decision.eligible is False


def test_registry_activates_only_matching_target_sources() -> None:
    registry = CalibrationRegistry(
        (
            CalibrationCapability(
                version="cal-1",
                model_version="spectral-v1",
                target_sources=("spectrophotometer",),
                material_scope="PP / opaque / 2mm",
                state="active",
            ),
        )
    )

    assert registry.evaluate_target("spectrophotometer").capability_version == "cal-1"
    assert registry.evaluate_target("lab").eligible is False


def test_target_validation_schema_is_separate_from_calibration_eligibility() -> None:
    target = TargetMeasurement(source="hex", hex_color="#123456")
    assert target.source == "hex"


def test_duplicate_capability_versions_are_rejected() -> None:
    capability = CalibrationCapability("cal-1", "model", ("lab",), "scope")
    with pytest.raises(ValueError, match="versions must be unique"):
        CalibrationRegistry((capability, capability))
