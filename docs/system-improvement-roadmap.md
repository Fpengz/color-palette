# Chromix System Improvement Roadmap

Status: software implementation complete; physical evidence pending
Reviewed: 2026-08-14
Scope: color capture, material formulation, calibration, and production
readiness

Implementation note: the current prototype implements the Phase 1 P0 slices
CAP-1 through CAP-3, MIX-1, MIX-2, API-1, and TEST-1; the API-2
status/telemetry slice; MIX-3 operational constraints; and software
foundations for spectral calibration, versioned sample records, residual
models, evaluation, active learning, and safe shadow/fallback serving. Real
material calibration, held-out physical validation, and production sign-off
remain external evidence gates, not claims that software tests can satisfy.

## Executive recommendation

Chromix is a deterministic pitch prototype, not a manufacturing-grade color
control system. The prototype can demonstrate a useful workflow—from an image
to a selectable color and an inventory-aware recipe—but its current accuracy
score only measures agreement with its own digital model.

The recommended order of work is:

1. make the prototype's target selection, upload handling, optimizer output,
   and quality labels trustworthy;
2. establish a repeatable spectral measurement and sample-preparation process;
3. fit and validate a wavelength-dependent physical baseline; and
4. add a learned residual model and calibrated uncertainty only after the
   measurement data is reliable.

Do not present a low digital Delta E as evidence that a manufactured sample
will pass. The application should remain explicitly labeled as an estimate
until it has passed the physical validation gates in this document.

## Current baseline

### Color capture

The current implementation in `app/extraction.py`:

1. accepts the complete request body in the route, then checks its byte length;
2. applies EXIF orientation, converts to RGBA, and checks decoded pixel count;
3. downsizes to at most 360 × 360 pixels and samples at most 45,000 visible
   pixels;
4. discards pixels with alpha below 32, but does not weight the remaining
   pixels by alpha;
5. clusters gamma-encoded RGB pixels with deterministic farthest-point seeded
   k-means; and
6. returns centroids as sRGB, Lab, palette shares, source/ROI metadata, decoded
   format metadata, and uncalibrated model status.

The pipeline is bounded and repeatable. The API can analyze the whole frame or
an explicit pixel ROI and returns the full-frame palette as context in either
case. The frontend no longer silently promotes the largest full-frame cluster
to the product target; the user must choose a swatch, enter a hex value, or
drag-select a region. This matters when the subject is smaller than its
background. The bundled examples make the problem measurable:

| Example | Current dominant centroid | Share | Product-color swatches in the example guide |
| --- | --- | ---: | --- |
| `coral-cup.png` | `#ECE1D8` (studio background) | 68.6% | `#D0362B`, `#EE4C3A`, `#EB6B58` |
| `teal-crate.png` | `#D5D4D4` (studio background) | 52.1% | `#043B3C`, `#0C5A5C`, `#25787B` |
| `yellow-hard-hat.png` | `#EDDECF` (studio background) | 61.1% | `#EEA806`, `#EFB748` |

These are extraction results from the current code and bundled files, not
certified measurements of the products. They are a regression fixture for
target-selection behavior, not a promise that an automatic segmenter will
recover the object in every customer photograph.

The current API also has important boundary behavior:

- `POST /api/extract` validates the decoded PNG, JPEG, or WebP format and does
  not trust the client-provided MIME type;
- the route reads uploads in bounded chunks and stops at the 12 MB application
  limit;
- the response reports analyzed dimensions as `width` and `height` and now
  includes `original_width` and `original_height`, first-frame animation
  metadata, ICC conversion status, and alpha policy; and
- `app/main.py` dispatches image decoding and clustering to a threadpool so the
  async route does not perform CPU-heavy work directly on the event loop.

### Material formulation

The current implementation in `app/mixing.py`:

1. converts each ingredient's entered sRGB color to three linear RGB values;
2. treats those three values as reflectance channels and derives K/S ratios;
3. multiplies each ingredient's K/S values by its scalar `strength` input;
4. mixes the channel-wise K/S values with an opaque Kubelka–Munk approximation;
5. minimizes squared CIELAB distance with SLSQP and deterministic multi-starts;
6. projects candidates onto a continuous capped simplex so fractions are
   nonnegative, within inventory caps, and sum to one; and
