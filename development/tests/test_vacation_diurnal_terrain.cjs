'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs'),proj4=require('../../assets/vendor/proj4/proj4.js');
const sum=a=>a.reduce((s,x)=>s+x,0),near=(a,b)=>assert(Math.abs(a-b)<=1e-10*Math.max(1,Math.abs(a),Math.abs(b)),a+' != '+b);
C.prepareBackendSync();
const m=new C.Model({geography:'idealized',preset:'coast',width:80000,height:80000,diurnalBoundaryLayer:true,disableBirths:true});m.preset={...m.preset,hour:8};m.fields.land.fill(1);m.captureInitialState();
const f=m.fields,k=m.env.index(40000,40000),water=sum(f.wl)+sum(f.wm),initialT=f.tl[k],initialRH=f.wl[k]/C.saturation(f.tl[k]);
for(let n=0;n<36;n++){for(let i=0;i<m.env.n;i++)m._applyDiurnalBoundaryLayer(i);m.t+=600;}
const afternoonRH=f.wl[k]/C.saturation(f.tl[k]);near(f.tl[k],initialT+3.5);near(sum(f.wl)+sum(f.wm),water);assert(afternoonRH<initialRH-.1,'warming and entrainment reduce afternoon RH');
assert(Math.abs(m.sourceAudit().heat.relativeResidual)<1e-10,'diurnal sensible heating is budgeted');
const ocean=new C.Model({geography:'idealized',preset:'coast',width:80000,height:80000,diurnalBoundaryLayer:true});ocean.preset={...ocean.preset,hour:11};ocean.fields.land.fill(0);const before=[...ocean.fields.wl];ocean._applyDiurnalBoundaryLayer(0);assert.deepEqual([...ocean.fields.wl],before);
const data=terrain(),real=new C.Model({geography:'real',preset:'monsoon',seed:130363},data),pr=proj4('EPSG:4326',data.meta.projection),directions=[];
for(const [name,lon,lat]of [['Yangchun',111.8,22.2],['EnpingFoothill',112.3,22.18],['EastGuangdong',116,23.2]]){
 const xy=pr.forward([lon,lat]),k=real.env.index(xy[0]+real.env.width/2,xy[1]+real.env.height/2),angle=15*Math.PI/180,[u,v]=real._terrainSteer(k,12*Math.cos(angle),12*Math.sin(angle));near(Math.hypot(u,v),12);directions.push({name,degrees:Math.atan2(v,u)*180/Math.PI,speed:Math.hypot(u,v)});
}
assert(directions[0].degrees>35&&directions[0].degrees<70);assert(directions[1].degrees>35&&directions[1].degrees<70);assert(Math.abs(directions[2].degrees)<25,'east Guangdong terrain favors eastward translation');
console.log(JSON.stringify({pass:true,initialRH,afternoonRH,waterConserved:true,heatResidual:m.sourceAudit().heat.relativeResidual,directions}));
