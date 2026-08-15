"""Build the optional Rust accelerator: ``uv run python -m app.native``."""

from . import build

print(f"built {build()}")
