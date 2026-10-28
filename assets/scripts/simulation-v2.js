(function(){
 'use strict';
 const $=id=>document.getElementById(id),D=SimulationData;
 const edition=document.body.dataset.edition==='sol'?'sol':'astra';
 const mobile=matchMedia('(pointer: coarse)').matches&&Math.min(screen.width,screen.height)<900;
 if(mobile&&edition==='astra'){$('local-grid').value='12';$('compute-mode').value='compact';$('frame-interval').value='30';}
 const localFile=location.protocol==='file:';
 function openingError(){
   if(localFile)return '不能直接双击 HTML 开始模拟。请双击项目中的「development/launchers/启动本地预览.command」，通过自动打开的 http://127.0.0.1 页面访问。';
   if(!window.isSecureContext)return '模拟需要安全环境。请使用 HTTPS，或通过本机 http://127.0.0.1 预览，不要使用局域网 HTTP 地址。';
   for(const [name,available]of [['WebAssembly',typeof WebAssembly==='object'],['Worker',typeof Worker==='function'],['本机存储',typeof indexedDB!=='undefined'||typeof caches!=='undefined'],['随机数',typeof crypto?.randomUUID==='function']])if(!available)return '当前浏览器不支持 '+name+'，请使用较新的 Chrome、Edge、Firefox 或 Safari。';
   return null;
 }
 function showOpeningError(text){lastError=text;computeState='error';$('compute-status').textContent=text;$('phase-title').textContent='暂时无法开始';$('start-simulation').disabled=true;$('stop-compute').disabled=true;say(text);}
 const transfer=new URLSearchParams(location.search);
 let transferSeed=edition==='sol'?Number(transfer.get('seed')):null,solSuggested=false;
 if(!Number.isInteger(transferSeed)||transferSeed<1||transferSeed>2147483646)transferSeed=null;
 if(transferSeed&&Number(transfer.get('hours'))>=1&&Number(transfer.get('hours'))<=96)$('local-hours').value=Number(transfer.get('hours'));
 const STORAGE='felicia-physics-points-v2';
 const REGION=L.latLngBounds([19.8,104.3],[26.7,118]);
 let manifest=null,frame=null,current=0,busy=false,picking=false,views=[],syncing=false;
 let worker=null,computeState='idle',archiveRun=null,entries=[],replayRevision=0,replayTimer=null;
 let workerWatchdog=null;
 let playbackState='idle',playTimer=null,roundLocked=false,lastError=null;
 const replayCache=new Map();
 try{archiveRun=sessionStorage.getItem('felicia-last-local-run');}catch(_){}
 let stations=[],custom=[],selected={id:'59493',name:'深圳',lon:114,lat:22.54},radar={...selected};
 // Representative stations present in the archived source table. Keep their
 // actual coordinates/IDs; a city label must not invent a city-centre station.
 const majorCities={'59287':'广州','59493':'深圳','59488':'珠海','59316':'汕头','59288':'佛山','59082':'韶关','59658':'湛江','59659':'茂名','59278':'肇庆','59298':'惠州','59117':'梅州','59501':'汕尾','59293':'河源','59663':'阳江','59280':'清远','59289':'东莞','59485':'中山','59312':'潮州','59315':'揭阳','59471':'云浮','59476':'江门','59431':'南宁','59046':'柳州','57957':'桂林','59265':'梧州','59644':'北海','59635':'防城港','59632':'钦州','59211':'百色','59065':'贺州','59023':'河池','59242':'来宾'};
 const records=new Map(),choices=['composite','velocity','lowwind','upperwind'];
 const layers={composite:['合成雷达回波','dBZ',5,60],reflectivity:['单站反射率','dBZ',5,60],velocity:['多普勒径向速度','m/s',-30,30],lowwind:['低空风 · 925 hPa','m/s',0,30],midwind:['中层风 · 500 hPa','m/s',0,50],upperwind:['高空风 · 300 hPa','m/s',0,80],mucape:['MUCAPE','J/kg',0,4000],temperature:['近地面温度','℃',10,35],rainrate:['格点平均雨强','mm/h',0,60],rain_hour:['近 1 小时降水','mm',0,60],rain_total:['累计降水','mm',0,150]};
 layers.surfacewind=['近地面风','m/s',0,40];layers.gust=['近地面阵风（诊断）','m/s',0,40];
 layers.rainrate=['点位雨强（估测）','mm/h',0,240];layers.rain5=['近 5 分钟降水（估测）','mm',0,20];layers.rain_hour[0]='近 1 小时降水（估测）';layers.rain_total[0]='累计降水（估测）';
 const palettes={rain:[[40,77,160],[39,175,223],[48,186,110],[231,220,67],[243,120,41],[206,49,85],[211,149,238]],wind:[[34,53,91],[52,106,160],[66,174,168],[157,204,123],[240,185,92],[223,100,100]],velocity:[[50,77,190],[46,182,200],[70,206,153],[39,49,66],[213,185,121],[238,121,84],[212,46,86]],terrain:[[30,78,61],[89,121,69],[140,139,98],[190,171,127],[218,215,192]]};
 function color(key,val){const p=palettes[key==='velocity'?'velocity':key==='terrain'?'terrain':['composite','reflectivity','rainrate','rain5','rainrate_core','rain_hour','rain_total'].includes(key)?'rain':'wind'],spec=layers[key],f=Math.max(0,Math.min(1,(val-spec[2])/(spec[3]-spec[2])))*(p.length-1),i=Math.min(p.length-2,Math.floor(f)),a=f-i;return p[i].map((v,k)=>Math.round(v+(p[i+1][k]-v)*a));}
 const clock=h=>{const minutes=Math.round(h*60)+480;return `第 ${Math.floor(minutes/1440)+1} 天 ${String(Math.floor(minutes/60)%24).padStart(2,'0')}:${String(minutes%60).padStart(2,'0')}`;};
 const duration=seconds=>seconds<60?Math.ceil(seconds)+' 秒':seconds<3600?Math.ceil(seconds/60)+' 分钟':(seconds/3600).toFixed(1)+' 小时';
 function initializationProgress(hour,hours,elapsed=null){
   if(!Number.isFinite(hour)||!Number.isFinite(hours)||hours<=0)return;
   const ratio=Math.max(0,Math.min(.999,hour/hours));
   $('compute-progress').value=Math.max($('compute-progress').value||0,ratio);
   $('compute-percent').textContent=($('compute-progress').value*100).toFixed(1)+'%';
   if(Number.isFinite(elapsed)&&elapsed>=2&&ratio>=.002){const remaining=elapsed*(hours-hour)/Math.max(hour,.001);$('compute-remaining').textContent='预计剩余时间：约 '+duration(Math.max(0,remaining));recommendSol(elapsed+remaining,remaining);}
 }
 function recommendSol(total,remaining){
   const dialog=$('sol-suggestion');
   if(edition!=='astra'||solSuggested||total<=300||remaining<=0||!worker||!dialog||dialog.dataset.enabled!=='true')return;
   solSuggested=true;
   $('sol-suggestion-text').textContent='按本机当前计算速度，Astra 本轮预计共需约 '+duration(total)+'，超过 5 分钟。可以切换到 StormSim 2.5 Sol。';
   const url=new URL('simulator-sol.html',location.href);if(manifest?.config?.seed)url.searchParams.set('seed',manifest.config.seed);url.searchParams.set('hours',manifest?.config?.hours||$('local-hours').value);
   $('switch-to-sol').href=url.href;dialog.showModal();
 }
 const say=t=>$('runtime-status').textContent=t;
 function decodeLive(raw){
   raw=JSON.parse(raw);
   if(raw.schema!==2||!Number.isFinite(raw.hour)||raw.hour<0)throw Error('模拟时刻不匹配');
   const fields=Object.fromEntries(Object.entries(raw.fields).map(([k,v])=>[k,D.unpack(v,k.startsWith('point_')?manifest.rain_grid:manifest.grid)]));
   const required=['temperature','rainrate','rain_total','mucape','terrain','t3','q3','p3','u3','v3','w3','dbz3','coldair'];
   if(edition==='astra')required.push('sbcape','mlcape','cin');
   for(const k of required)if(!fields[k])throw Error('缺少模拟字段 '+k);
   return {hour:raw.hour,fields,audit:raw.audit};
 }
 function playbackButton(){$('toggle-playback').textContent=playbackState==='playing'?'暂停播放':playbackState==='ended'?'重新播放':'继续播放';}
 function computeControls(locked){roundLocked=locked;for(const id of ['start-simulation','local-grid','local-hours','compute-mode','frame-interval'])$(id).disabled=locked;}
 function pausePlayback(){clearTimeout(playTimer);playTimer=null;playbackState=entries.length?'paused':'idle';playbackButton();}
 function clearFrames(){pausePlayback();replayRevision++;clearTimeout(replayTimer);replayCache.clear();entries=[];records.clear();frame=null;manifest=null;current=0;busy=false;playbackState='idle';$('replay-bar').hidden=true;$('station-time').textContent='';document.querySelectorAll('.map-time').forEach(e=>e.textContent='');$('sim-clock').textContent='环境准备中';$('run-info').textContent='';$('phase-title').textContent='准备中';update();}
 function showReplay(){if(entries.length<2)return;$('replay-bar').hidden=false;$('replay-slider').max=entries.length-1;$('replay-slider').value=current;$('replay-time').textContent=frame?clock(frame.hour):'';playbackButton();}
 async function seekReplay(position){if(worker||computeState!=='complete'||!manifest||!entries[position])return false;const revision=++replayRevision,run=archiveRun,entry=entries[position];busy=true;
   try{const state=replayCache.get(entry.index)||decodeLive(await SimulationFrameStore.getRaw(run,entry.index));if(revision!==replayRevision||run!==archiveRun)return false;if(state.hour!==entry.hour)throw Error('回看时刻不匹配');replayCache.set(entry.index,state);while(replayCache.size>2)replayCache.delete(replayCache.keys().next().value);frame=state;current=position;update();$('replay-slider').value=position;$('replay-time').textContent=clock(frame.hour);say(roundLocked?'天气演变中，可调整时间流速':playbackState==='playing'?'正在回顾本轮天气过程':'已定位至所选时刻');return true;}
   catch(e){if(revision===replayRevision){lastError=e.message;pausePlayback();computeControls(false);$('stop-compute').disabled=true;say('天气状态暂时无法读取，请重新开始本轮。');}return false;}finally{if(revision===replayRevision)busy=false;}
 }
 function schedulePlayback(){clearTimeout(playTimer);if(playbackState!=='playing'||worker)return;if(current>=entries.length-1){playbackState='ended';computeControls(false);$('stop-compute').disabled=true;$('phase-title').textContent='本轮天气过程已结束';$('compute-status').textContent='可回顾本轮，或开始全新的天气过程。';showReplay();say('本轮结束，可拖动回顾各时刻');return;}const run=archiveRun,rate=+$('flow-rate').value,delay=rate>0?(entries[current+1].hour-entries[current].hour)*3600000/rate:50;
   playTimer=setTimeout(async()=>{if(run!==archiveRun||playbackState!=='playing')return;if(await seekReplay(current+1))schedulePlayback();},Math.max(16,delay));
 }
 async function startPlayback(){if(worker||computeState!=='complete'||entries.length<2)return;clearTimeout(replayTimer);pausePlayback();replayRevision++;if(!frame||current>=entries.length-1){if(!await seekReplay(0))return;}playbackState='playing';playbackButton();schedulePlayback();}
 function stopCompute(){clearTimeout(workerWatchdog);if(computeState==='loading')computeState='stopped';if($('sol-suggestion')?.open)$('sol-suggestion').close();if(worker){worker.terminate();worker=null;busy=false;computeState='stopped';if(manifest)manifest.status='stopped';entries=[];SimulationFrameStore.remove(archiveRun).catch(()=>{});$('empty-state').hidden=false;$('sim-clock').textContent='等待开始';}pausePlayback();replayRevision++;clearTimeout(replayTimer);$('compute-status').removeAttribute('aria-busy');$('initialization').hidden=true;$('compute-status').textContent='本轮已结束，再次开始将生成全新的天气环境。';say('本轮已结束');$('stop-compute').disabled=true;computeControls(false);if(computeState==='complete')showReplay();}
 async function startCompute(){
   const unsupported=openingError();if(unsupported){showOpeningError(unsupported);return;}
   if(roundLocked||worker)return;
   lastError=null;solSuggested=false;
   const hours=+$('local-hours').value,grid_km=+$('local-grid').value,frame_minutes=+$('frame-interval').value,compact_transport=$('compute-mode').value==='compact';
   if(!Number.isFinite(hours)||hours<1||hours>96){$('compute-status').textContent='过程时长须在 1–96 小时之间。';return;}
   stopCompute();const old=archiveRun;archiveRun=crypto.randomUUID();const run=archiveRun;clearFrames();computeControls(true);if(old)SimulationFrameStore.remove(old).catch(()=>{});try{sessionStorage.setItem('felicia-last-local-run',run);}catch(_){}computeState='loading';$('compute-status').textContent='正在准备本轮天气环境，请稍候…';$('stop-compute').disabled=false;$('empty-state').hidden=true;$('compute-status').setAttribute('aria-busy','true');say('正在准备本轮天气环境');
   $('initialization').hidden=false;$('compute-progress').removeAttribute('value');$('compute-percent').textContent='载入中';$('compute-remaining').textContent='首次载入时暂无法估计剩余时间';
   $('compute-status').textContent='正在检查本机存储…';
   await SimulationFrameStore.prepare();
   if(archiveRun!==run||!roundLocked)return;
   const owned=new Worker('assets/scripts/simulation-local-worker.js?v=5.15.0');worker=owned;
   const fail=text=>{if(worker!==owned)return;busy=false;stopCompute();lastError=text;computeState='error';$('compute-status').textContent='模拟中止：'+text+'。请检查项目文件与浏览器存储权限后重试。';};
   const watch=()=>{clearTimeout(workerWatchdog);workerWatchdog=setTimeout(()=>{if(document.hidden)watch();else fail('计算线程长时间未响应，请保持 Safari 在前台，关闭其他占用内存的页面后重试');},180000);};watch();
   owned.onerror=e=>fail(e.message||'计算线程无法加载');
   owned.onmessageerror=()=>fail('浏览器无法读取计算线程的数据');
   owned.onmessage=async({data})=>{if(worker!==owned)return;
     watch();
     try{
       // Show actual setup progress/ETA, but no partial weather or replay UI.
       if(data.type==='status'){$('compute-status').textContent=data.text||'正在载入本轮初始环境…';$('compute-percent').textContent='载入中'+(data.stage?' · '+data.stage:'');}
       if(data.type==='progress')initializationProgress(data.hour,data.hours,data.elapsed);
       if(data.type==='manifest'){
         manifest=data.manifest;computeState='computing';$('run-info').textContent=`${manifest.config.month} 月 · ${manifest.grid.nominal_km} km · ${manifest.config.hours} 小时`;
         initializationProgress(0,manifest.config.hours);$('compute-status').textContent='环境初始化中，完成后自动开始本轮演变。';
       }
       if(data.type==='frame'){
         // Validate metadata now; decode large volumes only during viewing,
         // after the Python Worker has released its WASM memory on iOS.
         busy=true;const latest=JSON.parse(data.raw);if(latest.schema!==2||!latest.fields?.t3||!Number.isFinite(latest.hour)||data.index!==entries.length||entries.length&&latest.hour<=entries.at(-1).hour)throw Error('计算结果时刻没有前进');await SimulationFrameStore.putRaw(run,data.index,data.raw);if(worker!==owned){SimulationFrameStore.remove(run).catch(()=>{});return;}entries.push({index:data.index,hour:latest.hour});
         busy=false;
         initializationProgress(latest.hour,manifest.config.hours);
         if(worker===owned)owned.postMessage({type:'ack'});
       }
       if(data.type==='complete'){if(!entries.length||Math.abs(entries.at(-1).hour-manifest.config.hours)>1e-6)throw Error('完整过程未保存，拒绝展示');clearTimeout(workerWatchdog);manifest.status='complete';manifest.elapsed_seconds=data.elapsed;manifest.timing=data.timing;computeState='complete';if($('sol-suggestion')?.open)$('sol-suggestion').close();$('compute-status').removeAttribute('aria-busy');$('initialization').hidden=true;$('compute-status').textContent='本轮环境已就绪，可调整时间流速。';$('phase-title').textContent='天气演变中';owned.terminate();worker=null;$('empty-state').hidden=true;await startPlayback();}
       if(data.type==='error')fail(data.text);
     }catch(e){fail(e.message||String(e));}
   };
   owned.postMessage({type:'start',profile:edition,seed:transferSeed,mobile,controls:{hours,grid_km,frame_minutes,compact_transport}});
   if(transferSeed){const clean=new URL(location.href);clean.searchParams.delete('seed');clean.searchParams.delete('hours');history.replaceState(null,'',clean.pathname+clean.search+clean.hash);}transferSeed=null;
 }
 if($('keep-astra'))$('keep-astra').onclick=()=>$('sol-suggestion').close();
 if($('switch-to-sol'))$('switch-to-sol').onclick=()=>stopCompute();
 function stationOptions(){const query=$('station-search').value.trim();$('station-select').replaceChildren();for(const s of [...stations,...custom].filter(s=>(s.name+(s.stationName||'')+s.id+(s.province||'')).includes(query))){const o=document.createElement('option');o.value=s.id;o.textContent=s.name+(s.stationName&&s.stationName!==s.name?'（'+s.stationName+'站）':'')+' · '+(s.kind==='custom'?'自定义':s.id);o.selected=s.id===selected.id;$('station-select').append(o);}}
 function select(id){const s=[...stations,...custom].find(s=>s.id===id);if(!s)return;selected=s;if(!(s.name+(s.stationName||'')+s.id+(s.province||'')).includes($('station-search').value.trim()))$('station-search').value='';stationOptions();update();views.forEach(v=>v.markers());}
 function customSave(){try{localStorage.setItem(STORAGE,JSON.stringify(custom));return true;}catch(_){return false;}}
 function observation(point){if(!frame)return {};const i=D.index(manifest.grid,point.lon,point.lat),f=frame.fields;
   const out={hour:frame.hour};for(const k of ['temperature','dewpoint','rainrate','rain_hour','rain_total','mucape'])out[k]=D.value(f[k],i);
   for(const k of ['rainrate','rain_hour','rain_total','rain5']){
     const fine=manifest.rain_grid&&f['point_'+k],g=fine?manifest.rain_grid:manifest.grid;
     out[k]=D.sample(fine||f[k],g,point.lon,point.lat);
   }
   out.gust=D.value(f.gust,i);
   const u=D.value(f.u10,i),v=D.value(f.v10,i);out.wind=Math.hypot(u,v);out.direction=out.wind<.1?NaN:(Math.atan2(-u,-v)*180/Math.PI+360)%360;return out;
 }
 const obs=[['temperature','气温','℃'],['dewpoint','露点','℃'],['wind','风速','m/s'],['direction','风向（来向）','°'],['rainrate','雨强','mm/h'],['rain_hour','近 1h 降水','mm'],['rain_total','累计雨量','mm'],['mucape','MUCAPE','J/kg']];
 obs.splice(3,0,['gust','阵风（诊断）','m/s']);
 obs.splice(6,0,['rain5','近 5min 降水','mm']);
 function update(){
   $('station-name').textContent=selected.name;$('station-id').textContent=selected.id.startsWith('custom-')?'自定义观测点':selected.id+(selected.stationName&&selected.stationName!==selected.name?' · '+selected.stationName+'站':'');$('station-coordinates').textContent=`${selected.lon.toFixed(3)}°E / ${selected.lat.toFixed(3)}°N`;$('delete-station').hidden=selected.kind!=='custom';
   const o=observation(selected);for(const [k]of obs)$('obs-'+k).textContent=Number.isFinite(o[k])?o[k].toFixed(k.includes('cape')||k==='cin'||k==='direction'?0:1):'—';
   if(frame){const stamp=clock(frame.hour);$('sim-clock').textContent=stamp;$('station-time').textContent=stamp;document.querySelectorAll('.map-time').forEach(e=>e.textContent=stamp);
     if(!records.has(selected.id))records.set(selected.id,new Map());records.get(selected.id).set(frame.hour,o);
   }
   views.forEach(v=>v.draw());profile();
 }
 function profile(){const canvas=$('profile-chart'),rect=canvas.getBoundingClientRect();canvas.width=Math.max(1,rect.width);canvas.height=250;const c=canvas.getContext('2d'),w=canvas.width,h=canvas.height,theme=getComputedStyle(document.documentElement),tone=name=>theme.getPropertyValue(name).trim();c.fillStyle=tone('--panel-soft');c.fillRect(0,0,w,h);if(!frame)return;const g=manifest.grid,i=D.index(g,selected.lon,selected.lat);if(i<0)return;
   c.font='11px sans-serif';const X=t=>35+(t+85)/125*(w-60),Y=z=>h-25-z/18000*(h-50);c.fillStyle=tone('--muted');for(let z=0;z<=18000;z+=3000){c.fillText(z/1000+' km',3,Y(z));c.strokeStyle=tone('--line');c.beginPath();c.moveTo(38,Y(z));c.lineTo(w-10,Y(z));c.stroke();}for(const temp of [-60,-30,0,30])c.fillText(temp+'℃',X(temp),h-7);
   for(const kind of ['temp','dew']){c.beginPath();c.strokeStyle=tone(kind==='temp'?'--warm':'--blue');c.lineWidth=2;g.z_agl_m.forEach((z,k)=>{let t=D.value(frame.fields.t3,i,k);if(kind==='dew'){const q=D.value(frame.fields.q3,i,k),p=D.value(frame.fields.p3,i,k)*100,e=Math.max(.01,q*p/(.62195691+q)),a=Math.log(e/611.2);t=243.5*a/(17.67-a);}if(k)c.lineTo(X(t),Y(z));else c.moveTo(X(t),Y(z));});c.stroke();}
 }
 function contourPaths(g,sample,level){const segments=[];
   for(let y=0;y<g.ny-1;y++)for(let x=0;x<g.nx-1;x++){const nodes=[[x,y],[x+1,y],[x+1,y+1],[x,y+1]],values=nodes.map(([xx,yy])=>sample(yy*g.nx+xx)),hits=[];for(let edge=0;edge<4;edge++){const next=(edge+1)%4,a=values[edge],b=values[next];if(Number.isFinite(a)&&Number.isFinite(b)&&(a<level)!==(b<level)){const t=(level-a)/(b-a),xx=nodes[edge][0]+t*(nodes[next][0]-nodes[edge][0]),yy=nodes[edge][1]+t*(nodes[next][1]-nodes[edge][1]);hits.push([g.south+yy*g.dlat,g.west+xx*g.dlon]);}}for(let j=0;j+1<hits.length;j+=2)segments.push([hits[j],hits[j+1]]);}
   return segments;
 }
 // Native wheel zoom otherwise falls back to a destructive reset when the
 // regional boundary forces a large centre correction during zoom-out.
 const SmoothMap=L.Map.extend({setZoomAround(point,zoom,options){return L.Map.prototype.setZoomAround.call(this,point,zoom,{animate:true,...options});}});
 class MapView{
   constructor(card,key){this.card=card;this.key=key;this.rasterBuilds=0;this.map=new SmoothMap(card.querySelector('.weather-map'),{preferCanvas:false,renderer:L.svg({padding:.35}),zoomControl:true,zoomAnimation:true,markerZoomAnimation:true,zoomAnimationThreshold:10,minZoom:5,maxZoom:14,maxBounds:REGION,maxBoundsViscosity:1,zoomSnap:.25,zoomDelta:.5,wheelPxPerZoomLevel:140,wheelDebounceTime:70,inertia:true}).setView(REGION.getCenter(),6);this.group=L.layerGroup().addTo(this.map);this.vectors=L.polyline([],{color:'#eff7f4',weight:1,interactive:false}).addTo(this.map);this.front=L.polyline([],{color:'#9bc7ff',weight:1.5,interactive:false}).addTo(this.map);L.control.scale({imperial:false,maxWidth:90}).addTo(this.map);this.setBase();this.markers();this.limitView(true);
     this.map.createPane('weatherFields').style.zIndex='350';
     this.map.getPane('weatherFields').style.pointerEvents='none';
     this.map.on('zoomstart',()=>{this.zooming=true;});
     this.map.on('zoomend',()=>{this.zooming=false;this.constrainView();});
     // Followers emit asynchronous zoom events too. Keep their ownership
     // through moveend so they cannot bounce the same zoom back to the source.
     this.map.on('zoomanim',e=>{if(!this.disposed&&!this.following&&!syncing)this.syncView(e.center,e.zoom);});
     this.map.on('movestart',()=>{if(this.disposed||syncing||this.following)return;syncing=true;try{views.forEach(v=>{if(v!==this&&!v.disposed){cancelAnimationFrame(v.syncRAF);v.syncRAF=null;v.map.stop();}});}finally{syncing=false;}});
     this.map.on('move',()=>{if(this.disposed||syncing||this.following||this.syncRAF)return;this.syncRAF=requestAnimationFrame(()=>{this.syncRAF=null;this.syncView();});});
     this.map.on('moveend',()=>{if(this.disposed)return;if(this.following){this.following=false;const pending=this.pendingView;this.pendingView=null;if(pending){const locked=syncing;syncing=true;try{this.followView(pending.center,pending.zoom);}finally{syncing=locked;}}this.queueVectors();return;}if(syncing)return;cancelAnimationFrame(this.syncRAF);this.syncRAF=null;this.syncView();views.forEach(v=>v.queueVectors());});
     this.map.on('click',e=>{if(!picking){const s=this.nearestStation(e);if(s)select(s.id);return;}$('custom-lon').value=e.latlng.lng.toFixed(4);$('custom-lat').value=e.latlng.lat.toFixed(4);document.querySelector('.custom-station').open=true;$('custom-name').focus();picking=false;$('add-on-map').textContent='＋ 地图选点';});
   }
   syncView(center=this.map.getCenter(),zoom=this.map.getZoom()){if(this.disposed||syncing)return;syncing=true;try{for(const view of views)if(view!==this&&!view.disposed)view.followView(center,zoom);}finally{syncing=false;}}
   followView(center,zoom){if(this.following||this.zooming){this.pendingView={center,zoom};return;}if(this.map.getZoom()!==zoom){this.following=true;this.map.setView(center,zoom,{animate:true});return;}
     // Same-zoom motion translates retained panes, with pixel-rounded panBy.
     const delta=this.map.project(center,zoom).subtract(this.map.project(this.map.getCenter(),zoom));
     if(Math.abs(delta.x)>.5||Math.abs(delta.y)>.5)this.map.panBy(delta,{animate:false});
   }
   queueVectors(){cancelAnimationFrame(this.vectorRAF);this.vectorRAF=requestAnimationFrame(()=>{if(!this.disposed&&!this.zooming&&!this.following)this.drawVectors();});}
   constrainView(){
     // A fitted regional viewport can be larger than REGION. Leaflet's
     // viscous limiter then has reversed min/max offsets and snaps on drag.
     // Expand constraints ONLY by the viewport surplus, not the zoom limit.
     const m=this.map,z=m.getZoom(),a=m.project(REGION.getNorthWest(),z),b=m.project(REGION.getSouthEast(),z),size=m.getSize();
     const px=Math.max(0,(size.x-(b.x-a.x))/2)+1,py=Math.max(0,(size.y-(b.y-a.y))/2)+1;
     m.setMaxBounds(L.latLngBounds(m.unproject(a.subtract([px,py]),z),m.unproject(b.add([px,py]),z)));
     if(z<=m.getMinZoom()+.01)m.dragging.disable();else m.dragging.enable();
   }
   limitView(reset=false){this.map.setMinZoom(this.map.getBoundsZoom(REGION));this.constrainView();if(reset)this.map.fitBounds(REGION,{animate:false});this.constrainView();}
   destroy(){this.disposed=true;this.pendingView=null;cancelAnimationFrame(this.syncRAF);cancelAnimationFrame(this.vectorRAF);this.map.stop();
     // Leaflet's in-flight zoom timer still needs its pane at transition end.
     // The card is detached immediately by maps(); release its map only after
     // zoomend, instead of letting that timer touch an already removed pane.
     if(this.zooming)this.map.once('zoomend',()=>this.map.remove());else this.map.remove();
   }
   setBase(){if(this.base)this.map.removeLayer(this.base);if(this.baseFallback)this.map.removeLayer(this.baseFallback);$('map-status').textContent='';const name=$('basemap').value;this.vectors.setStyle({color:name==='satellite'?'#eff7f4':'#526588'});this.front.setStyle({color:name==='satellite'?'#bfcfff':'#6273a4'});if(name==='none'){this.base=null;this.baseFallback=null;return;}
     const url=name==='satellite'?'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}':'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
     const options={maxZoom:15,bounds:REGION,noWrap:true,keepBuffer:3,updateWhenZooming:false,updateWhenIdle:true};
     // A few retained native-z6 tiles cover South China underneath new detail.
     // Large zoom-outs therefore still have real imagery while new tiles load.
     this.baseFallback=L.tileLayer(url,{...options,minNativeZoom:6,maxNativeZoom:6,zIndex:1}).addTo(this.map);
     this.base=L.tileLayer(url,{...options,zIndex:2,attribution:name==='satellite'?'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community':'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(this.map);
     const activeBase=this.base;this.base.on('tileerror',()=>{if(this.base===activeBase)$('map-status').textContent='在线底图暂时无法加载；可切换底图。模拟气象场与 DEM 数据仍然可用。';});
   }
   nearestStation(e){
     if(!$('show-stations').checked||!e.latlng)return null;
     const point=e.containerPoint||this.map.latLngToContainerPoint(e.latlng),touch=matchMedia('(pointer: coarse)').matches||e.originalEvent?.pointerType==='touch';
     let distance=touch?22:14,nearest=null;
     for(const s of [...stations,...custom]){const delta=point.distanceTo(this.map.latLngToContainerPoint([s.lat,s.lon]));if(delta<distance){distance=delta;nearest=s;}}
     return nearest;
   }
   markers(){
     this.stationDots||=new Map();this.markerBuilds||=0;
     if(!$('show-stations').checked){this.group.clearLayers();this.stationDots.clear();return;}
     const points=[...stations,...custom],ids=new Set(points.map(s=>s.id)),theme=getComputedStyle(document.documentElement),touch=matchMedia('(pointer: coarse)').matches;
     for(const [id,item]of this.stationDots)if(!ids.has(id)){this.group.removeLayer(item.dot);this.group.removeLayer(item.hit);this.stationDots.delete(id);}
     for(const s of points){
       let item=this.stationDots.get(s.id);
       if(!item){
         const dot=L.circleMarker([s.lat,s.lon],{radius:4,color:'#fff',weight:1.3,fillOpacity:.95,interactive:false,className:'station-dot'}).addTo(this.group);
         const hit=L.circleMarker([s.lat,s.lon],{radius:touch?20:13,stroke:false,fill:true,fillOpacity:0,bubblingMouseEvents:false,className:'station-hit'}).addTo(this.group);
         const label=s.name+(s.stationName&&s.stationName!==s.name?'（'+s.stationName+'站）':'');hit.bindTooltip(document.createTextNode(label),{direction:'top',offset:[0,-8]});
         hit.on('click',e=>{if(picking){this.map.fire('click',{latlng:e.latlng||dot.getLatLng()});return;}select((this.nearestStation(e)||s).id);});
         hit.on('mouseover',()=>dot.setRadius(s.id===selected.id?6.5:5.5));hit.on('mouseout',()=>dot.setRadius(s.id===selected.id?6.5:4));
         const element=hit.getElement();element.setAttribute('tabindex','0');element.setAttribute('role','button');element.setAttribute('aria-label','选择观测站 '+label);element.dataset.stationId=s.id;
         L.DomEvent.on(element,'keydown',event=>{if(event.key==='Enter'||event.key===' '){L.DomEvent.stop(event);select(s.id);}});
         L.DomEvent.on(element,'focus',()=>hit.openTooltip());L.DomEvent.on(element,'blur',()=>hit.closeTooltip());
         item={dot,hit};this.stationDots.set(s.id,item);this.markerBuilds++;
       }
       const active=s.id===selected.id;if(item.active!==active){item.dot.setRadius(active?6.5:4);item.dot.setStyle({fillColor:theme.getPropertyValue(active?'--warm':'--accent').trim(),weight:active?2:1.3});item.hit.getElement().setAttribute('aria-pressed',String(active));item.active=active;}
     }
   }
   draw(){
     if(!frame){if(this.raster){this.map.removeLayer(this.raster);this.raster=null;}this.renderedFrame=null;this.frontFrame=null;this.front.setLatLngs([]);this.vectors.setLatLngs([]);return;}
     const signature=[this.key,radar.lon,radar.lat,$('radar-elevation').value,$('fold-velocity').checked].join('/');
     if(this.renderedFrame!==frame||this.signature!==signature){
       const f=frame.fields,key=this.key,pointRain=manifest.rain_grid&&f['point_'+key],g=pointRain?manifest.rain_grid:manifest.grid,wind=key.endsWith('wind'),level=key==='surfacewind'?'10':key==='lowwind'?'925':key==='midwind'?'500':'300';
       const west=g.west-g.dlon/2,east=g.west+(g.nx-.5)*g.dlon,south=g.south-g.dlat/2,north=g.south+(g.ny-.5)*g.dlat;
       const merc=lat=>Math.log(Math.tan(Math.PI/4+lat*Math.PI/360)),top=merc(north),bottom=merc(south);
       const canvas=document.createElement('canvas');canvas.width=g.nx*2;canvas.height=g.ny*2;const ctx=canvas.getContext('2d'),pixels=ctx.createImageData(canvas.width,canvas.height),memo=new Map(),elev=+$('radar-elevation').value,fold=$('fold-velocity').checked;
       const domain=manifest.config.bounds||[g.west,g.south,g.west+(g.nx-1)*g.dlon,g.south+(g.ny-1)*g.dlat];
       // Reproject native rows into Web Mercator once per field, not per pan.
       // Nearest native cells remain visible; this creates no extra physics.
       for(let y=0;y<canvas.height;y++){
         const lat=(2*Math.atan(Math.exp(top-(y+.5)/canvas.height*(top-bottom)))-Math.PI/2)*180/Math.PI;
         const row=Math.max(0,Math.min(g.ny-1,Math.round((lat-g.south)/g.dlat)));
         for(let x=0;x<canvas.width;x++){
           const lon=west+(x+.5)/canvas.width*(east-west);
           // An edge cell occupies half a cell outside the declared domain.
           // That is NO DATA, not an endlessly repeated outer rain pixel.
           if(lon<domain[0]||lon>domain[2]||lat<domain[1]||lat>domain[3])continue;
           const column=Math.max(0,Math.min(g.nx-1,Math.round((lon-g.west)/g.dlon)));
           const i=row*g.nx+column;let rgba=memo.get(i);
           if(!rgba){let val;if(key==='velocity'||key==='reflectivity'){const r=D.radar(f,g,g.west+column*g.dlon,g.south+row*g.dlat,radar,elev,fold);val=r.valid?(key==='velocity'?r.velocity:r.dbz):NaN;}else val=wind?Math.hypot(D.value(f['u'+level],i),D.value(f['v'+level],i)):D.value(pointRain||f[key],i);
             const visible=Number.isFinite(val)&&(!['composite','reflectivity'].includes(key)||val>=5)&&(!['rainrate','rain5','rainrate_core','rain_hour','rain_total','coldpool'].includes(key)||val>=.1)&&(key!=='coldpool_depth'||val>=30);rgba=visible?[...color(key,val),255]:[0,0,0,0];memo.set(i,rgba);
           }
           pixels.data.set(rgba,(y*canvas.width+x)*4);
         }
       }
       ctx.putImageData(pixels,0,0);const url=canvas.toDataURL();
       if(this.raster)this.raster.setBounds([[south,west],[north,east]]).setUrl(url);else this.raster=L.imageOverlay(url,[[south,west],[north,east]],{interactive:false,pane:'weatherFields',className:'weather-raster'}).addTo(this.map);
       this.renderedFrame=frame;this.signature=signature;this.rasterBuilds++;this.drawVectors();
     }
     this.raster.setOpacity(+$('opacity').value);this.drawFront();
   }
   drawVectors(){const paths=[];if(frame&&this.key.endsWith('wind')){const size=this.map.getSize(),g=manifest.grid,f=frame.fields,level=this.key==='surfacewind'?'10':this.key==='lowwind'?'925':this.key==='midwind'?'500':'300';for(let y=25;y<size.y;y+=55)for(let x=25;x<size.x;x+=55){const p=this.map.containerPointToLatLng([x,y]),i=D.index(g,p.lng,p.lat),u=D.value(f['u'+level],i),v=D.value(f['v'+level],i),a=Math.atan2(-v,u);if(!Number.isFinite(a))continue;const ex=x+Math.cos(a)*17,ey=y+Math.sin(a)*17,toLL=xy=>this.map.containerPointToLatLng(xy);paths.push([[x,y],[ex,ey],[ex-5*Math.cos(a-.5),ey-5*Math.sin(a-.5)]].map(toLL),[[ex,ey],[ex-5*Math.cos(a+.5),ey-5*Math.sin(a+.5)]].map(toLL));}}this.vectors.setLatLngs(paths);}
   drawFront(){if(!frame||!$('show-front').checked){this.frontFrame=null;this.front.setLatLngs([]);return;}if(this.frontFrame===frame)return;const g=manifest.grid,f=frame.fields;
     // Marching squares: retain ALL actual contour segments, including
     // disconnected fronts; never join the first crossing of each longitude.
     this.front.setLatLngs(contourPaths(g,i=>D.value(f.coldair,i),.5));
     this.frontFrame=frame;
   }
 }
 function maps(count){const center=views[0]?.map.getCenter(),zoom=views[0]?.map.getZoom();const previous=views;views=[];previous.forEach(v=>v.destroy());$('map-grid').replaceChildren();$('map-grid').className='map-grid layout-'+count;document.querySelectorAll('[data-layout]').forEach(b=>b.setAttribute('aria-pressed',String(+b.dataset.layout===count)));
   for(let i=0;i<count;i++){const card=document.createElement('article');card.className='map-card';card.innerHTML='<header><select aria-label="选择气象图"></select><time class="map-time"></time></header><div class="weather-map"></div><div class="legend"><div class="legend-bar"></div><div class="legend-text"></div></div>';const select=card.querySelector('select');for(const [k,s]of Object.entries(layers)){const o=document.createElement('option');o.value=k;o.textContent=s[0];select.append(o);}select.value=choices[i];$('map-grid').append(card);const view=new MapView(card,choices[i]);views.push(view);if(center)view.map.setView(center,zoom,{animate:false});const legend=()=>{const spec=layers[view.key];card.querySelector('.legend-text').textContent=`${spec[2]}${view.key==='velocity'?' 靠近':''} — ${spec[3]} ${spec[1]}${view.key==='velocity'?' 远离':''}`;card.querySelector('.legend-bar').style.background=`linear-gradient(90deg,${[0,.25,.5,.75,1].map(a=>'rgb('+color(view.key,spec[2]+a*(spec[3]-spec[2])).join(',')+')').join(',')})`;};select.onchange=()=>{choices[i]=view.key=select.value;legend();view.draw();};legend();}
   update();
 }
 function download(name,text,type='application/json'){const url=URL.createObjectURL(new Blob([text],{type})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 async function init(){
   for(const [key,name,unit]of obs){const div=document.createElement('div'),label=document.createElement('span'),strong=document.createElement('strong'),small=document.createElement('small');label.textContent=name;strong.id='obs-'+key;strong.textContent='—';small.textContent=unit;div.append(label,strong,small);$('observations').append(div);}
   try{const raw=JSON.parse(localStorage.getItem(STORAGE)||'[]');if(Array.isArray(raw))custom=raw.filter(s=>s&&/^custom-/.test(s.id)&&typeof s.name==='string'&&s.name.length<=30&&Number.isFinite(s.lon)&&Number.isFinite(s.lat)&&s.lon>=104.3&&s.lon<=118&&s.lat>=19.8&&s.lat<=26.7).slice(0,50);}catch(_){}
   if(localFile){stations=[selected];$('station-message').textContent='请通过本地预览载入完整站表。';}
   else try{const res=await fetch('assets/data/simulator-stations.json');if(!res.ok)throw Error();stations=(await res.json()).stations.filter(s=>majorCities[s.id]).map(s=>({...s,stationName:s.name,name:majorCities[s.id]}));stations.sort((a,b)=>a.province.localeCompare(b.province,'zh')||a.name.localeCompare(b.name,'zh'));selected=stations.find(s=>s.id==='59493')||selected;}catch(_){stations=[selected];$('station-message').textContent='站表加载失败，仅保留深圳参考点。';}
   stationOptions();maps(2);
   $('empty-state').hidden=false;say('选择时间流速，开始一轮天气演变');update();
 }
 $('start-simulation').onclick=()=>startCompute().catch(e=>{stopCompute();lastError=e.message;computeState='error';$('compute-status').textContent='暂时无法开始模拟：'+e.message+'。请通过本地预览或 HTTPS 访问。';});$('stop-compute').onclick=stopCompute;
 $('replay-slider').oninput=()=>{if(worker||roundLocked)return;pausePlayback();clearTimeout(replayTimer);replayRevision++;const position=+$('replay-slider').value;replayTimer=setTimeout(()=>seekReplay(position),80);};
 $('toggle-playback').onclick=()=>{if(playbackState==='playing'){pausePlayback();replayRevision++;busy=false;say('播放已暂停');}else startPlayback();};
 $('flow-rate').onchange=()=>{if(playbackState==='playing')schedulePlayback();};
 document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>maps(+b.dataset.layout));
 $('basemap').onchange=()=>views.forEach(v=>v.setBase());$('show-stations').onchange=()=>views.forEach(v=>v.markers());for(const id of ['show-front','opacity','radar-elevation','fold-velocity'])$(id).oninput=()=>views.forEach(v=>v.draw());
 $('view-region').onclick=()=>views[0].map.fitBounds(REGION,{animate:true});$('view-prd').onclick=()=>views[0].map.setView([22.65,113.7],9,{animate:true});
 $('station-search').oninput=stationOptions;$('station-select').onchange=()=>select($('station-select').value);$('station-center').onclick=()=>views[0].map.setView([selected.lat,selected.lon],10);$('station-radar').onclick=()=>{radar={...selected};$('radar-name').textContent='虚拟雷达：'+radar.name;views.forEach(v=>v.draw());};
 $('add-on-map').onclick=()=>{picking=!picking;$('add-on-map').textContent=picking?'点击地图后命名…':'＋ 地图选点';};
 $('station-form').onsubmit=e=>{e.preventDefault();const name=$('custom-name').value.trim(),lon=+$('custom-lon').value,lat=+$('custom-lat').value;if(!name||name.length>30||!Number.isFinite(lon)||!Number.isFinite(lat)||lon<104.3||lon>118||lat<19.8||lat>26.7||custom.length>=50){$('station-message').textContent='请检查名称、坐标及 50 个自定义点上限。';return;}const s={id:'custom-'+crypto.randomUUID(),name,lon,lat,kind:'custom'};custom.push(s);const saved=customSave();$('station-search').value='';select(s.id);$('station-message').textContent=saved?'已保存，直接读取当前网格状态。':'仅在本次页面有效：浏览器存储不可用。';};
 $('delete-station').onclick=()=>{if(selected.kind!=='custom')return;custom=custom.filter(s=>s.id!==selected.id);const saved=customSave();select(stations[0].id);$('station-message').textContent=saved?'自定义点已删除。':'本次已删除，但浏览器存储写入失败。';};
 $('export-station').onclick=()=>{const rows=records.get(selected.id);if(!rows?.size)return;const keys=['hour',...obs.map(x=>x[0])],lines=['TEACHING SIMULATION — loaded frames only',keys.join(',')];for(const o of [...rows.values()].sort((a,b)=>a.hour-b.hour))lines.push(keys.map(k=>Number.isFinite(o[k])?o[k]:'').join(','));download('simulation-observations.csv',lines.join('\n'),'text/csv');};
 let resize;window.addEventListener('resize',()=>{clearTimeout(resize);resize=setTimeout(()=>{views.forEach(v=>{v.map.invalidateSize();v.limitView();});profile();},150);});
 window.Simulator={getState:()=>({edition,manifest,frame,current,busy,computeState,playbackState,lastError,flowRate:+$('flow-rate').value,replayFrames:entries.length,stationCount:stations.length+custom.length,selected,layers:views.map(v=>v.key),maps:views.map(v=>({zoom:v.map.getZoom(),minZoom:v.map.getMinZoom(),center:v.map.getCenter(),rasterBuilds:v.rasterBuilds,markerBuilds:v.markerBuilds||0,frontSegments:v.front.getLatLngs().length})),cacheSize:Math.max(frame?1:0,replayCache.size)})};
 $('start-simulation').disabled=true;
 init().then(()=>{const unsupported=openingError();if(unsupported)showOpeningError(unsupported);else $('start-simulation').disabled=false;}).catch(e=>showOpeningError('初始化失败：'+e.message));
})();
