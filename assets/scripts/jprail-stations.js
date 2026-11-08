// City gateways and major interchanges, for overview labels (not a ridership ranking).
const HUBS=new Map('東京 大阪 札幌 博多 名古屋 仙台 広島 新潟 金沢 高松 鹿児島中央 函館 釧路 旭川 新青森 青森 盛岡 秋田 山形 福島 郡山 長野 高崎 大宮 宇都宮 水戸 上野 新宿 品川 横浜 小田原 静岡 浜松 豊橋 岐阜 富山 福井 米原 京都 新大阪 神戸 三ノ宮 姫路 岡山 倉敷 福山 新山口 鳥取 松江 松山 徳島 高知 小倉 長崎 佐世保 佐賀 熊本 大分 宮崎 那覇空港'.split(' ').map((name,rank)=>[name,rank]));
export function createStationLabels(map,getStations,onRender,getPins=()=>[]) {
 const Labels=L.Layer.extend({
  onAdd(m) {
   this.canvas=L.DomUtil.create('canvas','station-label-canvas leaflet-zoom-animated',m.getPane('railStations'));
   this.canvas.setAttribute('aria-label','车站名称；界为官方范围关键站，限为重要限制站');
   this.widths=new Map();this.sortBuilds=0;
   m.on('moveend zoomend resize',this.schedule,this);m.on('zoomanim',this.animate,this);this.schedule();
  },
  onRemove(m) {m.off('moveend zoomend resize',this.schedule,this);m.off('zoomanim',this.animate,this);cancelAnimationFrame(this.frame);this.canvas.remove();},
  schedule() {cancelAnimationFrame(this.frame);this.frame=requestAnimationFrame(()=>this.draw());},
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
     .sort((a,b)=>Number(Boolean(b.pin))-Number(Boolean(a.pin))||Number(b.hub)-Number(a.hub)||(HUBS.get(a.s[0])??999)-(HUBS.get(b.s[0])??999)||a.s[0].localeCompare(b.s[0],'ja'));
   }
   const size=map.getSize(),ratio=Math.min(devicePixelRatio||1,2),z=map.getZoom(),all=z>=16,bounds=map.getBounds();
   const canvas=this.canvas;canvas.width=size.x*ratio;canvas.height=size.y*ratio;canvas.style.width=size.x+'px';canvas.style.height=size.y+'px';
   L.DomUtil.setPosition(canvas,map.containerPointToLayerPoint([0,0]));
   this.anchor=map.containerPointToLatLng([0,0]);this.drawZoom=z;
   const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.textBaseline='middle';ctx.lineJoin='round';
   const occupied=new Map(),names=[],pinnedNames=[],dots=new Set();
   const cells=box=>{const out=[];for(let x=Math.floor(box[0]/64);x<=Math.floor(box[2]/64);x++)for(let y=Math.floor(box[1]/64);y<=Math.floor(box[3]/64);y++)out.push(x+','+y);return out;};
   const overlap=box=>cells(box).some(k=>(occupied.get(k)||[]).some(b=>box[0]<b[2]&&box[2]>b[0]&&box[1]<b[3]&&box[3]>b[1]));
   for(const {s,hub,pin} of this.items) {
    if(!pin&&z<7&&!hub)continue;
    if(s[1]<bounds.getSouth()||s[1]>bounds.getNorth()||s[2]<bounds.getWest()||s[2]>bounds.getEast())continue;
    const point=map.latLngToContainerPoint([s[1],s[2]]),key=s[0]+'|'+Math.round(point.x/8)+'|'+Math.round(point.y/8);if(dots.has(key))continue;dots.add(key);
    const text=pin?s[0]+(pin.role==='restriction'?' 限':' 界'):s[0],font=hub?12:11;
    ctx.font=`${hub?600:400} ${font}px -apple-system, "PingFang SC", sans-serif`;
    const widthKey=font+'|'+text;if(!this.widths.has(widthKey))this.widths.set(widthKey,ctx.measureText(text).width);
    const w=this.widths.get(widthKey),space=pin?3:z<9?14:z<12?8:3;
    let x=point.x+6,y=point.y,box;
    const positions=pin?[0,-16,16,-32,32,-48,48,-64,64].flatMap(d=>[[6,d],[-w-8,d]]):[[6,0]];
    for(const [dx,dy] of positions) {
     x=Math.max(3,Math.min(size.x-w-3,point.x+dx));y=Math.max(font/2+4,Math.min(size.y-font/2-4,point.y+dy));
     box=[x-space,y-font/2-space,x+w+space,y+font/2+space];if(!overlap(box))break;
    }
    if(!pin&&!all&&overlap(box))continue;
    for(const k of cells(box)){if(!occupied.has(k))occupied.set(k,[]);occupied.get(k).push(box);}
    const color=pin?.role==='restriction'?'#986321':pin?'#126958':hub?'#143b40':'#405859';
    if(pin) {
     ctx.beginPath();ctx.moveTo(point.x,point.y);ctx.lineTo(Math.max(x,Math.min(x+w,point.x)),y);ctx.strokeStyle=color;ctx.lineWidth=.8;ctx.stroke();
     ctx.fillStyle='#fffefa';ctx.fillRect(x-2,y-font/2-3,w+4,font+6);ctx.strokeStyle=color;ctx.strokeRect(x-2,y-font/2-3,w+4,font+6);
    }
    ctx.beginPath();ctx.arc(point.x,point.y,pin?3.4:hub?2.6:1.8,0,Math.PI*2);ctx.fillStyle='#fffefa';ctx.fill();ctx.lineWidth=pin?1.5:1;ctx.strokeStyle=color;ctx.stroke();
    ctx.lineWidth=3.5;ctx.strokeStyle='#fffefa';ctx.strokeText(text,x,y);ctx.fillStyle=color;ctx.fillText(text,x,y);
    names.push(s[0]);if(pin)pinnedNames.push(s[0]);
   }
   onRender({count:names.length,names,pinnedNames,sortBuilds:this.sortBuilds,renderMs:performance.now()-started,mode:all?'当前视野全部车站':z<7?'主要枢纽':'区域车站'});
  }
 });
 return new Labels().addTo(map);
}
