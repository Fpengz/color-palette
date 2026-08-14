# Chromix Evaluation Protocol

Protocol ID: `evaluation-protocol-v1`

Use `app.evaluation.split_by_time_lot_family` to construct leakage-resistant
train/validation/test partitions and `evaluate_observations` to calculate the
release metrics. A report is valid only when its sample counts and group keys
are retained with the artifact.

## Required metrics

- median, 90th-percentile, and worst-case CIEDE2000;
- first-shot pass rate at each product-specific tolerance;
- correction rounds and time to an accepted sample;
- recipe cost, ingredient count, and availability;
- pre- and post-dispensing constraint violations;
- performance by color region, resin, substrate, lot, machine, and finish;
- uncertainty coverage and interval sharpness; and
- OOD detection recall on deliberately unfamiliar material/process inputs.

## Release rules

Compare every residual model with the spectral physical baseline on the same
untouched test set. Report sample counts and bootstrap confidence intervals.
Do not promote a model because its mean error improves if its tail error,
constraint violations, or OOD behavior regresses.

Residual corrections are enabled in `shadow` mode first. The serving policy in
`app/serving.py` returns the baseline in shadow mode and falls back to the
baseline for an out-of-domain residual in active mode.

The current repository contains deterministic software fixtures for these
metrics and policies, but no production measurement dataset. Evaluation
reports must therefore be generated from externally stored, versioned samples
before any calibration or manufacturing claim is made.
