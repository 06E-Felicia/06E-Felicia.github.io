'use strict';
const assert=require('node:assert/strict');
const C=require('../../assets/scripts/vacation-model.js');
const {terrain}=require('../scripts/record_vacation_replay.cjs');
C.prepareBackendSync();
const data=terrain(),openings={west:[],south:[]},midpoints=[];
for(const start of ['west','south'])for(let seed=1;seed<=12;seed++){
 const config={preset:'monsoon',geography:'real',seed,windTurnStart:start,hours:72,quality:'low'};
 const m=new C.Model(config,data),angles=[];
 for(let h=0;h<=72;h++)angles.push(m._monsoonAngle(h*3600)*180/Math.PI);
 assert(angles.every(a=>a>=15-1e-8&&a<=75+1e-8));
 assert(angles.every((a,i)=>!i||(start==='west'?a>=angles[i-1]:a<=angles[i-1])),'slow turn keeps one direction');
 assert(Math.max(...angles.slice(1).map((a,i)=>Math.abs(a-angles[i])))<1.4,'no hourly jump');
 openings[start].push(angles[0]);midpoints.push((angles[36]-angles[0])/(angles[72]-angles[0]));
 const clone=new C.Model(config,data);assert.equal(clone._monsoonAngle(86400),m._monsoonAngle(86400),'same seed reproduces geometry and wind');
}
for(const values of Object.values(openings))assert(Math.max(...values)-Math.min(...values)>15,'opening angles spread within each regime');
assert(Math.max(...midpoints)-Math.min(...midpoints)>.15,'turn timing differs across seeds');
console.log(JSON.stringify({pass:true,realTerrainSeeds:24,openingDegrees:openings,midTurnProgressRange:[Math.min(...midpoints),Math.max(...midpoints)]}));
