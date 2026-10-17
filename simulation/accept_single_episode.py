"""Acceptance of saved Astra results, without another weather integration."""
import argparse
import json
import numpy as np
from pathlib import Path
from .core import source_digest,VERSION


def summarize(r):
    rows=r['samples']
    mature=lambda s:[o for o in s['complexes'] if max(o['ns_km'],o['ew_km'])>=120]
    return {'seed':r['config']['seed'],'month':r['config']['month'],'hours':r['config']['hours'],
            'first_initiation_h':next((s['hour'] for s in rows if s['new_cells']>0),None),
            'first_strong_echo_h':next((s['hour'] for s in rows if s['strong_cells']>0),None),
            'max_mature_components':max(len(mature(s)) for s in rows),
            'max_ns_extent_km':max((o['ns_km'] for s in rows for o in mature(s)),default=0),
            'gust_peak_m_s':max(s['audit']['gust_peak_m_s'] for s in rows),
            'point_rain5_peak_mm':max(s['audit']['point_rain5_peak_mm'] for s in rows),
            'water_max_relative_residual':max(abs(s['audit']['water_relative_residual']) for s in rows),
            'first_day_quiet_18_24h':all(s['new_cells']==0 for s in rows if 18<=s['hour']<24),
            'second_day_strong_hours':[s['hour'] for s in rows if 24<=s['hour']<48 and s['strong_cells']>=8],
            'days_with_initiation':sorted({s['episode_day'] for s in rows if s['new_cells']>0})}


def main():
    p=argparse.ArgumentParser();p.add_argument('--process',nargs='+',required=True)
    p.add_argument('--browser',required=True);p.add_argument('--fragment',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();reports=[json.loads(Path(x).read_text()) for x in a.process]
    browser=json.loads(Path(a.browser).read_text());rows=[summarize(r) for r in reports]
    digest=source_digest('experiment.py','browser.py')
    def one_origin(r):
        days={s['episode_day'] for s in r['samples']}
        return all(len({tuple(s['genesis_center']) for s in r['samples']
                        if s['episode_day']==day and s['genesis_center'] is not None})<=1 for day in days)
    fragment=json.loads(Path(a.fragment).read_text());split=next(s for s in fragment['samples'] if s['hour']==10.5)
    pieces=[o for o in split['complexes'] if max(o['ns_km'],o['ew_km'])>=120]
    pieces.sort(key=lambda o:o['south'])
    disjoint=(len(pieces)==2 and pieces[0]['north']<pieces[1]['south'])
    whole_index=next(i for i,r in enumerate(reports) if r['config']['hours']==72)
    with np.load(a.process[whole_index]+'.npz') as whole,np.load(a.fragment+'.npz') as detail:
        identical_prefix=all(np.array_equal(whole[f'h{hour}_radar'],detail[f'h{hour}_radar']) for hour in [6,10,11])
        def front(hour):
            strong=(detail[f'h{hour}_radar']>=40)&(detail[f'h{hour}_rate']>=5)&(detail[f'h{hour}_activity']>.1)
            y,x=np.nonzero(strong);rows=np.unique(y)
            return rows,np.array([max(x[y==row]) for row in rows])*fragment['grid_km']
        r0,f0=front('10');r1,f1=front('11');r,actual=front('10.5')
        expected=.5*(np.interp(r,r0,f0)+np.interp(r,r1,f1))
        front_error=float(np.max(np.abs(actual-expected)))
        # A tilted front's north/south pieces need not overlap in longitude.
        # Diagnose continuity against the actual preceding/following front,
        # not a vertical-map assumption or a new independent rain object.
        same_corridor=front_error<=4*fragment['grid_km']
    checks={'same_final_astra_source':all(r['source_sha256']==digest and r['edition']=='astra' and r['grid_km']==12 for r in reports),
            'three_spring_months':{r['month'] for r in rows}=={3,4,5},
            'one_configured_independent_origin_per_episode':all(one_origin(r) for r in reports),
            'primary_line_organizes_in_each_sample':all(r['max_mature_components']>=1 for r in rows),
            'split_is_along_one_front_not_parallel_rear_line':disjoint and same_corridor and identical_prefix and fragment['source_sha256']==digest,
            'new_second_day_episode_not_first_day_wake':any(r['hours']==72 and r['first_day_quiet_18_24h'] and r['second_day_strong_hours'] for r in rows),
            'gust_envelope':all(0<r['gust_peak_m_s']<=32 for r in rows),
            'real_heavy_rain_retained':all(r['point_rain5_peak_mm']>=10 for r in rows),
            'water_budget':all(r['water_max_relative_residual']<.002 for r in rows),
            'real_browser_uses_final_source':browser['manifest']['source_sha256']==digest and browser['manifest']['engine']==VERSION and browser['state']=='complete',
            'nojekyll_present':Path('.nojekyll').is_file()}
    result={'engine':VERSION,'source_sha256':digest,'checks':checks,'passed':all(checks.values()),'processes':rows,
            'diagnostics':{'strict_one_connected_strong_echo_component':all(r['max_mature_components']==1 for r in rows),
                           'split_hour':10.5,'split_pieces':pieces,'front_interpolation_max_error_km':front_error,
                           'note':'Strong fragments are not independent genesis episodes. Strict connectivity is retained as a diagnostic, not falsely called passed.'},
            'scope':'Astra 12-km sampled integrations, not all seeds or default 6-km accuracy; component cutoff is 1500 km2 and >=120-km extent, not a universal squall-line definition; fragments retained in source reports'}
    Path(a.output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
