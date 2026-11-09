// One requested step produces one zoom transition. Wheel tail events belong to
// the same gesture and must not enqueue additional zoom animations.
export function createCamera(map) {
 const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
 const actions=[];let animating=false,driving=false,frame=0,wheelTimer=0,lastWheel=-Infinity,wheelDelta=0,wheelUsed=false,wheelAnchor;
 const cancelWheel=()=>{clearTimeout(wheelTimer);wheelTimer=0;wheelDelta=0;wheelUsed=true;};
 const schedule=()=>{if(!frame)frame=requestAnimationFrame(pump);};
 const pump=()=>{
  frame=0;if(animating||!actions.length)return;
  const action=actions.shift();driving=true;
  if(action.view)action.view();
  else {
   const zoom=Math.max(map.getMinZoom(),Math.min(map.getMaxZoom(),map.getZoom()+action.delta));
   if(Math.abs(zoom-map.getZoom())>.001){
    // Leaflet starts an animated zoom on the next animation frame. Reserve it
    // now, otherwise another input can run before zoomstart and be lost.
    animating=true;
    map.setZoomAround(action.anchor||map.getSize().divideBy(2),zoom,{animate:!reduced});
   }
  }
  if(!animating){driving=false;schedule();}
 };
 map.on('zoomstart',()=>{animating=true;if(!driving){actions.length=0;cancelWheel();}});
 map.on('zoomend',()=>{animating=false;driving=false;schedule();});
 map.on('dragstart',()=>{actions.length=0;cancelWheel();});
 const zoomBy=(delta,anchor)=>{if(!delta)return;actions.push({delta,anchor});schedule();};
 const apply=view=>{actions.length=0;cancelWheel();if(animating){actions.push({view});}else{driving=true;view();if(!animating)driving=false;}};
 map.getContainer().addEventListener('wheel',event=>{
  event.preventDefault();event.stopPropagation();
  const pixels=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?map.getSize().y:1);if(!pixels)return;
  const now=performance.now();if(now-lastWheel>180){wheelUsed=false;wheelDelta=0;}lastWheel=now;
  if(wheelUsed)return;
  wheelDelta=Math.max(-120,Math.min(120,wheelDelta+pixels));wheelAnchor=map.mouseEventToContainerPoint(event);
  if(!wheelTimer)wheelTimer=setTimeout(()=>{
   wheelTimer=0;wheelUsed=true;
   const delta=Math.sign(-wheelDelta)*Math.max(.05,Math.round(Math.abs(wheelDelta)/600/.05)*.05);
   wheelDelta=0;zoomBy(delta,wheelAnchor);
  },55);
 },{passive:false});
 const Buttons=L.Control.extend({
  options:{position:'topleft'},
  onAdd(){
   const el=L.DomUtil.create('div','leaflet-bar jprail-zoom');
   for(const [label,delta,title] of [['+',.25,'放大'],['−',-.25,'缩小']]){
    const button=L.DomUtil.create('button','',el);button.type='button';button.textContent=label;button.title=title;button.setAttribute('aria-label',title);
    L.DomEvent.on(button,'click',event=>{L.DomEvent.stop(event);cancelWheel();zoomBy(delta);});
   }
   L.DomEvent.disableClickPropagation(el);L.DomEvent.disableScrollPropagation(el);return el;
  }
 });
 new Buttons().addTo(map);
 return {fitBounds:(bounds,options={})=>apply(()=>map.fitBounds(bounds,{...options,animate:false})),setView:(point,zoom,after)=>apply(()=>{map.setView(point,zoom,{animate:false});after?.();}),zoomBy,whenIdle:()=>!animating&&!actions.length&&!wheelTimer};
}
