/* Real local HTTP + Chrome; only saved snapshots, no live scraping. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const original=code=>JSON.parse(fs.readFileSync(path.join(root,'flightdata/docs/data',code.toLowerCase()+'.json'),'utf8'));
const NOW_MS=original('SZX').generated_at*1000;
const read=code=>{
 const d=original(code),now=NOW_MS/1000;
 const time=f=>Number(f.estimated_ts)>0?Number(f.estimated_ts):Number(f.scheduled_ts)||0;
 d.today=d.today.filter(f=>Math.floor((time(f)+28800)/86400)===Math.floor((now+28800)/86400));
 for(const [rows,key] of [[d.flights,'stats'],[d.today,'today_stats']]){
  d[key]={...d[key],total:rows.length,special:rows.length,widebody:rows.filter(f=>f.is_widebody).length};
 }
 return d;
};
const newPage=async context=>{const page=await context.newPage();await page.clock.setFixedTime(new Date(NOW_MS));return page;};
(async()=>{
 const server=http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');let name=decodeURIComponent(url.pathname);
  if(name.startsWith('/project/'))name=name.slice('/project'.length);
  const file=path.resolve(root,'.'+name);
  if(!file.startsWith(root+path.sep)||name.split('/').some(p=>p.startsWith('.'))||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',file.endsWith('.html')?'text/html; charset=utf-8':file.endsWith('.json')?'application/json':file.endsWith('.css')?'text/css':file.endsWith('.js')?'application/javascript':'application/octet-stream');
  fs.createReadStream(file).pipe(res);
 });
 await new Promise(r=>server.listen(0,'127.0.0.1',r));let browser;
 try{
  browser=await chromium.launch({headless:true,channel:'chrome'});
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await newPage(context),errors=[];
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const weather=JSON.parse(fs.readFileSync(path.join(root,'config.json'),'utf8'));
  weather.ALERT_CONFIG.enabled=false;weather.THUNDER_ALERT_CONFIG={enabled:false,candidates:[],radar:{}};
  await context.route('**/config.json*',r=>r.fulfill({json:weather}));
  page.on('pageerror',e=>errors.push(e.message));
  const base='http://127.0.0.1:'+server.address().port;
  await page.goto(base+'/index.html');await page.locator('#update-close').click();
  await page.locator('.nav-item[href="Flightdat.html"]').click();await page.waitForURL('**/Flightdat.html');
  await page.waitForFunction(()=>document.querySelector('#list .row'));
  assert.equal(await page.locator('#airportSel option').count(),5);
  for(const code of ['SZX','PEK','PVG','CAN','HKG']){
   await page.selectOption('#airportSel',code);const d=read(code);
   await page.waitForFunction(n=>document.querySelector('#list').querySelectorAll('.row').length===n,d.today.length);
   assert.equal(await page.locator('#brandIata').innerText(),code);
   assert.equal(await page.locator('#s-total').innerText(),String(d.today_stats.special));
   assert.match(await page.title(),new RegExp('Flightdat.*'+code));
   assert.match(await page.locator('#sourceLink').getAttribute('href'),new RegExp('/'+code.toLowerCase()+'$'));
  }
  await page.selectOption('#airportSel','SZX');await page.waitForFunction(n=>document.querySelector('#list').querySelectorAll('.row').length===n,read('SZX').today.length);
  await page.locator('#boardSeg [data-board="arrivals"]').click();
  assert.equal(await page.locator('#list .row').count(),read('SZX').today.filter(f=>f.board==='arrivals').length);
  await page.locator('#clearFilters').click();await page.locator('#chips [data-chip="four"]').click();
  assert.equal(await page.locator('#list .row').count(),read('SZX').today.filter(f=>f.is_four_engine).length);
  await page.locator('#clearFilters').click();await page.locator('#chips [data-chip="widebody"]').click();
  assert.equal(await page.locator('#list .row').count(),read('SZX').today.filter(f=>f.is_widebody).length);
  assert.equal(await page.locator('#s-widebody').innerText(),String(read('SZX').today_stats.widebody));
  await page.locator('#clearFilters').click();await page.keyboard.press('/');assert.equal(await page.locator('#search').evaluate(e=>e===document.activeElement),true);
  const flight=read('SZX').today[0].flight_number;await page.locator('#search').fill(flight);
  assert.ok(await page.locator('#list .row').count()>0);await page.locator('#search').fill('NO-SUCH-FLIGHT-999999');
  assert.equal(await page.locator('#list .row').count(),0);assert.match(await page.locator('#list').innerText(),/没有匹配的航班/);
  await page.locator('#clearFilters').click();
  await page.locator('#btnReload').click();await page.waitForFunction(()=>document.querySelector('#toastText').textContent.includes('不会启动抓取'));
  assert.match(await page.locator('#runLink').getAttribute('href'),/06E-Felicia.github.io\/actions\/(workflows\/flightdata.yml|runs\/\d+)$/);
  assert.match(await page.locator('#freqTag').innerText(),/30MIN/);

  // A slow old airport response must never overwrite a newly selected one.
  let release;const gate=new Promise(r=>release=r);
  const slow=async r=>{await gate;await r.continue();};
  await page.route('**/pek.json?*',slow);await page.selectOption('#airportSel','PEK');
  await page.selectOption('#airportSel','CAN');
  await page.waitForFunction(n=>document.querySelector('#list').querySelectorAll('.row').length===n,read('CAN').today.length);
  release();await page.waitForTimeout(150);assert.equal(await page.locator('#s-total').innerText(),String(read('CAN').today_stats.special));
  await page.unroute('**/pek.json?*',slow);

  for(const width of [1100,768,390,320]){
   await page.setViewportSize({width,height:844});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'mobile layout must not overflow');
  }
  await page.waitForFunction(()=>!document.querySelector('#toast').classList.contains('show'));
  await page.screenshot({path:'/private/tmp/flightdat-mobile.png',fullPage:false});
  await page.setViewportSize({width:1440,height:1000});
  await page.screenshot({path:'/private/tmp/flightdat-desktop.png',fullPage:false});

  const sub=await newPage(context);await sub.goto(base+'/project/Flightdat.html');
  await sub.waitForFunction(()=>document.querySelector('#list .row'));
  assert.equal(await sub.locator('#airportSel').inputValue(),'CAN');
  await sub.locator('.site-nav a[href="index.html"]').click();await sub.waitForURL('**/project/index.html');

  const bad=await newPage(context);await bad.route('**/docs/data/can.json?*',r=>r.fulfill({status:404,body:''}));
  await bad.goto(base+'/Flightdat.html');await bad.waitForFunction(()=>document.querySelector('#alertText').textContent.includes('flightdata/docs/data'));
  assert.match(await bad.locator('#alert').innerText(),/项目根目录/);
  assert.match(await bad.locator('#list').innerText(),/还没有可用的航班数据/);

  // An ordinary domestic widebody must not be discarded by the old special-only front-end gate.
  const injected=read('SZX'),ordinary={...injected.today[0],id:'offline-test',flight_number:'TEST-WIDE',
   type:'A359',type_family:'A350',is_special_livery:false,is_foreign:false,is_four_engine:false,
   is_cargo:false,is_bizjet:false,is_special_type:false,is_widebody:true,photo:null};
  injected.today.push(ordinary);injected.flights.push(ordinary);
  for(const key of ['stats','today_stats'])for(const count of ['total','special','widebody'])injected[key][count]++;
  const wc=await browser.newContext();await wc.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await wc.route('**/szx.json?*',r=>r.fulfill({json:injected}));const wp=await newPage(wc);await wp.goto(base+'/Flightdat.html');
  await wp.locator('#list .flight .f').filter({hasText:'TEST-WIDE'}).waitFor();
  await wp.locator('#chips [data-chip="widebody"]').click();assert.equal(await wp.locator('#list .flight .f').filter({hasText:'TEST-WIDE'}).count(),1);
  await wp.locator('#chips [data-chip="special"]').click();assert.equal(await wp.locator('#list .flight .f').filter({hasText:'TEST-WIDE'}).count(),0);
  await wc.close();

  // A successful board plus a blocked board is a visible partial update, not an empty success.
  const partialContext=await browser.newContext();
  await partialContext.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const partialStatus={updated_by:'github-actions',airports:{SZX:{ok:true,partial:true,
   last_success_at:read('SZX').generated_at,errors:{departures:'Just a moment...；源站显示访问验证'}}}};
  await partialContext.route('**/status.json?*',r=>r.fulfill({json:partialStatus}));
  const partialPage=await newPage(partialContext);
  partialPage.on('pageerror',e=>errors.push(e.message));
  await partialPage.goto(base+'/Flightdat.html');
  await partialPage.locator('#alert.warn.show').waitFor();
  assert.match(await partialPage.locator('#alertText').innerText(),/部分更新.*出发.*Just a moment/);
  assert.equal(await partialPage.locator('#list .row').count(),read('SZX').today.length);
  partialStatus.airports.SZX={ok:false,error:'HTTP 403',last_success_at:read('SZX').generated_at};
  await partialPage.locator('#btnReload').click();
  await partialPage.locator('#alert.bad.show').waitFor();
  assert.match(await partialPage.locator('#alertText').innerText(),/抓取失败.*HTTP 403/);
  assert.equal(await partialPage.locator('#list .row').count(),read('SZX').today.length);
  await partialContext.close();

  // Full-day history remains available; locate the user at the current time.
  const windowContext=await browser.newContext();
  await windowContext.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const now=Date.parse('2026-10-19T15:42:00+08:00')/1000;
  const make=(id,offset,extra={})=>({...ordinary,id,flight_number:id,scheduled_ts:now+offset,estimated_ts:null,
   status:'scheduled',status_cn:'计划',status_kind:'muted',last_seen_ts:now,from_history:true,...extra});
  const samples=[make('OLD-1210',-12720),make('EXPIRED',-3601),make('BOUNDARY',-3600),
   make('RECENT',-2820),make('LANDED',-1800,{status:'landed',status_cn:'已到达',status_kind:'ok'}),
   make('FUTURE',1800),make('DELAYED',-12000,{estimated_ts:now+1200}),make('TOMORROW',12*3600),
   make('NO-TIME',0,{scheduled_ts:null,estimated_ts:null})];
  const windowData={...original('SZX'),service_day:'2026-10-19',generated_at:now,today:samples,flights:samples};
  await windowContext.route('**/szx.json?*',r=>r.fulfill({json:windowData}));
  const windowPage=await windowContext.newPage();
  windowPage.on('pageerror',e=>errors.push(e.message));
  await windowPage.clock.setFixedTime(new Date(now*1000));
  await windowPage.goto(base+'/Flightdat.html');
  await windowPage.waitForFunction(()=>document.querySelectorAll('#list .row').length===7);
  const names=()=>windowPage.locator('#list .flight .f').allTextContents();
  assert.deepEqual((await names()).sort(),['BOUNDARY','DELAYED','EXPIRED','FUTURE','LANDED','OLD-1210','RECENT']);
  assert.equal(await windowPage.locator('#s-total').innerText(),'7');
  assert.equal(await windowPage.locator('#s-widebody').innerText(),'7');
  await windowPage.waitForFunction(()=>{
   const marker=document.querySelector('#currentTimeMarker')?.getBoundingClientRect();
   return marker&&marker.top>=0&&marker.bottom<=innerHeight&&scrollY>0;
  });
  const row=id=>windowPage.locator('#list .row').filter({has:windowPage.locator('.flight .f',{hasText:id})});
  assert.equal(await row('RECENT').locator('.pill').innerText(),'待核实');
  assert.match(await row('RECENT').locator('.pill').getAttribute('title'),/不代表航班已结束/);
  assert.equal(await row('LANDED').locator('.pill').innerText(),'已落地');
  assert.match(await row('LANDED').locator('.pill').getAttribute('title'),/源站已报告/);
  await windowPage.clock.setFixedTime(new Date((now+120)*1000));
  await windowPage.waitForTimeout(1100);
  assert.equal(await windowPage.locator('#list .row').count(),7,'morning history must not expire after an hour');
  await windowPage.evaluate(()=>scrollTo(0,0));
  await windowPage.locator('#btnReload').click();
  await windowPage.waitForFunction(()=>document.querySelector('#toastText').textContent.includes('不会启动抓取'));
  assert.ok((await names()).includes('OLD-1210'),'reload keeps the whole-day accumulation');
  assert.equal(await windowPage.evaluate(()=>scrollY),0,'background/manual reload must not force another time jump');
  await windowPage.locator('#jumpNow').click();
  assert.ok(await windowPage.evaluate(()=>scrollY)>0,'explicit return-to-now button locates the time divider');
  await windowPage.locator('label.switch').click();
  assert.equal(await windowPage.locator('#todayToggle').isChecked(),false);
  assert.ok((await names()).includes('TOMORROW'));
  assert.ok((await names()).includes('OLD-1210'));
  windowData.today=[];
  await windowPage.locator('label.switch').click();
  assert.equal(await windowPage.locator('#todayToggle').isChecked(),true);
  await windowPage.locator('#btnReload').click();
  await windowPage.waitForFunction(()=>document.querySelectorAll('#list .row').length===0);
  assert.equal(await windowPage.locator('#s-total').innerText(),'0','empty today must not fall back to all snapshot flights');
  await windowPage.clock.setFixedTime(new Date('2026-10-20T00:15:00+08:00'));
  const nextTime=Date.parse('2026-10-20T00:30:00+08:00')/1000;
  windowData.service_day='2026-10-20';windowData.generated_at=nextTime-900;
  windowData.today=windowData.flights=[make('NEW-DAY',0,{scheduled_ts:nextTime,from_history:false})];
  await windowPage.locator('#btnReload').click();
  await windowPage.waitForFunction(()=>document.querySelectorAll('#list .row').length===1);
  assert.deepEqual(await names(),['NEW-DAY'],'new-day snapshot replaces all old-day rows in memory');
  await windowContext.close();
  assert.deepEqual(errors,[]);
  console.log('PASS Flightdat: five airports, filters, responsive layouts, full-day accumulation, first-entry current-time jump, no forced re-jump on reload, return-to-now button, delayed flights, empty today, next-day replacement, clear statuses, 30-minute display; no live scrape');
 }finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
