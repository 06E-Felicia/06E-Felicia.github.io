"""Strict 4 km structure/lineage and rolling rainfall audit from immutable native replay fields."""
import argparse, gzip, json, math
from pathlib import Path
import numpy as np
from scipy import ndimage
from vacation_replay_data import load_manifest, read_frame


def passage_evidence(passages, births, expected_times, observed_times):
    """Different real IDs, first actual passage span; births are review evidence only."""
    if any(t not in observed_times for t in expected_times):
        return None
    visits = {}
    for p in passages:
        cid, t = p.get('id'), p.get('t')
        if cid not in births or not finite_number(t):
            continue
        visits[cid] = min(t, visits.get(cid, t))
    if len(visits) < 3:
        return None
    span = max(visits.values()) - min(visits.values())
    if span < 1800:
        return None
    ids = sorted(visits)
    born = [births[cid]['t'] for cid in ids]
    return {'birthIDs': ids, 'firstTimes': visits, 'passageSpanSeconds': span,
            'birthSpanSeconds': max(born) - min(born)}


def objects(z, cells, dx=4000):
    mask=np.nan_to_num(z,nan=-999)>=35
    labels,n=ndimage.label(mask,np.ones((3,3)))
    result=[]
    for label in range(1,n+1):
        yy,xx=np.where(labels==label)
        if len(xx)<2: continue
        cov=np.cov(np.array([xx,yy]),bias=True)*dx*dx
        eig=np.maximum(np.linalg.eigvalsh(cov),1)
        length=4*math.sqrt(eig[1]);aspect=math.sqrt(eig[1]/eig[0]);area=len(xx)*dx*dx/1e6
        member=np.array([c['derivedVelocity'][0] for c in cells if c.get('derivedVelocity') is not None and 0<=int(c['y']/dx)<mask.shape[0] and 0<=int(c['x']/dx)<mask.shape[1] and labels[int(c['y']/dx),int(c['x']/dx)]==label])
        membery=np.array([c['derivedVelocity'][1] for c in cells if c.get('derivedVelocity') is not None and 0<=int(c['y']/dx)<mask.shape[0] and 0<=int(c['x']/dx)<mask.shape[1] and labels[int(c['y']/dx),int(c['x']/dx)]==label])
        own=labels==label
        cores=ndimage.label(own & (np.nan_to_num(z,nan=-999)>=45),np.ones((3,3)))[1]
        result.append({'mask':own,'area':area,'length':length/1000,'aspect':aspect,'centroid':[float((np.mean(xx)+.5)*dx),float((np.mean(yy)+.5)*dx)],'velocity':[float(np.median(member)) if len(member) else 0,float(np.median(membery)) if len(membery) else 0], 'memberCells':len(member),'cores45':cores,'band':area>=1280 and length>=80000 and aspect>=3})
    return result


def gradient(a,dx):
    values=[]
    for axis in (0,1):
        d=np.abs(np.diff(a,axis=axis));coord=(np.arange(d.shape[axis])+1)*dx
        fence=np.isclose(np.mod(coord,10000),0)
        if np.any(fence) and np.any(~fence):
            b=np.take(d,np.where(fence)[0],axis=axis);inside=np.take(d,np.where(~fence)[0],axis=axis)
            values.append((float(np.mean(b)),float(np.mean(inside))))
    if not values:return None
    b=np.mean([v[0] for v in values]);i=np.mean([v[1] for v in values])
    return {'boundary':float(b),'interior':float(i),'ratio':float(b/i) if i>0 else None}


def finite_number(value):
    if isinstance(value,(bool,np.bool_)) or not isinstance(value,(int,float,np.integer,np.floating)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError,TypeError,ValueError):
        return False


def budget_check(initial,incoming,outgoing,inventory,activity=None,absolute_floor=1e-10):
    """Zero activity uses an explicit 8-ULP roundoff envelope, never an initial-mass relative denominator."""
    terms=(initial,incoming,outgoing,inventory)
    if not all(finite_number(v) for v in terms):return {'status':'fail','reason':'nonfinite_or_invalid_scalar'}
    if min(initial,incoming,outgoing,inventory)<0:return {'status':'fail','reason':'negative_inventory_or_flux'}
    residual=initial+incoming-outgoing-inventory
    if not finite_number(residual):return {'status':'fail','reason':'nonfinite_residual'}
    activity=incoming+outgoing if activity is None else activity
    if not finite_number(activity) or activity<0:return {'status':'fail','reason':'invalid_activity'}
    if activity==0:
        tolerance=max(absolute_floor,8*math.fsum(math.ulp(float(v)) for v in terms))
        return {'status':'zero_activity_consistent' if abs(residual)<=tolerance else 'fail','mode':'absolute_zero_activity','residual':residual,'absoluteTolerance':tolerance,'relativeResidual':None,'activity':0}
    relative=abs(residual)/activity
    return {'status':'pass' if relative<1e-7 else 'fail','mode':'actual_activity','residual':residual,'relativeResidual':relative,'activity':activity}