7. requires successful optimizer termination or an explicitly bounded,
   near-feasible SLSQP iterate, rechecks feasibility, rounds a single
   constrained dispensing vector to 0.0001 kg, and derives displayed mass,
   percentage, and cost from that vector.

The route/domain separation, explicit Pydantic bounds, deterministic
initialization, inventory caps, and mass-simplex projection are foundations to
retain. The current suite has 60 tests, including ROI/API source behavior,
decoded-format and metadata fixtures, CIEDE2000 reference pairs, optimizer
failure handling, dispensing rounding, and a simple mass/inventory case. It
still does not establish physical accuracy or calibration invariants needed
for production use.

The current prototype also accepts operational recipe constraints through the
API: minimum dose, dispensing increment, locked materials, mutually exclusive
groups, preferred ingredient count, correction masses, and a cost objective
within a declared color tolerance.

## Accuracy limitations and product boundaries

### RGB is insufficient for physical pigment formulation

The current model uses three display channels as a proxy for reflectance. Real
materials have wavelength-dependent absorption and scattering. Distinct
reflectance spectra can produce the same RGB or Lab value while mixing
differently or producing a metameric match under another illuminant.

A calibrated system must operate on measured spectral reflectance and estimate
separate `K(lambda)` and `S(lambda)` behavior for the applicable material
system. Combining precomputed RGB-channel K/S values is not a substitute when
ingredients have different scattering behavior.

### Tint strength is not physically anchored

The current `strength` is a scalar multiplier on K/S derived from the entered
display color. It is not a concentration, loading, or hiding-power measurement.
At strengths other than one, an ingredient used at 100% need not reproduce its
entered color.

Every material must have explicit semantics, for example:

- base resin or opacifier;
- pigment powder;
- masterbatch with a known carrier and pigment loading; or
- finished colored compound.

Strength and concentration behavior must be fitted from measured ladders for
the supported resin, substrate, thickness, opacity, and process. Until then,
the UI should call this field a relative model parameter rather than a
calibrated tint strength.

### A camera color is not a certified material target

An ordinary photograph combines illumination, camera response, white balance,
compression, glare, surface shape, and reflected surroundings. It cannot by
itself provide production-grade material reflectance.

Production target inputs should be accepted in this order of preference:

1. a spectrophotometer reflectance spectrum with raw measurement metadata;
2. Lab values with illuminant, observer, measurement geometry, and SCI/SCE
   metadata; or
3. a controlled light-booth image containing a supported calibration card.

Image-derived colors remain estimates. The API and interface must distinguish
`digital_model_fit` from a measured manufacturing prediction.

### Delta E and quality labels are provisional

The optimizer still minimizes squared CIELAB distance, while the user-facing
`delta_e` is now explicitly labeled CIEDE2000 and covered by reference-pair
tests. Acceptance limits must be set by product family, surface, gloss,
opacity, and customer requirements; there is no universal "good" threshold
for all products.

The current quality labels (`Excellent`, `Good`, `Approximate`, and `Needs
calibration`) describe fit inside the digital model. They must not be shown as
confidence in a physical result. A calibrated result needs a separate status,
domain-of-validity check, and uncertainty estimate.

## Target architecture

Use a hybrid physical-and-data forward model. Keep inverse recipe selection as
constrained optimization because many recipes can match one target and plant
constraints change independently of model training.

```text
recipe + material lot + process conditions
                    |
          spectral physical baseline
                    |
          baseline reflectance spectrum
                    |
       learned residual / error correction
                    |
       spectrum + calibrated uncertainty
                    |
       Lab under selected illuminants
                    |
        Delta E00 + metamerism checks
                    |
       constrained recipe optimization
```

Every prediction should carry the target provenance, material and lot
identifiers, process assumptions, physical-model version, residual-model
version, calibration dataset version, optimizer status, and uncertainty or
reason that uncertainty is unavailable.

