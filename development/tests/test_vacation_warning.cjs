'use strict';
const assert=require('node:assert/strict'),{Detector,stationCells}=require('../../assets/scripts/vacation-warning.js');
const stations=[{id:'dp',name:'龙岐',district:'大鹏新区',index:0},{id:'ft',name:'竹子林',district:'福田区',index:1}];
const m=new Detector(stations),totals=new Float64Array(2);let result,restored;
for(let t=0;t<=30000;t+=600){
 // Progressive 30 / 40 / 70 mm in an hour; only Dapeng is wet.
 if(t>0&&t<=3600)totals[0]+=t<=2400?10:20;
 result=m.update(t,totals);
 if(t===1800)assert.equal(result.level,1);
 if(t===2400)assert.equal(result.level,2);
 if(t===3600){assert.equal(result.level,3);assert.equal(result.stations[1].level,0);restored=new Detector(stations,m.checkpoint());}
 else if(restored)assert.deepEqual(restored.update(t,totals),result);
}
assert.equal(result.level,0);assert.deepEqual(result.events.filter(e=>e.level>0).map(e=>e.level),[1,2,3]);
assert(!Object.hasOwn(result,'areaKm2'));assert.equal(result.stationCount,2);assert(m.history.length<=37);
const d=new Detector(stations),r=new Float64Array(2);for(let t=0;t<=10800;t+=600){if(t)r[0]+=6;result=d.update(t,r);}assert.equal(result.level,3,'108 mm in 3h at 36 mm/h issues red without an area vote');
const slow=new Detector(stations),low=new Float64Array(2);for(let t=0;t<=86400;t+=600){if(t)low[0]+=2;result=slow.update(t,low);}assert(result.stations[0].total>200);assert.notEqual(result.level,3,'200 mm total does not replace the rolling threshold');
assert.throws(()=>new Detector(stations).update(900,totals),/十分钟/);
assert.throws(()=>stationCells({stations:[{id:'a',district:'a',lon:1,lat:1}]},{forward:x=>x},{width:2,height:2,index:()=>-1}),/超出/);
console.log('PASS: independent stations, yellow/orange/red history, rolling thresholds, wet tails, checkpoint continuity.');
// Red remains issued for one complete hour after the rolling red threshold fails.
const hold=new Detector(stations),heldTotals=new Float64Array(2);let holdRestored;
for(let t=0;t<=7800;t+=600){
 if(t)heldTotals[0]+=t===600?70:.2;
 const w=hold.update(t,heldTotals);
 if(t===4200)assert.equal(hold.belowSince[0],4200);
 if(t>=4200&&t<7800)assert.equal(w.stations[0].level,3,'retain red throughout the one-hour hold');
 if(t===6000)holdRestored=new Detector(stations,hold.checkpoint());
 else if(holdRestored)assert.deepEqual(holdRestored.update(t,heldTotals),w);
 if(t===7800)assert.equal(w.stations[0].level,2,'downgrade to orange only after 60 continuous minutes');
}
// Requalifying midway cancels the previous timer, even if rain stops again.
const reset=new Detector(stations),resetTotals=new Float64Array(2);
for(let t=0;t<=8400;t+=600){
 if(t===600||t===3600)resetTotals[0]+=80;
 const w=reset.update(t,resetTotals);
 if(t===1800)assert.equal(reset.belowSince[0],1800);
 if(t===3600){assert.equal(w.level,3);assert.equal(reset.belowSince[0],null);}
 if(t===4800)assert.equal(reset.belowSince[0],4800);
 if(t>=4800&&t<8400)assert.equal(w.level,3,'recovery restarts the full one-hour hold');
 if(t===8400)assert.equal(w.level,0);
}
const stationData=require('../../assets/data/vacation-warning-stations.json');assert.equal(stationData.stations.length,74);assert(stationData.stations.every(s=>!s.name.includes('代表站')));
console.log('PASS: one-hour downgrade hold, threshold recovery resets timer, hold checkpoint restore, street display names.');
