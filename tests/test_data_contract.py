import pytest

from app.data_contract import (
    AcceptanceDecision,
    LabMeasurement,
    MeasuredSampleRecord,
    MeasuredSpectrum,
    PredictionSnapshot,
    SampleVersions,
    TargetMeasurement,
)


def sample_record() -> MeasuredSampleRecord:
    return MeasuredSampleRecord(
        sample_id="sample-1",
        batch_id="batch-1",
        recipe_id="recipe-1",
        ingredient_concentrations={"Resin": 0.9, "Red": 0.1},
        material_roles={"Resin": "base_resin", "Red": "pigment_powder"},
        supplier_product_ids={"Resin": "resin-1", "Red": "red-1"},
        material_lots={"Resin": "lot-r", "Red": "lot-red"},
        carrier_base_resin="Resin",
        substrate="PP",
        process_settings={"temperature_c": 220, "residence_time_s": 45},
        operator="operator-1",
        measured_at="2026-08-14T00:00:00Z",
        replicate_number=1,
        thickness_mm=2.0,
        opacity="opaque",
        gloss=20,
        surface_texture="smooth",
        conditioning={"temperature_c": 23, "relative_humidity": 50},
        measured_spectrum=MeasuredSpectrum(
            wavelengths_nm=[400, 500, 600],
            reflectance=[0.2, 0.4, 0.6],
            instrument="test-spectro",
            raw_uri="s3://approved/sample-1.csv",
            calibration_evidence="white-tile-check-1",
            grid_policy="documented_resampling",
            resampling_plan="Test fixture uses a three-point grid before protocol resampling.",
        ),
        measured_lab=LabMeasurement(
            l=50,
            a=30,
            b=20,
            illuminant="D65",
            observer="2deg",
            geometry="45a:0",
            sci_sce="SCI",
        ),
        prediction=PredictionSnapshot(
            prediction_id="prediction-1",
            created_at="2026-08-14T00:00:00Z",
            model_version="digital-km-prototype-v1",
            optimizer_status="success",
            target_source="roi",
            delta_e_metric="CIEDE2000",
            predicted_delta_e=2.2,
            uncertainty_status="unavailable",
        ),
        acceptance=AcceptanceDecision(status="pending"),
        versions=SampleVersions(
            model_version="digital-km-prototype-v1",
            calibration_version="calibration-0",
            optimizer_version="optimizer-1",
        ),
    )


def test_measured_sample_record_round_trips_canonically() -> None:
    record = sample_record()

    restored = MeasuredSampleRecord.from_json(record.canonical_json())

    assert restored.sample_id == "sample-1"
    assert restored.measured_spectrum.reflectance == [0.2, 0.4, 0.6]
    assert restored.external_storage_payload()["schema_version"] == "spectral-sample-v1"


def test_measured_sample_requires_material_lots_and_matching_series() -> None:
    with pytest.raises(ValueError, match="equal lengths"):
        MeasuredSpectrum(
            wavelengths_nm=[400, 500],
            reflectance=[0.2, 0.4, 0.6],
            instrument="test",
            raw_uri="s3://approved/raw",
            calibration_evidence="white-tile-check-1",
        )

    with pytest.raises(ValueError, match="Material lots must match"):
        record = sample_record().model_dump()
        record["material_lots"] = {"Resin": "lot-r"}
        MeasuredSampleRecord.model_validate(record)


def test_measured_spectrum_requires_protocol_grid_or_documented_resampling() -> None:
    with pytest.raises(ValueError, match="400-700 nm grid"):
        MeasuredSpectrum(
            wavelengths_nm=[400, 500, 600],
            reflectance=[0.2, 0.4, 0.6],
            instrument="test",
            raw_uri="s3://approved/raw",
            calibration_evidence="white-tile-check-1",
        )

    with pytest.raises(ValueError, match="resampling plan"):
        MeasuredSpectrum(
            wavelengths_nm=[400, 500, 600],
            reflectance=[0.2, 0.4, 0.6],
            instrument="test",
            raw_uri="s3://approved/raw",
            calibration_evidence="white-tile-check-1",
            grid_policy="documented_resampling",
        )


def test_completed_acceptance_requires_a_traceable_decision() -> None:
    with pytest.raises(ValueError, match="Completed acceptance decisions need"):
        AcceptanceDecision(status="accepted")


def test_target_measurement_requires_source_specific_provenance() -> None:
    assert TargetMeasurement(source="hex", hex_color="#123456").hex_color == "#123456"
    with pytest.raises(ValueError, match="measured spectrum"):
        TargetMeasurement(source="spectrophotometer")
    with pytest.raises(ValueError, match="calibration card"):
        TargetMeasurement(source="controlled_image", image_uri="s3://approved/image.png")
