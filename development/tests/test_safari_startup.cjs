/* Real Safari-engine runtime and first saved frames; not a mock Worker. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),{webkit,devices}=require('playwright');
(async()=>{
 const browser=await webkit.launch({headless:true}),results=[];
 try{for(const edition of (process.env.TEST_EDITION?[process.env.TEST_EDITION]:['astra','sol'])){
  const context=await browser.newContext({...devices['iPhone 13']});const page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/MapServer/tile/**',r=>r.abort());await page.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await page.goto((process.env.PREVIEW_URL||'http://127.0.0.1:8766')+'/simulator'+(edition==='sol'?'-sol':'')+'.html');
  await page.waitForFunction(()=>window.Simulator&&!document.querySelector('#start-simulation').disabled);
  if(edition==='astra'){assert.equal(await page.locator('#local-grid').inputValue(),'12');assert.equal(await page.locator('#compute-mode').inputValue(),'compact');}
  await page.locator('#local-hours').fill('1');await page.locator('#start-simulation').click();
  await page.waitForFunction(()=>Simulator.getState().replayFrames>=1||Simulator.getState().computeState==='error',null,{timeout:180000});
  await page.waitForFunction(()=>Simulator.getState().computeState==='error'||Number(document.querySelector('#compute-progress').value)>0,null,{timeout:180000});
  const state=await page.evaluate(()=>{const s=Simulator.getState();return {edition:s.edition,state:s.computeState,error:s.lastError,frames:s.replayFrames,progress:document.querySelector('#compute-progress').value,storage:SimulationFrameStore.getBackend(),grid:s.manifest?.grid,engine:s.manifest?.engine,source_sha256:s.manifest?.source_sha256,terrain:s.manifest?.terrain};});
  results.push(state);
  console.log('SAFARI',JSON.stringify(state));assert.notEqual(state.state,'error',state.error);assert.ok(state.frames>=1);assert.ok(state.progress>0);assert.deepEqual(errors,[]);
  if(edition==='sol'){
   await page.waitForFunction(()=>['complete','error'].includes(Simulator.getState().computeState),null,{timeout:180000});
   await page.waitForFunction(()=>Simulator.getState().frame&&!Simulator.getState().busy);
   assert.equal(await page.evaluate(()=>Simulator.getState().computeState),'complete');
   assert.equal(await page.evaluate(()=>Simulator.getState().frame.fields.point_rain5.shape.length),2);
   console.log('SAFARI Sol complete + compressed replay + subgrid rain decoding');
  }
  await page.locator('#stop-compute').click();await context.close();
 }if(process.env.SAFARI_TEST_OUTPUT)fs.writeFileSync(process.env.SAFARI_TEST_OUTPUT,JSON.stringify({scope:'WebKit/iPhone viewport startup and first stored frame; not physical-iPhone full-process verification',results},null,2));}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
