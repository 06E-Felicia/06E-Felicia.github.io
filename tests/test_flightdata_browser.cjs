/* Real local HTTP + Chrome; only saved snapshots, no live scraping. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'..');
const original=code=>{
 const file=path.join(root,'flightdata/docs/data',code.toLowerCase()+'.json');
 if(fs.existsSync(file))return JSON.parse(fs.readFileSync(file,'utf8'));
 // New-airport fixtures are test-only; no production snapshots are fabricated.
 const d=JSON.parse(fs.readFileSync(path.join(root,'flightdata/docs/data/szx.json'),'utf8'));
 d.airport=JSON.parse(fs.readFileSync(path.join(root,'flightdata/config.json'),'utf8')).airports.find(a=>a.iata===code);
 return d;
};
const NOW_MS=original('SZX').generated_at*1000;
const read=code=>{
 const d=original(code),now=NOW_MS/1000;
 const time=f=>Number(f.estimated_ts)>0?Number(f.estimated_ts):Number(f.scheduled_ts)||0;
 d.today=d.today.filter(f=>time(f)>=now && Math.floor((time(f)+28800)/86400)===Math.floor((now+28800)/86400)
  && (f.is_special_livery||f.is_foreign||f.is_widebody||f.is_four_engine||f.is_cargo));
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
  for(const code of ['CTU','HND']) await context.route('**/'+code.toLowerCase()+'.json?*',r=>r.fulfill({json:original(code)}));
  const weather=JSON.parse(fs.readFileSync(path.join(root,'config.json'),'utf8'));
  weather.ALERT_CONFIG.enabled=false;weather.THUNDER_ALERT_CONFIG={enabled:false,candidates:[],radar:{}};
  await context.route('**/config.json*',r=>r.fulfill({json:weather}));
  page.on('pageerror',e=>errors.push(e.message));
  const base='http://127.0.0.1:'+server.address().port;
  await page.goto(base+'/index.html');await page.locator('#update-close').click();
  await page.locator('.nav-item[href="Flightdat.html"]').click();await page.waitForURL('**/Flightdat.html');
  await page.waitForFunction(()=>document.querySelector('#list .row'));
  assert.equal(await page.locator('#airportSel option').count(),7);
  for(const code of ['SZX','PEK','PVG','CAN','HKG','CTU','HND']){
   await page.selectOption('#airportSel',code);const d=read(code);
   await page.waitForFunction(n=>document.querySelector('#list').querySelectorAll('.row').length===n,d.today.length);
   assert.equal(await page.locator('#brandIata').innerText(),code);
   assert.equal(await page.locator('#s-total').innerText(),String(d.today_stats.special));
   assert.match(await page.title(),new RegExp('Flightdat.*'+code));
   assert.match(await page.locator('#sourceLink').getAttribute('href'),new RegExp('/'+code.toLowerCase()+'$'));
  }
  await page.locator('#list .row').first().click();
  await page.locator('#flightDetail[open]').waitFor();
  assert.match(await page.locator('#detailBody').innerText(),/羽田当地（UTC\+9）/);
  await page.locator('#closeDetail').click();
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
  assert.match(await page.locator('.statusbar').innerText(),/^更新时间\s+\S+/);
  assert.equal(await page.locator('.statusbar .item').count(),1);
  assert.equal(await page.locator('#freqTag,#countdown,#nextUpdate,#cycleBar').count(),0);
  assert.equal(await page.locator('[data-chip="bizjet"],.badge.bizjet').count(),0);
  assert.equal(await page.locator('#s-four').innerText(),String(read('SZX').today.filter(f=>f.is_four_engine).length));

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
  await bad.goto(base+'/Flightdat.html');await bad.getByText('航班资料正在准备',{exact:true}).waitFor();
  assert.doesNotMatch(await bad.locator('body').innerText(),/HTTP 404|读取失败|未更新|flightdata\/docs\/data/);

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

  // Source errors remain backend diagnostics, never public banners/toasts.
  const partialContext=await browser.newContext();
  await partialContext.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const partialStatus={updated_by:'github-actions',airports:{SZX:{ok:true,partial:true,
   last_success_at:read('SZX').generated_at,errors:{departures:'Just a moment...；源站显示访问验证'}}}};
  await partialContext.route('**/status.json?*',r=>r.fulfill({json:partialStatus}));
  const partialPage=await newPage(partialContext);
  partialPage.on('pageerror',e=>errors.push(e.message));
  await partialPage.goto(base+'/Flightdat.html');
  await partialPage.waitForFunction(()=>document.querySelector('#list .row'));
  assert.equal(await partialPage.locator('#alert').count(),0);
  assert.doesNotMatch(await partialPage.locator('body').innerText(),/部分更新|Just a moment|小时未更新/);
  assert.equal(await partialPage.locator('#list .row').count(),read('SZX').today.length);
  partialStatus.airports.SZX={ok:false,error:'HTTP 403',last_success_at:read('SZX').generated_at};
  await partialPage.locator('#btnReload').click();
  await partialPage.waitForFunction(()=>document.querySelector('#toastText').textContent.includes('不会启动抓取'));
  assert.doesNotMatch(await partialPage.locator('body').innerText(),/抓取失败|HTTP 403|小时未更新/);
  assert.equal(await partialPage.locator('#list .row').count(),read('SZX').today.length);
  await partialPage.route('**/szx.json?*',r=>r.fulfill({status:500,body:'source error'}));
  await partialPage.locator('#btnReload').click();
  await partialPage.waitForTimeout(150);
  assert.equal(await partialPage.locator('#list .row').count(),read('SZX').today.length,'failed refresh keeps loaded records');
  assert.doesNotMatch(await partialPage.locator('body').innerText(),/读取失败|source error|HTTP 500/);
  await partialContext.close();

  // Default to remaining-today flights; history expands ABOVE now without
  // changing counters or the reader's current-time viewport anchor.
  const windowContext=await browser.newContext();
  await windowContext.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const now=Date.parse('2026-10-19T15:42:00+08:00')/1000;
  const make=(id,offset,extra={})=>({...ordinary,id,flight_number:id,scheduled_ts:now+offset,estimated_ts:null,
   status:'scheduled',status_cn:'计划',status_kind:'muted',last_seen_ts:now,from_history:true,...extra});
  const samples=[make('OLD-1210',-12720),make('EXPIRED',-3601),make('BOUNDARY',-3600),
   make('RECENT',-2820),make('LANDED',-1800,{status:'landed',status_cn:'已到达',status_kind:'ok'}),
   make('FUTURE',1800),make('DELAYED',-12000,{estimated_ts:now+1200}),make('NOW',0),
   make('DAY-END',Date.parse('2026-10-19T23:59:59+08:00')/1000-now),
   make('LIVERY',2400,{is_special_livery:true,is_four_engine:true,livery:'特别彩绘 <测试> 多行涂装名称',is_foreign:false}),
   make('ONLY-BIZJET',3600,{is_bizjet:true,is_widebody:false}),make('TOMORROW',12*3600),
   make('NO-TIME',0,{scheduled_ts:null,estimated_ts:null})];
  const windowData={...original('SZX'),service_day:'2026-10-19',generated_at:now,today:samples,flights:samples};
  await windowContext.route('**/szx.json?*',r=>r.fulfill({json:windowData}));
  const windowPage=await windowContext.newPage();
  windowPage.on('pageerror',e=>errors.push(e.message));
  await windowPage.clock.setFixedTime(new Date(now*1000));
  await windowPage.goto(base+'/Flightdat.html');
  await windowPage.waitForFunction(()=>document.querySelectorAll('#list .row').length===5);
  const names=()=>windowPage.locator('#list .flight .f').allTextContents();
  assert.deepEqual((await names()).sort(),['DAY-END','DELAYED','FUTURE','LIVERY','NOW']);
  assert.equal(await windowPage.locator('#s-total').innerText(),'5');
  assert.equal(await windowPage.locator('#s-widebody').innerText(),'5');
  assert.equal(await windowPage.locator('#s-four').innerText(),'1');
  assert.equal(await windowPage.locator('#c-featured').innerText(),'5');
  assert.match(await windowPage.locator('#resultText').innerText(),/今日剩余\s+5\s+班/);
  assert.equal(await windowPage.locator('#showEarlier').getAttribute('aria-expanded'),'false');
  assert.match(await windowPage.locator('#showEarlier').innerText(),/5 班/);
  await windowPage.waitForFunction(()=>{
   const marker=document.querySelector('#currentTimeMarker')?.getBoundingClientRect();
   return marker&&marker.top>=0&&marker.bottom<=innerHeight&&scrollY>0;
  });
  assert.ok(await windowPage.locator('#showEarlier').evaluate(e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<innerHeight;}));
  const anchor=await windowPage.locator('#currentTimeMarker').evaluate(e=>e.getBoundingClientRect().top);
  await windowPage.locator('#showEarlier').click();
  assert.equal(await windowPage.locator('#pastFlights .row').count(),5);
  assert.equal(await windowPage.locator('#s-total').innerText(),'5','history must not inflate remaining counters');
  assert.equal(await windowPage.locator('#c-featured').innerText(),'5');
  assert.ok(Math.abs(await windowPage.locator('#currentTimeMarker').evaluate(e=>e.getBoundingClientRect().top)-anchor)<3,'expanding history must preserve the now anchor');
  assert.ok(await windowPage.locator('#pastFlights').evaluate(e=>e.getBoundingClientRect().bottom<=document.querySelector('#currentTimeMarker').getBoundingClientRect().top));
  const row=id=>windowPage.locator('#list .row').filter({has:windowPage.locator('.flight .f',{hasText:id})});
  assert.equal(await row('RECENT').locator('.pill').innerText(),'待核实');
  assert.match(await row('RECENT').locator('.pill').getAttribute('title'),/不代表航班已结束/);
  assert.equal(await row('LANDED').locator('.pill').innerText(),'已落地');
  assert.match(await row('LANDED').locator('.pill').getAttribute('title'),/源站已报告/);
  assert.equal(await row('LIVERY').locator('.badge.livery').innerText(),'✦ 彩绘机');
  assert.equal(await row('LIVERY').locator('.lv').innerText(),'✦\n特别彩绘 <测试> 多行涂装名称');
  assert.equal(await row('LANDED').evaluate(e=>getComputedStyle(e).opacity),'1','past text must not be faded');
  assert.equal(await row('FUTURE').locator('.flight .f').evaluate(e=>getComputedStyle(e).color),'rgb(20, 44, 64)');
  assert.equal(await row('FUTURE').evaluate(e=>getComputedStyle(e).borderBottomColor),'rgb(186, 203, 217)');
  await row('LIVERY').click();
  await windowPage.locator('#flightDetail[open]').waitFor();
  assert.equal(await windowPage.locator('#detailTitle').innerText(),'LIVERY');
  assert.match(await windowPage.locator('#detailBody').innerText(),/特别彩绘 <测试> 多行涂装名称/);
  assert.match(await windowPage.locator('#detailBody').innerText(),/登机口[\s\S]*未提供/);
  assert.match(await windowPage.locator('#detailBody').innerText(),/北京时间 · UTC\+8/);
  await windowPage.screenshot({path:'/private/tmp/flightdat-detail-desktop.png'});
  await windowPage.keyboard.press('Escape');
  await windowPage.locator('#flightDetail[open]').waitFor({state:'hidden'});
  assert.ok(await row('LIVERY').evaluate(e=>e===document.activeElement));
  await windowPage.keyboard.press('Enter');
  await windowPage.locator('#flightDetail[open]').waitFor();
  await windowPage.locator('#closeDetail').click();
  await windowPage.clock.setFixedTime(new Date((now+120)*1000));
  await windowPage.waitForTimeout(1100);
  assert.equal(await windowPage.locator('#list .row').count(),10,'history must remain available');
  assert.equal(await windowPage.locator('#s-total').innerText(),'4','the current-time flight must expire from remaining counts');
  assert.equal(await windowPage.locator('#pastFlights .row').count(),6);
  await windowPage.evaluate(()=>scrollTo(0,0));
  await windowPage.locator('#btnReload').click();
  await windowPage.waitForFunction(()=>document.querySelector('#toastText').textContent.includes('不会启动抓取'));
  assert.ok((await names()).includes('OLD-1210'),'reload keeps the whole-day accumulation');
  assert.equal(await windowPage.evaluate(()=>scrollY),0,'background/manual reload must not force another time jump');
  await windowPage.locator('#jumpNow').click();
  assert.ok(await windowPage.evaluate(()=>scrollY)>0,'explicit return-to-now button locates the time divider');
  await windowPage.selectOption('#sortSel','time-desc');
  assert.equal(await windowPage.locator('#pastFlights .row').count(),6,'all sorts keep history above now');
  assert.ok(!(await names()).includes('TOMORROW'));
  await windowPage.locator('#showEarlier').click();
  assert.equal(await windowPage.locator('#pastFlights .row').count(),0);
  assert.equal(await windowPage.locator('#list .row').count(),4);
  assert.equal(await windowPage.locator('#showEarlier').getAttribute('aria-expanded'),'false');
  await windowPage.setViewportSize({width:390,height:844});
  await row('LIVERY').click();
  await windowPage.locator('#flightDetail[open]').waitFor();
  assert.ok(await windowPage.locator('#flightDetail').evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight&&e.scrollWidth<=e.clientWidth+1;}));
  await windowPage.screenshot({path:'/private/tmp/flightdat-detail-mobile.png'});
  await windowPage.locator('#closeDetail').click();
  await windowPage.locator('#showEarlier').click();
  assert.equal(await windowPage.locator('#pastFlights .row').count(),6);
  assert.equal(await windowPage.locator('#s-total').innerText(),'4');
  assert.ok(await windowPage.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await windowPage.locator('#showEarlier').click();
  await windowPage.setViewportSize({width:1440,height:1000});
  await windowPage.locator('#chips [data-chip="four"]').click();
  assert.deepEqual(await names(),['LIVERY']);
  assert.equal(await windowPage.locator('#s-total').innerText(),'4');
  await windowPage.locator('#clearFilters').click();
  windowData.today=[];
  await windowPage.locator('#btnReload').click();
  await windowPage.waitForFunction(()=>document.querySelectorAll('#list .row').length===0);
  assert.equal(await windowPage.locator('#s-total').innerText(),'0','empty today must not fall back to all snapshot flights');
  assert.equal(await windowPage.locator('#historyTools').isVisible(),false);
  windowData.today=samples.filter(f=>f.flight_number==='OLD-1210');
  await windowPage.locator('#btnReload').click();
  await windowPage.waitForFunction(()=>!document.querySelector('#historyTools').hidden);
  assert.equal(await windowPage.locator('#list .row').count(),0,'past-only day has no remaining flights');
  await windowPage.locator('#showEarlier').click();
  assert.deepEqual(await names(),['OLD-1210'],'past-only day can still expand earlier flights');
  await windowPage.clock.setFixedTime(new Date('2026-10-20T00:15:00+08:00'));
  const nextTime=Date.parse('2026-10-20T00:30:00+08:00')/1000;
  windowData.service_day='2026-10-20';windowData.generated_at=nextTime-900;
  windowData.today=windowData.flights=[make('NEW-DAY',0,{scheduled_ts:nextTime,from_history:false})];
  await windowPage.locator('#btnReload').click();
  await windowPage.waitForFunction(()=>document.querySelector('#list .flight .f')?.textContent==='NEW-DAY');
  assert.deepEqual(await names(),['NEW-DAY'],'new-day snapshot replaces all old-day rows in memory');
  await windowContext.close();
  assert.deepEqual(errors,[]);
  console.log('PASS Flightdat: seven airports (new-airport offline fixtures), remaining-today counts, expandable history, current-time jump, delayed flights, filters/sorts, livery/dark text/borders, timestamp-only bar, no public errors, desktop/mobile flight dialog/keyboard/focus, empty/past-only days, next-day replacement; no live scrape');
 }finally{await browser?.close();server.closeAllConnections();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
