"""Controlled stationary/advancing-front regression, without injected storms."""
import argparse
import json
from pathlib import Path
import numpy as np
from .core import Model, source_digest, VERSION
from . import core
from .terrain import grid
from .validate import morphology


def run(seed, surge=False, solar=False):
    cfg={'bounds':[110.2,23.2,114.4,26.7],'grid_km':8,'hours':12,
         'seed':seed,'trough':0,'stochastic':0}
    model=Model(cfg,np.full(grid(cfg['bounds'],8)[0].shape,30))
    if surge:
        # Put the northern forcing upstream of this small domain, rather
        # than waiting days for it to arrive from the default upstream location.
        # Rain, cells, cold pools and front position are NOT initialized here.
        model.north_trough_lon=112.3
    initial=morphology(model);samples=[];daylight=core.daylight
    try:
        # Isolate confluence from solar-triggered warm-sector convection.
        # This is a controlled forcing experiment, not a 12 h night forecast.
        # Production always retains the actual solar cycle. A separate solar
        # case below must not reject physically triggered warm-sector lines.
        if not solar:core.daylight=lambda _:0.
        for target in np.arange(1,13)*3600:
            while model.time<target-1e-6:model.step(target)
            samples.append(morphology(model))
    finally:core.daylight=daylight
    final=samples[-1]
    displacement=initial['front_median_latitude']-final['front_median_latitude']
    if not surge:
        assert abs(displacement)<.2,'stalled front drifted more than 22 km'
        if not solar:assert not any(s['line_candidates'] for s in samples),'isolated stalled confluence generated a spurious line'
        assert max(s['front_rain_mean_mm_h'] for s in samples)>0,'frontal rain was simply masked out'
    else:
        assert displacement>.2,'a real surge no longer advances the front'
    assert abs(final['budget']['water_relative_residual'])<2e-5
    assert final['budget']['positivity_correction']==0
    return {'seed':seed,'surge':surge,'solar':solar,'displacement_deg':displacement,'samples':samples}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args()
    cases=[run(20260421),run(20260422),run(20260421,True),run(20260422,solar=True)]
    Path(args.output).write_text(json.dumps({'engine':VERSION,'source_sha256':source_digest(),'cases':cases},indent=2))
    print(json.dumps([{'seed':c['seed'],'surge':c['surge'],'solar':c['solar'],'front_southward_deg':c['displacement_deg'],
                       'line_samples':sum(bool(s['line_candidates']) for s in c['samples']),
                       'front_rain_peak_mm_h':max(s['front_rain_mean_mm_h'] for s in c['samples'])} for c in cases]))


if __name__=='__main__':main()
