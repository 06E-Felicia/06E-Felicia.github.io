"""Repeatable compute / frame-packing benchmark; no display pacing or I/O.

Timing is measured on the same seed, domain, grid, simulated duration and
output interval. Profiling is opt-in because it adds overhead to the timing.
"""
import argparse
import cProfile
import io
import json
import pstats
import time
import numpy as np
from .core import Model, VERSION, settings, source_digest
from .run import terrain_for, pack


def benchmark(hours=1, grid_km=6, seed=20260421, profile=False, state_output=None,compact_transport=False):
    cfg=settings({'hours':hours,'grid_km':grid_km,'seed':seed,'frame_minutes':10,'compact_transport':compact_transport})
    height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    profiler=cProfile.Profile() if profile else None
    if profiler:profiler.enable()
    start=time.perf_counter();model=Model(cfg,height)
    initialized=time.perf_counter()-start
    integration=0.;snapshots=0.;frames=0;encoded_bytes=0
    targets=np.arange(0,hours*3600+1e-6,600).tolist()
    if abs(targets[-1]-hours*3600)>1e-6:targets.append(hours*3600)
    for target in targets:
        started=time.perf_counter()
        while model.time<target-1e-6:model.step(target)
        integration+=time.perf_counter()-started
        started=time.perf_counter()
        encoded=json.dumps({key:pack(value) for key,value in model.fields().items()},separators=(',',':'),allow_nan=False)
        snapshots+=time.perf_counter()-started;frames+=1;encoded_bytes+=len(encoded)
    elapsed=time.perf_counter()-start
    if profiler:
        profiler.disable();stream=io.StringIO()
        pstats.Stats(profiler,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(25)
        print(stream.getvalue())
    if state_output:
        np.savez_compressed(state_output,**{key:getattr(model,key) for key in ['temp','q','cloud','rain','plume_cloud','plume_rain','rain_area','total','u','v','syn_u','syn_v','air','cold_content','cold_depth','activity']})
    result={'engine':VERSION,'source_sha256':source_digest(),
            'seed':seed,'grid_km':grid_km,'hours':hours,'compact_transport':compact_transport,'frames':frames,'cells':model.lon.size,'steps':model.steps,
            'initialized_s':initialized,'integration_s':integration,'snapshots_s':snapshots,'total_s':elapsed,
            'encoded_MiB':encoded_bytes/1024**2,'profiled':profile,'audit':model.audit_state()}
    print(json.dumps(result));return result


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--hours',type=float,default=1);ap.add_argument('--grid-km',type=float,default=6)
    ap.add_argument('--seed',type=int,default=20260421);ap.add_argument('--profile',action='store_true');ap.add_argument('--state-output')
    ap.add_argument('--compact-transport',action='store_true')
    a=ap.parse_args();benchmark(a.hours,a.grid_km,a.seed,a.profile,a.state_output,a.compact_transport)
