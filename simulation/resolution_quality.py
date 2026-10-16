"""QA only: resolution-matched comparisons, never a replacement weather run.

Thresholds are engineering acceptance tolerances, not forecast skill scores.
Compare linear reflectivity and water on the SAME area-averaged grid. Do not
compare a fine-grid maximum directly to a coarse-grid mean.
"""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from scipy.ndimage import binary_dilation, label
from .core import Model, VERSION, source_digest
from .experiment import random_environment
from .run import terrain_for
from .terrain import grid
from .validate import morphology, LineTracker, band_geometry


def run(args):
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    cfg=random_environment(args.seed,{'hours':args.hours,'grid_km':args.grid_km,'frame_minutes':60},grid_limit=max(12,args.grid_km))
    height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz')
    model=Model(cfg,height,grid_limit=max(12,args.grid_km))
    tracker=LineTracker(args.grid_km);rows=[];started=time.monotonic()
    for hour in range(args.hours+1):
        while model.time<hour*3600-1e-6:model.step(hour*3600)
        row,_,masks=morphology(model,with_curved_masks=True)
        tracker.update(hour,row['curved_band_candidates'],masks);rows.append(row)
        fields=model.fields(include_mixed=False)
        keys=['composite','rainrate','rain_total','rain_hour','coldpool','coldpool_depth','coldair','mucape','temperature','gust','organization']
        np.savez_compressed(output/('%d.npz'%hour),lon=model.lon,lat=model.lat,activity=model.activity,
                            **{k:fields[k] for k in keys})
        if hour%6==0:print(json.dumps({'quality_hour':hour,'grid_km':args.grid_km,'elapsed_s':round(time.monotonic()-started,1),'bands':len(row['curved_band_candidates'])}),flush=True)
    report={'engine':VERSION,'source_sha256':source_digest(),'config':cfg,'samples':rows,
            'elapsed_seconds':time.monotonic()-started,'curved_band_tracks':tracker.tracks,
            'longest_curved_band_hours':max((x['duration_hours'] for x in tracker.tracks),default=0)}
    (output/'process.json').write_text(json.dumps(report,indent=2))


def overlap(source,target):
    def edges(a):return np.r_[a[0]-(a[1]-a[0])/2,(a[:-1]+a[1:])/2,a[-1]+(a[-1]-a[-2])/2]
    s=edges(source);t=edges(target)
    weights=np.maximum(0,np.minimum(t[1:,None],s[None,1:])-np.maximum(t[:-1,None],s[None,:-1]))
    coverage=weights.sum(axis=1)/np.diff(t)
    return weights/np.maximum(weights.sum(axis=1,keepdims=True),1e-20),coverage


def regrid(raw,lon,lat):
    x,cx=overlap(raw['lon'][0],lon[0]);y,cy=overlap(raw['lat'][:,0],lat[:,0])
    valid=(cy[:,None]>.999)&(cx[None,:]>.999)
    out={}
    aliases={'rainrate':'rainrate','rain_total':'rain_total','rain_hour':'rain_hour',
             'coldpool':'cold','coldpool_depth':'cold_depth','coldair':'air','activity':'activity'}
    for key,old in aliases.items():out[key]=y@raw[key if key in raw else old]@x.T
    linear=10**(np.clip(raw['composite'],-30,80)/10)
    out['composite']=10*np.log10(np.maximum(y@linear@x.T,1e-9))
    return out,valid


def line_length(f,km,valid):
    strong=(f['composite']>=35)&(f['rainrate']>=5)&(f['activity']>.1)&valid
    objects,count=label(binary_dilation(strong))
    longest=0.
    for ident in range(1,count+1):
        core=(objects==ident)&strong;area=core.sum()*km*km
        if area<1152 or core.sum()<3:continue
        length=band_geometry(objects==ident,km)
        if length>=120 and length*length/area>=4:longest=max(longest,length)
    return longest


def front_positions(f,lat):
    positions=[]
    for x in range(f.shape[1]):
        crossing=np.flatnonzero(np.diff(f[:,x]>=.5))
        positions.append(np.interp(.5,f[crossing[0]:crossing[0]+2,x],lat[crossing[0]:crossing[0]+2,x]) if len(crossing)==1 else np.nan)
    return np.asarray(positions)


