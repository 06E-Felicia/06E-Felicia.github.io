"""Native low-resolution multi-seed QA; no Astra or diagnostic wind caps."""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from .core import Model,VERSION,source_digest
from .experiment import random_environment
from .run import terrain_for
from .validate import morphology


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seeds',type=int,nargs='+',default=[20260421,20260422]);ap.add_argument('--hours',type=int,default=8);ap.add_argument('--output',required=True);args=ap.parse_args()
    results=[]
    for seed in args.seeds:
        cfg=random_environment(seed,{'hours':72,'grid_km':28,'frame_minutes':60},grid_limit=28)
        height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz');m=Model(cfg,height,grid_limit=28);started=time.monotonic();rows=[]
        for hour in range(args.hours+1):
            while m.time<hour*3600-1e-6:m.step(hour*3600)
            shape=morphology(m);row=m.audit_state()
            row.update({'gust_p99_m_s':float(np.percentile(m.surface_gust(),99)),
                        'longest_candidate_km':max((x['geodesic_length_km'] for x in shape['curved_band_candidates']),default=0),
                        'strong_echo_cells':int(shape['strong_pixels']) if 'strong_pixels' in shape else None})
            rows.append(row)
        summary={'seed':seed,'hours':args.hours,'gust_peak_m_s':m.gust_peak,'meanwind_peak_m_s':m.meanwind_peak,
                 'rain5_peak_mm':m.surface_rain.max_five,'total_point_max_mm':float(m.surface_rain.total.max()),
                 'max_water_residual':max(abs(x['water_relative_residual']) for x in rows),
                 'max_curved_length_km':max(x['longest_candidate_km'] for x in rows),'elapsed_s':time.monotonic()-started}
        results.append({'summary':summary,'samples':rows});print(json.dumps(summary),flush=True)
    Path(args.output).write_text(json.dumps({'engine':VERSION,'source_sha256':source_digest('experiment.py','browser.py'),'grid_km':28,'execution':'native; not browser performance','results':results},indent=2))


if __name__=='__main__':main()
