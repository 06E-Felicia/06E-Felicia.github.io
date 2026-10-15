/* Slow synthetic tiles expose zoom blanking without depending on the network.
   Weather fields are genuine packed process frames, not drawn test echoes. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const data=process.env.SIM_TEST_RUN;if(!data)throw Error('Set SIM_TEST_RUN to a completed simulation directory');
 const manifest=JSON.parse(fs.readFileSync(path.join(data,'manifest.json'),'utf8'));
 const frames=manifest.frames.slice(0,3).map(f=>zlib.gunzipSync(fs.readFileSync(path.join(data,f.file))).toString('utf8'));
 const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1080}}),errors=[];let slowTiles=false;
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(({manifest,frames})=>{window.Worker=class{
   constructor(){this.index=0;}
   postMessage(message){if(message.type==='start'){this.onmessage({data:{type:'manifest',manifest:{...manifest,status:'running',frames:[],config:{...manifest.config,hours:2}}}});this.emit();}
    else if(message.type==='ack'){if(++this.index<frames.length)this.emit();else this.onmessage({data:{type:'complete'}});}}
   emit(){this.onmessage({data:{type:'frame',index:this.index,hour:JSON.parse(frames[this.index]).hour,raw:frames[this.index]}});}
   terminate(){}
  };},{manifest,frames});
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.hostname==='server.arcgisonline.com'&&url.pathname.includes('/tile/')){
    if(slowTiles)await new Promise(resolve=>setTimeout(resolve,450));
    return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#425c65"/><path d="M0 0H256V256H0Z M128 0V256 M0 128H256" stroke="#56747c" fill="none"/></svg>'});
   }
   if(url.origin!=='http://127.0.0.1:14332')return route.abort();
   const file=path.resolve(process.cwd(),'.'+url.pathname);
   if(!file.startsWith(process.cwd()+path.sep)||!fs.existsSync(file))return route.fulfill({status:404,body:''});
   if(url.pathname==='/assets/vendor/leaflet/leaflet.js')return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(file,'utf8')+'\n;window.__zoomMaps=[];L.Map.addInitHook(function(){const record={map:this,resets:0,animations:0};window.__zoomMaps.push(record);this.on("viewreset",()=>record.resets++);this.on("zoomanim",()=>record.animations++);});'});
   return route.fulfill({path:file});
  });
  await page.goto('http://127.0.0.1:14332/simulator.html');
  await page.waitForFunction(()=>window.Simulator&&Simulator.getState().stationCount===32);
  await page.locator('[data-layout="4"]').click();await page.locator('#flow-rate').selectOption('60');
  await page.locator('#start-simulation').click();
  await page.waitForFunction(()=>Simulator.getState().frame&&!Simulator.getState().busy);
  await page.locator('#stop-compute').click();await page.locator('#view-prd').click();
  const settled=()=>{const maps=Simulator.getState().maps;if(maps.length!==4)return false;const p=L.CRS.EPSG3857.latLngToPoint(maps[0].center,maps[0].zoom);return maps.every(m=>m.zoom===maps[0].zoom&&L.CRS.EPSG3857.latLngToPoint(m.center,m.zoom).distanceTo(p)<=.8)&&!document.querySelector('.leaflet-zoom-anim');};
  await page.waitForFunction(settled);await page.waitForTimeout(650);
  await page.waitForFunction(()=>[...document.querySelectorAll('.weather-map')].every(el=>el.querySelectorAll('.leaflet-tile-loaded').length>0));
  slowTiles=true;
  for(const [index,delta] of [[0,-150],[1,150],[3,-250],[0,5000]]){
   await page.locator('.weather-map').nth(index).scrollIntoViewIfNeeded();
   const before=await page.evaluate(()=>window.__zoomMaps.filter(x=>x.map.getContainer().isConnected).map(x=>({resets:x.resets,animations:x.animations})));
   const builds=await page.evaluate(()=>Simulator.getState().maps.map(m=>m.rasterBuilds));
   await page.evaluate(()=>{window.__zoomSamples=[];const until=performance.now()+1200;function sample(){const rows=[...document.querySelectorAll('.weather-map')].map(el=>{
     const r=el.getBoundingClientRect(),image=el.querySelector('.weather-raster');
     const visible=[...el.querySelectorAll('.leaflet-tile-loaded')].filter(tile=>+getComputedStyle(tile).opacity>.05).map(tile=>tile.getBoundingClientRect());
     let coverage=0;for(const x of [.2,.5,.8])for(const y of [.2,.5,.8])if(visible.some(t=>t.left<=r.left+r.width*x&&t.right>=r.left+r.width*x&&t.top<=r.top+r.height*y&&t.bottom>=r.top+r.height*y))coverage++;
     return {tiles:visible.length,coverage,raster:!!image&&image.complete&&image.naturalWidth>0&&getComputedStyle(image).visibility!=='hidden',animated:!!el.querySelector('.leaflet-zoom-anim')};
    });window.__zoomSamples.push(rows);if(performance.now()<until)requestAnimationFrame(sample);}requestAnimationFrame(sample);});
   const box=await page.locator('.weather-map').nth(index).boundingBox();
   await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.wheel(0,delta);
   await page.waitForTimeout(1250);await page.waitForFunction(settled);
   const result=await page.evaluate(()=>({samples:window.__zoomSamples,records:window.__zoomMaps.filter(x=>x.map.getContainer().isConnected).map(x=>({resets:x.resets,animations:x.animations})),builds:Simulator.getState().maps.map(m=>m.rasterBuilds)}));
   assert.ok(result.samples.length>10);
   assert.ok(result.samples.every(rows=>rows.every(r=>r.tiles>0)),'old loaded tiles must survive while delayed new zoom tiles load');
   assert.ok(result.samples.every(rows=>rows.every(r=>r.coverage===9)),'the retained base map must cover all nine interior sample points, including large regional zoom-outs');
   assert.ok(result.samples.every(rows=>rows.every(r=>r.raster)),'weather raster must remain visible across zoom');
   assert.ok(result.samples.some(rows=>rows.every(r=>r.animated)),'all four maps must zoom together, not in successive waves');
   assert.deepEqual(result.records.map(x=>x.resets),before.map(x=>x.resets),'ordinary wheel zoom must not hard-reset any map');
   assert.deepEqual(result.builds,builds,'zoom must reuse the meteorological raster');
   console.log('PASS continuous zoom',JSON.stringify({source:index,delta,sampledFrames:result.samples.length,minLoadedTiles:Math.min(...result.samples.flat().map(r=>r.tiles)),minNinePointCoverage:Math.min(...result.samples.flat().map(r=>r.coverage))}));
  }
  await page.locator('.weather-map').nth(2).scrollIntoViewIfNeeded();
  const burstBefore=await page.evaluate(()=>window.__zoomMaps.filter(x=>x.map.getContainer().isConnected).map(x=>x.resets));
  const burstBox=await page.locator('.weather-map').nth(2).boundingBox();
  await page.mouse.move(burstBox.x+burstBox.width*.5,burstBox.y+burstBox.height*.5);
  for(const delta of [-100,-100,100,-180,100]){await page.mouse.wheel(0,delta);await page.waitForTimeout(80);}
  await page.waitForFunction(settled);await page.waitForTimeout(650);
  assert.deepEqual(await page.evaluate(()=>window.__zoomMaps.filter(x=>x.map.getContainer().isConnected).map(x=>x.resets)),burstBefore,'rapid wheel reversals must not hard-reset maps or create feedback loops');
  assert.ok(await page.evaluate(()=>[...document.querySelectorAll('.weather-map')].every(el=>el.querySelector('.leaflet-tile-loaded')&&el.querySelector('.weather-raster')?.complete)));
  console.log('PASS rapid wheel reversals and final four-map alignment');
  assert.ok(await page.evaluate(()=>[...document.querySelectorAll('.weather-map')].every(el=>el.querySelector('.leaflet-overlay-pane svg')&&!el.querySelector('.leaflet-overlay-pane canvas'))),'map vectors use retained SVG rather than a cleared zoom canvas');
  assert.ok(await page.evaluate(()=>Simulator.getState().maps.every(m=>m.zoom>=m.minZoom)));
  assert.deepEqual(errors,[]);
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
