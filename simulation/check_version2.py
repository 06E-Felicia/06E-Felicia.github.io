"""Astra process diagnostics for trigger/air-mass/CAPE regressions.

Measures actual parameterized initiation separately from advected echoes;
no radar mask, physics monkeypatch or preselected storm object is applied.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from .core import Model, VERSION, source_digest
from .experiment import random_environment
from .run import terrain_for


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--seed',type=int,default=20260423)
    ap.add_argument('--hours',type=int,default=72)
    ap.add_argument('--grid-km',type=int,choices=[6,8,12],default=12)
    ap.add_argument('--output',required=True)
    args=ap.parse_args()
    cfg=random_environment(args.seed,{'grid_km':args.grid_km,'hours':args.hours})
    height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    m=Model(cfg,height);digest=source_digest('experiment.py','browser.py')
    rows=[];arrays={'lon':m.lon,'lat':m.lat};started=time.monotonic()
    for hour in range(args.hours+1):
        while m.time<hour*3600-1e-6:m.step(hour*3600)
        f=m.fields(include_mixed=False);cape=f['mucape']
        cold=m.air>.97;warm=m.air<.1
        active=m.activity>.15;new=m.initiation>.1
        row={'hour':hour,'warm_cells':int(warm.sum()),'postfront_cells':int(cold.sum()),
             'active_fraction':float(active.mean()),'new_fraction':float(new.mean()),
             'strong_echo_fraction':float((f['composite']>=40).mean()),
             'postfront_initiation_fraction':float(new[cold].mean()) if cold.any() else 0.,
             'postfront_cape_p95':float(np.percentile(cape[cold],95)) if cold.any() else 0.,
             'warm_cape_p50':float(np.median(cape[warm])) if warm.any() else 0.,
             'cape_on_hard_ceiling_fraction':float(np.isclose(cape,m.cape_ceiling,rtol=1e-5,atol=.01).mean()),
             'new_without_upward_forcing_fraction':float((new&(m.background_w<=0)&(m.gust_lift<10)).mean()),
             'active_coldpool_fraction':float(((m.cold>.5)&(m.cold_depth>100)).mean()),
             'audit':m.audit_state()}
        rows.append(row)
        if hour%6==0 or hour==args.hours:
            print(json.dumps({k:v for k,v in row.items() if k!='audit'}),flush=True)
            for key,a in {'radar':f['composite'],'cape':cape,'air':m.air,'cold':m.cold,'depth':m.cold_depth,'initiation':m.initiation}.items():
                arrays[f'h{hour}_{key}']=a.copy()
    result={'engine':VERSION,'source_sha256':digest,'edition':'astra','grid_km':args.grid_km,
            'config':cfg,'elapsed_s':time.monotonic()-started,'samples':rows}
    Path(args.output).write_text(json.dumps(result,indent=2))
    np.savez_compressed(args.output+'.npz',**arrays)


if __name__=='__main__':main()
