"""Controlled moist, advancing front: isolate opening the frontal trigger."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from .core import Model,VERSION,Z,source_digest
from .sol import SolModel
from .terrain import grid


def check(edition,enabled):
    km=12 if edition=='astra' else 28
    cfg={'seed':20261017,'bounds':[110,21,115,25.5],'grid_km':km,'month':5,'moisture':1.15,'stochastic':.4}
    m=(Model if edition=='astra' else SolModel)(cfg,np.full(grid(cfg['bounds'],km)[0].shape,30),grid_limit=km)
    previous=m.frontal_layers();m.synoptic.front_lat.fill(23.7)
    m.air=m.synoptic.external_air().astype('float32')
    change=m.frontal_layers()-previous
    m.temp-=9*change*np.exp(-Z[:,None,None]/2000);m.q*=np.exp(-.55*change)
    # These are initial conditions, not a mid-process water/CAPE reset.
    m.initial_water=float(np.sum((m.q+m.cloud+m.rain)*m.mass))
    m.inflow_air=m.air.copy();m.inflow_q=m.q.copy();m.radiative_reference=m.temp.copy()
    m.syn_u,m.syn_v=m.synoptic.surface_target(m.air,0)
    m.u=m.syn_u.copy();m.v=m.syn_v.copy();m.diagnostics()
    m.genesis_closed=True;m.synoptic.genesis_center=None;m.next_genesis_check=1e9
    if not enabled:m.frontal_initiation_permission=lambda:np.zeros(m.shape)
    rows=[];start=time.monotonic()
    for half in range(5):
        while m.time<half*1800-1e-6:m.step(half*1800)
        f=m.fields(include_mixed=False);belt=(m.air>.015)&(m.air<.85)
        rows.append({'hour':m.time/3600,'frontal_active_cells':int((belt&(m.activity>.1)).sum()),
            'frontal_strong_cells':int((belt&(m.activity>.1)&(f['composite']>=40)).sum()),
            'cape_p95':float(np.percentile(f['mucape'][belt],95)),
            'water_relative_residual':m.audit_state()['water_relative_residual']})
    return {'edition':edition,'grid_km':km,'frontal_route_open':enabled,'hours':2,
            'peak_active_cells':max(r['frontal_active_cells'] for r in rows),
            'peak_strong_cells':max(r['frontal_strong_cells'] for r in rows),'samples':rows,'elapsed_s':time.monotonic()-start}


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    digest=source_digest('experiment.py','browser.py','sol.py')
    cases=[check(edition,enabled) for edition in ['astra','sol'] for enabled in [False,True]]
    assert all(c['peak_strong_cells']>0 if c['frontal_route_open'] else c['peak_active_cells']==0 for c in cases)
    assert all(abs(r['water_relative_residual'])<.002 for c in cases for r in c['samples'])
    if digest!=source_digest('experiment.py','browser.py','sol.py'):raise RuntimeError('Source changed during check')
    Path(a.output).write_text(json.dumps({'engine':VERSION,'source_sha256':digest,
        'scope':'Controlled 2-hour entered-front scenario on flat terrain; not a new 72-hour forecast','cases':cases},indent=2))
    print(json.dumps([{'edition':c['edition'],'open':c['frontal_route_open'],'peak_active':c['peak_active_cells'],'peak_strong':c['peak_strong_cells']} for c in cases]),flush=True)


if __name__=='__main__':main()
