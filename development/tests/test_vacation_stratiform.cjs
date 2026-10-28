'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');C.prepareBackendSync();
const drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;},sum=a=>a.reduce((s,x)=>s+x,0);
const result=[];
for(const computeBackend of ['js','wasm'])for(const stratiformOutflow of [false,true]){
 const m=new C.Model({preset:'coast',geography:'idealized',width:160000,height:160000,disableBirths:true,disableCold:true,computeBackend,stratiformOutflow});
 for(const k of ['u','v','um','vm'])m.fields[k].fill(0);m.cu.fill(0);m.cv.fill(0);m.eu.fill(0);m.ev.fill(0);m.fields.rhL.fill(1);m.fields.rhM.fill(1);
 const P=m.precipWater;
 // Dilute real condensate below the old autoconversion cutoff: the former
 // reservoir cannot produce any stratiform radar return or ground rain here.
 for(let k=0;k<m.precip.n;k++){const x=(k%m.precip.nx+.5)*m.precip.dx,y=(Math.floor(k/m.precip.nx)+.5)*m.precip.dx;if(Math.hypot(x-80000,y-80000)<25000)P.qa[k]=.08;}
 m.captureInitialState();const initial=sum(P.qa)*m.precip.area;let echoAbove5DbzKm2=0;
 for(let n=0;n<12;n++){drain(m.release());const products=drain(m.projectProducts());let area=0;for(const z of products.compositeZ)if(z>=10**.5)area+=m.precip.area/1e6;echoAbove5DbzKm2=Math.max(echoAbove5DbzKm2,area);}
 const retained=Object.values(P).reduce((s,a)=>s+sum(a)*m.precip.area,0),audit=m.audit();assert(audit.activityResidual<1e-9);assert(Math.abs(initial-retained-m.stats.ground-m.stats.outflow)<initial*1e-10);assert.equal(sum(P.upper_core)+sum(P.lower_core),0,'no fabricated convective core');assert(Object.values(P).every(a=>a.every(x=>Number.isFinite(x)&&x>=0)));
 result.push({computeBackend,stratiformOutflow,echoAbove5DbzKm2,groundKg:m.stats.ground,retainedKg:retained,initialKg:initial,residual:audit.activityResidual});
}
for(let i=0;i<2;i++){const a=result[i],b=result[i+2];assert.equal(a.echoAbove5DbzKm2,b.echoAbove5DbzKm2);assert(Math.abs(a.groundKg-b.groundKg)<1e-10*a.initialKg);}
assert.equal(result[0].groundKg,0);assert(result[1].groundKg>0);assert(result[1].echoAbove5DbzKm2>1000);
// Diffusion broadens a finite patch while conserving its exact inventory.
const m=new C.Model({preset:'coast',geography:'idealized',width:160000,height:160000,stratiformOutflow:true}),k=m.precip.index(80000,80000);m.precipWater.qa[k]=1;m.precipWater.upper_core[k]=2;const before=sum(m.precipWater.qa);for(let i=0;i<6;i++)drain(m._spreadStratiform());assert(Math.abs(sum(m.precipWater.qa)-before)<1e-12);assert.equal(m.precipWater.upper_core[k],2);assert(m.precipWater.qa.filter(v=>v>.0001).length>100);
console.log(JSON.stringify({pass:true,result}));
