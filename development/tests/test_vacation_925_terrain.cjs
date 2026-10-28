'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
C.prepareBackendSync();const data=terrain(),pr=proj4('EPSG:4326',data.meta.projection),drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;};
const xy=(lon,lat)=>{const p=pr.forward([lon,lat]);return [p[0]+640000,p[1]+400000];};
const m=new C.Model({preset:'monsoon',geography:'real',seed:20210520,hillJetBraking:false,coastalForcing:{exitOffset:60000}},data),f=m.fields,bg={...m.background(),windAngle:Math.PI/4};
f.rhL.fill(.98);f.rhM.fill(.98);f.el.fill(.95);f.em.fill(.95);f.xiL.fill(10000);f.xiM.fill(10000);f.wConvergence.fill(.8);f.inflowFocus.fill(1);
const sites=[];
for(const [name,lon,lat,mountain]of [['Maoming',110.92,21.66,false],['Yangxi',111.62,21.75,false],['GuangzhouPlain',113.3,23.12,false],['Yangchun',111.79,22.17,true],['EnpingMountain',112.2,22.3,true]]){
 const [x,y]=xy(lon,lat),anchor=m._terrainAnchor(x,y),gate=m.gate(x,y,0,bg,true),a=m._jetExitAccess(x,y,bg);sites.push({name,anchor,gate:gate.F,exitDistanceM:a.distanceFromExitM});
 if(mountain){assert(anchor.factor>0);assert(gate.F>0,name+' mountain row intersects the inland jet exit');}
 else {assert.equal(anchor.factor,0);assert.equal(gate.F,0,name+' plain cannot initiate under ideal thermodynamics');assert.equal(m.gate(x,y,1,bg,true).F,0);assert.equal(m._liftAccess(m.env.index(x,y),x,y,0,bg,10000,{x,y}).factor,0,'cold-pool head cannot bypass terrain requirement');assert.equal(m._persistentSourceGate({id:name,x,y,activated:0,lastBirth:0},bg).F,0);}
}
assert.equal(m._jetFrame(bg).exit,60000,'inland jet is not clamped to coastal 10 km');
// Move only the deceleration zone seaward: inland mountains cease to ignite.
const inland=m.coastalGeometry.exitOffset,sampled=m.coastalGeometry.sampledExitOffset;
m.coastalGeometry.exitOffset=0;m.coastalGeometry.sampledExitOffset=0;m._jetFrameCache=null;
for(const point of [[111.79,22.17],[112.3,22.18]]){const [x,y]=xy(...point);assert.equal(m.gate(x,y,0,bg,true).F,0);}
m.coastalGeometry.exitOffset=inland;m.coastalGeometry.sampledExitOffset=sampled;m._jetFrameCache=null;
// Weak coastal hills remain valid anchors where the actual DEM supports them.
for(const point of [[113.27,22.2],[113.57,22.27]]){const [x,y]=xy(...point);assert(m._terrainAnchor(x,y).factor>0);}
// The displayed 925 hPa carrier does not inherit surface roughness or sea breeze.
const [x,y]=xy(110.92,21.66),a=[],b=[];m._finiteWindSample(x,y,bg,1,30000,0,1,{u:0,v:0},a);m._finiteWindSample(x,y,bg,.6,30000,0,1,{u:0,v:0},b);assert.deepEqual(a,b);assert.equal(a[6],0);assert.equal(a[7],0);
// Rain/carrier motion in plains and open sea follows the actual modeled wind.
for(const point of [[110.92,21.66],[111.62,21.75],[113,20.8]]){const [x,y]=xy(...point),k=m.env.index(x,y);assert.equal(m._terrainAnchor(x,y).factor,0);assert(Math.abs(f.um[k]-f.u[k])<1e-12);assert(Math.abs(f.vm[k]-f.v[k])<1e-12);}
const sea=new C.Model({preset:'monsoon',geography:'real',seed:20210520,directionalCoastalTrigger:false,coastalForcing:{exitOffset:-40000}},data);
for(const key of ['xiL','xiM'])sea.fields[key].fill(10000);sea.fields.rhL.fill(.98);sea.fields.el.fill(.95);sea.fields.inflowFocus.fill(1);drain(sea.initiate());
const newborn=sea.cells.find(c=>sea._terrainAnchor(c.x,c.y).factor===0);assert(newborn,'open-sea new tower exists');const k=sea.env.index(newborn.x,newborn.y);assert(Math.abs(newborn.vx-sea.fields.u[k])<1e-12);assert(Math.abs(newborn.vy-sea.fields.v[k])<1e-12);
console.log(JSON.stringify({pass:true,sites,checks:['plains reject both layers and persistent roots','inland jet and mountain row move together','Doumen/Zhuhai terrain retained','925 carrier excludes surface friction/breeze','flat motion and initial cell velocity match wind']}));
