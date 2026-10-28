'use strict';
const assert=require('node:assert/strict'),R=require('../../assets/scripts/vacation-random.js'),C=require('../../assets/scripts/vacation-model.js'),fs=require('node:fs');
const mem=new Map(),storage={getItem:k=>mem.get(k),setItem:(k,v)=>mem.set(k,v)};let n=0;const sequence=Array.from({length:100},()=>R.nextWindStart(storage,()=>C.hash(71,'bag',n++)&1));
for(let i=0;i<sequence.length;i+=2)assert.notEqual(sequence[i],sequence[i+1]);for(let i=2;i<sequence.length;i++)assert(!sequence.slice(i-2,i+1).every(x=>x===sequence[i]));
mem.set('vacation-wind-opening-bag','broken');assert(['west','south'].includes(R.nextWindStart(storage,()=>1)));
let west=0;for(let seed=0;seed<10000;seed++)if(C.random(C.hash(seed,'three-day-wind-turn'))()<.5)west++;assert(west>4700&&west<5300,'seeded opening itself is not south-biased');
for(const windTurnStart of ['west','south']){const m=new C.Model({preset:'monsoon',geography:'idealized',width:120000,height:120000,slowMonsoonTurn:true,seed:17,windTurnStart});const from=270-m._monsoonAngle(0)*180/Math.PI,to=270-m._monsoonAngle(72*3600)*180/Math.PI;assert(windTurnStart==='west'?from>245&&to<205:from<205&&to>245);}
C.prepareBackendSync();const data=require('../scripts/record_vacation_replay.cjs').terrain(),admitted=[];
for(const seed of [1,17,131,20210520])for(const windTurnStart of ['west','south']){const m=new C.Model({preset:'monsoon',geography:'real',seed,windTurnStart},data),angle=m._monsoonAngle(0)*180/Math.PI;assert(windTurnStart==='west'?angle<=35:angle>=55,'geographic admission cannot reverse chosen opening');admitted.push({seed,windTurnStart,angle});}
const html=fs.readFileSync(require.resolve('../../Vacation.html'),'utf8'),ui=fs.readFileSync(require.resolve('../../assets/scripts/vacation.js'),'utf8');assert(!html.includes('value="200"'));assert(html.includes('value="600" selected'));assert(ui.includes("const choices=['radar','monsoon']"));
console.log(JSON.stringify({pass:true,seedSample:{west,south:10000-west},balancedDraws:sequence.slice(0,12),admitted,ui:'600x default; radar/monsoon; no 200x'}));
