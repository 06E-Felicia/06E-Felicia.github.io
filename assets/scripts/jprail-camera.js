// Serialize zoom animations so rapid input updates the destination instead of
// restarting jumps or losing a station-search/fit request mid-transition.
export function createCamera(map) {
 let target=map.getZoom(),anchor,queued=null,animating=false,driving=false,frame=0,lastWheel=0;
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const pump=()=>{
  frame=0;if(animating)return;
  if(queued){const fn=queued;queued=null;fn();target=map.getZoom();return;}
  const current=map.getZoom(),step=Math.round(Math.max(-.5,Math.min(.5,target-current))*10)/10;
  if(Math.abs(step)<.05)return;
  const point=anchor||map.getSize().divideBy(2);
  driving=true;map.setZoomAround(point,current+step,{animate:!reduced});
 };
 const schedule=()=>{if(!frame)frame=requestAnimationFrame(pump);};
 map.on('zoomstart',()=>{animating=true;});
 map.on('zoomend',()=>{animating=false;if(!driving)target=map.getZoom();driving=false;schedule();});
 map.on('dragstart',()=>{target=map.getZoom();queued=null;});
 const apply=fn=>{target=map.getZoom();if(animating)queued=fn;else{fn();target=map.getZoom();}};
 const zoomBy=(delta,point)=>{const wanted=target+delta;target=Math.max(map.getMinZoom(),Math.min(map.getMaxZoom(),point?Math.max(map.getZoom()-1,Math.min(map.getZoom()+1,wanted)):wanted));anchor=point;schedule();};
 map.getContainer().addEventListener('wheel',event=>{
  event.preventDefault();const now=performance.now();if(now-lastWheel>300&&!animating)target=map.getZoom();lastWheel=now;
  const pixels=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?map.getSize().y:1);
  zoomBy(-Math.max(-120,Math.min(120,pixels))/240,map.mouseEventToContainerPoint(event));
 },{passive:false});
 const Buttons=L.Control.extend({
  options:{position:'topleft'},
  onAdd(){
   const el=L.DomUtil.create('div','leaflet-bar jprail-zoom');
   for(const [label,delta,title] of [['+',.5,'放大'],['−',-.5,'缩小']]){
    const button=L.DomUtil.create('button','',el);button.type='button';button.textContent=label;button.title=title;button.setAttribute('aria-label',title);
    L.DomEvent.on(button,'click',event=>{L.DomEvent.stop(event);zoomBy(delta);});
   }
   L.DomEvent.disableClickPropagation(el);L.DomEvent.disableScrollPropagation(el);return el;
  }
 });
 new Buttons().addTo(map);
 return {fitBounds:(bounds,options={})=>apply(()=>map.fitBounds(bounds,{...options,animate:false})),setView:(point,zoom,after)=>apply(()=>{map.setView(point,zoom,{animate:false});after?.();}),zoomBy,whenIdle:()=>!animating&&!queued&&Math.abs(target-map.getZoom())<.06};
}
