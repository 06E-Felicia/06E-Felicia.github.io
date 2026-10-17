"""Compare saved Astra weather, retaining residual echoes and all segments."""
import argparse
import hashlib
import json
import pickle
import tempfile
from pathlib import Path
import numpy as np
from .core import VERSION, source_digest


def main():
    p=argparse.ArgumentParser();p.add_argument('--process',nargs=2,required=True)
    p.add_argument('--baseline',nargs=2,required=True);p.add_argument('--browser',required=True)
    p.add_argument('--output',required=True);a=p.parse_args()
    digest=source_digest('experiment.py','browser.py');comparisons=[];cases=[];fronts=[];grids={}
    for current,old in zip(a.process,a.baseline):
        r=json.loads(Path(current).read_text());b=json.loads(Path(old).read_text())
        assert r['source_sha256']==digest and r['edition']=='astra' and r['grid_km']==12
        assert r['config']['seed']==b['config']['seed']
        with np.load(current+'.npz') as new,np.load(old+'.npz') as before:
            np.testing.assert_array_equal(new['lon'],before['lon']);np.testing.assert_array_equal(new['lat'],before['lat'])
            # Fixed warm-sector ROI, away from the legitimate northern front.
            region=(new['lon']>106)&(new['lon']<117)&(new['lat']>21)&(new['lat']<24.5)
            for hour in [12,18]:
                key=f'h{hour}_radar'
                if key not in before or key not in new:continue
                row={'seed':r['config']['seed'],'hour':hour}
                for threshold in [5,15]:
                    def area(data):return int(((data[key]>=threshold)&(data[f'h{hour}_activity']<.05)&region).sum())*144
                    old_area,new_area=area(before),area(new)
                    row[str(threshold)]={'before_km2':old_area,'after_km2':new_area,'ratio':new_area/max(old_area,1)}
                comparisons.append(row)
        def span(report):return max((o['ns_km'] for s in report['samples'] if s['hour']<=12 for o in s['complexes']),default=0)
        rows=r['samples'];cases.append({'seed':r['config']['seed'],'hours':r['config']['hours'],
            'first_episode_ns_km':span(r),'previous_first_episode_ns_km':span(b),
            'rainrate_peak_mm_h':max(s['rainrate_max_mm_h'] for s in rows),
            'five_minute_point_peak_mm':rows[-1]['audit']['point_rain5_peak_mm'],
            'gust_peak_m_s':rows[-1]['audit']['gust_peak_m_s'],
            'water_max_relative_residual':max(abs(s['audit']['water_relative_residual']) for s in rows)})
        # Only this task's trusted, same-source local checkpoint is read.
        token=hashlib.sha256(str(Path(current).resolve()).encode()).hexdigest()[:16]
        with (Path(tempfile.gettempdir())/('stormsim-checkpoint-'+token+'.pkl')).open('rb') as f:state=pickle.load(f)
        assert state['digest']==digest
        m=state['model'];points=[]
        for x in range(m.shape[1]):
            column=m.air[:,x]
            for y in np.flatnonzero((column[:-1]<.5)&(column[1:]>=.5)):
                latitude=m.lat[y,x]+(.5-column[y])/(column[y+1]-column[y])*(m.lat[y+1,x]-m.lat[y,x])
                points.append([float(m.lon[y,x]),float(latitude)])
        if len(points)>3:
            x,y=np.asarray(points).T;residual=y-np.polyval(np.polyfit(x,y,1),x)
            fronts.append({'seed':m.cfg['seed'],'hour':m.time/3600,'latitude_span_deg':float(np.ptp(y)),
                           'detrended_bend_deg':float(np.ptp(residual)),'actual_air_half_contour_points':points})
        grids[str(m.cfg['seed'])+'_coldair']=m.air;grids[str(m.cfg['seed'])+'_pressure_front']=m.synoptic.front_lat
        grids['lon']=m.lon;grids['lat']=m.lat;grids['terrain']=m.h
    browser=json.loads(Path(a.browser).read_text())
    checks={'final_source_real_astra':len(cases)==2,
        'warm_residual_5dbz_area_at_least_halved':all(row['5']['ratio']<=.5 for row in comparisons),
        'warm_residual_15dbz_area_at_least_halved':all(row['15']['ratio']<=.5 for row in comparisons),
        'modest_extra_line_extent_realized_in_a_sample':any(c['first_episode_ns_km']>c['previous_first_episode_ns_km'] for c in cases),
        'no_giant_north_south_line':all(120<=c['first_episode_ns_km']<=400 for c in cases),
        # A front may legitimately have left a completed run's domain.
        'actual_material_front_has_bends':bool(fronts) and all(f['detrended_bend_deg']>.1 for f in fronts),
        'heavy_rain_retained':all(c['rainrate_peak_mm_h']>=20 and c['five_minute_point_peak_mm']>=10 for c in cases),
        'wind_envelope_and_water_budget':all(c['gust_peak_m_s']<=32 and c['water_max_relative_residual']<.002 for c in cases),
        'real_browser_final_source':browser['state']=='complete' and browser['manifest']['source_sha256']==digest,
        'nojekyll':Path('.nojekyll').is_file()}
    report={'engine':VERSION,'source_sha256':digest,'checks':checks,'passed':all(checks.values()),
        'echo_area_comparisons':comparisons,'cases':cases,'material_fronts':fronts,
        'scope':'Astra 12-km sampled runs, not default 6-km or all-seed proof. Wider initiation does not force every seed to grow longer. '
                'Normal frontal/orographic/stratiform rain and all weak echoes remain in saved data; no display masking.'}
    Path(a.output).write_text(json.dumps(report,indent=2));np.savez_compressed(a.output+'.fronts.npz',**grids)
    print(json.dumps({k:report[k] for k in ['engine','source_sha256','checks','passed','echo_area_comparisons','cases']},indent=2))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
