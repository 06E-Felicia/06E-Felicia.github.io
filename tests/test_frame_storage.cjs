'use strict';
const assert=require('node:assert/strict'),{chromium,webkit}=require('playwright');
(async()=>{for(const [engine,type]of [['chrome',chromium],['webkit',webkit]]){
 const browser=await type.launch({headless:true,...(engine==='chrome'?{channel:'chrome'}:{})});
 try{for(const fault of ['none','pending','blocked','transaction','no-gzip']){
  const page=await browser.newPage();await page.route('**/MapServer/tile/**',r=>r.abort());await page.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await page.addInitScript(fault=>{
   if(fault==='pending'||fault==='blocked')Object.defineProperty(window,'indexedDB',{value:{open(){const request={};if(fault==='blocked')setTimeout(()=>request.onblocked?.(),0);return request;}}});
   if(fault==='transaction')Object.defineProperty(window,'indexedDB',{value:{open(){const request={result:{close(){},transaction(){return {objectStore(){return {put(){return {}},get(){return {}}};},abort(){this.onabort?.();}};}}};setTimeout(()=>request.onsuccess?.(),0);return request;}}});
   if(fault==='no-gzip')Object.defineProperty(window,'CompressionStream',{value:undefined});
  },fault);
  await page.goto('http://127.0.0.1:8766/simulator-sol.html');
  const result=await page.evaluate(async()=>{const start=performance.now(),backend=await SimulationFrameStore.prepare(),run=crypto.randomUUID(),other=crypto.randomUUID(),raw=JSON.stringify({hour:1,test:'雷雨'.repeat(1000)});await SimulationFrameStore.putRaw(run,0,raw);await SimulationFrameStore.putRaw(other,0,'other');const got=await SimulationFrameStore.getRaw(run,0);await SimulationFrameStore.remove(run);let removed=false;try{await SimulationFrameStore.getRaw(run,0);}catch(_){removed=true;}const retained=await SimulationFrameStore.getRaw(other,0);await SimulationFrameStore.remove(other);return {backend,elapsed:performance.now()-start,ok:got===raw,removed,retained};});
  assert.equal(result.ok,true);assert.equal(result.removed,true);assert.equal(result.retained,'other');assert.ok(result.elapsed<15000);assert.equal(result.backend,['pending','blocked','transaction'].includes(fault)?'cache':'idb');console.log('STORAGE',engine,fault,JSON.stringify(result));await page.close();
 }}finally{await browser.close();}
}})().catch(e=>{console.error(e);process.exitCode=1;});
