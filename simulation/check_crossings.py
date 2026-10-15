"""Idealized warm-cell transfer checks, NOT real-case or radar calibration.

Only this TEST seeds a finite updraft/cold pool. Production initialization
still has no storm objects, tracks or prescribed rain. All later evolution
uses the same core, with identical random seeds in the paired environments.
"""
import json
import numpy as np
from .core import Model, VERSION, Z, settings, rain_reflectivity, DZ
from .terrain import grid


def run_case(kind,time_offset=0):
    cfg=settings({'bounds':[111,22,113.8,23.4],'grid_km':8,'hours':3,
                  'seed':611,'trough':0,'sst_c':21,'stochastic':.4})
    lon,lat=grid(cfg['bounds'],cfg['grid_km'])
    h=np.ones(lon.shape)
    if kind=='ridge':h+=1400*np.exp(-((lon-112.05)/.12)**2)
    if kind=='water':h=np.where((lon>111.95)&(lon<112.8),0,h)
    m=Model(cfg,h)
    # A clock jump left the SAME 08:00 sounding at 14:00 and 04:00, bypassing
    # the very land heating/mixing and nighttime jet being checked. Evolve
    # the actual background to the requested hour before seeding the test.
    while m.time<time_offset*3600-1e-6:m.step(time_offset*3600)
    pool=np.exp(-((lon-111.35)/.16)**2-((lat-22.65)/.2)**2)
    m.cold_depth=500*pool;m.cold_content=4*m.cold_depth
    m.cold_source=float(m.cold_content.sum());m.cold_diagnostics()
    m.temp-=m.cold[None]*np.exp(-Z[:,None,None]/600)
    m.activity=.75*np.exp(-((lon-111.40)/.09)**2-((lat-22.65)/.12)**2)
    m.surface_activity=m.activity*np.clip(m.sb['cape']/np.maximum(m.mu['cape'],100),0,1)
    m.diagnostics()
    receiving=(lon>112.05)&(lon<112.7)&(lat>22.2)&(lat<23.1)
    rows=[]
    for target in np.arange(0,10801,900):
        physical_target=target+time_offset*3600
        while m.time<physical_target-1e-6:m.step(physical_target)
        if target>=3600:
            echo=np.max(rain_reflectivity(m.rain,m.plume_rain,m.rain_area,m.mass/DZ[:,None,None]),axis=0)
            rows.append({'hour':target/3600,'active':float(m.activity[receiving].mean()),
                         'new_activity':float(m.initiation[receiving].mean()),
                         'new_plume_area':float((m.initiation*m.plume_fraction)[receiving].mean()),
                         'rain_mean':float(m.last_rate[receiving].mean()),
                         'strong_echo_cells':int(np.sum(echo[receiving]>40))})
    return {'case':kind,'initial_local_hour':(8+time_offset)%24,'background_hours':time_offset,'mean_received_activity':float(np.mean([r['active'] for r in rows])),
            'mean_received_new_activity':float(np.mean([r['new_activity'] for r in rows])),
            'mean_received_new_plume_area':float(np.mean([r['new_plume_area'] for r in rows])),
            'mean_received_rain_mm_h':float(np.mean([r['rain_mean'] for r in rows])),
            'peak_received_strong_echo_cells':max(r['strong_echo_cells'] for r in rows),
            'audit':m.audit_state(),'samples':rows}


if __name__=='__main__':
    rows=[run_case(kind) for kind in ['plain','ridge','water']]
    daily=[run_case('plain',time_offset=t) for t in [6,20]]
    print(json.dumps({'engine':VERSION,'seed':611,'hours':3,'grid_km':8,'cases':rows,'daily_cases':daily},indent=2))
    for row in rows[1:]:
        # Eligibility or weak new-cloud area need not decrease: windward CI
        # and elevated maritime showers are legitimate. Test ACTUAL visible
        # intensity, not the raw trigger flag. Original implementation failed
        # both these checks; a radar colour/mask change cannot satisfy rainfall.
        if row['mean_received_rain_mm_h']>=.85*rows[0]['mean_received_rain_mm_h']:
            raise SystemExit('Crossing check did not reduce rainfall: '+row['case'])
        if row['peak_received_strong_echo_cells']>=.8*rows[0]['peak_received_strong_echo_cells']:
            raise SystemExit('Crossing check did not weaken strong echoes: '+row['case'])
    intensity=[r['mean_received_rain_mm_h'] for r in daily]
    if abs(intensity[0]-intensity[1])<.1*max(intensity):
        raise SystemExit('Day/night physical forcings do not appreciably change this test storm')
