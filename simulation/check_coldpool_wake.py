"""Diagnostic only: inspect saved fields and a no-new-cooling sensitivity.

Never patches production physics. The source-off branch deliberately disables
only cold-pool buoyancy/depth supply; it is a causal experiment, not a second
physically complete weather forecast. No Astra run is performed.
"""
import argparse
import copy
import json
import time
from pathlib import Path
import numpy as np
from scipy.ndimage import label
from .core import Model, VERSION, source_digest
from .experiment import random_environment
from .run import terrain_for


def pools(model):
    active=(model.cold>.5)&(model.cold_depth>100)
    objects,count=label(active);out=[]
    for ident in range(1,count+1):
        mask=objects==ident
        if mask.sum()<3:continue
        out.append({'cells':int(mask.sum()),'lon':float(model.lon[mask].mean()),'lat':float(model.lat[mask].mean()),
                    'mean_deficit_K':float(model.cold[mask].mean()),'max_deficit_K':float(model.cold[mask].max()),
                    'mean_depth_m':float(model.cold_depth[mask].mean()),'rain_mean_mm_h':float(model.last_rate[mask].mean()),
                    'buoyancy_content':float(model.cold_content[mask].sum())})
    return sorted(out,key=lambda r:-r['cells'])


def state(model):
    weak=(model.cold<.1)&(model.cold_depth>100)
    return {'hour':model.time/3600,'cold_Q':float(model.cold_content.sum()),'source_Q':model.cold_source,
            'max_deficit_K':float(model.cold.max()),'max_depth_m':float(model.cold_depth.max()),
            'active_cells':int(((model.cold>.5)&(model.cold_depth>100)).sum()),
            'neutral_deep_cells':int(weak.sum()),'neutral_depth_max_m':float(model.cold_depth[weak].max()) if weak.any() else 0.,
            'pools':pools(model)}


def neutral_probe(seed):
    """Flat, source-free weak layer; cold-pool operators ONLY, no weather."""
    from .terrain import grid
    from .coldpool import velocity
    cfg=random_environment(seed,{'grid_km':28},grid_limit=28)
    lon,lat=grid(cfg['bounds'],28);m=Model(cfg,np.full(lon.shape,30.),grid_limit=28)
    m.u.fill(8);m.v.fill(0);m.syn_u.fill(8);m.syn_v.fill(0)
    m.cold_depth=600*np.exp(-((lon-108.3)/1.)**2-((lat-22.8)/.6)**2)
    m.cold_content=m.cold_depth*.08;m.cold_mx=m.cold_depth*8;m.cold_my=m.cold_depth*0
    m.cold_source=0.;m.cold_recovery=0.;m.cold_external=0.;m.cold_diagnostics();rows=[]
    for hour in range(13):
        while m.time<hour*3600-1e-6:
            dt=min(90,hour*3600-m.time);m.transport_cold_pool(dt);m.recover_cold_pool(dt,np.zeros(m.shape),0);m.time+=dt
        u,v=velocity(m.cold_depth,m.cold_mx,m.cold_my)
        if hour in (0,2,4,6,8,12):
            weight=m.cold_depth
            rows.append({'hour':hour,'max_K':float(m.cold.max()),'max_depth_m':float(weight.max()),
                         'centroid_lon':float(np.sum(lon*weight)/np.sum(weight)) if weight.sum()>0 else None,
                         'layer_mean_eastward_m_s':float(np.sum(u*weight)/np.sum(weight)) if weight.sum()>0 else None,
                         'new_source_Q':m.cold_source,'cold_Q':float(m.cold_content.sum())})
    return {'kind':'isolated cold-pool operators; flat terrain, fixed 8 m/s background, no new cooling or weather integration','rows':rows}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=20260423);ap.add_argument('--checkpoint',type=int,default=8);ap.add_argument('--after',type=int,default=16);ap.add_argument('--output',required=True);ap.add_argument('--neutral-only',action='store_true');args=ap.parse_args()
    if args.neutral_only:
        result=neutral_probe(args.seed);Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps(result));return
    cfg=random_environment(args.seed,{'hours':72,'grid_km':28,'frame_minutes':60},grid_limit=28)
    height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz');model=Model(cfg,height,grid_limit=28)
    started=time.monotonic();history=[]
    for hour in range(args.checkpoint+1):
        while model.time<hour*3600-1e-6:model.step(hour*3600)
        history.append(state(model))
    checkpoint=copy.deepcopy(model);branches={}
    for mode in ['normal','no_new_cold_source']:
        m=copy.deepcopy(checkpoint)
        if mode=='no_new_cold_source':m.supply_cold_pool=lambda evaporation:None
        rows=[state(m)];initial_source=m.cold_source
        for hour in range(args.checkpoint+1,args.checkpoint+args.after+1):
            while m.time<hour*3600-1e-6:m.step(hour*3600)
            row=state(m);row['new_source_Q']=m.cold_source-initial_source;rows.append(row)
            if (hour-args.checkpoint)%4==0:print(json.dumps({'branch':mode,'hour':hour,'active':row['active_cells'],'neutral_deep':row['neutral_deep_cells'],'max_K':row['max_deficit_K'],'elapsed_s':round(time.monotonic()-started,2)}),flush=True)
        branches[mode]=rows
    result={'engine':VERSION,'source_sha256':source_digest('experiment.py','browser.py'),'seed':args.seed,
            'grid_km':28,'threshold':{'active_deficit_K':.5,'active_depth_m':100,'neutral_deficit_K':.1},
            'checkpoint_hour':args.checkpoint,'history':history,'branches':branches,'elapsed_seconds':time.monotonic()-started,
            'limitation':'no_new_cold_source is a controlled diagnostic, not a physically complete alternate forecast; .5 K / 100 m are analysis thresholds, not universal meteorological definitions'}
    Path(args.output).write_text(json.dumps(result,indent=2));print('SAVED',args.output,flush=True)


if __name__=='__main__':main()
