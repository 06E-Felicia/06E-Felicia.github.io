"""Process diagnostics, not a claim of forecast skill or a squall-line classifier.

Measure connected strong-rain echoes AND geometry rather than passing a run
merely because it did not crash. The thresholds are explicit experimental QA.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from scipy.ndimage import binary_dilation, gaussian_filter, maximum_filter, label, shift
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from .core import Model, VERSION, settings, DZ, rain_reflectivity, source_digest
from .run import terrain_for
from .experiment import random_environment


def band_geometry(mask,km):
    """Curved-band diagnostic independent of the existing PCA criterion."""
    yy,xx=np.nonzero(mask);top,bottom=yy.min(),yy.max()+1;left,right=xx.min(),xx.max()+1
    local=mask[top:bottom,left:right];y,x=np.nonzero(local);n=len(x)
    ids=np.full(local.shape,-1,dtype=int);ids[y,x]=np.arange(n)
    rows=[];cols=[];weights=[]
    for dy,dx in [(0,1),(1,0),(1,1),(1,-1)]:
        ny,nx=y+dy,x+dx;valid=(ny>=0)&(ny<local.shape[0])&(nx>=0)&(nx<local.shape[1])
        source=np.flatnonzero(valid);target=ids[ny[valid],nx[valid]];keep=target>=0
        source=source[keep];target=target[keep]
        rows.extend([source,target]);cols.extend([target,source]);weights.extend([np.full(len(source),km*np.hypot(dx,dy))]*2)
    graph=coo_matrix((np.concatenate(weights),(np.concatenate(rows),np.concatenate(cols))),shape=(n,n)).tocsr()
    start=int(np.argmax((x-x.mean())**2+(y-y.mean())**2))
    first=dijkstra(graph,indices=start);end=int(np.argmax(np.where(np.isfinite(first),first,-1)))
    distance=dijkstra(graph,indices=end);length=float(np.max(distance[np.isfinite(distance)]))+km
    return length


def morphology(model,with_masks=False,with_curved_masks=False):
    echo=np.max(rain_reflectivity(model.rain,model.plume_rain,model.rain_area,model.mass/DZ[:,None,None],model.anvil,model.graupel,model.graupel_area),axis=0)
    gust=model.surface_gust()
    strong=(echo>=35)&(model.last_rate>=5)&(model.activity>.1)
    # One-cell gaps allowed, but PCA and area use only original strong cells.
    objects,count=label(binary_dilation(strong,iterations=1))
    candidates=[];masks=[];cell_u,cell_v=model.steering(*model.winds())
    for ident in range(1,count+1):
        y,x=np.nonzero((objects==ident)&strong)
        if len(x)<8:continue
        coords=np.column_stack((x,y))*model.cfg['grid_km']
        centered=coords-coords.mean(axis=0)
        eig,axes=np.linalg.eigh(centered.T@centered/len(x))
        projected=centered@axes
        length=float(np.ptp(projected[:,1])+model.cfg['grid_km'])
        width=float(np.ptp(projected[:,0])+model.cfg['grid_km'])
        core=(objects==ident)&strong
        geodesic=band_geometry((objects==ident),model.cfg['grid_km'])
        area=len(x)*model.cfg['grid_km']**2
        candidates.append({'cells':len(x),'length_km':round(length,1),
                           'ns_extent_km':round(float(np.ptp(y)*model.cfg['grid_km']+model.cfg['grid_km']),1),
                           'aspect':round(length/max(width,1),2),
                           'geodesic_length_km':round(geodesic,1),
                           'band_thinness':round(geodesic**2/max(area,1),2),
                           'coldpool_max_K':round(float(model.cold[y,x].max()),2),
                           'coldpool_depth_mean_m':round(float(model.cold_depth[y,x].mean()),1),
                           'coldair_mean':round(float(model.air[y,x].mean()),3),
                           'rain_mean_mm_h':round(float(model.last_rate[y,x].mean()),2),
                           'rain_peak_mm_h':round(float(model.last_rate[y,x].max()),2),
                           'gust_peak_ms':round(float(gust[y,x].max()),2),
                           'centroid_km':coords.mean(axis=0).round(2).tolist(),
                           'orientation_deg':round(float(np.degrees(np.arctan2(axes[1,1],axes[0,1]))%180),1),
                           'motion_ms':[float(cell_u[y,x].mean()),float(cell_v[y,x].mean())]})
        masks.append((objects==ident)&strong)
    # A front can leave the domain; report coverage separately from continuity.
    crossings=np.sum(np.diff((model.air>=.5).astype('int8'),axis=0)!=0,axis=0)
    represented=crossings>0
    yy,xx=np.nonzero(np.diff((model.air>=.5).astype('int8'),axis=0)!=0)
    lower=model.air[yy,xx];upper=model.air[yy+1,xx]
    latitudes=model.lat[yy,xx]+(model.lat[yy+1,xx]-model.lat[yy,xx])*(.5-lower)/(upper-lower)
    near=(model.air>.15)&(model.air<.85)
    warm=model.air<.1
    wake=warm&(model.total>2)&(model.activity<.1)&(model.cold>.5)
    head=maximum_filter(model.cold_depth,size=3,mode='nearest')
    donor_depth=model.donor_field(model.cold_depth)
    interior=warm&(model.cold>1)&(model.cold_depth>250)&(donor_depth>.5*np.maximum(head,1))
    raw_energy=np.minimum(model.mu['cape'],model.cape_ceiling)
    ice_column=np.sum(model.anvil*model.mass,axis=0)
    strat_column=np.sum(model.stratiform_rain*model.mass,axis=0)
    strat_echo=np.max(rain_reflectivity(model.stratiform_rain,np.zeros_like(model.rain),np.zeros_like(model.rain),model.mass/DZ[:,None,None],model.anvil),axis=0)
    rear=warm&(model.cold>.5)&(model.cold_depth>100)&(model.activity<.1)
    causal_rear=rear&(strat_echo>=10)&(strat_echo<40)&((ice_column+strat_column)>.02)
    qualified=[i for i,x in enumerate(candidates) if x['length_km']>=100 and x['aspect']>=3 and x['coldpool_max_K']>=.5]
    curved=[i for i,x in enumerate(candidates) if x['geodesic_length_km']>=120 and x['band_thinness']>=4 and x['coldpool_max_K']>=.5]
    combined=sorted(set(qualified+curved))
    regional_front={}
    for name,west,east in [('guangxi',106,111),('guangdong',111,116.5)]:
        region=(model.lon[yy,xx]>=west)&(model.lon[yy,xx]<east)
        regional_front[name]=round(float(np.median(latitudes[region])),3) if region.any() else None
    row={'hour':round(model.time/3600,3),
            'strong_cells':int(strong.sum()),'echo_max_dbz':round(float(echo.max()),2),
            'front_coverage':round(float(represented.mean()),3),
            'front_median_latitude':round(float(np.median(latitudes)),3) if len(latitudes) else None,
            'front_regional_latitude':regional_front,
            'front_latitude_5_95':np.percentile(latitudes,[5,95]).round(3).tolist() if len(latitudes) else None,
            'warm_sector_fraction':round(float(warm.mean()),4),
            'front_multi_crossing_fraction':round(float(np.mean(crossings[represented]>1)),3) if represented.any() else 0.,
            'front_rain_mean_mm_h':round(float(model.last_rate[near].mean()),3) if near.any() else 0.,
            'front_active_fraction':round(float(np.mean(model.activity[near]>.1)),4) if near.any() else 0.,
            'front_convective_rain_fraction':round(float(np.sum(model.plume_rain[:,near]*model.mass[:,near])/max(1e-12,np.sum(model.rain[:,near]*model.mass[:,near]))),4) if near.any() else 0.,
            'warm_echo_max_dbz':round(float(echo[warm].max()),2) if warm.any() else None,
            'warm_rain_max_mm_h':round(float(model.last_rate[warm].max()),2) if warm.any() else None,
            'coldpool_max_K':round(float(model.cold.max()),3),
            'coldpool_depth_max_m':round(float(model.cold_depth.max()),1),
            'coldpool_area_km2':round(float(np.sum((model.cold>1)&(model.cold_depth>100))*model.cfg['grid_km']**2),1),
            'coldpool_speed_max_ms':round(float(np.sqrt(2*9.80665*model.cold_content/295).max()),2),
            'cell_motion_mean_ms':[round(float(cell_u[model.activity>.1].mean()),2),round(float(cell_v[model.activity>.1].mean()),2)] if np.any(model.activity>.1) else None,
            'upper_wind_mean_ms':round(float(np.mean(np.hypot(*[a[11] for a in model.winds()]))),2),
            'echo_texture_dbz':round(float(np.sqrt(np.mean((echo-gaussian_filter(echo,1))[echo>20]**2))),2) if np.any(echo>20) else 0.,
            'lift_max_m':round(float(model.lift.max()),1),
            'cape_max':round(float(model.available_cape(model.mu['cape']).max()),1),
            'raw_cape_max':round(float(model.mu['cape'].max()),1),
            'cin_median':round(float(np.median(model.sb['cin'])),1),
            'rain_max_mm_h':round(float(model.last_rate.max()),2),
            'rain_over_20_area_km2':int(np.sum(model.last_rate>=20))*model.cfg['grid_km']**2,
            'gust_max_ms':round(float(gust.max()),2),
            'surface_wind_max_ms':round(float(np.hypot(model.u,model.v).max()),2),
            'hourly_rain_max_mm':round(float(model.hourly_rain().max()),2),
            'total_rain_max_mm':round(float(model.total.max()),2),
            'wake_cells':int(wake.sum()),
            'wake_cape_remaining_fraction':round(float(np.sum(model.available_cape(model.mu['cape'])[wake])/max(np.sum(raw_energy[wake]),1)),4) if wake.any() else None,
            'wake_cape_deficit_mean':round(float(model.cape_deficit[wake].mean()),1) if wake.any() else None,
            'cold_interior_cells':int(interior.sum()),
            'cold_interior_new_activity_fraction':round(float(np.mean(model.initiation[interior]>.1)),4) if interior.any() else 0.,
            'cold_interior_new_activity_mean':round(float(np.mean(model.initiation[interior])),5) if interior.any() else 0.,
            'core_rain_max_mm_h':round(float(model.last_core_rate.max()),2),
            'trailing_weak_echo_cells':int(((model.cold>.5)&(model.cold_depth>100)&(model.activity<.1)&(echo>=5)&(echo<35)).sum()),
            'anvil_water_kg_m2_max':float(ice_column.max()),
            'stratiform_rain_max_mm_h':float(model.last_stratiform_rate.max()),
            'stratiform_surface_rain_fraction':float(np.sum(model.last_stratiform_rate)/max(np.sum(model.last_rate),1e-12)),
            'rear_stratiform_area_km2':float(causal_rear.sum()*model.cfg['grid_km']**2),
            'rear_stratiform_ground_area_km2':float((causal_rear&(model.last_stratiform_rate>.1)).sum()*model.cfg['grid_km']**2),
            'rear_stratiform_echo_fraction':float(causal_rear.sum()/max(rear.sum(),1)),
            'line_candidates':[candidates[i] for i in qualified],
            'curved_band_candidates':[dict(candidates[i]) for i in combined],
            'largest_objects':sorted(candidates,key=lambda x:x['cells'],reverse=True)[:3],
            'budget':model.audit_state()}
    if with_curved_masks:return row,[masks[i] for i in qualified],[masks[i] for i in combined]
    return (row,[masks[i] for i in qualified]) if with_masks else row


class LineTracker:
    """Conservative identity matching of successive strong linear components.

    Advect the previous mask with its cloud wind, allow cold-pool propagation,
    require >=30% matched cells and <=45 degrees orientation change. No gaps
    are filled and a vanished line cannot be revived under its old identity.
    This is experimental object tracking, not an operational radar algorithm.
    """
    def __init__(self,grid_km):self.grid_km=grid_km;self.active=[];self.tracks=[]

    def update(self,hour,candidates,masks):
        scores=[]
        for a,old in enumerate(self.active):
            dt=(hour-old['hour'])*3600;obj=old['candidate'];u,v=obj['motion_ms']
            predicted=shift(old['mask'].astype('uint8'),(v*dt/(self.grid_km*1000),u*dt/(self.grid_km*1000)),order=0,mode='constant',cval=0)>0
            speed=np.sqrt(2*9.80665*obj.get('coldpool_depth_mean_m',650)*obj['coldpool_max_K']/295)
            tolerance=max(1,int(np.ceil(speed*dt/(self.grid_km*1000))))
            predicted=binary_dilation(predicted,iterations=tolerance)
            for b,(new,mask) in enumerate(zip(candidates,masks)):
                angle=abs(obj['orientation_deg']-new['orientation_deg']);angle=min(angle,180-angle)
                overlap=float((predicted&mask).sum())/max(1,min(int(old['mask'].sum()),int(mask.sum())))
                if angle<=45 and overlap>=.3:scores.append((overlap,a,b))
        assigned={};used=set()
        for score,a,b in sorted(scores,reverse=True):
            if a not in used and b not in assigned:assigned[b]=self.active[a]['track'];used.add(a)
        active=[]
        for b,(obj,mask) in enumerate(zip(candidates,masks)):
            if b in assigned:track=assigned[b]
            else:
                track={'id':len(self.tracks)+1,'start_hour':hour,'end_hour':hour,'duration_hours':0.,'samples':0,'max_length_km':0.}
                self.tracks.append(track)
            track['end_hour']=hour;track['duration_hours']=round(hour-track['start_hour'],3)
            track['samples']+=1;track['max_length_km']=max(track['max_length_km'],obj['length_km'])
            obj['track_id']=track['id']
            active.append({'hour':hour,'candidate':obj,'mask':mask,'track':track})
        self.active=active


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--hours',type=float,default=36)
    ap.add_argument('--seed',type=int,default=20260421);ap.add_argument('--grid-km',type=float,default=8)
    ap.add_argument('--moisture',type=float);ap.add_argument('--output',required=True)
    ap.add_argument('--random-environment',action='store_true',help='Use exactly the same seeded environment sampler as the live page')
    ap.add_argument('--compact-transport',action='store_true')
    ap.add_argument('--sample-minutes',type=float,default=30)
    ap.add_argument('--require-duration-hours',type=float,default=0)
    ap.add_argument('--quiet',action='store_true');ap.add_argument('--snapshots',action='store_true')
    ap.add_argument('--progress',action='store_true',help='Compact diagnostics during a quiet long run')
    args=ap.parse_args()
    if args.random_environment and args.moisture is not None:ap.error('random-environment cannot override its sampled moisture')
    cfg=settings({'hours':args.hours,'seed':args.seed,'grid_km':args.grid_km,**({'moisture':args.moisture} if args.moisture is not None else {})})
    if args.random_environment:cfg=random_environment(args.seed,{'hours':args.hours,'grid_km':args.grid_km,'frame_minutes':10})
    if args.compact_transport:cfg['compact_transport']=True
    digest=source_digest()
    started=time.monotonic()
    height,_=terrain_for(cfg,'assets/data/simulation-terrain.npz');m=Model(cfg,height)
    samples=[];tracker=LineTracker(cfg['grid_km']);curved_tracker=LineTracker(cfg['grid_km']);peak_score=0
    def snapshot(suffix):
        f=m.fields()
        np.savez_compressed(args.output+'.'+suffix+'.npz',time_hours=m.time/3600,lon=m.lon,lat=m.lat,air=m.air,cold=m.cold,cold_depth=m.cold_depth,cold_content=m.cold_content,initiation=m.initiation,activity=m.activity,lift=m.lift,anvil_column=np.sum(m.anvil*m.mass,axis=0),stratiform_column=np.sum(m.stratiform_rain*m.mass,axis=0),stratiform_rainrate=m.last_stratiform_rate,**{k:f[k] for k in ['composite','rainrate','rain_hour','sbcape','mlcape','mucape','mucape_raw','cape_deficit','rain_total','cin','temperature','gust','u10','v10']})
    if not 10<=args.sample_minutes<=60:ap.error('sample-minutes must be 10..60')
    times=np.arange(0,args.hours*3600+1,args.sample_minutes*60).tolist()
    if times[-1]<args.hours*3600:times.append(args.hours*3600)
    for target in times:
        while m.time<target-1e-6:m.step(target)
        row,masks,curved_masks=morphology(m,with_curved_masks=True)
        tracker.update(row['hour'],row['line_candidates'],masks)
        curved_tracker.update(row['hour'],row['curved_band_candidates'],curved_masks);samples.append(row)
        if abs(row['budget']['water_relative_residual'])>.002:raise FloatingPointError('Full-process water budget residual exceeds 0.2%')
        if not args.quiet:print(json.dumps(row),flush=True)
        elif args.progress:
            au,av=m.anvil_winds(*m.winds())
            print(json.dumps({'hour':row['hour'],'steps':m.steps,'anvil_wind_max_ms':float(np.max(np.abs(au)+np.abs(av))),
                              'elapsed_s':round(time.monotonic()-started,1),'line_count':len(row['line_candidates']),
                              'curved_band_count':len(row['curved_band_candidates']),
                              'front_lat':row['front_regional_latitude'],'gust_max_ms':row['gust_max_ms'],
                              'rear_stratiform_area_km2':row['rear_stratiform_area_km2'],'rain_max_mm_h':row['rain_max_mm_h']}),flush=True)
        if args.snapshots and target%21600==0:
            snapshot(str(int(target/3600)))
        score=max((x['geodesic_length_km']*x['rain_mean_mm_h'] for x in row['curved_band_candidates']),default=0)
        if args.snapshots and score>peak_score:
            peak_score=score;snapshot('peak')
    longest=max((t['duration_hours'] for t in tracker.tracks),default=0)
    Path(args.output).write_text(json.dumps({'engine':VERSION,'source_sha256':digest,'config':cfg,'front_regime':m.front_regime,'elapsed_seconds':round(time.monotonic()-started,2),'sample_minutes':args.sample_minutes,'longest_tracked_line_hours':longest,'longest_curved_band_hours':max((t['duration_hours'] for t in curved_tracker.tracks),default=0),'tracks':tracker.tracks,'curved_band_tracks':curved_tracker.tracks,'samples':samples},indent=2))
    print(json.dumps({'output':args.output,'max_strong_cells':max(x['strong_cells'] for x in samples),'line_samples':sum(bool(x['line_candidates']) for x in samples),'longest_tracked_line_hours':longest,'max_rain':max(x['rain_max_mm_h'] for x in samples),'final':samples[-1]}),flush=True)
    if longest<args.require_duration_hours:raise SystemExit('Required continuous line duration not reached')


if __name__=='__main__':main()
