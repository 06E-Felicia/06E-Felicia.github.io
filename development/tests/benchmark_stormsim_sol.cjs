/* Real browser + real Python/WASM, including compressed frame storage. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'../..'),hours=+(process.env.SOL_BENCH_HOURS||72),seed=+(process.env.SOL_BENCH_SEED||20260421);
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost'),file=path.resolve(root,'.'+decodeURIComponent(url.pathname));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.wasm')?'application/wasm':file.endsWith('.html')?'text/html':file.endsWith('.json')?'application/json':file.endsWith('.css')?'text/css':'application/octet-stream');
  if(url.pathname.endsWith('/simulation-local-worker.js')){
   const source=fs.readFileSync(file,'utf8'),hook='const send=(type,payload={})=>self.postMessage({type,...payload});';
   assert.ok(source.includes(hook));let body=source.replace(hook,"const send=(type,payload={})=>{if(type==='frame')console.log('STORMSIM_AUDIT',JSON.stringify({index:payload.index,...JSON.parse(payload.raw).audit}));self.postMessage({type,...payload});};");
   if(process.env.SOL_CHECK_KERNEL){const seedHook="py.globals.set('browser_seed',seed);";assert.ok(body.includes(seedHook));body=body.replace(seedHook,`const checkFile=await fetch(new URL('simulation/check_acceleration.py',base));py.FS.writeFile('/home/pyodide/simulation/check_acceleration.py',await checkFile.text());console.log('STORMSIM_KERNEL',await py.runPythonAsync('import json\\nfrom simulation.check_acceleration import check\\njson.dumps(check(include_model=False))'));${seedHook}`);}
   res.end(body);return;
  }
  fs.createReadStream(file).pipe(res);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try{
  browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],audits=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',message=>{if(message.text().startsWith('STORMSIM_KERNEL'))console.log(message.text());});
  page.on('console',message=>{if(message.text().startsWith('STORMSIM_AUDIT ')){const audit=JSON.parse(message.text().slice(15));audits.push(audit);if(audit.hours%6===0)console.log('PROGRESS',JSON.stringify({hour:audit.hours,elapsed_s:(Date.now()-started)/1000,rain:audit.max_rain_mm_h,cold:audit.coldpool_depth_max_m}));}});
  await page.route('**/MapServer/tile/**',r=>r.abort());await page.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port+'/simulator-sol.html?seed='+seed+'&hours='+hours);
  await page.waitForFunction(()=>window.Simulator&&!document.querySelector('#start-simulation').disabled);
  assert.equal(await page.locator('h1').innerText(),'StormSim 2.5 Sol');
  const started=Date.now();await page.locator('#start-simulation').click();
  await page.waitForFunction(()=>['complete','error'].includes(Simulator.getState().computeState),null,{timeout:600000});
  const wall=(Date.now()-started)/1000,result=await page.evaluate(()=>{const s=Simulator.getState();return {status:s.computeState,error:s.lastError,manifest:s.manifest,frames:s.replayFrames,stations:s.stationCount};});
  assert.equal(result.status,'complete',result.error);assert.equal(result.frames,hours+1);assert.equal(result.stations,32);
  assert.equal(result.manifest.edition,'sol');assert.equal(result.manifest.config.seed,seed);assert.equal(result.manifest.grid.z_agl_m.length,14);
  assert.ok(audits.length===hours+1);assert.ok(audits.every(a=>Math.abs(a.water_relative_residual)<.002));assert.ok(audits.every(a=>a.max_cfl<=.450001));
  await page.waitForFunction(()=>Simulator.getState().frame&&!Simulator.getState().busy);
  assert.equal(await page.locator('#start-simulation').isDisabled(),true);assert.equal(await page.locator('#replay-bar').isVisible(),false);
  await page.locator('#flow-rate').selectOption('0');await page.waitForFunction(()=>Simulator.getState().playbackState==='ended');
  assert.equal(await page.locator('#replay-bar').isVisible(),true);assert.equal(await page.evaluate(()=>Simulator.getState().frame.hour),hours);
  const peak=audits.reduce((a,b)=>b.coldpool_depth_max_m>a.coldpool_depth_max_m?b:a);
  if(process.env.SOL_BENCH_FIELDS){
   const fields=await page.evaluate(async()=>{const run=sessionStorage.getItem('felicia-last-local-run'),count=Simulator.getState().replayFrames,rows=[];for(let i=0;i<count;i++){const raw=JSON.parse(await SimulationFrameStore.getRaw(run,i));rows.push({hour:raw.hour,fields:Object.fromEntries(['composite','rainrate','rain_total','rain_hour','coldpool','coldpool_depth','coldair','organization','gust'].map(k=>[k,raw.fields[k]]))});}return rows;});
   fs.writeFileSync(process.env.SOL_BENCH_FIELDS,JSON.stringify({manifest:result.manifest,fields}));
  }
  await page.locator('#replay-slider').fill(String(peak.index));await page.waitForFunction(i=>Simulator.getState().current===i&&!Simulator.getState().busy,peak.index);
  await page.screenshot({path:'/private/tmp/stormsim-sol-'+seed+'.png',fullPage:true});
  assert.deepEqual(errors,[]);
  const summary={hours,seed,wall_seconds:wall,grid_km:result.manifest.grid.nominal_km,shape:[result.manifest.grid.ny,result.manifest.grid.nx],frames:result.frames,acceleration:result.manifest.acceleration,timing:result.manifest.timing,
    max_rain:Math.max(...audits.map(a=>a.max_rain_mm_h)),max_core_rain:Math.max(...audits.map(a=>a.core_rain_max_mm_h)),max_total_rain:Math.max(...audits.map(a=>a.total_rain_max_mm)),max_cold_depth:peak.coldpool_depth_max_m,max_water_residual:Math.max(...audits.map(a=>Math.abs(a.water_relative_residual))),
    gust_peak_m_s:Math.max(...audits.map(a=>a.gust_peak_m_s||0)),meanwind_peak_m_s:Math.max(...audits.map(a=>a.meanwind_peak_m_s||0)),point_rain5_peak_mm:Math.max(...audits.map(a=>a.point_rain5_peak_mm)),point_total_max_mm:Math.max(...audits.map(a=>a.point_total_max_mm))};
  if(process.env.SOL_BENCH_OUTPUT)fs.writeFileSync(process.env.SOL_BENCH_OUTPUT,JSON.stringify({summary,manifest:result.manifest,audits},null,2));
  console.log('RESULT REAL SOL',JSON.stringify(summary));
  if(hours===72)assert.ok(wall<300,'72-hour run exceeds the five-minute target on this test device: '+wall);
  console.log('PASS REAL SOL full process, budget, replay and performance');
  if(process.env.SOL_BENCH_CHECK_FRESH){
   const seeds=[seed],environments=[];
   for(let round=0;round<2;round++){
    await page.locator('#local-hours').fill('1');await page.locator('#flow-rate').selectOption('0');await page.locator('#start-simulation').click();
    await page.waitForFunction(()=>['complete','error'].includes(Simulator.getState().computeState),null,{timeout:60000});
    const fresh=await page.evaluate(()=>{const s=Simulator.getState();return {state:s.computeState,error:s.lastError,config:s.manifest.config};});
    assert.equal(fresh.state,'complete',fresh.error);assert.ok(!seeds.includes(fresh.config.seed));seeds.push(fresh.config.seed);environments.push(fresh.config);
    await page.waitForFunction(()=>Simulator.getState().playbackState==='ended');
   }
   assert.ok(['moisture','jet','shear','trough','sst_c'].some(k=>environments[0][k]!==environments[1][k]));
   console.log('PASS real fresh starts',JSON.stringify({seeds}));
  }
 }finally{await browser?.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
