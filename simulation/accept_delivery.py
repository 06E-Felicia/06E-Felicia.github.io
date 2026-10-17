"""Explicit acceptance gates for THIS sample set, not forecast-skill claims."""
import argparse
import json
from pathlib import Path
import numpy as np
from .core import VERSION,source_digest


def main():
    ap=argparse.ArgumentParser()
    for arg in ['process','stations','wake','frontal','secondary','output']:ap.add_argument('--'+arg,required=True)
    args=ap.parse_args();docs={k:json.loads(Path(getattr(args,k)).read_text()) for k in ['process','stations','wake','frontal','secondary']}
    checks={};details={};digest=source_digest('experiment.py','browser.py')
    checks['final_source_matches_all_astra_evidence']=all(r['engine']==VERSION and r['source_sha256']==digest for r in docs.values())
    checks['astra_only_process_validation']=all(docs[k].get('edition')=='astra' and docs[k]['grid_km']==12 for k in ['process','stations','frontal','secondary'])
    p=docs['process'];samples={round(x['hour']):x for x in p['samples']}
    checks['complete_72_hours']=72 in samples
    field=np.load(args.process+'.npz')
    checks['external_start_then_actual_cold_air_exits_south']=float(field['h0_coldair'].max())<.15 and float(field['h54_coldair'].min())>.8
    movement={}
    for province in ['guangxi','guangdong']:
        a,b,c=[samples[h]['front'][province] for h in [12,24,36]]
        movement[province]={'early_deg':a-b,'later_deg':b-c,'acceleration_ratio':(b-c)/(a-b)}
    checks['both_provinces_move_and_accelerate']=all(r['early_deg']>.3 and r['acceleration_ratio']>1.5 for r in movement.values())
    details['front_movement']=movement
    for level in ['925','500','300']:
        wind=np.array([r['winds'][level] for r in p['samples']]);spread=np.ptp(wind,axis=0)
        checks['wind_'+level+'_both_components_evolve']=bool(spread[0]>.2 and spread[1]>2)
        details['wind_'+level+'_component_ranges_m_s']=spread.tolist()
    ns=max(x['longest_ns_km'] for x in p['samples'])
    checks['no_domain_height_squall_line_in_sample']=120<=ns<=500;details['max_ns_extent_km']=ns
    tracks=[*docs['stations'].get('line_tracks',[]),*docs['secondary'].get('line_tracks',[])]
    duration=max((r['duration_hours'] for r in tracks),default=0)
    checks['organized_band_tracks_more_than_single_cell_life']=duration>=2;details['longest_band_track_hours']=duration
    cities=docs['stations']['cities']
    checks['all_32_actual_public_stations_sampled']=len(cities)==32 and 'Exact 32' in docs['stations'].get('station_sampling','')
    # National stations need not coincide with the tiny regional maximum.
    # Require a measured 20+ mm station passage AND separately verify the
    # actual strong-core flux and typical core-hit passage-window amount.
    heavy={name:r for name,r in cities.items() if max(r['rain_events_mm'],default=0)>=20}
    checks['actual_station_heavy_passage_not_just_regional_peak']=bool(heavy);details['heavy_station_passages']=heavy
    peak5=max(r['audit']['point_rain5_peak_mm'] for r in docs['stations']['samples'])
    core_amount=docs['stations']['core_hit_six_hour_rain_quantiles_mm']
    checks['strong_cores_have_five_minute_bursts_and_20_to_40_mm_typical_windows']=peak5>=10 and len(core_amount)==4 and 20<=core_amount[1]<=40
    details['regional_five_minute_peak_and_core_window_quantiles']=[peak5,core_amount]
    checks['paired_gust_exceeds_sustained_at_heavy_station']=any(r['peak_gust_increment_m_s']>=2 for r in heavy.values())
    peaks=[max(r['audit']['gust_peak_m_s'] for r in docs[k]['samples']) for k in ['process','secondary']]
    checks['ordinary_sample_gusts_not_40_to_50_m_s']=all(10<v<40 for v in peaks);details['sample_gust_peaks_m_s']=peaks
    w=docs['wake'];by={r['hours_since_source_off']:r for r in w['samples']}
    ratio4=by[4]['convective_ice_mass']/by[0]['convective_ice_mass'];ratio8=by[8]['convective_ice_mass']/by[0]['convective_ice_mass']
    checks['cloud_decay_uses_native_number_not_inferred_checkpoint']=not w['inferred_number_for_old_checkpoint']
    checks['detached_old_cloud_family_clears_without_age_mask']=ratio4<.005 and ratio8<.0001 and by[4]['convective_ice_column_max']<.005
    details['remaining_old_cloud_family_fraction_4h_8h']=[ratio4,ratio8]
    frontal=docs['frontal'];count=max(r['front_convective_cells'] for r in frontal['samples'])
    checks['moving_front_can_really_trigger_convection']=frontal['controlled_entered_front'] and count>0
    details['controlled_front_convective_cells_peak']=count
    residual=max(abs(r['audit']['water_relative_residual']) for k in ['process','stations','frontal','secondary'] for r in docs[k]['samples'])
    checks['water_budget']=residual<2e-5;details['max_water_relative_residual']=residual
    result={'engine':VERSION,'source_sha256':digest,'all_passed':all(checks.values()),'checks':checks,'details':details,
            'scope':'Controlled/unit regressions are separate; these are Astra 12 km representative process gates, not 6 km or all-seed forecast accuracy'}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['all_passed']:raise SystemExit(1)


if __name__=='__main__':main()
