/* Exercise the production Sol Worker and stored frames through the real page. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'../..'),hours=Number(process.env.SOL_BENCH_HOURS||6);
 const seed=Number(process.env.SOL_BENCH_SEED||20260421);
 const server=http.createServer((req,res)=>{
   const file=path.resolve(root,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
   if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
   res.setHeader('Content-Type',({'.js':'application/javascript','.css':'text/css','.html':'text/html','.json':'application/json'})[path.extname(file)]||'application/octet-stream');
   fs.createReadStream(file).pipe(res);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try{
   browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
   const page=await browser.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route(url=>!['localhost','127.0.0.1'].includes(url.hostname),r=>r.abort());
   await page.goto('http://127.0.0.1:'+server.address().port+'/simulator-sol.html?seed='+seed+'&hours='+hours);
   await page.waitForFunction(()=>window.Simulator&&!document.querySelector('#start-simulation').disabled);
   // Hold the fourth write to test live playback without racing fast devices.
   await page.evaluate(()=>{
     const put=SimulationFrameStore.putRaw;
     SimulationFrameStore.putRaw=async(...args)=>{
       if(args[1]===4)await new Promise(resolve=>{window.releaseTestFrame=resolve;});
       return put(...args);
     };
   });
   await page.locator('#flow-rate').selectOption('0');
   const start=Date.now();await page.locator('#start-simulation').click();
   await page.waitForFunction(()=>window.releaseTestFrame&&Simulator.getState().current===3);
   assert.equal(await page.evaluate(()=>Simulator.getState().computeState),'computing');
   await page.locator('#replay-slider').fill('1');
   await page.waitForFunction(()=>Simulator.getState().current===1);
   assert.equal(await page.evaluate(()=>Simulator.getState().playbackState),'paused');
   await page.evaluate(()=>{window.releaseTestFrame();});
   await page.waitForFunction(()=>['complete','error'].includes(Simulator.getState().computeState),null,{timeout:600000});
   const result=await page.evaluate(()=>{const s=Simulator.getState(),m=s.manifest;return {state:s.computeState,error:s.lastError,
     mesh:m?.physicsMesh,frames:s.replayFrames,seed:m?.config.seed,stations:s.stationCount,timing:m?.timing};});
   assert.equal(result.state,'complete',result.error);assert.equal(result.frames,hours*6+1);assert.equal(result.seed,seed);assert.equal(result.stations,32);
   assert.equal(result.mesh.coreStepSeconds,600);console.log(JSON.stringify({...result,wallSeconds:(Date.now()-start)/1000}));
   await page.waitForFunction(()=>Simulator.getState().frame&&!Simulator.getState().busy);
   assert.equal(await page.evaluate(()=>Simulator.getState().current),1,'worker completion must preserve the reviewed time');
   const edges=await page.evaluate(()=>{
     const s=Simulator.getState(),g=s.manifest.grid,f=s.frame.fields.temperature;
     return {views:s.maps.map(m=>m.bounds.split(',').map(Number)),
       east:SimulationData.sample(f,g,118,23),outside:SimulationData.index(g,118.001,23)};
   });
   for(const [w,s,e,n] of edges.views)assert.ok(w>=104.3-.015&&e<=118+.015&&s>=19.8-.015&&n<=26.7+.015);
   assert.ok(Number.isFinite(edges.east));assert.equal(edges.outside,-1);
   await page.locator('#toggle-playback').click();
   // Verify the ordinary playback and the public station readout.
   await page.locator('#flow-rate').selectOption('0');
   await page.waitForFunction(()=>Simulator.getState().current>0,null,{timeout:30000});
   assert.ok(Number.isFinite(Number(await page.locator('#obs-temperature').innerText())));
   if(hours<=2){
     await page.waitForFunction(()=>Simulator.getState().playbackState==='ended');
     await page.locator('#replay-slider').fill('1');
     await page.waitForFunction(()=>Simulator.getState().current===1 && !Simulator.getState().busy);
     assert.equal(await page.evaluate(()=>Simulator.getState().frame.hour),1/6);
     await page.locator('.map-card select').first().selectOption('rain_hour');
     await page.locator('.map-card select').first().selectOption('reflectivity');
   }
   assert.deepEqual(errors,[]);
 }finally{await browser?.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
