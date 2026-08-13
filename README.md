# Chromix

A pitch-ready prototype that turns a customer product image into a color target and an inventory-aware material recipe.

## Run locally

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Interactive API documentation is available at <http://127.0.0.1:8000/docs>.

## What the demo does

- Extracts 1–8 dominant colors from PNG, JPG, or WebP images.
- Reports RGB, RGBA hex, and CIE Lab color values.
- Matches a target from a user-defined material palette.
- Observes per-material inventory limits, calibrated tint strength, and exact total batch mass.
- Shows ingredient mass, percentage, estimated cost, predicted color, and ΔE.

The mixing engine estimates opaque-material absorption/scattering with Kubelka–Munk K/S values, optimizes mass fractions against perceptual CIE Lab distance, and projects every candidate recipe onto the inventory-constrained mass simplex.

## Production roadmap

The current model is intentionally a digital estimator. Pigments mix through absorption and scattering, not simple RGB addition. For production use:

1. Photograph samples under a controlled D65 light booth with a color calibration card—or use a spectrophotometer.
2. Measure each resin/pigment combination at several known concentrations.
3. Fit wavelength-dependent Kubelka–Munk absorption/scattering coefficients.
4. Train a residual model from historical lab recipes and measured outcomes.
5. Add tolerances for resin grade, opacity, wall thickness, temperature, moisture, and machine settings.
6. Close the loop by feeding every lab correction back into the model.

## Test

```bash
uv run pytest
```
