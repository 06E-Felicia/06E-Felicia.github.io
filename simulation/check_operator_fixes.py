"""Fast reproducible closure and cropped postfrontal process probes."""
import argparse
import json
from pathlib import Path
import numpy as np
from .core import Model, VERSION, source_digest
from .terrain import grid
from .numerics import Advection
from .precipitation import SurfaceRain


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args()
    cfg={'seed':20260423,'bounds':[112,22,113,23],'grid_km':12}
    m=Model(cfg,np.full(grid(cfg['bounds'],12)[0].shape,30.))
    before=float(m.mu['cape'].mean());old=m.frontal_layers();m.air.fill(.999999)
    zero=np.zeros_like(m.q)
    m.transport_front_thermodynamics(old,m.frontal_layers(),Advection(zero,zero,m.dx),90)
    m.diagnostics()
    front={'before_raw_cape_mean':before,'after_raw_cape_mean':float(m.mu['cape'].mean()),
           'water_relative_residual':m.audit_state()['water_relative_residual']}
    m=Model(cfg,np.full(grid(cfg['bounds'],12)[0].shape,30.))
    old=m.frontal_layers();m.air.fill(1);zero=np.zeros_like(m.q)
    m.transport_front_thermodynamics(old,m.frontal_layers(),Advection(zero,zero,m.dx),90)
    m.synoptic.front_lat.fill(19);m.syn_u,m.syn_v=m.synoptic.surface_target(m.air,0)
    m.u=m.syn_u.copy();m.v=m.syn_v.copy();m.diagnostics();peak=0
    while m.time<21600-1e-6:
        m.step(21600);peak=max(peak,float(m.initiation.max()))
    f=m.fields(include_mixed=False)
    postfront={'scope':'12 km, cropped flat 112-113E / 22-23N, controlled deep cold-air entry; 6 h actual steps with soil/surface fluxes retained',
               'mucape_mean':float(f['mucape'].mean()),'mucape_max':float(f['mucape'].max()),
               'peak_new_initiation':peak,'water_residual':m.audit_state()['water_relative_residual']}
    m=Model(cfg,np.full(grid(cfg['bounds'],12)[0].shape,30.))
    m.cold_depth.fill(600);m.cold_content.fill(2400);m.cold_mx[:]=600*m.syn_u;m.cold_my[:]=600*m.syn_v
    m.cold_diagnostics();m.cape_deficit.fill(800);cold=[]
    for hour in range(5):
        cold.append({'hour':hour,'deficit_K':float(m.cold.max()),'depth_m':float(m.cold_depth.max()),
                     'remaining_cape_debt':float(m.cape_deficit.min())})
        for _ in range(40):m.recover_cold_pool(90,np.zeros(m.shape),0)
    shape=(8,8);z=np.zeros(shape);a,b=[SurfaceRain(shape,13) for _ in range(2)]
    for step in range(40):
        for rain in (a,b):rain.advance((step+1)*30,30,z+.25,z,z+.125,velocity=(z+15,z+5) if rain is b else None,dx=12000)
    rain={}
    for name,r in [('stationary',a),('advected',b)]:
        coarse=r.total.reshape(8,4,8,4).mean(axis=(1,3),dtype='float64')
        rain[name]={'fraction_below_half_mm':float((r.total<.5).mean()),'point_total_percentiles_mm':np.percentile(r.total,[10,50,90]).tolist(),
                    'max_native_water_error_mm':float(np.max(np.abs(coarse-10)))}
    checks={'material_front_reduces_actual_energy':front['after_raw_cape_mean']<front['before_raw_cape_mean']*.15,
            'controlled_postfront_does_not_reignite':peak==0 and postfront['mucape_mean']<before*.1,
            'cold_pool_under_half_kelvin_at_four_hours':cold[4]['deficit_K']<.5,
            'retirement_does_not_restore_consumed_cape':cold[4]['remaining_cape_debt']==800,
            'moving_shafts_reduce_false_dry_holes':rain['advected']['fraction_below_half_mm']<rain['stationary']['fraction_below_half_mm']*.5,
            'native_rain_conserved':max(r['max_native_water_error_mm'] for r in rain.values())<1e-5}
    report={'engine':VERSION,'source_sha256':source_digest('experiment.py','browser.py'),
            'scope':'Isolated closures plus one cropped 6 h postfrontal integration, not a full South-China run',
            'checks':checks,'front':front,'postfront_six_hour':postfront,'source_free_cold_pool':cold,'rain_footprint_probe':rain}
    Path(args.output).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if not all(checks.values()):raise SystemExit(1)


if __name__=='__main__':main()
