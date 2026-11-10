// Leaflet 1.9.4's continuous movement API is also used by its touch-zoom
// handler. Keep one target and one RAF, rather than queuing CSS zooms or
// treating a whole trackpad gesture as one mouse-wheel notch.
export function createCamera(map) {
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 let frame=0,moving=false,target=map.getZoom(),anchor,anchorLatLng,lastFrame=0,lastInput=0,refreshZoom=map.getZoom(),ownMove=false;
 const clamp=z=>Math.max(map.getMinZoom(),Math.min(map.getMaxZoom(),z));
 function finish() {
  cancelAnimationFrame(frame);frame=0;
  if(moving){moving=false;ownMove=true;map._moveEnd(true);ownMove=false;}
  target=map.getZoom();
 }
 function tick(now) {
  frame=0;
  const dt=Math.min(40,now-lastFrame||16);lastFrame=now;
  const difference=target-map.getZoom();
  const zoom=Math.abs(difference)<.0005||reduced.matches?target:map.getZoom()+difference*(1-Math.exp(-dt/35));
  if(Math.abs(zoom-map.getZoom())>1e-8){
   // Anchor the actual geographical point, including after a direction change.
   const center=map.unproject(map.project(anchorLatLng,zoom).subtract(anchor.subtract(map.getSize().divideBy(2))),zoom);
   ownMove=true;map._move(map._limitCenter(center,zoom,map.options.maxBounds),zoom,{continuousWheel:true});ownMove=false;
   // Redraw the clipped vector viewport during long gestures, without
   // snapping the zoom or starting a second transition.
   if(Math.abs(zoom-refreshZoom)>.35){refreshZoom=zoom;map.fire('camerarefresh');}
  }
  if(Math.abs(target-map.getZoom())>1e-8||now-lastInput<90)frame=requestAnimationFrame(tick);
  else finish();
 }
 function zoomBy(delta,point=map.getSize().divideBy(2)) {
  if(!Number.isFinite(delta)||!delta)return;
  const next=clamp((moving?target:map.getZoom())+delta);
  if(!moving&&Math.abs(next-map.getZoom())<1e-8)return;
  // Changing the pointer position reanchors at the currently visible view.
  anchor=point;anchorLatLng=map.containerPointToLatLng(point);target=next;lastInput=performance.now();
  if(!moving){map._stop();moving=true;lastFrame=0;refreshZoom=map.getZoom();ownMove=true;map._moveStart(true,false);ownMove=false;}
  if(!frame)frame=requestAnimationFrame(tick);
 }
 const el=map.getContainer();
 // Desktop Safari exposes native scale events; Chromium encodes a trackpad
 // pinch as ctrl+wheel. Select one path so a pinch cannot be applied twice.
 const nativePinch='ongesturestart' in window&&navigator.maxTouchPoints===0&&matchMedia('(pointer:fine)').matches;
 let gestureScale=null;
 const blocked=event=>event.target.closest('.leaflet-control, .leaflet-popup');
 const pointFor=event=>Number.isFinite(event.clientX)&&Number.isFinite(event.clientY)?map.mouseEventToContainerPoint(event):map.getSize().divideBy(2);
 function wheel(event) {
  if(blocked(event))return;
  event.preventDefault();event.stopPropagation();
  if(nativePinch&&event.ctrlKey)return;
  const unit=event.deltaMode===1?16:event.deltaMode===2?map.getSize().y:1;
  // A pinch gets eight times the wheel gain. Ordinary scrolling retains its
  // small step, with no minimum delta, release snap or delayed replay.
  const pixels=Math.max(-160,Math.min(160,event.deltaY*unit));
  zoomBy(-pixels/(event.ctrlKey?100:800),pointFor(event));
 }
 el.addEventListener('wheel',wheel,{passive:false});
 function gestureStart(event) {
  if(!nativePinch||blocked(event))return;
  event.preventDefault();event.stopPropagation();gestureScale=1;
 }
 function gestureChange(event) {
  if(gestureScale===null||!Number.isFinite(event.scale)||event.scale<=0)return;
  event.preventDefault();event.stopPropagation();
  zoomBy(Math.log2(event.scale/gestureScale),pointFor(event));gestureScale=event.scale;
 }
 function gestureEnd(event) {
  if(gestureScale===null)return;
  event.preventDefault();event.stopPropagation();gestureScale=null;
 }
 if(nativePinch){
  el.addEventListener('gesturestart',gestureStart,{passive:false});
  el.addEventListener('gesturechange',gestureChange,{passive:false});
  el.addEventListener('gestureend',gestureEnd,{passive:false});
 }
 function key(event) {
  if(event.altKey||event.ctrlKey||event.metaKey||/^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(event.target.tagName))return;
  const delta=['+','=','Add'].includes(event.key)?.25:['-','_','Subtract'].includes(event.key)?-.25:0;
  if(delta){event.preventDefault();event.stopImmediatePropagation();zoomBy(delta);}
 }
 el.addEventListener('keydown',key,true);
 const dblclick=event=>{zoomBy(event.originalEvent.shiftKey?-.25:.25,map.mouseEventToContainerPoint(event.originalEvent));};
 map.doubleClickZoom.disable();map.on('dblclick',dblclick);
 // A drag, pinch or programmatic view change takes ownership immediately.
 const external=()=>{if(!ownMove)finish();};
 map.on('dragstart zoomstart',external);
 const Buttons=L.Control.extend({
  options:{position:'topleft'},
  onAdd(){
   const control=L.DomUtil.create('div','leaflet-bar jprail-zoom');
   for(const [label,delta,title] of [['+',.25,'放大'],['−',-.25,'缩小']]){
    const button=L.DomUtil.create('button','',control);button.type='button';button.textContent=label;button.title=title;button.setAttribute('aria-label',title);
    L.DomEvent.on(button,'click',event=>{L.DomEvent.stop(event);zoomBy(delta);});
   }
   L.DomEvent.disableClickPropagation(control);L.DomEvent.disableScrollPropagation(control);return control;
  }
 });
 const buttons=new Buttons().addTo(map);
 map.once('unload',()=>{finish();el.removeEventListener('wheel',wheel);el.removeEventListener('gesturestart',gestureStart);el.removeEventListener('gesturechange',gestureChange);el.removeEventListener('gestureend',gestureEnd);el.removeEventListener('keydown',key,true);map.off('dblclick',dblclick);map.off('dragstart zoomstart',external);buttons.remove();});
 const apply=view=>{finish();view();target=map.getZoom();};
 return {fitBounds:(bounds,options={})=>apply(()=>map.fitBounds(bounds,{...options,animate:false})),setView:(point,zoom,after)=>apply(()=>{map.setView(point,zoom,{animate:false});after?.();}),zoomBy,whenIdle:()=>!moving&&!frame};
}
