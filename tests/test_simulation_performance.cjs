/* Repeatable real-WASM timing, using a test-only fixed seed in the Worker. */
'use strict';
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1400,height:1000}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/MapServer/tile/**',r=>r.abort());await page.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await page.route('**/simulation-local-worker.js*',async route=>{
   const response=await route.fetch();let source=await response.text();
   const random='crypto.getRandomValues(new Uint32Array(1))[0]%2147483646+1';
   assert.ok(source.includes(random),'test seed hook matches actual Worker');
   source=source.replace(random,'20260421');
   if(process.env.BENCH_BACKEND==='force-fused')source=source.replace("send('manifest',{manifest});",`await py.runPythonAsync("from simulation import numerics\\nnumerics.install_accelerator(simulationAdvectionKernel)");manifest.acceleration.selected.transport='fused-test-override';send('manifest',{manifest});`);
   if(process.env.DEBUG_NUMERICS)source=source.replace("send('manifest',{manifest});",`console.log('DEBUG_BACKEND',JSON.stringify(manifest.acceleration));await py.runPythonAsync("import numpy as np\\nnp.seterr(divide='raise',invalid='raise',over='raise')");send('manifest',{manifest});`);
   if(process.env.BENCH_BACKEND==='numpy')source=source.replace('install_accelerator(simulationAdvectionKernel)','install_accelerator(None)');
   if(['numpy','transport','force-fused'].includes(process.env.BENCH_BACKEND))source=source.replace('install_moist_accelerator(simulationMoistKernel)','install_moist_accelerator(None)');
   source=source.replace('self.postMessage({type,...payload})',"(type==='complete'&&console.log('COMPUTE_TIMING',JSON.stringify(payload)),self.postMessage({type,...payload}))");
   if(process.env.CHECK_KERNEL){
    const hook="py.globals.set('browser_seed',seed);";
    assert.ok(source.includes(hook),'kernel comparison must run after actual seeded Worker initialization');
    source=source.replace(hook,`const checkFile=await fetch(new URL('simulation/check_acceleration.py',base));py.FS.writeFile('/home/pyodide/simulation/check_acceleration.py',await checkFile.text());console.log('ACCELERATION_CHECK',await py.runPythonAsync('import json\\nfrom simulation.check_acceleration import check\\njson.dumps(check())'));${hook}`);
   }
   await route.fulfill({response,body:source});
  });
  await page.goto((process.env.PREVIEW_URL||'http://127.0.0.1:8765')+'/simulator.html');
  page.on('console',message=>{if(/ACCELERATION_CHECK|COMPUTE_TIMING|DEBUG_BACKEND/.test(message.text()))console.log(message.text());});
  await page.locator('#local-grid').selectOption(process.env.BENCH_GRID||'6');
  await page.locator('#local-hours').fill(process.env.BENCH_HOURS||'1');
  await page.locator('#compute-mode').selectOption(process.env.BENCH_COMPACT?'compact':'accurate');
  await page.locator('#frame-interval').selectOption(process.env.BENCH_INTERVAL||'10');
  await page.locator('#flow-rate').selectOption('60');const started=Date.now();
  await page.locator('#start-simulation').click();
  await page.waitForFunction(()=>['complete','error'].includes(Simulator.getState().computeState),null,{timeout:600000});
  const stats=await page.evaluate(()=>{const s=Simulator.getState();return {status:s.computeState,error:s.lastError,config:s.manifest?.config,frames:s.replayFrames,text:document.querySelector('#compute-status').textContent,engine:s.manifest?.engine,acceleration:s.manifest?.acceleration};});
  stats.wall_seconds=(Date.now()-started)/1000;
  stats.backend=process.env.BENCH_BACKEND||'auto';
  assert.equal(stats.status,'complete',stats.text+' '+(stats.error||''));assert.deepEqual(errors,[]);
  assert.equal(stats.config.seed,20260421);
  assert.equal(stats.frames,Math.round(stats.config.hours*60/stats.config.frame_minutes)+1);
  console.log('PASS real-WASM benchmark',JSON.stringify(stats));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
