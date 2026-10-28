/* Short real-DEM terrain-access regression; no weather replay. */
'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
C.prepareBackendSync();
const data=terrain(),project=proj4('EPSG:4326',data.meta.projection),m=new C.Model({preset:'monsoon',geography:'real',seed:17,weatherRegion:'west_guangdong',windTurnStart:'south',coastalForcing:{exitOffset:50000}},data),bg={...m.background(),windAngle:Math.PI/4};
const xy=(lon,lat)=>{const p=project.forward([lon,lat]);return [p[0]+640000,p[1]+400000];},rows=[];
for(const [name,lon,lat] of [['Yangchun',111.79,22.17],['Enping',112.3,22.18]]){
 const [x,y]=xy(lon,lat),now=m._jetExitAccess(x,y,bg),helper=m._westernSlopeChannel;
 m._westernSlopeChannel=()=>({factor:0,coastalWeight:1});const prior=m._jetExitAccess(x,y,bg);m._westernSlopeChannel=helper;
 assert(now.slopeChannel.easternFlank>0,name+' is east of DEM mountain relief');
 assert(now.factor>prior.factor && now.ascent>prior.ascent,name+' gains lifting and initiation access');
 rows.push({name,previousAccess:prior.factor,currentAccess:now.factor,previousLift:prior.ascent,currentLift:now.ascent});
}
for(const point of [[111.62,21.75],[111.8,21.85]]){const s=m._westernSlopeChannel(...xy(...point),bg);assert.equal(s.factor,0,'flat coastal strip gets no inland slope/channel boost');assert(s.coastalWeight<.5);}
assert.equal(m._westernSlopeChannel(...xy(115.36,22.79),bg).factor,0,'east Guangdong unchanged');
const c=m.coastalGeometry,exit=c.exitOffset,sampled=c.sampledExitOffset;c.exitOffset=-80000;c.sampledExitOffset=-80000;m._jetFrameCache=null;
assert.equal(m._jetExitAccess(...xy(111.79,22.17),bg).factor,0,'far offshore exit still excludes inland initiation');
c.exitOffset=exit;c.sampledExitOffset=sampled;m._jetFrameCache=null;
console.log(JSON.stringify({model:C.VERSION,pass:true,rows,scope:'terrain-access samples only; no full-run longevity claim'}));
