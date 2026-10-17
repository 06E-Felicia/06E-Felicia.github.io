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


def face_flux(state, terrain, axis, higher_order=False):
    dimension = axis + 1
    pad = [(0, 0)] * 3; pad[dimension] = (1, 1)
    # Continue an outgoing current across the open edge. A permanently DRY
    # ghost made the rectangle itself a density-current front, launching
    # rarefactions and convergence whenever a real pool reached the boundary.
    padded = np.pad(state, pad, mode='edge')
    bed_pad = [(0, 0)] * 2; bed_pad[axis] = (1, 1)
    bed = np.pad(terrain, bed_pad, mode='edge')
    left = [slice(None)] * 3; right = left.copy()
    left[dimension] = slice(None, -1); right[dimension] = slice(1, None)
    lo, hi = padded[tuple(left)], padded[tuple(right)]
    bl = [slice(None)] * 2; br = bl.copy()
    bl[axis] = slice(None, -1); br[axis] = slice(1, None)
    zl, zr = bed[tuple(bl)], bed[tuple(br)]
    if higher_order:
        # Limit free-surface elevation (not depth), buoyancy and velocities.
        # A first-order HLL head spreads several cells in a few hours, putting
        # processed cold air into every nearby warm-inflow donor. Reconstruct
        # the head without prescribing a contour or borrowing distant donors.
        h=state[0];u,v=velocity(h,state[2],state[3])
        variables=[h+terrain,state[1]/np.maximum(h,1e-20),u,v]
        variables.extend([a/np.maximum(h,1e-20) for a in state[4:]])
        variables=np.stack(variables);extended=np.pad(variables,pad,mode='edge')
        centre=[slice(None)]*3;centre[dimension]=slice(1,-1)
        before=centre.copy();after=centre.copy();before[dimension]=slice(None,-2);after[dimension]=slice(2,None)
        a=extended[tuple(centre)]-extended[tuple(before)];b=extended[tuple(after)]-extended[tuple(centre)]
        slope=np.where(a*b>0,np.where(a>0,np.minimum(a,b),np.maximum(a,b)),0)
        slope[0]=np.clip(slope[0],-2*h,2*h)
        positive=variables+slope*.5;negative=variables-slope*.5
        # The exterior is a zero-gradient continuation, not a dry wall.
        plus=np.pad(positive,pad,mode='edge');minus=np.pad(negative,pad,mode='edge')
        a=plus[tuple(left)];b=minus[tuple(right)]
        hl0=np.maximum(a[0]-zl,0);hr0=np.maximum(b[0]-zr,0)
        hl0=np.where(lo[0]>0,hl0,0);hr0=np.where(hi[0]>0,hr0,0)
        lo=np.stack([hl0,hl0*np.maximum(a[1],0),hl0*a[2],hl0*a[3],*[hl0*a[k] for k in range(4,len(state))]])
        hi=np.stack([hr0,hr0*np.maximum(b[1],0),hr0*b[2],hr0*b[3],*[hr0*b[k] for k in range(4,len(state))]])
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
    # Diode boundary: export water/debt/momentum, never import an artificial
    # exterior pool. Retain hydrostatic pressure even when mass inflow stops.
    for index,outward in [(0,-1),(-1,1)]:
        face=[slice(None)]*3;face[dimension]=index;face=tuple(face)
        pressure=(pl+pr)*.5
        pface=[slice(None)]*2;pface[axis]=index
        incoming=outward*flux[face][0]<0
        edge=flux[face].copy();edge[:,incoming]=0
        edge[normal]=np.where(incoming,pressure[tuple(pface)],edge[normal])
        flux[face]=edge
    # Cell-sided hydrostatic pressure corrections balance resting pools on
    # terrain and block a shallow current at a ridge higher than its head.
    correction_lo = .5 * GRAVITY * (lo[1] * lo[0] - a[1] * hl)
    correction_hi = .5 * GRAVITY * (hi[1] * hi[0] - b[1] * hr)
    return flux, correction_lo, correction_hi


def advance(depth, content, mx, my, terrain, duration, dx, tracer=None,higher_order=False):
    fields=[depth,content,mx,my]
    if tracer is not None:
        fields.extend(tracer if np.ndim(tracer)==3 else [tracer])
    state = np.stack(fields).astype('float64')
    remaining = duration; external = 0.; max_cfl = 0.
    while remaining > 1e-8:
        u, v = velocity(state[0], state[2], state[3])
        c = np.sqrt(GRAVITY * np.maximum(state[1], 0))
        # Two horizontal directions and wet/dry rarefaction speeds included.
        speed = float(np.max(np.abs(u) + np.abs(v) + 4 * c))
        dt = min(remaining, .4 * dx / max(speed, 1))
        max_cfl = max(max_cfl, dt * speed / dx)
        def tendency(a):
            fx,xl,xr=face_flux(a,terrain,1,higher_order)
            fy,yl,yr=face_flux(a,terrain,0,higher_order)
            change=-(np.diff(fx,axis=2)+np.diff(fy,axis=1))/dx
            change[2]-=(xl[:,1:]-xr[:,:-1])/dx
            change[3]-=(yl[1:,:]-yr[:-1,:])/dx
            external_rate=-(float(np.sum(fx[1,:,-1]-fx[1,:,0]))+float(np.sum(fy[1,-1,:]-fy[1,0,:])))/dx
            return change,external_rate
        if higher_order:
            change,rate=tendency(state);first=state+dt*change
            change2,rate2=tendency(first)
            state=.5*(state+first+dt*change2);external+=.5*dt*(rate+rate2)
        else:
            # Keep the paused Sol branch's operation ordering bit-for-bit.
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
