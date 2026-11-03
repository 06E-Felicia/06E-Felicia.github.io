'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');
C.prepareBackendSync();
const m=new C.Model({preset:'coast',geography:'idealized',width:240000,height:240000,trainingInflowFan:true,connectedTrainingFeed:true});
Object.assign(m.config,{organizedWarmSector:true,monsoon925:true,initiationModel:'focused_lift',jetExitControl:false});
const x=120000,y=150000,bg={...m.background(),iL:2};
m.fields.u.fill(0);m.fields.v.fill(13);m.fields.rhL.fill(.98);m.fields.rhM.fill(.9);m.fields.el.fill(.95);m.fields.em.fill(.9);m.fields.xiL.fill(1000);m.fields.xiM.fill(1000);m.fields.wConvergence.fill(.8);m.fields.inflowFocus.fill(1);
m._birthRegionAllowed=()=>true;m._newInitiationMoisture=()=>1;m._liftAccess=()=>({factor:1,parcelDisplacementM:1000});
const source={id:'north',x,y,activated:0,lastBirth:0};
function strip(openSide=false,edge=110000){
 m.h.fill(0);m.q.fill(0);
 for(let k=0;k<m.cold.n;k++){
  const px=(k%m.cold.nx+.5)*m.cold.dx,py=(Math.floor(k/m.cold.nx)+.5)*m.cold.dx;
  if(py>=90000&&py<=110000&&(!openSide||px>=edge)){m.h[k]=1200;m.q[k]=3600;}
 }
}
assert(m._trainingFeed(x,y).accessible);
assert(m._focusedGate(x,y,0,bg,true).F>0);
assert(m._focusedGate(x,y,1,bg,true).F>0);
strip();
assert(m.surfaceAccess(x,y).warmAccessible,'target still looks locally warm');
assert(m.surfaceAccess(x,y-10000).warmAccessible,'old early-return donor still warm');
assert.equal(m._trainingFeed(x,y).accessible,false,'farther upstream barrier closes all fan paths');
assert.equal(m._focusedGate(x,y,0,bg,true).F,0,'stored local moisture cannot restart low-level convection');
assert.equal(m._focusedGate(x,y,1,bg,true).F,0,'mid-level proposal cannot bypass severed warm-sector supply');
assert.equal(m._persistentSourceGate(source,bg).F,0,'persistent root also loses supply');
const inlet={x,y:y-5000},b={x,y:y-1000,nx:0,ny:1,id:1,faceId:'north',feeds:{low:m.env.index(inlet.x,inlet.y)},inlets:{low:inlet},relativeWinds:{low:{normalInflow:10}},rejections:{},paths:{low:[]},head:{Hhead:300,Qhead:900},geometricNormal:{x:0,y:1},velocity:{x:0,y:20}};
assert.equal(m._boundaryEventGate(b,x,y,bg).F,0,'advancing northern cold front cannot bypass supply check');
strip(true,80000);assert.equal(m._trainingFeed(x,y).accessible,false,'a far lateral gap cannot supply fictitious diagonal flow behind a wide cold strip');
assert.equal(m._trainingFeed(x,y,false,true).accessible,false,'even established plumes cannot bypass a province-scale barrier');
strip(true,90000);assert.equal(m._trainingFeed(x,y).accessible,false,'new northern root cannot borrow a distant flank');assert(m._persistentSourceGate(source,bg).F>0,'established plume can retain its broader connected warm flank');
strip(true);assert(m._boundaryEventGate(b,x,y,bg).F>0,'same warm front succeeds when its lateral supply opens');assert(m._persistentSourceGate(source,bg).F>0,'same source resumes when supply opens');assert(m._trainingFeed(x,y).accessible,'genuinely connected lateral inlet survives');assert(m._focusedGate(x,y,0,bg,true).F>0);
m.h.fill(150);m.q.fill(225);assert(m._trainingFeed(x,y).accessible,'shallow own-pool cooling does not cut the warm column');
m.h.fill(0);m.q.fill(0);
for(let k=0;k<m.env.n;k++){const py=(Math.floor(k/m.env.nx)+.5)*m.env.dx;if(py>=90000&&py<=110000)m.fields.v[k]=-4;}
assert.equal(m._trainingFeed(x,y).accessible,false,'reversed upstream flow is not a connected monsoon');
console.log(JSON.stringify({pass:true,warmPocketBehindBarrierRejected:true,allBirthChannelsBlocked:true,openFlankAndShallowColumnPreserved:true,reversedFlowRejected:true}));
