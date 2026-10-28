"""Audit fixed birth regions and moving cell IDs; never alter simulated fields."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
from pyproj import Transformer
from vacation_replay_data import load_manifest, read_frame


def rows(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s]


def analyze(root):
    root = Path(root)
    manifest = load_manifest(root)
    births = {r['id']: r for r in rows(root / 'births.ndjson')}
    deaths = {r['id']: r for r in rows(root / 'deaths.ndjson')}
    tracks = defaultdict(list)
    grid = manifest['grids']['coldPool']
    to_xy = Transformer.from_crs('EPSG:4326', manifest['projection'], always_xy=True)
    qx, qy = to_xy.transform(108.62, 21.96)
    qx -= grid['origin'][0]; qy -= grid['origin'][1]
    yy, xx = np.indices((grid['ny'], grid['nx']))
    qmask = ((xx + .5) * grid['dx'] - qx)**2 + ((yy + .5) * grid['dx'] - qy)**2 <= 25000**2
    qinzhou = []; peaks = {'dBZ': 0., 'coldDepthM': 0., 'coldDeltaK': 0.}
    trigger_fraction = []
    for entry in manifest['frames']:
        meta, fields = read_frame(root, manifest, entry)
        h, heat = fields['cold_depth'], fields['cold_heat']
        delta = np.divide(heat, h, out=np.zeros_like(h), where=h > 0)
        cold = (h >= 40) & (heat >= 20) & (delta >= .3)
        qinzhou.append({'t': entry['simTime'], 'coldAreaFraction25km': float(cold[qmask].mean()),
                        'maxDepthM25km': float(h[qmask].max()), 'maxDeltaK25km': float(delta[qmask].max())})
        valid_echo = fields['reflectivity_composite'][np.isfinite(fields['reflectivity_composite'])]
        if valid_echo.size: peaks['dBZ'] = max(peaks['dBZ'], float(valid_echo.max()))
        peaks['coldDepthM'] = max(peaks['coldDepthM'], float(h.max()))
        peaks['coldDeltaK'] = max(peaks['coldDeltaK'], float(delta.max()))
        trigger_fraction.append(float((fields['triggerLow'] > 0).mean()))
        for cell in meta['cells']:
            i, j = int(cell['x'] / grid['dx']), int(cell['y'] / grid['dx'])
            local_cold = bool(cold[j, i]) if 0 <= j < grid['ny'] and 0 <= i < grid['nx'] else False
            tracks[cell['id']].append({**cell, 't': entry['simTime'], 'underCold': local_cold})
    boxes = defaultdict(list)
    directions = {}
    decays = []
    for cid, track in tracks.items():
        birth = births[cid]
        distance = lambda p: float(np.hypot(p['x'] - birth['x'], p['y'] - birth['y']))
        mature = [p for p in track if p['a'] >= .1 and p.get('suppliedKgThisStep', 0) > 0]
        if mature and max(distance(p) for p in mature) >= 15000:
            boxes[(int(birth['x'] // 20000), int(birth['y'] // 20000))].append(cid)
            farthest = max(mature, key=distance)
            directions[cid] = np.array([farthest['x'] - birth['x'], farthest['y'] - birth['y']]) / distance(farthest)
        for p in track:
            if not p['underCold'] or distance(p) < 10000 or p['a'] < .1:
                continue
            later = next((q for q in track if p['t'] < q['t'] <= p['t'] + 1800 and q['a'] <= .5 * p['a']), None)
            death = deaths.get(cid, {})
            lost = p['t'] < death.get('t', 0) <= p['t'] + 1800 and death.get('reason') == 'thermal_or_updraft_support_lost'
            if later or lost:
                decays.append({'id': cid, 'coldTime': p['t'], 'distanceKm': distance(p) / 1000,
                               'activityBefore': p['a'], 'activityAfter': later['a'] if later else None,
                               'afterTime': later['t'] if later else death['t'], 'supportLostDeath': lost})
                break
    repeated = []
    for (bx, by), ids in boxes.items():
        ordered = sorted(ids, key=lambda cid: births[cid]['t'])
        bins = sorted({int(births[cid]['t'] // 1800) for cid in ids})
        longest = run = 1
        for a, b in zip(bins, bins[1:]):
            run = run + 1 if b == a + 1 else 1
            longest = max(longest, run)
        span = births[ordered[-1]]['t'] - births[ordered[0]]['t']
        direction = np.mean([directions[cid] for cid in ids], axis=0)
        concentration = float(np.linalg.norm(direction))
        if len(ids) >= 3 and span >= 3600 and longest >= 3 and concentration >= .85:
            relief = [births[cid]['triggerEvidence'].get('focusedLift', {}).get('terrainRiseM', 0) for cid in ids]
            repeated.append({'boxM': [bx*20000, by*20000, (bx+1)*20000, (by+1)*20000],
                             'ids': ordered, 'mobileMatureCells': len(ids), 'birthSpanHours': span/3600,
                             'consecutiveHalfHourBins': longest, 'firstBirth': births[ordered[0]]['t'],
                             'terrainRiseMedianM': float(np.median(relief)),
                             'travelDirectionConcentration': concentration,
                             'travelHeadingXYDegrees': float(np.degrees(np.arctan2(direction[1], direction[0]))),
                             'environmentBirths': sum(births[cid]['source'] == 'environment' for cid in ids),
                             'coldFrontBirths': sum(births[cid]['source'] != 'environment' for cid in ids)})
    repeated.sort(key=lambda r: (r['consecutiveHalfHourBins'], r['mobileMatureCells']), reverse=True)
    qbirths = [b for b in births.values() if (b['x']-qx)**2+(b['y']-qy)**2 <= 25000**2]
    cold_births = [b['id'] for b in births.values() if b['layer'] == 0 and b['triggerEvidence']['surfaceAccess']['cold']]
    result = {'model': manifest['model'], 'config': manifest['config'],
              'criteria': 'Fixed 20 km diagnostic box; at least 3 supplied active IDs moving >=15 km; births span >=1 h with >=3 consecutive 30 min bins; displacement unit-vector concentration >=0.85. Box never used by the model.',
              'decayCriteria': 'At >=10 km from birth under resolved cold air (h>=40 m, Q>=20 K m, Q/h>=0.3 K), activity halves within 30 min or cell dies from lost support.',
              'limitations': 'Sampled cold/decay association is not causal attribution. Paired cold-supply unit test isolates causality. Finite pulses can also decay naturally. A training sequence need not have a stationary radar centroid.',
              'frames': len(manifest['frames']), 'births': len(births), 'repeatedSources': repeated,
              'downstreamColdDecayCount': len(decays), 'downstreamColdDecayExamples': decays[:30],
              'surfaceBirthsInsideCold': cold_births, 'peaks': peaks,
              'maxTriggerAreaFraction': max(trigger_fraction),
              'qinzhou': {'radiusKm': 25, 'births': len(qbirths), 'maxColdAreaFraction': max(q['coldAreaFraction25km'] for q in qinzhou), 'timeline': qinzhou}}
    (root / 'birth-cycle-analysis.json').write_text(json.dumps(result, indent=2))
    print(root.name, json.dumps({'sources': len(repeated), 'coldDecays': len(decays), 'birthsInCold': len(cold_births), 'peaks': peaks, 'qinzhouCold': result['qinzhou']['maxColdAreaFraction']}), flush=True)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('directory'); args = parser.parse_args()
    root = Path(args.directory)
    for path in ([root] if (root / 'manifest.json').exists() else sorted(p.parent for p in root.glob('*/report.json'))):
        analyze(path)
