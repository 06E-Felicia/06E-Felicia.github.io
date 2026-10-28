'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');
const drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;};
C.prepareBackendSync();
function make(){
 const m=new C.Model({geography:'idealized',preset:'coast',width:80000,height:80000,hours:6,seed:17,lambda0:.001});
 const f=m.fields;f.xiL.fill(0);f.xiM.fill(0);f.wTerrain.fill(0);f.wConvergence.fill(0);f.inflowFocus.fill(0);
 const k=m.env.index(42500,42500);f.xiL[k]=700;f.xiTerrain[k]=700;f.terrainRise[k]=900;f.wTerrain[k]=.3;f.inflowFocus[k]=1;f.rhL[k]=.96;f.el[k]=.9;
 return {m,k};
}
function tick(m){drain(m.initiate());const births=m.events.slice();m.cells=[];m.t+=C.DT;m.stats.steps++;return births;}
const {m}=make();tick(m);assert.equal(m.triggerSources.length,1,'first eligible random birth establishes one root');
const root={...m.triggerSources[0]},first=m.events[0];m.config.lambda0=0;
for(let n=0;n<8;n++)tick(m);
const descendants=m.events.filter(e=>e.triggerSourceId===root.id);
assert.equal(descendants.length,9,'one new tower each physical step without further stochastic proposals');
for(let i=0;i<descendants.length;i++){const e=descendants[i];assert.equal(e.x,first.x);assert.equal(e.y,first.y);assert.equal(e.t,first.t+i*600);}
assert.equal(new Set(descendants.map(e=>e.id)).size,9,'new cell IDs, not an indefinitely living old echo');
// Root phase/identity are physical continuation state, not reconstructed from a
// moving cell. Restore must produce exactly the same next birth and location.
const cp=m.checkpoint(),r=C.Model.restore(cp);tick(m);tick(r);assert.deepEqual(m.triggerSources,r.triggerSources);assert.deepEqual(m.events,r.events);
const missing=structuredClone(cp);delete missing.triggerSources;assert.throws(()=>C.Model.restore(missing),/triggerSources/);
const invalid=structuredClone(cp);invalid.triggerSources[0].x=-1;assert.throws(()=>C.Model.restore(invalid),/triggerSources/);
const closures={};
for(const cause of ['humidity','energy','lifting','cold']){
 const {m,k}=make();tick(m);m.config.lambda0=0;const before=m.stats.births,source=m.triggerSources[0];
 if(cause==='humidity')m.fields.rhL[k]=.6;
 if(cause==='energy')m.fields.el[k]=.1;
 if(cause==='lifting'){m.fields.xiL[k]=0;m.fields.wTerrain[k]=0;}
 if(cause==='cold'){const ck=m.cold.index(source.x,source.y);m.h[ck]=200;m.q[ck]=1000;}
 tick(m);assert.equal(m.stats.births,before,cause+' stops regeneration');assert.equal(m.triggerSources.length,0,cause+' closes root');closures[cause]='closed';
}
console.log(JSON.stringify({pass:true,source:root,consecutiveBirths:descendants.length,cadenceSeconds:600,closures,checkpoint:'exact continuation'}));
