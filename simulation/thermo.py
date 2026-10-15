"""Vectorized pseudo-adiabatic parcel diagnostics, SI units throughout.

Not a CAPE-driven rain generator. Diagnostics are evaluated from the evolving
pressure-level temperature and mixing-ratio columns. CIN is signed (<= 0).
"""
import numpy as np

RD, CP, G, EPS, LV = 287.05, 1004.0, 9.80665, 0.62195691, 2.50084e6

_accelerator=None


def install_accelerator(callback):
    global _accelerator
    _accelerator=callback


def saturation(t, p):
    e = 611.2 * np.exp(17.67 * (t - 273.15) / np.maximum(t - 29.65, 120))
    return EPS * e / np.maximum(p - e, 100)


def saturation_ice(t, p):
    """Murphy & Koop (2005) saturation over ice, SI; liquid above 0 C.

    Parcel reference calculations deliberately retain liquid saturation.
    This separate function is used only by the prognostic ice reservoir.
    """
    ti=np.maximum(t,110.)
    e=np.exp(9.550426-5723.265/ti+3.53068*np.log(ti)-.00728332*ti)
    return np.where(t<273.15,EPS*e/np.maximum(p-e,100),saturation(t,p))


def dewpoint(q, p):
    e = np.maximum(q, 1e-9) * p / (EPS + np.maximum(q, 1e-9))
    a = np.log(np.maximum(e, .01) / 611.2)
    return 243.5 * a / (17.67 - a) + 273.15


def virtual(t, q):
    return t * (1 + q / EPS) / (1 + q)


def moist_step(t, p0, p1, count=None):
    """RK4 integration of saturated pseudoadiabatic dT/d(ln p)."""
    def rate(temp, pressure):
        r = saturation(temp, pressure)
        return (RD * temp + LV * r) / (CP + LV * LV * r * EPS / (RD * temp * temp))
    lp = np.log(p0); dl = np.log(p1 / p0)
    # Resolve thick upper-tropospheric layers without a fixed moist lapse rate.
    if count is None:count = max(1, int(np.ceil(np.max(np.abs(dl)) / .025)))
    h = dl / count
    if _accelerator is not None and np.ndim(t)>0 and np.shape(t)==np.shape(lp)==np.shape(h):
        source=np.ascontiguousarray(t,dtype='float64');out=np.empty_like(source)
        _accelerator(source,np.ascontiguousarray(lp),np.ascontiguousarray(h),out,count)
        return out
    pressure = np.exp(lp)
    for _ in range(count):
        midpoint = np.exp(lp+h/2); end = np.exp(lp+h)
        a = rate(t, pressure); b = rate(t + a*h/2, midpoint)
        c = rate(t + b*h/2, midpoint); d = rate(t + c*h, end)
        t = t + h*(a+2*b+2*c+d)/6; lp += h
        pressure = end
    return t


