'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
C.prepareBackendSync();const data=terrain(),project=proj4('EPSG:4326',data.meta.projection),m=new C.Model({preset:'monsoon',geography:'real',seed:17,coastalForcing:{exitOffset:45000}},data),xy=(lon,lat)=>{const p=project.forward([lon,lat]);return[p[0]+640000,p[1]+400000]};
const angle=65*Math.PI/180,bg={...m.background(),windAngle:angle};m.fields.u.fill(13*Math.cos(angle));m.fields.v.fill(13*Math.sin(angle));
for(const p of [[114.39,22.75],[114.35,22.68]])assert.equal(m._jetExitAccess(...xy(...p),bg).factor,0,'Pingshan lee must not act as terrain source');
for(const p of [[114.13,22.38],[113.57,22.27]]){const a=m._jetExitAccess(...xy(...p),bg);assert(a.factor>.05);assert(a.ascent>.02,'southerly exposed delta/island terrain lifts air');}
const westBg={...bg,windAngle:50*Math.PI/180};m.fields.u.fill(13*Math.cos(westBg.windAngle));m.fields.v.fill(13*Math.sin(westBg.windAngle));assert.equal(m._windwardExposure(...xy(112.3,22.2),westBg).factor,0,'Enping lee profile rejected');
// A resolved cold head supplies lifting on a warm offshore side even when
// the background's static terrain gate is zero. No geography or water is faked.
const [x,y]=xy(114.5,22),feed=m.env.index(x,y-5000),candidate=m.cold.index(x,y);
m.fields.rhL.fill(.98);m.fields.rhM.fill(.9);m.fields.el.fill(.9);m.fields.xiL.fill(100);m.fields.inflowFocus.fill(1);
const b={x,y:y+1000,nx:0,ny:-1,id:1,faceId:'test',feeds:{low:feed},inlets:{low:{x,y:y-5000}},relativeWinds:{low:{normalInflow:10}},rejections:{},paths:{low:[]},head:{Hhead:300,Qhead:900},geometricNormal:{x:0,y:-1},velocity:{x:0,y:-2}};
const coastBg={...bg,windAngle:25*Math.PI/180};assert.equal(m._jetExitAccess(x,y,coastBg).factor,0);
let gate=m._boundaryEventGate(b,x,y,coastBg);assert(gate.F>0,JSON.stringify(gate));assert(gate.evidence.focusedLift.coldFrontSite>0);assert(gate.evidence.lift.Hlift*.08<=gate.evidence.lift.energyLimit+1e-9);
m.config.disableCold=true;assert.equal(m._boundaryEventGate(b,x,y,coastBg).F,0);m.config.disableCold=false;
m.fields.rhL.fill(.6);assert.equal(m._boundaryEventGate(b,x,y,coastBg).F,0);m.fields.rhL.fill(.98);
m.h[candidate]=300;m.q[candidate]=900;assert.equal(m._boundaryEventGate(b,x,y,coastBg).F,0,'cold interior is never a new surface source');m.h[candidate]=m.q[candidate]=0;
// Lateral movement responds reversibly to cold outflow, remains bounded, and
// stores all memory in the cell/source records already saved by checkpoints.
const c={x,y,swayOffsetM:0},orig=m._coldCarrierAt;m._coldCarrierAt=()=>({relativeX:0,relativeY:8});m.fields.u.fill(12);m.fields.v.fill(0);
for(let j=0;j<30;j++){const a=m._cellSway(c,12,0,600);assert(Math.hypot(...a)<1.1);assert(Math.abs(c.swayOffsetM)<=2500);}const positive=c.swayOffsetM;assert(positive>1000);
m._coldCarrierAt=()=>({relativeX:0,relativeY:-8});for(let j=0;j<30;j++)m._cellSway(c,12,0,600);assert(c.swayOffsetM<-1000);
const clone=structuredClone(c);assert.deepEqual(m._cellSway(clone,12,0,600),m._cellSway(c,12,0,600));
const originalGate=m._persistentSourceGate;m._persistentSourceGate=()=>({F:1});const root={x,y,anchorX:x,anchorY:y,anchorAngle:0};for(let i=0;i<30;i++){const a={x:root.x,y:root.y};m._shiftTrainingSource(root,bg);assert(Math.hypot(root.x-a.x,root.y-a.y)<=1000.001);assert(Math.hypot(root.x-x,root.y-y)<=5000.001);}m._persistentSourceGate=()=>({F:0});const old={...root};m._shiftTrainingSource(root,{...bg,windAngle:0});assert.deepEqual(root,old);m._persistentSourceGate=originalGate;m._coldCarrierAt=orig;
console.log(JSON.stringify({pass:true,leeRejected:['Pingshan','Enping'],southerlyCoast:true,offshoreColdFrontGate:gate.F,dryAndColdInteriorRejected:true,lateralLimitsM:{cell:2500,root:5000,step:1000}}));
