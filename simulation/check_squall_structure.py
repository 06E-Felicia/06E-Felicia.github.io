"""Matched-seed Astra line geometry, rear cold volume and actual gauges.

No field masks alter weather. Radar exposure and a completed gauge passage
are reported separately; a still-crossing station is not called a dry miss.
"""
import argparse
import json
import re
import time
from pathlib import Path
import numpy as np
from scipy.ndimage import map_coordinates, label, binary_dilation, gaussian_filter1d
from scipy.signal import find_peaks
from .core import Model, VERSION, source_digest
from .experiment import random_environment
from .run import terrain_for


def structure(m,f):
    strong=(f['composite']>=40)&(m.last_rate>=5)&(m.activity>.1)
    regions,count=label(binary_dilation(strong,iterations=1))
    objects=[]
    for ident in range(1,count+1):
        mask=(regions==ident)&strong;y,x=np.nonzero(mask)
        if len(y)<8 or len(np.unique(y))<2:continue
        rows=np.unique(y);front=np.array([np.max(x[y==yy]) for yy in rows])*m.cfg['grid_km']
        north=rows*m.cfg['grid_km'];fit=np.polyval(np.polyfit(north,front,1),north)
        residual=front-fit
        span=float(np.ptp(north)+m.cfg['grid_km'])
        tilt=float(np.degrees(np.arctan(np.polyfit(north,front,1)[0])))
        cold=(m.cold>.5)&(m.cold_depth>100)
        rx=np.indices(m.shape)[1]*m.cfg['grid_km']
        leading=np.interp(np.indices(m.shape)[0][:,0]*m.cfg['grid_km'],north,front)
        rear=cold&(rx<leading[:,None])&(rx>leading[:,None]-150)
        rear&=(m.lat>=m.lat[rows.min(),0])&(m.lat<=m.lat[rows.max(),0])
        source_cape=m.plume_cape(m.donor_field(m.mu['cape']))
        # Independently measure embedded bows and rain/cold-head contrasts.
        # This is diagnosis only: no residual, peak or threshold enters Model.
        smooth=gaussian_filter1d(residual,.65)
        peaks,_=find_peaks(smooth,prominence=m.cfg['grid_km']*.75,distance=max(2,round(30/m.cfg['grid_km'])))
        intensity=np.array([m.last_rate[yy,(regions[yy]==ident)&strong[yy]].mean() for yy in rows])
        pressure=[]
        for yy,leading_x in zip(rows,front):
            behind=(rx[yy]<=leading_x)&(rx[yy]>=leading_x-80)
            pressure.append(float(m.cold_content[yy,behind].max()) if behind.any() else 0.)
        pressure=np.asarray(pressure)
        correlation=float(np.corrcoef(intensity,pressure)[0,1]) if min(intensity.std(),pressure.std())>1e-6 else None
        objects.append({'cells':len(y),'ns_extent_km':span,'tilt_from_north_deg':tilt,
                        'bow_10_90_excursion_km':float(np.percentile(residual,90)-np.percentile(residual,10)),
                        'bow_to_length_ratio':float((np.percentile(residual,90)-np.percentile(residual,10))/span),
                        'mean_native_rain_mm_h':float(m.last_rate[mask].mean()),
                        'mean_organization':float(m.organization[mask].mean()),
                        'mean_activity':float(m.activity[mask].mean()),
                        'mean_initiation':float(m.initiation[mask].mean()),
                        'mean_plume_cape':float(source_cape[mask].mean()),
                        'mean_updraft_fraction':float(m.plume_fraction[mask].mean()),
                        'embedded_bow_count':len(peaks),
                        'along_line_rain_cv':float(intensity.std()/max(intensity.mean(),1e-9)),
                        'along_line_cold_head_cv':float(pressure.std()/max(pressure.mean(),1e-9)),
                        'rain_cold_head_correlation':correlation,
                        'rear_cold_area_km2':int(rear.sum())*m.cfg['grid_km']**2})
    return sorted(objects,key=lambda r:-r['cells'])[:3]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seed',type=int,default=20260423)
    ap.add_argument('--hours',type=int,default=18);ap.add_argument('--grid-km',type=int,choices=[6,8,12],default=12)
    ap.add_argument('--output',required=True);args=ap.parse_args()
    cfg=random_environment(args.seed,{'grid_km':args.grid_km,'hours':args.hours})
    h,terrain=terrain_for(cfg,'assets/data/simulation-terrain.npz');m=Model(cfg,h)
    digest=source_digest('experiment.py','browser.py');started=time.monotonic()
    text=Path('assets/scripts/simulation-v2.js').read_text()
    block=re.search(r'const majorCities=(\{[^;]+\});',text).group(1)
    names=dict(re.findall(r"'([^']+)':'([^']+)'",block))
    stations=[s for s in json.loads(Path('assets/data/simulator-stations.json').read_text())['stations'] if s['id'] in names]
    x=np.array([(s['lon']-m.lon[0,0])/(m.lon[0,1]-m.lon[0,0]) for s in stations])
    y=np.array([(s['lat']-m.lat[0,0])/(m.lat[1,0]-m.lat[0,0]) for s in stations])
    def sample(a,fine=False):return map_coordinates(a,[y*4+1.5,x*4+1.5] if fine else [y,x],order=1,mode='nearest')
    exposure=np.zeros(len(stations));last_exposure=np.full(len(stations),-1.);first=np.full(len(stations),-1.)
    before=np.zeros(len(stations));peak5=exposure.copy();peak_rate=exposure.copy();peak_radar=exposure.copy()
    rows=[];arrays={'lon':m.lon,'lat':m.lat}
    for minute in range(0,args.hours*60+1,5):
        while m.time<minute*60-1e-6:m.step(minute*60)
        # Quantities accumulated every integration step, sampled at 5 min.
        total=sample(m.surface_rain.total,True);rate=sample(m.surface_rain.rate,True)
        peak5=np.maximum(peak5,sample(m.surface_rain.accumulation(300),True));peak_rate=np.maximum(peak_rate,rate)
        from .core import rain_reflectivity,DZ
        echo=np.max(rain_reflectivity(m.rain,m.plume_rain,m.rain_area,m.mass/DZ[:,None,None],m.anvil,m.graupel,m.graupel_area),axis=0)
        radar=sample(echo);peak_radar=np.maximum(peak_radar,radar)
        exposed=radar>=40
        newly=exposed&(first<0);first[newly]=m.time;before[newly]=total[newly]-sample(m.surface_rain.accumulation(300),True)[newly]
        exposure+=exposed*5;last_exposure[exposed]=m.time
        if minute%30==0:
            f=m.fields(include_mixed=False);cold=(m.cold>.5)&(m.cold_depth>100)
            rows.append({'hour':minute/60,'objects':structure(m,f),
                         'cold_area_km2':int(cold.sum())*args.grid_km**2,
                         'cold_volume_km3':float(m.cold_depth[cold].sum()*m.dx**2/1e9),
                         'cold_content':float(m.cold_content.sum()),'audit':m.audit_state()})
            rows[-1]['domain_surface_rain_sum_mm']=float(m.total.sum())
            rows[-1]['remaining_hydrometeor_sum_mm']=float(np.sum((m.rain+m.cloud+m.graupel+m.anvil)*m.mass))
        if minute%120==0:
            print(json.dumps({'hour':minute/60,'cold_area_km2':rows[-1]['cold_area_km2'],
                              'objects':rows[-1]['objects'][:1],'elapsed_s':time.monotonic()-started}),flush=True)
        if minute%60==0 and minute>0:
            for key,a in {'radar':echo,'cold':m.cold,'depth':m.cold_depth,'rain_total':m.total,'point_total':m.surface_rain.total,
                          'rate':m.last_rate,'fraction':m.plume_fraction,'activity':m.activity,'organization':m.organization,
                          'cape':m.available_cape(m.mu['cape']),'air':m.air}.items():arrays[f'h{minute//60}_{key}']=a.copy()
    gauges=[]
    for i,s in enumerate(stations):
        gauges.append({'id':s['id'],'name':names[s['id']],'lon':s['lon'],'lat':s['lat'],
                       'total_mm':float(total[i]),'since_first_40dbz_mm':float(total[i]-before[i]) if first[i]>=0 else None,
                       'radar_exposure_minutes':float(exposure[i]),'peak_radar_dbz':float(peak_radar[i]),
                       'peak5_mm':float(peak5[i]),'peak_rate_mm_h':float(peak_rate[i]),
                       'completed_passage':bool(exposure[i]>=15 and m.time-last_exposure[i]>=7200)})
    cohort=[s['since_first_40dbz_mm'] for s in gauges if s['completed_passage']]
    result={'engine':VERSION,'source_sha256':digest,'edition':'astra','config':cfg,'grid_km':args.grid_km,'terrain':terrain,
            'elapsed_s':time.monotonic()-started,'gauges':gauges,'samples':rows,
            'completed_radar_exposed_gauge_quantiles_mm':np.percentile(cohort,[10,50,90]).tolist() if cohort else [],
            'caveat':'40 dBZ composite exposure is not proof of surface core interception; all 32 gauges, unfinished passages and actual point totals are retained'}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    np.savez_compressed(args.output+'.npz',**arrays)
    print(json.dumps({'gauge_quantiles':result['completed_radar_exposed_gauge_quantiles_mm'],'gauges':gauges},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
