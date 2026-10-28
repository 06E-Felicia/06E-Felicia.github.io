'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');
C.prepareBackendSync();
const base={geography:'idealized',preset:'coast',width:160000,height:160000,hours:3,seed:42};
function make(extra={}){const m=new C.Model({...base,...extra});const f=m.fields;f.z.fill(0);f.zx.fill(0);f.zy.fill(0);f.u.fill(10);f.v.fill(0);f.rhL.fill(.94);f.rhM.fill(.85);f.el.fill(.85);f.em.fill(.7);f.upperDiv.fill(5e-5);return m;}
function lift(m,div=0,n=60){const k=m.env.index(77500,77500),bg=m.background();for(let t=0;t<n;t++)m._advanceLiftColumn(k,77500,77500,div,bg);return m.gate(77500,77500,0,bg,true);}
// Warm/humid but flat nonconvergent column: neither layer can ignite from
// large-scale upper divergence or numerical time integration alone.
const flat=make();assert.equal(lift(flat).F,0);assert.equal(flat.gate(77500,77500,1,flat.background(),true).F,0);
// Same warm column over a resolved windward slope; reversing the flow makes it
// a lee slope, so local terrain triggering disappears without a location mask.
const ridge=make();for(let j=0;j<ridge.env.ny;j++)for(let i=0;i<ridge.env.nx;i++){const k=j*ridge.env.nx+i;ridge.fields.z[k]=(i+.5)*ridge.env.dx*.025;ridge.fields.zx[k]=.025;}
const windward=lift(ridge);assert(windward.F>.2);assert(windward.evidence.focusedLift.terrainRiseM>400);ridge.fields.u.fill(-10);assert.equal(lift(ridge).F,0);
const noTerrain=make({disableTerrainLift:true});noTerrain.fields.z.set(ridge.fields.z);noTerrain.fields.zx.fill(.025);assert.equal(lift(noTerrain).F,0);
// Sustained mesoscale convergence can lift the same flat column. Transient
// convergence cannot immediately jump the displacement threshold; divergence
// erases the parcel displacement instead of accumulating positive-only lift.
const convergence=make();assert.equal(lift(convergence,-3e-4,1).F,0);assert(lift(convergence,-3e-4,90).F>0);assert.equal(lift(convergence,3e-4,90).F,0);
// The marine inflow has both a finite cross-axis width and a finite terminus.
const focus=make();focus.coastalGeometry={options:{},crossing:{x:80000,y:40000},axisDirection:{x:0,y:1},exit:{x:80000,y:80000}};const bg=focus.background();assert(focus._inflowFocus(80000,40000,bg)>0);assert.equal(focus._inflowFocus(80000,160000,bg),0);assert.equal(focus._inflowFocus(400000,40000,bg),0);
// Restoration keeps all lift memories; quality cannot feed back into physics.
const m=make();for(let t=0;t<6;t++)m.step();const cp=m.checkpoint(),restored=C.Model.restore(cp);m.step();restored.step();for(const k of Object.keys(m.fields))assert.deepEqual(m.fields[k],restored.fields[k],k);
const broken=structuredClone(cp);delete broken.arrays.field_xiConvergence;assert.throws(()=>C.Model.restore(broken),/xiConvergence/);
const untouched=m.checkpoint(),snap=m.getSnapshot();assert.deepEqual(m.checkpoint(),untouched);assert.equal(snap.triggerGrid.buffer.byteLength,m.env.n*12);assert.notEqual(snap.triggerGrid.buffer,m.fields.xiTerrain.buffer);
const scenario=require('../../assets/scripts/vacation-scenario.js');
for(let seed=0;seed<256;seed++){const c=scenario.generate({seed},seed);assert(['coastal','terrain'].includes(c.scenarioGroup));assert.equal(c.hours,72);}
for(const scenarioGroup of ['afternoon','fastline'])assert.equal(scenario.generate({seed:1,scenarioGroup},1).scenarioGroup,scenarioGroup);
console.log(JSON.stringify({model:C.VERSION,checks:['flat moist no-trigger / upper divergence no-trigger','windward trigger and wind reversal','terrain removal','sustained convergence / transient rejection / signed descent','finite marine footprint','checkpoint exact continuation'],windwardGate:windward.F},null,2));
