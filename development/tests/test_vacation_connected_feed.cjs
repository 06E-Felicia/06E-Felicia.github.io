'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs');C.prepareBackendSync();
const drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;};
// Same finite cold layer, with independent changes to intake and inflow speed.
const m=new C.Model({preset:'coast',geography:'idealized',width:120000,height:120000,connectedTrainingFeed:true,lambda0:0});
m.fields.u.fill(0);m.fields.v.fill(12);m.fields.rhL.fill(.96);m.fields.el.fill(.9);m.fields.xiL.fill(1000);m.fields.wConvergence.fill(.8);m.fields.inflowFocus.fill(1);
const x=60000,y=60000,k=m.cold.index(x,y);m.h[k]=180;m.q[k]=270;
assert.equal(m.gate(x,y,0,m.background(),true).F,0,'new arbitrary surface births still vetoed inside cold air');
const source={id:'established',x,y,activated:0,lastBirth:0};
let feed=m._trainingFeed(x,y);assert(feed.accessible);assert(feed.headLift>0);assert(m._persistentSourceGate(source,m.background()).F>0,'established source survives shallow local cold with an open warm intake');
m.triggerSources=[source];m.t=600;drain(m.initiate());assert.equal(m.events.length,1);assert.equal(m.events[0].triggerSourceId,source.id);assert.equal(m.events[0].x,x);assert.equal(m.events[0].y,y);
// Supply must still come only from warm grid fractions; no cold water exemption.
const foot=drain(m.supplyFootprint(feed.x,feed.y,30000,18000,feed.angle));assert(foot.some(([,a,w])=>w<a));assert(foot.some(([,a,w])=>w>0));
m.fields.v.fill(3);assert.equal(m._trainingFeed(x,y).accessible,false,'weak inflow cannot overrun the cold head');
m.fields.v.fill(12);const barrier=m.cold.index(x,y-7500);m.h[barrier]=700;m.q[barrier]=2100;
assert.equal(m._trainingFeed(x,y).reason,'coldBarrier');assert.equal(m._persistentSourceGate(source,m.background()).F,0,'upstream blocking pool shuts persistent source');
m.h[barrier]=0;m.q[barrier]=0;m.fields.rhL.fill(.6);assert.equal(m._trainingFeed(x,y).reason,'dryInflow');
m.fields.rhL.fill(.96);m.h.fill(180);m.q.fill(270);assert.equal(m._trainingFeed(x,y).accessible,false,'no unlimited jump across a fully cold supply corridor');
m.h.fill(0);m.q.fill(0);m.fields.xiL.fill(80);m.t=3600;
assert.equal(m.gate(x,y,0,m.background(),true).F,0,'sub-LFC new parcel cannot start a new train');
assert(m._persistentSourceGate(source,m.background()).F>0,'fed established plume can maintain under a lower lifting threshold');
m.fields.wConvergence.fill(0);assert.equal(m._persistentSourceGate(source,m.background()).F,0,'plume memory cannot replace all resolved lifting');
const data=terrain(),real=new C.Model({preset:'monsoon',geography:'real',seed:20210520,coastalForcing:{exitOffset:10000}},data),f=real.fields;
f.rhL.fill(.98);f.el.fill(.95);f.xiL.fill(10000);f.wConvergence.fill(.8);f.inflowFocus.fill(1);
const response=[],spots={};
for(const from of [204,239]){
 const bg={...real.background(),windAngle:(270-from)*Math.PI/180},sum={west:0,delta:0,east:0};
 for(let j=0;j<real.env.ny;j++)for(let i=0;i<real.env.nx;i++){
  const x=(i+.5)*real.env.dx,y=(j+.5)*real.env.dx,lon=real._approxLongitude(x),region=lon<112.6?'west':lon>=114.7?'east':'delta';
  const gate=real.gate(x,y,0,bg,true);sum[region]+=gate.F;if(gate.F>0&&region!=='delta'&&!spots[region])spots[region]={id:region,x,y,activated:0,lastBirth:0};
 }
 if(from===204)assert(sum.west>sum.east*3&&sum.west>0,'P1: west Guangdong favored under SSW/SW');
 else assert(sum.east>sum.west*3&&sum.east>0,'P2: eastern coastal belt favored under WSW');
 assert(sum.delta>0,'delta remains possible in both regimes');response.push({from,...sum});
}
real.t=3600;for(const [region,from]of [['west',239],['east',204]])assert.equal(real._persistentSourceGate(spots[region],{...real.background(),windAngle:(270-from)*Math.PI/180}).F,0,'existing root also closes after direction switches away from its coastal belt');
console.log(JSON.stringify({pass:true,feed:'shallow own-footprint cooling survives; weak inflow, deep barrier and dry/fully cold intake stop',response}));
