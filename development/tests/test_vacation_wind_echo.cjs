'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js'),{terrain}=require('../scripts/record_vacation_replay.cjs');
const drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;},sum=a=>a.reduce((s,x)=>s+x,0);
C.prepareBackendSync();const data=terrain(),inlets=[];
for(const seed of [1,2,3,4,17,29,71,131,104729,130363,20210520,20260601]){
 const m=new C.Model({preset:'monsoon',geography:'real',hours:48,quality:'low',seed},data),p=m.config.coastalWindParameters,c=m.coastalGeometry;
 assert.equal(m.config.weatherRegion,'auto');assert(p.jetExcessAlong>=2&&p.jetExcessAlong<=5);assert(p.backgroundAlong>=9&&p.backgroundAlong<=12);
 const axis=Math.atan2(c.axisDirection.y,c.axisDirection.x)*180/Math.PI;assert(axis>=15&&axis<=75);inlets.push({seed,x:c.crossing.x,y:c.crossing.y,axis,excess:p.jetExcessAlong});assert.equal(axis<45,C.random(C.hash(seed,'three-day-wind-turn'))()<.5,'coast admission retry must preserve the seeded opening regime');
 for(const scale of [0,.5,1,2,4]){
  const bg={...m.background(0),V:scale*m.preset.baseV,exitEnvelope:0},out=[];
  m._finiteWindSample(c.crossing.x,c.crossing.y,bg,1,-40000,0,1,{u:0,v:0},out);
  assert(Math.hypot(out[4],out[5])<=5+1e-12,'nighttime/synoptic scaling cannot amplify jet contrast beyond 5 m/s');
  if(scale>0){assert(Math.hypot(out[0],out[1])<=15+1e-10);assert(Math.hypot(out[0],out[1])>=10-1e-10);}
  if(scale===0)assert.equal(Math.hypot(out[2],out[3],out[4],out[5]),0,'supply-off control remains effective');
 }
 // Cache/restore starts from the same random axis and same accepted inlet.
 const restored=new C.Model(m.config,data);assert.deepEqual(restored.coastalGeometry.crossing,c.crossing);
 const angles=Array.from({length:433},(_,i)=>m._monsoonAngle(i*600)*180/Math.PI),direction=Math.sign(angles.at(-1)-angles[0]);
 assert(Math.abs(angles[0]-axis)<1e-10);assert(Math.abs(angles.at(-1)-angles[0])>=35-1e-10);
 for(let i=1;i<angles.length;i++){assert((angles[i]-angles[i-1])*direction>=0);assert(Math.abs(angles[i]-angles[i-1])<.15);assert.equal(restored._monsoonAngle(i*600),m._monsoonAngle(i*600));}
 inlets.at(-1).turnDirection=direction;inlets.at(-1).endAngle=angles.at(-1);
}
assert(Math.max(...inlets.map(p=>p.x))-Math.min(...inlets.map(p=>p.x))>400000,'random inflow spans Guangdong coast');
assert.equal(new Set(inlets.map(p=>p.turnDirection)).size,2,'both seeded rotation directions occur');
assert(new Set(inlets.map(p=>p.axis)).size>=10,'initial direction is seeded, not a fixed coast-normal angle');
// Equal water, identical still air and saturation. Compare the former repeated
// parent-size deposition with partitioned subcores at native 2 km resolution.
const cases=[];
for(const oldSpread of [true,false]){
 const m=new C.Model({geography:'idealized',preset:'coast',width:80000,height:80000,quality:'standard',disableBirths:true,disableCold:true});
 for(const k of ['u','v','um','vm'])m.fields[k].fill(0);m.fields.rhL.fill(1);m.fields.rhM.fill(1);
 const c={id:'core',born:0,age:1800,activeStepSeconds:600,x:40000,y:40000,angle:0,major:7000,minor:4200,updraftArea:Math.PI*4000**2,M:1e9,a:1,supplyRatio:1,convectivePhaseEnergyJ:0};m.cells=[c];
 if(oldSpread){const deposit=m.depositPrecip;let coreIndex=0;m.depositPrecip=function*(a,x,y,major,minor,angle,mass,origin){if(origin==='core'){const width=4000*(.8+.4*coreIndex++/3);major=minor=width;}yield*deposit.call(this,a,x,y,major,minor,angle,mass,origin);};}
 m.captureInitialState();drain(m.release());const p=drain(m.projectProducts()),peak=Math.max(...p.compositeZ);
 assert(Math.abs(m.audit().activityResidual)<1e-12);cases.push({oldSpread,peakDbz:10*Math.log10(peak),releasedKg:c.releasedKgThisStep,groundKg:m.stats.ground,storedKg:Object.values(m.precipWater).reduce((s,a)=>s+sum(a)*m.precip.area,0)});
}
for(const k of ['releasedKg','groundKg','storedKg'])assert(Math.abs(cases[0][k]-cases[1][k])<1e-10*cases[0][k],k+' conserved');
assert(cases[1].peakDbz>cases[0].peakDbz+2,'stronger cores with the same physical water budget');
console.log(JSON.stringify({pass:true,inlets,echoComparison:cases},null,2));
