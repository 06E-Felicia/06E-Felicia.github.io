'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
C.prepareBackendSync();const data=terrain(),project=proj4('EPSG:4326',data.meta.projection),xy=(lon,lat)=>{const p=project.forward([lon,lat]);return [p[0]+640000,p[1]+400000];};
for(const seed of [17,131]){
 const m=new C.Model({preset:'monsoon',geography:'real',seed,coastalForcing:{exitOffset:45000}},data);
 for(const [angle,points]of [[25,[[113.57,22.27],[114.13,22.38],[114.5,22.58]]],[50,[[111.67,22.03]]]]){
  const bg={...m.background(),windAngle:angle*Math.PI/180};
  for(const p of points){const a=m._jetExitAccess(...xy(...p),bg);assert(a.factor>.05,JSON.stringify({seed,angle,p,a}));assert(a.ascent>.02,'coastal hill lifts parcel');}
  for(const p of [[113.3,23.12],[113.6,23.5],[114.25,23.78]]){const a=m._jetExitAccess(...xy(...p),bg);assert.equal(a.factor,0,'inland PRD does not initiate');}
 }
 const a={...m.background(),windAngle:50*Math.PI/180},p=xy(111.67,22.03);
 m.fields.rhL.fill(.98);m.fields.el.fill(.9);m.fields.xiL.fill(800);m.fields.u.fill(10);m.fields.v.fill(10);
 assert(m._persistentSourceGate({id:'west',x:p[0],y:p[1],activated:0,lastBirth:0},a).F>0,'wet western source remains eligible');
}
console.log('PASS: southwest supports Yangchun; WSW supports coastal PRD; inland PRD suppressed; source maintenance remains eligible.');
