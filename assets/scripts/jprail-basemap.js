// A real white street basemap. Its local style omits rail/transit symbols so
// pass filtering never leaves unrelated railway lines visible underneath.
export function createStreetMap(map,onStatus) {
 let layer,gl,timeout,generation=0,tiles=0,status='loading';
 const statusEl=document.getElementById('basemapStatus'),retry=document.getElementById('retryBasemap');
 const report=(next,message)=>{
  status=next;statusEl.textContent=message;retry.hidden=next==='ready'||next==='loading';
  if(layer)layer.getContainer().style.opacity=next==='ready'?'1':'0';
  onStatus({status:next,tiles,message});
 };
 const load=async()=>{
  const attempt=++generation;clearTimeout(timeout);if(layer){map.removeLayer(layer);layer=null;}gl=null;tiles=0;
  report('loading','白色街道底图载入中…');
  try {
   if(!window.maplibregl||!window.L.maplibreGL||(typeof maplibregl.supported==='function'&&!maplibregl.supported()))throw new Error('当前浏览器不支持街道底图所需的 WebGL');
   const response=await fetch('assets/data/jprail/streets-style.json',{cache:'no-cache'});if(!response.ok)throw new Error('底图样式读取失败');
   const style=await response.json();if(attempt!==generation)return;
   maplibregl.setWorkerCount(1);
   layer=L.maplibreGL({style,pane:'railBase',padding:.15,updateInterval:32,interactive:false,renderWorldCopies:false,fadeDuration:0,localIdeographFontFamily:'Hiragino Kaku Gothic ProN, PingFang SC, sans-serif',attributionControl:false}).addTo(map);
   layer.getContainer().style.opacity='0';gl=layer.getMaplibreMap();
   const ready=()=>{
    if(attempt!==generation||status==='ready')return;
    const rendered=gl.queryRenderedFeatures({layers:['water','landuse_residential','highway_minor','highway_major_inner']}).length;
    if(rendered>0){tiles=Math.max(tiles,1);clearTimeout(timeout);report('ready','白色街道底图 · 道路 / 街区 / 地名');}
   };
   gl.on('sourcedata',event=>{if(event.sourceId==='openmaptiles'&&event.sourceDataType==='content'&&(event.coord||event.tile)){tiles++;ready();}});
   gl.on('idle',ready);gl.on('render',ready);
   gl.on('error',event=>{console.warn('Street basemap:',event.error?.message||'source unavailable');if(attempt===generation&&tiles===0)report('error','街道底图连接失败，线路仍可浏览');});
   timeout=setTimeout(()=>{if(attempt===generation&&tiles===0)report('error','街道底图暂未响应，请重试');},12000);
  } catch(error){if(attempt===generation)report('error',error.message||'街道底图载入失败');}
 };
 retry.addEventListener('click',load);
 map.attributionControl.addAttribution('<a href="https://openfreemap.org/">OpenFreeMap</a> · <a href="https://openmaptiles.org/">OpenMapTiles</a> · © <a href="https://www.openstreetmap.org/copyright">OSM</a>');
 load();return {retry:load,getMap:()=>gl,getStatus:()=>({status,tiles})};
}
