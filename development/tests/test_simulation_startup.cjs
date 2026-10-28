/* Startup only: real browser/runtime/assets, stop before ANY integration step. */
'use strict';
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
 try{
  const page=await browser.newPage(),errors=[],failures=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('requestfailed',request=>{if(request.url().includes('127.0.0.1'))failures.push({url:request.url(),error:request.failure()?.errorText});});
  await page.route('**/MapServer/tile/**',r=>r.abort());await page.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await page.route('**/simulation-local-worker.js*',async route=>{
   const response=await route.fetch(),source=await response.text(),hook="send('manifest',{manifest});";
   assert.ok(source.includes(hook));
   // Leave the real loading and initialization path intact, but block before
   // the target loop. No model.step/advance call or new weather process runs.
   await route.fulfill({response,body:source.replace(hook,hook+'await new Promise(()=>{});')});
  });
  await page.goto((process.env.PREVIEW_URL||'http://127.0.0.1:8765')+'/simulator.html');
  await page.waitForFunction(()=>window.Simulator&&!document.querySelector('#start-simulation').disabled);
  console.log('PAGE',JSON.stringify(await page.evaluate(()=>({stations:Simulator.getState().stationCount,stationMessage:document.querySelector('#station-message').textContent,secure:isSecureContext,uuid:typeof crypto.randomUUID,worker:typeof Worker}))));
  await page.locator('#local-grid').selectOption('12');await page.locator('#local-hours').fill('1');await page.locator('#start-simulation').click();
  await page.waitForFunction(()=>['computing','error'].includes(Simulator.getState().computeState),null,{timeout:90000});
  const result=await page.evaluate(()=>{const s=Simulator.getState();return {status:s.computeState,error:s.lastError,text:document.querySelector('#compute-status').textContent,stations:s.stationCount,seed:s.manifest?.config.seed,frames:s.replayFrames};});
  console.log('STARTUP',JSON.stringify({result,errors,failures}));
  await page.locator('#stop-compute').click();
  assert.equal(result.status,'computing');assert.equal(result.frames,0);assert.equal(result.stations,32);assert.deepEqual(errors,[]);
  console.log('PASS real startup, 32 stations, zero weather integration steps');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
