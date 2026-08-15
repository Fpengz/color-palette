"""Measured-spectrum primitives for the calibrated formulation path.

The browser demo still uses the RGB prototype in :mod:`app.mixing`. This module
provides the explicit wavelength, measurement, K/S, and metamerism contracts
needed before a measured model can be enabled in production.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from .color import delta_e_2000


WAVELENGTHS_400_700_10NM = tuple(range(400, 701, 10))
_CMF_X = (
    0.01431, 0.04351, 0.13438, 0.28390, 0.34828, 0.33620, 0.29080, 0.19536,
    0.09564, 0.03201, 0.00490, 0.00930, 0.06327, 0.16550, 0.29040, 0.43345,
    0.59450, 0.76210, 0.91630, 1.02630, 1.06220, 1.00260, 0.85445, 0.64240,
    0.44790, 0.28350, 0.16490, 0.08740, 0.04677, 0.02270, 0.01136,
)
_CMF_Y = (
    0.00040, 0.00121, 0.00400, 0.01160, 0.02300, 0.03800, 0.06000, 0.09100,
    0.13902, 0.20802, 0.32300, 0.50300, 0.71000, 0.86200, 0.95400, 0.99495,
    0.99500, 0.95200, 0.87000, 0.75700, 0.63100, 0.50300, 0.38100, 0.26500,
    0.17500, 0.10700, 0.06100, 0.03200, 0.01700, 0.00821, 0.00410,
)
_CMF_Z = (
    0.06785, 0.20740, 0.64560, 1.38560, 1.74706, 1.77211, 1.66920, 1.28764,
    0.81295, 0.46518, 0.27200, 0.15820, 0.07825, 0.04216, 0.02030, 0.00875,
    0.00390, 0.00210, 0.00165, 0.00110, 0.00080, 0.00034, 0.00019, 0.00005,
    0.00002, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000,
)
_D65_SPD = (
    82.755, 91.486, 93.432, 86.682, 104.865, 117.008, 117.812, 114.861,
    115.923, 108.811, 109.354, 107.802, 104.790, 107.689, 104.405, 104.046,
    100.000, 96.334, 95.788, 88.686, 90.006, 89.599, 88.649, 87.699,
    83.289, 83.699, 80.027, 80.215, 82.278, 78.284, 69.721,
)


@dataclass(frozen=True)
class SpectralGrid:
    wavelengths_nm: tuple[float, ...]

    def __post_init__(self) -> None:
        values = np.asarray(self.wavelengths_nm, dtype=float)
        if values.ndim != 1 or len(values) < 2 or not np.all(np.isfinite(values)):
            raise ValueError("A spectral grid needs at least two finite wavelengths")
        if not np.all(np.diff(values) > 0):
            raise ValueError("Spectral wavelengths must be strictly increasing")

    @classmethod
    def standard(cls) -> SpectralGrid:
        return cls(WAVELENGTHS_400_700_10NM)

    @classmethod
    def regular(cls, start_nm: float, end_nm: float, step_nm: float) -> SpectralGrid:
        if not all(math.isfinite(value) for value in (start_nm, end_nm, step_nm)) or step_nm <= 0:
            raise ValueError("A regular spectral grid needs finite bounds and a positive step")
        count = round((end_nm - start_nm) / step_nm)
        if count < 1 or not math.isclose(start_nm + count * step_nm, end_nm, abs_tol=1e-8):
            raise ValueError("Spectral grid bounds must be divisible by the step")
        return cls(tuple(start_nm + index * step_nm for index in range(count + 1)))

    @property
    def size(self) -> int:
        return len(self.wavelengths_nm)

    def array(self) -> np.ndarray:
        return np.asarray(self.wavelengths_nm, dtype=float)


@dataclass(frozen=True)
class Spectrum:
    grid: SpectralGrid
    values: tuple[float, ...]
    kind: str = "reflectance"

    def __post_init__(self) -> None:
        values = np.asarray(self.values, dtype=float)
        if values.shape != (self.grid.size,) or not np.all(np.isfinite(values)):
            raise ValueError("Spectrum values must match the grid and be finite")
        if self.kind == "reflectance" and np.any((values < 0) | (values > 1)):
            raise ValueError("Reflectance values must be between 0 and 1")
        if self.kind in {"k", "s", "ks"} and np.any(values < 0):
            raise ValueError("K/S coefficient values cannot be negative")

    @classmethod
    def from_array(cls, grid: SpectralGrid, values: np.ndarray, kind: str = "reflectance") -> Spectrum:
        return cls(grid, tuple(float(value) for value in np.asarray(values, dtype=float)), kind)

    def array(self) -> np.ndarray:
        return np.asarray(self.values, dtype=float)

    def resample(self, grid: SpectralGrid) -> Spectrum:
        values = np.interp(grid.array(), self.grid.array(), self.array())
        return Spectrum.from_array(grid, values, self.kind)


@dataclass(frozen=True)
class Illuminant:
    name: str
    spectrum: Spectrum

    def __post_init__(self) -> None:
        if self.spectrum.kind != "illuminant":
            raise ValueError("Illuminant spectra must use kind='illuminant'")
        if np.any(self.spectrum.array() <= 0):
            raise ValueError("Illuminant power must be positive")


@dataclass(frozen=True)
class Observer:
    name: str
    grid: SpectralGrid
    x_bar: tuple[float, ...]
    y_bar: tuple[float, ...]
    z_bar: tuple[float, ...]

    def __post_init__(self) -> None:
        values = [np.asarray(item, dtype=float) for item in (self.x_bar, self.y_bar, self.z_bar)]
        if any(item.shape != (self.grid.size,) or not np.all(np.isfinite(item)) for item in values):
            raise ValueError("Observer functions must match the spectral grid")

    def arrays(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return tuple(np.asarray(item, dtype=float) for item in (self.x_bar, self.y_bar, self.z_bar))  # type: ignore[return-value]


@dataclass(frozen=True)
class MeasurementMetadata:
    instrument: str
    illuminant: str
    observer: str
    geometry: str
    sci_sce: str
    wavelength_start_nm: float
    wavelength_end_nm: float
    wavelength_interval_nm: float
    thickness_mm: float | None = None
    gloss: float | None = None
    lot_id: str | None = None

    def __post_init__(self) -> None:
        if not self.instrument.strip() or not self.illuminant.strip() or not self.observer.strip():
            raise ValueError("Measurement instrument, illuminant, and observer are required")
        if self.geometry not in {"45a:0", "d:8", "0:45"}:
            raise ValueError("Measurement geometry must be a supported geometry identifier")
        if self.sci_sce not in {"SCI", "SCE", "unspecified"}:
            raise ValueError("SCI/SCE must be SCI, SCE, or unspecified")
        numeric_values = (
            self.wavelength_start_nm,
            self.wavelength_end_nm,
            self.wavelength_interval_nm,
            self.thickness_mm,
            self.gloss,
        )
        if any(value is not None and not math.isfinite(value) for value in numeric_values):
            raise ValueError("Measurement metadata values must be finite")
        if self.wavelength_start_nm >= self.wavelength_end_nm or self.wavelength_interval_nm <= 0:
            raise ValueError("Measurement wavelength bounds are invalid")
        if self.thickness_mm is not None and self.thickness_mm <= 0:
            raise ValueError("Sample thickness must be positive")
        if self.gloss is not None and self.gloss < 0:
            raise ValueError("Sample gloss must be nonnegative")


def standard_observer_2deg() -> Observer:
    grid = SpectralGrid.standard()
    return Observer("CIE 1931 2 degree", grid, _CMF_X, _CMF_Y, _CMF_Z)


def standard_illuminant_d65() -> Illuminant:
    grid = SpectralGrid.standard()
    return Illuminant("D65", Spectrum(grid, _D65_SPD, kind="illuminant"))


def reflectance_to_ks(reflectance: Spectrum) -> Spectrum:
    if reflectance.kind != "reflectance":
        raise ValueError("K/S conversion requires a reflectance spectrum")
    safe = np.clip(reflectance.array(), 1e-5, 1.0)
    return Spectrum.from_array(reflectance.grid, (1 - safe) ** 2 / (2 * safe), kind="ks")


def ks_to_reflectance(ks: Spectrum) -> Spectrum:
    if ks.kind != "ks":
        raise ValueError("Reflectance conversion requires a K/S spectrum")
    values = np.clip(ks.array(), 0, None)
    # Equivalent to 1 + k - sqrt(k^2 + 2k), but without the subtraction of two
    # near-equal terms that loses precision once K/S is large.
    reflectance = 1.0 / (1.0 + values + np.sqrt(values**2 + 2 * values))
    return Spectrum.from_array(ks.grid, np.clip(reflectance, 0, 1), kind="reflectance")


def mix_k_s(materials: tuple[tuple[Spectrum, Spectrum], ...], fractions: np.ndarray) -> Spectrum:
    if not materials or len(materials) != len(fractions):
        raise ValueError("K/S materials and fractions must have matching non-empty lengths")
    fractions = np.asarray(fractions, dtype=float)
    if not np.all(np.isfinite(fractions)) or np.any(fractions < 0) or not math.isclose(float(fractions.sum()), 1.0, abs_tol=1e-8):
        raise ValueError("Spectral mixture fractions must be nonnegative and sum to one")
    grid = materials[0][0].grid
    k_values = np.zeros(grid.size)
    s_values = np.zeros(grid.size)
    for fraction, (k, s) in zip(fractions, materials, strict=True):
        if k.kind != "k" or s.kind != "s" or k.grid != grid or s.grid != grid:
            raise ValueError("All K/S materials must share a grid and coefficient kinds")
        k_values += fraction * k.array()
        s_values += fraction * s.array()
    safe_s = np.clip(s_values, 1e-8, None)
    return ks_to_reflectance(Spectrum.from_array(grid, k_values / safe_s, kind="ks"))


def spectrum_to_xyz(
    reflectance: Spectrum,
    illuminant: Illuminant | None = None,
    observer: Observer | None = None,
) -> np.ndarray:
    if reflectance.kind != "reflectance":
        raise ValueError("Color conversion requires a reflectance spectrum")
    illuminant = illuminant or standard_illuminant_d65()
    observer = observer or standard_observer_2deg()
    if illuminant.spectrum.grid != reflectance.grid:
        illuminant_spectrum = illuminant.spectrum.resample(reflectance.grid)
    else:
        illuminant_spectrum = illuminant.spectrum
    if observer.grid != reflectance.grid:
        observer = Observer(
            observer.name,
            reflectance.grid,
            tuple(np.interp(reflectance.grid.array(), observer.grid.array(), observer.x_bar)),
            tuple(np.interp(reflectance.grid.array(), observer.grid.array(), observer.y_bar)),
            tuple(np.interp(reflectance.grid.array(), observer.grid.array(), observer.z_bar)),
        )
    x_bar, y_bar, z_bar = observer.arrays()
    wavelengths = reflectance.grid.array()
    power = illuminant_spectrum.array()
    sample = reflectance.array()
    denominator = np.trapezoid(power * y_bar, wavelengths)
    if denominator <= 0:
        raise ValueError("Illuminant/observer normalization is not positive")
    scale = 100 / denominator
    return scale * np.array([
        np.trapezoid(sample * power * x_bar, wavelengths),
        np.trapezoid(sample * power * y_bar, wavelengths),
        np.trapezoid(sample * power * z_bar, wavelengths),
    ])


def xyz_to_lab(xyz: np.ndarray, white_xyz: np.ndarray | None = None) -> np.ndarray:
    values = np.asarray(xyz, dtype=float)
    if values.shape != (3,) or not np.all(np.isfinite(values)):
        raise ValueError("XYZ must contain three finite components")
    if white_xyz is None:
        white_xyz = spectrum_to_xyz(Spectrum(SpectralGrid.standard(), (1.0,) * 31))
    white = np.asarray(white_xyz, dtype=float)
    if white.shape != (3,) or np.any(white <= 0):
        raise ValueError("White point must contain three positive components")
    ratio = values / white
    delta = 6 / 29
    f = np.where(ratio > delta**3, np.cbrt(ratio), ratio / (3 * delta**2) + 4 / 29)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def spectrum_to_lab(
    reflectance: Spectrum,
    illuminant: Illuminant | None = None,
    observer: Observer | None = None,
) -> np.ndarray:
    illuminant = illuminant or standard_illuminant_d65()
    observer = observer or standard_observer_2deg()
    xyz = spectrum_to_xyz(reflectance, illuminant, observer)
    white = spectrum_to_xyz(Spectrum(reflectance.grid, (1.0,) * reflectance.grid.size), illuminant, observer)
    return xyz_to_lab(xyz, white)


@dataclass(frozen=True)
class ConcentrationSample:
    sample_id: str
    concentration: float
    reflectance: Spectrum
    scattering: Spectrum
    metadata: MeasurementMetadata

    def __post_init__(self) -> None:
        if not self.sample_id.strip() or not math.isfinite(self.concentration) or self.concentration < 0:
            raise ValueError("Concentration samples need an ID and nonnegative finite concentration")
        if self.reflectance.grid != self.scattering.grid:
            raise ValueError("Reflectance and scattering spectra must share a grid")
        if self.reflectance.kind != "reflectance" or self.scattering.kind != "s":
            raise ValueError("Concentration samples need reflectance and scattering spectra")
        if np.any(self.scattering.array() <= 0):
            raise ValueError("Scattering coefficients must be positive")


@dataclass(frozen=True)
class KSModel:
    grid: SpectralGrid
    k_intercept: Spectrum
    k_slope: Spectrum
    s_intercept: Spectrum
    s_slope: Spectrum
    version: str

    def at_concentration(self, concentration: float) -> tuple[Spectrum, Spectrum]:
        if not math.isfinite(concentration) or concentration < 0:
            raise ValueError("Concentration must be nonnegative and finite")
        k = self.k_intercept.array() + concentration * self.k_slope.array()
        s = self.s_intercept.array() + concentration * self.s_slope.array()
        if np.any(k < 0) or np.any(s <= 0):
            raise ValueError("Concentration is outside the calibrated K/S domain")
        return Spectrum.from_array(self.grid, k, "k"), Spectrum.from_array(self.grid, s, "s")


@dataclass(frozen=True)
class SpectralMaterial:
    material_id: str
    k: Spectrum
    s: Spectrum
    available_kg: float
    cost_per_kg: float = 0.0

    def __post_init__(self) -> None:
        if not self.material_id.strip() or self.k.kind != "k" or self.s.kind != "s" or self.k.grid != self.s.grid:
            raise ValueError("Spectral materials need an ID and matching K/S spectra")
        if not all(math.isfinite(value) and value >= 0 for value in (self.available_kg, self.cost_per_kg)):
            raise ValueError("Spectral material inventory and cost must be finite and nonnegative")


@dataclass(frozen=True)
class SpectralRecipeResult:
    fractions: tuple[float, ...]
    predicted: Spectrum
    target_lab: tuple[float, float, float]
    predicted_lab: tuple[float, float, float]
    delta_e_00: float
    total_cost: float
    optimizer_status: str
    calibration_version: str


def _project_fractions(values: np.ndarray, caps: np.ndarray) -> np.ndarray:
    if caps.sum() < 1 - 1e-9:
        raise ValueError("Spectral inventory is insufficient for the requested batch")
    low = float(np.min(values - caps))
    high = float(np.max(values))
    for _ in range(80):
        midpoint = (low + high) / 2
        projected = np.clip(values - midpoint, 0, caps)
        if projected.sum() > 1:
            low = midpoint
        else:
            high = midpoint
    return np.clip(values - high, 0, caps)


def optimize_spectral_recipe(
    target: Spectrum,
    materials: tuple[SpectralMaterial, ...],
    batch_kg: float,
    illuminant: Illuminant | None = None,
    observer: Observer | None = None,
    calibration_version: str = "uncalibrated",
) -> SpectralRecipeResult:
    """Optimize a recipe against a measured spectrum and CIEDE2000."""
    if len(materials) < 2 or not math.isfinite(batch_kg) or batch_kg <= 0:
        raise ValueError("A spectral recipe needs at least two materials and a positive batch")
    if any(material.k.grid != target.grid for material in materials):
        raise ValueError("Spectral target and materials must share a grid")
    caps = np.asarray([material.available_kg / batch_kg for material in materials], dtype=float)
    target_lab = spectrum_to_lab(target, illuminant, observer)

    def loss(fractions: np.ndarray) -> float:
        safe_fractions = _project_fractions(np.clip(fractions, 0, None), caps)
        predicted = mix_k_s(tuple((material.k, material.s) for material in materials), safe_fractions)
        predicted_lab = spectrum_to_lab(predicted, illuminant, observer)
        difference = delta_e_2000(target_lab, predicted_lab)
        return float(difference**2)

    rng = np.random.default_rng(73)
    starts = [_project_fractions(np.ones(len(materials)) / len(materials), caps)]
    starts.extend(
        _project_fractions(rng.random(len(materials)), caps)
        for _ in range(min(12, 3 * len(materials)))
    )
    best = None
    best_loss = float("inf")
    for start in starts:
        result = minimize(
            loss,
            start,
            method="SLSQP",
            bounds=[(0.0, float(cap)) for cap in caps],
            constraints={"type": "eq", "fun": lambda values: float(values.sum() - 1)},
            options={"maxiter": 300, "ftol": 1e-10, "disp": False},
        )
        current = _project_fractions(result.x, caps) if np.all(np.isfinite(result.x)) else None
        if current is None or abs(float(current.sum()) - 1) > 1e-7 or not result.success:
            continue
        current_loss = loss(current)
        if current_loss < best_loss:
            best, best_loss = current, current_loss
    if best is None:
        raise ValueError("The spectral optimizer could not find a feasible recipe")
    predicted = mix_k_s(tuple((material.k, material.s) for material in materials), best)
    predicted_lab = spectrum_to_lab(predicted, illuminant, observer)
    return SpectralRecipeResult(
        tuple(float(value) for value in best),
        predicted,
        tuple(float(value) for value in target_lab),
        tuple(float(value) for value in predicted_lab),
        delta_e_2000(target_lab, predicted_lab),
        float(sum(fraction * batch_kg * material.cost_per_kg for fraction, material in zip(best, materials, strict=True))),
        "success",
        calibration_version,
    )


def fit_ks_ladder(samples: tuple[ConcentrationSample, ...], version: str = "ks-ladder-v1") -> KSModel:
    """Fit wavelength-dependent linear K and S coefficients from a ladder.

    Scattering must be measured or supplied by a validated material model; it
    is not inferred from an RGB swatch. At least two distinct concentrations
    are required for every wavelength.
    """
    if len(samples) < 2:
        raise ValueError("A K/S ladder needs at least two concentration samples")
    grid = samples[0].reflectance.grid
    if len({sample.concentration for sample in samples}) < 2:
        raise ValueError("A K/S ladder needs distinct concentrations")
    if any(sample.reflectance.grid != grid for sample in samples):
        raise ValueError("All K/S ladder samples must share a grid")
    concentrations = np.asarray([sample.concentration for sample in samples], dtype=float)
    design = np.column_stack([np.ones(len(samples)), concentrations])
    ks = np.stack([reflectance_to_ks(sample.reflectance).array() for sample in samples])
    scattering = np.stack([sample.scattering.array() for sample in samples])
    k = ks * scattering
    k_coefficients = np.linalg.lstsq(design, k, rcond=None)[0]
    s_coefficients = np.linalg.lstsq(design, scattering, rcond=None)[0]
    return KSModel(
        grid,
        Spectrum.from_array(grid, k_coefficients[0], "k"),
        Spectrum.from_array(grid, k_coefficients[1], "k"),
        Spectrum.from_array(grid, s_coefficients[0], "s"),
        Spectrum.from_array(grid, s_coefficients[1], "s"),
        version,
    )


@dataclass(frozen=True)
class MetamerismReport:
    delta_e_by_illuminant: dict[str, float]
    primary_illuminant: str
    tolerance: float
    is_metameric: bool


def metamerism_report(
    first: Spectrum,
    second: Spectrum,
    illuminants: tuple[Illuminant, ...],
    observer: Observer | None = None,
    primary_illuminant: str = "D65",
    tolerance: float = 1.0,
) -> MetamerismReport:
    if first.grid != second.grid or not illuminants:
        raise ValueError("Metamerism needs matching spectra and at least one illuminant")
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Metamerism tolerance must be finite and nonnegative")
    names = [illuminant.name for illuminant in illuminants]
    if len(names) != len(set(names)):
        raise ValueError("Each illuminant in a metamerism report needs a distinct name")
    observer = observer or standard_observer_2deg()
    differences: dict[str, float] = {}
    for illuminant in illuminants:
        first_lab = spectrum_to_lab(first, illuminant, observer)
        second_lab = spectrum_to_lab(second, illuminant, observer)
        differences[illuminant.name] = delta_e_2000(first_lab, second_lab)
    if primary_illuminant not in differences:
        raise ValueError("Primary illuminant is not included in the report")
    primary = differences[primary_illuminant]
    return MetamerismReport(
        differences,
        primary_illuminant,
        tolerance,
        primary <= tolerance and any(value > tolerance for name, value in differences.items() if name != primary_illuminant),
    )
