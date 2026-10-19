"""Native Astra/Sol trajectory diagnostics, using actual model fields."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from scipy.ndimage import label,gaussian_filter1d
from .core import Model,VERSION,source_digest
from .sol import SolModel
from .experiment import random_environment
from .run import terrain_for


def measure(m):
    f=m.fields(include_mixed=False)
    warm=(m.air<.1)&(m.activity>.1)&(f['composite']>=40)
    objects,count=label(warm,structure=np.ones((3,3)))
    sizes=np.bincount(objects.ravel());sizes[0]=0
    mask=objects==int(sizes.argmax()) if count else np.zeros(m.shape,dtype=bool)
    y,x=np.nonzero(mask);line=None
    if len(y)>=3:
        weights=np.maximum(m.activity[mask],.01)
        line={'cells':len(y),'lon':float(np.average(m.lon[mask],weights=weights)),
              'lat':float(np.average(m.lat[mask],weights=weights)),
              'ns_km':float((np.ptp(y)+1)*m.cfg['grid_km']),
              'ew_km':float((np.ptp(x)+1)*m.cfg['grid_km'])}
        rows=np.unique(y)
        if len(rows)>=5:
            front=np.array([np.percentile(np.nonzero(mask[row])[0],80) for row in rows])*m.dx
            front=gaussian_filter1d(front,.8)
            fit=np.polyval(np.polyfit(rows*m.dx,front,1),rows*m.dx)
            bend=front-fit
            line['bow_departure_km']=float(np.ptp(bend)/1000)
            line['bend_angle_deg']=float(np.max(np.abs(np.degrees(np.arctan(np.gradient(bend,rows*m.dx))))))
    u,v=m.winds();su,sv=m.steering(u,v)
    motion=m.storm_motion(u,v) if hasattr(m,'storm_motion') else (su,sv)
    frontal=(m.air>.03)&(m.air<.85)
    return {'hour':m.time/3600,'warm_strong_cells':int(warm.sum()),'line':line,
            'pressure_front_lat':{str(lon):float(np.interp(lon,m.lon[0],m.synoptic.front_lat))
                for lon in [108,110,112,114,116] if m.lon[0,0]<=lon<=m.lon[0,-1]},
            'material_front_lat':{str(lon):float(np.interp(.5,m.air[:,int(np.argmin(abs(m.lon[0]-lon)))],m.lat[:,0]))
                for lon in [108,110,112,114,116] if m.lon[0,0]<=lon<=m.lon[0,-1]},
            'genesis_episode':m.synoptic.episode_index,'genesis_start_hour':m.synoptic.genesis_start/3600,
            'steering_speed_m_s':float(np.median(np.hypot(su[warm],sv[warm]))) if warm.any() else None,
            'storm_speed_m_s':float(np.median(np.hypot(motion[0][warm],motion[1][warm]))) if warm.any() else None,
            'storm_motion_u_m_s':float(np.median(motion[0][warm])) if warm.any() else None,
            'storm_motion_v_m_s':float(np.median(motion[1][warm])) if warm.any() else None,
            'wind_500_u_m_s':float(np.median(f['u500'][warm])) if warm.any() else None,
            'wind_500_v_m_s':float(np.median(f['v500'][warm])) if warm.any() else None,
            'frontal_active_cells':int((frontal&(m.activity>.1)).sum()),
            'frontal_strong_cells':int((frontal&(f['composite']>=40)&(m.activity>.1)).sum()),
            'frontal_cape_p95':float(np.percentile(f['mucape'][frontal],95)) if frontal.any() else 0,
            'max_rainrate':float(m.last_rate.max()),'grid_total_max_mm':float(m.total.max()),
            'audit':m.audit_state()}


def main():
    p=argparse.ArgumentParser();p.add_argument('--edition',choices=['astra','sol'],required=True)
    p.add_argument('--seed',type=int,default=20261017);p.add_argument('--hours',type=int,default=12)
    p.add_argument('--output',required=True);p.add_argument('--baseline',action='store_true')
    a=p.parse_args();km=12 if a.edition=='astra' else 28
    cfg=random_environment(a.seed,{'grid_km':km,'hours':a.hours},grid_limit=km)
    h,_=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    m=(Model if a.edition=='astra' else SolModel)(cfg,h,grid_limit=km)
    digest=source_digest('experiment.py','browser.py',*(['sol.py'] if a.edition=='sol' else []))
    start=time.monotonic();rows=[]
    for half in range(a.hours*2+1):
        while m.time<half*1800-1e-6:m.step(half*1800)
        row=measure(m);rows.append(row)
        if half%6==0:print(json.dumps({k:v for k,v in row.items() if k!='audit'}),flush=True)
    if not a.baseline and digest!=source_digest('experiment.py','browser.py',*(['sol.py'] if a.edition=='sol' else [])):
        raise RuntimeError('Source changed during integration')
    Path(a.output).write_text(json.dumps({'engine':VERSION,'source_sha256':digest,'baseline':a.baseline,
        'edition':a.edition,'grid_km':km,'config':cfg,'samples':rows,'elapsed_s':time.monotonic()-start},indent=2))


if __name__=='__main__':main()
