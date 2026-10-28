'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),C=require('../../assets/scripts/vacation-model.js'),S=require('../../assets/scripts/vacation-scenario.js'),D=require('../../assets/scripts/vacation-map-domain.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
C.prepareBackendSync();const data=terrain(),projection=proj4('EPSG:4326',data.meta.projection),drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;};
const seeds=[1,2,3,4,17,29,71,131,104729,130363,20210520,20260601],entries=[];
for(const seed of seeds){const m=new C.Model({preset:'monsoon',geography:'real',seed,hours:72},data),c=m.coastalGeometry;
 const [lon,lat]=projection.inverse([c.crossing.x-640000,c.crossing.y-400000]);assert(lon>=110.2&&lon<=117);assert(m.config.coastalWindParameters.sigmaJet>=110000);
 const initial=m._jetFrame(m.background());entries.push({seed,lon,lat,placement:initial.placement,sampledExitM:initial.sampledExit});
 for(let hour=0;hour<=72;hour+=3){const f=m._jetFrame(m.background(hour*3600));assert(f.sampledExit>=-80000&&f.sampledExit<=80000);assert.equal(f.exit,f.sampledExit);assert.equal(m._jetCoastWindow(200000),0);}
 assert.deepEqual(new C.Model(m.config,data).coastalGeometry,c,'same seed/config restores the accepted coast');
}
assert(entries.some(e=>e.placement==='offshore')&&entries.some(e=>e.placement==='inland'));
const siteTests=[];
for(const exitOffset of [-60000,60000]){
 const m=new C.Model({geography:'real',preset:'monsoon',seed:20210520,directionalCoastalTrigger:false,terrainBoundTrigger:false,coastalForcing:{exitOffset},hours:72},data),c=m.coastalGeometry,bg=m.background(),frame=m._jetFrame(bg),f=m.fields;
 let x=0,y=0,best=-1;for(let k=0;k<m.env.n;k++){const xx=(k%m.env.nx+.5)*m.env.dx,yy=(Math.floor(k/m.env.nx)+.5)*m.env.dx,a=m._jetExitAccess(xx,yy,bg);if(a.factor>best){best=a.factor;x=xx;y=yy;}}
 for(const key of ['xiL','xiM'])f[key].fill(10000);f.rhL.fill(.98);f.rhM.fill(.98);f.el.fill(.9);f.em.fill(.9);f.inflowFocus.fill(1);f.wConvergence.fill(.8);
 const access=m._jetExitAccess(x,y,bg);assert(access.factor>.8);assert(m.gate(x,y,0,bg,true).F>0,'actual low-level gate accepts eligible '+access.placement+' exit');
 // Even artificially perfect lifting/thermodynamics cannot bypass the exit mask.
 const outside={};for(const side of [-1,1]){for(let k=0;k<m.env.n;k++){const xx=(k%m.env.nx+.5)*m.env.dx,yy=(Math.floor(k/m.env.nx)+.5)*m.env.dx,d=m.forcing.sample(data.fields.signedDistance,xx,yy);if(m._jetCoastWindow(xx)>.5&&side*(d-frame.exit)>80000){outside[side]={x:xx,y:yy};break;}}assert(outside[side]);for(const layer of [0,1])assert.equal(m.gate(outside[side].x,outside[side].y,layer,bg,true).F,0,'both layers reject outside coast-normal exit');}
 // The cold-front/head-lift path uses the same mandatory location mask.
 const {x:xx,y:yy}=outside[1];assert.equal(m._liftAccess(m.env.index(xx,yy),xx,yy,0,bg,20000,{x,y}).factor,0);
 m.triggerSources=[{id:'outside',x:xx,y:yy,activated:0,lastBirth:0}];m.config.lambda0=0;drain(m.initiate());assert.equal(m.triggerSources.length,0,'persistent roots close when outside exit');
 siteTests.push({sampled:exitOffset,effective:frame.exit,placement:access.placement,gate:m.gate(x,y,0,bg,true).F});
}
const m=new C.Model({geography:'real',preset:'monsoon',seed:104729},data),alignment=[];
for(const [name,lon,lat,parallel,across]of [['Yangchun',111.8,22.2,45,135],['Enping',112.3,22.2,55,145],['Shanwei',115.4,22.9,15,75],['Shantou',116.7,23.4,15,75],['PRD',113.3,22.9,15,75]]){
 const [px,py]=projection.forward([lon,lat]),x=px+640000,y=py+400000,bg=m.background(),a=m._jetExitAccess(x,y,{...bg,windAngle:parallel*Math.PI/180}).alignment,b=m._jetExitAccess(x,y,{...bg,windAngle:across*Math.PI/180}).alignment;
 if(name==='PRD')assert(Math.abs(a-b)<.05);else assert(a>b+.25,name+' parallel flow favored');alignment.push({name,parallel:a,across:b});
}
const stations=D.stations(JSON.parse(fs.readFileSync('assets/data/simulator-stations.json')),data.meta,projection);assert.equal(stations.length,158);assert(stations.some(s=>s.name==='阳春'));assert(stations.some(s=>s.name==='恩平'));assert(stations.some(s=>s.id==='59635'));
for(let seed=0;seed<256;seed++)assert.equal(S.generate({seed},seed).hours,72);
console.log(JSON.stringify({pass:true,entries,siteTests,alignment,stations:stations.length,durationHours:72},null,2));
