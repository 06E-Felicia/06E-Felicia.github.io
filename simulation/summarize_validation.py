"""Compact, auditable process reports. Keep straight/curved metrics separate."""
import argparse
import json
from pathlib import Path


def summarize(path):
    raw=json.loads(Path(path).read_text());rows=raw['samples']
    def peak(key):return max((x.get(key,0) or 0) for x in rows)
    by_hour={x['hour']:x for x in rows}
    return {'report':Path(path).name,'engine':raw['engine'],'source_sha256':raw['source_sha256'],
        'config':raw['config'],'front_regime':raw.get('front_regime'),
        'completed_hours':rows[-1]['hour'],'elapsed_seconds':raw.get('elapsed_seconds'),
        'sample_minutes':raw['sample_minutes'],
        'straight_line_hours':raw['longest_tracked_line_hours'],
        'curved_band_hours':raw.get('longest_curved_band_hours'),
        'max_rain_mm_h':peak('rain_max_mm_h'),'max_hourly_rain_mm':peak('hourly_rain_max_mm'),
        'max_total_rain_mm':peak('total_rain_max_mm'),'max_echo_dbz':peak('echo_max_dbz'),
        'max_gust_ms':peak('gust_max_ms'),'max_mean_surface_wind_ms':peak('surface_wind_max_ms'),
        'max_water_relative_residual':max(abs(x['budget']['water_relative_residual']) for x in rows),
        'max_cfl':max(x['budget']['max_cfl'] for x in rows),
        'max_coldpool_cfl':max(x['budget']['coldpool_max_cfl'] for x in rows),
        'max_front_multicrossing_fraction':peak('front_multi_crossing_fraction'),
        'max_wake_initiation_fraction':peak('cold_interior_new_activity_fraction'),
        'frontal_latitudes':{str(h):by_hour[h].get('front_regional_latitude') for h in [0,12,24,36,48,60,72] if h in by_hour},
        'limitations':['格点平均降水不等于站点/亚格点核区雨量；阵风为参数化诊断',
                       '直线 PCA 与弯曲带状指标不可混为同一判据或业务飑线分类器',
                       '数值稳定不等于所有气象形态及现实预报技能达标']}


def main():
    p=argparse.ArgumentParser();p.add_argument('reports',nargs='+');p.add_argument('--output',required=True)
    a=p.parse_args();summaries=[summarize(path) for path in a.reports]
    Path(a.output).write_text(json.dumps({'runs':summaries},ensure_ascii=False,indent=2))
    for s in summaries:
        print(json.dumps({k:s[k] for k in ['report','completed_hours','straight_line_hours','curved_band_hours','max_rain_mm_h','max_hourly_rain_mm','max_total_rain_mm','max_gust_ms','max_water_relative_residual']},ensure_ascii=False))


if __name__=='__main__':main()
