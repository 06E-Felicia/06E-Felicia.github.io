/* Station-based game warnings, not an operational warning service. */
(function(root){
 'use strict';
 const STEP=600,DOWNGRADE_HOLD=3600;
 function stationCells(data,project,grid){
  const ids=new Set(),streets=new Set();
  return data.stations.map(s=>{
   if(ids.has(s.id)||streets.has(s.street)||!Number.isFinite(s.lon)||!Number.isFinite(s.lat))throw Error('代表站信息重复或坐标无效');
   ids.add(s.id);streets.add(s.street);
   const p=project.forward([s.lon,s.lat]),x=p[0]+grid.width/2,y=p[1]+grid.height/2;
   const index=grid.index(x,y);if(index<0)throw Error('代表站超出模拟范围：'+s.name);
   return {...s,index};
  });
 }
 // Relative-neighborhood graph of the approved representative points.
 // A spatial proxy, not administrative boundary topology; no links over 20 km.
 function streetNeighbors(stations){
  const n=stations.length,graph=stations.map(()=>[]),distance=(a,b)=>Math.hypot((a.lon-b.lon)*102700,(a.lat-b.lat)*111195);
  for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){
   const d=distance(stations[i],stations[j]);if(!Number.isFinite(d)||d<=0||d>20000)continue;
   if(stations.some((s,k)=>k!==i&&k!==j&&Math.max(distance(stations[i],s),distance(stations[j],s))<d-1e-6))continue;
   graph[i].push(j);graph[j].push(i);
  }return graph;
 }
 class Detector{
  constructor(stations,saved=null){
   if(!stations.length)throw Error('没有预警代表站');
   this.stations=stations;this.neighbors=streetNeighbors(stations);this.ids=stations.map(s=>s.id+':'+s.index).join(',');this.history=[];this.lastTime=-STEP;this.current=null;
   this.levels=stations.map(()=>0);this.belowSince=stations.map(()=>null);this.events=[];
   if(saved){
    if(saved.schema!==2||saved.ids!==this.ids)throw Error('预警代表站存档不匹配');
    if(!Array.isArray(saved.history)||!saved.history.length||saved.history.length>37||saved.lastTime!==saved.history.at(-1).t||saved.current?.t!==saved.lastTime||saved.history.some((h,i)=>h.t<0||h.t%STEP||h.values.length!==stations.length||h.values.some(v=>!Number.isFinite(v)||v<0)||(i&&h.t!==saved.history[i-1].t+STEP)))throw Error('预警雨量历史损坏');
    if(saved.levels?.length!==stations.length||saved.belowSince?.length!==stations.length||saved.levels.some(v=>![0,1,2,3].includes(v))||!Array.isArray(saved.events))throw Error('预警状态损坏');
    for(const k of ['history','lastTime','current','levels','belowSince','events'])this[k]=structuredClone(saved[k]);
   }
  }
  update(t,totals){
   if(t===this.lastTime)return this.current;
   if(t<0||t%STEP||t!==this.lastTime+STEP)throw Error('预警检测需要连续十分钟雨量');
   const values=this.stations.map(s=>totals[s.index]);if(values.some(v=>!Number.isFinite(v)||v<0))throw Error('代表站雨量无效');
   const previousValues=this.history.at(-1)?.values||values;
   if(values.some((v,i)=>v+1e-6<previousValues[i]))throw Error('累计雨量不能倒退');
   this.history.push({t,values});
   const previous=seconds=>this.history.find(h=>h.t===Math.max(0,t-seconds))?.values;
   const p1=previous(3600),p3=previous(10800),p6=previous(21600),p20=previous(1200);
   if(!p1||!p3||!p6||!p20)throw Error('预警滑动雨量历史不完整');
   const readings=this.stations.map((s,i)=>{
    const r1=Math.max(0,values[i]-p1[i]),r3=Math.max(0,values[i]-p3[i]),r6=Math.max(0,values[i]-p6[i]);
    // Any measurable continuing rain is sufficient for the observed branch.
    // No area vote and no 20 mm/h continuation gate that suppresses wet tails.
    const continuing=values[i]-p20[i]>=.1;
    const raw=continuing?((r3>=100||r1>=70)?3:(r3>=50||r1>=40)?2:(r1>=30||r6>=50)?1:0):0;
    return {r1,r3,r6,continuing,raw};
   });
   // Only measured threshold levels are seeds. Two hops for red (orange,
   // yellow), one for orange (yellow); linked or held levels never seed again.
   const linked=readings.map(r=>r.raw);
   for(let i=0;i<readings.length;i++)if(readings[i].raw>=2){
    for(const j of this.neighbors[i]){
     linked[j]=Math.max(linked[j],readings[i].raw-1);
     if(readings[i].raw===3)for(const k of this.neighbors[j])linked[k]=Math.max(linked[k],1);
    }
   }
   const stations=this.stations.map((s,i)=>{
    const {r1,r3,r6,continuing}=readings[i],raw=linked[i],old=this.levels[i];
    if(raw>=old){this.levels[i]=raw;this.belowSince[i]=null;}
    else{this.belowSince[i]??=t;if(t-this.belowSince[i]>=DOWNGRADE_HOLD){this.levels[i]=raw;this.belowSince[i]=null;}}
    if(this.levels[i]!==old)this.events.push({t,id:s.id,district:s.district,street:s.street,name:s.name,from:old,level:this.levels[i],r1,r3});
    return {...s,r1,r3,r6,total:values[i],level:this.levels[i],observedLevel:readings[i].raw,linkedLevel:raw,continuing};
   });
   this.lastTime=t;this.current={t,level:Math.max(...this.levels),stationCount:stations.length,stations,max1h:Math.max(...stations.map(s=>s.r1)),max3h:Math.max(...stations.map(s=>s.r3)),events:structuredClone(this.events)};
   while(this.history.length>37)this.history.shift();return this.current;
  }
  checkpoint(){return {schema:2,ids:this.ids,lastTime:this.lastTime,history:structuredClone(this.history),levels:[...this.levels],belowSince:[...this.belowSince],events:structuredClone(this.events),current:structuredClone(this.current)};}
 }
 const api={Detector,stationCells,streetNeighbors};root.VacationWarning=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
