//! Inner solve loop for Chromix recipe optimization.
//!
//! `app/mixing.py` is the reference implementation and stays authoritative. This
//! crate exists because the objective is evaluated tens of thousands of times per
//! request on three-channel data, where the cost is dominated by crossing into
//! and out of Python and SciPy rather than by arithmetic. Running an entire
//! active set's multistart in one call removes those crossings.
//!
//! The optimizer is a spectral projected gradient method rather than a port of
//! SLSQP. The feasible set here is only `sum(x) == 1` with box bounds, which is
//! convex and cheap to project onto, so the general nonlinear-constraint
//! machinery SLSQP carries is not needed.

const LAB_DELTA: f64 = 6.0 / 29.0;
const KS_GRADIENT_FLOOR: f64 = 1e-9;
const SPARSITY_EPSILON: f64 = 1e-8;

/// Linear RGB -> XYZ (D65), pre-divided by the white point.
const SCALED: [[f64; 3]; 3] = [
    [0.4124564 / 0.95047, 0.2126729, 0.0193339 / 1.08883],
    [0.3575761 / 0.95047, 0.7151522, 0.1191920 / 1.08883],
    [0.1804375 / 0.95047, 0.0721750, 0.9503041 / 1.08883],
];

/// Project onto `{ lower <= x <= upper, sum(x) == 1 }` by bisecting the shift.
///
/// Mirrors `_project_capped_simplex` in `app/mixing.py`: work in `z = x - lower`
/// so the target set is a capped simplex, then shift back.
fn project(values: &[f64], lower: &[f64], caps: &[f64], total: f64, out: &mut [f64]) {
    let n = values.len();
    let mut low = f64::INFINITY;
    let mut high = f64::NEG_INFINITY;
    for i in 0..n {
        let shifted = values[i] - lower[i];
        low = low.min(shifted - caps[i]);
        high = high.max(shifted);
    }
    if total <= 0.0 {
        out[..n].copy_from_slice(&lower[..n]);
        return;
    }
    for _ in 0..80 {
        let mid = 0.5 * (low + high);
        let mut sum = 0.0;
        for i in 0..n {
            sum += (values[i] - lower[i] - mid).clamp(0.0, caps[i]);
        }
        if sum > total {
            low = mid;
        } else {
            high = mid;
        }
    }
    let mut sum = 0.0;
    for i in 0..n {
        let z = (values[i] - lower[i] - high).clamp(0.0, caps[i]);
        out[i] = lower[i] + z;
        sum += z;
    }
    // Push the bisection residual onto a component that has headroom.
    let residual = total - sum;
    if residual.abs() > 1e-12 {
        for i in 0..n {
            let z = out[i] - lower[i];
            if z + residual >= -1e-15 && z + residual <= caps[i] + 1e-15 {
                out[i] += residual;
                break;
            }
        }
    }
}

