"""Real-DEM paired obstacle probes, not a full weather/event simulation.

Identical initialized shallow currents cross the same mean terrain with/without
the fine-DEM form drag. No radar mask or site-name attenuation enters Model.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from .core import Model,settings,source_digest,VERSION
from .run import terrain_for
from .coldpool import velocity


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args()
    cfg=settings({'grid_km':6,'seed':20260423});h,meta=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    rows=[]
    for name,lon0,lat0,downwind in [('Phoenix',113.43,22.44,113.65),('Lantau',113.77,22.25,114.02)]:
        pair=[]
        for detailed in [False,True]:
            m=Model(cfg,h)
            if not detailed:m.terrain_relief.fill(0);m.terrain_cover.fill(0)
            # Same finite 300-m / 3-K air volume; 12 m/s initial eastward flow.
            radius=((m.lon-lon0)*102000/13000)**2+((m.lat-lat0)*111195/9000)**2
            m.cold_depth=300*np.exp(-radius);m.cold_content=m.cold_depth*3
            m.cold_mx=m.cold_depth*12;m.cold_my=np.zeros(m.shape);m.cold_diagnostics()
            initial=float(m.cold_content.sum());before=float(m.cold_depth.sum())
            for _ in range(60):m.transport_cold_pool(30)
            u,v=velocity(m.cold_depth,m.cold_mx,m.cold_my)
            corridor=(np.abs(m.lat-lat0)<.2)&(m.lon>downwind)
            pair.append({'fine_relief':detailed,'downwind_cold_content':float(m.cold_content[corridor].sum()),
                         'downwind_depth_sum':float(m.cold_depth[corridor].sum()),
                         'max_cold_current_speed':float(np.hypot(u,v)[m.cold_depth>30].max()),
                         'depth_relative_residual':(float(m.cold_depth.sum())-before)/before,
                         'cold_content_relative_residual':(float(m.cold_content.sum())-initial-m.cold_external)/initial})
        rows.append({'site':name,'initial_lon':lon0,'initial_lat':lat0,'elapsed_minutes':30,'cases':pair,
                     'fine_relief_to_mean_only_downwind_ratio':pair[1]['downwind_cold_content']/max(pair[0]['downwind_cold_content'],1e-12)})
    result={'engine':VERSION,'source_sha256':source_digest('experiment.py','browser.py'),'terrain':meta,
            'scope':'Controlled 6-km real-DEM density-current crossings, not a 6-km full weather simulation or a guarantee that all storms weaken over hills',
            'sites':rows}
    Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


if __name__=='__main__':main()
