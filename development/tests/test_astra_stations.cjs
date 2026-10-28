/* Interaction-only: never starts a worker or a weather calculation. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
 try{
  const root=path.resolve(__dirname,'../..'),stations=JSON.parse(fs.readFileSync(path.join(root,'assets/data/simulator-stations.json'))).stations;
  const setup=async options=>{
   const context=await browser.newContext(options);await context.route('**/*',route=>{
    const url=new URL(route.request().url());if(url.origin!=='http://127.0.0.1:14331')return route.abort();
    const file=path.resolve(root,'.'+url.pathname);if(!file.startsWith(root+path.sep)||!fs.existsSync(file))return route.fulfill({status:404,body:''});
    if(url.pathname.endsWith('/leaflet.js'))return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(file,'utf8')+'\n;window.__stationMaps=[];L.Map.addInitHook(function(){window.__stationMaps.push(this);});'});
    return route.fulfill({path:file});
   });
   const page=await context.newPage();page.on('pageerror',e=>{throw e;});await page.goto('http://127.0.0.1:14331/'+(process.env.TEST_EDITION==='sol'?'simulator-sol.html':'simulator.html'));
   await page.waitForFunction(()=>window.Simulator&&Simulator.getState().stationCount===32&&!document.querySelector('#start-simulation').disabled);return {page,context};
  };
  const {page,context}=await setup({viewport:{width:1440,height:1000}});
  const position=async(page,id,offset=0)=>{
   const s=stations.find(s=>s.id===id),box=await page.locator('.weather-map').first().boundingBox();
   const point=await page.evaluate(s=>{const p=window.__stationMaps.find(m=>m.getContainer().isConnected).latLngToContainerPoint([s.lat,s.lon]);return {x:p.x,y:p.y};},s);
   return {x:box.x+point.x+offset,y:box.y+point.y};
  };
  assert.equal(await page.locator('.station-hit').count(),64);
  await page.evaluate(()=>window.__originalStation=document.querySelector('.station-hit'));
  const before=await page.evaluate(()=>Simulator.getState().maps);
  await page.locator('.weather-map').first().scrollIntoViewIfNeeded();
  await page.locator('#station-search').fill('59488');
  let p=await position(page,'57957',8);await page.mouse.click(p.x,p.y);
  assert.equal(await page.locator('#station-name').innerText(),'桂林');assert.equal(await page.locator('#station-search').inputValue(),'');
  assert.equal(await page.locator('#station-select').inputValue(),'57957');
  // Pearl River Delta hit circles overlap at regional scale: choose the
  // nearest geographical point, not whichever SVG path was created last.
  for(const id of ['59287','59288','59289','59485','59493']){
   p=await position(page,id);await page.mouse.click(p.x,p.y);assert.equal(await page.evaluate(()=>Simulator.getState().selected.id),id);
  }
  const hit=page.locator('.station-hit[data-station-id="59488"]').first();await hit.focus();await page.keyboard.press('Enter');
  assert.equal(await page.locator('#station-name').innerText(),'珠海');assert.equal(await hit.getAttribute('aria-pressed'),'true');
  assert.equal(await hit.evaluate(el=>el===document.activeElement),true,'selection must preserve the focused SVG node');
  assert.equal(await page.evaluate(()=>window.__originalStation.isConnected&&window.__originalStation===document.querySelector('.station-hit')),true);
  const after=await page.evaluate(()=>Simulator.getState().maps);
  assert.deepEqual(after.map(v=>v.markerBuilds),before.map(v=>v.markerBuilds),'no marker rebuild/flicker per selection');
  assert.deepEqual(after.map(v=>v.center),before.map(v=>v.center),'choosing a station must not jump/zoom the map');
  assert.equal(await page.evaluate(()=>Simulator.getState().manifest),null,'this regression must not start computation');
  p=await position(page,'57957');const selected=await page.evaluate(()=>Simulator.getState().selected.id);
  await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(p.x+65,p.y+25,{steps:10});await page.mouse.up();
  assert.equal(await page.evaluate(()=>Simulator.getState().selected.id),selected,'dragging across a station is not a click');
  await page.locator('#add-on-map').click();p=await position(page,'57957');await page.mouse.click(p.x,p.y);
  assert.equal(await page.locator('.custom-station').getAttribute('open'),'');assert.equal(await page.evaluate(()=>Simulator.getState().selected.id),selected);
  await page.screenshot({path:'/private/tmp/stormsim-astra-station-picking.png',fullPage:true});
  await context.close();
  const touch=await setup({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  assert.equal(await touch.page.evaluate(()=>matchMedia('(pointer: coarse)').matches),true);
  const target=touch.page.locator('.station-hit[data-station-id="57957"]').first();const bounds=await target.boundingBox();assert.ok(bounds.width>=39,'touch hit area must be about 40 CSS pixels');
  await touch.page.locator('.weather-map').first().scrollIntoViewIfNeeded();p=await position(touch.page,'57957');await touch.page.touchscreen.tap(p.x,p.y);
  assert.equal(await touch.page.locator('#station-select').inputValue(),'57957');await touch.context.close();
  console.log('PASS '+(process.env.TEST_EDITION||'astra')+' stations: enlarged mouse/touch targets, nearest-point overlap resolution, keyboard/focus, filtered list sync, retained SVG identity, no view jump, drag safety and custom picking; no simulation');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