/// Squared CIELAB distance to the target, plus the sparsity term, and gradient.
fn objective(
    x: &[f64],
    ks: &[f64],
    target_lab: &[f64],
    sparsity_weight: f64,
    gradient: &mut [f64],
) -> f64 {
    let n = x.len();
    let delta3 = LAB_DELTA * LAB_DELTA * LAB_DELTA;
    let linear_slope = 1.0 / (3.0 * LAB_DELTA * LAB_DELTA);

    let mut mixed = [0.0f64; 3];
    for i in 0..n {
        let weight = x[i].max(0.0);
        for c in 0..3 {
            mixed[c] += weight * ks[i * 3 + c];
        }
    }

    let mut reflect = [0.0f64; 3];
    let mut d_reflect = [0.0f64; 3];
    for c in 0..3 {
        let k = mixed[c].max(0.0);
        // 1/(1+k+sqrt(k^2+2k)) instead of 1+k-sqrt(k^2+2k): algebraically equal,
        // but the subtraction cancels catastrophically once K/S is large.
        reflect[c] = 1.0 / (1.0 + k + (k * k + 2.0 * k).sqrt());
        let guarded = k.max(KS_GRADIENT_FLOOR);
        let root = (guarded * guarded + 2.0 * guarded).sqrt();
        d_reflect[c] = -reflect[c] * reflect[c] * (1.0 + (guarded + 1.0) / root);
    }

    let mut f = [0.0f64; 3];
    let mut d_f = [0.0f64; 3];
    for c in 0..3 {
        let mut v = 0.0;
        for j in 0..3 {
            v += reflect[j] * SCALED[j][c];
        }
        if v > delta3 {
            let root3 = v.cbrt();
            f[c] = root3;
            d_f[c] = 1.0 / (3.0 * root3 * root3);
        } else {
            f[c] = v * linear_slope + 4.0 / 29.0;
            d_f[c] = linear_slope;
        }
    }

    let diff = [
        116.0 * f[1] - 16.0 - target_lab[0],
        500.0 * (f[0] - f[1]) - target_lab[1],
        200.0 * (f[1] - f[2]) - target_lab[2],
    ];

    // d(loss)/d(f) = A^T (2 * diff), with A the Lab-from-f matrix.
    let g_f = [
        2.0 * (500.0 * diff[1]),
        2.0 * (116.0 * diff[0] - 500.0 * diff[1] + 200.0 * diff[2]),
        2.0 * (-200.0 * diff[2]),
    ];
    let mut g_ks = [0.0f64; 3];
    for j in 0..3 {
        let mut v = 0.0;
        for c in 0..3 {
            v += SCALED[j][c] * (g_f[c] * d_f[c]);
        }
        g_ks[j] = v * d_reflect[j];
    }

    let mut total = diff[0] * diff[0] + diff[1] * diff[1] + diff[2] * diff[2];
    for i in 0..n {
        let mut v = 0.0;
        for c in 0..3 {
            v += ks[i * 3 + c] * g_ks[c];
        }
        let safe = x[i].max(0.0);
        let root = (safe + SPARSITY_EPSILON).sqrt();
        total += sparsity_weight * root;
        gradient[i] = if x[i] < 0.0 {
            0.0
        } else {
            v + sparsity_weight * 0.5 / root
        };
    }
    total
}

/// Spectral projected gradient with Barzilai-Borwein steps and a nonmonotone
/// line search (Grippo-Lampariello-Lucidi). Returns the final objective value.
#[allow(clippy::too_many_arguments)]
fn spg(
    x: &mut Vec<f64>,
    ks: &[f64],
    target_lab: &[f64],
    lower: &[f64],
    caps: &[f64],
    total_mass: f64,
    sparsity_weight: f64,
    max_iter: usize,
    converged: &mut bool,
) -> f64 {
    const MEMORY: usize = 10;
    const GAMMA: f64 = 1e-4;
    // K/S spans zero to ~5e5 across a palette, so an optimal fraction can sit
    // near 1e-5 and the Barzilai-Borwein step that reaches it near 1e-12. A
    // conventional 1e-10 floor clamps exactly those steps away and strands the
    // solver short of the optimum on high-contrast material sets.
    const ALPHA_MIN: f64 = 1e-30;
    const ALPHA_MAX: f64 = 1e10;
    const TOLERANCE: f64 = 1e-10;
    // The projected-direction norm is scaled by the Barzilai-Borwein step, so it
    // is a poor stopping test on its own. Declare convergence on a stalled
    // objective instead, mirroring what SLSQP's `ftol` does.
    const FTOL: f64 = 1e-12;
    const STALLS_TO_STOP: u32 = 2;

    let n = x.len();
    let mut gradient = vec![0.0; n];
    let mut candidate = vec![0.0; n];
    let mut trial = vec![0.0; n];
    let mut direction = vec![0.0; n];
    let mut previous_gradient = vec![0.0; n];
    let mut history: Vec<f64> = Vec::with_capacity(MEMORY);

    let mut value = objective(x, ks, target_lab, sparsity_weight, &mut gradient);
    let mut alpha = 1.0f64;
    let mut stalls = 0u32;
    *converged = false;

    for _ in 0..max_iter {
        for i in 0..n {
            candidate[i] = x[i] - alpha * gradient[i];
        }
        project(&candidate, lower, caps, total_mass, &mut direction);
        let mut slope = 0.0;
        let mut norm = 0.0f64;
        for i in 0..n {
            direction[i] -= x[i];
            slope += gradient[i] * direction[i];
            norm = norm.max(direction[i].abs());
        }
        if norm < TOLERANCE {
            *converged = true;
            break;
        }
        // A projected direction is a descent direction; guard against roundoff.
        if slope >= 0.0 {
            *converged = true;
            break;
        }

        history.push(value);
        if history.len() > MEMORY {
            history.remove(0);
        }
        let reference = history.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

        let mut step = 1.0f64;
        let mut trial_value = value;
        let mut accepted = false;
        for _ in 0..30 {
            for i in 0..n {
                trial[i] = x[i] + step * direction[i];
            }
            trial_value = objective(&trial, ks, target_lab, sparsity_weight, &mut previous_gradient);
            if trial_value.is_finite() && trial_value <= reference + GAMMA * step * slope {
                accepted = true;
                break;
            }
            step *= 0.5;
            if step < 1e-14 {
                break;
            }
        }
        if !accepted {
            *converged = true;
            break;
        }

        // Barzilai-Borwein step from the accepted move.
        let mut s_dot_s = 0.0;
        let mut s_dot_y = 0.0;
        for i in 0..n {
            let s = trial[i] - x[i];
            let y = previous_gradient[i] - gradient[i];
            s_dot_s += s * s;
            s_dot_y += s * y;
        }
        if (value - trial_value).abs() <= FTOL * value.abs().max(1.0) {
            stalls += 1;
        } else {
            stalls = 0;
        }
        x.copy_from_slice(&trial);
        gradient.copy_from_slice(&previous_gradient);
        value = trial_value;
        if stalls >= STALLS_TO_STOP {
            *converged = true;
            break;
        }
        alpha = if s_dot_y > 1e-30 {
            (s_dot_s / s_dot_y).clamp(ALPHA_MIN, ALPHA_MAX)
        } else {
            ALPHA_MAX
        };
    }
    value
}

