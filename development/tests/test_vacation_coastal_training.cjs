'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),V=require('../../assets/scripts/vacation-version.js'),{terrain}=require('../scripts/record_vacation_replay.cjs');
C.prepareBackendSync();const drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;};
const calendar={startHour:20,calendarOrigin:'previous_day'};
assert.deepEqual(V.simulationTime(0,calendar),{clock:'20:00',day:'前一日'});
assert.deepEqual(V.simulationTime(4*3600,calendar),{clock:'00:00',day:'第 1 天'});
assert.deepEqual(V.simulationTime(28*3600,calendar),{clock:'00:00',day:'第 2 天'});
assert.deepEqual(V.simulationTime(72*3600,calendar),{clock:'20:00',day:'第 3 天'});
assert.equal(V.simulationTime(0,{startHour:22}).day,'第 1 天','old archived replay keeps its original calendar');
const data=terrain(),areas=[];
for(const region of ['west_guangdong','pearl_river','east_guangdong']){
 const m=new C.Model({preset:'monsoon',geography:'real',seed:20210520,directionalCoastalTrigger:false,terrainBoundTrigger:false,weatherRegion:region,coastalForcing:{exitOffset:10000}},data);assert.equal(m.config.startHour,20);assert.equal(m.preset.hour,20);assert.equal(m.config.calendarOrigin,'previous_day');
 const bg=m.background(),area={region};
 for(const geometry of ['planar','coast_following']){m.config.jetExitGeometry=geometry;let n=0,minX=Infinity,maxX=-Infinity;const bins=new Set();
  for(let k=0;k<m.env.n;k++){const x=(k%m.env.nx+.5)*m.env.dx,y=(Math.floor(k/m.env.nx)+.5)*m.env.dx,a=m._jetExitAccess(x,y,bg);if(a.factor>.15&&a.alignment>.3){n++;minX=Math.min(minX,x);maxX=Math.max(maxX,x);bins.add(Math.floor(m._approxLongitude(x)));}}
  area[geometry]={km2:n*25,spanKm:(maxX-minX)/1000,longitudeBins:[...bins].sort()};
 }
 assert(area.coast_following.km2>area.planar.km2*2);assert(area.coast_following.spanKm>400);assert(area.coast_following.longitudeBins.length>=4);areas.push(area);
 // The wind termination and gate must use precisely the same exit coordinate.
 const x=m.coastalGeometry.crossing.x+10000,y=m.coastalGeometry.crossing.y,b=m._jetFrame(bg),coord=m._jetCoordinates(x,y,bg),f=data.fields,g=m.forcing,out=[];
 m._finiteWindSample(x,y,bg,1,g.sample(f.signedDistance,x,y),g.sample(f.coastX,x,y),g.sample(f.coastY,x,y),{u:0,v:0},out);
 assert.equal(out[12],coord.along);assert.equal(m._jetExitAccess(x,y,bg).distanceFromExitM,coord.along-b.exit);
}
// Real-terrain restart must retain the calendar, coast coordinates and fixed roots.
const live=new C.Model({preset:'monsoon',geography:'real',seed:20210520,hours:3},data);
for(let n=0;n<6;n++)live.step();assert(live.triggerSources.length>0);
const restored=C.Model.restore(live.checkpoint(),data);live.step();restored.step();
assert.deepEqual(restored.triggerSources,live.triggerSources);assert.deepEqual(restored.events,live.events);
for(const key of ['wl','wm','xiL','xiM'])assert.deepEqual(restored.fields[key],live.fields[key]);
assert.equal(restored.config.startHour,20);assert.equal(restored.config.calendarOrigin,'previous_day');
// Isolate source competition using deterministic eligible thermodynamics. No
// moving-cell or cold-pool method is mocked or altered by the initiation pass.
function competition(existing){
 const m=new C.Model({geography:'idealized',preset:'coast',width:120000,height:160000,seed:17,upstreamSourceBlocking:true,lambda0:.001});
 m._jetFrame=()=>({e:{x:0,y:1}});
 const south={id:'south',x:60000,y:40000,activated:0,lastBirth:0},north={id:'north',x:60000,y:70000,activated:0,lastBirth:0};
 m.triggerSources=existing?[north,south]:[];m.t=600;
 m.gate=(x,y,layer)=>({F:(!layer||y>60000)&&Math.abs(x-60000)<2000&&(Math.abs(y-40000)<2000||Math.abs(y-70000)<2000)?1:0,source:'environment',power:100,coldPower:0,CIN:0,rh:.95,energy:.9,evidence:{}});
 const cell={x:110000,y:150000,age:2000};m.cells=[cell];drain(m.initiate());
 assert(m.triggerDiagnostics.byLayer.mid.acceptedBeforeSpacing>0,'northern elevated proposals also exercise the veto');assert(m.events.length>0);assert(m.events.every(e=>e.y<50000),'southern source prevents northern births, including same-step candidates');assert(m.cells.includes(cell),'existing moving cells are not deleted');
 assert.equal(m._upstreamSource(60000,70000,m.background())?.id,m.triggerSources[0].id);
 assert.equal(m._upstreamSource(110000,70000,m.background()),null,'independent coastal corridor stays available');
 assert.equal(m._upstreamSource(60000,20000,m.background()),null,'southern upstream point stays available');
 m.triggerSources=[];assert.equal(m._upstreamSource(60000,70000,m.background()),null,'shadow ends when source closes');
}
competition(false);competition(true);
console.log(JSON.stringify({pass:true,calendar:true,areas,sourceBlocking:'new and persistent births, same-step ordering, cross-corridor access, closure release'}));
