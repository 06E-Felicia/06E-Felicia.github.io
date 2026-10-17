"""Trusted post-storm checkpoint sensitivity, not a restarted forecast.

Only reads checkpoints generated locally by check_single_episode. An old
initial state is intentionally allowed for a causal same-state comparison;
the initial-state and executing-source hashes are recorded separately.
"""
import argparse
import hashlib
import json
import pickle
import tempfile
from pathlib import Path
import numpy as np
from scipy.ndimage import gaussian_filter
from .core import VERSION, source_digest, DZ, echo_components


def main():
    p=argparse.ArgumentParser();p.add_argument('--checkpoint-ref',required=True)
    p.add_argument('--hours',type=int,default=6);p.add_argument('--output',required=True)
    a=p.parse_args();token=hashlib.sha256(str(Path(a.checkpoint_ref).resolve()).encode()).hexdigest()[:16]
    checkpoint=Path(tempfile.gettempdir())/('stormsim-checkpoint-'+token+'.pkl')
    digest=source_digest('experiment.py','browser.py')
    with checkpoint.open('rb') as file:state=pickle.load(file)
    m=state['model'];start=m.time;rows=[]
    # Only the new driver terrain cache is missing in old trusted states.
    if not hasattr(m.synoptic,'terrain'):
        m.synoptic.terrain=gaussian_filter(m.h,max(.5,24/m.cfg['grid_km']))
    print(json.dumps({'engine':VERSION,'executing_source':digest,'initial_source':state['digest'],'start_hour':start/3600}),flush=True)
    for hour in range(a.hours+1):
        target=start+hour*3600
        while m.time<target-1e-6:m.step(target)
        density=m.mass/DZ[:,None,None]
        b,c,ice,_=echo_components(m.rain,m.plume_rain,m.rain_area,density,m.anvil,m.graupel,m.graupel_area)
        dbz=10*np.log10(np.maximum(np.max(b+c+ice,axis=0),1e-3))
        warm=(m.air<.2)&(m.activity<.05)
        row={'hour':m.time/3600,'weak_warm_area_15dbz_km2':int((warm&(dbz>=15)).sum())*m.cfg['grid_km']**2,
             'weak_warm_area_25dbz_km2':int((warm&(dbz>=25)).sum())*m.cfg['grid_km']**2,
             'liquid_rain_mass':float((m.rain*m.mass).sum()),'cloud_mass':float((m.cloud*m.mass).sum()),
             'convective_ice_mass':float((m.anvil_convective*m.mass).sum()),
             'ice_mass':float((m.anvil*m.mass).sum()),'water_residual':m.audit_state()['water_relative_residual']}
        rows.append(row);print(json.dumps(row),flush=True)
    Path(a.output).write_text(json.dumps({'engine':VERSION,'source_sha256':digest,'initial_source_sha256':state['digest'],
        'scope':'same-state post-storm sensitivity, not an independent whole-process validation',
        'grid_km':m.cfg['grid_km'],'samples':rows},indent=2))


if __name__=='__main__':main()