/// Optimize every start for one active set.
///
/// # Safety
/// All pointers must reference the element counts implied by `n` and `starts`,
/// and must stay valid for the duration of the call.
#[no_mangle]
pub unsafe extern "C" fn chromix_solve_starts(
    ks: *const f64,
    target_lab: *const f64,
    lower: *const f64,
    upper: *const f64,
    starts: *const f64,
    n: usize,
    start_count: usize,
    max_iter: usize,
    sparsity_weight: f64,
    out_x: *mut f64,
    out_loss: *mut f64,
    out_converged: *mut i32,
) -> i32 {
    if ks.is_null() || target_lab.is_null() || lower.is_null() || upper.is_null() {
        return -1;
    }
    if starts.is_null() || out_x.is_null() || out_loss.is_null() || out_converged.is_null() {
        return -1;
    }
    if n == 0 || start_count == 0 {
        return -1;
    }
    let ks = std::slice::from_raw_parts(ks, n * 3);
    let target_lab = std::slice::from_raw_parts(target_lab, 3);
    let lower = std::slice::from_raw_parts(lower, n);
    let upper = std::slice::from_raw_parts(upper, n);
    let starts = std::slice::from_raw_parts(starts, n * start_count);
    let out_x = std::slice::from_raw_parts_mut(out_x, n * start_count);
    let out_loss = std::slice::from_raw_parts_mut(out_loss, start_count);
    let out_converged = std::slice::from_raw_parts_mut(out_converged, start_count);

    let caps: Vec<f64> = (0..n).map(|i| (upper[i] - lower[i]).max(0.0)).collect();
    let total_mass = 1.0 - lower.iter().sum::<f64>();

    for s in 0..start_count {
        let mut x = starts[s * n..(s + 1) * n].to_vec();
        let mut converged = false;
        let value = spg(
            &mut x,
            ks,
            target_lab,
            lower,
            &caps,
            total_mass,
            sparsity_weight,
            max_iter,
            &mut converged,
        );
        // Land exactly on the feasible set; the caller revalidates regardless.
        let mut projected = vec![0.0; n];
        project(&x, lower, &caps, total_mass, &mut projected);
        out_x[s * n..(s + 1) * n].copy_from_slice(&projected);
        out_loss[s] = value;
        out_converged[s] = i32::from(converged);
    }
    0
}

/// Objective and gradient for a single point, used to pin this crate against the
/// Python reference in tests.
///
/// # Safety
/// Pointers must reference `n`, `n * 3`, `3`, and `n` elements respectively.
#[no_mangle]
pub unsafe extern "C" fn chromix_color_loss_and_gradient(
    fractions: *const f64,
    ks: *const f64,
    target_lab: *const f64,
    n: i32,
    gradient_out: *mut f64,
) -> f64 {
    let count = n as usize;
    let x = std::slice::from_raw_parts(fractions, count);
    let ks = std::slice::from_raw_parts(ks, count * 3);
    let target_lab = std::slice::from_raw_parts(target_lab, 3);
    let gradient = std::slice::from_raw_parts_mut(gradient_out, count);
    // Sparsity weight zero: this entry point reports the colour term alone.
    objective(x, ks, target_lab, 0.0, gradient)
}
