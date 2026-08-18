# Chromix improvement backlog

Status: software phase complete; physical evidence pending
Updated: 2026-08-16

This backlog separates software work from evidence that requires a laboratory,
manufacturing partner, or production system. A calibrated result must not be
enabled merely because the corresponding code exists.

## P0 — trustworthy formulation seam

- [x] Replace the `dict | SpectralRecipeResult` union with a typed formulation
  result envelope containing recipe, prediction, provenance, uncertainty,
  reachability, and diagnostics.
- [x] Add a calibration capability registry describing supported materials,
  lots, processes, target sources, illuminants, and model versions.
- [x] Make target validation and formulation consult the same registry.
- [ ] Add a versioned measured-target formulation request while preserving the
  digital hex path as the default.

## P0 — target capture quality

- [x] Add capture-quality metadata for background dominance, clipping, and
  transparency.
- [ ] Add glare and region-size quality metrics.
- [x] Add alpha weighting; [ ] evaluate linear-light or Lab-space clustering.
- [x] Keep target selection explicit and show digital fit separately from
  calibrated confidence in the frontend.
- [x] Add bilingual UI copy for capture warnings and calibration state.

## P1 — physical calibration path

- [x] Enforce the measurement protocol in the data contract: wavelength range,
  interval, units, timestamps, provenance, and replicate metadata.
- [ ] Add strict calibration-bundle validation and immutable artifact hashes.
- [ ] Fit concentration/process effects against replicated measured spectra.
- [ ] Optimize against multiple illuminants and report metamerism risk.

## P1 — robust recipe proposals

- [x] Represent mass in integer dispensing units and preserve exact batch mass.
- [x] Return alternative recipes within a declared color tolerance.
- [ ] Score robustness to lot, process, measurement, and dispensing variation.
- [x] Keep post-rounding feasibility as a hard invariant.

## P1 — runtime and production operations

- [x] Add live/readiness health checks for workers, calibration, and backends.
- [x] Add solve timeout, cancellation, queue-depth, and sanitized metrics.
- [ ] Add recipe IDs, idempotency, inventory reservation, operator approval,
  actual weighed masses, and correction-round audit history.
- [ ] Add authentication, tenant isolation, quotas, and upload abuse controls
  before exposing the service to untrusted callers.

## P1 — evaluation and release gates

- [ ] Add property-based, metamorphic, image-fuzz, and Python/Rust differential
  tests.
- [ ] Require held-out time/lot/family evaluation artifacts for calibration.
- [ ] Track first-shot pass rate, p90/worst Delta E00, uncertainty coverage,
  OOD recall, cost, and post-dispensing violations.
- [ ] Keep residual corrections in shadow mode until physical release gates
  are signed off.

## External evidence gates

- [ ] Define the supported resin, substrate, material roles, process, finish,
  thickness, and product-specific tolerances with a lab partner.
- [ ] Collect replicated 400–700 nm measurements across concentration ladders,
  lots, time periods, and recipe families.
- [ ] Produce repeatability, held-out validation, uncertainty, metamerism, and
  sign-off reports before making a manufacturing claim.

## Execution log

- [x] Baseline reviewed: existing suite passes 117 tests.
- [x] Typed formulation/capability-gate slice.
- [x] Capture-quality/UI slice.
- [x] Contract/runtime/evaluation slices.
- [x] Final validation and backlog update.
