'use strict';
// Paired intervention: identical moving surface-fed cells and thermodynamics;
// only resolved cold coverage differs. Disable pulse ageing to isolate supply.
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');
const drain=it=>{while(!it.next().done){}};C.prepareBackendSync();
const results=[];
for(const computeBackend of ['js','wasm']){
 const models=[false,true].map(cold=>{
  const m=new C.Model({geography:'idealized',preset:'monsoon',width:160000,height:160000,hours:6,seed:17,computeBackend,disableBirths:true,cellLifecycle:'legacy'}),f=m.fields;
  for(let i=0;i<m.env.n;i++){f.wl[i]=.9*f.sl[i];f.wm[i]=.8*f.sm[i];f.rhL[i]=.9;f.rhM[i]=.8;f.el[i]=.9;f.em[i]=.9;f.u[i]=8;f.v[i]=0;f.um[i]=10;f.vm[i]=0;}
  m.cells=[{id:'paired',born:0,age:600,x:80000,y:80000,T:10800,major:8000,minor:5000,updraftArea:Math.PI*1000**2,starvedSeconds:0,supplyRatio:1,a:1,M:1e8,layer:0,source:'environment',angle:0,vx:10,vy:0,phase:0,convectivePhaseEnergyJ:0}];
  if(cold){m.h.fill(200);m.q.fill(400);}m.captureInitialState();return m;
 });
 const [warm,cold]=models;models.forEach(m=>{drain(m.evolveCells());m.t+=600;});const a=warm.cells[0],b=cold.cells[0];
 assert.equal(b.suppliedLKgThisStep,0);assert(b.suppliedMKgThisStep>0,'elevated feed remains possible');
 assert(b.instantSupplyRatio<a.instantSupplyRatio*.5,'missing low feed is not replaced by middle feed');assert(b.a<a.a*.2,'activity responds to cold cutoff');
 assert.equal(a.x,b.x,'do not slow storms to create training');assert.equal(a.x,86000);
 const first={computeBackend,warmSupply:a.instantSupplyRatio,coldSupply:b.instantSupplyRatio,warmActivity:a.a,coldActivity:b.a};
 for(let i=0;i<2;i++)models.forEach(m=>{drain(m.evolveCells());m.t+=600;});
 assert.equal(warm.cells.length,1);assert.equal(cold.cells.length,0);assert.equal(cold.lifeEvents.at(-1).reason,'thermal_or_updraft_support_lost');
 results.push({...first,coldDeathSeconds:cold.lifeEvents.at(-1).t});
}
assert.deepEqual({...results[0],computeBackend:null},{...results[1],computeBackend:null});
console.log(JSON.stringify({pass:true,intervention:'surface cold coverage only; pulse aging disabled',results},null,2));
