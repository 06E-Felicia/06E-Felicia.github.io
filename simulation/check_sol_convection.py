"""Native, real-terrain Sol initiation/process checks; never substitutes Astra."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from scipy.ndimage import label
from .core import Model,VERSION,source_digest
from .sol import SolModel
from .experiment import random_environment
from .run import terrain_for


def check(seed,hours,baseline=False):
    cfg=random_environment(seed,{'grid_km':28,'hours':hours,'frame_minutes':60},grid_limit=28)
    terrain,_=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    m=(Model if baseline else SolModel)(cfg,terrain,grid_limit=28)
    start=time.monotonic();rows=[];days={};peak_residual=0.
    for half in range(int(round(hours*2))+1):
        target=half*1800
        while m.time<target-1e-6:m.step(target)
        f=m.fields(include_mixed=False)
        strong=(f['composite']>=40)&(m.activity>.1)
        objects,count=label(strong,structure=np.ones((3,3)))
        complexes=[]
        for k in range(1,count+1):
            y,x=np.nonzero(objects==k)
            if len(y)<3:continue
            complexes.append({'cells':len(y),'ns_km':int((np.ptp(y)+1)*28),'ew_km':int((np.ptp(x)+1)*28),
                              'mean_lon':float(m.lon[y,x].mean()),'mean_lat':float(m.lat[y,x].mean())})
        row={'hour':m.time/3600,'active_cells':int((m.activity>.1).sum()),'strong_cells':int(strong.sum()),
             'initiation_max':float(m.initiation.max()),'complexes':complexes,
             'grid_rainrate_max_mm_h':float(m.last_rate.max()),'grid_rain_total_max_mm':float(m.total.max()),
             'cold_depth_max_m':float(m.cold_depth.max()),'genesis_closed':m.genesis_closed}
        rows.append(row)
        day=days.setdefault(int(m.time//86400),{'peak_active_cells':0,'peak_strong_cells':0,'peak_connected_cells':0,'active_sample_hours':0.})
        day['peak_active_cells']=max(day['peak_active_cells'],row['active_cells'])
        day['peak_strong_cells']=max(day['peak_strong_cells'],row['strong_cells'])
        day['peak_connected_cells']=max(day['peak_connected_cells'],max((o['cells'] for o in complexes),default=0))
        if row['active_cells']>=4:day['active_sample_hours']+=.5
        residual=abs(m.audit_state()['water_relative_residual']);peak_residual=max(peak_residual,residual)
        if half%12==0:print(json.dumps({'baseline':baseline,'seed':seed,**row,'elapsed_s':round(time.monotonic()-start,2)}),flush=True)
    return {'baseline':baseline,'seed':seed,'grid_km':28,'hours':hours,'config':cfg,'days':days,
            'samples':rows,'final_audit':m.audit_state(),'max_water_relative_residual':peak_residual,'elapsed_s':time.monotonic()-start}


def main():
    p=argparse.ArgumentParser();p.add_argument('--seeds',type=int,nargs='+',default=[20260421,20260423,20261017])
    p.add_argument('--hours',type=int,default=12);p.add_argument('--compare-baseline',action='store_true');p.add_argument('--output',required=True)
    args=p.parse_args();digest=source_digest('experiment.py','browser.py','sol.py');cases=[]
    for seed in args.seeds:
        if args.compare_baseline:cases.append(check(seed,args.hours,True))
        cases.append(check(seed,args.hours))
    if digest!=source_digest('experiment.py','browser.py','sol.py'):raise RuntimeError('Source changed while running; discard result')
    Path(args.output).write_text(json.dumps({'engine':VERSION,'source_sha256':digest,'edition':'sol','cases':cases},indent=2))
    print('COMPLETE',json.dumps([{'seed':c['seed'],'baseline':c['baseline'],'days':c['days'],'elapsed_s':c['elapsed_s']} for c in cases]),flush=True)


if __name__=='__main__':main()
