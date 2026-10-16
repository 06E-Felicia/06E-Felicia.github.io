/* UI/protocol regression with a mock worker; no weather integration. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),root=path.resolve(__dirname,'..'),errors=[];
  await context.addInitScript(()=>{window.Worker=class{
   constructor(){window.__worker=this;this.terminated=false;}
   postMessage(message){if(message.type!=='start')return;window.__start=message;const sol=message.profile==='sol';this.onmessage({data:{type:'manifest',manifest:{schema:2,edition:message.profile,config:{seed:message.seed||20260421,month:4,grid_km:sol?28:6,hours:message.controls.hours},grid:{nominal_km:sol?28:6},frames:[]}}});}
   terminate(){this.terminated=true;sessionStorage.setItem('test-terminated','yes');}
  };});
  await context.route('**/*',route=>{
   const url=new URL(route.request().url());if(url.origin!=='http://127.0.0.1:14331')return route.abort();
   const file=path.resolve(root,url.pathname.replace(/^\/nested\//,''));
   if(!file.startsWith(root+path.sep)||!fs.existsSync(file))return route.fulfill({status:404,body:''});return route.fulfill({path:file});
  });
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  const ready=()=>page.waitForFunction(()=>window.Simulator&&!document.querySelector('#start-simulation').disabled);
  const progress=(hour,elapsed)=>page.evaluate(({hour,elapsed})=>window.__worker.onmessage({data:{type:'progress',hour,hours:72,elapsed}}),{hour,elapsed});
  await page.goto('http://127.0.0.1:14331/nested/simulator.html');await ready();
  assert.equal(await page.title(),'StormSim 1.1 Astra · 深中气象');assert.equal(await page.locator('h1').innerText(),'StormSim 1.1 Astra');
  await page.locator('#start-simulation').click();assert.equal(await page.locator('#start-simulation').isDisabled(),true);
  await progress(.5,1);assert.equal(await page.locator('#sol-suggestion').isVisible(),false,'wait for actual timing, not a guessed device class');
  await progress(1,2);assert.equal(await page.locator('#sol-suggestion').isVisible(),false,'under five minutes: no prompt');
  assert.equal(await page.locator('#sol-suggestion').getAttribute('data-enabled'),'true','Sol recommendation must be enabled after reopening');
  assert.ok(fs.statSync(path.join(root,'.nojekyll')).isFile(),'Pages upload needs the root .nojekyll file');
  await progress(.5,4);assert.equal(await page.locator('#sol-suggestion').isVisible(),true);
  assert.match(await page.locator('#sol-suggestion-text').innerText(),/超过 5 分钟/);
  const link=new URL(await page.locator('#switch-to-sol').getAttribute('href'));
  assert.equal(link.pathname,'/nested/simulator-sol.html');assert.equal(link.searchParams.get('seed'),'20260421');assert.equal(link.searchParams.get('hours'),'72');
  await page.screenshot({path:'/private/tmp/stormsim-astra-sol-suggestion.png',fullPage:true});
  await page.locator('#keep-astra').click();await progress(.6,6);assert.equal(await page.locator('#sol-suggestion').isVisible(),false,'one recommendation per run');
  assert.equal(await page.evaluate(()=>window.__worker.terminated),false,'continuing Astra must not restart/terminate it');
  await page.locator('#stop-compute').click();await page.locator('#start-simulation').click();await progress(.5,4);
  assert.equal(await page.locator('#sol-suggestion').isVisible(),true,'a new run may recommend again');
  await page.keyboard.press('Escape');assert.equal(await page.locator('#sol-suggestion').isVisible(),false);
  await page.locator('#stop-compute').click();await page.locator('#start-simulation').click();await progress(.5,4);
  await page.locator('#switch-to-sol').click();await page.waitForURL('**/simulator-sol.html?*');await ready();
  assert.equal(await page.locator('h1').innerText(),'StormSim 1.1 Sol');assert.equal(await page.evaluate(()=>sessionStorage.getItem('test-terminated')),'yes');
  assert.equal(await page.locator('#local-grid').inputValue(),'28');assert.equal(await page.locator('#frame-interval').inputValue(),'60');
  assert.equal(await page.locator('#station-select option').count(),32);
  await page.locator('#start-simulation').click();assert.equal(await page.evaluate(()=>window.__start.profile),'sol');assert.equal(await page.evaluate(()=>window.__start.seed),20260421);
  assert.equal(new URL(page.url()).searchParams.has('seed'),false,'refreshing must not silently reuse a transferred seed');
  await progress(.5,4);assert.equal(await page.locator('#sol-suggestion').count(),0,'Sol never prompts to switch to itself');
  await page.locator('#stop-compute').click();await page.locator('#start-simulation').click();assert.equal(await page.evaluate(()=>window.__start.seed),null,'transfer seed is used only once; later starts get fresh worker RNG');await page.locator('#stop-compute').click();
  await page.setViewportSize({width:390,height:844});await page.reload();await ready();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:'/private/tmp/stormsim-sol-mobile.png',fullPage:true});
  for(const file of ['index.html','forecast.html','warnings.html','simulator.html','simulator-sol.html']){
   await page.goto('http://127.0.0.1:14331/nested/'+file);
   assert.ok(await page.locator('a[href*="simulator-sol.html"]:not([hidden])').count()>0,file+' must expose a Sol entry');
  }
  assert.deepEqual(errors,[]);console.log('PASS Astra/Sol names, isolated profiles, real-speed ETA threshold, dismiss/Escape/one-per-run, cancellation + seed transfer, fresh restart, subdirectory links, stations and mobile');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
