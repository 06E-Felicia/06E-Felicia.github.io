"""Read saved Astra evidence; never retune weather to a fixed screenshot."""
import argparse
import json
from pathlib import Path
from .core import VERSION, source_digest


def summarize(report):
    rows=report['samples']
    bearings=[x for row in rows for x in row['wind500_from_deg']]
    strong=[row['hour'] for row in rows if row['strong_cells']>=10]
    return {
        'seed':report['config']['seed'],'hours':report['config']['hours'],
        'moisture':report['config']['moisture'],
        'first_initiation_h':next((row['hour'] for row in rows if row['new_cells']),None),
        'first_strong_h':next(iter(strong),None),
        'strong_hours':strong,
        'day_two_strong_hours':[hour for hour in strong if 24<=hour<48],
        'wind500_from_range_deg':[min(bearings),max(bearings)],
        'rainrate_peak_mm_h':max(row['rainrate_max_mm_h'] for row in rows),
        'grid_total_peak_mm':max(row['grid_total_max_mm'] for row in rows),
        'point_five_minute_peak_mm':rows[-1]['audit']['point_rain5_peak_mm'],
        'point_total_peak_mm':rows[-1]['audit']['point_total_max_mm'],
        'gust_peak_m_s':rows[-1]['audit']['gust_peak_m_s'],
        'water_max_relative_residual':max(abs(row['audit']['water_relative_residual']) for row in rows),
        'front_latitude_by_hour':{str(row['hour']):row['front_latitude']
                                  for row in rows if row['hour'] in [24,36,48,72]},
        'largest_strong_ns_km':max((obj['ns_km'] for row in rows for obj in row['complexes']),default=0),
    }


def main():
    p=argparse.ArgumentParser();p.add_argument('--process',nargs='+',required=True)
    p.add_argument('--browser',required=True);p.add_argument('--safari');p.add_argument('--output',required=True)
    a=p.parse_args();reports=[json.loads(Path(path).read_text()) for path in a.process]
    browser=json.loads(Path(a.browser).read_text());digest=source_digest('experiment.py','browser.py')
    summaries=[summarize(report) for report in reports]
    full=next(report for report in reports if report['config']['hours']==72)
    full_rows=full['samples'];front24=next(row for row in full_rows if row['hour']==24)
    checks={
        'same_final_astra_source':all(report['source_sha256']==digest and report['edition']=='astra'
                                     and report['grid_km']==12 for report in reports),
        '500hpa_westerly_wsw':all(247.5<=s['wind500_from_range_deg'][0]
                                    <=s['wind500_from_range_deg'][1]<=270 for s in summaries),
        'each_sample_triggers_and_organizes':all(s['first_strong_h'] is not None
                                                and s['largest_strong_ns_km']>=120 for s in summaries),
        'dry_sample_included':any(report['config']['moisture']<.9 for report in reports),
        'three_spring_months':{report['config']['month'] for report in reports}=={3,4,5},
        'first_day_wake_stays_quiet':all(row['new_cells']==0 and row['strong_cells']==0
                                         for row in full_rows if 18<=row['hour']<=24),
        'day_two_warm_sector_not_preempted':min(front24['front_latitude'])>25.5,
        'new_day_two_outbreak_lasts_multiple_samples':sum(24<=r['hour']<48 and r['strong_cells']>=10
                                                          for r in full_rows)>=4,
        'front_continues_south_after_warm_phase':max(full_rows[-1]['front_latitude'])<20,
        'real_convective_rain':all(s['rainrate_peak_mm_h']>=20 and s['point_five_minute_peak_mm']>=10
                                    for s in summaries),
        'water_budget':all(s['water_max_relative_residual']<.002 for s in summaries),
        'gust_not_excessive':all(s['gust_peak_m_s']<=32 for s in summaries),
        'real_browser_final_source':browser['state']=='complete' and browser['manifest']['source_sha256']==digest
                                      and browser['manifest']['engine']==VERSION,
        'nojekyll_present':Path('.nojekyll').is_file(),
    }
    if a.safari:
        safari=json.loads(Path(a.safari).read_text())['results']
        checks['webkit_final_source_starts']=any(row['edition']=='astra' and row['source_sha256']==digest
            and row['engine']==VERSION and row['frames']>=1 and row['progress']>0 and row['error'] is None
            for row in safari)
    result={'engine':VERSION,'source_sha256':digest,'checks':checks,'passed':all(checks.values()),
            'cases':summaries,'scope':'Astra 12-km sampled integrations; not a default 6-km or all-seed guarantee. '
            'Rain peaks are domain maxima, not a promise at every station. Echo fragments are retained.'}
    Path(a.output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
