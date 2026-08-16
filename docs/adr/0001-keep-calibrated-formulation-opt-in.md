# ADR-0001: Keep calibrated formulation opt-in

- Status: accepted
- Date: 2026-08-16

## Decision

Keep the calibrated spectral formulation behind the formulation seam, but leave
the browser demo's default formulation on the digital RGB implementation.

## Context

The repository contains measured-spectrum, residual, evaluation, and fallback
foundations, but it does not yet contain the physical measurement evidence or
held-out validation required for manufacturing claims.

## Consequences

The two formulation implementations can share a caller-facing seam while
preserving the current demo payload and behavior. Enabling the calibrated path
for production requires measured calibration data and evidence rather than a
code-only switch.
