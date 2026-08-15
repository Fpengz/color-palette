# Repository Guidelines

## Project Structure & Module Organization

Chromix is a Python 3.12 FastAPI application with a browser frontend.

- `app/main.py`: API routes, validation models, admission control, and static-file serving.
- `app/errors.py`: user-facing errors carrying a stable code for localization.
- `app/color.py`: color parsing and RGB/Lab conversions.
- `app/extraction.py`: image validation and dominant-palette extraction.
- `app/mixing.py`: Kubelka–Munk estimation and constrained recipe optimization.
- `app/native/`: optional Rust accelerator for the search; never required.
- `app/static/`: the HTML, CSS, and vanilla JavaScript pitch interface.

Foundations for the calibrated path, not yet wired into the demo:

- `app/spectral.py`: wavelength grids, measured spectra, K/S fitting, metamerism.
- `app/data_contract.py`: versioned record schema for measured samples.
- `app/residual.py`: residual model, conformal intervals, active learning.
- `app/evaluation.py`: leakage-resistant splits and held-out reporting.
- `app/serving.py`: shadow/fallback policy for residual corrections.

- `tests/`: pytest unit and API tests, organized by the matching application module.
- `example/`: demo product images, material data, and presentation instructions.
- `docs/`: technical review, calibration protocol, and evaluation protocol.

Keep color science and optimization logic out of routes. Routes should validate input, call domain functions, and translate known failures into clear HTTP responses.

User-facing text is bilingual (English and Chinese). Domain code must not emit
display strings only in English: raise `CodedError` with a stable `code` and
parameters, and add the matching `error_<code>` entry to both locales in
`app/static/app.js`. The same applies to formulation reason and suggestion
codes. `tests/test_localization.py` fails when a locale falls behind.

## Build, Test, and Development Commands

Use `uv` for all Python environment and dependency operations.

```bash
uv sync                              # Install locked runtime and dev dependencies
uv run uvicorn app.main:app --reload # Start the local development server
uv run pytest -q                     # Run the complete test suite
uv build                             # Build source and wheel distributions
uv run python -m app.native          # Optional: build the Rust accelerator
```

Formulation is CPU-bound and GIL-bound, so `app/main.py` runs each solve in a
worker process and bounds how many callers may queue for one. Keep solver work
picklable and free of process-global state, and do not move it back onto the
threadpool: threads measured slower than solving one request at a time.

`app/native/rust/` holds an optional Rust accelerator, built with
`uv run python -m app.native` (needs `cargo`) and ignored by git. It is never
required: without it the SciPy path runs unchanged. It screens candidate
ingredient sets only -- SLSQP still refines whatever gets shipped, because the
crate's projected-gradient method settles for a worse optimum on high-contrast
material sets. Any change to the objective must be made in both `app/mixing.py`
and `src/lib.rs` and kept in agreement; `tests/test_native.py` pins them
together and the Python side stays the reference.

## Coding Style & Naming Conventions

Use four-space indentation, type hints, and concise docstrings for non-obvious Python functions. Follow PEP 8 naming: `snake_case` for functions and variables, `PascalCase` for classes, and uppercase module constants. Prefer small pure functions and explicit boundary validation.

Frontend code uses two-space indentation, `camelCase` JavaScript identifiers, semantic HTML, and kebab-case CSS classes. No automated formatter or linter is configured, so preserve the surrounding style and run `git diff --check` before committing.

## Testing Guidelines

Tests use pytest and FastAPI's `TestClient`. Name files `test_<module>.py` and functions `test_<behavior>`. Add focused tests for color conversions, optimizer constraints, upload edge cases, and API validation. There is no fixed coverage threshold; all tests must pass.

## Commit & Pull Request Guidelines

History uses short, imperative commit subjects such as `Build Chromix color formulation demo` and `Add pitch-ready demo samples`. Keep each commit scoped to one coherent change.

Pull requests should explain the purpose and user impact, list validation commands, and link relevant issues. Include screenshots for interface changes and example request/response payloads for API changes. Call out any modification to color-model assumptions or production-calibration requirements.

## Security & Data Handling

Preserve upload size, pixel-count, MIME-type, and numeric-bound validation. Do not commit customer images, proprietary pigment recipes, credentials, or production measurement data. Treat formulation output as an estimate unless it is calibrated against measured samples.
