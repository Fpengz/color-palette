"""Optional Rust accelerator for the formulation inner loop.

`app/mixing.py` is the reference implementation and stays authoritative. This
package exists because a request evaluates the objective tens of thousands of
times on three-channel data, where the cost is dominated by crossing into and
out of Python and SciPy rather than by arithmetic. The crate runs an entire
active set's multistart in one call, so those crossings collapse from tens of
thousands to a few hundred.

Strictly an accelerator: everything works without a Rust toolchain, in which
case :func:`load_solver` returns ``None`` and the SciPy path runs instead. The
two are pinned against each other in ``tests/test_native.py``.

Build with::

    uv run python -m app.native
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path


CRATE = Path(__file__).resolve().parent / "rust"
LIBRARY_NAME = {
    "win32": "chromix_solver.dll",
    "darwin": "libchromix_solver.dylib",
}.get(sys.platform, "libchromix_solver.so")
LIBRARY = CRATE / "target" / "release" / LIBRARY_NAME
_solver: Solver | None = None
_looked_up = False


class Solver:
    """Thin ctypes binding to the crate's two entry points."""

    def __init__(self, library: ctypes.CDLL) -> None:
        self._library = library
        self.solve_starts = library.chromix_solve_starts
        self.solve_starts.restype = ctypes.c_int
        self.solve_starts.argtypes = [
            ctypes.c_void_p,  # ks
            ctypes.c_void_p,  # target_lab
            ctypes.c_void_p,  # lower
            ctypes.c_void_p,  # upper
            ctypes.c_void_p,  # starts
            ctypes.c_size_t,  # n
            ctypes.c_size_t,  # start_count
            ctypes.c_size_t,  # max_iter
            ctypes.c_double,  # sparsity_weight
            ctypes.c_void_p,  # out_x
            ctypes.c_void_p,  # out_loss
            ctypes.c_void_p,  # out_converged
        ]
        self.color_loss_and_gradient = library.chromix_color_loss_and_gradient
        self.color_loss_and_gradient.restype = ctypes.c_double
        self.color_loss_and_gradient.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
        ]


def build(cargo: str = "cargo") -> Path:
    """Compile the crate in release mode. Returns the library path."""
    subprocess.run([cargo, "build", "--release"], cwd=CRATE, check=True)
    return LIBRARY


def load_solver() -> Solver | None:
    """Return the compiled solver, or None when it is unavailable.

    Cached per process, so worker processes each pay the lookup once.
    """
    global _solver, _looked_up
    if _looked_up:
        return _solver
    _looked_up = True
    if LIBRARY.exists():
        try:
            _solver = Solver(ctypes.CDLL(str(LIBRARY)))
        except (OSError, AttributeError):
            _solver = None
    return _solver
