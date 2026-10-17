"""Inspect saved strong sections AND weak links; never integrates weather.

Selecting only >=40 dBZ pixels for both profiles discards the weak links
whose contrast is being tested. Trace each active component, interpolate
missing trace rows, then sample the same finite front-relative strips in all
rows. No interpolation or contour is fed back into any meteorological field.
"""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.ndimage import label,binary_dilation,gaussian_filter1d
from scipy.signal import find_peaks


def main():
    ap=argparse.ArgumentParser();ap.add_argument('report');ap.add_argument('--output',required=True);args=ap.parse_args()
    report=json.loads(Path(args.report).read_text());data=np.load(args.report+'.npz');km=report['grid_km']
    hours=sorted(int(key.split('_')[0][1:]) for key in data.files if key.endswith('_rate'))
    result=[]
    for hour in hours:
        rain=data[f'h{hour}_rate'];z=data[f'h{hour}_radar'];activity=data[f'h{hour}_activity']
        cold=data[f'h{hour}_cold'];depth=data[f'h{hour}_depth'];content=cold*np.maximum(depth,30)
        strong=(z>=40)&(rain>=5)&(activity>.1);regions,count=label(binary_dilation(strong))
        objects=[]
        for ident in range(1,count+1):
            y,x=np.nonzero((regions==ident)&strong)
            if len(y)<8 or len(np.unique(y))<2:continue
            known=np.unique(y);rows=np.arange(y.min(),y.max()+1)
            front=np.interp(rows,known,[x[y==yy].max() for yy in known])
            intensity=[];pressure=[];volume=[];width=[]
            for yy,xx in zip(rows,front):
                leading=int(round(xx));lo=max(0,leading-round(24/km));hi=min(rain.shape[1],leading+max(1,round(12/km)))
                intensity.append(float(rain[yy,lo:hi].mean()))
                lo=max(0,leading-round(80/km));strip=slice(lo,leading+1)
                pressure.append(float(content[yy,strip].mean()))
                volume.append(float(depth[yy,strip].sum()*km**2/1000))
                width.append(float(((cold[yy,strip]>.5)&(depth[yy,strip]>100)).sum()*km))
            intensity=np.array(intensity);pressure=np.array(pressure)
            low=intensity<=np.percentile(intensity,33);high=intensity>=np.percentile(intensity,67)
            fit=np.polyval(np.polyfit(rows*km,front*km,1),rows*km);residual=front*km-fit
            peaks,_=find_peaks(gaussian_filter1d(residual,.65),prominence=km*.75,distance=max(2,round(30/km)))
            correlation=float(np.corrcoef(intensity,pressure)[0,1]) if min(intensity.std(),pressure.std())>1e-6 else None
            objects.append({'hour':hour,'strong_cells':len(y),'ns_extent_km':float(len(rows)*km),'embedded_bows':len(peaks),
                            'rain_cold_head_correlation_with_links':correlation,
                            'strong_to_weak_head_content_ratio':float(pressure[high].mean()/max(pressure[low].mean(),1e-9)),
                            'strong_to_weak_cold_volume_ratio':float(np.mean(np.array(volume)[high])/max(np.mean(np.array(volume)[low]),1e-9)),
                            'rain_mm_h':intensity.tolist(),'cold_head_K_m':pressure.tolist(),
                            'cold_volume_km3_per_row':volume,'cold_width_km':width})
        result.extend(sorted(objects,key=lambda obj:-obj['strong_cells'])[:3])
    output={'engine':report['engine'],'source_sha256':report['source_sha256'],'seed':report['config']['seed'],'grid_km':km,
            'definition':'All rows between active-component ends, including weak links; rain mean 24km behind to 12km ahead; cold content/volume mean/sum up to 80km behind. Trace interpolation is diagnosis only.',
            'samples':result}
    Path(args.output).write_text(json.dumps(output,indent=2));print(json.dumps([{k:v for k,v in obj.items() if not isinstance(v,list)} for obj in result if obj['embedded_bows']>=2],indent=2))


if __name__=='__main__':main()