## Prioritized engineering backlog

The first workstream is deliberately limited to changes that can be validated
without production measurement data. Priority indicates ordering, not a
commitment to a delivery date.

| ID | Priority | Work | Owner / dependency | Exit evidence |
| --- | --- | --- | --- | --- |
| CAP-1 | P0 | Add crop/ROI selection and an explicit target-selection mode. Keep the full-frame palette available, but do not silently call its largest cluster the product. | Frontend + API; none | A user can select a region or swatch, the response records its source, and the three bundled examples no longer default to the neutral background when the product is selected. |
| CAP-2 | P0 | Define image color semantics: preserve original dimensions, honor or reject ICC profiles explicitly, define alpha handling, and define first-frame/animation behavior. | Color engineering; CAP-1 | Fixture tests cover EXIF rotation, ICC profile, alpha, animation, malformed content, and dimensions with documented expected outputs. |
| CAP-3 | P0 | Enforce the byte ceiling while reading the upload, then move decode and clustering off the async event loop. | API/runtime; none | Oversized bodies are rejected without being fully buffered by application code, and concurrency tests show image work does not block unrelated requests. |
| MIX-1 | P0 | Implement CIEDE2000, retain a clearly named CIE76 field only for compatibility if needed, and label the displayed score as digital-model fit. | Color engineering; reference pairs | Published reference-pair tests pass; API field names identify the metric and UI copy does not imply physical accuracy. |
| MIX-2 | P0 | Validate optimizer status, finite values, feasibility, and post-rounding constraints. Make the final dispensing vector the source of mass, percentage, and cost outputs. | Optimization; MIX-1 | Property tests show exact allowed mass within dispensing precision, no rounded row exceeds inventory, and reported cost equals the displayed masses. Failed or infeasible solves return an explicit error/status. |
| MIX-3 | P1 | Add minimum dose, scale increment, locked ingredient, mutually exclusive ingredient, preferred ingredient-count, and correction-recipe constraints. | Operations + optimization; MIX-2 | Each constraint has an API contract and a solver test for feasible and infeasible cases. |
| API-1 | P0 | Normalize and validate material names, reject non-finite numeric values, define decoded-format allowlists, and return structured validation errors. | API; none | Whitespace-only names, NaN/Infinity, duplicate identifiers, unsupported decoded formats, and malformed multipart requests have stable responses. |
| API-2 | P1 | Return model version, calibration status, optimizer status, input provenance, and structured timing/failure telemetry without logging proprietary recipes. | API + operations; MIX-1 | Contract tests cover success, known failure, and unavailable-calibration states; telemetry review shows no recipe or customer-image leakage. |
| TEST-1 | P0 | Expand invariant and regression coverage around extraction, optimization, API validation, and output rounding. | Engineering; CAP/MIX items | CI runs deterministic tests for the complete P0 exit checklist. |

## Delivery phases and gates

### Phase 1 — trustworthy prototype

The P0 backlog is implemented in code. The phase gate below remains required
before changing the product's positioning. The prototype may continue using
its three-channel digital model, but its behavior must be honest, bounded, and
reproducible.

Required outcomes:

1. target selection is explicit and the neutral background is not silently
   treated as the product;
2. original versus analyzed image dimensions are distinguishable;
3. uploads have an enforced byte ceiling, decoded-format policy, and documented
   alpha/ICC/animation behavior;
4. CIEDE2000 is tested and the score is identified as a digital-model result;
5. optimizer failures and infeasible constraints are not presented as valid
   recipes;
6. displayed masses, percentages, inventory caps, and cost agree after
   dispensing-unit rounding; and
7. model, metric, and calibration status are visible in the API response.

Phase 1 gate: a repeatable test run passes the P0 exit checklist, and a product
review confirms that no UI copy implies that a photograph or low Delta E alone
certifies a production match.

### Phase 2 — establish physical calibration

This phase requires a laboratory or manufacturing partner and cannot be
completed by software changes alone.

The software-side protocol and spectral foundations are available in
[`docs/physical-calibration-protocol.md`](physical-calibration-protocol.md),
`app/spectral.py`, and `app/data_contract.py`. They remain disabled as a
production claim until measured records satisfy the gate below.

