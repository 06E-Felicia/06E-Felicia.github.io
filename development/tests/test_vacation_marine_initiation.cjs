'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
C.prepareBackendSync();const data=terrain(),pr=proj4('EPSG:4326',data.meta.projection),xy=(lon,lat)=>{const p=pr.forward([lon,lat]);return[p[0]+640000,p[1]+400000]};
const m=new C.Model({preset:'monsoon',geography:'real',seed:17,coastalForcing:{exitOffset:-30000}},data);
m.t=10800;m.fields.rhL.fill(.99);m.fields.el.fill(.95);m.fields.xiL.fill(1000);m.fields.inflowFocus.fill(1);
const south={...m.background(),windAngle:72*Math.PI/180},west={...south,windAngle:25*Math.PI/180};
for(const p of [[113.6,21.9],[114.5,22],[112.4,21.7]]){
 const q=xy(...p);assert.equal(m._jetExitAccess(...q,south).factor,0,'ordinary offshore exit cannot bypass meridional restriction');
 assert.equal(m.gate(...q,0,south,true).F,0,'wet energetic marine parcel still cannot start a southerly train');
 assert.equal(m._frontDevelopmentAccess(...q,south),0,'cold-front route uses the same marine restriction');
 assert.equal(m._persistentSourceGate({id:'sea',x:q[0],y:q[1],activated:0,lastBirth:0},south).F,0,'offshore root cannot keep re-firing after wind turns southerly');
}
assert(m.gate(...xy(113.6,21.9),0,west,true).F>.1,'zonal marine deceleration still initiates');
const speeds=m._monsoonSpeeds(south);assert(Math.abs(m._remainingMonsoonFraction(south,1e6,10000)-speeds.background/speeds.jet)<1e-8,'background monsoon survives jet deceleration');
const hills=new C.Model({preset:'monsoon',geography:'real',seed:17,coastalForcing:{exitOffset:35000}},data);hills.t=14400;hills.fields.rhL.fill(.98);hills.fields.el.fill(.9);hills.fields.xiL.fill(800);hills.fields.inflowFocus.fill(1);
const bg={...hills.background(),windAngle:72*Math.PI/180},rows=[];
for(const p of [[111.75,22.06],[112.10,22.03],[112.20,22.10]]){const q=xy(...p),a=hills._jetExitAccess(...q,bg);assert(a.factor>.15&&a.ascent>.1,'actual western windward foothill retains lifting');assert(hills._persistentSourceGate({id:'hill',x:q[0],y:q[1],activated:0,lastBirth:0},bg).F>0);rows.push({p,factor:a.factor,ascent:a.ascent});}
const cell={id:'fed-train',triggerSourceId:'root'};hills._ensurePulse(cell);assert(cell.pulse.Nend>=8&&cell.pulse.Nend<=11.5,'finite sustained pulse range');
console.log(JSON.stringify({pass:true,ordinaryAndPersistentMarineSouthBlocked:true,zonalMarineAllowed:true,westernSoutherlySlopes:rows,pulseRange:[8,11.5]}));
