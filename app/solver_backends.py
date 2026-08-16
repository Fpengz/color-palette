"""Optimizer adapters used by the recipe search module."""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from typing import Protocol

import numpy as np
from scipy.optimize import minimize


LossAndGradient = Callable[[np.ndarray], tuple[float, np.ndarray]]
Attempt = tuple[np.ndarray, str | None]
SPARSITY_WEIGHT = 0.002


class OptimizerBackend(Protocol):
    """The small seam shared by the reference and screening adapters."""

    def optimize_starts(
        self,
        starts: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        ingredient_ks: np.ndarray,
        target_lab: np.ndarray,
        max_iter: int,
        loss_and_gradient: LossAndGradient,
    ) -> list[Attempt]: ...


class ScipySLSQPBackend:
    """Reference optimizer used for every recipe that may be dispensed."""

    def optimize_starts(
        self,
        starts: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        ingredient_ks: np.ndarray,
        target_lab: np.ndarray,
        max_iter: int,
        loss_and_gradient: LossAndGradient,
    ) -> list[Attempt]:
        del ingredient_ks, target_lab
        bounds = [(float(low), float(high)) for low, high in zip(lower, upper, strict=True)]
        ones = np.ones(starts.shape[1])
        equality = {
            "type": "eq",
            "fun": lambda values: float(values.sum() - 1.0),
            "jac": lambda values: ones,
        }
        results: list[Attempt] = []
        for start in starts:
            result = minimize(
                loss_and_gradient,
                start,
                method="SLSQP",
                jac=True,
                bounds=bounds,
                constraints=equality,
                options={"maxiter": max_iter, "ftol": 1e-11, "disp": False},
            )
            if result.success:
                results.append((result.x, "converged"))
                continue
            # Status 8 is a line-search stall: the iterate is often still usable.
            usable = (
                getattr(result, "status", None) == 8
                and np.all(np.isfinite(result.x))
                and abs(float(result.x.sum()) - 1.0) <= 1e-3
                and np.all(result.x >= lower - 1e-6)
                and np.all(result.x <= upper + 1e-6)
            )
            results.append((result.x, "iterate") if usable else (result.x, None))
        return results


class RustScreeningBackend:
    """Optional first-order adapter used only to rank active sets cheaply."""

    def __init__(self, solver: object) -> None:
        self.solver = solver

    def optimize_starts(
        self,
        starts: np.ndarray,
        lower: np.ndarray,
        upper: np.ndarray,
        ingredient_ks: np.ndarray,
        target_lab: np.ndarray,
        max_iter: int,
        loss_and_gradient: LossAndGradient,
    ) -> list[Attempt]:
        del loss_and_gradient
        count = starts.shape[1]
        material_ks = np.ascontiguousarray(ingredient_ks, dtype=np.float64)
        target = np.ascontiguousarray(target_lab, dtype=np.float64)
        low = np.ascontiguousarray(lower, dtype=np.float64)
        high = np.ascontiguousarray(upper, dtype=np.float64)
        seeds = np.ascontiguousarray(starts, dtype=np.float64)
        solved = np.empty_like(seeds)
        losses = np.empty(starts.shape[0], dtype=np.float64)
        converged = np.empty(starts.shape[0], dtype=np.int32)
        status = self.solver.solve_starts(
            ctypes.c_void_p(material_ks.ctypes.data),
            ctypes.c_void_p(target.ctypes.data),
            ctypes.c_void_p(low.ctypes.data),
            ctypes.c_void_p(high.ctypes.data),
            ctypes.c_void_p(seeds.ctypes.data),
            count,
            starts.shape[0],
            max_iter,
            SPARSITY_WEIGHT,
            ctypes.c_void_p(solved.ctypes.data),
            ctypes.c_void_p(losses.ctypes.data),
            ctypes.c_void_p(converged.ctypes.data),
        )
        if status != 0:
            raise RuntimeError("Rust screening backend rejected the optimizer arguments")
        return [
            (solved[index], "converged" if converged[index] else "iterate")
            for index in range(starts.shape[0])
        ]


def select_optimizer_backend(solver: object | None = None) -> OptimizerBackend:
    """Select the Rust adapter when available, otherwise the reference adapter."""
    return RustScreeningBackend(solver) if solver is not None else ScipySLSQPBackend()


def optimize_starts(
    starts: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    ingredient_ks: np.ndarray,
    target_lab: np.ndarray,
    max_iter: int,
    loss_and_gradient: LossAndGradient,
    backend: OptimizerBackend | object | None = None,
) -> list[Attempt]:
    """Run a start set through an explicit backend seam.

    The final argument accepts the old native solver object as a compatibility
    convenience for callers that used the original private helper.
    """
    if backend is None:
        selected: OptimizerBackend = ScipySLSQPBackend()
    elif hasattr(backend, "optimize_starts"):
        selected = backend  # type: ignore[assignment]
    else:
        selected = RustScreeningBackend(backend)
    try:
        return selected.optimize_starts(
            starts,
            lower,
            upper,
            ingredient_ks,
            target_lab,
            max_iter,
            loss_and_gradient,
        )
    except RuntimeError:
        # A native adapter is a performance aid, never a correctness dependency.
        if isinstance(selected, RustScreeningBackend):
            return ScipySLSQPBackend().optimize_starts(
                starts,
                lower,
                upper,
                ingredient_ks,
                target_lab,
                max_iter,
                loss_and_gradient,
            )
        raise
