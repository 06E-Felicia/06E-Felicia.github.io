"""GitHub Actions / local CLI. Produces static, self-describing compressed frames."""
import argparse
import base64
import gzip
import hashlib
import importlib.metadata
import json
import math
import time
from pathlib import Path
import numpy as np
from scipy.ndimage import zoom
from .core import Model, VERSION, Z, settings, source_digest
from .terrain import grid


def pack(array):
    a=np.asarray(array,dtype=float)
    valid=np.isfinite(a)
    low=float(a[valid].min()) if valid.any() else 0
    high=float(a[valid].max()) if valid.any() else 0
    offset=(low+high)/2;scale=max((high-low)/65000,1e-7)
    values=np.full(a.shape,32767,dtype='<i2')
    values[valid]=np.rint((a[valid]-offset)/scale).astype('<i2')
    return {'shape':list(a.shape),'scale':scale,'offset':offset,'data':base64.b64encode(values.tobytes()).decode('ascii')}


def write_gzip(path, value):
    raw=json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    with path.open('wb') as dest:
        # No timestamp in gzip, so equal seeds/versions have equal frame bytes.
        with gzip.GzipFile(fileobj=dest,mode='wb',mtime=0,filename='',compresslevel=4) as output:output.write(raw)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def terrain_for(config, path):
    with np.load(path,allow_pickle=False) as data:
        if not np.allclose(data['bounds'],config['bounds']):raise ValueError('DEM bounds mismatch; regenerate terrain for these bounds')
        target=grid(config['bounds'],config['grid_km'])[0].shape
        h=data['height']
        if target!=h.shape:h=zoom(h,(target[0]/h.shape[0],target[1]/h.shape[1]),order=1)
        return h,{'source':str(data['source']),'native_zoom':int(data['zoom']),'source_grid_km':float(data['grid_km'])}


def run(config, terrain_path, output):
    cfg=settings(config);output=Path(output)
    if output.exists() and any(output.iterdir()):raise ValueError('Output directory must be empty; existing results are never overwritten')
    output.mkdir(parents=True,exist_ok=True)
    height,source=terrain_for(cfg,terrain_path);model=Model(cfg,height)
    # Bound deployment size BEFORE running. Only output frequency is reduced;
    # native grid, vertical fields and internal stability steps are retained.
    requested_interval=cfg['frame_minutes']
    max_frames=max(2,int(400*1024**2/(180*model.lon.size)))
    safe_interval=math.ceil(cfg['hours']*60/(max_frames-1)/30)*30
    cfg['frame_minutes']=max(requested_interval,safe_interval)
    start=time.monotonic();entries=[];size=0
    lon,lat=model.lon,model.lat
    manifest={'schema':2,'engine':VERSION,'status':'complete','simulation':True,
        'dependencies':{name:importlib.metadata.version(name) for name in ['numpy','scipy','Pillow']},
        'source_sha256':source_digest('run.py'),
        'config':cfg,'seed_streams':dict(zip(['initial_temperature','initial_moisture','time_evolution','synoptic','convective_cells'],model.seed_ids)),
        'grid':{'nx':lon.shape[1],'ny':lon.shape[0],'west':float(lon[0,0]),'south':float(lat[0,0]),
                'dlon':float(lon[0,1]-lon[0,0]),'dlat':float(lat[1,0]-lat[0,0]),'nominal_km':cfg['grid_km'],'z_agl_m':Z.tolist()},
        'terrain':source,'frames':entries,'requested_frame_minutes':requested_interval,
        'limitations':['简化分层热力/水物质输送和对流质量通量闭合；非完整三维非静力模式',
                      '暖雨与单一脱离凝结水储库；无完整冰相/冰雹微物理或可解析超级单体旋转',
                      '参考静力气压；无完整压力扰动方程，近地风并非严格的 10 m 诊断',
                      '无实况同化；南岭锋区是物理场初始条件，不预设风暴数量、路线和抵达时间',
                      '1 个网格不是有效预报精度；结果只用于机制实验']}
    times=np.arange(0,cfg['hours']*3600+1,cfg['frame_minutes']*60).tolist()
    if abs(times[-1]-cfg['hours']*3600)>.01:times.append(cfg['hours']*3600)
    for index, target in enumerate(times):
        while model.time<target-1e-6:model.step(target)
        if time.monotonic()-start>9000:raise TimeoutError('Compute budget exceeded (150 min); use coarser grid or shorter duration')
        fields=model.fields();audit=model.audit_state()
        if abs(audit['water_relative_residual'])>2e-3:raise FloatingPointError('Water budget residual exceeds 0.2%; refusing to publish')
        name=f'frame-{index:04d}.json.gz'
        digest=write_gzip(output/name,{'schema':2,'hour':model.time/3600,'fields':{k:pack(v) for k,v in fields.items()},'audit':audit})
        size+=(output/name).stat().st_size
        if size>450*1024**2:raise ValueError('Output budget exceeded (450 MiB); increase output interval')
        entries.append({'hour':model.time/3600,'file':name,'sha256':digest})
        print(json.dumps({'frame':index+1,'of':len(times),'hour':round(model.time/3600,2),'elapsed_s':round(time.monotonic()-start,1),'MiB':round(size/1024**2,2),'audit':audit}),flush=True)
    manifest['audit']=model.audit_state();manifest['elapsed_seconds']=round(time.monotonic()-start,3)
    manifest['bytes']=size
    (output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    return manifest


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',default='simulation/config.json');ap.add_argument('--terrain',default='assets/data/simulation-terrain.npz');ap.add_argument('--output',required=True)
    ap.add_argument('--seed',type=int);ap.add_argument('--hours',type=float);ap.add_argument('--grid-km',type=float);ap.add_argument('--frame-minutes',type=float)
    ap.add_argument('--compact-transport',action='store_true')
    args=ap.parse_args();cfg=json.loads(Path(args.config).read_text())
    for key in ['seed','hours','grid_km','frame_minutes']:
        value=getattr(args,key)
        if value is not None:cfg[key]=value
    if args.compact_transport:cfg['compact_transport']=True
    run(cfg,args.terrain,args.output)


if __name__=='__main__':main()
