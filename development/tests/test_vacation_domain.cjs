'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),S=require('../../assets/scripts/vacation-scenario.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
const data=terrain(),projection=proj4('EPSG:4326',data.meta.projection),drain=it=>{while(!it.next().done){}};
const regions=['west_guangdong','pearl_river','east_guangdong'],anchors=[];
for(const weatherRegion of regions){
 const m=new C.Model({geography:'real',preset:'monsoon',seed:130363,hours:48,weatherRegion,quality:'low'},data);assert.equal(m.config.width,1280000);assert.equal(m.config.height,800000);
 for(const [name,lon,lat]of [['Chongzuo',107.36,22.42],['Fangchenggang',108.35,21.61],['Qinzhou',108.62,21.96],['Shenzhen',114.06,22.54]]){
  const [x,y]=projection.forward([lon,lat]).map((v,k)=>v+(k?m.config.height:m.config.width)/2);assert(m.env.index(x,y)>=0,name+' included');assert(x>100000&&x<m.config.width-100000,name+' outside lateral boundary buffer');
 }
 const dirs=Array.from({length:433},(_,i)=>270-m._monsoonAngle(i*600)*180/Math.PI);assert(Math.min(...dirs)>=195-1e-8&&Math.max(...dirs)<=255+1e-8);assert(Math.max(...dirs)-Math.min(...dirs)>34.9);
 const sign=Math.sign(dirs.at(-1)-dirs[0]);for(let i=1;i<dirs.length;i++){assert((dirs[i]-dirs[i-1])*sign>=0);assert(Math.abs(dirs[i]-dirs[i-1])<.15);}
 anchors.push({region:weatherRegion,x:m.coastalGeometry.crossing.x,y:m.coastalGeometry.crossing.y,windFromMin:Math.min(...dirs),windFromMax:Math.max(...dirs)});
 drain(m.updateForcing());drain(m.diagnoseEnvironment(true));assert(m.fields.xiTerrain.some(v=>v>100),'resolved windward terrain lift');
 // Every low-level parcel under a resolved cold pool must be rejected, even
 // when all thermodynamic/lifting factors would otherwise permit initiation.
 const x=m.coastalGeometry.crossing.x,y=m.coastalGeometry.crossing.y,k=m.cold.index(x,y);m.h[k]=200;m.q[k]=400;
 assert.equal(m.gate(x,y,0,m.background(),true).F,0,'cold-covered low-level trigger veto');
}
for(let i=1;i<anchors.length;i++)assert(anchors[i].x>anchors[i-1].x+100000,'regional inlet selection actually moves east');
for(let seed=0;seed<256;seed++)assert.equal(S.generate({seed},seed).weatherRegion,'auto');
const D=require('../../assets/scripts/vacation-map-domain.js'),b=D.bounds(data.meta,projection);assert(D.covered(b,data.meta,projection));
assert(!D.covered({west:104.3,east:118,south:19.8,north:26.7},data.meta,projection),'old draggable region exceeded the model');
for(const [lon,lat] of [[107.36,22.42],[108.35,21.61],[114.06,22.54]])assert(lon>b.west&&lon<b.east&&lat>b.south&&lat<b.north);
console.log(JSON.stringify({model:C.VERSION,domainKm:[1280,800],anchors,mapBounds:b,checks:['western cities covered','Guangdong regional diagnostic overrides','195–255 degree slow monotonic 72-hour turn','terrain lift','cold veto','automatic default','projected map containment']},null,2));
