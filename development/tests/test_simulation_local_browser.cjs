/* Real Pyodide worker, real same-origin Python/DEM, no mocked computation. */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/MapServer/tile/**',r=>r.abort());await context.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await page.goto('http://127.0.0.1:8765/simulator.html');
  await page.waitForFunction(()=>window.Simulator);
  assert.equal(await page.locator('#play,#timeline,#reload,#follow-live').count(),0);
  assert.equal(await page.evaluate(()=>Simulator.getState().manifest),null);
  await page.locator('#local-grid').selectOption('12');await page.locator('#local-hours').fill('1');await page.locator('#flow-rate').selectOption('60');
  await page.locator('#start-simulation').click();
  await page.waitForFunction(()=>Simulator.getState().replayFrames>=1,null,{timeout:120000});
  assert.equal(await page.evaluate(()=>Simulator.getState().frame),null,'no partial weather display during computation');
  assert.equal(await page.locator('#replay-bar').isVisible(),false);
  const complete=async()=>{await page.waitForFunction(()=>Simulator.getState().computeState==='error'||Simulator.getState().computeState==='complete'&&Simulator.getState().frame,null,{timeout:240000});const s=await page.evaluate(()=>({status:Simulator.getState().computeState,text:document.querySelector('#compute-status').textContent,manifest:Simulator.getState().manifest,current:Simulator.getState().current,hour:Simulator.getState().frame?.hour}));assert.equal(s.status,'complete',s.text);return s;};
  const first=await complete();assert.equal(first.current,0);assert.equal(first.hour,0);assert.equal(first.manifest.execution,'browser');
  assert.equal(await page.locator('#initialization').isVisible(),false);assert.equal(await page.locator('#start-simulation').isDisabled(),true);assert.equal(await page.locator('#replay-bar').isVisible(),false);
  assert.equal(await page.evaluate(()=>Simulator.getState().playbackState),'playing');
  await page.waitForTimeout(1000);assert.equal(await page.evaluate(()=>Simulator.getState().current),0,'slow playback does not throttle computation');
  await page.locator('#flow-rate').selectOption('0');await page.waitForFunction(()=>Simulator.getState().playbackState==='ended');
  assert.equal(await page.evaluate(()=>Simulator.getState().frame.hour),1);
  assert.equal(await page.locator('#replay-bar').isVisible(),true);
  await page.locator('#replay-slider').evaluate(el=>{el.value=0;el.dispatchEvent(new Event('input',{bubbles:true}));});await page.waitForFunction(()=>Simulator.getState().frame.hour===0&&!Simulator.getState().busy);
  await page.locator('#replay-slider').evaluate(el=>{el.value=6;el.dispatchEvent(new Event('input',{bubbles:true}));});await page.waitForFunction(()=>Simulator.getState().frame.hour===1&&!Simulator.getState().busy);
  console.log('FIRST',first.manifest.config.seed,first.text);
  await page.locator('#flow-rate').selectOption('60');await page.locator('#start-simulation').click();const second=await complete();
  assert.notEqual(first.manifest.config.seed,second.manifest.config.seed);assert.notDeepEqual(['moisture','jet','shear','trough'].map(k=>first.manifest.config[k]),['moisture','jet','shear','trough'].map(k=>second.manifest.config[k]));
  console.log('SECOND',second.manifest.config.seed,second.text);
  await page.locator('#stop-compute').click();assert.equal(await page.locator('#start-simulation').isDisabled(),false);await page.locator('#local-hours').fill('72');await page.locator('#start-simulation').click();await page.locator('#stop-compute').click();
  assert.equal(await page.locator('#replay-bar').isVisible(),false);
  assert.equal(await page.evaluate(()=>Simulator.getState().computeState),'stopped');
  await page.waitForTimeout(1000);assert.equal(await page.evaluate(()=>Simulator.getState().manifest),null);
  await page.screenshot({path:'/private/tmp/felicia-local-controls.png',fullPage:true});
  assert.ok(await page.evaluate(()=>Simulator.getState().cacheSize<=1));
  assert.deepEqual(errors,[]);console.log('PASS real WASM compute-first twice, fresh environments, locked start, initialization progress, auto playback, adjustable speed, compressed seek, immediate cancellation, no stale result.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
