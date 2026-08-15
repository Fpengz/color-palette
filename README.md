# Chromix

A pitch-ready prototype that turns a customer product image into a color target and an inventory-aware material recipe.

## Run locally

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Use the `EN / 中文` switch in the demo header, or open
<http://127.0.0.1:8000/?lang=zh> directly for the Chinese version. Interactive API
documentation is available at <http://127.0.0.1:8000/docs>.

Pitch-ready product photos and a matching material inventory are available in [`example/`](example/README.md).

## What the demo does

- Extracts 1–8 colors from PNG, JPG, or WebP images, with full-frame and explicit region analysis.
- Reports RGB, RGBA hex, and CIE Lab color values.
- Requires an explicit swatch, manual hex value, or selected image region before using a captured color as the target.
- Matches a target from a user-defined material palette.
- Observes per-material inventory limits, relative tint-strength parameters, and a total batch-mass constraint.
- Shows ingredient mass, percentage, estimated cost, predicted color, and CIEDE2000 (ΔE00).
- Explains any target it cannot match, attributing the color gap to the material set, the stocked quantities, the recipe constraints, or scale rounding.
- The API also supports shop-floor constraints such as minimum doses, scale increments, locked or mutually exclusive materials, correction masses, and cost within a color tolerance.

The mixing engine estimates opaque-material absorption/scattering with Kubelka–Munk K/S values, optimizes mass fractions against perceptual CIE Lab distance, and projects every candidate recipe onto the inventory-constrained mass simplex.

Formulation is CPU-bound and GIL-bound, so each solve runs in a worker process
and a semaphore bounds how many callers queue for one. Past that queue the API
returns `503` with `Retry-After` rather than accepting work nobody is waiting
for. On an 8-core machine, 24 concurrent worst-case solves went from 155s to 14s
wall and from a 154s to a 10s median, and `/api/health` stayed at 5ms instead of
degrading to 591ms.

An optional Rust accelerator screens candidate ingredient sets. It is not
required and is not built by default:

```bash
uv run python -m app.native   # needs cargo; safe to skip
```

It speeds up large palettes (2.6x on twelve materials) and leaves small ones
unchanged. SLSQP still refines the recipe that gets shipped, so the accelerator
cannot change the answer's quality -- only how quickly the search narrows to it.
Without `cargo`, the SciPy path runs and remains the reference.

All formulation results are marked `uncalibrated` and include model, optimizer,
metric, provenance, uncertainty, and telemetry fields. Image-derived targets
remain digital estimates until they are linked to measured material data.

## API examples

Analyze a complete image or an explicit pixel region. The API uses decoded
content rather than trusting the client MIME type.

```bash
curl -X POST http://127.0.0.1:8000/api/extract \
  -F "file=@example/coral-cup.png" \
  -F "colors=5" \
  -F "roi_x=120" -F "roi_y=80" -F "roi_width=640" -F "roi_height=640"
```

Submit a target and inventory to the digital formulation engine. The
`target_source` value records how the target was selected; it does not imply
physical calibration.

```bash
curl -X POST http://127.0.0.1:8000/api/mix \
  -H 'Content-Type: application/json' \
  -d '{
    "target": "#EE4C3A",
    "target_source": "roi",
    "batch_kg": 1,
    "ingredients": [
      {"name": "Resin", "color": "#EFE9DB", "available_kg": 10},
      {"name": "Red", "color": "#D92F26", "available_kg": 10, "strength": 10}
    ],
    "constraints": {
      "minimum_dose_kg": 0.001,
      "scale_increment_kg": 0.0001,
      "preferred_ingredient_count": 2
    }
  }'
```

Every `/api/mix` response carries a `target_reachability` block. When the
target cannot be matched it names the causes, each as a stable `code` plus
`params` for localization and an English `message`:

```json
{
  "status": "unreachable",
  "summary": "This target is out of reach for the current inventory; the closest mix is 5.1 Delta E away.",
  "reasons": [
    {
      "code": "inventory_limited",
      "message": "The closest recipe needs more material than is in stock; running out costs 4.7 Delta E. Fully consumed: Carbon black.",
      "params": {"penalty_delta_e": 4.68, "exhausted_materials": ["Carbon black"]}
    }
  ],
  "suggestions": [{"code": "restock_materials", "message": "Restock Carbon black.", "params": {"materials": ["Carbon black"]}}],
  "attribution": {
    "material_gamut_delta_e": 0.4,
    "inventory_penalty_delta_e": 4.68,
    "constraint_penalty_delta_e": 0.0,
    "dispensing_penalty_delta_e": 0.0
  }
}
```

Failures follow the same pattern. A rejected request returns `detail.message`
in English plus a `reason_code` and `reason_params`, so a client can render the
failure in its own language:

```json
{
  "code": "formulation_failed",
  "message": "Only 248.000 kg is available for a 500.000 kg batch",
  "reason_code": "insufficient_inventory",
  "reason_params": {"available_kg": 248.0, "batch_kg": 500.0}
}
```

`attribution` re-solves the same target under progressively fewer restrictions,
so it separates a color the materials simply cannot make from one blocked only
by stock levels, shop-floor constraints, or the dispensing scale. Constraint
combinations that no recipe can satisfy are rejected up front with the blocking
rule named, rather than returning a bare search failure.

Use `POST /api/target/validate` for source-specific target metadata. It
accepts `spectrophotometer`, `lab`, `controlled_image`, and `hex` payloads and
returns `pending` calibration status until a validated material calibration is
configured.

```bash
curl -X POST http://127.0.0.1:8000/api/target/validate \
  -H 'Content-Type: application/json' \
  -d '{"source": "hex", "hex_color": "#EE4C3A"}'
```

## Production roadmap

The current model is intentionally a digital estimator. Pigments mix through absorption and scattering, not simple RGB addition. For production use:

1. Photograph samples under a controlled D65 light booth with a color calibration card—or use a spectrophotometer.
2. Measure each resin/pigment combination at several known concentrations.
3. Fit wavelength-dependent Kubelka–Munk absorption/scattering coefficients.
4. Train a residual model from historical lab recipes and measured outcomes.
5. Add tolerances for resin grade, opacity, wall thickness, temperature, moisture, and machine settings.
6. Close the loop by feeding every lab correction back into the model.

See [`docs/system-improvement-roadmap.md`](docs/system-improvement-roadmap.md) for the detailed technical review, prioritized engineering refinements, calibration plan, and machine-learning strategy.
The executable measurement contract is in [`docs/physical-calibration-protocol.md`](docs/physical-calibration-protocol.md), with evaluation guidance in [`docs/evaluation-protocol.md`](docs/evaluation-protocol.md).

## Test

```bash
uv run pytest -q
```
