/* Short real-DEM terrain-access regression; no weather replay. */
'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
C.prepareBackendSync();
const data=terrain(),project=proj4('EPSG:4326',data.meta.projection),m=new C.Model({preset:'monsoon',geography:'real',seed:17,weatherRegion:'west_guangdong',windTurnStart:'south',coastalForcing:{exitOffset:50000}},data),bg={...m.background(),windAngle:Math.PI/4};
const xy=(lon,lat)=>{const p=project.forward([lon,lat]);return [p[0]+640000,p[1]+400000];},rows=[];
for(const [name,lon,lat] of [['Yangchun SW',111.67,22.03],['Yangjiang NE',112.10,22.03],['South Enping',112.20,22.10]]){
 const [x,y]=xy(lon,lat),a=m._jetExitAccess(x,y,bg);
 assert(a.slopeChannel.easternFlank>0,name+' is east of actual mountain relief');
 assert(a.factor>.2 && a.ascent>.1,name+' supports mountain lifting');
 rows.push({name,access:a.factor,lift:a.ascent});
}
for(const point of [[111.8,22.4],[112.2,22.45]])assert.equal(m._jetExitAccess(...xy(...point),bg).factor,0,'no new western source too far north');
assert.equal(m._westernSlopeChannel(...xy(111.62,21.75),bg).factor,0,'Yangxi coastal plain gains no source');
const longmen=xy(114.25,23.78);assert.equal(m._birthRegionAllowed(...longmen),false);assert.equal(m.gate(...longmen,0,bg).F,0);assert.equal(m.gate(...longmen,1,bg).F,0);
assert.equal(m._persistentSourceGate({id:'longmen',x:longmen[0],y:longmen[1],activated:0,lastBirth:0},bg).F,0,'persistent source cannot bypass exclusion');
assert.equal(m._westernSlopeChannel(...xy(115.36,22.79),bg).factor,0,'east Guangdong unchanged');
const c=m.coastalGeometry,exit=c.exitOffset,sampled=c.sampledExitOffset;c.exitOffset=-80000;c.sampledExitOffset=-80000;m._jetFrameCache=null;
assert.equal(m._jetExitAccess(...xy(111.79,22.17),bg).factor,0,'far offshore exit still excludes inland initiation');
c.exitOffset=exit;c.sampledExitOffset=sampled;m._jetFrameCache=null;
console.log(JSON.stringify({model:C.VERSION,pass:true,rows,scope:'terrain-access samples only; no full-run longevity claim'}));