#### 2.1 Define the measurement contract

Before collecting training data, document and version:

- supported resin, substrate, pigment, and masterbatch roles;
- sample preparation, mixing, molding/printing, conditioning, and thickness;
- instrument make/model, calibration standards, wavelength range and interval;
- illuminant and observer used for derived Lab values;
- measurement geometry and SCI/SCE mode;
- gloss, texture, opacity, and surface-finish descriptors;
- repeat measurements, operator, date, environment, and acceptance tolerance;
  and
- the identifier and revision of the recipe, material lot, and process setup.

#### 2.2 Build concentration ladders

For each supported material system, measure concentration ladders with
replicates across relevant lots and process conditions. Record pure and base
states where physically meaningful. Do not infer tint strength from a display
swatch or from one end-point sample.

#### 2.3 Fit a spectral baseline

Store raw spectra and fit wavelength-dependent absorption/scattering behavior
for the actual material system. Validate the baseline on samples separated by
time, lot, and recipe family. Include mixtures that expose interactions,
opacity limits, and differences between expected and actual scattering.

#### 2.4 Validate the target path

Compare spectrophotometer targets, metadata-complete Lab targets, and controlled
camera targets. Measure matches under every illuminant relevant to the product
and flag metameric recipes rather than selecting only the best score under one
condition.

Phase 2 gate: the physical baseline has a predeclared evaluation protocol,
held-out samples, product-specific tolerances, and traceable measurements. No
production claim should be made merely because the baseline fits its training
ladder.

### Phase 3 — close the learning loop

Only after Phase 2 has produced reliable measurements:

The software-side residual baseline, calibration-set uncertainty, OOD scoring,
active-learning selection, leakage-resistant evaluation, and shadow/fallback
serving policy are implemented in `app/residual.py`, `app/evaluation.py`, and
`app/serving.py`. Training and calibration artifacts still require the external
measurement dataset described by Phase 2.

1. store predictions, physical outcomes, corrections, and acceptance decisions
   as versioned records outside this source repository;
2. train transparent residual baselines against the spectral physical model;
3. compare Gaussian-process, boosted-tree, and regularized spectral residual
   baselines as appropriate to dataset size and feature types;
4. calibrate uncertainty and detect out-of-domain materials, lots, colors, and
   process conditions;
5. use active learning to select laboratory samples that reduce uncertainty or
   cover weak regions of recipe space; and
6. consider deeper models only if simpler models and the physical baseline have
   been evaluated on the same held-out data and a measurable performance gain
   justifies the operational cost.

Roll out a learned correction in shadow mode first. A fallback to the physical
baseline must remain available, and a model cannot expand its supported domain
without new validation data.

## Data contract for measured samples

Each physical sample record should contain, at minimum:

- unique sample, batch, recipe, prediction, correction, and acceptance IDs;
- exact ingredient quantities, units, material roles, supplier/product IDs,
  lots, and carrier/base resin;
- substrate, process settings, thickness, opacity, gloss, texture, and
  conditioning state;
- full measured reflectance spectrum, instrument metadata, calibration
  evidence, raw-file location, and derived Lab values;
- illuminant, observer, geometry, and SCI/SCE metadata;
- model, optimizer, calibration, and data-schema versions;
- initial prediction, every laboratory correction round, final measurement,
  final acceptance decision, and applicable tolerance; and
- provenance and retention classification for any customer-associated image.

Units and measurement conditions must be explicit. Keep customer images,
proprietary recipes, credentials, raw production measurements, and any other
sensitive records in approved external storage; do not commit them to this
repository.

## Evaluation protocol

The executable contract and release guidance are also recorded in
[`docs/evaluation-protocol.md`](evaluation-protocol.md).

Every learned model must be compared with the spectral physical baseline on the
same untouched test set. Split by time, material lot, and recipe family so
replicates and near-duplicates cannot leak across train and test partitions.

Track at least:

