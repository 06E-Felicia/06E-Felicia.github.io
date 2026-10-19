"""Offline morphology of ACTUAL saved fields; never used to shape weather."""
import numpy as np
from scipy.ndimage import label,gaussian_filter1d
from scipy.signal import find_peaks,peak_widths


def morphology(echo,activity,air,cold,depth,km,*,anvil_column=None,stratiform_rate=None):
    active=(echo>=35)&(activity>.05)&(air<.1)
    components,count=label(active,structure=np.ones((3,3)))
    sizes=np.bincount(components.ravel());sizes[0]=0
    principal=components==int(sizes.argmax()) if count else np.zeros(active.shape,dtype=bool)
    y,x=np.nonzero(principal)
    cold_mask=(cold>.5)&(depth>100)
    pools,_=label(cold_mask,structure=np.ones((3,3)))
    overlap=np.bincount(pools[principal].ravel(),minlength=int(pools.max())+1);overlap[0]=0
    pool=pools==int(overlap.argmax()) if overlap.any() else np.zeros_like(cold_mask)
    result={'strong35_cells':int(active.sum()),'principal35_cells':len(y),
        'all_cold_area_km2':int(cold_mask.sum())*km**2,
        'matched_cold_area_km2':int(pool.sum())*km**2,
        'matched_cold_volume_km3':float(depth[pool].sum()*km**2/1000),
        'same_pool_southern_fragments':0,'same_pool_southern_fragment_cells':0}
    if len(y)<4 or len(np.unique(y))<4:return result
    # Count, never erase or connect, nearby southern pieces which REALLY
    # share the main system's cold air. Separate storms/pools are not labelled
    # a broken link merely because they lie to the south of the largest echo.
    for ident in range(1,count+1):
        piece=components==ident
        if np.any(piece&principal) or np.count_nonzero(piece)<4:continue
        py,_=np.nonzero(piece)
        if (np.median(py)<np.min(y) and max(0,np.min(y)-np.max(py)-1)*km<=100
                and np.count_nonzero(piece&pool)>=.5*np.count_nonzero(piece)):
            result['same_pool_southern_fragments']+=1
            result['same_pool_southern_fragment_cells']+=int(np.count_nonzero(piece))
    rows=np.unique(y);north=rows*km
    front=np.array([x[y==yy].max()*km for yy in rows])
    fit=np.polyfit(north,front,1);departure=front-np.polyval(fit,north)
    broad=gaussian_filter1d(departure,max(.5,42/km))
    fine=gaussian_filter1d(departure,max(.4,6/km))
    peaks,_=find_peaks(fine,prominence=max(8,km*.75),distance=max(2,round(24/km)))
    widths=peak_widths(fine,peaks,rel_height=.5)[0]*km if len(peaks) else np.array([])
    rear=[];near_rear=np.zeros_like(cold_mask);weak_rear=np.zeros_like(cold_mask)
    for row,leading in zip(rows,front):
        zone=(np.arange(pool.shape[1])*km<=leading)&(np.arange(pool.shape[1])*km>=leading-150)
        near_rear[row]=pool[row]&zone
        weak_rear[row]=zone&(echo[row]>=10)&(echo[row]<35)
        xx=np.nonzero(near_rear[row])[0]
        if len(xx):rear.append(leading-xx.min()*km)
    result.update({'ns_span_km':float((np.ptp(rows)+1)*km),
        'tilt_from_north_deg':float(np.degrees(np.arctan(fit[0]))),
        'front_rms_departure_km':float(np.sqrt(np.mean(departure**2))),
        'broad_front_rms_km':float(np.sqrt(np.mean(broad**2))),
        'bow_10_90_excursion_km':float(np.percentile(departure,90)-np.percentile(departure,10)),
        'embedded_bow_half_prominence_widths_km':widths.tolist(),
        'rear_cold_width_median_km':float(np.median(rear)) if rear else 0,
        'rear150_cold_area_km2':int(near_rear.sum())*km**2,
        'rear150_weak_echo_area_km2':int(weak_rear.sum())*km**2})
    midpoint=(rows.min()+rows.max())/2
    for name,selected in [('south',rows<=midpoint),('north',rows>midpoint)]:
        result[f'{name}_half_front_rms_km']=float(np.sqrt(np.mean(departure[selected]**2)))
        sector=principal&(np.indices(echo.shape)[0]<=midpoint if name=='south'
                          else np.indices(echo.shape)[0]>midpoint)
        result[f'{name}_half_50dbz_area_km2']=int(np.count_nonzero(sector&(echo>=50)))*km**2
        rear_zone=np.zeros_like(cold_mask)
        for row,leading in zip(rows[selected],front[selected]):
            rear_zone[row]=(np.arange(pool.shape[1])*km<=leading)&(np.arange(pool.shape[1])*km>=leading-150)
        result[f'{name}_rear150_weak_echo_area_km2']=int(np.count_nonzero(weak_rear&rear_zone))*km**2
        result[f'{name}_rear150_cold_area_km2']=int(np.count_nonzero(near_rear&rear_zone))*km**2
        if anvil_column is not None:
            water=np.where(rear_zone,anvil_column,0)
            result[f'{name}_rear150_anvil_mass_kg']=float(water.sum()*km**2*1e6)
            distances=np.zeros_like(water)
            for row,leading in zip(rows[selected],front[selected]):
                distances[row]=np.maximum(leading-np.arange(pool.shape[1])*km,0)
            result[f'{name}_rear150_anvil_mean_distance_km']=float(np.sum(water*distances)/max(water.sum(),1e-12))
        if stratiform_rate is not None:
            result[f'{name}_rear150_stratiform_area_km2']=int(np.count_nonzero(rear_zone&(stratiform_rate>.2)))*km**2
        # A flatter global x(y) fit can hide an east--west southern tail or
        # merely discard its detached component. Measure the actual southern
        # band's spatial axis, including active pieces in the SAME real pool.
        cohort=active&(pool|principal)
        cohort&=(np.indices(echo.shape)[0]<=midpoint if name=='south'
                 else np.indices(echo.shape)[0]>midpoint)
        sy,sx=np.nonzero(cohort)
        if len(sy)>=4:
            sx=(sx-sx.mean())*km;sy=(sy-sy.mean())*km
            xx=float(np.mean(sx*sx));yy=float(np.mean(sy*sy));xy=float(np.mean(sx*sy))
            angle=.5*np.degrees(np.arctan2(2*xy,xx-yy))
            tilt=(90-angle+90)%180-90
            result[f'{name}_band_axis_from_north_deg']=float(tilt)
            result[f'{name}_band_axis_anisotropy']=float(np.hypot(xx-yy,2*xy)/max(xx+yy,1e-12))
            result[f'{name}_band_cells']=int(len(sy))
            result[f'{name}_band_ns_span_km']=float(np.ptp(sy)+km)
            result[f'{name}_band_ew_span_km']=float(np.ptp(sx)+km)
    return result


def saved_morphology(path,hours=(6,7,8,9)):
    with np.load(str(path)+'.npz',allow_pickle=False) as a:
        # Shared continuity runner stores the exact hourly cold/echo fields.
        lon=a['lon'];km=round(float(np.diff(a['lat'][:,0]).mean())*111.195,8)
        return [{'hour':h,**morphology(*[a[f'h{h}_{key}'] for key in
                ['radar','activity','air','cold','depth']],km,
                **{key:a[f'h{h}_{key}'] for key in ['anvil_column','stratiform_rate'] if f'h{h}_{key}' in a})} for h in hours]
