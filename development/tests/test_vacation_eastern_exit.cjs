/* Short real-DEM probes only; no full-field replay or weather history. */
'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
C.prepareBackendSync();const data=terrain(),project=proj4('EPSG:4326',data.meta.projection),xy=(lon,lat)=>{const p=project.forward([lon,lat]);return[p[0]+640000,p[1]+400000]};
const m=new C.Model({preset:'monsoon',geography:'real',seed:17},data),bg={...m.background(),windAngle:25*Math.PI/180};
function sample(exit){m.coastalGeometry.options.exitOffset=exit;m.coastalGeometry.exitOffset=exit;m.coastalGeometry.sampledExitOffset=exit;m._jetFrameCache=null;return {coast:m._jetExitAccess(...xy(116.29,23.03),bg),inland:m._jetExitAccess(...xy(115.3,23.05),bg)};}
const interior=sample(60000),coastal=sample(10000),offshore=sample(-40000);
assert(interior.inland.factor>interior.coast.factor*4,'inland deceleration can initiate inland first');
assert(coastal.coast.factor>coastal.inland.factor*4,'shoreward deceleration moves the preferred zone to coast');
assert.equal(offshore.inland.factor,0);assert(offshore.coast.exitM<0,'negative random exit remains offshore');
assert(m._birthRegionAllowed(...xy(115.3,23.05)),'no permanent eastern inland exclusion');
const coord=m._jetCoordinates(...xy(116.29,23.03),bg);assert.equal(coord.exit,offshore.coast.exitM,'wind and lifting use shared effective exit');
// Random daily migration remains reproducible, with either sign possible.
function exits(seed){const a=new C.Model({preset:'monsoon',geography:'real',seed},data);return [0,43200,86400,129600,172800].map(t=>a._jetCoordinates(...xy(116.29,23.03),{...a.background(t),atSeconds:t,windAngle:25*Math.PI/180}).exit);}
const a=exits(17),b=exits(131);assert.deepEqual(exits(17),a);assert.notDeepEqual(a,b);assert(a.some((x,i)=>i&&x!==a[i-1]));
let maxTurn=0;for(let k=0;k<m.env.n;k+=7){const speed=13,angle=.7,u=speed*Math.cos(angle),v=speed*Math.sin(angle),out=m._terrainSteer(k,u,v);assert(Math.abs(Math.hypot(...out)-speed)<1e-9);maxTurn=Math.max(maxTurn,Math.abs(Math.atan2(out[1],out[0])-angle));}
assert(maxTurn<20*Math.PI/180,'terrain may deflect, but cannot dominate steering');
console.log(JSON.stringify({pass:true,randomExitTracks:[a,b],coastalAccess:coastal.coast.factor,inlandAccess:interior.inland.factor,maxTurnDeg:maxTurn*180/Math.PI}));
