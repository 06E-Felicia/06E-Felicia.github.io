// City gateways and major interchanges, for overview labels (not a ridership ranking).
const HUBS=new Map('東京 大阪 札幌 博多 名古屋 仙台 広島 新潟 金沢 高松 鹿児島中央 函館 釧路 旭川 新青森 青森 盛岡 秋田 山形 福島 郡山 長野 高崎 大宮 宇都宮 水戸 上野 新宿 品川 横浜 小田原 静岡 浜松 豊橋 岐阜 富山 福井 米原 京都 新大阪 神戸 三ノ宮 姫路 岡山 倉敷 福山 新山口 鳥取 松江 松山 徳島 高知 小倉 長崎 佐世保 佐賀 熊本 大分 宮崎 那覇空港'.split(' ').map((name,rank)=>[name,rank]));
const lineBounds=new WeakMap();
const cells=box=>{const out=[];for(let x=Math.floor(box[0]/64);x<=Math.floor(box[2]/64);x++)for(let y=Math.floor(box[1]/64);y<=Math.floor(box[3]/64);y++)out.push(x+','+y);return out;};
function crossesBox([ax,ay,bx,by],box) {
 let start=0,end=1;
 for(const [p,q] of [[ax-bx,ax-box[0]],[bx-ax,box[2]-ax],[ay-by,ay-box[1]],[by-ay,box[3]-ay]]) {
  if(!p){if(q<0)return false;continue;}
  const t=q/p;if(p<0)start=Math.max(start,t);else end=Math.min(end,t);if(start>end)return false;
 }
 return true;
}
// Keep label halos and framed key-station names off railway strokes. Testing
// actual segments also avoids treating a large line bounding box as occupied.
function railCollisionIndex(map,features) {
 const grid=new Map(),bounds=map.getBounds().pad(.05),view=[bounds.getWest(),bounds.getSouth(),bounds.getEast(),bounds.getNorth()],size=map.getSize();
 for(const f of features) {
  const lines=f.geometry.type==='LineString'?[f.geometry.coordinates]:f.geometry.coordinates;
  for(const line of lines) {
   if(!lineBounds.has(line))lineBounds.set(line,line.reduce((b,p)=>[Math.min(b[0],p[0]),Math.min(b[1],p[1]),Math.max(b[2],p[0]),Math.max(b[3],p[1])],[Infinity,Infinity,-Infinity,-Infinity]));
   const b=lineBounds.get(line);if(b[2]<view[0]||b[0]>view[2]||b[3]<view[1]||b[1]>view[3])continue;
   // Collision detection needs pixel precision, not thousands of coincident
   // survey vertices. The two-pixel guard below covers this .5px tolerance;
   // the actual painted railway always keeps every detailed source vertex.
   const points=L.LineUtil.simplify(line.map(p=>map.latLngToContainerPoint([p[1],p[0]])),.5);
   for(let i=1;i<points.length;i++) {
    const p=points[i-1],q=points[i];if(Math.max(p.x,q.x)<-8||Math.min(p.x,q.x)>size.x+8||Math.max(p.y,q.y)<-8||Math.min(p.y,q.y)>size.y+8)continue;
    const segment=[p.x,p.y,q.x,q.y],box=[Math.max(-8,Math.min(p.x,q.x)),Math.max(-8,Math.min(p.y,q.y)),Math.min(size.x+8,Math.max(p.x,q.x)),Math.min(size.y+8,Math.max(p.y,q.y))];
    for(const key of cells(box)){if(!grid.has(key))grid.set(key,[]);grid.get(key).push(segment);}
   }
  }
 }
 return box=>{const padded=[box[0]-2,box[1]-2,box[2]+2,box[3]+2];return cells(padded).some(key=>(grid.get(key)||[]).some(segment=>crossesBox(segment,padded)));};
}
export function createStationLabels(map,getStations,onRender,getPins=()=>[],getRails=()=>[]) {
 const Labels=L.Layer.extend({
  onAdd(m) {
   this.canvas=L.DomUtil.create('canvas','station-label-canvas leaflet-zoom-animated',m.getPane('railStations'));
   this.canvas.setAttribute('aria-label','车站名称；视野内适用边界与重要限制站名始终显示');
   this.widths=new Map();this.sortBuilds=0;
   m.on('moveend zoomend resize',this.schedule,this);m.on('zoomanim',this.animate,this);m.on('zoom',this.followZoom,this);this.schedule();
  },
  onRemove(m) {m.off('moveend zoomend resize',this.schedule,this);m.off('zoomanim',this.animate,this);m.off('zoom',this.followZoom,this);cancelAnimationFrame(this.frame);this.canvas.remove();},
  schedule() {cancelAnimationFrame(this.frame);this.frame=requestAnimationFrame(()=>this.draw());},
  followZoom() {this.animate({center:map.getCenter(),zoom:map.getZoom()});},
  animate(event) {
   if(!this.anchor)return;
   const offset=map.project(this.anchor,event.zoom).subtract(map.project(event.center,event.zoom)).add(map.getSize().divideBy(2)).add(map.containerPointToLayerPoint([0,0]));
   L.DomUtil.setTransform(this.canvas,offset,map.getZoomScale(event.zoom,this.drawZoom));
  },
  draw() {
   const started=performance.now(),pool=getStations(),pins=getPins();
   if(pool!==this.pool||pins!==this.pins) {
    this.pool=pool;this.pins=pins;this.sortBuilds++;
    const pinNames=new Set(pins.map(p=>p.station[0]));
    this.items=[...pins.map(pin=>({s:pin.station,pin,hub:true})),...pool.filter(s=>!pinNames.has(s[0])).map(s=>({s,hub:HUBS.has(s[0]),pin:null}))]
     .sort((a,b)=>({boundary:3,restriction:2,terminus:1}[b.pin?.role]||0)-({boundary:3,restriction:2,terminus:1}[a.pin?.role]||0)||Number(Boolean(b.pin))-Number(Boolean(a.pin))||Number(b.hub)-Number(a.hub)||(HUBS.get(a.s[0])??999)-(HUBS.get(b.s[0])??999)||a.s[0].localeCompare(b.s[0],'ja'));
   }
   const size=map.getSize(),ratio=Math.min(devicePixelRatio||1,2),z=map.getZoom(),all=z>=16,bounds=map.getBounds();
   const canvas=this.canvas;canvas.width=size.x*ratio;canvas.height=size.y*ratio;canvas.style.width=size.x+'px';canvas.style.height=size.y+'px';
   L.DomUtil.setPosition(canvas,map.containerPointToLayerPoint([0,0]));
   this.anchor=map.containerPointToLatLng([0,0]);this.drawZoom=z;
   const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.textBaseline='middle';ctx.lineJoin='round';
   const anchors=new Map(),anchorGap=z<9?28:z<12?22:12;
   const nearAnchor=p=>{const x=Math.floor(p.x/anchorGap),y=Math.floor(p.y/anchorGap);for(let i=x-1;i<=x+1;i++)for(let j=y-1;j<=y+1;j++)if((anchors.get(i+','+j)||[]).some(q=>Math.hypot(p.x-q.x,p.y-q.y)<anchorGap))return true;return false;};
   const occupied=new Map(),names=[],texts=[],pinnedNames=[],boundaryNames=[],companyNames=[],pinnedBoxes=[],dots=new Set(),crossesRail=railCollisionIndex(map,getRails());
   const mapRect=map.getContainer().getBoundingClientRect();
   const uiBoxes=[...map.getContainer().closest('.map-frame').querySelectorAll('.leaflet-control,.map-layer-controls,.map-state,.basemap-status,.rail-legend')]
    .filter(el=>el.getClientRects().length).map(el=>{const b=el.getBoundingClientRect();return [b.left-mapRect.left-4,b.top-mapRect.top-4,b.right-mapRect.left+4,b.bottom-mapRect.top+4];});
   const intersects=(a,b)=>a[0]<b[2]&&a[2]>b[0]&&a[1]<b[3]&&a[3]>b[1];
   const protectedOverlap=box=>uiBoxes.some(b=>intersects(box,b))||pinnedBoxes.some(p=>intersects(box,p.box));
   for(const box of uiBoxes)for(const key of cells(box)){if(!occupied.has(key))occupied.set(key,[]);occupied.get(key).push(box);}
   const overlap=box=>cells(box).some(k=>(occupied.get(k)||[]).some(b=>box[0]<b[2]&&box[2]>b[0]&&box[1]<b[3]&&box[3]>b[1]));
   for(const {s,hub,pin} of this.items) {
    if(!pin&&z<7&&!hub)continue;
    if(s[1]<bounds.getSouth()||s[1]>bounds.getNorth()||s[2]<bounds.getWest()||s[2]>bounds.getEast())continue;
    const point=map.latLngToContainerPoint([s[1],s[2]]),key=s[0]+'|'+Math.round(point.x/8)+'|'+Math.round(point.y/8);if(dots.has(key))continue;dots.add(key);
    if(!pin&&!hub&&!all&&nearAnchor(point))continue;
    const text=s[0],font=pin?.role==='boundary'?13:hub?12:11,weight=pin?.role==='boundary'?750:pin?.role==='terminus'?650:hub?600:400;
    ctx.font=`${weight} ${font}px -apple-system, "PingFang SC", sans-serif`;
    const widthKey=weight+'|'+font+'|'+text;if(!this.widths.has(widthKey))this.widths.set(widthKey,ctx.measureText(text).width);
    const w=this.widths.get(widthKey),space=pin?3:z<9?14:z<12?8:3;
    let x=point.x+6,y=point.y,box,best,score=Infinity;
    const positions=[0,-16,16,-28,28,-44,44,...(pin?[-60,60,-84,84,-110,110]:[])].flatMap(d=>[[6,d],[-w-8,d],[-w/2,d||-16]]);
    const consider=(dx,dy)=>{
     const px=Math.max(3,Math.min(size.x-w-3,point.x+dx)),py=Math.max(font/2+4,Math.min(size.y-font/2-4,point.y+dy));
     const candidate=[px-space,py-font/2-space,px+w+space,py+font/2+space];
     const penalty=Number(overlap(candidate))*100+Number(crossesRail([px-3,py-font/2-3,px+w+3,py+font/2+3]))*1000+Number(protectedOverlap(candidate))*10000;
     if(penalty<score){score=penalty;best=[px,py,candidate];}return !penalty;
    };
    for(const [dx,dy] of positions)if(consider(dx,dy))break;
    // At national zoom many endpoints can occupy one small city. Search the
    // remaining viewport instead of hiding names under controls or each other.
    if(pin&&score>0){
     const grid=[];
     for(let py=font/2+7;py<size.y-font/2-7;py+=font+9)for(let px=7;px<size.x-w-7;px+=Math.max(32,w/2+8))grid.push([px-point.x,py-point.y]);
     grid.sort((a,b)=>a[0]*a[0]+a[1]*a[1]-b[0]*b[0]-b[1]*b[1]);
     for(const [dx,dy] of grid)if(consider(dx,dy))break;
    }
    [x,y,box]=best;
    if(!pin&&((!all&&overlap(box))||protectedOverlap(box)))continue;
    if(pin)pinnedBoxes.push({name:s[0],role:pin.role,box});
    for(const k of cells(box)){if(!occupied.has(k))occupied.set(k,[]);occupied.get(k).push(box);}
    const color=pin?.boundaryKind==='company'?'#116979':pin?.role==='restriction'?'#986321':pin?.role==='terminus'?'#405859':pin?'#126958':hub?'#143b40':'#405859';
    if(pin) {
     ctx.beginPath();ctx.moveTo(point.x,point.y);ctx.lineTo(Math.max(x,Math.min(x+w,point.x)),y);ctx.strokeStyle=color;ctx.lineWidth=.8;ctx.stroke();
    }
    if(pin&&score<1000) {
     ctx.fillStyle='#fffefa';ctx.fillRect(x-2,y-font/2-3,w+4,font+6);ctx.strokeStyle=color;ctx.strokeRect(x-2,y-font/2-3,w+4,font+6);
    }
    ctx.beginPath();ctx.arc(point.x,point.y,pin?3.4:hub?2.6:1.8,0,Math.PI*2);ctx.fillStyle='#fffefa';ctx.fill();ctx.lineWidth=pin?1.5:1;ctx.strokeStyle=color;ctx.stroke();
    if(score<1000){ctx.lineWidth=3.5;ctx.strokeStyle='#fffefa';ctx.strokeText(text,x,y);}ctx.fillStyle=color;ctx.fillText(text,x,y);
    const anchorKey=Math.floor(point.x/anchorGap)+','+Math.floor(point.y/anchorGap);if(!anchors.has(anchorKey))anchors.set(anchorKey,[]);anchors.get(anchorKey).push(point);
    names.push(s[0]);texts.push(text);if(pin)pinnedNames.push(s[0]);if(pin?.role==='boundary')boundaryNames.push(s[0]);if(pin?.boundaryKind==='company')companyNames.push(s[0]);
   }
   onRender({count:names.length,names,texts,pinnedNames,boundaryNames,companyNames,pinnedBoxes,uiBoxes,sortBuilds:this.sortBuilds,renderMs:performance.now()-started,mode:all?'当前视野全部车站':z<7?'主要枢纽':'区域车站'});
  }
 });
 return new Labels().addTo(map);
}
