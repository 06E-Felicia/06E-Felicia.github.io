'use strict';
const assert=require('node:assert/strict'),{Game,schedule,END}=require('../../assets/scripts/vacation-game.js');
function run(choices,reds,repents={}){const g=new Game();let prompts=0;for(let t=0;t<=END;t+=600){g.update(t,{level:reds(t)?3:0});if(g.pending){assert.throws(()=>g.update(t+600,{level:0}),/决策/);const saved=new Game(g.checkpoint());assert.deepEqual(saved.view(),g.view());prompts++;const {day,stage}=g.pending;g.choose(day,stage,choices[day-1][stage]);assert.throws(()=>g.choose(day,stage,'write'),/失效/);}for(const[day,at]of Object.entries(repents))if(t===at)g.repent(+day,t);}return {g,v:g.view(),prompts};}
let out=run([{first:'skip',second:'sleep'},{first:'write'},{first:'skip',second:'awake'}],t=>t===41400||t===214200);
assert.equal(out.v.total,3000);assert.equal(out.prompts,5);assert(out.v.finished);assert.equal(out.v.days[0].result.caption,'暖区，简单！');
out=run([{first:'skip',second:'makeup'},{first:'skip',second:'awake'},{first:'skip',second:'sleep'}],t=>t===214800,{2:114000});
assert.deepEqual(out.v.days.map(d=>d.result.points),[667,Math.round(667*(1-13200/27000)),0]);assert.equal(out.v.days[1].result.caption,'好险，活过来了');assert.equal(out.v.days[2].result.caption,'Mission Failed');assert(!out.v.days[2].red);
out=run([{first:'skip',second:'awake'},{first:'write'},{first:'skip',second:'makeup'}],t=>t===41400||t===127800||t===214200,{1:30000});
assert.deepEqual(out.v.days.map(d=>d.result.points),[0,0,0]);assert(out.v.days.every(d=>d.result.caption==='Mission Failed'));
const g=new Game();for(let t=0;t<=14400;t+=600){g.update(t,{level:0});if(g.pending)g.choose(1,g.pending.stage,g.pending.stage==='first'?'skip':'awake');}g.repent(1,14400);assert.throws(()=>g.repent(1,14400),/不能/);assert.equal(new Game(g.checkpoint()).days[0].repentAt,14400);
assert.throws(()=>g.choose(2,'first','write'),/失效/);
console.log('PASS: decision fences, three midnight choices, early write skips second, 1000/667/time decay, captions, independent days, 3000 total and restore.');
