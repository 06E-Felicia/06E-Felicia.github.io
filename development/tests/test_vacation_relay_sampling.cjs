'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');
const m=Object.create(C.Model.prototype);m.config={organizedWarmSector:true,seed:131,width:200000,height:100000};m.terrain={meta:{center:[113.5,22.5]}};m.env={index:()=>0};m.fields={rhL:[.88],rhM:[.72]};m._approxLongitude=x=>x;m._monsoonAngle=()=>Math.PI/3;let cold=false;m.surfaceAccess=()=>({inDomain:true,cold,h:200});const south={windAngle:65*Math.PI/180},west={windAngle:25*Math.PI/180};
assert.equal(m._initiationSequenceWeight(112,0,south),1);
assert(m._initiationSequenceWeight(113.5,0,south)<.2,'delta spontaneous birth starts below western pole');cold=true;
assert(m._initiationSequenceWeight(113.5,0,south)>.8,'approaching cold edge promotes delta relay');cold=false;m.fields.rhL[0]=.98;m.fields.rhM[0]=.92;
assert(m._initiationSequenceWeight(113.5,0,south)>.99,'fully moistened delta is independently eligible');assert.equal(m._initiationSequenceWeight(113.5,0,west),1);
m._southernRelaySource=()=>({id:'existing'});const b={x:0,y:0,head:{Hhead:240},geometricNormal:{x:0,y:-1}};assert.equal(m._frontSamplingWidth(b,south),12000);b.head.Hhead=40;assert.equal(m._frontSamplingWidth(b,south),2000);b.head.Hhead=240;b.geometricNormal.y=1;assert.equal(m._frontSamplingWidth(b,south),2000);b.geometricNormal.y=-1;m._southernRelaySource=()=>null;assert.equal(m._frontSamplingWidth(b,south),2000);
m.config.coastalWindParameters={exitLength:20000,sigmaJet:100000};m._jetCoastWindow=()=>1;let distance=0;m._jetCoordinates=()=>({along:distance,exit:0,cross:0});assert.equal(m._relayJetWeight(0,0,west),1);distance=90000;assert(m._relayJetWeight(0,0,west)<.02,'distant deceleration zone suppresses sampled relay');
// An invalid full sway step can still reach a valid shorter piece of foothill.
m.t=0;m.background=()=>south;m._coldCarrierAt=()=>({relativeX:0,relativeY:0});m._trainingMeander=()=>1;m._persistentSourceGate=p=>({F:Math.hypot(p.x,p.y)<=600?1:0});m.env.index=()=>0;const source={id:'root',x:0,y:0,anchorX:0,anchorY:0,anchorAngle:south.windAngle};m._shiftTrainingSource(source,south);assert(Math.hypot(source.x,source.y)>400&&Math.hypot(source.x,source.y)<600);
console.log(JSON.stringify({pass:true,moistureAndFrontSequencing:true,warmWedgeMaxKm:12,remoteJetSuppressed:true,partialWindwardSway:true}));
