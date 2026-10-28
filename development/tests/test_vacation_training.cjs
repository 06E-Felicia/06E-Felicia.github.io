'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),C=require('../../assets/scripts/vacation-model.js'),Coast=require('../../assets/scripts/vacation-coast.js'),{physical,seedState}=require('./vacation-fixtures.cjs');
const drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;},sum=a=>a.reduce((s,x)=>s+x,0),close=(a,b,t=1e-10)=>assert(Math.abs(a-b)<=t*Math.max(1,Math.abs(a),Math.abs(b)),`${a} != ${b}`);
const config={geography:'idealized',preset:'coast',width:80000,height:80000,hours:6,seed:42,coldMomentumCoupling:'surface_drag',coldSourceGeometry:'rain_footprint'};
function run(){
  C.prepareBackendSync();const result={model:C.VERSION,checks:[]};
  // A uniform layer has no pressure acceleration: ground-relative velocity must
  // decay analytically; the old relative damper instead restores ambient wind.
  const m=new C.Model({...config,coldBoundary:'periodic',coldMixing:false});m.h.fill(100);m.q.fill(250);m.cu.fill(10);m.cv.fill(-4);m.captureInitialState();
  for(let n=0;n<3;n++)drain(m.advanceCold(false));
  for(let k=0;k<m.cold.n;k++){close(10+m.Px[k]/100,10*Math.exp(-3*C.DT/900));close(-4+m.Py[k]/100,-4*Math.exp(-3*C.DT/900));close(m.h[k],100);close(m.q[k],250);}
  const pa=m.sourceAudit().coldMomentum;assert(Math.abs(pa.residual.x)+Math.abs(pa.residual.y)<1e-10*(Math.abs(m.coldMomentumLedger.dampingRemoval.x)+Math.abs(m.coldMomentumLedger.dampingRemoval.y)+m.coldMomentumLedger.transportActivity));result.checks.push('ground drag analytic velocity and explicit momentum budget');
  const s=new C.Model(config),k=s.cold.index(12500,12500),e=s.env.index(12500,12500);s.cu.fill(9);s.cv.fill(5);s.fields.um.fill(6);s.fields.vm.fill(-2);s._addColdSource(k,20,50,e);
  close(9+s.Px[k]/20,6);close(5+s.Py[k]/20,-2);close(s.coldMomentumLedger.source.x,s.Px[k]*s.cold.area);result.checks.push('descending source inherits declared midlevel wind, no massless impulse');
  const r=new C.Model({...config,coldMomentumCoupling:'ambient_relative'}),requests=new Float64Array(r.precip.n*7),accepted=new Float64Array(r.env.n).fill(.37),indices=new Int32Array(r.precip.n);
  for(let i=0;i<r.precip.n;i++)indices[i]=r.env.index((i%r.precip.nx+.5)*r.precip.dx,(Math.floor(i/r.precip.nx)+.5)*r.precip.dx);
  const pk=r.precip.index(5000,5000);requests[pk*7+2]=2e6;requests[pk*7+4]=1e6;drain(r._depositColdEvaporation(requests,accepted,indices));const alpha=2.5e6/(1.15*1004);
  close(sum(r.q)*r.cold.area,alpha*3e6*.37);close(sum(r.h)*r.cold.area,alpha*3e6*.37/2.5);assert.equal(r.q.filter(x=>x>0).length,4);
  const before=r.q.slice();drain(r._depositColdEvaporation(new Float64Array(requests.length),accepted,indices));assert.deepEqual(r.q,before);result.checks.push('2km to 2.5km exact overlap source, conservation, dry no-op');
  const g=new C.Grid(200000,200000,2500),land=new Float64Array(g.n),mask=new Uint8Array(g.n);for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++)land[j*g.nx+i]=mask[j*g.nx+i]=j>=40?1:0;
  const chain=Coast.shoreline(g,land,mask,{x:100000,y:100000},{x:1,y:0}),a=Coast.nearest(chain,100000,110000),b=Coast.nearest(chain,100000,90000);close(a.n,10000);close(b.n,-10000);close(a.nx,0);close(a.ny,1);assert(a.weight>0);assert.equal(Coast.at(chain,1e6),null);assert.deepEqual(chain,Coast.shoreline(g,land,mask,{x:100000,y:100000},{x:1,y:0}));
  // Island cells do not join the mainland chain.
  land[20*g.nx+40]=1;assert.deepEqual(chain,Coast.shoreline(g,land,mask,{x:100000,y:100000},{x:1,y:0}));
  const geometry=Coast.field(chain,g);for(const key of ['s','n','normalX','normalY','weight'])assert(geometry[key].every(Number.isFinite));result.checks.push('straight coast limit, sign, endpoint, island exclusion, deterministic cache');
  const models=['low','standard','high'].map(quality=>new C.Model({...config,quality}));for(const x of models)seedState(x,{dense:true});
  const js=new C.Model({...config,computeBackend:'js'});seedState(js,{dense:true});
  for(let i=0;i<8;i++){for(const x of models)x.step();js.step();physical(models[0],models[1]);physical(models[1],models[2]);physical(js,models[1]);}
  const cp=models[1].checkpoint(),restored=C.Model.restore(cp);for(let i=0;i<3;i++){models[1].step();restored.step();physical(models[1],restored);}
  for(const key of ['coldMomentumCoupling','coldSourceGeometry','coastalConvergenceGeometry']){const bad=structuredClone(cp);delete bad.config[key];assert.throws(()=>C.Model.restore(bad),new RegExp('config\\.'+key));}
  const untouched=models[1].checkpoint(),snapshot=models[1].getSnapshot();assert.deepEqual(models[1].checkpoint(),untouched);assert.equal(snapshot.coldGrid.buffer.byteLength,models[1].cold.n*16);const depth=new Float32Array(snapshot.coldGrid.buffer,0,models[1].cold.n);for(let k=0;k<depth.length;k++)assert.equal(depth[k],Math.fround(models[1].h[k]));assert.notEqual(snapshot.coldGrid.buffer,models[1].h.buffer);result.checks.push('three qualities identical physics, JS/WASM exact, checkpoint continuation, read-only cold products');
  for(const x of models)assert(x.check().activityResidual<1e-7);
  result.negativeControls={};
  for(const kind of ['dry','highCIN']){
    const n=new C.Model({...config,inhibitionOffset:kind==='highCIN'?1000:0,controls:{flow:1,humidity:kind==='dry'?-.8:0}});
    for(let step=0;step<6*3600/C.DT;step++)n.step();
    assert.equal(n.stats.births,0);assert.equal(n.stats.coldBirths,0);assert.equal(sum(n.rainTotal),0);
    result.negativeControls[kind]={hours:6,births:0,coldBirths:0,rain:0,activityResidual:n.check().activityResidual};
  }
  console.log(JSON.stringify(result,null,2));return result;
}
if(require.main===module)run();module.exports={run};
