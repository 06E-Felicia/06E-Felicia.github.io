"""Active reduced-gravity layer: depth, buoyancy content and two momenta.

Hydrostatic reconstruction + HLL wet/dry fluxes, not prescribed radial motion.
The overlying atmosphere is a reference layer, not a resolved two-fluid model.
"""
import numpy as np

GRAVITY = 9.80665 / 295.


def velocity(depth, mx, my):
    # Desingularize only the vanishing numerical wet/dry tail (<10 cm).
    factor = 2 * depth / np.maximum(depth * depth + np.maximum(depth * depth, .1**2), 1e-20)
    return mx * factor, my * factor


def face_flux(state, terrain, axis):
    dimension = axis + 1
    pad = [(0, 0)] * 3; pad[dimension] = (1, 1)
    padded = np.pad(state, pad, mode='constant')
    bed_pad = [(0, 0)] * 2; bed_pad[axis] = (1, 1)
    bed = np.pad(terrain, bed_pad, mode='edge')
    left = [slice(None)] * 3; right = left.copy()
    left[dimension] = slice(None, -1); right[dimension] = slice(1, None)
    lo, hi = padded[tuple(left)], padded[tuple(right)]
    bl = [slice(None)] * 2; br = bl.copy()
    bl[axis] = slice(None, -1); br[axis] = slice(1, None)
    zl, zr = bed[tuple(bl)], bed[tuple(br)]
    top = np.maximum(zl, zr)
    hl, hr = np.maximum(0, lo[0] + zl - top), np.maximum(0, hi[0] + zr - top)
    al = hl / np.maximum(lo[0], 1e-20); ar = hr / np.maximum(hi[0], 1e-20)
    a, b = lo * al[None], hi * ar[None]
    ul, vl = velocity(lo[0], lo[2], lo[3]); ur, vr = velocity(hi[0], hi[2], hi[3])
    a[2], a[3] = hl * ul, hl * vl; b[2], b[3] = hr * ur, hr * vr
    un, vn = (ul, ur) if axis == 1 else (vl, vr)
    cl, cr = np.sqrt(GRAVITY * a[1]), np.sqrt(GRAVITY * b[1])
    slow = np.minimum(np.minimum(un - cl, vn - cr), 0)
    fast = np.maximum(np.maximum(un + cl, vn + cr), 0)
    # Exact dry-side rarefaction bounds are +/-2c rather than +/-c.
    slow = np.where(hl == 0, np.minimum(slow, vn - 2 * cr), slow)
    fast = np.where(hr == 0, np.maximum(fast, un + 2 * cl), fast)
    fl, fr = a * un[None], b * vn[None]
    normal = 2 if axis == 1 else 3
    pl, pr = .5 * GRAVITY * a[1] * hl, .5 * GRAVITY * b[1] * hr
    fl[normal] += pl; fr[normal] += pr
    flux = (fast[None] * fl - slow[None] * fr + (slow * fast)[None] * (b - a)) / np.maximum(fast - slow, 1e-20)[None]
    # Cell-sided hydrostatic pressure corrections balance resting pools on
    # terrain and block a shallow current at a ridge higher than its head.
    correction_lo = .5 * GRAVITY * (lo[1] * lo[0] - a[1] * hl)
    correction_hi = .5 * GRAVITY * (hi[1] * hi[0] - b[1] * hr)
    return flux, correction_lo, correction_hi


def advance(depth, content, mx, my, terrain, duration, dx, tracer=None):
    fields=[depth,content,mx,my]
    if tracer is not None:fields.append(tracer)
    state = np.stack(fields).astype('float64')
    remaining = duration; external = 0.; max_cfl = 0.
    while remaining > 1e-8:
        u, v = velocity(state[0], state[2], state[3])
        c = np.sqrt(GRAVITY * np.maximum(state[1], 0))
        # Two horizontal directions and wet/dry rarefaction speeds included.
        speed = float(np.max(np.abs(u) + np.abs(v) + 4 * c))
        dt = min(remaining, .4 * dx / max(speed, 1))
        max_cfl = max(max_cfl, dt * speed / dx)
        fx, xl, xr = face_flux(state, terrain, 1)
        fy, yl, yr = face_flux(state, terrain, 0)
        state -= dt / dx * (np.diff(fx, axis=2) + np.diff(fy, axis=1))
        state[2] -= dt / dx * (xl[:, 1:] - xr[:, :-1])
        state[3] -= dt / dx * (yl[1:, :] - yr[:-1, :])
        external -= dt / dx * (float(np.sum(fx[1, :, -1] - fx[1, :, 0])) + float(np.sum(fy[1, -1, :] - fy[1, 0, :])))
        if min(float(state[0].min()), float(state[1].min())) < -1e-8:
            raise FloatingPointError('Negative density-current depth or buoyancy')
        state[:2] = np.maximum(state[:2], 0)
        if not np.isfinite(state).all(): raise FloatingPointError('Non-finite density current')
        remaining -= dt
    return (*state, external, max_cfl)