def valid_budget(result):
    return result['status'] in ['pass','zero_activity_consistent']


def analyze(directory):
    directory=Path(directory);manifest=load_manifest(directory);report=json.loads((directory/'report.json').read_text());g=manifest['grids']['radar'];interval=manifest['frameIntervalSeconds']
    factor=round(4000/g['dx'])
    if factor<1 or factor*g['dx']!=4000:raise ValueError('Output must conservatively reduce to common 4 km')
    nx=g['nx']//factor;previous=[];next_track=0;tracks={};nodes={};children={};frame_records=[];trajectories={};previous_cells={};totals=[];times=[]
    rolling={str(h):None for h in [1,3,6,12,24]};maxz=-999;area_time=0;maxsource=0.;missing_sources=[];invalid_cells=[];maxheat=0.;missing_heat=[];source_budget_checks=[];heat_budget_checks=[];zero_activity=[]
    required_sources=['vaporL','vaporM','cloudL','cloudM','core','detrained','boundary']
    for fi,entry in enumerate(manifest['frames']):
        meta,f=read_frame(directory,manifest,entry);t=entry['simTime']
        if factor>1:
            for key in ['rain_total','rain_rate','reflectivity_composite']:
                a=f[key];ny0,nx0=a.shape
                if key.startswith('reflectivity'):
                    linear=np.where(np.isfinite(a),10**(np.nan_to_num(a,nan=-999)/10),0);mean=linear.reshape(ny0//factor,factor,nx0//factor,factor).mean((1,3));f[key]=np.where(mean>0,10*np.log10(np.maximum(mean,1e-99)),np.nan)
                else:f[key]=a.reshape(ny0//factor,factor,nx0//factor,factor).mean((1,3))
        current_cells={};members=[]
        for raw in meta.get('cells',[]):
            cell=dict(raw);cid=cell.get('id')
            if cid is None or cid in current_cells or not all(finite_number(cell.get(k)) for k in ['x','y']):invalid_cells.append({'t':t,'id':cid,'reason':'missing or duplicate sampled ID'});continue
            prev=previous_cells.get(cid);velocity=None
            if prev and t-prev['t']==interval:velocity=[(cell['x']-prev['x'])/interval,(cell['y']-prev['y'])/interval]
            supplied=cell.get('suppliedKgThisStep')
            if not finite_number(supplied) and prev and finite_number(cell.get('supplied')) and finite_number(prev.get('supplied')):supplied=max(0,cell['supplied']-prev['supplied'])
            cell.update(t=t,derivedVelocity=velocity,actualSupply=supplied)
            current_cells[cid]=cell;members.append(cell);trajectories.setdefault(cid,[]).append(cell)
        previous_cells=current_cells
        z=f['reflectivity_composite'];cur=objects(z,members);maxz=max(maxz,float(np.nanmax(z)) if np.any(np.isfinite(z)) else -999)
        actual_dt=t-times[-1] if times else 0;area_time+=int(np.count_nonzero(np.nan_to_num(z,nan=-999)>=35))*16*actual_dt
        pairs=[]
        for ci,obj in enumerate(cur):
            obj['objectId']=f'{fi}:{ci}';obj['parents']=[]
            for pi,prev in enumerate(previous):
                predicted=np.array(prev['centroid'])+np.array(prev['velocity'])*actual_dt
                if np.linalg.norm(predicted-obj['centroid'])>30000:continue
                if 'adv' not in prev:prev['adv']=ndimage.shift(prev['mask'].astype(np.uint8),np.array(prev['velocity'])[::-1]*actual_dt/4000,order=0,mode='constant')>0
                adv=prev['adv'];union=np.count_nonzero(adv|obj['mask']);iou=np.count_nonzero(adv&obj['mask'])/union if union else 0
                if iou>=.15:
                    pairs.append((float(iou),pi,ci));obj['parents'].append(prev['objectId'])
                    children.setdefault(prev['objectId'],[]).append(obj['objectId'])
        used_previous=set();used_current=set()
        for score,pi,ci in sorted(pairs,key=lambda v:(-v[0],v[1],v[2])):
            if pi in used_previous or ci in used_current:continue
            cur[ci]['trackId']=previous[pi]['trackId'];cur[ci]['mainParent']=previous[pi]['objectId'];used_previous.add(pi);used_current.add(ci)
        for obj in cur:
            if 'trackId' not in obj:obj['trackId']=next_track;next_track+=1
            obj['id']=obj['trackId']
            record={k:v for k,v in obj.items() if k not in ['mask','adv']};record['t']=t;record['pixels']=np.flatnonzero(obj['mask']).astype(int).tolist()
            nodes[obj['objectId']]=record;tracks.setdefault(str(obj['trackId']),[]).append(record)
        frame_records.append({'t':t,'objects':[nodes[o['objectId']] for o in cur],'cellIDs':list(current_cells)})
        previous=cur;totals.append(f['rain_total'].astype(np.float32));times.append(t)
        for h in [1,3,6,12,24]:
            if t<h*3600:continue
            matches=[j for j,tt in enumerate(times) if tt==t-h*3600]
            if not matches:continue
            acc=f['rain_total']-totals[matches[0]];value=float(np.max(acc));yy,xx=np.unravel_index(np.argmax(acc),acc.shape)
            if rolling[str(h)] is None or value>rolling[str(h)]['maxMm']:rolling[str(h)]={'maxMm':value,'endSeconds':t,'locationGrid':[int(xx),int(yy)],'area50Km2':int(np.count_nonzero(acc>=50))*16,'area80Km2':int(np.count_nonzero(acc>=80))*16}
        accounting=meta.get('sourceAccounting')
        for key in required_sources+['total']:
            balance=accounting.get(key) if isinstance(accounting,dict) else None
            required=['initial','in','out','inventory','residual']+(['inventorySumResidual','groundSumResidual'] if key=='total' else [])
            if not isinstance(balance,dict) or any(k not in balance for k in required):
                missing_sources.append({'t':t,'source':key});continue
            if not all(finite_number(balance[k]) for k in required):
                source_budget_checks.append({'t':t,'source':key,'status':'fail','reason':'invalid_scalar'});continue
            check=budget_check(balance['initial'],balance['in'],balance['out'],balance['inventory'])
            if 'mode' not in check:
                source_budget_checks.append({'t':t,'source':key,**check});continue
            if check['mode']=='actual_activity':maxsource=max(maxsource,check['relativeResidual'])
            if check['mode']=='absolute_zero_activity':zero_activity.append({'t':t,'source':key,**check})
            # Verify declared residual and inventory/ground reconciliation with the same actual activity rule.
            for name,delta in [('declaredResidual',balance['residual']-check['residual'])]+([(name,balance[name]) for name in ['inventorySumResidual','groundSumResidual']] if key=='total' else []):
                if check['activity']==0:
                    if abs(delta)>check['absoluteTolerance']:check={**check,'status':'fail','reason':name}
                elif abs(delta)/check['activity']>=1e-7:check={**check,'status':'fail','reason':name}
            source_budget_checks.append({'t':t,'source':key,**check})
        heat=accounting.get('heat') if isinstance(accounting,dict) else None
        required_heat=['initial','in','out','inventory','phaseHeating','phaseCooling']
        if not isinstance(heat,dict) or any(k not in heat for k in required_heat):missing_heat.append(t)
        elif not all(finite_number(heat[k]) for k in required_heat):heat_budget_checks.append({'t':t,'status':'fail','reason':'invalid_scalar'})
        else:
            check=budget_check(heat['initial'],heat['in'],heat['out'],heat['inventory'],activity=heat['in']+heat['out']+heat['phaseHeating']+heat['phaseCooling'],absolute_floor=1e-6)
            heat_budget_checks.append({'t':t,**check})
            if check.get('relativeResidual') is not None:maxheat=max(maxheat,check['relativeResidual'])
    births={};duplicate_birth_ids=set()
    for line in (directory/'births.ndjson').read_text().splitlines():
        if not line:continue
        b=json.loads(line);cid=b.get('id')
        if not isinstance(cid,str) or not all(finite_number(b.get(k)) for k in ['t','x','y']):continue
        if cid in births:duplicate_birth_ids.add(cid)
        else:births[cid]=b
    persistent=[];verified=[];window_rejections=[];time_index={t:i for i,t in enumerate(times)}
    sample_supported=interval>0 and 5400%interval==0
    if sample_supported:
        expected_count=5400//interval+1
        for first in frame_records:
            start=first['t'];end=start+5400
            if end>times[-1]:continue
            expected=[start+k*interval for k in range(expected_count)]
            if any(tt not in time_index for tt in expected):window_rejections.append({'start':start,'reason':'missing frame'});continue
            indices=[time_index[tt] for tt in expected]
            for anchor in first['objects']:
                if not(anchor['band'] and anchor['cores45']>=2):continue
                lineage={anchor['objectId']};queue=[anchor['objectId']]
                while queue:
                    oid=queue.pop()
                    for child in children.get(oid,[]):
                        if nodes[child]['t']<=end and child not in lineage:lineage.add(child);queue.append(child)
                selections=[];pixel_sets=[]
                for idx in indices:
                    qualified=[o for o in frame_records[idx]['objects'] if o['objectId'] in lineage and o['band'] and o['cores45']>=2]
                    selections.append(max(qualified,key=lambda o:(o['area'],o['objectId'])) if qualified else None)
                    pixel_sets.append(set().union(*(set(o['pixels']) for o in qualified)))
                qualified_count=sum(o is not None for o in selections)
                if qualified_count<math.ceil(.75*expected_count):continue
                band={'track':str(anchor['trackId']),'objectId':anchor['objectId'],'start':start,'end':end,'qualifiedFrames':qualified_count,'expectedFrames':expected_count,'qualifiedFraction':qualified_count/expected_count}
                persistent.append(band)
                if selections[-1] is None:continue
                displacement=float(np.linalg.norm(np.array(selections[-1]['centroid'])-anchor['centroid']))
                if displacement>30000:continue
                passages=[]
                for wi,idx in enumerate(indices):
                    valid_pixels=pixel_sets[wi]
                    if not valid_pixels:continue
                    t=times[idx]
                    for cid in frame_records[idx]['cellIDs']:
                        if cid not in births or cid in duplicate_birth_ids:continue
                        cell=next(c for c in trajectories[cid] if c['t']==t);velocity=cell['derivedVelocity'];supply=cell['actualSupply']
                        if velocity is None or cell.get('age',0)<600 or not finite_number(supply) or supply<=0:continue
                        px=int(cell['x']//4000);py=int(cell['y']//4000)
                        if px<0 or py<0 or px>=nx or py*nx+px not in valid_pixels:continue
                        passages.append({'id':cid,'t':t,'x':cell['x'],'y':cell['y'],'speed':math.hypot(*velocity)})
                anchors=sorted({(int(c['x']//4000),int(c['y']//4000)) for c in passages})
                for px,py in anchors:
                    x=(px+.5)*4000;y=(py+.5)*4000;near=[c for c in passages if math.hypot(c['x']-x,c['y']-y)<=8000];ids=sorted({c['id'] for c in near})
                    evidence=passage_evidence(near,births,expected,time_index)
                    if evidence is None:continue
                    visits=evidence['firstTimes']
                    speed=float(np.median([c['speed'] for c in near]))
                    if speed<5:continue
                    strong_seconds=0;rain_evidence=[]
                    for wi in range(1,len(indices)):
                        dt=expected[wi]-expected[wi-1];pixels=pixel_sets[wi]&pixel_sets[wi-1]
                        local=[k for k in pixels if math.hypot((k%nx+.5)*4000-x,(k//nx+.5)*4000-y)<=8000]
                        if not local:continue
                        rates=(totals[indices[wi]].ravel()[local]-totals[indices[wi-1]].ravel()[local])*3600/dt
                        if np.any(rates<-1e-5):continue
                        maximum=float(np.max(rates));rain_evidence.append({'start':expected[wi-1],'end':expected[wi],'maxIntervalMeanMmH':maximum})
                        if maximum>=20:strong_seconds+=dt
                    if strong_seconds>=1800:
                        verified.append({**band,'x':x,'y':y,'birthIDs':ids,'passageFirstTimes':visits,'passageSpanSeconds':evidence['passageSpanSeconds'],'birthSpanSeconds':evidence['birthSpanSeconds'],'medianPositionDerivedSpeed':speed,'centroidDisplacementKm':displacement/1000,'strongIntervalSeconds':strong_seconds,'intervalRain':rain_evidence});break
    native=np.frombuffer(gzip.decompress((directory/'rain-total-1km.f32.gz').read_bytes()),dtype='<f4').reshape(manifest['grids']['rainLedger']['ny'],manifest['grids']['rainLedger']['nx'])
    gradients={}
    for scale in [1,2,4,10]:
        ny0,nx0=native.shape;coarse=native[:ny0//scale*scale,:nx0//scale*scale].reshape(ny0//scale,scale,nx0//scale,scale).mean((1,3));gradients[str(scale)]=gradient(coarse,scale*1000)
    water=report.get('audit',{}).get('activityResidual');water_check=bool(water<1e-7) if finite_number(water) else None
    source_check=False if any(not valid_budget(c) for c in source_budget_checks) else None if missing_sources else True
    continuity=all(b-a==interval for a,b in zip(times,times[1:]));window_available=times[-1]-times[0]>=5400;regeneration_check=bool(verified) if sample_supported and continuity and window_available and not invalid_cells else None
    checks={'heat':False if any(not valid_budget(c) for c in heat_budget_checks) else None if missing_heat else True,'water':water_check,'sources':source_check,'native10kmFence':gradients['1']['ratio'] is not None and gradients['1']['ratio']<3,'persistentBand':bool(persistent) if sample_supported and continuity and window_available else None,'regeneration':regeneration_check,'rainfall80mm':any(v and v['maxMm']>=80 and v['area50Km2']>=100 for k,v in rolling.items() if int(k)<=12)}
    result={'model':report['model'],'config':report['config'],'durationHours':times[-1]/3600,'maxDbz':maxz,'area35Km2Seconds':area_time,'birthDensityPer10000Km2Hour':report['stats']['births']/(g['width']*g['height']/1e10)/(times[-1]/3600),'rolling':rolling,'gradient':gradients,'persistentBands':persistent,'regeneration':verified,'sourceRelativeResidual':maxsource if not missing_sources else None,'checks':checks,'checkStatus':{k:'not_measured' if v is None else 'pass' if v else 'fail' for k,v in checks.items()},'dataLimits':{'zeroActivityBudgets':zero_activity,'sourceBudgetChecks':source_budget_checks,'heatBudgetChecks':heat_budget_checks,'heatAccountingMissing':missing_heat,'sourceAccountingMissing':missing_sources,'invalidSampledIDs':invalid_cells,'duplicateBirthIDs':sorted(duplicate_birth_ids),'windowRejections':window_rejections,'archiveIntervalSeconds':interval,'continuousFrames':continuity,'samplingLimit':'Interpret 2/5/10 minute comparisons only where crossing and maturation are temporally resolved. Only sampled mature, supplied IDs count; trajectories shorter than two contiguous frames cannot establish motion.'}}
    (directory/'structure-tracks.json').write_text(json.dumps({'frames':frame_records,'tracks':tracks,'lineageEdges':children},indent=2,default=lambda v:v.item()))
    (directory/'revision-analysis.json').write_text(json.dumps(result,indent=2,default=lambda v:v.item()));return result

def combine_checks(values):
    values=list(values)
    if not values:return None
    if any(v is False for v in values):return False
    return None if any(v is None for v in values) else True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory');args=parser.parse_args();root=Path(args.directory)
    if (root/'manifest.json').is_file():print(json.dumps(analyze(root),indent=2,default=lambda v:v.item()));return
    results=[]
    for p in sorted(root.glob('*/report.json')):
        result=analyze(p.parent);results.append(result);print(p.parent.name,result['checks'],flush=True)
    groups={}
    for group in ['coastal','terrain','afternoon','fastline']:
        subset=[r for r in results if r['config'].get('scenarioGroup')==group and r['durationHours']==6]
        groups[group]={'cases':len(subset),'bands':sum(r['checks']['persistentBand'] is True for r in subset),'regeneration':sum(r['checks']['regeneration'] is True for r in subset),'rainfall80':sum(r['checks']['rainfall80mm'] for r in subset),'allWater':combine_checks(r['checks']['water'] for r in subset) if len(subset)==8 else None,'allSources':combine_checks(r['checks']['sources'] for r in subset) if len(subset)==8 else None}
    summary={'cases':len(results),'groups':groups,'casesData':results,'acceptance':{'coastal6of8Bands':groups['coastal']['bands']>=6 if groups['coastal']['cases']==8 else None,'coastal4of8Regeneration':groups['coastal']['regeneration']>=4 if groups['coastal']['cases']==8 else None,'ordinary6of8Rain':groups['coastal']['rainfall80']>=6 if groups['coastal']['cases']==8 else None,'qualityConvergence':'not yet measured; requires common 4 km conservative reduction of all quality levels'}}
    (root/'ensemble-analysis.json').write_text(json.dumps(summary,indent=2,default=lambda v:v.item()))

if __name__=='__main__':main()
