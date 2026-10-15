/* Six-hour real Worker computation followed by playback, no fixture results. */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1500,height:1050}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/MapServer/tile/**',r=>r.abort());await page.route('**/tile.openstreetmap.org/**',r=>r.abort());
  await page.goto('http://127.0.0.1:8765/simulator.html');
  await page.locator('#local-grid').selectOption('8');await page.locator('#local-hours').fill('6');await page.locator('#flow-rate').selectOption('0');
  await page.locator('#start-simulation').click();
  await page.waitForFunction(()=>['complete','error'].includes(Simulator.getState().computeState),null,{timeout:600000});
  await page.waitForFunction(()=>Simulator.getState().computeState==='error'||Simulator.getState().playbackState==='ended',null,{timeout:60000});
  const stats=await page.evaluate(()=>{const s=Simulator.getState(),f=s.frame?.fields;let rain=0,cold=0,echo=-30;if(f)for(let i=0;i<f.rain_total.data.length;i++){rain=Math.max(rain,SimulationData.value(f.rain_total,i));cold=Math.max(cold,SimulationData.value(f.coldpool,i));echo=Math.max(echo,SimulationData.value(f.composite,i));}return {status:s.computeState,config:s.manifest?.config,hour:s.frame?.hour,current:s.current,rain,cold,echo,text:document.querySelector('#compute-status').textContent};});
  assert.equal(stats.status,'complete',stats.text);assert.equal(stats.hour,6);assert.equal(stats.current,36);assert.ok(stats.rain>0);assert.deepEqual(errors,[]);
  assert.ok(await page.evaluate(()=>{const f=Simulator.getState().frame.fields;return f.coldpool_depth&&f.u300&&f.cape_deficit;}));
  assert.equal(await page.locator('h1').innerText(),'强对流模拟器V1');
  await page.locator('#station-search').fill('南宁');await page.locator('#station-select').selectOption('59431');await page.locator('#station-radar').click();
  await page.locator('.map-card select').nth(1).selectOption('lowwind');
  await page.locator('#basemap').selectOption('none');await page.locator('#view-region').click();
  await page.locator('.map-card select').nth(1).selectOption('rain_total');
  assert.notEqual(await page.locator('#obs-rain_hour').innerText(),'—');
  assert.ok(await page.evaluate(()=>Simulator.getState().maps.every(m=>m.frontSegments>0)), 'synoptic front remains available without a cold-pool outline');
  assert.equal(await page.locator('#start-simulation').isDisabled(),false);
  assert.equal(await page.locator('#replay-bar').isVisible(),true);
  await page.setViewportSize({width:1440,height:1080});await page.evaluate(()=>scrollTo(0,0));
  await page.screenshot({path:'assets/images/simulator-v1-preview.png',fullPage:false});
  await page.screenshot({path:'/private/tmp/felicia-v36-browser-six-hours.png',fullPage:true});
  console.log('PASS six-hour real compute-first process and playback',JSON.stringify(stats));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
