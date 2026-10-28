/* Exercise the actual launcher and exported native snapshots; never run a Worker. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{spawn}=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
 const root=path.resolve(__dirname,'../..'),index=JSON.parse(fs.readFileSync(path.join(root,'local-test-results/astra/index.json'),'utf8'));
 const child=spawn('python3',['-m','simulation.test_replay','--no-open','--port','8877'],{cwd:root});let browser;
 try{
  const url=await new Promise((resolve,reject)=>{let text='';const timeout=setTimeout(()=>reject(Error('launcher timeout')),15000);child.stdout.on('data',chunk=>{text+=chunk;const hit=text.match(/http:\/\/127\.0\.0\.1:\d+\/simulation\/test-replay\.html/);if(hit){clearTimeout(timeout);resolve(hit[0]);}});child.on('error',reject);child.on('exit',code=>{if(code){clearTimeout(timeout);reject(Error('launcher exited '+code));}});});
  browser=await chromium.launch({headless:true,channel:'chrome'});const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],requested=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>requested.push(new URL(r.url()).pathname));
  await page.addInitScript(()=>{window.Worker=class{constructor(){throw Error('test replay must not start computation');}};});
  await page.route('**/MapServer/tile/**',r=>r.abort());await page.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await page.goto(url);await page.waitForFunction(()=>window.AstraTestReplay?.getState().ready);
  assert.equal(await page.evaluate(()=>AstraTestReplay.getState().seed),index.cases[0].seed);
  assert.equal(await page.evaluate(()=>AstraTestReplay.getState().hour),index.cases[0].default_hour);
  assert.equal(await page.evaluate(()=>AstraTestReplay.getState().frameCount),11);
  await page.selectOption('#test-basemap','none');await page.selectOption('#test-layer','mucape');
  assert.match(await page.locator('#test-legend').innerText(),/J\/kg/);
  await page.evaluate(()=>{const e=document.getElementById('test-slider');e.value='4';e.dispatchEvent(new Event('input'));});
  const data=JSON.parse(fs.readFileSync(path.join(root,'local-test-results/astra',index.cases[0].file),'utf8'));
  const expected=Buffer.from(data.frames[4].fields.mucape,'base64').readDoubleLE((30*data.grid.nx+30)*8);
  assert.equal(await page.evaluate(()=>AstraTestReplay.sample('mucape',30,30)),expected,'exact archived value, not simulated or interpolated');
  await page.locator('#test-map').click({position:{x:350,y:200}});assert.match(await page.locator('#test-values').innerText(),/MUCAPE/);
  await page.selectOption('#test-case','1');await page.waitForFunction(()=>AstraTestReplay.getState().ready&&AstraTestReplay.getState().seed===20260421);
  await page.locator('#test-restart').click();assert.equal(await page.evaluate(()=>AstraTestReplay.getState().hour),0);
  await page.locator('#test-play').click();assert.equal(await page.evaluate(()=>AstraTestReplay.getState().playing),false);
  await page.selectOption('#test-speed','300');await page.locator('#test-play').click();
  await page.waitForFunction(()=>AstraTestReplay.getState().hour===10&&!AstraTestReplay.getState().playing,null,{timeout:10000});
  assert.ok(await page.evaluate(()=>AstraTestReplay.getState().cachedFrames<=2));
  assert.ok(!requested.some(p=>p.endsWith('.wasm')||p.endsWith('.py')||p.includes('simulation-local-worker')));
  assert.deepEqual(errors,[]);
  await page.screenshot({path:'/private/tmp/stormsim-astra-test-launcher.png',fullPage:true});
  const bad=await browser.newPage();await bad.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await bad.route('**/astra-20260421.json',r=>r.fulfill({status:200,body:'corrupt archive',contentType:'application/json'}));
  await bad.goto(url);await bad.waitForFunction(()=>window.AstraTestReplay?.getState().ready);
  await bad.selectOption('#test-case','1');await bad.waitForFunction(()=>!!AstraTestReplay.getState().error);
  assert.match(await bad.locator('#test-status').innerText(),/完整性校验失败/);
  assert.equal(await bad.evaluate(()=>AstraTestReplay.getState().ready),false);
  console.log('PASS real launcher, two completed Astra archives, exact values, mature initial view, layers, playback/seek, no computation, corrupt-data rejection');
 }finally{await browser?.close();child.kill('SIGINT');}
})().catch(e=>{console.error(e);process.exitCode=1;});
