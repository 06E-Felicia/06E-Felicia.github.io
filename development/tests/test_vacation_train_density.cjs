'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');
const m=Object.create(C.Model.prototype);m.config={organizedWarmSector:true,stratiformOutflow:true};m.triggerSources=[{id:'a',x:50000,y:50000}];const bg={windAngle:0};assert(m._competingTriggerSource(70000,50000,bg));assert(m._competingTriggerSource(50000,64000,bg));assert(!m._competingTriggerSource(80000,50000,bg),'separate downstream lifting point remains possible');assert(!m._competingTriggerSource(50000,70000,bg),'independent lane retained');assert(!m._competingTriggerSource(50000,44000,bg,true),'verified cold-front relay retained');
m.precip={n:1};m.env={index:()=>0};m.fields={um:[12],vm:[0]};m.precipWater={qa:[]};m.stats={sources:{detrained:0}};m.recordWater=()=>{};m._buffers=new Map();const deposits=[];m.depositPrecip=function*(array,x,y,major,minor,angle,mass,kind){deposits.push({x,y,major,minor,angle,mass,kind});};
const cell={M:100000,activeStepSeconds:600,suppliedKgThisStep:30000,a:.8,supplyRatio:1,age:1800,phase:0,major:7000,minor:7000,x:30000,y:30000,angle:0,updraftArea:Math.PI*5000**2};m.cells=[cell];const it=m.release();for(let next=it.next();!next.done&&next.value!=='qa_import';next=it.next()){}
const cores=deposits.filter(d=>d.kind==='core');assert.equal(cores.length,4);assert(cores.every(d=>d.major>d.minor*1.5),'core elongation follows wind, not crosswind');assert(Math.abs(deposits.reduce((n,d)=>n+d.mass,0)+cell.M-100000)<1e-8,'rotation preserves water');assert(Math.abs(cell.subcores.reduce((n,d)=>n+d.weight,0)-1)<1e-12);
console.log(JSON.stringify({pass:true,duplicateRootsThinned:true,relayAndIndependentLanesKept:true,alongWindCoreElongation:true,releaseMassConserved:true}));

assert(!m._competingTriggerSource(70000,50000,bg,false,true),'verified separate hill survives ordinary exclusion');
assert(m._competingTriggerSource(58000,50000,bg,false,true),'same-hill duplicates still rejected');
const fresh={thermalPotential:.8,supplyRatio:1,a:.8,starvedSeconds:0};
assert.equal(m._updraftAreaTarget(fresh),m._updraftAreaTarget({...fresh,a:.3,trainingSupport:.4}),'along-track damping applies once at effective area');
assert(m._updraftAreaTarget({...fresh,supplyRatio:.2})<m._updraftAreaTarget(fresh)*.2,'actual water starvation still contracts the plume');
assert.equal(m._updraftAreaTarget({...fresh,starvedSeconds:600}),Math.PI*1000**2);

const coast=Object.create(C.Model.prototype);coast.config={organizedWarmSector:true,height:100000};coast.terrain={meta:{center:[112,22]},fields:{signedDistance:[]}};coast._approxLongitude=()=>112;
let depth=35000;coast.forcing={sample:()=>depth};
assert.equal(coast._coastalFoothillAccess(0,50000,{windAngle:Math.PI/6}),0,'westerly western interior excluded');
assert.equal(coast._coastalFoothillAccess(0,50000,{windAngle:Math.PI/3}),1,'southerly western mountain access preserved');
depth=5000;assert.equal(coast._coastalFoothillAccess(0,50000,{windAngle:Math.PI/6}),1,'western coastal exit remains available');
