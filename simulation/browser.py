"""Pyodide bridge; uses exactly the same core as the GitHub Actions runner."""
import json
import time
import numpy as np
from .core import Model, VERSION, Z, source_digest
from .run import terrain_for, pack
from .experiment import random_environment
from . import numerics, thermo


def select_backends(model):
    """Time equivalent operators on this device; retain only faster paths.

    Probe arrays are never assigned back to the model; no RNG draws, physics
    steps or parcel refresh events are consumed by this calibration.
    """
    selected={};checks={}
    for name,module,operation in [
        ('transport',numerics,lambda:numerics.Advection(*model.winds(),model.dx)(np.asarray(model.q*model.mass,dtype='float64'),30,boundary=0,conservative=True)),
        ('moist_rk4',thermo,lambda:thermo.parcel(model.p,model.temp,model.q,'surface'))]:
        callback=module._accelerator
        if callback is None:selected[name]='numpy';continue
        timings=[]
        for backend in [None,callback]:
            module.install_accelerator(backend);operation()  # warm JIT/caches
            measured=[]
            for _ in range(2):
                start=time.perf_counter();operation();measured.append(time.perf_counter()-start)
            timings.append(min(measured))
        accelerated=timings[1]<.9*timings[0]
        module.install_accelerator(callback if accelerated else None)
        selected[name]='fused' if accelerated else 'numpy'
        checks[name]={'numpy_s':timings[0],'fused_s':timings[1]}
    return {'selected':selected,'calibration':checks}


def initialize(seed, controls):
    global model, config
    config=random_environment(seed,json.loads(controls))
    height,terrain=terrain_for(config,'assets/data/simulation-terrain.npz')
    model=Model(config,height)
    acceleration=select_backends(model)
    lon,lat=model.lon,model.lat
    return json.dumps({'schema':2,'engine':VERSION,'status':'running','simulation':True,
        'source_sha256':source_digest('experiment.py'),
        'execution':'browser','config':config,'terrain':terrain,'frames':[],'acceleration':acceleration,
        'seed_streams':dict(zip(['initial_temperature','initial_moisture','time_evolution','synoptic','convective_cells'],model.seed_ids)),
        'grid':{'nx':lon.shape[1],'ny':lon.shape[0],'west':float(lon[0,0]),'south':float(lat[0,0]),
                'dlon':float(lon[0,1]-lon[0,0]),'dlat':float(lat[1,0]-lat[0,0]),'nominal_km':config['grid_km'],'z_agl_m':Z.tolist()}})


def advance(target):
    # Small batches allow progress messages; no steps are skipped. Worker
    # termination is immediate even while Python is computing.
    for _ in range(10):
        if model.time>=target-1e-6:break
        model.step(target)
    return model.time


def snapshot():
    audit=model.audit_state()
    if abs(audit['water_relative_residual'])>.002:raise FloatingPointError('Water budget failure; simulation stopped')
    return json.dumps({'schema':2,'hour':model.time/3600,
        'fields':{k:pack(v) for k,v in model.fields().items()},'audit':audit},separators=(',',':'),allow_nan=False)
