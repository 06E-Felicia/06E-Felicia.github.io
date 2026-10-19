"""Pyodide bridge; uses exactly the same core as the GitHub Actions runner."""
import json
import time
import numpy as np
from .core import Model, VERSION, Z, source_digest
from .run import terrain_for, pack
from .experiment import random_environment
from . import numerics, thermo

SOL_GRID_KM=28
SOL_FIELDS={'temperature','dewpoint','u10','v10','rainrate','rain_total','rain_hour',
            'gust',
            'mucape','coldair','coldpool','coldpool_depth','organization','composite',
            'u925','v925','u500','v500','u300','v300','terrain',
            't3','q3','p3','u3','v3','w3','dbz3','fall3','echo_u3','echo_v3'}
SOL_FIELDS.update(['point_rainrate','point_rain_total','point_rain_hour','point_rain5'])


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


def initialize(seed, controls, profile='astra'):
    global model, config, selected_profile
    if profile not in ('astra','sol'):raise ValueError('Unknown StormSim edition')
    selected_profile=profile
    controls=json.loads(controls)
    if profile=='sol':
        # Coarsen the horizontal domain, NOT the time axis or physical source
        # terms. Keep all 14 vertical layers, CFL and cold-pool substeps.
        controls={'hours':controls.get('hours',72),'grid_km':SOL_GRID_KM,
                  'frame_minutes':60,'compact_transport':False}
    config=random_environment(seed,controls,grid_limit=SOL_GRID_KM if profile=='sol' else 12)
    height,terrain=terrain_for(config,'assets/data/simulation-terrain.npz')
    model_type=Model
    if profile=='sol':
        from .sol import SolModel
        model_type=SolModel
    model=model_type(config,height,grid_limit=SOL_GRID_KM if profile=='sol' else 12)
    acceleration=select_backends(model)
    lon,lat=model.lon,model.lat
    return json.dumps({'schema':2,'engine':VERSION,'status':'running','simulation':True,
        'source_sha256':source_digest('experiment.py','browser.py',*(['sol.py'] if profile=='sol' else [])),
        'execution':'browser','edition':profile,'product_version':'2.5','config':config,'terrain':terrain,'frames':[],'acceleration':acceleration,
        'rain_grid':model.surface_rain.grid(lon,lat),
        'seed_streams':dict(zip(['initial_temperature','initial_moisture','time_evolution','synoptic','convective_cells'],model.seed_ids)),
        'grid':{'nx':lon.shape[1],'ny':lon.shape[0],'west':float(lon[0,0]),'south':float(lat[0,0]),
                'dlon':float(lon[0,1]-lon[0,0]),'dlat':float(lat[1,0]-lat[0,0]),'nominal_km':config['grid_km'],'z_agl_m':Z.tolist()}})


def advance(target, batch=10):
    # Small batches allow progress messages; no steps are skipped. Worker
    # termination is immediate even while Python is computing.
    for _ in range(max(1,min(10,int(batch)))):
        if model.time>=target-1e-6:break
        model.step(target)
    return model.time


def snapshot():
    audit=model.audit_state()
    if abs(audit['water_relative_residual'])>.002:raise FloatingPointError('Water budget failure; simulation stopped')
    fields=model.fields(include_mixed=selected_profile!='sol')
    fields.update(model.surface_rain.fields())
    if selected_profile=='sol':fields={k:v for k,v in fields.items() if k in SOL_FIELDS}
    return json.dumps({'schema':2,'hour':model.time/3600,
        'fields':{k:pack(v) for k,v in fields.items()},'audit':audit},separators=(',',':'),allow_nan=False)
