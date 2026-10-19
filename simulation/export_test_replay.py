"""Package actual completed diagnostic NPZ frames, never synthesize weather.

Only the developer/export step needs scientific packages. The launcher and
viewer use stdlib/static assets and do not depend on /tmp after export.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import numpy as np
from .core import VERSION,source_digest
from .test_replay import ARCHIVE

FIELDS={'composite':'radar','mucape':'cape','rainrate':'rain','rain_total':'total'}


def export_reports(reports,output=ARCHIVE):
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory must be empty; existing test archives are never overwritten')
    prepared=[];seeds=set()
    for report in reports:
        path=Path(report);raw=path.read_bytes();d=json.loads(raw)
        if d.get('edition')!='astra' or d.get('reference_4_9_memory') or d.get('candidate_override'):
            raise ValueError('Only actual Astra runs, not comparison overrides, may be exported')
        if d['engine']!=VERSION or d['source_sha256']!=source_digest('experiment.py','browser.py'):
            raise ValueError('Report does not match the current tested physical source')
        if abs(d['samples'][-1]['hour']-d['config']['hours'])>1e-6:
            raise ValueError('Incomplete test process')
        seed=d['config']['seed']
        if seed in seeds:raise ValueError('Duplicate test seed')
        seeds.add(seed);npz=Path(str(path)+'.npz')
        with np.load(npz,allow_pickle=False) as arrays:
            lon,lat=arrays['lon'],arrays['lat'];frames=[]
            hours=sorted(int(k.split('_')[0][1:]) for k in arrays.files if k.endswith('_radar'))
            if not hours or hours[0]!=0 or hours[-1]!=d['config']['hours']:
                raise ValueError('Saved snapshots do not include both process endpoints')
            for hour in hours:
                fields={}
                for name,key in FIELDS.items():
                    a=np.asarray(arrays[f'h{hour}_{key}'],dtype='<f8')
                    if a.shape!=lon.shape:raise ValueError('Snapshot grid mismatch')
                    fields[name]=base64.b64encode(a.tobytes()).decode('ascii')
                frames.append({'hour':hour,'fields':fields})
            payload={'schema':'stormsim-astra-test-v1','status':'complete','edition':'astra',
                'engine':VERSION,'source_sha256':d['source_sha256'],'config':d['config'],
                'grid':{'nx':lon.shape[1],'ny':lon.shape[0],'west':float(lon[0,0]),'south':float(lat[0,0]),
                    'dlon':float(lon[0,1]-lon[0,0]),'dlat':float(lat[1,0]-lat[0,0])},
                'encoding':'float64-le-base64','snapshot_interval_hours':1,
                'source_report_sha256':hashlib.sha256(raw).hexdigest(),
                'source_npz_sha256':hashlib.sha256(npz.read_bytes()).hexdigest(),
                'audit':d['samples'][-1]['audit'],'frames':frames}
        # Prefer a mature saved time, not an empty initial radar. These are
        # unmodified recorded hours; no intermediate radar is interpolated.
        mature=[s for s in d['samples'] if s['hour'] in hours and 4<=s['hour']<=8]
        best=max(mature or d['samples'],key=lambda s:(s.get('coastal_active40_cells',0),
                    s['echo40']['ns_span_km'],s['echo40']['largest_cells']))
        default_hour=best['hour'] if best['hour'] in hours else hours[0]
        prepared.append((payload,default_hour))
    if not prepared:raise ValueError('At least one report is required')
    output.mkdir(parents=True,exist_ok=True);entries=[]
    for payload,default_hour in prepared:
        seed=payload['config']['seed'];name=f'astra-{seed}.json'
        data=json.dumps(payload,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
        (output/name).write_bytes(data)
        entries.append({'file':name,'sha256':hashlib.sha256(data).hexdigest(),'seed':seed,'engine':VERSION,
                        'default_hour':default_hour,'hours':payload['config']['hours'],
                        'grid_km':payload['config']['grid_km'],'frames':len(payload['frames'])})
    index={'schema':'stormsim-astra-test-v1','status':'complete','cases':entries}
    (output/'index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf8')
    return index


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports',nargs='+');parser.add_argument('--output',default=str(ARCHIVE))
    args=parser.parse_args();index=export_reports(args.reports,args.output)
    print(json.dumps(index,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
