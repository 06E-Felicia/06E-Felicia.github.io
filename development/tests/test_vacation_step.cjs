'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),V=require('../../assets/scripts/vacation-version.js');
const drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;};
const sum=a=>a.reduce((s,x)=>s+x,0),near=(a,b)=>assert(Math.abs(a-b)<1e-10*Math.max(1,Math.abs(a),Math.abs(b)),`${a} != ${b}`);
C.prepareBackendSync();assert.equal(C.DT,600);
const base={geography:'idealized',preset:'coast',width:80000,height:80000,hours:6,seed:17,disableBirths:true,disableCold:true};
// Exact two-reservoir cascade: with identical 300 s fall times, U=e^-2,
// L=2e^-2 after a 600 s step. Sequentially draining the arriving water gives
// the wrong lower reservoir and suppresses its radar reflectivity.
const states=[];
for(const computeBackend of ['js','wasm']){
  const m=new C.Model({...base,computeBackend});
  for(const k of ['u','v','um','vm'])m.fields[k].fill(0);
  m.fields.rhL.fill(1);m.fields.rhM.fill(1);
  const k=m.precip.index(40000,40000);m.precipWater.upper_core[k]=1;m.captureInitialState();drain(m.release());
  near(m.precipWater.upper_core[k],Math.exp(-2));near(m.precipWater.lower_core[k],2*Math.exp(-2));
  near(sum(m.rainStep)*m.rain.area,m.precip.area*(1-3*Math.exp(-2)));near(m.audit().activityResidual,0);
  const p=drain(m.projectProducts());near(sum(p.rainRate)*p.grid.area/6,sum(m.rainStep)*m.rain.area);
  states.push(m);assert.equal(m.interval,600);
}
for(const k of Object.keys(states[0].precipWater))assert.deepEqual(states[0].precipWater[k],states[1].precipWater[k]);
// Core time, checkpoints and product cadence all use the physical 600 s step.
const m=new C.Model(base);m.step();assert.equal(m.t,600);assert.equal(m.stats.steps,1);const cp=m.checkpoint();assert(V.checkpointPreflight(cp).eligible);const r=C.Model.restore(cp);m.step();r.step();assert.equal(m.t,1200);for(const k of Object.keys(m.fields))assert.deepEqual(m.fields[k],r.fields[k]);
const bad=structuredClone(cp);bad.t=30;assert.equal(V.checkpointPreflight(bad).eligible,false);
console.log('PASS 600 s physical step, analytic cascade, JS/WASM identity, rain-rate units and checkpoint continuation');
// A continuously released source must retain more upper/lower condensate than
// a pulse deposited at the beginning. Test the independent analytic solution.
for(const computeBackend of ['js','wasm']){
 const m=new C.Model({...base,computeBackend});for(const k of ['u','v','um','vm'])m.fields[k].fill(0);m.fields.rhL.fill(1);m.fields.rhM.fill(1);
 m.cells=[{id:'source',born:0,activeStepSeconds:600,age:1200,x:40000,y:40000,angle:0,major:2000,minor:1500,updraftArea:Math.PI*1000**2,M:1e8,a:1,supplyRatio:1,convectivePhaseEnergyJ:0}];m.captureInitialState();drain(m.release());
 const q=m.cells[0].releasedKgThisStep,u=sum(m.precipWater.upper_core)*m.precip.area,l=sum(m.precipWater.lower_core)*m.precip.area;
 near(u/q,(1-Math.exp(-2))/2);near(l/q,(1-3*Math.exp(-2))/2);near(m.stats.sources.coreGround/q,2*Math.exp(-2));near(m.audit().activityResidual,0);
}
console.log('PASS continuous core source analytic upper/lower storage and rainfall, both backends');
