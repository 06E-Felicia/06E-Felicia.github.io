"""Full-domain Astra/Sol process checks, including point/event statistics.

Not a forecast skill score. Astra defaults to its supported 12 km grid;
6 km is never silently substituted or claimed as tested.
"""
import argparse
import json
import re
import time
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates
from .core import Model,VERSION,source_digest
from .experiment import random_environment
from .run import terrain_for
from .validate import morphology,LineTracker


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=20260421)
    ap.add_argument('--hours',type=int,default=72);ap.add_argument('--output',required=True)
    ap.add_argument('--edition',choices=['astra','sol'],default='astra');ap.add_argument('--grid-km',type=int,default=12)
    ap.add_argument('--frontal-case',action='store_true',help='Controlled entered-front initial condition, NOT an unmodified random-weather run')
    ap.add_argument('--checkpoint-file',help='Optional trusted local pickle for causal follow-up; never deployed to the public site')
    ap.add_argument('--checkpoint-at-hour',type=int,default=0)
    args=ap.parse_args();km=28 if args.edition=='sol' else args.grid_km
    if args.edition=='astra' and km not in [4,6,8,12]:ap.error('Astra grid must be 4/6/8/12 km')
    cfg=random_environment(args.seed,{'grid_km':km,'frame_minutes':60,'hours':args.hours},grid_limit=28 if args.edition=='sol' else 12)
    height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz');m=Model(cfg,height,grid_limit=28 if args.edition=='sol' else 12)
    if args.frontal_case:
        from .core import Z
        from .thermo import saturation
        old=m.air.copy();old_layers=m.frontal_layers().copy()
        m.synoptic.front_lat.fill(23.8);m.air=m.synoptic.external_air()
        m.temp-=7*(m.frontal_layers()-old_layers)*np.exp(-Z[:,None,None]/5000)
        m.q=np.minimum(m.q*np.exp(-.22*(m.air-old))[None],saturation(m.temp,m.p)*.98)
        m.syn_u,m.syn_v=m.synoptic.surface_target(m.air,0);m.u=m.syn_u.copy();m.v=m.syn_v.copy()
        m.trough_lon=111;m.initial_water=float(np.sum(m.q*m.mass,dtype='float64'));m.diagnostics()
    # Use the PUBLIC UI's exact representative IDs and actual archived station
    # coordinates, never substitute city centres for point-gauge verification.
    source=Path('assets/scripts/simulation-v2.js').read_text()
    block=re.search(r'const majorCities=(\{[^;]+\});',source).group(1)
    names=dict(re.findall(r"'([^']+)':'([^']+)'",block))
    station_data=json.loads(Path('assets/data/simulator-stations.json').read_text())['stations']
    cities={names[s['id']]:(s['lon'],s['lat']) for s in station_data if s['id'] in names}
    if len(cities)!=32:raise ValueError('Public representative station set changed; inspect verification selection')
    x=np.array([v[0] for v in cities.values()]);y=np.array([v[1] for v in cities.values()])
    nx=(x-m.lon[0,0])/(m.lon[0,1]-m.lon[0,0]);ny=(y-m.lat[0,0])/(m.lat[1,0]-m.lat[0,0])
    def sample(a,fine=False):
        return map_coordinates(a,[ny*4+1.5,nx*4+1.5] if fine else [ny,nx],order=1,mode='nearest')
    rain5=np.zeros(len(cities));gust_extra=np.zeros(len(cities));city_gust=np.zeros(len(cities))
    events=[[] for _ in cities];start_total=np.zeros(len(cities));last_rain=np.full(len(cities),-1e9);active=np.zeros(len(cities),bool)
    last_core=np.full(m.shape,-1e9);last_native=m.total.copy();six_hour=np.zeros(m.shape);six_hour_peak=np.zeros(m.shape)
    rows=[];snapshots={};started=time.monotonic();tracker=LineTracker(km)
    fine_previous=m.surface_rain.total.copy();fine_six=np.zeros_like(fine_previous);fine_six_peak=np.zeros_like(fine_previous);fine_five_peak=np.zeros_like(fine_previous)
    for minute in range(0,args.hours*60+1,5):
        target=minute*60
        while m.time<target-1e-6:m.step(target)
        point_total=sample(m.surface_rain.total,True);rate=sample(m.surface_rain.rate,True)
        five=m.surface_rain.accumulation(300);last_five=sample(five,True);rain5=np.maximum(rain5,last_five)
        fine_five_peak=np.maximum(fine_five_peak,five);fine_six+=m.surface_rain.total-fine_previous;fine_previous=m.surface_rain.total.copy()
        wind=sample(np.hypot(m.u,m.v));gust=sample(m.surface_gust())
        city_gust=np.maximum(city_gust,gust);gust_extra=np.maximum(gust_extra,gust-wind)
        for i in range(len(cities)):
            if rate[i]>=5:
                if not active[i]:start_total[i]=point_total[i]-last_five[i];active[i]=True
                last_rain[i]=m.time
            if active[i] and (m.time-last_rain[i]>=7200 or minute==args.hours*60):
                events[i].append(float(point_total[i]-start_total[i]));active[i]=False
        deep=(m.activity>.1)&(m.last_rate>5);last_core[deep]=m.time
        six_hour+=m.total-last_native;last_native=m.total.copy()
        if minute%60==0:
            shape,_,curved_masks=morphology(m,with_curved_masks=True);tracker.update(m.time/3600,shape['curved_band_candidates'],curved_masks)
            f=m.fields(include_mixed=args.edition=='astra')
            f['convective_anvil_column']=np.sum(m.anvil_convective*m.mass,axis=0)
            f['environmental_anvil_column']=np.sum(np.maximum(m.anvil-m.anvil_convective,0)*m.mass,axis=0)
            weak=(f['composite']>=5)&(f['composite']<35)
            old=(last_core>0)&(m.time-last_core>6*3600)&(m.air<.15)
            front=shape['front_regional_latitude']
            row={'hour':minute/60,'front':front,'front_coverage':shape['front_coverage'],
                 'front_convective_cells':int(((m.air>.1)&(m.air<.7)&(f['composite']>=35)&(m.last_rate>=5)&(m.activity>.1)).sum()),
                 'driver_latitude_range':[float(m.synoptic.front_lat.min()),float(m.synoptic.front_lat.max())],
                 'strong_cells':shape['strong_cells'],'old_warm_wake_cells':int(old.sum()),
                 'weak_echo_in_old_wake':int((old&weak).sum()),
                 'longest_ns_km':max((o.get('ns_extent_km',0) for o in shape['largest_objects']),default=0),
                 'largest_objects':shape['largest_objects'],
                 'winds':{str(p):[float(np.nanmean(f['u'+str(p)])),float(np.nanmean(f['v'+str(p)]))] for p in [925,500,300]},
                 'audit':m.audit_state()};rows.append(row)
            if minute%360==0:
                six_hour_peak=np.maximum(six_hour_peak,six_hour);six_hour.fill(0)
                fine_six_peak=np.maximum(fine_six_peak,fine_six);fine_six.fill(0)
                print(json.dumps({'hour':minute/60,'front':front,'rain_max':float(m.total.max()),'rain5_peak':m.surface_rain.max_five,'elapsed_s':time.monotonic()-started}),flush=True)
                for k in ['composite','rain_total','rainrate','coldpool','coldair','u500','v500','convective_anvil_column','environmental_anvil_column']:
                    snapshots[f'h{minute//60}_{k}']=f[k]
        if args.checkpoint_file and args.checkpoint_at_hour>0 and minute==args.checkpoint_at_hour*60:
            import pickle
            with Path(args.checkpoint_file+'.h'+str(args.checkpoint_at_hour)).open('wb') as destination:pickle.dump(m,destination,protocol=5)
    city_rows={name:{'total_mm':float(point_total[i]),'peak5_mm':float(rain5[i]),'peak_gust_m_s':float(city_gust[i]),
                          'peak_gust_increment_m_s':float(gust_extra[i]),'rain_events_mm':events[i]} for i,name in enumerate(cities)}
    output={'engine':VERSION,'source_sha256':source_digest('experiment.py','browser.py'),'seed':args.seed,
            'edition':args.edition,'grid_km':km,
            'station_sampling':'Exact 32 public UI station IDs and archived coordinates; same fine-grid bilinear sampler',
            'controlled_entered_front':args.frontal_case,
            'execution':f'native {args.edition} {km} km, five-minute point sampling; not browser performance',
            'elapsed_s':time.monotonic()-started,'cities':city_rows,'samples':rows,
            'line_tracks':tracker.tracks,
            'core_hit_six_hour_rain_quantiles_mm':np.percentile(fine_six_peak[fine_five_peak>=10],[10,50,90,100]).tolist() if np.any(fine_five_peak>=10) else [],
            'six_hour_native_rain_quantiles_mm':np.percentile(six_hour_peak[six_hour_peak>5],[10,50,90,100]).tolist() if np.any(six_hour_peak>5) else []}
    Path(args.output).write_text(json.dumps(output,indent=2));np.savez_compressed(args.output+'.npz',lon=m.lon,lat=m.lat,**snapshots)
    if args.checkpoint_file:
        import pickle
        with Path(args.checkpoint_file).open('wb') as destination:pickle.dump(m,destination,protocol=5)
    print(json.dumps({'cities':city_rows,'six_hour_native_rain_quantiles_mm':output['six_hour_native_rain_quantiles_mm'],'elapsed_s':output['elapsed_s']}),flush=True)


if __name__=='__main__':main()
