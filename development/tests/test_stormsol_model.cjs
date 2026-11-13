'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const S=require('../../assets/scripts/stormsol-model.js');require('../../assets/scripts/stormsol-frame.js');
const F=globalThis.StormSolFrame,buf=fs.readFileSync(path.join(__dirname,'../../assets/data/stormsol-terrain.u16'));
const terrain=new Uint16Array(buf.buffer,buf.byteOffset,buf.length/2);
const sum=field=>field.reduce((s,v)=>s+v,0);
const seed=20260421,m=new S.Model(seed,terrain),manifest=F.manifest(m,seed,72);
assert.deepEqual([m.water.length,m.cold.length,m.rate.length,m.total.length],[280*154,560*308,700*385,1400*770]);
assert.notDeepEqual(m.config,S.environment(seed+1));
// Check the wind sampled by the atlas and station, including the cold-pool
// blend, instead of testing the sign of a background constant.
function checkColdWind(display){
  let found=0;
  for(let k=0;k<m.rate.length;k+=37){
    if(display.fields.coldair.read(k)<.9)continue;
    for(const level of [10,925])assert.ok(display.fields['v'+level].read(k)<0,'postfrontal low-level wind must blow southward');
    found++;
  }
  assert.ok(found>0);
}
const n=process.env.SOL_FULL==='1'?432:72,since=performance.now();
let peak5=0,peakRate=0;
for(let i=0;i<n;i++){
  m.advance();
  for(const r of m.last5)peak5=Math.max(peak5,r);
  for(const r of m.rate)peakRate=Math.max(peakRate,r);
}
const rain=sum(m.total),residual=(sum(m.water)*25+sum(m.ice)*4+rain+m.exportedIce-m.initialMass-m.fluxIn)/m.initialMass;
assert.ok(Math.abs(residual)<2e-5);assert.ok(Math.abs(rain-m.rainMass)<.00001*rain);
assert.ok(m.births.warm>0 && peakRate>20);
const snap=F.snapshot(m),display=F.frame(snap,manifest);
let i=0;
for(let j=0;j<m.total.length;j++)if(m.total[j]>m.total[i])i=j;
assert.ok(Math.abs(display.fields.point_rain_total.read(i)-m.total[i])<.051);
assert.ok(m.hour[i]<=m.total[i]+1e-4);
if(n===432){checkColdWind(display);assert.ok(m.births.front>0 && m.births.outflow>0);assert.ok(peak5>=8);}
else{
  const copy=new S.Model(seed,terrain);
  for(let j=0;j<n;j++)copy.advance();
  assert.deepEqual(m.births,copy.births);assert.deepEqual(m.total,copy.total);
}
console.log(JSON.stringify({hours:n/6,seconds:(performance.now()-since)/1000,births:m.births,peak5,peakRate,residual}));
