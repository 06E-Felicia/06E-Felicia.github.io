"""Verify saved final-source evidence; never runs weather integration."""
import argparse
import json
from pathlib import Path
from .core import VERSION, source_digest


def main():
    ap=argparse.ArgumentParser()
    for name in ['process','moist','probes','browser','output']:ap.add_argument('--'+name,required=True)
    args=ap.parse_args();docs={name:json.loads(Path(getattr(args,name)).read_text()) for name in ['process','moist','probes','browser']}
    p,m,o,b=[docs[k] for k in ['process','moist','probes','browser']]
    digest=source_digest('experiment.py','browser.py');manifest=b['manifest']
    checks={'same_final_source':all(r['engine']==VERSION and r['source_sha256']==digest for r in [p,m,o,manifest]),
            'astra_not_sol_processes':all(r['edition']=='astra' and r['grid_km']==12 for r in [p,m]),
            'whole_72_hours_complete':p['samples'][-1]['hour']==72,
            'high_moisture_stress_complete':m['samples'][-1]['hour']==12 and m['config']['moisture']>1.1,
            'no_geographic_cape_plateau':max(r['cape_on_hard_ceiling_fraction'] for d in [p,m] for r in d['samples'])<.005,
            'no_domain_wide_deep_activation_in_samples':max(r['active_fraction'] for d in [p,m] for r in d['samples'])<.15,
            'postfront_air_reaches_entire_domain':p['samples'][-1]['postfront_cells']>7000 and p['samples'][-1]['warm_cells']==0,
            # Any plume activation != redevelopment of strong convection.
            # Keep the stricter all-zero result visible below: one isolated
            # weak afternoon shower must NOT be erased to satisfy this test.
            'no_late_strong_echo_or_heavy_redevelopment':all(r['strong_echo_fraction']==0 and r['audit']['max_rain_mm_h']<5 for r in p['samples'] if r['hour']>=48),
            'strong_rain_not_removed':m['samples'][-1]['audit']['point_rain5_peak_mm']>=10,
            'water_budget':max(abs(r['audit']['water_relative_residual']) for d in [p,m] for r in d['samples'])<2e-5,
            'real_astra_browser':b['edition']=='astra' and manifest['product_version']=='2' and b['state']=='complete',
            **o['checks']}
    details={'late_postfront':[{'hour':r['hour'],'cape_p95':r['postfront_cape_p95'],'new_fraction':r['new_fraction'],
                                'strong_echo_fraction':r['strong_echo_fraction'],'active_coldpool_fraction':r['active_coldpool_fraction']}
                               for r in p['samples'] if r['hour'] in [48,54,60,66,72]],
             'max_sample_activation':max(r['active_fraction'] for d in [p,m] for r in d['samples']),
             'moist_case_point_five_minute_peak_mm':m['samples'][-1]['audit']['point_rain5_peak_mm']}
    details['strict_zero_initiation_after_48h']=all(r['new_fraction']==0 for r in p['samples'] if r['hour']>=48)
    details['late_weak_activations']=[{'hour':r['hour'],'fraction':r['new_fraction'],'max_rain_mm_h':r['audit']['max_rain_mm_h'],
                                     'strong_echo_fraction':r['strong_echo_fraction']} for r in p['samples'] if r['hour']>=48 and r['new_fraction']>0]
    result={'engine':VERSION,'source_sha256':digest,'all_passed':all(checks.values()),'checks':checks,'details':details,
            'scope':'Representative Astra 12 km samples and controlled closure probes; empirical area thresholds are not a universal weather definition; 6 km full process and all seeds are not certified'}
    Path(args.output).write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    if not result['all_passed']:raise SystemExit(1)


if __name__=='__main__':main()
