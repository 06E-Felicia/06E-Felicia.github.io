'use strict';
const assert=require('node:assert/strict');
const C=require('../../assets/scripts/vacation-model.js');
const {terrain}=require('../scripts/record_vacation_replay.cjs');
const proj4=require('../../assets/vendor/proj4/proj4.js');
// Rotate the same ridge relative to incoming air. Lee rejection must not
// disappear when the flow changes from southerly to westerly.
for(const degrees of [15,25,38,50,65,75]){
 const m=Object.create(C.Model.prototype),angle=degrees*Math.PI/180,ex=Math.cos(angle),ey=Math.sin(angle);
 m.config={organizedWarmSector:true};m.t=0;m.env={nx:40,dx:5000,index:(x,y)=>Math.floor(y/5000)*40+Math.floor(x/5000)};
 m.terrain={fields:{z:[]}};m.forcing={sample:(_,x,y)=>Math.max(0,400-Math.abs((x-50625)*ex+(y-50625)*ey)*.04)};
 const at=d=>m._windwardExposure(50625+ex*d,50625+ey*d,{windAngle:angle});
 assert(at(-5000).factor>.5,'windward face survives '+degrees);
 assert.equal(at(5000).factor,0,'lee rejected '+degrees);
}
C.prepareBackendSync();const data=terrain(),project=proj4('EPSG:4326',data.meta.projection);
const m=new C.Model({preset:'monsoon',geography:'real',seed:17,windTurnStart:'west',coastalForcing:{exitOffset:20000}},data);
const counts={pearlEast:0,east:0},front={pearlEast:0,east:0};
for(const deg of [20,30,38]){
 const bg={...m.background(),windAngle:deg*Math.PI/180};
 for(let lon=114.1;lon<=116.3;lon+=.08)for(let lat=22.3;lat<=23.4;lat+=.06){
  const p=project.forward([lon,lat]),x=p[0]+640000,y=p[1]+400000;
  if(m.forcing.sample(data.fields.land,x,y)<.5)continue;
  const a=m._jetExitAccess(x,y,bg),region=lon<114.7?'pearlEast':'east';
  if(a.windwardExposure.factor===0){counts[region]++;assert.equal(a.factor,0,'lee cannot be a terrain/linked source');}
  if(a.factor>.01&&a.windwardExposure.riseM>20)front[region]++;
 }
}
assert(Object.values(counts).every(n=>n>0));assert(Object.values(front).every(n=>n>0),'real windward candidates remain in both regions');
console.log(JSON.stringify({pass:true,leeCandidatesRejected:counts,windwardCandidatesRetained:front}));
