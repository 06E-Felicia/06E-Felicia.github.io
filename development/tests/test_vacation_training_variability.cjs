'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
C.prepareBackendSync();const data=terrain(),project=proj4('EPSG:4326',data.meta.projection),xy=(lon,lat)=>{const p=project.forward([lon,lat]);return[p[0]+640000,p[1]+400000]};
const m=new C.Model({preset:'monsoon',geography:'real',seed:131,coastalForcing:{exitOffset:20000}},data);m.t=28800;
const rows=[];
for(const deg of [25,38,45]){const bg={...m.background(),windAngle:deg*Math.PI/180},a=m._jetExitAccess(...xy(116.29,23.03),bg);assert(a.factor>.1,'WSW must not be rejected like cross-range southerly flow');assert(a.ascent>.1,'reachable eastern windward slopes have sufficient lifting');rows.push({deg,factor:a.factor,ascent:a.ascent});}
const south={...m.background(),windAngle:72*Math.PI/180};assert.equal(m._jetExitAccess(...xy(116.29,23.03),south).factor,0,'cross-range southern inflow remains suppressed in the east');
const [x,y]=xy(111.75,22.06);m.background=()=>south;const c={triggerSourceId:'western-root',originX:x,originY:y,x,y,layer:0};assert.equal(m._trainingSupport(c),1,'an eligible source must not be dimmed by a second terrain-angle amplitude multiplier');c.y+=110000;assert.equal(m._trainingSupport(c),0,'downstream length limit still applies');
// Exercise motion at advancing simulation times, including checkpoint copying.
const bg={...south,windAngle:.7};m._persistentSourceGate=()=>({F:1});m._coldCarrierAt=()=>({relativeX:0,relativeY:0});const root={id:'meander',x,y,anchorX:x,anchorY:y,anchorAngle:.7};let lo=Infinity,hi=-Infinity;
for(let t=0;t<18000;t+=600){m.t=t;const before={...root};m._shiftTrainingSource(root,bg);assert(Math.hypot(root.x-before.x,root.y-before.y)<=1000.001);const offset=-(root.x-x)*Math.sin(.7)+(root.y-y)*Math.cos(.7);lo=Math.min(lo,offset);hi=Math.max(hi,offset);const copy=structuredClone(root);m._shiftTrainingSource(copy,bg);const other=structuredClone(root);m._shiftTrainingSource(other,bg);assert.deepEqual(copy,other);}
assert(hi-lo>3000,'a train must actually sway both ways, not merely approach a static offset');
m.triggerSources=[{id:'parent',x,y}];assert.equal(m._southernRelaySource(x+18000,y+2000,bg)?.id,'parent','eastward front can inherit a nearby train');assert.equal(m._southernRelaySource(x,y+10000,bg),null,'pure northern flank cannot bypass upstream blocking');assert.equal(m._southernRelaySource(x+80000,y,bg),null);
const first=m._directionalJetShift(bg);m.config.seed=17;assert(Math.hypot(first.x-m._directionalJetShift(bg).x,first.y-m._directionalJetShift(bg).y)>10000,'seed changes actual jet target location');
console.log(JSON.stringify({pass:true,easternWSW:rows,rootSwayRangeM:hi-lo,nearSourceSupport:1,eastwardRelayEligible:true}));

for(const seed of [17,131,920]){m.config.seed=seed;const west=m._rainPolePreference(...xy(111.85,22.06)),east=m._rainPolePreference(...xy(115.45,22.86)),gap=m._rainPolePreference(...xy(113.6,22.4));assert(west>gap&&east>gap,'both preferred rain regions survive seed variation');}

// Moving precipitating cores can pass their cold-front lineage onward beyond
// the stationary root's immediate neighborhood; dry/old cells cannot do so.
m.cells=[{triggerSourceId:'parent',x:x+60000,y,age:1800,a:.5}];assert.equal(m._southernRelaySource(x+66000,y-6000,bg)?.id,'parent');m.cells[0].a=0;assert.equal(m._southernRelaySource(x+66000,y-6000,bg),null);
