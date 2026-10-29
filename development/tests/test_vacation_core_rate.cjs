'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');
const m={config:{organizedWarmSector:true},rain:{nx:2,dx:1000,area:1e6},precip:{area:4e6,index:()=>0},activeRain:new Set([0,1]),rainStep:Float64Array.from([40,10]),convectiveStep:Float64Array.from([39,9]),precipWater:{lower_core:new Float64Array(1)},stats:{ground:50e6,sources:{coreGround:48e6}},ledger:{core:{out:48e6,flows:{'ground:out':48e6}}}};
const before=m.stats.ground;m.water=()=>m.precipWater.lower_core[0]*4e6;
C.Model.prototype._limitCoreRain.call(m);
assert(Math.abs(m.rainStep[0]*6-100)<1e-8);assert.equal(m.rainStep[1],10);assert(Math.abs(m.stats.ground+m.water()-before)<1e-5);assert(Math.abs(m.ledger.core.out-m.stats.sources.coreGround)<1e-5);assert(m.precipWater.lower_core[0]>0);
const returned=m.stats.coreFalloutDeferred;C.Model.prototype._limitCoreRain.call(m);assert.equal(m.stats.coreFalloutDeferred,returned);
console.log('PASS: 100 mm/h core fallout limit, unaffected moderate rain, retained condensate and conserved ground/source ledger.');
