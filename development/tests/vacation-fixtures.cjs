/* Short fixed-mesh/product and dense-reference checks, not formal weather acceptance. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const C=require('../../assets/scripts/vacation-model.js');
const drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;},sum=a=>a.reduce((s,v)=>s+v,0),json=x=>JSON.stringify(x);
const close=(a,b,tol=2e-12)=>assert(Math.abs(a-b)<=tol*Math.max(1,Math.abs(a),Math.abs(b)),`${a} != ${b}`);
const bytes=a=>Buffer.from(a.buffer,a.byteOffset,a.byteLength);
const cfg={geography:'idealized',preset:'monsoon',scenarioGroup:'coastal',quality:'standard',width:160000,height:160000,hours:6,seed:130363,coastalPrototype:{coastY:72000},coastalForcing:{offshoreRun:40000,mesoscale:false},controls:{flow:1,humidity:0}};
function physical(a,b){
 for(const key of Object.keys(a.fields))assert(bytes(a.fields[key]).equals(bytes(b.fields[key])),key);
 for(const [key,value] of Object.entries(a))if(ArrayBuffer.isView(value)&&!key.startsWith('_'))assert(bytes(value).equals(bytes(b[key])),key);
 for(const key of Object.keys(a.precipWater))assert(bytes(a.precipWater[key]).equals(bytes(b.precipWater[key])),key);
 for(const key of ['cells','events','lifeEvents','stats','ledger','heatBudget','convectiveEnergyBudget','coldMomentumLedger','frontTotals','windowTotals','triggerDiagnostics','supplyDiagnostics','frontDiagnostics','windowDiagnostics','forcingEvents','forcingEventStates','controls','targets','operationLog'])assert.equal(json(a[key]),json(b[key]),key);
}
function seedState(m,{dense=false}={}){
 const f=m.fields;f.wl.fill(.8*f.sl[0]);f.wm.fill(.7*f.sm[0]);f.el.fill(.9);f.em.fill(.9);f.xiL.fill(180);f.xiM.fill(40);drain(m.diagnoseEnvironment(false));
 let i=0;for(const a of Object.values(m.precipWater)){if(dense)a.fill(.02+.01*i);a[m.precip.index(m.precip.width/2,m.precip.height/2)]=.3+.04*i;i++;}
 m.precipWater.upper_core[m.precip.n-1]=.2;m.precipWater.lower_core[m.precip.n-1]=.1;f.ls[m.env.index(m.env.width/2,m.env.height/2)]=.05;
 m.cells=[{id:'mesh-actual',born:0,age:600,x:m.env.width/2,y:m.env.height/2,T:10800,major:8000,minor:5000,updraftArea:Math.PI*1000**2,starvedSeconds:0,supplyRatio:1,a:1,M:1e6,layer:0,source:'environment',angle:0,vx:0,vy:0,phase:0}];
 m.captureInitialState();
}
module.exports={physical,seedState};
