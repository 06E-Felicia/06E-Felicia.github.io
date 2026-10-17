"""Check saved matched-source evidence only; never advances a weather step."""
import argparse
import json
from pathlib import Path
import numpy as np
from .core import source_digest,VERSION


def main():
    ap=argparse.ArgumentParser()
    for name in ['process','warm','moist','baseline','operators','coastal','browser','links','output']:
        ap.add_argument('--'+name,required=True)
    args=ap.parse_args()
    docs={name:json.loads(Path(getattr(args,name)).read_text()) for name in
          ['process','warm','moist','baseline','operators','coastal','browser','links']}
    p,w,m,old,o,c,b=[docs[k] for k in ['process','warm','moist','baseline','operators','coastal','browser']]
    digest=source_digest('experiment.py','browser.py')
    links=docs['links']
    objects=[(row['hour'],obj) for run in [w,m] for row in run['samples'] for obj in row['objects'] if 2<=row['hour']<=8]
    main=[obj for hour,obj in objects if obj['ns_extent_km']>=150]
    contrast=[obj for obj in main if obj['rain_cold_head_correlation'] is not None]
    late=[r for r in p['samples'] if r['hour']>=48]
    audits=[r['audit'] for run in [p,w,m] for r in run['samples']]
    cities={s['id']:s for s in w['gauges']};prior={s['id']:s for s in old['gauges']}
    # All 32 public gauges, with no rain/radar/completion-based filtering.
    paired=sorted(cities.keys()&prior.keys())
    old_total=[prior[k]['total_mm'] for k in paired];new_total=[cities[k]['total_mm'] for k in paired]
    old_median=float(np.median(old_total));new_median=float(np.median(new_total))
    hits=[{'seed':run['config']['seed'],'station':s['name'],'total_mm':s['total_mm'],'peak5_mm':s['peak5_mm']}
          for run in [w,m] for s in run['gauges'] if s['total_mm']>=20 and s['peak5_mm']>=10]
    checks={
        'same_final_source':all(r['engine']==VERSION and r['source_sha256']==digest for r in [p,w,m,o,c,b['manifest'],links]),
        'real_astra_processes':all(r['edition']=='astra' and r['grid_km']==12 for r in [p,w,m]),
        'whole_72h_and_two_warm_processes':p['samples'][-1]['hour']==72 and w['samples'][-1]['hour']==18 and m['samples'][-1]['hour']==12,
        'multibow_and_strong_weak_cold_head_contrast_observed':any(obj['embedded_bows']>=2 and obj['ns_extent_km']>=150 and (obj['rain_cold_head_correlation_with_links'] or 0)>.2 and obj['strong_to_weak_head_content_ratio']>1.05 and obj['strong_to_weak_cold_volume_ratio']>1.05 for obj in links['samples']),
        'main_active_components_not_single_giant_bows':bool(main) and max(obj['ns_extent_km'] for obj in main)<=500 and max(obj['bow_10_90_excursion_km'] for obj in main)<=120,
        'actual_32_gauge_median_not_reduced':len(paired)==32 and new_median>=old_median,
        'observed_heavy_gauge_passage_not_just_domain_peak':bool(hits),
        'native_water_budget':max(abs(a['water_relative_residual']) for a in audits)<2e-5,
        'no_late_strong_redevelopment':all(r['strong_echo_fraction']==0 and r['audit']['max_rain_mm_h']<5 for r in late),
        'coastal_obstacles_have_measured_response':all(0<r['fine_relief_to_mean_only_downwind_ratio']<.95 for r in c['sites']),
        'coastal_current_inventory_conserved':max(abs(case['cold_content_relative_residual']) for r in c['sites'] for case in r['cases'])<1e-9,
        'real_worker_wasm_new_terrain_playback':b['edition']=='astra' and b['state']=='complete' and b['manifest']['terrain']['coastal_detail']['grid_km']==.25,
        'nojekyll_preserved':Path('.nojekyll').is_file(),
        **o['checks']}
    details={'main_active_component_ns_range_km':[min(obj['ns_extent_km'] for obj in main),max(obj['ns_extent_km'] for obj in main)] if main else [],
             'main_active_component_bow_max_km':max((obj['bow_10_90_excursion_km'] for obj in main),default=0),
             'main_rain_cold_head_correlation_median':float(np.median([obj['rain_cold_head_correlation'] for obj in contrast])) if contrast else None,
             'all_32_gauge_median_before_after_mm':[old_median,new_median],
             'old_strong_pixels_only_contrast_threshold_passed':any(obj['embedded_bow_count']>=2 and obj['along_line_rain_cv']>.15 and obj['along_line_cold_head_cv']>.05 and (obj['rain_cold_head_correlation'] or 0)>.2 for obj in main),
             'contrast_metric_revision':'Old >=40dBZ-pixels-only mean excluded the weak links. Its strict result is retained here; required contrast uses fixed front-relative strips including those links, not changed weather or a relaxed numeric threshold.',
             'all_32_gauges':[{'name':cities[k]['name'],'before_mm':prior[k]['total_mm'],'after_mm':cities[k]['total_mm']} for k in paired],
             'actual_station_heavy_passages':hits,'late_weak_initiations':[{'hour':r['hour'],'fraction':r['new_fraction'],'max_rain_mm_h':r['audit']['max_rain_mm_h']} for r in late if r['new_fraction']>0]}
    result={'engine':VERSION,'source_sha256':digest,'all_passed':all(checks.values()),'checks':checks,'details':details,
            'scope':'Project regression thresholds for these Astra 12-km seeds and controlled 6-km obstacle probes, not forecast skill, every-gauge 20-40mm certification, or full default 6-km weather verification'}
    Path(args.output).write_text(json.dumps(result,indent=2,ensure_ascii=False));print(json.dumps(result,indent=2,ensure_ascii=False))
    if not result['all_passed']:raise SystemExit(1)


if __name__=='__main__':main()