- median, 90th-percentile, and worst-case Delta E00;
- first-shot pass rate at each product-specific tolerance;
- laboratory correction rounds and time to accepted sample;
- recipe cost, ingredient count, and material availability;
- constraint violations before and after dispensing-unit rounding;
- results by color region, resin, substrate, lot, machine, and surface finish;
- uncertainty-interval coverage and interval sharpness; and
- out-of-distribution detection recall on deliberately unfamiliar inputs.

Report confidence intervals and sample counts. Averages alone are insufficient
for release decisions because a small number of large failures can be costly.

## Release gates

| Release state | What can be claimed | Minimum evidence |
| --- | --- | --- |
| Demo / current prototype | Deterministic digital estimate and inventory-constrained recipe proposal | Unit/API tests, explicit disclaimer, bounded inputs, and no manufacturing accuracy claim |
| Calibration pilot | Measured-sample workflow for named material systems under named conditions | Versioned measurement protocol, repeatability study, held-out physical samples, and human review of warnings/fallbacks |
| Production candidate | Validated prediction within declared product scope | Product-specific first-shot and tail-error limits, zero post-rounding constraint violations, calibrated uncertainty/OOD warnings, and end-to-end traceability |

Production readiness is a scoped claim. It must name the supported resin,
material lots or lot policy, process, surface, measurement condition, and
tolerance. Passing one product family does not certify another.

## Machine-learning policy

Machine learning is useful for residual correction, foreground segmentation,
and uncertainty estimation, but it should not be the first answer to missing
measurement data.

Start with models appropriate to the data volume and the required
interpretability:

- Gaussian processes when calibrated uncertainty matters and the dataset is
  small enough for their computational cost;
- gradient-boosted trees for heterogeneous lot and process features;
- a small multi-output model for smooth spectral residuals once sample volume
  justifies it; and
- regularized polynomial or spline residual models as transparent baselines.

Foreground or instance segmentation can be considered for uncontrolled
photographs, separately from spectral forward prediction. A direct
target-color-to-recipe network should not be the first production model: the
inverse is non-unique and the network would handle inventory, cost, dosing,
and safety constraints poorly.

## Risks and decisions to resolve

| Risk / open decision | Why it matters | Decision or mitigation |
| --- | --- | --- |
| Target capture is uncontrolled | Lighting and glare can dominate the target before formulation starts | Define the supported capture protocol and require ROI/card guidance when confidence is low |
| Material semantics are ambiguous | A color swatch plus scalar strength does not identify concentration or hiding power | Version a material-role schema and calibration per resin/process |
| Spectral data is sparse or correlated | A model can appear accurate while failing on new lots or recipe regions | Use lot/time/family splits, replicates, uncertainty, and active-learning selection |
| The inverse recipe is non-unique | Several formulations can have similar color but different cost, robustness, or manufacturability | Optimize with explicit operational constraints and treat cost as a secondary objective within a color tolerance |
| Dispensing resolution changes the recipe | A mathematically feasible continuous solution can be infeasible on the shop floor | Model minimum doses and scale increments before a production claim |
| Customer and production data leaks | Images and recipes may be proprietary | Keep sensitive records outside the repository and sanitize telemetry |
| One-illuminant matches are metameric | A match can fail under the customer's viewing condition | Evaluate multiple relevant illuminants and report metamerism |

The next product decisions are the supported material system, target
measurement source, instrument/protocol owner, required dispensing precision,
and product-specific acceptance tolerances. These decisions unblock Phase 2;
they should not be guessed by the software team.

## Success criteria

Chromix may be described as production-ready only within a declared scope and
only when held-out physical samples demonstrate:

- repeatable measurement and sample preparation;
- product-specific first-shot pass rates and tail-error limits;
- no recipe-constraint violations after dispensing-unit rounding;
- calibrated warnings for unfamiliar materials and process conditions;
- tested behavior under the illuminants relevant to the product; and
- traceability from every prediction to its model, calibration, material lot,
  recipe, process, and measurement versions.

Until those criteria are met, the correct product language is "estimated
digital match" or "prototype formulation proposal," not a guaranteed
manufacturing recipe.
