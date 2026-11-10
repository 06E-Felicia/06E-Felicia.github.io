import {createStationLabels} from './jprail-stations.js?v=20261110-touch2';
import {createCamera} from './jprail-camera.js?v=20261110-touch2';
import {createStreetMap} from './jprail-basemap.js?v=20261110-touch2';
import {officialStationPins} from './jprail-boundaries.js?v=20261110-touch2';
import {createRailColors,JR_OPERATORS} from './jprail-colors.js?v=20261110-colors1';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const GRADES = {
 highspeed:{label:'高速铁路 / 新干线',color:'#ff0c00'},main:{label:'主干线',color:'#ff8100'},
 branch:{label:'支线',color:'#c4b600'},industrial:{label:'工业 / 专用线',color:'#87491d'},
 subway:{label:'地铁',color:'#0300c3'},light_rail:{label:'轻轨',color:'#00bd14'},tram:{label:'路面电车',color:'#d877b8'},
 unclassified:{label:'未分类 / 其他',color:'#343c39'}
};
const NATIONAL = [[30.7,129.35],[45.65,145.95]];
const state = {passes:[],network:null,overviewNetwork:null,detailNetwork:null,detailStatus:"overview",stations:[],boundaryMarkers:null,selected:null,active:null,layers:new Map(),passCoverage:[],displayed:[],paintFeatures:[],stationPool:[],pinnedStations:[],basemap:{status:"loading",tiles:0},stationLabels:{count:0,names:[],mode:"主要枢纽"}};
let map, infra, railRenderer, stationMarker, stationLabels, camera, streets, toastTimer, detailPromise, renderedBounds, railColors, homeView=true;
const geometryBounds=new WeakMap();
function toast(message) { $('toast').textContent=message; $('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500); }
function duration(p) { return p.durations.map(v=>typeof v==='number'?`${v} 日`:v).join(' / '); }
function currentDateJST() { return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()); }
export function gradeOf(feature) {return feature.properties.grade || (feature.properties.kind==='1'?'highspeed':'unclassified');}
export function railColorInfo(feature) {
 const themed=railColors?.forFeature(feature);
 if(themed)return themed;
 const grade=gradeOf(feature),item=GRADES[grade]||GRADES.unclassified;
 return {id:'other:'+grade,label:item.label+'（原等级色）',color:item.color,basis:'未纳入本次铁路公司配色'};
}
export function railStyle(feature) {return {color:railColorInfo(feature).color,weight:gradeOf(feature)==='highspeed'?4:3,opacity:1};}
export function matchesRailFilters(feature,grade,operator) {
 if(grade && gradeOf(feature)!==grade)return false;
 return railColors.matchesOperator(feature,operator);
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
  if(pass.routeFeatures&&!pass.routeOverridesOnly)return pass.routeFeatures;
  const result=[];
  for(const f of network.features) {
    const p=f.properties;const segments=[];
    if(pass.routeOverridesOnly&&pass.routeFeatureKeys.has(p.operator+'|'+p.name))continue;
    for(const s of pass.selectors) {
      if(!s.operators.includes(p.operator))continue;
      if(s.kinds&&!s.kinds.includes(p.kind))continue;
      if(s.lines&&!s.lines.some(n=>p.name.includes(n)))continue;
      if(s.lineNames&&!s.lineNames.includes(p.name))continue;
      if(s.exclude&&s.exclude.some(n=>p.name.includes(n)))continue;
      const lines=f.geometry.type==='LineString'?[f.geometry.coordinates]:f.geometry.coordinates;
      if(!s.bbox)segments.push(...lines);else for(const line of lines)segments.push(...clipLine(line,s.bbox));
    }
    if(segments.length)result.push({type:'Feature',properties:p,geometry:{type:'MultiLineString',coordinates:segments}});
  }return result.concat(pass.routeFeatures||[]);
}
function linePopup(f,selected=false) {
 const info=railColorInfo(f),op=railColors.operatorOf(f.properties.operator);
 return `<strong>${esc(f.properties.name)}</strong><br>${esc(op)}<br><small>${esc(info.label)} · ${esc(info.basis)}</small>${info.source?`<br><a href="${esc(info.source)}" target="_blank" rel="noopener">配色参考来源 ↗</a>`:''}${selected?'<br><small>Pass 范围示意；请核对产品区间与列车限制。</small>':''}`;
}

function renderColorLegend(features) {
 const items=new Map();
 for(const feature of features){const info=railColorInfo(feature);items.set(info.id,info);}
 const sorted=[...items.values()].sort((a,b)=>{
  const rank=id=>id==='shinkansen'?0:id==='jr'?1:id.startsWith('operator:')?2:3;
  return rank(a.id)-rank(b.id)||a.label.localeCompare(b.label,'ja');
 });
 state.colorLegend=sorted;
 $('railLegendItems').innerHTML=sorted.map(info=>`<span title="${esc(info.basis)}"><i style="--rail:${info.color}"></i>${esc(info.label)}</span>`).join('')||'<span>当前筛选没有匹配线路</span>';
 $('railLegendNote').textContent=$('infrastructure').checked?'设施原图使用 OpenRailwayMap 自身等级配色。':'仅列出当前匹配线路。JR 普速橙黄色、新干线红色；私铁采用公司标识或注明来源的替代参考色。颜色不表示乘车权限。';
}
function setupMap() {
 map=L.map('map',{preferCanvas:true,zoomAnimation:true,zoomAnimationThreshold:4,zoomControl:false,zoomSnap:0,zoomDelta:.25,scrollWheelZoom:false,inertiaMaxSpeed:850,inertiaDeceleration:2200,minZoom:4,maxZoom:18,maxBounds:[[22,119],[49,156.3]],maxBoundsViscosity:.8}).fitBounds(NATIONAL,{padding:[12,12]});
 for(const [name,z] of [['railLand',150],['railBase',200],['railRoutes',350],['railInfrastructure',300],['railStations',450],['railBoundaries',475]])map.createPane(name).style.zIndex=z;
 // A continuous zoom scales the previous raster between refreshes. Keep
 // enough real painted margin for a .35-level zoom even at a corner anchor.
 railRenderer=L.canvas({pane:'railRoutes',padding:.3});
 state.boundaryMarkers=L.layerGroup().addTo(map);
 infra=L.tileLayer('https://{s}.tiles.openrailwaymap.org/standard/{z}/{x}/{y}.png',{subdomains:'abc',pane:'railInfrastructure',minZoom:6,maxNativeZoom:19,maxZoom:18,attribution:'<a href="https://www.openrailwaymap.org/">OpenRailwayMap</a> · © <a href="https://www.openstreetmap.org/copyright">OSM</a>'});
 infra.on('tileerror',()=>{if($('infrastructure').checked)toast('在线设施瓦片未能加载，本地线路仍可使用。');});
 $('infrastructure').addEventListener('change',()=>{syncInfrastructure();updateDetailLevel();});
 map.on('zoomend',syncInfrastructure);
 map.on('zoomend',updateDetailLevel);
 map.on('camerarefresh',()=>{if(state.network){
  // Reset an empty renderer, then project each exact visible path once.
  for(const layer of state.layers.values())map.removeLayer(layer);state.layers.clear();
  map.fire('viewreset');renderRoutes(true);
  // Leaflet 1.9.4 normally defers Canvas paint another frame. Complete this
  // refreshed buffer now so a continuous gesture never paints a blank frame.
  L.Util.cancelAnimFrame(railRenderer._redrawRequest);railRenderer._redraw();
  stationLabels?.schedule();
 }});
 map.on('moveend',()=>{if(state.network&&state.detailStatus==='detail')renderRoutes();});
 $('resetView').addEventListener('click',fitHome);
 map.on('dragstart zoomstart',()=>homeView=false);
 const observer=new ResizeObserver(()=>{map.invalidateSize({pan:false});if(homeView)fitHome();});observer.observe($('map'));
 camera=createCamera(map);
 streets=createStreetMap(map,summary=>{state.basemap=summary;});
 stationLabels=createStationLabels(map,()=>state.stationPool,summary=>{state.stationLabels=summary;$('stationDensity').textContent=`站名：${summary.mode} · ${summary.count} 站${summary.pinnedNames.length?' · 常驻 '+summary.pinnedNames.length+' 站':''}`;},()=>state.pinnedStations,()=>state.paintFeatures);
 $('map').closest('.map-frame').querySelector('.rail-legend').addEventListener('toggle',()=>stationLabels.schedule());
 fitHome();
 for(const id of ['railGrade','railOperator'])$(id).addEventListener('change',()=>{renderSelection();renderDetail();updateURL();fitDisplayed();});
 $('clearRailFilters').onclick=()=>{$('railGrade').value='';$('railOperator').value='';renderSelection();renderDetail();updateURL();};
 map.attributionControl.addAttribution('<a href="https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-2025.html">N02-25（加工）</a> · © <a href="https://www.openstreetmap.org/copyright">OSM</a> · <a href="https://www.naturalearthdata.com/">Natural Earth</a>');
}

function fitHome() {camera.fitBounds(NATIONAL,{padding:[8,8]});homeView=true;}
function refreshStationPool() {
 const routes=new Map();for(const f of state.displayed){const p=f.properties;routes.set(p.operator+'|'+p.name,p);}
 const pass=state.passes.find(p=>p.id===state.selected);
 state.pinnedStations=officialStationPins(pass,state.stations);
 state.boundaryMarkers.clearLayers();
 for(const pin of state.pinnedStations.filter(pin=>['boundary','terminus'].includes(pin.role))){
  const boundary=pin.role==='boundary',company=pin.boundaryKind==='company';
  const color=company?'#116979':boundary?'#126958':'#405859';
  L.circleMarker([pin.station[1],pin.station[2]],{pane:'railBoundaries',radius:boundary?6.5:4.5,color,weight:boundary?2.2:1.5,fill:false,dashArray:company?'3 2':null})
   .bindTooltip(`${esc(pin.name)} · ${company?'本券止于公司局界':boundary?'指定线路适用边界':'已含铁路端点'}`)
   .bindPopup(`<strong>${esc(pin.name)}</strong><br>${esc(pin.note)}`).addTo(state.boundaryMarkers);
 }
 state.stationPool=state.stations.filter(s=>{
  const p=routes.get(s[3]+'|'+s[4]);if(!p)return false;
  if(pass?.routeStationKeys&&(!pass.routeOverridesOnly||pass.routeFeatureKeys.has(s[3]+'|'+s[4]))){
   if(!pass.routeStationKeys.has(s[3]+'|'+s[4]+'|'+s[0]))return false;
   if(pass.routeOverridesOnly)return true;
  }
  return !pass||pass.selectors.some(a=>a.operators.includes(p.operator)&&(!a.kinds||a.kinds.includes(p.kind))&&(!a.lines||a.lines.some(n=>p.name.includes(n)))&&(!a.lineNames||a.lineNames.includes(p.name))&&(!a.exclude||!a.exclude.some(n=>p.name.includes(n)))&&(!a.bbox||(s[2]>=a.bbox[0]&&s[2]<=a.bbox[2]&&s[1]>=a.bbox[1]&&s[1]<=a.bbox[3])));
 });
 stationLabels?.schedule();
}

function syncInfrastructure() {
 const filtered=Boolean(state.selected||$('railGrade').value||$('railOperator').value);
 $('infrastructure').disabled=filtered;
 if(filtered)$('infrastructure').checked=false;
 const detailed=!filtered&&$('infrastructure').checked;
 if(detailed)infra.addTo(map);else if(map.hasLayer(infra))map.removeLayer(infra);
 const showDetailed=detailed&&map.getZoom()>=6;
 for(const layer of state.layers.values()) {
  if(showDetailed&&map.hasLayer(layer))map.removeLayer(layer);
  else if(!showDetailed&&!map.hasLayer(layer))layer.addTo(map);
 }
 $('infrastructureHint').textContent=filtered?'筛选中：仅显示匹配线路':detailed&&!showDetailed?'放大地图以显示详细设施':'原图含货运、站场、专用与停用设施';
 // The optional raster has its own grade palette and cannot inherit our
 // company colors. Do not show a company legend for that separate layer.
 $('railLegendItems').hidden=showDetailed;
 $('railLegendNote').textContent=showDetailed?'当前显示 OpenRailwayMap 设施原图，请使用其完整等级图例。':'仅列出当前匹配线路。JR 普速橙黄色、新干线红色；私铁采用公司标识或注明来源的替代参考色。颜色不表示乘车权限。';
}
function fitDisplayed() {const bounds=L.latLngBounds([]);for(const f of state.displayed)bounds.extend(featureBounds(f));if(bounds.isValid()){for(const pin of state.pinnedStations)bounds.extend([pin.station[1],pin.station[2]]);camera.fitBounds(bounds,{padding:[36,50],maxZoom:12});}}
function renderList() {
  const q=$('passSearch').value.trim().toLocaleLowerCase(),region=$('regionFilter').value,group=$('operatorFilter').value;
  const list=state.passes.filter(p=>(!q||[p.name,p.en,p.issuer,p.scope,...p.regions].join(' ').toLocaleLowerCase().includes(q))&&(!region||p.regions.includes(region))&&(!group||p.group===group)&&($('showEnded').checked||p.status==='current'));
  $('resultCount').textContent=`${list.length} 种匹配票券`;
  $('passList').innerHTML=list.length?list.map(p=>`<button type="button" class="pass-card ${state.selected===p.id?'selected':''}" data-pass="${p.id}" aria-pressed="${state.selected===p.id}" style="--pass-color:#26746c"><span class="card-top"><span>${esc(p.issuer)}</span>${p.status==='ended'?'<span class="badge">已停售 / 已结束</span>':''}${p.audit?.status==='partial'?'<span class="badge">范围待核</span>':''}</span><h3>${esc(p.name)}</h3><p class="english">${esc(p.en)}</p><span class="card-bottom"><strong>${esc(duration(p))}</strong><span>${esc(p.regions.slice(0,2).join(' · '))} <span class="card-arrow">↗</span></span></span></button>`).join(''):'<p class="no-results">没有匹配的票券。可试试地区、运营商或勾选历史票券。</p>';
}
function updateURL() {
 const url=new URL(location.href);url.searchParams.delete('passes');
 for(const [name,value] of [['pass',state.selected],['grade',$('railGrade').value],['operator',$('railOperator').value]])value?url.searchParams.set(name,value):url.searchParams.delete(name);
 history.replaceState(null,'',url.pathname+url.search+url.hash);
}
function featureBounds(feature) {
 if(geometryBounds.has(feature))return geometryBounds.get(feature);
 let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;
 const visit=coords=>{if(typeof coords[0]==='number'){minX=Math.min(minX,coords[0]);minY=Math.min(minY,coords[1]);maxX=Math.max(maxX,coords[0]);maxY=Math.max(maxY,coords[1]);}else for(const child of coords)visit(child);};
 if(feature.bbox)[minX,minY,maxX,maxY]=feature.bbox;else visit(feature.geometry.coordinates);
 const bounds=L.latLngBounds([[minY,minX],[maxY,maxX]]);geometryBounds.set(feature,bounds);return bounds;
}
// Keep exact source vertices; only omit whole off-screen chunks. Adjacent
// chunks share their endpoint, so no segment is cut or newly connected.
const railChunks=new WeakMap();
export function windowFeature(feature,view) {
 let chunks=railChunks.get(feature);
 if(!chunks){
  chunks=[];const lines=feature.geometry.type==='LineString'?[feature.geometry.coordinates]:feature.geometry.coordinates;
  for(const line of lines)for(let start=0;start<line.length-1;start+=127){
   const points=line.slice(start,start+128),bbox=[Infinity,Infinity,-Infinity,-Infinity];
   for(const p of points){bbox[0]=Math.min(bbox[0],p[0]);bbox[1]=Math.min(bbox[1],p[1]);bbox[2]=Math.max(bbox[2],p[0]);bbox[3]=Math.max(bbox[3],p[1]);}
   chunks.push({points,bbox});
  }
  railChunks.set(feature,chunks);
 }
 const coordinates=chunks.filter(({bbox:b})=>b[2]>=view[0]&&b[0]<=view[2]&&b[3]>=view[1]&&b[1]<=view[3]).map(c=>c.points);
 return {...feature,geometry:{type:'MultiLineString',coordinates},sourceFeature:feature};
}

function renderRoutes(force=false) {
 if(!state.network)return;
 const detail=state.detailStatus==='detail',view=map.getBounds();
 // The cache must cover the renderer's padded buffer, not just today's
 // visible rectangle, so the next wheel gesture cannot reveal a data hole.
 if(!force&&renderedBounds?.contains(view.pad(railRenderer.options.padding)))return;
 renderedBounds=detail?view.pad(.35):null;state.paintBounds=renderedBounds;
 for(const layer of state.layers.values())map.removeLayer(layer);state.layers.clear();
 const features=detail?state.displayed.filter(f=>featureBounds(f).intersects(renderedBounds)):state.displayed;
 const pass=state.passes.find(p=>p.id===state.selected);
 const b=renderedBounds;state.paintFeatures=detail?features.map(f=>windowFeature(f,[b.getWest(),b.getSouth(),b.getEast(),b.getNorth()])):features;
 const layer=L.geoJSON({type:'FeatureCollection',features:state.paintFeatures},{pane:'railRoutes',renderer:railRenderer,smoothFactor:detail?.15:1,style:railStyle,onEachFeature:(f,l)=>{const source=f.sourceFeature||f;l.feature=source;l.bindPopup(linePopup(source,Boolean(pass)));}}).addTo(map);
 state.layers.set(pass?.id||'filtered',layer);syncInfrastructure();
}
async function updateDetailLevel() {
 if(!state.network)return;
 const wanted=map.getZoom()>=10&&!$('infrastructure').checked;
 if(wanted&&!state.detailNetwork) {
  $('lineDetailStatus').textContent='精细线路载入中…';
  if(!detailPromise)detailPromise=Promise.all([json('assets/data/jprail/network-detail.geojson'),json('assets/data/jprail/pass-ranges-detail.json')]).then(([network,ranges])=>{
   state.detailNetwork=network;
   for(const p of state.passes)if(ranges[p.id]){p.detailRouteFeatures=ranges[p.id].features;p.detailRouteStationKeys=new Set(ranges[p.id].stationKeys);}
  }).catch(()=>{detailPromise=null;$('lineDetailStatus').textContent='精细线路读取失败，缩放后重试';});
  await detailPromise;
  if(!state.detailNetwork)return;
 }
 const useDetail=map.getZoom()>=10&&!$('infrastructure').checked&&Boolean(state.detailNetwork),next=useDetail?'detail':'overview';
 $('lineDetailStatus').textContent=useDetail?'线路：原始精细轨迹':'线路：全国概览';
 if(state.detailStatus===next)return;
 state.detailStatus=next;state.network=useDetail?state.detailNetwork:state.overviewNetwork;
 for(const p of state.passes)if(p.overviewRouteFeatures){p.routeFeatures=useDetail?p.detailRouteFeatures:p.overviewRouteFeatures;p.routeStationKeys=useDetail?p.detailRouteStationKeys:p.overviewRouteStationKeys;}
 renderSelection();
}
function renderSelection() {
 const pass=state.passes.find(p=>p.id===state.selected),grade=$('railGrade').value,operator=$('railOperator').value;
 $('selectedPasses').innerHTML=pass?`<button class="selected-chip" type="button" data-focus="${pass.id}" style="--pass-color:#26746c">${esc(pass.name)}</button>`:'<span>全国客运铁路</span>';
 $('clearSelection').hidden=!state.selected;
 if(!state.network)return;
 const coverage=pass?coverageFeatures(state.network,pass):state.network.features;state.passCoverage=pass?coverage:[];
 const features=coverage.filter(f=>matchesRailFilters(f,grade,operator));
 state.displayed=features;renderColorLegend(features);refreshStationPool();
 renderRoutes(true);
 const title=pass?pass.name:'全国客运铁路';
 $('mapState').textContent=`${title} · ${features.length} 个匹配线路组${features.length?'':'，请调整筛选条件'}`;
 const counts=new Map();for(const f of features){const op=railColors.operatorOf(f.properties.operator);counts.set(op,(counts.get(op)||0)+1);}
 $('railResults').innerHTML=[...counts].sort((a,b)=>a[0].localeCompare(b[0],'ja')).map(([op,n])=>`<span>${esc(JR_OPERATORS[op]||op)} <b>${n}</b></span>`).join('')||'<span>没有匹配线路</span>';
 $('clearRailFilters').hidden=!grade&&!operator;
}
function fitPass(id) {fitDisplayed();if(!state.displayed.length)toast('当前 Pass 与筛选条件没有匹配线路。');}
function showPass(id,fit=true) {
 homeView=false;state.selected=id;state.active=id;renderSelection();renderList();renderDetail();updateURL();if(fit)fitPass(id);
 if(fit&&matchMedia('(max-width:960px)').matches)requestAnimationFrame(()=>{
  if(state.selected===id&&state.active===id)$('map').closest('.map-frame').scrollIntoView({block:'start',behavior:'auto'});
 });
}
function removePass(id) {state.selected=null;state.active=null;renderSelection();renderList();renderDetail();updateURL();}
function renderPinnedStops(p) {
 const info=p.stationPins;if(!info)return '';
 const pins=info.stations,company=pins.filter(pin=>pin.boundaryKind==='company');
 return `<section class="detail-section"><h3>适用边界与铁路端点</h3><div class="boundary-stations">${pins.map(pin=>`<button type="button" data-boundary="${esc(pin.name)}" title="${esc(pin.note)}" class="${pin.role} ${pin.boundaryKind||''}">${esc(pin.name)}</button>`).join('')}</div>${company.length?`<p class="company-boundary-note">本券止于公司局界：${esc(company.map(pin=>pin.name).join('、'))}。蓝色虚圈只用于官方范围确认的外缘；内部接续不作边界。</p>`:''}<p style="font-size:10px;margin-top:8px">粗圆圈：指定线路适用边界；细圆圈：已含铁路端点。限制与通过条件见车站提示。站名始终显示；同站其他线路的范围可能不同。</p><a href="${esc(info.source)}" target="_blank" rel="noopener" style="font-size:10px">官方范围来源 ↗</a></section>`;
}
function renderAudit(p) {
 const audit=p.audit;if(!audit)return '';
 return `<section class="detail-section ${audit.status==='partial'?'restriction-box':''}"><h3>范围核对 · ${esc(audit.checked)}</h3><p>${audit.status==='partial'?'尚有未核实项目，不能将当前高亮视作完整可乘清单。':'已按官方产品与使用范围资料逐券整理。'}</p>${audit.issues.length?`<ul>${audit.issues.map(i=>`<li>${esc(i)}</li>`).join('')}</ul>`:''}<a href="assets/data/jprail/pass-audit.json" target="_blank" rel="noopener">逐券来源与核对记录 ↗</a></section>`;
}
function renderPrice(p) {
 const price=p.price;if(!price)return '';
 const rows=price.variants.map(v=>`<tr><td>${esc(typeof v.duration==='number'?v.duration+' 日':v.duration)}</td><td>${v.amountJPY===null?'无现行售价':'¥'+v.amountJPY.toLocaleString('ja-JP')}</td></tr>`).join('');
 return `<section class="price-section" aria-label="成人日元票价"><h3>${price.historical?'历史票价':'成人票价'} · 普通车厢 · JPY</h3><table aria-label="各有效时长票价"><tbody>${rows}</tbody></table><p>${esc(price.note)}</p><a href="${esc(price.source)}" target="_blank" rel="noopener">官方票价 ↗</a>${price.channelSource?` · <a href="${esc(price.channelSource)}" target="_blank" rel="noopener">渠道价差 ↗</a>`:''}<p>票价核查 ${esc(price.checked)} · 以购买时官方售价为准</p></section>`;
}
function renderDetail() {
 const p=state.passes.find(p=>p.id===state.active);
 const panel=$('detailPanel'),visible=Boolean(p),changed=panel.hidden===visible;
 panel.hidden=!visible;panel.classList.toggle('has-selection',visible);
 panel.closest('.workspace').classList.toggle('has-detail',visible);
 // Measure the new column width before fitting the selected pass. Waiting for
 // ResizeObserver would fit against the old, wider map and clip the range.
 if(changed)map.invalidateSize({pan:false});
 if(!p){$('passDetail').innerHTML='';return;}
 const routes=state.displayed.length;
 $('passDetail').innerHTML=`<div class="detail-top"><span class="eyebrow">${esc(p.issuer)}</span><button id="closeDetail" type="button" aria-label="收起详情">×</button></div><h2>${esc(p.name)}</h2><p class="detail-en">${esc(p.en)}</p><div class="detail-duration"><span class="duration-value">${esc(duration(p))}</span><span class="duration-copy">${p.continuous?'连续使用':'可非连续使用'}<br>时间以日本当地为准</span></div>${renderAudit(p)}${renderPrice(p)}<span class="precision-tag">范围示意 · 非精确票券适用图</span>${p.status==='ended'?'<p class="ended-note">此产品已停售或当季已结束，请勿将历史资料当作当前可购票券。</p>':''}<div class="route-count">地图匹配 ${routes} 个运营商 / 线路组 · <button class="detail-fit" type="button" id="fitPass">定位范围</button> · <button class="detail-fit" type="button" id="removePass">移除</button></div>${renderPinnedStops(p)}<section class="detail-section"><h3>可乘铁路范围</h3><p>${esc(p.scope)}</p>${p.note?`<p>${esc(p.note)}</p>`:''}</section><section class="detail-section"><h3>适用列车</h3><p>${esc(p.trains)}</p></section>${p.exceptions.length?`<section class="detail-section restriction-box"><h3>乘车前，留意这些限制</h3><ul>${p.exceptions.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></section>`:''}<section class="detail-section"><h3>销售与使用时间</h3><dl class="detail-period"><div><dt>销售 / 兑换</dt><dd>${esc(p.sales)}</dd></div><div><dt>使用期间</dt><dd>${esc(p.use)}</dd></div><div><dt>购买资格</dt><dd>${esc(p.eligibility)}</dd></div></dl></section><section class="detail-section"><h3>估算有效期</h3><div class="date-check"><label class="sr-only" for="startDate">起始日期</label><input type="date" id="startDate" value="${currentDateJST()}"><label class="sr-only" for="durationChoice">有效时长</label><select id="durationChoice">${p.durations.map((d,i)=>`<option value="${i}">${esc(typeof d==='number'?d+' 日':d)}</option>`).join('')}</select></div><p class="date-result" id="dateResult"></p><p style="font-size:9px;color:#6d7c78">仅计算日历有效期，不代表有票或符合购买资格。</p></section><section class="detail-section"><h3>附带权益</h3><p>${esc(p.extras)}</p></section><a class="official-link" href="${esc(p.source)}" target="_blank" rel="noopener">官方产品与范围图 ↗</a><p class="detail-sources">来源核查：${esc(p.checked)}</p>`;
 $('passDetail').querySelectorAll('[data-boundary]').forEach(button=>button.onclick=()=>{const pin=state.pinnedStations.find(p=>p.name===button.dataset.boundary);if(!pin)return;camera.setView([pin.station[1],pin.station[2]],13,()=>{map.closePopup();L.popup().setLatLng([pin.station[1],pin.station[2]]).setContent(`<strong>${esc(pin.name)}</strong><br>${esc(pin.note)}`).openOn(map);});});
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
 if(p.activationEnd&&start>p.activationEnd)$('dateResult').textContent+='，超出已记录启用截止日。';
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
  const b=e.target.closest('[data-station]');if(!b)return;const s=state.stations[Number(b.dataset.station)];camera.setView([s[1],s[2]],13,()=>{
  if(stationMarker)map.removeLayer(stationMarker);stationMarker=L.circleMarker([s[1],s[2]],{radius:6,color:'#193c3f',fillColor:'#fffefa',fillOpacity:1,weight:2}).addTo(map).bindPopup(`<strong>${esc(s[0])}</strong><br>${esc(s[3])} · ${esc(s[4])}`).openPopup();$('stationResults').innerHTML='';$('stationSearch').value=s[0];
  });
 });
 $('stationSearch').addEventListener('keydown',e=>{if(e.key==='Escape')$('stationResults').innerHTML='';if(e.key==='Enter')$('stationResults').querySelector('button:not([disabled])')?.click();});
 document.addEventListener('click',e=>{if(!e.target.closest('.station-search'))$('stationResults').innerHTML='';});
}
async function json(path) {const r=await fetch(path,{cache:'no-cache'});if(!r.ok)throw new Error(`${r.status}`);return r.json();}
async function start() {
 if(!window.L){$('mapState').textContent='地图组件加载失败，请刷新页面。';return;}setupMap();
 ['passSearch','regionFilter','operatorFilter','showEnded'].forEach(id=>$(id).addEventListener(id==='passSearch'?'input':'change',renderList));
 $('passList').addEventListener('click',e=>{const card=e.target.closest('[data-pass]');if(card)showPass(card.dataset.pass);});
 $('selectedPasses').addEventListener('click',e=>{const c=e.target.closest('[data-focus]');if(c)showPass(c.dataset.focus);});
 $('clearSelection').onclick=()=>removePass(state.selected);
 $('aboutBtn').onclick=()=>$('aboutDialog').showModal();$('closeAbout').onclick=()=>$('aboutDialog').close();
 try {
  const [catalog,network,land,ranges,palette]=await Promise.all([json('assets/data/jprail/passes.json'),json('assets/data/jprail/network.geojson'),json('assets/data/jprail/japan.geojson'),json('assets/data/jprail/pass-ranges.json'),json('assets/data/jprail/operator-colors.json')]);
  state.palette=palette;railColors=createRailColors(palette);
  for(const pass of catalog.passes)if(ranges[pass.id]){pass.routeFeatures=pass.overviewRouteFeatures=ranges[pass.id].features;pass.routeStationKeys=pass.overviewRouteStationKeys=new Set(ranges[pass.id].stationKeys);pass.routeOverridesOnly=Boolean(ranges[pass.id].partial);pass.routeFeatureKeys=new Set(pass.routeFeatures.map(f=>f.properties.operator+'|'+f.properties.name));}
  state.passes=catalog.passes;state.network=state.overviewNetwork=network;$('coverageNote').textContent=catalog.coverageNote;
  L.geoJSON(land,{pane:'railLand',interactive:false,style:{color:'#b9c9b5',weight:1,fillColor:'#f7f5e9',fillOpacity:1}}).addTo(map);
  for(const [value,item] of Object.entries(GRADES)){const option=document.createElement('option');option.value=value;option.textContent=item.label;$('railGrade').append(option);}
  const operators=[...new Set(network.features.filter(railColors.isRailway).map(f=>railColors.operatorOf(f.properties.operator)))].sort((a,b)=>a.localeCompare(b,'ja'));
  for(const [value,label] of [['jr','JR 六家公司'],['private','私铁 / 第三部门 / 公营（普通铁路）'],...Object.entries(JR_OPERATORS),...operators.filter(op=>!Object.hasOwn(JR_OPERATORS,op)).map(op=>[op,op])]){const option=document.createElement('option');option.value=value;option.textContent=label;$('railOperator').append(option);}
  $('catalogCount').textContent=`${state.passes.filter(p=>p.status==='current').length} 种现行`;
  $('dataDate').textContent=`范围核对 ${catalog.checked} · 票价日期见详情`;
  const regions=['全国','北海道','东北','关东','甲信越','东海','北陆','关西','中国','四国','九州'];
  for(const region of regions){const option=document.createElement('option');option.value=region;option.textContent=region;$('regionFilter').append(option);}
  renderList();
  const params=new URLSearchParams(location.search);
  if([...$('railGrade').options].some(x=>x.value===params.get('grade')))$('railGrade').value=params.get('grade');
  const operator=railColors.operatorOf(params.get('operator'));
  if([...$('railOperator').options].some(x=>x.value===operator))$('railOperator').value=operator;
  const id=params.get('pass')||(params.get('passes')||'').split(',')[0];
  if(state.passes.some(p=>p.id===id))showPass(id,false);else renderSelection();
  if(state.selected||$('railGrade').value||$('railOperator').value)fitDisplayed();
  updateDetailLevel();
  window.JPRail={state,map,camera,streets,windowFeature,coverageFeatures,gradeOf,railStyle,railColorInfo,railColors,matchesRailFilters};

 } catch(e) {$('passList').innerHTML='<p class="no-results">数据加载失败，请刷新页面或检查本地文件是否完整。</p>';$('resultCount').textContent='目录读取失败';$('mapState').textContent='铁路数据加载失败；在线设施图仍可浏览';console.error('JPRail data load:',e);}
 try{state.stations=await json('assets/data/jprail/stations.json');refreshStationPool();}catch{$('stationSearch').placeholder='车站数据暂不可用';}
 setupStationSearch();
}

start();
