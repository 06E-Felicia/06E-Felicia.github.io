/* Local-only rendering fixtures. No provider calls or production fake data. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict'),vm=require('node:vm');
const {chromium}=require('playwright');
const root=path.resolve(__dirname,'../..');
const html=fs.readFileSync(path.join(root,'Feimadat.html'),'utf8');
for(const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g))new vm.Script(match[1]);
const NOW=Date.parse('2026-10-20T15:00:00+08:00')/1000;
const fixture=(id,offset,extra={})=>({id,flight_number:id,board:'arrivals',scheduled_ts:NOW+offset,
 estimated_ts:null,status:'scheduled',airline:'测试航司',endpoint:{iata:'PEK',city:'Beijing'},...extra});
const samples=[fixture('UI-LIVERY',1800,{is_special_livery:true}),fixture('UI-WIDE',3600,{is_widebody:true,type:'A359',
 gate:'<img src=x onerror="window.BAD_SCRIPT=1">',photo:{src:'javascript:window.BAD_SCRIPT=1'}}),
 fixture('UI-HISTORY',-1800,{is_special_livery:true}),fixture('UI-TOMORROW',86400,{is_widebody:true}),
 fixture('UI-ORDINARY',1200,{type:'A320',is_widebody:false}),fixture('UI-UNKNOWN',900)];
const snapshot={source:'variflight-mcp',airport:{iata:'SZX',name:'深圳宝安国际机场',city:'Shenzhen'},
 generated_at:NOW,service_day:'2026-10-20',flights:samples,today:samples};
const status={source:'variflight-mcp',connection_state:'ready',connected:true,
 airports:{SZX:{last_success_at:NOW}}};
async function localPage(browser,base,options={}){
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[],requests=[];
 page.on('pageerror',error=>errors.push(error.message));
 await context.addInitScript(()=>localStorage.setItem('feimadat-airport','HND'));
 await page.clock.setFixedTime(new Date((options.realTime || NOW)*1000));
 await context.route('**/*',route=>{
  const url=new URL(route.request().url());requests.push(url);
  return url.hostname==='127.0.0.1'?route.continue():route.abort();
 });
 if(options.photos){
  await context.route('https://api.planespotters.net/pub/photos/reg/*',route=>route.fulfill({json:{photos:[{
   thumbnail_large:{src:'https://t.plnspttrs.net/1/test.jpg'},link:'https://www.planespotters.net/photo/1/b-2043-test',
   photographer:'Lazy Test author'}]}}));
  await context.route('https://t.plnspttrs.net/1/test.jpg',route=>route.fulfill({contentType:'image/svg+xml',
   body:'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect width="120" height="80" fill="blue"/></svg>'}));
 }
 if(options.active){
  await context.route('**/feimadata/data/status.json?*',route=>route.fulfill({json:status}));
  await context.route('**/feimadata/data/szx.json?*',route=>route.fulfill({json:options.data||snapshot}));
 }else if(!options.real){
  // Pending-state regressions must not depend on whether live local snapshots exist.
  await context.route('**/feimadata/data/status.json?*',route=>route.fulfill({json:{
   source:'variflight-mcp',connection_state:'awaiting_key',connected:false,airports:{}}}));
 }
 if(options.legacyIndex)await context.route('**/feimadata/data/index.json?*',route=>route.fulfill({json:{
  source:'variflight-mcp',default_airport:'HND',airports:[{iata:'HND',name:'东京羽田'},{iata:'SZX',name:'深圳宝安国际机场'}]}}));
 // Exercise the preserved implementation offline only; production stays suspended.
 await page.route('**/Feimadat.html',route=>route.fulfill({contentType:'text/html; charset=utf-8',
  body:html.replace(/<!-- FEIMADAT_SUSPENDED_START[\s\S]*?<!-- FEIMADAT_SUSPENDED_END -->/,'')}));
 await page.goto(base+(options.prefix||'')+'/Feimadat.html');
 return {context,page,errors,requests};
}
(async()=>{
 const server=http.createServer((req,res)=>{
  let name=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  if(name.startsWith('/project/'))name=name.slice('/project'.length);
  if(name==='/__test_photo.svg'){
   res.setHeader('Content-Type','image/svg+xml');
   res.end('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="80"><rect width="120" height="80" fill="#c9dfee"/></svg>');
   return;
  }
  const file=path.resolve(root,'.'+name);
  if(!file.startsWith(root+path.sep)||name.split('/').some(p=>p.startsWith('.'))||!fs.existsSync(file)||!fs.statSync(file).isFile()){
   res.writeHead(404);res.end();return;
  }
  res.setHeader('Content-Type',file.endsWith('.html')?'text/html; charset=utf-8':file.endsWith('.json')?'application/json':file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'application/octet-stream');
  fs.createReadStream(file).pipe(res);
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));let browser;
 try{
  browser=await chromium.launch({channel:'chrome',headless:true});
  const base='http://127.0.0.1:'+server.address().port;
  const suspended=await browser.newContext();
  const suspendedRequests=[];
  await suspended.route('**/*',route=>{
   const url=new URL(route.request().url());suspendedRequests.push(url.pathname);
   return url.hostname==='127.0.0.1'?route.continue():route.abort();
  });
  const hiddenPage=await suspended.newPage();
  for(const prefix of ['', '/project']){
   await hiddenPage.goto(base+prefix+'/Feimadat.html');
   await hiddenPage.waitForURL(base+prefix+'/Flightdat.html');
   assert.equal(await hiddenPage.locator('a[href="Feimadat.html"]').count(),0);
  }
  assert.equal(suspendedRequests.some(p=>p.includes('/feimadata/data/')),false,
   'hidden page must not load Feimadat snapshots');
  await suspended.close();
  const pending=await localPage(browser,base),{page}=pending;
  await page.getByText('飞常准数据尚未接通',{exact:true}).waitFor();
  assert.equal(await page.locator('#airportSel option').count(),1);
  assert.equal(await page.locator('#sourceStateText').innerText(),'待接入');
  assert.equal(await page.locator('#lastUpdate').innerText(),'--');
  assert.deepEqual(await page.locator('.stat .value').allTextContents(),Array(5).fill('—'));
  assert.match(await page.locator('#list').innerText(),/不代表当天没有航班/);
  assert.equal(await page.locator('#list .row').count(),0);
  assert.equal(pending.requests.some(u=>u.hostname!=='127.0.0.1'),false);
  assert.equal(pending.requests.some(u=>/flightdata\/|\/szx\.json/.test(u.pathname)),false);
  await page.evaluate(()=>localStorage.setItem('fr24-airport','PEK'));
  for(const airport of ['SZX']){
   await page.selectOption('#airportSel',airport);
   await page.waitForFunction(code=>document.querySelector('#brandIata').textContent===code,airport);
   await page.getByText('飞常准数据尚未接通',{exact:true}).waitFor();
  }
  assert.equal(await page.evaluate(()=>localStorage.getItem('fr24-airport')),'PEK');
  assert.equal(await page.evaluate(()=>localStorage.getItem('feimadat-airport')),'SZX');
  await page.locator('[data-board="arrivals"]').click();
  await page.locator('#chips [data-chip="widebody"]').click();
  await page.locator('#search').fill('NOT-CONNECTED');
  assert.equal(await page.locator('#s-total').innerText(),'—');
  await page.locator('#btnReload').click();
  await page.waitForFunction(()=>document.querySelector('#toastText').textContent.includes('不会获取授权'));
  for(const width of [1440,768,390,320]){
   await page.setViewportSize({width,height:844});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no horizontal overflow at '+width);
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.screenshot({path:'/private/tmp/feimadat-pending-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'/private/tmp/feimadat-pending-mobile.png'});
  assert.deepEqual(pending.errors,[]);await pending.context.close();

  const active=await localPage(browser,base,{active:true,legacyIndex:true});
  await active.page.waitForFunction(()=>document.querySelectorAll('#list .row').length===2);
  assert.equal(await active.page.evaluate(()=>scrollY),0,'opening Feimadat must not scroll to the list');
  assert.equal(await active.page.locator('#airportSel option').count(),1,'ignore stale multi-airport index');
  assert.equal(await active.page.locator('#brandIata').innerText(),'SZX','ignore old HND preference');
  assert.equal(await active.page.locator('#s-total').innerText(),'2');
  assert.doesNotMatch(await active.page.locator('#list').innerText(),/UI-ORDINARY|UI-UNKNOWN|UI-TOMORROW/);
  await active.page.locator('#search').fill('UI-ORDINARY');
  assert.equal(await active.page.locator('#list .row').count(),0,'search cannot bypass curated filtering');
  await active.page.locator('#search').fill('');
  assert.equal(await active.page.locator('#sourceStateText').innerText(),'SNAPSHOT');
  assert.equal(await active.page.locator('#list .photo-thumb img').count(),0,'reject unsafe image URLs');
  await active.page.locator('#showEarlier').click();
  assert.equal(await active.page.locator('#pastFlights .row').count(),1);
  assert.equal(await active.page.locator('#s-total').innerText(),'2');
  await active.page.locator('#chips [data-chip="widebody"]').click();
  assert.equal(await active.page.locator('#list .row').count(),1);
  await active.page.locator('#list .row').click();
  await active.page.locator('#flightDetail[open]').waitFor();
  assert.match(await active.page.locator('#detailBody').innerText(),/UI-WIDE/);
  assert.equal(await active.page.locator('#detailBody img').count(),0);
  assert.equal(await active.page.evaluate(()=>window.BAD_SCRIPT),undefined);
  await active.page.keyboard.press('Escape');
  assert.equal(await active.page.locator('#flightDetail[open]').count(),0);
  assert.deepEqual(active.errors,[]);await active.context.close();

  for(const data of [{...snapshot,source:'flightradar24-web'},{...snapshot,airport:{iata:'PEK'}},
                     {...snapshot,generated_at:'bad'},{...snapshot,flights:null}]){
   const invalid=await localPage(browser,base,{active:true,data});
   await invalid.page.getByText('该机场数据暂未就绪',{exact:true}).waitFor();
   assert.equal(await invalid.page.locator('#list .row').count(),0);
   assert.deepEqual(invalid.errors,[]);await invalid.context.close();
  }
  const limited=await localPage(browser,base,{active:true,data:{...snapshot,capabilities:{
   aircraft_type:false,widebody:false,four:false,cargo:false,foreign_airline:false}}});
  await limited.page.waitForFunction(()=>document.querySelectorAll('#list .row').length===2);
  for(const chip of ['widebody','four','cargo','special']){
   assert.equal(await limited.page.locator(`#chips [data-chip="${chip}"]`).isDisabled(),true);
   assert.equal(await limited.page.locator(`#chips [data-chip="${chip}"] .n`).innerText(),'—');
  }
  assert.equal(await limited.page.locator('#s-widebody').innerText(),'—');
  assert.match(await limited.page.locator('#capabilityNote').innerText(),/未提供机型/);
  assert.deepEqual(limited.errors,[]);await limited.context.close();

  const enrichedData={...snapshot,capabilities:{aircraft_type:true,widebody:true,four:true,cargo:false},
    detail_coverage:{total:1,registration:1,aircraft_type:1,photo:1},flights:[fixture('UI-ENRICHED',1800,{
      registration:'B-30EC',registration_source:'getFlightStatus',detail_checked_at:NOW-60,is_special_livery:true,
      type:'A321-253NX',type_family:'A320',photo:{source:'planespotters',reg:'B-30EC',src:'https://t.plnspttrs.net/1/test.jpg',link:'https://www.planespotters.net/photo/1/b-30ec-test',
       photographer:'Test author',provider:'PlaneSpotters.net · 同注册号资料照片（非本航班实拍）'}})]};
  enrichedData.today=enrichedData.flights;
  const enriched=await localPage(browser,base,{active:true,photos:true,data:enrichedData});
  await enriched.page.getByText('B-30EC',{exact:true}).waitFor();
  assert.match(await enriched.page.locator('#list').innerText(),/A321-253NX/);
  assert.match(await enriched.page.locator('.credit').innerText(),/Test author.*非本航班实拍/);
  assert.match(await enriched.page.locator('#capabilityNote').innerText(),/1\/1 条有注册号/);
  await enriched.page.locator('#list .row').click();
  assert.match(await enriched.page.locator('#detailBody').innerText(),/飞常准航班详情/);
  assert.match(await enriched.page.locator('#detailBody').innerText(),/同注册号资料照片/);
  assert.deepEqual(enriched.errors,[]);await enriched.context.close();

  const lazyRows=[fixture('UI-LAZY',1800,{registration:'B-2043',is_special_livery:true,
    photo:{src:'https://file.variflight.com/theme.png',provider:'飞常准主题图片'},type:'777-39L'})];
  const lazy=await localPage(browser,base,{active:true,photos:true,data:{...snapshot,flights:lazyRows,today:lazyRows}});
  await lazy.page.getByText('B-2043',{exact:true}).waitFor();
  await lazy.page.locator('#list .row').scrollIntoViewIfNeeded();
  await lazy.page.getByText(/Lazy Test author/).first().waitFor();
  assert.equal(await lazy.page.locator('#list .photo-thumb img').count(),1);
  assert.equal(lazy.requests.some(url=>url.hostname.endsWith('variflight.com')),false,'never load legacy theme images');
  assert.match(await lazy.page.locator('#list .photo-thumb img').getAttribute('src'),/^https:\/\/t\.plnspttrs\.net\//);
  await lazy.page.locator('#list .row').click();
  await lazy.page.locator('#detailBody .detail-photo img').waitFor();
  assert.match(await lazy.page.locator('#detailBody figcaption').innerText(),/非本航班实拍/);
  assert.deepEqual(lazy.errors,[]);await lazy.context.close();

  // A tab opened before the first capture must discover it on the next poll.
  const transition=await localPage(browser,base);
  await transition.page.getByText('飞常准数据尚未接通',{exact:true}).waitFor();
  let ready=false;
  await transition.page.route('**/feimadata/data/status.json?*',r=>r.fulfill({json:ready?status:{
   source:'variflight-mcp',connection_state:'awaiting_key',connected:false,airports:{}}}));
  await transition.page.route('**/feimadata/data/szx.json?*',r=>r.fulfill({json:snapshot}));
  await transition.page.clock.install({time:new Date(NOW*1000)});
  await transition.page.reload();
  await transition.page.getByText('飞常准数据尚未接通',{exact:true}).waitFor();
  ready=true;
  await transition.page.clock.fastForward(60001);
  await transition.page.waitForFunction(()=>document.querySelectorAll('#list .row').length===2);
  assert.deepEqual(transition.errors,[]);await transition.context.close();

  // Real, already-saved API snapshots are read locally, not fetched again.
  const liveStatus=JSON.parse(fs.readFileSync(path.join(root,'feimadata/data/status.json'),'utf8'));
  if(liveStatus.connection_state==='ready'){
   const realTime=Math.floor(Date.now()/1000),live=await localPage(browser,base,{real:true,realTime});
   const operation=f=>Number(f.actual_ts)>0?Number(f.actual_ts):Number(f.estimated_ts)>0?Number(f.estimated_ts):Number(f.scheduled_ts)||0;
   for(const code of ['SZX']){
    const d=JSON.parse(fs.readFileSync(path.join(root,'feimadata/data',code.toLowerCase()+'.json'),'utf8'));
    const expected=d.today.filter(f=>(f.is_special_livery||f.is_foreign||f.is_widebody||f.is_four_engine||f.is_cargo)&&operation(f)>=realTime&&Math.floor((operation(f)+28800)/86400)===Math.floor((realTime+28800)/86400));
    await live.page.selectOption('#airportSel',code);
    await live.page.waitForFunction(({code,n})=>document.querySelector('#brandIata').textContent===code&&
      document.querySelectorAll('#list .row').length===n&&document.querySelector('#sourceStateText').textContent==='SNAPSHOT',
      {code,n:expected.length});
    assert.equal(await live.page.locator('#s-total').innerText(),String(expected.length));
    assert.equal(await live.page.locator('#s-widebody').innerText(),d.capabilities?.widebody===false?'—':String(expected.filter(f=>f.is_widebody).length));
    assert.match(await live.page.title(),new RegExp('Feimadat.*'+code));
   }
   await live.page.selectOption('#airportSel','SZX');
   await live.page.waitForFunction(()=>document.querySelector('#brandIata').textContent==='SZX');
   await live.page.evaluate(()=>scrollTo(0,0));
   await live.page.screenshot({path:'/private/tmp/feimadat-real-desktop.png'});
   await live.page.setViewportSize({width:390,height:844});
   assert.ok(await live.page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await live.page.screenshot({path:'/private/tmp/feimadat-real-mobile.png'});
   assert.deepEqual(live.errors,[]);await live.context.close();
  }
  const sub=await localPage(browser,base,{prefix:'/project'});
  await sub.page.getByText('飞常准数据尚未接通',{exact:true}).waitFor();
  assert.equal(sub.requests.some(u=>u.pathname.startsWith('/project/feimadata/')),true);
  assert.deepEqual(sub.errors,[]);await sub.context.close();
  console.log('PASS Feimadat: SZX only, stale-index/preferences isolation, no entry auto-scroll, curated filters, P-only photos, mobile layouts, history, details and subpaths');
 }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);process.exitCode=1;});