def parcel(p, temperature, moisture, kind='surface'):
    """p: (level,) descending Pa; temperature/moisture: (level,...).

    Mixed parcel uses pressure-mass-weighted lowest 100 hPa. Most unstable
    parcel is the maximum approximate equivalent potential temperature in the
    lowest 300 hPa. Returns CAPE, signed CIN, parcel path and LCL pressure.
    """
    p = np.asarray(p, dtype=float)
    if np.any(np.diff(p, axis=0) >= 0) or len(p) < 4:
        raise ValueError('Pressure must strictly decrease, with at least four levels')
    t = np.asarray(temperature); q = np.asarray(moisture)
    if t.shape != q.shape or t.shape[0] != len(p):
        raise ValueError('Incompatible pressure/temperature/moisture shapes')
    shape = (len(p),) + (1,) * (t.ndim - 1)
    pp = np.broadcast_to(p.reshape(shape) if p.ndim == 1 else p, t.shape)
    theta = t * (100000/pp)**(RD/CP)
    start = np.zeros(t.shape[1:], dtype=int)
    if kind == 'mixed':
        weights = np.maximum(0, np.minimum(pp[:-1], pp[0])-np.maximum(pp[1:], pp[0]-10000))
        qt = np.sum((q[:-1]+q[1:])*.5*weights, axis=0)/np.sum(weights, axis=0)
        tt = np.sum((theta[:-1]+theta[1:])*.5*weights, axis=0)/np.sum(weights, axis=0)*(pp[0]/100000)**(RD/CP)
    elif kind == 'unstable':
        te = np.where(pp >= pp[0]-30000, theta*np.exp(LV*q/(CP*t)), -np.inf)
        start = np.argmax(te, axis=0)
        tt = np.take_along_axis(t, start[None], axis=0)[0]
        qt = np.take_along_axis(q, start[None], axis=0)[0]
    elif kind == 'surface':
        tt, qt = t[0], q[0]
    else:
        raise ValueError('Unknown parcel definition')
    ps = np.take_along_axis(pp, start[None], axis=0)[0]
    td = np.minimum(tt, dewpoint(qt, ps))
    tlcl = 1/(1/(td-56) + np.log(tt/td)/800) + 56
    plcl = ps*(tlcl/tt)**(CP/RD)
    paths = []; vapors = []
    tp = np.array(tt, copy=True)
    for k, pk in enumerate(pp):
        dry = tt*(pk/ps)**(RD/CP)
        if k:
            # Starting the saturated integration exactly at LCL matters in a
            # coarse vertical grid. Integrate each column's fractional step.
            saturated = pk < plcl
            if np.all(saturated):
                wet = moist_step(tp, pp[k-1], pk)
            else:
                wet = np.array(dry,copy=True)
                if np.any(saturated):
                    count=max(1,int(np.ceil(np.max(np.abs(np.log(pk/pp[k-1])))/.025)))
                    wet[saturated]=moist_step(tp[saturated],pp[k-1][saturated],pk[saturated],count=count)
            crossing = (pp[k-1] > plcl) & (pk < plcl)
            # Variable LCL integration, midpoint with short fractional steps.
            # Only columns crossing LCL need the fractional integration.
            # Previously all columns repeated 12 saturation evaluations at
            # EVERY level, then discarded almost all of those results.
            if np.any(crossing):
                dl = np.log(pk[crossing]/plcl[crossing])
                tm = tlcl[crossing].copy();lcl = plcl[crossing]
                if _accelerator is not None:
                    result=np.empty_like(tm)
                    _accelerator(tm,np.ascontiguousarray(lcl),np.ascontiguousarray(dl),result,12,True)
                    tm=result
                else:
                    for j in range(12):
                        r = saturation(tm, lcl*np.exp(dl*(j+.5)/12))
                        tm += (dl/12)*(RD*tm+LV*r)/(CP+LV*LV*r*EPS/(RD*tm*tm))
                wet = np.asarray(wet)
                wet[crossing] = tm
            tp = np.where(pk >= plcl, dry, wet)
        else:
            tp = dry.copy()
        paths.append(np.where(k >= start, tp, t[k]))
        vapors.append(np.where(pk >= plcl, qt, saturation(tp, pk)))
    path = np.stack(paths); pq = np.stack(vapors)
    delta = virtual(path, pq)-virtual(t, q)
    cape = np.zeros(t.shape[1:]); cin = cape.copy(); found = np.zeros_like(cape, dtype=bool)
    # Integrate positive/negative portions exactly across linear zero crossings
    # in log pressure. Include every buoyant layer above LCL (explicit policy).
    for k in range(1, len(p)):
        a, b = delta[k-1], delta[k]
        width = RD*np.log(pp[k-1]/pp[k])
        pos = np.where((a>=0)&(b>=0), (a+b)/2,
                       np.where((a<=0)&(b<=0), 0, np.maximum(a,b)**2/(2*np.maximum(np.abs(b-a),1e-9))))*width
        neg = (a+b)*width/2-pos
        eligible = (k>start) & (pp[k]<plcl)
        cape += np.where(eligible, pos, 0)
        cin += np.where((k>start)&~found, neg, 0)
        found |= eligible & (pos>0)
    return {'cape': np.maximum(cape, 0), 'cin': np.minimum(cin, 0),
            'path': path, 'lcl_pressure': plcl, 'start_index': start,
            'source_mixing_ratio':qt}
