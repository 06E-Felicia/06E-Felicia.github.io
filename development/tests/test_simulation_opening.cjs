/* File URL guidance and real HTTP loading. No weather integration. */
'use strict';
const assert=require('node:assert/strict'),path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
 try{
  const context=await browser.newContext(),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/MapServer/tile/**',r=>r.abort());await page.route('**/tile.openstreetmap.org/**',r=>r.abort());
  for(const file of ['simulator.html','simulator-sol.html']){
   await page.goto(pathToFileURL(path.resolve(__dirname,'../..',file)).href);
   await page.waitForFunction(()=>window.Simulator&&Simulator.getState().computeState==='error');
   assert.equal(await page.locator('#start-simulation').isDisabled(),true);
   assert.match(await page.locator('#compute-status').innerText(),/启动本地预览.command/);
   assert.equal(await page.evaluate(()=>Simulator.getState().manifest),null);
  }
  const base=process.env.PREVIEW_URL||'http://127.0.0.1:8766';
  for(const file of ['simulator.html','simulator-sol.html']){
   await page.goto(base+'/'+file);
   await page.waitForFunction(()=>window.Simulator&&!document.querySelector('#start-simulation').disabled);
   assert.equal(await page.locator('#station-select option').count(),32);
   assert.equal(await page.evaluate(()=>Simulator.getState().lastError),null);
  }
  assert.deepEqual(errors,[]);
  console.log('PASS file:// clear guidance + disabled start; HTTP Astra/Sol ready with 32 stations; zero simulation');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
