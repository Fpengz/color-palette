# Repository Guidelines

## Project Structure & Module Organization

Chromix is a Python 3.12 FastAPI application with a browser frontend.

- `app/main.py`: API routes, validation models, and static-file serving.
- `app/color.py`: color parsing and RGB/Lab conversions.
- `app/extraction.py`: image validation and dominant-palette extraction.
- `app/mixing.py`: Kubelka–Munk estimation and constrained recipe optimization.
- `app/static/`: the HTML, CSS, and vanilla JavaScript pitch interface.
- `tests/`: pytest unit and API tests, organized by the matching application module.
- `example/`: demo product images, material data, and presentation instructions.

Keep color science and optimization logic out of routes. Routes should validate input, call domain functions, and translate known failures into clear HTTP responses.

## Build, Test, and Development Commands

Use `uv` for all Python environment and dependency operations.

```bash
uv sync                              # Install locked runtime and dev dependencies
uv run uvicorn app.main:app --reload # Start the local development server
uv run pytest -q                     # Run the complete test suite
uv build                             # Build source and wheel distributions
```

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
