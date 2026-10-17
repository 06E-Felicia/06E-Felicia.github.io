"""Actual Astra integrations: initiation, mature complexes and gust envelope."""
import argparse
import json
import time
import pickle
import tempfile
import hashlib
from pathlib import Path
import numpy as np
from scipy.ndimage import label, binary_dilation
from .core import Model,VERSION,source_digest
from .experiment import random_environment
from .run import terrain_for


def measure(m):
    f=m.fields(include_mixed=False)
    strong=(f['composite']>=40)&(m.activity>.1)&(m.last_rate>=5)
    objects,n=label(binary_dilation(strong,iterations=max(1,round(24/m.cfg['grid_km']))))
    complexes=[]
    for k in range(1,n+1):
        yy,xx=np.nonzero((objects==k)&strong)
        if len(yy)*m.cfg['grid_km']**2<1500:continue
        ns=(np.ptp(yy)+1)*m.cfg['grid_km'];ew=(np.ptp(xx)+1)*m.cfg['grid_km']
        complexes.append({'area_km2':len(yy)*m.cfg['grid_km']**2,'ns_km':int(ns),'ew_km':int(ew),
                          'south':float(m.lat[yy,xx].min()),'north':float(m.lat[yy,xx].max()),
                          'west':float(m.lon[yy,xx].min()),'east':float(m.lon[yy,xx].max())})
    return {'hour':round(m.time/3600,2),'new_cells':int((m.initiation>.1).sum()),
            'active_cells':int((m.activity>.1).sum()),'strong_cells':int(strong.sum()),
            'complexes':complexes,'cold_area_km2':int(((m.cold>.5)&(m.cold_depth>100)).sum())*m.cfg['grid_km']**2,
            'episode_day':m.convective_day,'genesis_center':m.synoptic.genesis_center,
            'genesis_closed':m.genesis_closed,'lift_max_m':float(m.synoptic_lift.max()),
            'front_latitude':np.percentile(m.synoptic.front_lat,[0,50,100]).tolist(),
            'wind500_from_deg':np.percentile((np.degrees(np.arctan2(-f['u500'],-f['v500']))+360)%360,[0,50,100]).tolist(),
            'rainrate_max_mm_h':float(m.last_rate.max()),'grid_total_max_mm':float(m.total.max()),
            'gust_max_m_s':float(m.surface_gust().max()),'audit':m.audit_state()},f


def main():
    p=argparse.ArgumentParser();p.add_argument('--seed',type=int,required=True)
    p.add_argument('--hours',type=int,default=12);p.add_argument('--output',required=True)
    p.add_argument('--resume',action='store_true',help='Resume only this script\'s trusted local same-source checkpoint')
    a=p.parse_args();c=random_environment(a.seed,{'grid_km':12,'hours':a.hours})
    h,_=terrain_for(c,'assets/data/simulation-terrain.npz');m=Model(c,h);start=time.monotonic()
    rows=[];arrays={'lon':m.lon,'lat':m.lat};first_half=0
    digest=source_digest('experiment.py','browser.py')
    token=hashlib.sha256(str(Path(a.output).resolve()).encode()).hexdigest()[:16]
    checkpoint=Path(tempfile.gettempdir())/('stormsim-checkpoint-'+token+'.pkl')
    if a.resume:
        with checkpoint.open('rb') as file:state=pickle.load(file)
        if state['digest']!=digest:raise ValueError('Checkpoint source differs; do not reuse a different physics run')
        m,rows,arrays=state['model'],state['rows'],state['arrays'];first_half=int(round(m.time/1800))+1
    for half in range(first_half,a.hours*2+1):
        target=half*1800
        while m.time<target-1e-6:m.step(target)
        row,f=measure(m);rows.append(row)
        _,permission=m.synoptic.genesis(m.time);eligible=permission>.5
        if eligible.any():
            row['genesis_soundings']={'cells':int(eligible.sum()),'mu_lfc_p50_m':float(np.median(m.mu_lfc[eligible])),
                'mu_source_p50_m':float(np.median(m.mu['start_index'][eligible])),
                'synoptic_lift_p95_m':float(np.percentile(m.synoptic_lift[eligible],95)),
                'mucape_p95':float(np.percentile(f['mucape'][eligible],95))}
        fragmented=sum(max(o['ns_km'],o['ew_km'])>=120 for o in row['complexes'])>1
        if half%2==0 or fragmented:
            print(json.dumps({k:v for k,v in row.items() if k!='audit'}),flush=True)
            for key,field in {'radar':f['composite'],'cold':m.cold,'depth':m.cold_depth,'rate':m.last_rate,'cape':f['mucape'],
                              'grid_total':m.total,'activity':m.activity,'initiation':m.initiation}.items():
                arrays[f'h{half/2:g}_{key}']=field.copy()
        if half and half%12==0:
            with checkpoint.open('wb') as file:
                pickle.dump({'digest':digest,'model':m,'rows':rows,'arrays':arrays},file,protocol=pickle.HIGHEST_PROTOCOL)
    # Refuse to label an in-flight old model with newly edited disk sources.
    if source_digest('experiment.py','browser.py')!=digest:
        raise RuntimeError('Model sources changed during integration; rerun before using this report')
    result={'engine':VERSION,'source_sha256':digest,'edition':'astra','grid_km':12,
            'config':c,'genesis_center':m.synoptic.genesis_center,'samples':rows,'elapsed_s':time.monotonic()-start}
    Path(a.output).write_text(json.dumps(result,indent=2));np.savez_compressed(a.output+'.npz',**arrays)


if __name__=='__main__':main()
