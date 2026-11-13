// Track connected warm-sector precipitation independently of the cell count.
// No snapshots or replay storage; only two sets of component centroids are kept.
'use strict';
const S=require('../../assets/scripts/stormsol-model.js'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const bytes=fs.readFileSync(path.resolve(__dirname,'../../assets/data/stormsol-terrain.u16'));
const terrain=new Uint16Array(bytes.buffer,bytes.byteOffset,bytes.length/2);
const {nx,ny}=S.product,queue=new Int32Array(nx*ny),seen=new Uint8Array(queue.length);
// Diagnose the rendered rain field, independently of the model's convergence
// segments. Compare the east edge with the chord joining its own two flanks;
// this removes line tilt. Require strong crests separated by weaker, still
// connected rain. No target for the system's total north/south extent.
function countBows(m,count){
  const edge=new Float32Array(ny).fill(NaN),peak=new Float32Array(ny);
  for(let j=0;j<count;j++){
    const k=queue[j],row=Math.floor(k/nx),x=2*(k%nx)+1;
    edge[row]=Number.isNaN(edge[row])?x:Math.max(x,edge[row]);
    peak[row]=Math.max(peak[row],m.rate[k]);
  }
  const avg=(a,r)=>(a[r-1]+a[r]+a[r+1])/3,crests=[];
  for(let r=10;r<ny-10;r++){
    const bulge=avg(edge,r)-.5*(avg(edge,r-8)+avg(edge,r+8));
    if(!(bulge>=4&&avg(peak,r)>=30))continue;
    const last=crests.at(-1);
    if(last&&r-last.r<10){if(bulge>last.bulge)crests[crests.length-1]={r,bulge};}
    else crests.push({r,bulge});
  }
  let countConnected=0,streak=1;
  for(let k=1;k<crests.length;k++){
    const a=crests[k-1].r,b=crests[k].r;
    let gap=Infinity;
    for(let r=a+2;r<=b-2;r++)gap=Math.min(gap,avg(peak,r));
    // A factor of 1.55 in surface rain corresponds to ~3 dBZ in this Z-R relation.
    streak=gap*1.55<=Math.min(avg(peak,a),avg(peak,b))?streak+1:1;
    countConnected=Math.max(countConnected,streak);
  }
  return countConnected;
}
function lines(m){
  const result=[];
  const cutoff=(1e4/200)**(1/1.6);let total=0;
  for(let k=0;k<seen.length;k++){
    const x=(k%nx+.5)*2,y=((k/nx|0)+.5)*2;
    const warm=m.air[S.index(S.grid,x,y)]<.1;
    seen[k]=!(warm&&m.rate[k]>=5&&Math.max(m.rate[k],1.3*m.ice[k])>=cutoff);
    if(!seen[k])total++;
    if(m.convRate[k]>0)assert.ok(!m.coldInterior(S.index(S.forcing,x,y)),'deep convection inside the cold wake');
  }
  for(let i=0;i<seen.length;i++){
    if(seen[i])continue;
    let ymin=1000,ymax=0,peak=0,end=1,sx=0,sy=0,xx=0,xy=0,yy=0;seen[i]=1;queue[0]=i;
    for(let head=0;head<end;head++){
      const k=queue[head],x=(k%nx+.5)*2,y=((k/nx|0)+.5)*2;
      ymin=Math.min(ymin,y);ymax=Math.max(ymax,y);peak=Math.max(peak,m.rate[k]);sx+=x;sy+=y;xx+=x*x;xy+=x*y;yy+=y*y;
      for(const j of [k%nx?k-1:-1,k%nx<nx-1?k+1:-1,k-nx,k+nx]){
        if(j<0||j>=seen.length||seen[j])continue;
        seen[j]=1;queue[end++]=j;
      }
    }
    if(end<50||peak<30)continue;
    const x=sx/end,y=sy/end;
    if(m.front[Math.floor(x/5)]-y<75)continue;
    const a=xx/end-x*x,b=xy/end-x*y,c=yy/end-y*y;
    const disc=Math.hypot(a-c,2*b),major=(a+c+disc)/2,minor=(a+c-disc)/2;
    // Four standard deviations along the principal axis: length estimate,
    // not a diagonal bounding box (which also rewards round cloud shields).
    const length=4*Math.sqrt(major);
    if(major>=3*minor&&end/total>=.35)result.push({x,y,length,ns:ymax-ymin+2,share:end/total,bows:countBows(m,end)});
  }
  return result;
}
function track(seed,turn){
  const m=new S.Model(seed,terrain);
  // Optional controlled experiment: change wind turning only. Hold the
  // terrain, initial fields, humidity, bulk speed and random stream fixed.
  if(turn!==undefined)m.config.lowTurn=turn;
  let prev=[],best=0,longest=0,east=0,isolated=0,multiBowFrames=0,maxBows=0;const streak=new WeakMap();
  for(let t=1;t<=144;t++){
    m.advance();
    for(const c of m.cells){
      if(m.front[Math.floor(c.x/5)]-c.y<75)continue;
      const k=S.index(S.product,c.x,c.y);
      const separate=!m.cells.some(d=>d!==c&&d.strength>.25&&Math.hypot(c.x-d.x,c.y-d.y)<22);
      // Require a sustained isolated rain core, storm-scale rotation, and
      // opposing resolved velocity perturbations on either side of the core.
      const shear=m.stormV[k+2]-m.stormV[k-2];
      if(c.spin>.4&&shear>5&&m.rate[k]>=30&&separate){
        const duration=(streak.get(c)||0)+10;streak.set(c,duration);isolated=Math.max(isolated,duration);
      }else streak.delete(c);
    }
    if(t%3)continue;
    const now=lines(m);
    if(now.some(l=>l.bows>=2))multiBowFrames++;
    for(const line of now){
      const match=prev.map(p=>({p,d:Math.hypot(p.x-line.x,p.y-line.y)}))
        .filter(q=>q.d<55).sort((a,b)=>a.d-b.d)[0]?.p;
      line.start=match?.start??t;line.origin=match?.origin??line.x;
      maxBows=Math.max(maxBows,line.bows);best=Math.max(best,(t-line.start)/6);longest=Math.max(longest,line.length);
      east=Math.max(east,line.x-line.origin);
    }
    prev=now;
  }
  const result={seed,turn:m.config.lowTurn,trackedHours:best,lengthKm:Math.round(longest),eastwardKm:Math.round(east),isolatedMinutes:isolated,multiBowFrames,maxBows};
  console.log(result);return result;
}
const linear=track(20260421),veering=track(20260423),changed=track(20260421,1.1);
// A short-lived line can have several bowed segments at a single instant.
// Require continuity in time and translation of its measured rain footprint.
assert.ok(linear.trackedHours>=5 && linear.eastwardKm>=200 && linear.multiBowFrames>=2);
for(const run of [veering,changed])assert.ok(run.isolatedMinutes>=90 && run.trackedHours<linear.trackedHours);
// Seed one ordinary plume, let its real rain evaporate on flat terrain, then
// switch off all supply. Translation alone cannot pass the width/area tests.
const m=new S.Model(37,new Uint16Array(terrain.length)),g=S.forcing;
m.cells.push({x:450,y:400,age:25,life:120,amplitude:1,radius:7,strength:1,org:0,spin:0});
for(let n=0;n<4;n++){m.poolInput.fill(0);m.rainHalf(5);m.propagateCold(300);}
function footprint(){
  let minY=Infinity,maxY=-Infinity,area=0,heat=0;
  for(let i=0;i<m.cold.length;i++){
    heat+=m.poolHeat[i];if(m.cold[i]<.5||m.poolDepth[i]<50)continue;
    const y=((i/g.nx)|0)*2.5;area+=6.25;minY=Math.min(minY,y);maxY=Math.max(maxY,y);
  }
  return {area,minY,maxY,heat};
}
const before=footprint();m.cells=[];m.poolInput.fill(0);
for(let n=0;n<6;n++)m.propagateCold();
const after=footprint();console.log({initialArea:before.area,areaAfterHour:after.area,
  southKm:before.minY-after.minY,northKm:after.maxY-before.maxY});
assert.ok(before.area>0&&after.area>2*before.area&&after.heat>0&&after.heat<before.heat);
assert.ok(before.minY-after.minY>=5&&after.maxY-before.maxY>=5);
// Maximum ascent/overlapping plumes cannot override a capped northern column.
m.head.fill(1);m.energy.fill(160);m.air.fill(.35);m.rainHalf(5);
assert.ok(!m.convRate.some(v=>v>0)); // old stratiform ice may still fall
m.energy.fill(450);m.rainHalf(5);assert.ok(m.convRate.some(v=>v>0)&&!m.convRate.some(v=>v>20));

// Translate the same ridge across the inflow path. Hold the front, wind
// profile and donor thermodynamics fixed to isolate ascent versus descent.
function terrainFront(){
  const z=new Uint16Array(terrain.length),m=new S.Model(20260421,z);
  m.front.fill(410);m.air.fill(0);m.water.fill(38);m.energy.fill(1500);
  m.temp.fill(25);m.dew.fill(18);
  const column=Math.floor(575/2.5);
  function strongestRain(crest,cape){
    for(let k=0;k<z.length;k++){
      const y=(Math.floor(k/S.forcing.nx)+.5)*2.5;
      z[k]=crest?Math.round(1400*Math.exp(-.5*((y-crest)/3)**2)):0;
    }
    m.water.fill(38);m.energy.fill(cape);m.overturn.fill(0);
    m.ice.fill(0);m.head.fill(0);m.frontLift.fill(0);
    for(let i=0;i<8;i++)m.frontalAscent();
    m.rainHalf(5);
    let peak=0;
    for(let y=370;y<=405;y+=2)peak=Math.max(peak,m.convRate[S.index(S.product,(column+.5)*2.5,y)]);
    return peak;
  }
  const flat=strongestRain(0,1500),lee=strongestRain(371,1500);
  const ascent=strongestRain(381,1500),stable=strongestRain(381,160);
  console.log({flat,lee,ascent,stable});
  assert.ok(flat>0&&ascent>flat*1.3&&lee<flat*.4&&stable===0);
}
terrainFront();
