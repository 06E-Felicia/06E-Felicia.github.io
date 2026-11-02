'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');
const m=Object.create(C.Model.prototype);m.config={organizedWarmSector:true,upstreamSourceBlocking:true,disableCold:true};m.terrain={fields:{signedDistance:[]}};m.forcing={sample:(_,x,y)=>y};m.triggerSources=[{id:'hk',x:10000,y:10000}];m._birthRegionAllowed=()=>true;m._coastInward=()=>({x:.6,y:.8});m._jetExitAccess=()=>({factor:.7,ascent:.2,windwardExposure:{factor:1,riseM:100}});m._trainingFeed=()=>({accessible:true,x:30000,y:0,rh:.98,energy:.9});const bg={windAngle:Math.PI/6,iL:2};
assert(m._upstreamSource(40000,25000,bg),'old exclusion covers another hill in the same coastal band');assert.equal(m._coastalPeer(40000,25000,bg)?.source.id,'hk');
m.triggerSources.push({id:'dapeng',x:40000,y:25000,trainGroupId:'hk'});assert.equal(m._coastalPeer(70000,25000,bg)?.source.id,'dapeng','successive coastal hills can form one group');assert.equal(m._coastalPeer(40000,70000,bg),null,'northern inland triggering is not reopened');
m._trainingFeed=()=>({accessible:false});assert.equal(m._coastalPeer(70000,25000,bg),null,'a source cannot borrow nonexistent moisture');m._trainingFeed=()=>({accessible:true,x:30000,y:0,rh:.98,energy:.9});
m.env={index:()=>0};m.fields={rhL:[.98],el:[.9],xiL:[600],xiTerrain:[300],xiConvergence:[300]};let depth=150;m.surfaceAccess=()=>({cold:true,warmAccessible:false,Q:depth*2,h:depth});m._columnSupplyFraction=()=>depth<450?.8:0;m._newInitiationMoisture=()=>1;m._liftAccess=()=>({factor:.7,parcelDisplacementM:600});
assert(m._focusedGate(70000,25000,0,bg,true).F>0,'independently lifted warm column can rise above a shallow neighboring pool');depth=1200;assert.equal(m._focusedGate(70000,25000,0,bg,true).F,0,'deep blocking pool still prevents new growth');depth=150;m._jetExitAccess=()=>({factor:0,ascent:0,windwardExposure:{factor:0,riseM:0}});assert.equal(m._focusedGate(70000,25000,0,bg,true).F,0,'lee or jet-ineligible terrain remains excluded');
console.log(JSON.stringify({pass:true,coastalChain:true,independentWarmLift:true,inlandDryDeepAndLeeRejected:true}));
// Run the production proposal/spacing/birth loop with three controlled hills.
// The initial hill's southern exclusion must not veto the two independent ones.
C.prepareBackendSync();const data=require('../scripts/record_vacation_replay.cjs').terrain();
function chain(open){
 const a=new C.Model({preset:'monsoon',geography:'real',seed:17},data);Object.assign(a.config,{width:90000,height:40000,lambda0:.001,jetExitControl:false});a.background=()=>bg;
 a.triggerSources=[{id:'first-hill',x:10000,y:10000,activated:0,lastBirth:0}];a._shiftTrainingSource=()=>{};a._persistentSourceGate=()=>({F:1});a._birthRegionAllowed=()=>true;a._coastInward=()=>({x:.6,y:.8});a._southernColdBarrier=()=>true;
 a.forcing={sample:(_,x,y)=>y};a._jetExitAccess=()=>({factor:.7,ascent:.2,windwardExposure:{factor:1,riseM:100}});a._trainingFeed=()=>({accessible:open,x:30000,y:0,rh:.98,energy:.9});
 a.gate=(x,y,layer)=>({F:!layer&&[40000,70000].some(cx=>Math.hypot(x-cx,y-25000)<2500)?1:0,source:'environment',power:50,coldPower:0,CIN:2,rh:.98,energy:.9,evidence:{}});
 for(const unused of a.initiate()){}return a;
}
const connected=chain(true);assert.equal(connected.triggerSources.length,3);assert(connected.triggerSources.slice(1).every(s=>s.trainGroupId==='first-hill'));assert.equal(chain(false).triggerSources.length,1,'no exemption without independent feed');console.log('PASS: three production roots share a coastal group; loss of feed blocks new roots.');
