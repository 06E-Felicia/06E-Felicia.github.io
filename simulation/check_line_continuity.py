"""Matched-seed head-memory comparison using unmodified physical echoes.

The optional reference restores only 4.9 organization transport. Metrics
describe threshold connectivity, not a guarantee of one permanent object.
"""
import argparse
import json
import time
from pathlib import Path
from types import MethodType
import numpy as np
from scipy.ndimage import label,distance_transform_edt,maximum_filter
from .core import Model,VERSION,source_digest,advect
from .sol import SolModel
from .experiment import random_environment
from .run import terrain_for


def instrument_head(m):
    """Observe the actual last step, without changing any closure or state."""
    m.head_probe={}
    for name in ['warm_inflow','head_inflow','gust_activation','organized_coverage']:
        original=getattr(m,name)
        def observed(*args,_name=name,_original=original,**kwargs):
            result=_original(*args,**kwargs)
            probe=m.head_probe
            if _name=='warm_inflow':probe['warm_donor']=result[1].copy()
            if _name=='head_inflow':
                probe['approach']=result.copy()
                probe['cell_u']=args[0].copy();probe['cell_v']=args[1].copy()
                probe['cold_u']=args[2].copy();probe['cold_v']=args[3].copy()
                probe['nx']=args[6].copy();probe['ny']=args[7].copy()
            if _name=='gust_activation':
                for key,value in zip(['Q','H','edge','balance','source_height','cin'],args):
                    probe[key]=np.broadcast_to(value,m.shape).copy()
                probe['pressure_activation']=result.copy()
                probe['donor_cape']=m.plume_cape(m.donor_field(m.mu['cape'])).copy()
            if _name=='organized_coverage':
                for key,index in [('target',4),('support',5),('efficiency',6),('feeding',7)]:
                    probe[key]=np.broadcast_to(args[index],m.shape).copy()
            return result
        setattr(m,name,observed)


def head_summary(m):
    p=m.head_probe
    if not p:return {}
    near=maximum_filter(m.activity,size=5,mode='constant')>.01
    candidates=near&(p['edge']>.08)&(m.air<.1)
    masks={'edge':candidates,'feeding':candidates&p['feeding'],
           'lost_donor':candidates&~p['warm_donor'],
           'lost_inflow':candidates&p['warm_donor']&(p['approach']<=0),
           'not_activated':candidates&p['feeding']&(p['target']<.1)}
    keys=['Q','H','edge','balance','source_height','cin','donor_cape','approach','pressure_activation','target','support','efficiency']
    return {name:{'cells':int(mask.sum()),'p10_p50_p90':{
        key:np.percentile(p[key][mask],[10,50,90]).tolist() if mask.any() else [] for key in keys}}
        for name,mask in masks.items()}


def reference_memory(m):
    original_transport=m.transport_cold_pool
    original_evolve=m.evolve_head_organization
    def transport(self,dt):
        before=self.organization.copy()
        original_transport(dt)
        self.organization=before
    def evolve(self,dt,target,depth,speed,balance):
        self.organization=advect(self.organization,self.u,self.v,dt,self.dx,boundary=0)
        original_evolve(dt,target,depth,speed,balance)
    m.transport_cold_pool=MethodType(transport,m)
    m.evolve_head_organization=MethodType(evolve,m)