def compare(args):
    directory=Path(args.candidate);process=json.loads((directory/'process.json').read_text())
    km=process['config']['grid_km'];lon,lat=grid(process['config']['bounds'],km)
    references=sorted(Path(args.reference).parent.glob(Path(args.reference).name+'.[0-9]*.npz'),key=lambda p:int(p.name.split('.')[-2]))
    rows=[];candidate={}
    for path in directory.glob('[0-9]*.npz'):
        with np.load(path) as source:candidate[int(path.stem)]=regrid(source,lon,lat)
    for path in references:
        hour=int(path.name.split('.')[-2])
        if hour not in candidate:continue
        with np.load(path) as source:reference,ref_valid=regrid(source,lon,lat)
        test,test_valid=candidate[hour];valid=ref_valid&test_valid
        ref_line=line_length(reference,km,valid)
        nearby=[(h,f) for h,(f,_) in candidate.items() if abs(h-hour)<=2]
        best_line=max((line_length(f,km,valid) for _,f in nearby),default=0)
        front_a=front_positions(reference['coldair'],lat);front_b=front_positions(test['coldair'],lat)
        finite=np.isfinite(front_a)&np.isfinite(front_b)
        row={'hour':hour,'reference_line_km':round(ref_line,1),'candidate_best_line_within_2h_km':round(best_line,1),
             'front_median_error_km':round(float(np.median(np.abs(front_a[finite]-front_b[finite]))*111.195),2) if finite.any() else None}
        for key in ['rain_total','rain_hour']:
            for name,stat in [('mean',np.mean),('p99',lambda a:np.quantile(a,.99))]:
                a=float(stat(reference[key][valid]));b=float(stat(test[key][valid]))
                row[key+'_'+name]={'astra':a,'sol':b,'ratio':b/a if a>1e-6 else None}
        cold_a=float(((reference['coldpool']>1)&valid).sum()*km*km)
        cold_b=float(((test['coldpool']>1)&valid).sum()*km*km)
        row['coldpool_area_km2']={'astra':cold_a,'sol':cold_b,'ratio':cold_b/cold_a if cold_a else None}
        rows.append(row)
    if not rows:raise ValueError('No matching snapshots')
    final=rows[-1];checks={}
    for name in ['rain_total_mean','rain_total_p99']:
        ratio=final[name]['ratio'];checks[name]=ratio is not None and .7<=ratio<=1.3
    lines=[x for x in rows if x['reference_line_km']>=120]
    checks['line_retention']=bool(lines) and all(x['candidate_best_line_within_2h_km']>=.7*x['reference_line_km'] for x in lines)
    fronts=[x['front_median_error_km'] for x in rows if x['front_median_error_km'] is not None]
    checks['front_position']=bool(fronts) and max(fronts)<=75
    report={'comparison_grid_km':km,'reference':args.reference,'candidate':str(directory),
            'checks':checks,'passed':all(checks.values()),'samples':rows,
            'tolerances':{'precipitation_ratio':[.7,1.3],'line_length_retained_fraction':.7,'line_timing_window_hours':2,'front_error_km':75},
            'limitations':['同种子跨网格的随机空间场不逐格相同；只比较组织形态及区域统计，不要求逐格相同',
                           '反射率在线性 Z 域面积平均；雨量在同一网格比较；阈值为预先固定的工程容差，非业务评估标准',
                           '参考场每6小时保存，不能据此证明完整连续寿命；仍须联合过程追踪和实际雷达图判断']}
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'passed':report['passed'],'checks':checks,'final':final},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('run');p.add_argument('--seed',type=int,required=True);p.add_argument('--grid-km',type=float,required=True)
    p.add_argument('--hours',type=int,default=72);p.add_argument('--output',required=True);p.set_defaults(action=run)
    p=sub.add_parser('compare');p.add_argument('--reference',required=True);p.add_argument('--candidate',required=True);p.add_argument('--output',required=True);p.set_defaults(action=compare)
    args=parser.parse_args();args.action(args)


if __name__=='__main__':main()
