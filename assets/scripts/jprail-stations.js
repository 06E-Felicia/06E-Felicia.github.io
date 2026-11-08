// City gateways and major interchanges, for overview labels (not a ridership ranking).
const HUBS=new Map('東京 大阪 札幌 博多 名古屋 仙台 広島 新潟 金沢 高松 鹿児島中央 函館 釧路 旭川 新青森 青森 盛岡 秋田 山形 福島 郡山 長野 高崎 大宮 宇都宮 水戸 上野 新宿 品川 横浜 小田原 静岡 浜松 豊橋 岐阜 富山 福井 米原 京都 新大阪 神戸 三ノ宮 姫路 岡山 倉敷 福山 新山口 鳥取 松江 松山 徳島 高知 小倉 長崎 佐世保 佐賀 熊本 大分 宮崎 那覇空港'.split(' ').map((name,rank)=>[name,rank]));
export function createStationLabels(map,getStations,onRender) {
 const Labels=L.Layer.extend({
  onAdd(m) {
   this.canvas=L.DomUtil.create('canvas','station-label-canvas',m.getPane('railStations'));
   this.canvas.setAttribute('aria-label','车站名称；放大地图显示更多车站');
   m.on('moveend zoomend resize',this.schedule,this);this.schedule();
  },
  onRemove(m) {m.off('moveend zoomend resize',this.schedule,this);cancelAnimationFrame(this.frame);this.canvas.remove();},
  schedule() {cancelAnimationFrame(this.frame);this.frame=requestAnimationFrame(()=>this.draw());},
  draw() {
   const size=map.getSize(),ratio=Math.min(devicePixelRatio||1,2),z=map.getZoom(),all=z>=16;
   const canvas=this.canvas;canvas.width=size.x*ratio;canvas.height=size.y*ratio;
   canvas.style.width=size.x+'px';canvas.style.height=size.y+'px';
   L.DomUtil.setPosition(canvas,map.containerPointToLayerPoint([0,0]));
   const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.textBaseline='middle';ctx.lineJoin='round';
   const occupied=new Map(),names=[],dots=new Set();
   const items=getStations().filter(s=>z>=7||HUBS.has(s[0])).map(s=>({s,hub:HUBS.has(s[0])})).sort((a,b)=>Number(b.hub)-Number(a.hub)||(HUBS.get(a.s[0])??999)-(HUBS.get(b.s[0])??999)||a.s[0].localeCompare(b.s[0],'ja'));
   for(const {s,hub} of items) {
    const p=map.latLngToContainerPoint([s[1],s[2]]);
    if(p.x<0||p.y<0||p.x>size.x||p.y>size.y)continue;
    const key=s[0]+'|'+Math.round(p.x/8)+'|'+Math.round(p.y/8);if(dots.has(key))continue;dots.add(key);
    const font=hub?12:11;ctx.font=`${hub?600:400} ${font}px -apple-system, "PingFang SC", sans-serif`;
    const w=ctx.measureText(s[0]).width,space=z<9?14:z<12?8:3;
    const box=[p.x+5-space,p.y-font/2-space,p.x+9+w+space,p.y+font/2+space];
    const cells=[];for(let x=Math.floor(box[0]/64);x<=Math.floor(box[2]/64);x++)for(let y=Math.floor(box[1]/64);y<=Math.floor(box[3]/64);y++)cells.push(x+','+y);
    if(!all&&cells.some(k=>(occupied.get(k)||[]).some(b=>box[0]<b[2]&&box[2]>b[0]&&box[1]<b[3]&&box[3]>b[1])))continue;
    for(const k of cells){if(!occupied.has(k))occupied.set(k,[]);occupied.get(k).push(box);}
    ctx.beginPath();ctx.arc(p.x,p.y,hub?2.6:1.8,0,Math.PI*2);ctx.fillStyle='#fffefa';ctx.fill();ctx.lineWidth=1;ctx.strokeStyle='#36585a';ctx.stroke();
    ctx.lineWidth=3.5;ctx.strokeStyle='#fffefa';ctx.strokeText(s[0],p.x+6,p.y);ctx.fillStyle=hub?'#143b40':'#405859';ctx.fillText(s[0],p.x+6,p.y);
    names.push(s[0]);
   }
   onRender({count:names.length,names,mode:all?'当前视野全部车站':z<7?'主要枢纽':'区域车站'});
  }
 });
 const layer=new Labels().addTo(map);return layer;
}