def connectivity(m,echo,threshold):
    active=(echo>=threshold)&(m.activity>.05)&(m.air<.1)
    objects,count=label(active,structure=np.ones((3,3)))
    sizes=np.bincount(objects.ravel());sizes[0]=0
    ordered=np.argsort(sizes)[::-1]
    principal=objects==int(ordered[0]) if count else np.zeros(m.shape,dtype=bool)
    y,x=np.nonzero(principal)
    weights=m.activity[principal]
    return {'cells':int(active.sum()),'components':int(count),
            'largest_cells':int(len(y)),
            'largest_fraction':float(len(y)/max(active.sum(),1)),
            'ns_span_km':float((np.ptp(y)+1)*m.cfg['grid_km']) if len(y) else 0,
            'lon':float(np.average(m.lon[principal],weights=weights)) if len(y) else None,
            'lat':float(np.average(m.lat[principal],weights=weights)) if len(y) else None,
            'top3_cells':[int(sizes[i]) for i in ordered[:3] if sizes[i]>0]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--edition',choices=['astra','sol'],default='astra')
    p.add_argument('--seed',type=int,default=20261017)
    p.add_argument('--hours',type=int,default=10)
    p.add_argument('--sample-minutes',type=int,choices=[15,30],default=30)
    p.add_argument('--reference-memory',action='store_true')
    p.add_argument('--head-diagnostics',action='store_true')
    p.add_argument('--output',required=True)
    a=p.parse_args();km=12 if a.edition=='astra' else 28
    cfg=random_environment(a.seed,{'grid_km':km,'hours':a.hours},grid_limit=km)
    h,terrain=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    m=(Model if a.edition=='astra' else SolModel)(cfg,h,grid_limit=km)
    if a.head_diagnostics:instrument_head(m)
    digest=source_digest('experiment.py','browser.py',*(['sol.py'] if a.edition=='sol' else []))
    if a.reference_memory:reference_memory(m)
    start=time.monotonic();rows=[];snapshots={'lon':m.lon,'lat':m.lat}
    coastal_distance=np.where(m.land,distance_transform_edt(m.land),distance_transform_edt(~m.land))*km
    coast=(coastal_distance<=40)&(m.lon>=110)&(m.lon<=116)&(m.lat<=23.5)
    origin=m.synoptic.genesis_center
    radius=((m.lon-origin[0])*111195*np.cos(np.radians(origin[1])))**2+((m.lat-origin[1])*111195)**2 if origin else np.full(m.shape,np.inf)
    for tick in range(a.hours*60//a.sample_minutes+1):
        target=tick*a.sample_minutes*60
        while m.time<target-1e-6:m.step(target)
        f=m.fields(include_mixed=False);echo=f['composite']
        active=(echo>=35)&(m.activity>.05)&(m.air<.1)
        u,v=m.winds();cu,cv=m.storm_motion(u,v)
        wind={name:float(np.median(field[active])) if active.any() else None
              for name,field in [('pattern_u',cu),('pattern_v',cv),('u500',f['u500']),('v500',f['v500'])]}
        row={'hour':m.time/3600,'echo35':connectivity(m,echo,35),'echo40':connectivity(m,echo,40),
             'active_wind_m_s':wind,'genesis_closed':m.genesis_closed,
             'genesis_started':m.genesis_started,'genesis_center':m.synoptic.genesis_center,
             'origin_active35_cells':int((active&(radius<=40000**2)).sum()),
             'coastal_active35_cells':int((coast&active).sum()),
             'coastal_active40_cells':int((coast&active&(echo>=40)).sum()),
             'coastal_max_rainrate_mm_h':float(m.last_rate[coast].max()) if coast.any() else 0,
             'coastal_max_total_mm':float(m.total[coast].max()) if coast.any() else 0,
             'genesis_episode':m.synoptic.episode_index,'audit':m.audit_state()}
        rows.append(row)
        if a.head_diagnostics:row['head']=head_summary(m)
        if tick%(60//a.sample_minutes)==0:
            for key,v in {'radar':echo,'cold':m.cold,'depth':m.cold_depth,'activity':m.activity,
                'organization':m.organization,'cape':m.available_cape(m.mu['cape']),
                'air':m.air,'rain':m.last_rate,'total':m.total,
                'anvil_column':np.sum(m.anvil*m.mass,axis=0),
                'stratiform_rate':m.last_stratiform_rate}.items():snapshots[f'h{tick*a.sample_minutes//60}_{key}']=v.copy()
            if a.head_diagnostics:
                for key,value in m.head_probe.items():snapshots[f'h{tick*a.sample_minutes//60}_head_{key}']=value.copy()
        if tick%(120//a.sample_minutes)==0:
            print(json.dumps({k:v for k,v in row.items() if k!='audit'}),flush=True)
    if digest!=source_digest('experiment.py','browser.py',*(['sol.py'] if a.edition=='sol' else [])):
        raise RuntimeError('Physical source changed during integration')
    Path(a.output).write_text(json.dumps({'engine':VERSION,'source_sha256':digest,'config':cfg,'edition':a.edition,
        'reference_4_9_memory':a.reference_memory,'terrain':terrain,'elapsed_s':time.monotonic()-start,
        'sample_minutes':a.sample_minutes,'initial_genesis_center':origin,
        'coastal_metric':'within 40km of binary DEM shore, 110--116E and <=23.5N; diagnosis only',
        'final_genesis_half_length_km':m.synoptic.genesis_half_length/1000 if m.synoptic.genesis_center else None,
        'samples':rows},indent=2))
    np.savez_compressed(a.output+'.npz',**snapshots)


if __name__=='__main__':main()
