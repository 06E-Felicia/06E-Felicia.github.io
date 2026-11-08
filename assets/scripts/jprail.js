const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const GRADES = {
 highspeed:{label:'高速铁路 / 新干线',color:'#ff0c00'},main:{label:'主干线',color:'#ff8100'},
 branch:{label:'支线',color:'#c4b600'},industrial:{label:'工业 / 专用线',color:'#87491d'},
 subway:{label:'地铁',color:'#0300c3'},light_rail:{label:'轻轨',color:'#00bd14'},tram:{label:'路面电车',color:'#d877b8'},
 unclassified:{label:'未分类 / 其他',color:'#343c39'}
};
const JR_OPERATORS = {'北海道旅客鉄道':'JR 北海道','東日本旅客鉄道':'JR 东日本','東海旅客鉄道':'JR 东海','西日本旅客鉄道':'JR 西日本','四国旅客鉄道':'JR 四国','九州旅客鉄道':'JR 九州'};
const NATIONAL = [[30.0,128.0],[45.7,146.1]];
const state = {passes:[],network:null,stations:[],selected:null,active:null,layers:new Map(),displayed:[]};
let map, infra, stationMarker, toastTimer;
function toast(message) { $('toast').textContent=message; $('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500); }
function duration(p) { return p.durations.map(v=>typeof v==='number'?`${v} 日`:v).join(' / '); }
function currentDateJST() { return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()); }
export function gradeOf(feature) {return feature.properties.grade || (feature.properties.kind==='1'?'highspeed':'unclassified');}
export function railStyle(feature) {return {color:(GRADES[gradeOf(feature)]||GRADES.unclassified).color,weight:gradeOf(feature)==='highspeed'?3.4:2.5,opacity:1};}
export function matchesRailFilters(feature,grade,operator) {
 if(grade && gradeOf(feature)!==grade)return false;
 const op=feature.properties.operator;
 return !operator || (operator==='jr'?Object.hasOwn(JR_OPERATORS,op):operator==='private'?!Object.hasOwn(JR_OPERATORS,op):op===operator);
}
function outcode([x,y],b) { return (x<b[0]?1:0)|(x>b[2]?2:0)|(y<b[1]?4:0)|(y>b[3]?8:0); }
// Clip to the declared schematic boundary, never draw a whole long line because
// just one of its segments happens to intersect the region.
export function clipSegment(a,b,box) {
  a=[...a];b=[...b];let ca=outcode(a,box),cb=outcode(b,box);
  for(let tries=0;tries<12;tries++) {
    if(!(ca|cb))return [a,b];if(ca&cb)return null;
    const c=ca||cb;let x,y;
    if(c&8){y=box[3];x=a[0]+(b[0]-a[0])*(y-a[1])/(b[1]-a[1]);}
    else if(c&4){y=box[1];x=a[0]+(b[0]-a[0])*(y-a[1])/(b[1]-a[1]);}
    else if(c&2){x=box[2];y=a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0]);}
    else{x=box[0];y=a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0]);}
    if(c===ca){a=[x,y];ca=outcode(a,box);}else{b=[x,y];cb=outcode(b,box);}
  }return null;
}
function clipLine(coords,box) {
  const out=[];let current=[];
  for(let i=1;i<coords.length;i++) {
    const pair=clipSegment(coords[i-1],coords[i],box);
    if(!pair){if(current.length>1)out.push(current);current=[];continue;}
    const last=current.at(-1);
    if(last&&(Math.abs(last[0]-pair[0][0])>1e-6||Math.abs(last[1]-pair[0][1])>1e-6)){if(current.length>1)out.push(current);current=[];}
    if(!current.length)current.push(pair[0]);current.push(pair[1]);
  }if(current.length>1)out.push(current);return out;
}
export function coverageFeatures(network,pass) {
  const result=[];
  for(const f of network.features) {
    const p=f.properties;const segments=[];
    for(const s of pass.selectors) {
      if(!s.operators.includes(p.operator))continue;
      if(s.kinds&&!s.kinds.includes(p.kind))continue;
      if(s.lines&&!s.lines.some(n=>p.name.includes(n)))continue;
      if(s.exclude&&s.exclude.some(n=>p.name.includes(n)))continue;
      const lines=f.geometry.type==='LineString'?[f.geometry.coordinates]:f.geometry.coordinates;
      if(!s.bbox)segments.push(...lines);else for(const line of lines)segments.push(...clipLine(line,s.bbox));
    }
    if(segments.length)result.push({type:'Feature',properties:p,geometry:{type:'MultiLineString',coordinates:segments}});
  }return result;
}
function linePopup(f,selected=false) {
 return `<strong>${esc(f.properties.name)}</strong><br>${esc(f.properties.operator)}<br><small>${esc((GRADES[gradeOf(f)]||GRADES.unclassified).label)}</small>${selected?'<br><small>Pass 范围示意；请核对产品区间与列车限制。</small>':''}`;
}
function setupMap() {
 map=L.map('map',{preferCanvas:true,zoomAnimation:false,minZoom:4,maxZoom:18,maxBounds:[[18,118],[50,156]],maxBoundsViscosity:.4}).fitBounds(NATIONAL,{padding:[12,12]});
 for(const [name,z] of [['railLand',150],['railRoutes',350],['railInfrastructure',300]])map.createPane(name).style.zIndex=z;
 infra=L.tileLayer('https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png',{subdomains:'abc',pane:'railInfrastructure',minZoom:6,maxNativeZoom:19,maxZoom:18,attribution:'<a href="https://www.openrailwaymap.org/">OpenRailwayMap</a> · © <a href="https://www.openstreetmap.org/copyright">OSM</a>'});
 infra.on('tileerror',()=>{if($('infrastructure').checked)toast('在线设施瓦片未能加载，本地线路仍可使用。');});
 $('infrastructure').addEventListener('change',syncInfrastructure);
 $('resetView').addEventListener('click',()=>map.fitBounds(NATIONAL,{padding:[12,12],animate:false}));
 for(const id of ['railGrade','railOperator'])$(id).addEventListener('change',()=>{renderSelection();renderDetail();updateURL();fitDisplayed();});
 $('clearRailFilters').onclick=()=>{$('railGrade').value='';$('railOperator').value='';renderSelection();renderDetail();updateURL();};
 map.attributionControl.addAttribution('<a href="https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-2025.html">N02-25（加工）</a> · © <a href="https://www.openstreetmap.org/copyright">OSM</a> · <a href="https://www.naturalearthdata.com/">Natural Earth</a>');
}
function syncInfrastructure() {
 const filtered=Boolean(state.selected||$('railGrade').value||$('railOperator').value);
 $('infrastructure').disabled=filtered;
 if(filtered)$('infrastructure').checked=false;
 const detailed=!filtered&&$('infrastructure').checked;
 if(detailed)infra.addTo(map);else if(map.hasLayer(infra))map.removeLayer(infra);
 for(const layer of state.layers.values())layer.setStyle(f=>({...railStyle(f),opacity:detailed?0:1}));
 $('infrastructureHint').textContent=filtered?'筛选中：仅显示匹配线路':'原图含货运、站场、专用与停用设施';
}
function fitDisplayed() {const layer=state.layers.values().next().value;if(layer?.getBounds().isValid())map.fitBounds(layer.getBounds(),{padding:[25,25],maxZoom:12,animate:false});}
function renderList() {
  const q=$('passSearch').value.trim().toLocaleLowerCase(),region=$('regionFilter').value,group=$('operatorFilter').value;
  const list=state.passes.filter(p=>(!q||[p.name,p.en,p.issuer,p.scope,...p.regions].join(' ').toLocaleLowerCase().includes(q))&&(!region||p.regions.includes(region))&&(!group||p.group===group)&&($('showEnded').checked||p.status==='current'));
  $('resultCount').textContent=`${list.length} 种匹配票券`;
  $('passList').innerHTML=list.length?list.map(p=>`<button type="button" class="pass-card ${state.selected===p.id?'selected':''}" data-pass="${p.id}" aria-pressed="${state.selected===p.id}" style="--pass-color:#26746c"><span class="card-top"><span>${esc(p.issuer)}</span>${p.status==='ended'?'<span class="badge">已停售 / 已结束</span>':''}</span><h3>${esc(p.name)}</h3><p class="english">${esc(p.en)}</p><span class="card-bottom"><strong>${esc(duration(p))}</strong><span>${esc(p.regions.slice(0,2).join(' · '))} <span class="card-arrow">↗</span></span></span></button>`).join(''):'<p class="no-results">没有匹配的票券。可试试地区、运营商或勾选历史票券。</p>';
}
function updateURL() {
 const url=new URL(location.href);url.searchParams.delete('passes');
 for(const [name,value] of [['pass',state.selected],['grade',$('railGrade').value],['operator',$('railOperator').value]])value?url.searchParams.set(name,value):url.searchParams.delete(name);
 history.replaceState(null,'',url.pathname+url.search+url.hash);
}
function renderSelection() {
 const pass=state.passes.find(p=>p.id===state.selected),grade=$('railGrade').value,operator=$('railOperator').value;
 $('selectedPasses').innerHTML=pass?`<button class="selected-chip" type="button" data-focus="${pass.id}" style="--pass-color:#26746c">${esc(pass.name)}</button>`:'<span>全国客运铁路</span>';
 $('clearSelection').hidden=!state.selected;
 for(const layer of state.layers.values())map.removeLayer(layer);state.layers.clear();
 if(!state.network)return;
 const features=(pass?coverageFeatures(state.network,pass):state.network.features).filter(f=>matchesRailFilters(f,grade,operator));
 state.displayed=features;
 const layer=L.geoJSON({type:'FeatureCollection',features},{pane:'railRoutes',style:railStyle,onEachFeature:(f,l)=>l.bindPopup(linePopup(f,Boolean(pass)))}).addTo(map);
 state.layers.set(pass?.id||'filtered',layer);syncInfrastructure();
 const title=pass?pass.name:'全国客运铁路';
 $('mapState').textContent=`${title} · ${features.length} 个匹配线路组${features.length?'':'，请调整筛选条件'}`;
 const counts=new Map();for(const f of features)counts.set(f.properties.operator,(counts.get(f.properties.operator)||0)+1);
 $('railResults').innerHTML=[...counts].sort((a,b)=>a[0].localeCompare(b[0],'ja')).map(([op,n])=>`<span>${esc(JR_OPERATORS[op]||op)} <b>${n}</b></span>`).join('')||'<span>没有匹配线路</span>';
 $('clearRailFilters').hidden=!grade&&!operator;
}
function fitPass(id) {fitDisplayed();if(!state.displayed.length)toast('当前 Pass 与筛选条件没有匹配线路。');}
function showPass(id,fit=true) {
 state.selected=id;state.active=id;renderSelection();renderList();renderDetail();updateURL();if(fit)fitPass(id);
}
function removePass(id) {state.selected=null;state.active=null;renderSelection();renderList();renderDetail();updateURL();}
function renderDetail() {
 const p=state.passes.find(p=>p.id===state.active);
 $('detailPanel').classList.toggle('has-selection',Boolean(p));
 if(!p){$('passDetail').innerHTML='<div class="detail-empty"><span class="big-rail">↝</span><span class="eyebrow">PICK A PASS</span><h2>让票券范围<br>在地图上展开</h2><p>从左侧选择一张周游券，查看可乘线路、有效时间和需要另外付费的列车。</p></div>';return;}
 const routes=state.layers.get(p.id)?.getLayers().length||0;
 $('passDetail').innerHTML=`<div class="detail-top"><span class="eyebrow">${esc(p.issuer)}</span><button id="closeDetail" type="button" aria-label="收起详情">×</button></div><h2>${esc(p.name)}</h2><p class="detail-en">${esc(p.en)}</p><div class="detail-duration"><span class="duration-value">${esc(duration(p))}</span><span class="duration-copy">${p.continuous?'连续使用':'可非连续使用'}<br>时间以日本当地为准</span></div><span class="precision-tag">范围示意 · 非精确票券适用图</span>${p.status==='ended'?'<p class="ended-note">此产品已停售或当季已结束，请勿将历史资料当作当前可购票券。</p>':''}<div class="route-count">地图匹配 ${routes} 个运营商 / 线路组 · <button class="detail-fit" type="button" id="fitPass">定位范围</button> · <button class="detail-fit" type="button" id="removePass">移除</button></div><section class="detail-section"><h3>可乘铁路范围</h3><p>${esc(p.scope)}</p>${p.note?`<p>${esc(p.note)}</p>`:''}</section><section class="detail-section"><h3>适用列车</h3><p>${esc(p.trains)}</p></section>${p.exceptions.length?`<section class="detail-section restriction-box"><h3>乘车前，留意这些限制</h3><ul>${p.exceptions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></section>`:''}<section class="detail-section"><h3>销售与使用时间</h3><dl class="detail-period"><div><dt>销售 / 兑换</dt><dd>${esc(p.sales)}</dd></div><div><dt>使用期间</dt><dd>${esc(p.use)}</dd></div><div><dt>购买资格</dt><dd>${esc(p.eligibility)}</dd></div></dl></section><section class="detail-section"><h3>估算有效期</h3><div class="date-check"><label class="sr-only" for="startDate">起始日期</label><input type="date" id="startDate" value="${currentDateJST()}"><label class="sr-only" for="durationChoice">有效时长</label><select id="durationChoice">${p.durations.map((d,i)=>`<option value="${i}">${esc(typeof d==='number'?d+' 日':d)}</option>`).join('')}</select></div><p class="date-result" id="dateResult"></p><p style="font-size:9px;color:#6d7c78">仅计算日历有效期，不代表有票或符合购买资格。</p></section><section class="detail-section"><h3>附带权益</h3><p>${esc(p.extras)}</p></section><a class="official-link" href="${esc(p.source)}" target="_blank" rel="noopener">官方产品与范围图 ↗</a><p class="detail-sources">来源核查：${esc(p.checked)}</p>`;
 $('closeDetail').onclick=()=>{state.active=null;renderDetail();};
 $('fitPass').onclick=()=>fitPass(p.id);$('removePass').onclick=()=>removePass(p.id);
 $('startDate').onchange=()=>renderDate(p);$('durationChoice').onchange=()=>renderDate(p);renderDate(p);
}
function renderDate(p) {
 const start=$('startDate').value,d=p.durations[Number($('durationChoice').value)];if(!start){$('dateResult').textContent='请选择起始日期';return;}
 if(p.status==='ended'){$('dateResult').textContent='历史票券：不推定现在仍可使用，请核对已购票面。';return;}
 if(typeof d!=='number'){$('dateResult').textContent=d.includes('小时')?'自首次启用时刻起连续 24 小时；以实际票面为准。':'当日有效；京阪按 03:00 起的交通日规则使用。';return;}
 if(!p.continuous){$('dateResult').textContent=`有效期内任选 ${d} 日；终止日期须核对票面。`;return;}
 const date=new Date(start+'T12:00:00Z');date.setUTCDate(date.getUTCDate()+d-1);const end=date.toISOString().slice(0,10);
 $('dateResult').textContent=`${start} — ${end}（日本时间）${p.use.includes('03:00')?'；结束时刻按次日 02:59 计算':''}`;
 if(p.useEnd&&end>p.useEnd)$('dateResult').textContent+='，超出已记录使用截止日。';
}
function setupStationSearch() {
 const aliases={'东京':'東京','大阪':'大阪','京都':'京都','札幌':'札幌','横滨':'横浜','名古屋':'名古屋','广岛':'広島','福冈':'博多','新宿':'新宿','镰仓':'鎌倉'};
 $('stationSearch').addEventListener('input',()=>{
  const raw=$('stationSearch').value.trim(),q=aliases[raw]||raw;
  if(!q){$('stationResults').innerHTML='';return;}
  const result=state.stations.map((s,i)=>({s,i})).filter(({s})=>s[0].includes(q)||s[4].includes(q)).sort((a,b)=>Number(b.s[0]===q)-Number(a.s[0]===q)).slice(0,8);
  $('stationResults').innerHTML=result.length?result.map(({s,i})=>`<button type="button" data-station="${i}">${esc(s[0])}<small>${esc(s[3])} · ${esc(s[4])}</small></button>`).join(''):'<button type="button" disabled>未找到车站；可尝试日文站名</button>';
 });
 $('stationResults').addEventListener('click',e=>{
  const b=e.target.closest('[data-station]');if(!b)return;const s=state.stations[Number(b.dataset.station)];map.setView([s[1],s[2]],13,{animate:false});
  if(stationMarker)map.removeLayer(stationMarker);stationMarker=L.circleMarker([s[1],s[2]],{radius:6,color:'#193c3f',fillColor:'#fffefa',fillOpacity:1,weight:2}).addTo(map).bindPopup(`<strong>${esc(s[0])}</strong><br>${esc(s[3])} · ${esc(s[4])}`).openPopup();$('stationResults').innerHTML='';$('stationSearch').value=s[0];
 });
 $('stationSearch').addEventListener('keydown',e=>{if(e.key==='Escape')$('stationResults').innerHTML='';if(e.key==='Enter')$('stationResults').querySelector('button:not([disabled])')?.click();});
 document.addEventListener('click',e=>{if(!e.target.closest('.station-search'))$('stationResults').innerHTML='';});
}
async function json(path) {const r=await fetch(path);if(!r.ok)throw new Error(`${r.status}`);return r.json();}
async function start() {
 if(!window.L){$('mapState').textContent='地图组件加载失败，请刷新页面。';return;}setupMap();
 ['passSearch','regionFilter','operatorFilter','showEnded'].forEach(id=>$(id).addEventListener(id==='passSearch'?'input':'change',renderList));
 $('passList').addEventListener('click',e=>{const card=e.target.closest('[data-pass]');if(card)showPass(card.dataset.pass);});
 $('selectedPasses').addEventListener('click',e=>{const c=e.target.closest('[data-focus]');if(c)showPass(c.dataset.focus);});
 $('clearSelection').onclick=()=>removePass(state.selected);
 $('aboutBtn').onclick=()=>$('aboutDialog').showModal();$('closeAbout').onclick=()=>$('aboutDialog').close();
 try {
  const [catalog,network,land]=await Promise.all([json('assets/data/jprail/passes.json'),json('assets/data/jprail/network.geojson'),json('assets/data/jprail/japan.geojson')]);
  state.passes=catalog.passes;state.network=network;$('coverageNote').textContent=catalog.coverageNote;
  L.geoJSON(land,{pane:'railLand',interactive:false,style:{color:'#b9c9b5',weight:1,fillColor:'#f7f5e9',fillOpacity:1}}).addTo(map);
  for(const [value,item] of Object.entries(GRADES)){const option=document.createElement('option');option.value=value;option.textContent=item.label;$('railGrade').append(option);}
  const operators=[...new Set(network.features.map(f=>f.properties.operator))].sort((a,b)=>a.localeCompare(b,'ja'));
  for(const [value,label] of [['jr','JR 六家公司'],['private','私铁 / 第三部门 / 公营'],...Object.entries(JR_OPERATORS),...operators.filter(op=>!Object.hasOwn(JR_OPERATORS,op)).map(op=>[op,op])]){const option=document.createElement('option');option.value=value;option.textContent=label;$('railOperator').append(option);}
  $('catalogCount').textContent=`${state.passes.filter(p=>p.status==='current').length} 种现行`;
  $('dataDate').textContent=`票券核查 ${catalog.checked} · 非实时售票信息`;
  const regions=['全国','北海道','东北','关东','甲信越','东海','北陆','关西','中国','四国','九州'];
  for(const region of regions){const option=document.createElement('option');option.value=region;option.textContent=region;$('regionFilter').append(option);}
  renderList();
  const params=new URLSearchParams(location.search);
  if([...$('railGrade').options].some(x=>x.value===params.get('grade')))$('railGrade').value=params.get('grade');
  if([...$('railOperator').options].some(x=>x.value===params.get('operator')))$('railOperator').value=params.get('operator');
  const id=params.get('pass')||(params.get('passes')||'').split(',')[0];
  if(state.passes.some(p=>p.id===id))showPass(id,false);else renderSelection();
  if(state.selected||$('railGrade').value||$('railOperator').value)fitDisplayed();
  window.JPRail={state,map,coverageFeatures,gradeOf,railStyle,matchesRailFilters};

 } catch(e) {$('passList').innerHTML='<p class="no-results">数据加载失败，请刷新页面或检查本地文件是否完整。</p>';$('resultCount').textContent='目录读取失败';$('mapState').textContent='铁路数据加载失败；在线设施图仍可浏览';console.error('JPRail data load:',e);}
 try{state.stations=await json('assets/data/jprail/stations.json');}catch{$('stationSearch').placeholder='车站数据暂不可用';}
 setupStationSearch();
}

start();
