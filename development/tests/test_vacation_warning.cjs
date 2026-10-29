'use strict';
const assert=require('node:assert/strict'),{Detector}=require('../../assets/scripts/vacation-warning.js');
const cells=Array.from({length:4},(_,index)=>({index,district:0,weight:1})),districts=[{id:'test',name:'test'}];
const make=()=>new Detector(cells,districts),t=new Float64Array(4),m=make();
let result,restored;
for(let step=0;step<=432;step++){
 const time=step*600;
 // Day 1 reaches red; day 2 stays dry and fails; day 3 independently reaches red.
 if(step>0&&(time<=7200||(time>187200&&time<=194400)))t[0]+=12;
 result=m.update(time,t);
 if(time===3600){assert.equal(result.level,3);assert.equal(result.results[0].outcome,'complete');restored=new Detector(cells,districts,m.checkpoint());}
 else if(restored){assert.deepEqual(restored.update(time,t),result);}
 if(time===100800)assert.equal(result.results[1],null,'new day does not inherit prior success');
 if(time===127800)assert.equal(result.results[1].outcome,'failed');
}
assert.deepEqual(result.results.map(r=>r.outcome),['complete','failed','complete']);
assert.equal(result.level,0,'old rain leaves rolling windows');assert(m.history.length<=37);
const exact=make(),totals=new Float64Array(4);for(let time=0;time<=41400;time+=600){if(time>37800)totals[0]+=12;result=exact.update(time,totals);}assert.equal(result.results[0].outcome,'complete','red exactly at 07:30 succeeds');
const late=make(),lt=new Float64Array(4);for(let time=0;time<=45000;time+=600){if(time>41400)lt[0]+=15;result=late.update(time,lt);}assert.equal(result.results[0].outcome,'failed','late red cannot rewrite deadline');
const coverage=new Detector([...cells,{index:4,district:0,weight:1}],districts),small=new Float64Array(5);for(let time=0;time<=3600;time+=600){if(time)small[0]+=15;result=coverage.update(time,small);}assert.equal(result.level,0,'20% coverage is insufficient');
assert.throws(()=>make().update(900,new Float64Array(4)),/十分钟/);
console.log('PASS: rolling rain, regional coverage, three daily results, exact deadline, no late override and checkpoint continuity.');
