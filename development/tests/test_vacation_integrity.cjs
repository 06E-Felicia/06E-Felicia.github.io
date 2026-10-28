/* Checkpoint/projection input integrity only; bounded developer fixtures, no weather acceptance. */
'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{seedState,physical}=require('./vacation-fixtures.cjs');
function run(){
 const result={model:C.VERSION,scope:'Short positive/negative input and resume fixtures only; no formal weather or browser acceptance.'},cfg={geography:'idealized',preset:'coast',width:80000,height:80000,hours:6,seed:42};
 let positive=0;for(const quality of ['low','standard','high'])for(const mechanismEvidence of [false,true]){
   const m=new C.Model({...cfg,quality,mechanismEvidence});seedState(m);const k=m.cold.index(40000,40000);m.h[k]=100;m.q[k]=200;m.captureInitialState();for(let i=0;i<2;i++)m.step();
   const c=m.checkpoint(),before=structuredClone(c),r=C.Model.restore(c);assert.deepEqual(c,before);assert.deepEqual(r.checkpoint(),c);
   for(let i=0;i<2;i++){m.step();r.step();physical(m,r);}positive++;if(quality==='standard'&&mechanismEvidence)result._sample=c;
 }
 const c=result._sample;delete result._sample;assert(c.arrays.precip_upper_core.some(v=>v>0));assert(c.arrays.q.some(v=>v>0));
 const rejected=[],reject=(name,mutate,pattern=/检查点/)=>{const damaged=structuredClone(c);mutate(damaged);const before=structuredClone(damaged);assert.throws(()=>C.Model.restore(damaged),pattern,name);assert.deepEqual(damaged,before,name+' mutated its input');rejected.push(name);};
 const required=Object.keys(c.arrays).filter(k=>!k.startsWith('mechanism_'));
 for(const key of required){reject('missing arrays.'+key,x=>delete x.arrays[key],new RegExp('arrays\\.'+key));reject('NaN arrays.'+key,x=>{x.arrays[key][0]=NaN;},new RegExp('arrays\\.'+key));}
 for(const value of [Infinity,-Infinity])for(const key of ['field_wl','q','precip_upper_core','rainTotal','Px'])reject(String(value)+' '+key,x=>{x.arrays[key][0]=value;});
 reject('short array',x=>{x.arrays.q=x.arrays.q.slice(1);},/尺寸/);reject('ordinary Array unsupported',x=>{x.arrays.field_wl=Array.from(x.arrays.field_wl);},/Float64Array/);reject('Float32 unsupported',x=>{x.arrays.q=Float32Array.from(x.arrays.q);},/Float64Array/);
 for(const key of ['heatBudget','ledger','convectiveEnergyBudget','coldMomentumLedger','stats','controls','targets','cells','events','lifeEvents','forcingEvents','forcingEventStates','frontTotals','windowTotals'])reject('missing '+key,x=>delete x[key]);
 for(const [name,mutate]of [
   ['missing low water balance',x=>delete x.ledger.vaporL],['missing heat initial',x=>delete x.heatBudget.initial],['missing heat flow map',x=>delete x.heatBudget.flows],
   ['bad heat flow scalar',x=>{x.heatBudget.flows.bad='4';}],['negative flow',x=>{x.ledger.vaporL.flows['bad:in']=-1;}],['missing energy source',x=>delete x.convectiveEnergyBudget.sourceJ],['nonfinite heat',x=>{x.heatBudget.in=Infinity;}],
   ['missing cold initial x',x=>delete x.coldMomentumLedger.initial.x],['step mismatch',x=>{x.stats.steps++;}],['fractional steps',x=>{x.stats.steps=.5;}],['off-boundary time',x=>{x.t++;}],['negative time',x=>{x.t=-30;}],['time nonfinite',x=>{x.t=NaN;}],
   ['unbalanced water ledger',x=>{x.ledger.vaporL.initial+=1e10;}],['unbalanced initial water',x=>{x.initialWater+=1e10;}],['unbalanced heat',x=>{x.heatBudget.initial+=1e15;}],['unbalanced energy',x=>{x.convectiveEnergyBudget.sourceJ+=1e12;}],['missing flow history',x=>{x.ledger.vaporL.flows={};}],
   ['missing cell energy',x=>delete x.cells[0].convectivePhaseEnergyJ],['nonfinite cell energy',x=>{x.cells[0].convectivePhaseEnergyJ=NaN;}],['missing cell pulse',x=>delete x.cells[0].pulse],['missing energy-step source',x=>delete x.cells[0].convectiveEnergyStep.sourceJ],['missing actual supply',x=>delete x.cells[0].suppliedKgThisStep],
   ['duplicate actual ID',x=>{x.cells.push(structuredClone(x.cells[0]));}],['unknown array',x=>{x.arrays.unrecognized=new Float64Array(1);}],['missing saved config',x=>delete x.config.coldDampingSeconds],['invalid saved config',x=>{x.config.controls.flow=NaN;}],
   ['mechanism length',x=>{const key=Object.keys(x.arrays).find(k=>k.startsWith('mechanism_'));x.arrays[key]=x.arrays[key].slice(1);}],['invalid optional diagnostic',x=>{x.supplyDiagnostics.global.suppliedKg=Infinity;}],['optional diagnostic wrong type',x=>{x.supplyDiagnostics='bad';}],['missing event energy mode',x=>{if(x.events.length)delete x.events[0].convectiveHeating;else x.events.push({id:'bad',t:0,x:0,y:0});}]
 ])reject(name,mutate);
 const optional=structuredClone(c);for(const key of ['triggerDiagnostics','supplyDiagnostics','frontDiagnostics','windowDiagnostics','coldKinematicDiagnostics','convectiveEnergyDiagnostics','forcingInterpolation'])delete optional[key];for(const key of Object.keys(optional.arrays))if(key.startsWith('mechanism_'))delete optional.arrays[key];
 const input=structuredClone(optional),without=C.Model.restore(optional),complete=C.Model.restore(c);assert.deepEqual(optional,input);for(let i=0;i<2;i++){without.step();complete.step();physical(without,complete);}
 const order=structuredClone(c);for(const owner of [order,order.config])for(const key of ['physicsMesh','productMesh'])owner[key]=Object.fromEntries(Object.entries(owner[key]).reverse());assert.deepEqual(C.Model.restore(order).physicsMesh,C.Model.restore(c).physicsMesh);
 for(const quality of ['low','standard','high']){const zero=new C.Model({...cfg,quality});assert.deepEqual(C.Model.restore(zero.checkpoint()).checkpoint(),zero.checkpoint());}
 const source=new C.Grid(4000,4000,2000),target=new C.Grid(4000,4000,4000),values=Float64Array.from([1,2,3,4]);assert.equal(C.areaMean(values,source,target)[0],2.5);
 let projectionRejected=0;const bad=(s,t)=>{assert.throws(()=>C.areaMean(values,s,t),/投影|网格/);projectionRejected++;};
 for(const area of [0,-1,1,NaN,Infinity,-Infinity,undefined,target.area+1])bad(source,{...target,area});bad({...source,area:1},target);
 for(const patch of [{nx:1.5},{nx:'1'},{ny:0},{n:Infinity},{n:2},{width:NaN},{dx:Infinity},{origin:null},{origin:[0]},{origin:[0,0,0]},{origin:[NaN,0]},{origin:[0,Infinity]},{origin:[1,0]}])bad(source,{...target,...patch});
 const shifted={...source,origin:[-2000,1000]},shiftedTarget={...target,origin:[-2000,1000]};assert.equal(C.areaMean(values,shifted,shiftedTarget)[0],2.5);
 result.positiveWetQualityMechanismPairs=positive;result.requiredPhysicalArrays=required.length;result.deletedEveryRequiredArray=true;result.nonfiniteEveryRequiredArray=true;result.rejectedCheckpointCases=rejected;result.optionalCacheRemovalResumeSteps=2;result.nativeArrayType='Float64Array only';result.invalidProjectionCases=projectionRejected;result.inputMutation=false;
 console.log(JSON.stringify(result,null,2));console.log('Checkpoint completeness and projection input probes passed; formal acceptance belongs to design.');return result;
}
if(require.main===module)run();module.exports={run};
