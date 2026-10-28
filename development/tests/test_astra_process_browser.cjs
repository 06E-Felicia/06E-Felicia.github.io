/* Genuine Astra page/Worker/WASM/storage/playback, not a mock or Sol profile. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'../..'),hours=+(process.env.ASTRA_TEST_HOURS||3),km=+(process.env.ASTRA_TEST_GRID||12),seed=20260421;
 const fetched=new Set(),server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost'),file=path.resolve(root,'.'+decodeURIComponent(url.pathname));
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  fetched.add(url.pathname);res.setHeader('Content-Type',file.endsWith('.js')?'application/javascript':file.endsWith('.wasm')?'application/wasm':file.endsWith('.html')?'text/html':file.endsWith('.json')?'application/json':'application/octet-stream');
  if(url.pathname.endsWith('/simulation-local-worker.js')){
   const source=fs.readFileSync(file,'utf8'),hook="py.globals.set('browser_seed',seed);";
   assert.ok(source.includes(hook));res.end(source.replace(hook,`py.globals.set('browser_seed',${seed});`));return;
  }
  fs.createReadStream(file).pipe(res);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
 try{
  browser=await chromium.launch({headless:true,channel:'chrome'});const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.route('**/MapServer/tile/**',r=>r.abort());await page.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await page.goto('http://127.0.0.1:'+server.address().port+'/simulator.html');await page.waitForFunction(()=>window.Simulator&&!document.querySelector('#start-simulation').disabled);
  await page.locator('#local-grid').selectOption(String(km));await page.locator('#local-hours').fill(String(hours));await page.locator('#frame-interval').selectOption('30');
  const started=Date.now();await page.locator('#start-simulation').click();
  await page.waitForFunction(()=>['complete','error'].includes(Simulator.getState().computeState),null,{timeout:600000});
  await page.waitForFunction(()=>Simulator.getState().frame&&!Simulator.getState().busy);
  const result=await page.evaluate(async()=>{
   const s=Simulator.getState(),run=sessionStorage.getItem('felicia-last-local-run'),raw=JSON.parse(await SimulationFrameStore.getRaw(run,s.replayFrames-1));
   return {edition:s.edition,state:s.computeState,error:s.lastError,manifest:s.manifest,frames:s.replayFrames,fields:Object.keys(raw.fields),audit:raw.audit};
  });
  assert.equal(result.state,'complete',result.error);assert.equal(result.edition,'astra');assert.equal(result.manifest.edition,'astra');
  assert.equal(result.manifest.engine,'4.15.0-rear-circulation');assert.equal(result.manifest.config.grid_km,km);assert.equal(result.manifest.config.seed,seed);
  for(const key of ['u925','v925','u500','v500','u300','v300','mlcape','t3','q3','dbz3','gust','point_rain5'])assert.ok(result.fields.includes(key),key);
  assert.ok(fetched.has('/simulation/synoptic.py'),'new model dependency must really load');assert.ok(Math.abs(result.audit.water_relative_residual)<.002);
  assert.ok(fetched.has('/assets/data/simulation-terrain-detail.npz'),'coastal relief must really load, not just satellite map tiles');
  assert.equal(result.manifest.terrain.coastal_detail.grid_km,.25);
  assert.equal(await page.locator('#start-simulation').isDisabled(),true);assert.equal(await page.locator('#replay-bar').isVisible(),false);
  await page.locator('#flow-rate').selectOption('0');await page.waitForFunction(()=>Simulator.getState().playbackState==='ended');
  assert.equal(await page.locator('#replay-bar').isVisible(),true);assert.deepEqual(errors,[]);
  result.wall_seconds=(Date.now()-started)/1000;
  if(process.env.ASTRA_TEST_OUTPUT)fs.writeFileSync(process.env.ASTRA_TEST_OUTPUT,JSON.stringify(result,null,2));
  console.log('PASS REAL ASTRA',JSON.stringify({hours,grid_km:km,frames:result.frames,wall_seconds:result.wall_seconds,engine:result.manifest.engine,water_residual:result.audit.water_relative_residual}));
 }finally{await browser?.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
