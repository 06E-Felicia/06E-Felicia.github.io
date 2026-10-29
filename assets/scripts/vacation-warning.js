/* Synthetic Shenzhen rain warnings; no connection to real warning publication. */
(function(root){
 'use strict';
 const STEP=600,START=20*3600,DEADLINES=[41400,127800,214200];
 function inRing(x,y,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>y)!==(b[1]>y)&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])inside=!inside;}return inside;}
 function inPolygon(x,y,rings){return inRing(x,y,rings[0])&&!rings.slice(1).some(r=>inRing(x,y,r));}
 function mask(geo,project,grid){
  const cells=[],districts=geo.features.map(f=>({id:String(f.properties.adcode),name:f.properties.name}));
  geo.features.forEach((f,district)=>{
   const source=f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates;
   const polys=source.map(rings=>rings.map(r=>r.map(p=>{const q=project.forward(p);return [q[0]+grid.width/2,q[1]+grid.height/2];})));
   const points=polys.flat(2),xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
   const x0=Math.max(0,Math.floor(Math.min(...xs)/grid.dx)),x1=Math.min(grid.nx-1,Math.floor(Math.max(...xs)/grid.dx)),y0=Math.max(0,Math.floor(Math.min(...ys)/grid.dx)),y1=Math.min(grid.ny-1,Math.floor(Math.max(...ys)/grid.dx));
   for(let j=y0;j<=y1;j++)for(let i=x0;i<=x1;i++){
    let hits=0;for(const ox of [.125,.375,.625,.875])for(const oy of [.125,.375,.625,.875])if(polys.some(p=>inPolygon((i+ox)*grid.dx,(j+oy)*grid.dx,p)))hits++;
    if(hits)cells.push({index:j*grid.nx+i,district,weight:hits/16*grid.dx**2/1e6});
   }
  });return {cells,districts};
 }
 class Detector{
  constructor(cells,districts,saved=null){
   if(!cells.length)throw Error('深圳检测范围没有有效格点');this.cells=cells;this.districts=districts;this.history=[];this.results=[null,null,null];this.lastTime=-STEP;this.current=null;
   if(saved){
    if(saved.schema!==1||saved.ids!==cells.map(c=>c.index+':'+c.district+':'+c.weight).join(','))throw Error('预警检测存档的地理范围不匹配');
    if(!Array.isArray(saved.history)||saved.history.length>37||!Array.isArray(saved.results)||saved.results.length!==3)throw Error('预警检测存档损坏');
    for(const h of saved.history)if(!Number.isSafeInteger(h.t)||h.t<0||h.t%STEP||!Array.isArray(h.values)||h.values.length!==cells.length||h.values.some(v=>!Number.isFinite(v)||v<0))throw Error('预警雨量历史损坏');
    if(!saved.history.length||saved.lastTime!==saved.history.at(-1).t||saved.current?.t!==saved.lastTime||saved.history.some((h,i)=>i>0&&h.t!==saved.history[i-1].t+STEP)||saved.results.some((r,i)=>r&&(r.day!==i+1||!['complete','failed'].includes(r.outcome)||!Number.isFinite(r.at))))throw Error('预警检测存档时间或任务结果损坏');
    this.history=structuredClone(saved.history);this.results=structuredClone(saved.results);this.lastTime=saved.lastTime;this.current=structuredClone(saved.current);
   }
  }
  update(t,totals){
   if(t===this.lastTime)return this.current;
   if(t%STEP||t<0||(this.lastTime>=0&&t!==this.lastTime+STEP))throw Error('预警检测需要连续十分钟雨量');
   const values=this.cells.map(c=>totals[c.index]);if(values.some(v=>!Number.isFinite(v)||v<0))throw Error('深圳格点雨量无效');
   this.history.push({t,values});
   const previous=seconds=>{const target=Math.max(0,t-seconds);return this.history.find(h=>h.t===target)?.values;};
   const p1=previous(3600),p3=previous(10800),p6=previous(21600),p20=previous(1200);
   if(!p1||!p3||!p6||!p20)throw Error('预警滑动雨量历史不完整');
   const areas=this.districts.map(d=>({...d,area:0,levels:[0,0,0,0],max1h:0,max3h:0,max6h:0}));
   for(let i=0;i<values.length;i++){
    const c=this.cells[i],a=areas[c.district],r1=Math.max(0,values[i]-p1[i]),r3=Math.max(0,values[i]-p3[i]),r6=Math.max(0,values[i]-p6[i]),continuation=(values[i]-p20[i])*3600/Math.max(STEP,Math.min(1200,t));
    // Observed-threshold branch only. Recent 20-minute persistence approximates
    // continued rainfall; it is not an operational forecast or indicator station.
    const level=(r3>=100||r1>=70)&&continuation>=20?3:(r3>=50||r1>=40)&&continuation>=20?2:(r1>=30||r6>=50)&&continuation>=5?1:0;
    a.area+=c.weight;for(let l=1;l<=level;l++)a.levels[l]+=c.weight;
    a.max1h=Math.max(a.max1h,r1);a.max3h=Math.max(a.max3h,r3);a.max6h=Math.max(a.max6h,r6);
   }
   for(const a of areas){a.level=0;for(let l=1;l<=3;l++)if(a.area>0&&a.levels[l]/a.area>=.25)a.level=l;a.coverage=a.area?a.levels[a.level]/a.area:0;}
   const level=Math.max(0,...areas.map(a=>a.level)),day=Math.max(1,Math.floor((START+t)/86400));
   for(let i=0;i<3;i++){
    if(this.results[i])continue;const start=i===0?0:(i+1)*86400-START;
    if(t>=start&&t<=DEADLINES[i]&&level===3)this.results[i]={day:i+1,outcome:'complete',at:t};
    else if(t>=DEADLINES[i])this.results[i]={day:i+1,outcome:'failed',at:DEADLINES[i]};
   }
   this.lastTime=t;this.current={t,day,level,areas,max1h:Math.max(...areas.map(a=>a.max1h)),max3h:Math.max(...areas.map(a=>a.max3h)),areaKm2:areas.reduce((s,a)=>s+a.area,0),gridCount:new Set(this.cells.map(c=>c.index)).size,results:structuredClone(this.results)};
   while(this.history.length>37)this.history.shift();return this.current;
  }
  checkpoint(){return {schema:1,ids:this.cells.map(c=>c.index+':'+c.district+':'+c.weight).join(','),lastTime:this.lastTime,history:structuredClone(this.history),results:structuredClone(this.results),current:structuredClone(this.current)};}
 }
 const api={Detector,mask,DEADLINES};root.VacationWarning=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
