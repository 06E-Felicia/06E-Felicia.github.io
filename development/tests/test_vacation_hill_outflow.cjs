'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs');
C.prepareBackendSync();const drain=it=>{while(!it.next().done){}};
const m=new C.Model({preset:'monsoon',geography:'real',seed:20210520,coastalForcing:{exitOffset:80000}},terrain());
// Resolved total wind, including perturbations, cannot inherit nighttime amplification.
const c=m.coastalGeometry,wind=[];
m.config.hillJetBraking=false;
for(const scale of [.4,1,2,4])for(const cross of [0,1000000])for(const delta of [{u:0,v:0},{u:15,v:15},{u:-5,v:-5}]){
 const bg={...m.background(),V:scale*m.preset.baseV,exitEnvelope:0},e=m._jetFrame(bg).e,out=[],x=c.crossing.x-e.y*cross,y=c.crossing.y+e.x*cross;
 m._finiteWindSample(x,y,bg,1,0,0,1,delta,out);const speed=Math.hypot(out[0],out[1]);
 if(cross===0){assert(speed>=13-1e-9&&speed<=15+1e-9);}else assert(speed>=10-1e-9&&speed<=13+1e-9);
 wind.push(speed);
}
m.config.hillJetBraking=true;
for(const key of ['rhL','rhM','el','em','inflowFocus'])m.fields[key].fill(.98);m.fields.xiL.fill(10000);m.fields.xiM.fill(10000);
const hills=[];
for(const degrees of [20,65]){
 const bg={...m.background(),windAngle:degrees*Math.PI/180},e=m._jetFrame(bg).e;let found=null;
 for(let k=0;k<m.env.n&&!found;k++){
  const x=(k%m.env.nx+.5)*m.env.dx,y=(Math.floor(k/m.env.nx)+.5)*m.env.dx,a=m._jetExitAccess(x,y,bg);
  if(y<220000||(degrees===20?m._approxLongitude(x)<114.7:m._approxLongitude(x)>112.65))continue;
  if(a.factor<.02||a.hillFront<.25||a.ascent<.02||m.gate(x,y,0,bg,true).F<=0)continue;
  const out=[],up=[];m._finiteWindSample(x-e.x*10000,y-e.y*10000,bg,1,undefined,0,1,{u:0,v:0},up);m._finiteWindSample(x+e.x*10000,y+e.y*10000,bg,1,undefined,0,1,{u:0,v:0},out);
  const slowdown=Math.hypot(up[0],up[1])-Math.hypot(out[0],out[1]);
  if(slowdown>.5)found={degrees,x,y,slowdown,peakM:a.terrainAnchor.peakM,ascent:a.ascent};
 }
 assert(found,'real windward mountain front can initiate under both western and southern inflow');hills.push(found);
}
let unseededInlandCutoff=false;
for(let k=0;k<m.env.n&&!unseededInlandCutoff;k++){
 const x=(k%m.env.nx+.5)*m.env.dx,y=(Math.floor(k/m.env.nx)+.5)*m.env.dx;
 if(y<550000)continue;
 const inlet=m._trainingFeed(x,y),moving=m._trainingFeed(x,y,true);
 if(inlet.accessible&&moving.reason==='outsideFedJet')unseededInlandCutoff=true;
}
assert(unseededInlandCutoff,'background inland monsoon alone cannot keep travelling cores alive');
// Persistent sources may draw from a connected warm flank; they cannot jump a
// closed deep-cold ring, or obtain water from an entirely cold/dry domain.
const fan=new C.Model({preset:'coast',geography:'idealized',width:240000,height:240000,trainingInflowFan:true});
fan.fields.u.fill(0);fan.fields.v.fill(13);fan.fields.rhL.fill(.96);fan.fields.el.fill(.9);
for(let k=0;k<fan.cold.n;k++){const x=(k%fan.cold.nx+.5)*fan.cold.dx,y=(Math.floor(k/fan.cold.nx)+.5)*fan.cold.dx;if(Math.abs(x-120000)<5000&&y<122500){fan.h[k]=700;fan.q[k]=2100;}}
assert(fan._trainingFeed(120000,130000).accessible,'open side intake remains connected');
fan.config.trainingInflowFan=false;assert.equal(fan._trainingFeed(120000,130000).accessible,false,'straight-only sampler misses that intake');fan.config.trainingInflowFan=true;
fan.h.fill(700);fan.q.fill(2100);assert.equal(fan._trainingFeed(120000,130000).accessible,false);fan.h.fill(0);fan.q.fill(0);fan.fields.rhL.fill(.6);assert.equal(fan._trainingFeed(120000,130000).accessible,false);
// Same finite initial cold pool; no rainfall or extra cold mass. Test expansion
// and explicit sinks rather than drawing a radius or changing the cold threshold.
const spreading=[];
for(const current of [false,true]){
 const a=new C.Model({preset:'coast',geography:'idealized',width:320000,height:320000,coldDampingSeconds:current?7200:900,coldVolumeMixingSeconds:current?43200:5400,coldThermalMixingSeconds:current?28800:3600});
 a.cz.fill(0);a.cu.fill(0);a.cv.fill(0);
 for(let k=0;k<a.cold.n;k++){const x=(k%a.cold.nx+.5)*a.cold.dx,y=(Math.floor(k/a.cold.nx)+.5)*a.cold.dx;if(Math.hypot(x-160000,y-160000)<30000){a.h[k]=500;a.q[k]=1250;}}
 a.captureInitialState();let maxArea=0,area=0;
 for(let step=0;step<36;step++){drain(a.advanceCold());area=0;for(let k=0;k<a.cold.n;k++)if(a.h[k]>=40&&a.q[k]>=20&&a.q[k]/a.h[k]>=.3)area+=a.cold.area/1e6;maxArea=Math.max(maxArea,area);}
 const audit=a.audit();assert(Math.abs(audit.coldVolumeResidual)/a.initialColdVolume<1e-10);assert(Math.abs(audit.coldHeatResidual)/a.initialColdHeat<1e-10);assert(a.h.every(v=>Number.isFinite(v)&&v>=0));assert.equal(a.stats.coldVolumeSource,0);assert.equal(a.stats.coldHeatSource,0);
 spreading.push({current,maxAreaKm2:maxArea,areaAfter6HoursKm2:area,volumeResidual:audit.coldVolumeResidual,heatResidual:audit.coldHeatResidual});
}
assert(spreading[1].maxAreaKm2>spreading[0].maxAreaKm2*1.5);assert(spreading[1].areaAfter6HoursKm2>spreading[0].areaAfter6HoursKm2);assert(spreading[1].areaAfter6HoursKm2>Math.PI*30**2,'finite source expands beyond its initial footprint');
console.log(JSON.stringify({pass:true,windRange:[Math.min(...wind),Math.max(...wind)],hills,spreading}));
