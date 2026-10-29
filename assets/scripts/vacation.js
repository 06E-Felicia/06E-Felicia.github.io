(function(){
  'use strict';
  const $=id=>document.getElementById(id),SCHEMA=1,V=VacationVersion;
  const testRun=new URLSearchParams(location.search).get('test');
  const STORAGE_NAME=testRun?.startsWith('acceptance')?'vacation-simulator-'+testRun:'vacation-simulator';
  let REGION=null;
  const LAYERS={rain24:{name:'24 小时滑动降水',labels:['0','10','25','50','100','250','500 mm']},radar:{name:'雷达回波',labels:['5','15','25','35','45','55','65 dBZ']},monsoon:{name:'西南季风',labels:['0','5','10','15','20','25','30 m/s']},cold:{name:'冷池温差与相对外流',labels:['0','0.5','1','1.5','2','2.5 K']},terrain:{name:'迎风坡有效抬升',labels:['0','100','200','300','400','500','600 m']},trigger:{name:'环境起生条件',labels:['0','20','40','60','80','100 %']}};
  const radarPalette=[[40,77,160],[39,175,223],[48,186,110],[231,220,67],[243,120,41],[206,49,85],[211,149,238]];
  const windPalette=[[34,53,91],[52,106,160],[66,174,168],[157,204,123],[240,185,92],[223,100,100]];
  const coldPalette=[[220,243,249],[126,206,227],[56,151,211],[58,90,188],[92,51,145]],coldCache=new WeakMap();
  const coldColor=value=>interpolate(coldPalette,value/2.5),triggerCache=new WeakMap(),liftPalette=[[230,235,201],[173,199,134],[245,191,91],[222,111,44],[175,48,56]];
  const liftColor=(value,max=600)=>interpolate(liftPalette,value/max);
  function interpolate(palette,f){const x=Math.max(0,Math.min(1,f))*(palette.length-1),i=Math.min(palette.length-2,Math.floor(x)),a=x-i;return palette[i].map((v,k)=>Math.round(v+(palette[i+1][k]-v)*a));}
  const radarColor=value=>interpolate(radarPalette,(value-5)/60),windColor=value=>interpolate(windPalette,value/30);
  let meta=null,projection=null,coastlines=[],views=[],syncing=false,picking=false;
  const rain24Cache=new WeakMap(),rain24Pending=new WeakMap(),rainBreaks=[0,10,25,50,100,250,500],rainPalette=[[232,245,250],[126,211,186],[60,173,111],[239,211,80],[240,132,50],[197,57,99],[127,62,162]];
  const rain24Color=value=>{let i=0;while(i<rainBreaks.length-2&&value>rainBreaks[i+1])i++;return interpolate(rainPalette,(i+Math.min(1,(value-rainBreaks[i])/(rainBreaks[i+1]-rainBreaks[i])))/(rainBreaks.length-1));};
  const choices=['radar','monsoon'],windCache=new WeakMap();
  const majorCities={'59287':'广州','59493':'深圳','59488':'珠海','59316':'汕头','59288':'佛山','59082':'韶关','59658':'湛江','59659':'茂名','59278':'肇庆','59298':'惠州','59117':'梅州','59501':'汕尾','59293':'河源','59663':'阳江','59280':'清远','59289':'东莞','59485':'中山','59312':'潮州','59315':'揭阳','59471':'云浮','59476':'江门','59431':'南宁','59046':'柳州','57957':'桂林','59265':'梧州','59644':'北海','59635':'防城港','59632':'钦州','59211':'百色','59065':'贺州','59023':'河池','59242':'来宾'};
  const radarColors=Array.from({length:255},(_,i)=>radarColor(i*.5-10)),windColors=Array.from({length:301},(_,i)=>windColor(i/10));
  let worker=null,runId=null,store=null,frame=null,latest=null,config=null,state='idle',isPaused=false,replaying=false,replayPlaying=false,paintTask=null;
  let displayTime=0,latestTime=0,coreTime=0,command=0,seqCount=0,lastTick=performance.now(),lastProgress=0,lastPaint=0;
  let renderMs=0,cacheWriteMs=0;
  let confirmedCoreTime=0,lastRequestedControl=null,lastReceivedControl=null,lastAppliedControl=null,actualCoreState='idle';
  let liveStats={},runLog=[],pending=new Map(),lastError=null,restorable=null,restorableHistory=null,initialized,startWall=0,firstFrameMs=null;
  let point={id:'59493',name:'深圳',lon:114.06,lat:22.55},stations=[point];
  function clock(t){return V.simulationTime(t,config||{startHour:20,calendarOrigin:'previous_day'}).clock;}
  function day(t){return V.simulationTime(t,config||{startHour:20,calendarOrigin:'previous_day'}).day;}
  function setStatus(text){$('status').textContent=text;}
  function post(type,payload={},transfer=[]){worker?.postMessage({type,runId,schemaVersion:SCHEMA,...payload},transfer);}
  function sendCommand(type,payload={}){const id=++command;pending.set(id,performance.now());runLog.push({type,commandId:id,requestedAtCore:coreTime,requestedAtPage:performance.now(),...payload});if(type==='PAUSE'||type==='RESUME')lastRequestedControl={commandId:id,type};post(type,{commandId:id,...payload});return id;}
  function setState(next){
    state=next;const active=(!!worker||state==='initializing')&&!['complete','error','stopped'].includes(state);
    $('start').disabled=active;$('quality').disabled=active;$('restore').disabled=active;
    $('pause').disabled=!frame||['stopped','error'].includes(state);$('stop').disabled=!active;
    $('save').disabled=!worker||!frame;$('export').disabled=!frame;
    $('pause').textContent=isPaused?'▶ 继续':'Ⅱ 暂停';
    $('pause').setAttribute('aria-label',isPaused?'继续计算和播放':'暂停计算和播放');
    const pill=$('live-pill');pill.classList.toggle('running',active&&!isPaused);
    const pendingControl=lastRequestedControl&&pending.has(lastRequestedControl.commandId);pill.textContent=replaying?'正在回看':state==='error'?'已停止':state==='stopped'?'本轮已结束':pendingControl?(lastRequestedControl.type==='PAUSE'?'正在暂停计算':'正在继续计算'):isPaused?'已暂停':state==='complete'?'本轮已完成':state==='initializing'?'环境准备中':active?'天气演变中':'未开始';
  }
  function decode(entry){const n=entry.grid.nx*entry.grid.ny;return {low:new Uint8Array(entry.buffer,0,n),composite:new Uint8Array(entry.buffer,n,n),rain:new Uint16Array(entry.buffer,2*n,n),total:new Uint32Array(entry.buffer,4*n,n)};}
  function decodeWind(entry){if(!entry?.windGrid)return null;if(!windCache.has(entry)){const g=entry.windGrid,n=g.nx*g.ny;windCache.set(entry,{u:new Float32Array(g.buffer,0,n),v:new Float32Array(g.buffer,n*4,n)});}return windCache.get(entry);}
  function decodeCold(entry){if(!entry?.coldGrid)return null;if(!coldCache.has(entry)){const g=entry.coldGrid,n=g.nx*g.ny;coldCache.set(entry,{depth:new Float32Array(g.buffer,0,n),deficit:new Float32Array(g.buffer,n*4,n),u:new Float32Array(g.buffer,n*8,n),v:new Float32Array(g.buffer,n*12,n)});}return coldCache.get(entry);}
  function decodeTrigger(entry){if(!entry?.triggerGrid)return null;if(!triggerCache.has(entry)){const g=entry.triggerGrid,n=g.nx*g.ny;triggerCache.set(entry,{elevation:new Float32Array(g.buffer,0,n),lift:new Float32Array(g.buffer,n*4,n),gate:new Float32Array(g.buffer,n*8,n)});}return triggerCache.get(entry);}
  function ensureRain24(entry){
    if(!entry||!store||rain24Cache.has(entry)||rain24Pending.has(entry))return;
    const owned=store,task=VacationRain24.calculate(entry,owned.index.slice(),seq=>owned.get(seq),decode).then(values=>{
      rain24Cache.set(entry,values);if(frame===entry&&store===owned){for(const view of views)if(view.key==='rain24')view.draw();updatePoint();}
    }).catch(error=>{if(frame===entry&&store===owned){$('point-rain24').textContent='—';$('map-status').textContent=error.message;}}).finally(()=>rain24Pending.delete(entry));
    rain24Pending.set(entry,task);
  }
  function coldAt(entry,lon,lat){const g=entry?.coldGrid,c=decodeCold(entry);if(!g||!c||!projection)return null;const p=projection.forward([lon,lat]),x=p[0]+g.width/2,y=p[1]+g.height/2;if(x<0||y<0||x>=g.width||y>=g.height)return null;const k=Math.floor(y/g.dx)*g.nx+Math.floor(x/g.dx);return {depth:c.depth[k],deficit:c.deficit[k],u:c.u[k],v:c.v[k]};}
  function windAt(entry,lon,lat){const g=entry?.windGrid,wind=decodeWind(entry);if(!g||!wind||!projection)return null;const xy=projection.forward([lon,lat]),x=xy[0]+g.width/2,y=xy[1]+g.height/2;if(x<0||y<0||x>=g.width||y>=g.height)return null;const k=Math.floor(y/g.dx)*g.nx+Math.floor(x/g.dx);return {u:wind.u[k],v:wind.v[k]};}
  const Raster=L.Layer.extend({
    initialize(view){this.view=view;},
    onAdd(map){this.map=map;this.canvas=L.DomUtil.create('canvas','vacation-raster leaflet-zoom-animated');map.getPane('vacationRadar').appendChild(this.canvas);this.gl=this.canvas.getContext('webgl',{alpha:true,antialias:false,premultipliedAlpha:false,preserveDrawingBuffer:true});if(this.gl)this.initGL();else this.context=this.canvas.getContext('2d');this.redraw=this.draw.bind(this);this.animate=e=>{if(this.topLeft)L.DomUtil.setTransform(this.canvas,map._latLngToNewLayerPoint(this.topLeft,e.zoom,e.center),map.getZoomScale(e.zoom,this.drawZoom));};map.on('move zoom resize zoomend',this.redraw);map.on('zoomanim',this.animate);this.draw();},
    initGL(){const gl=this.gl,shader=(type,src)=>{const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error('地图着色器不可用');return s;};this.program=gl.createProgram();gl.attachShader(this.program,shader(gl.VERTEX_SHADER,'attribute vec2 p;attribute vec2 uv;varying vec2 v;void main(){v=uv;gl_Position=vec4(p,0.,1.);}'));gl.attachShader(this.program,shader(gl.FRAGMENT_SHADER,'precision mediump float;uniform sampler2D image;uniform float opacity;varying vec2 v;void main(){vec4 c=texture2D(image,v);gl_FragColor=vec4(c.rgb,c.a*opacity);}'));gl.linkProgram(this.program);gl.useProgram(this.program);this.buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);for(const [name,offset]of [['p',0],['uv',8]]){const loc=gl.getAttribLocation(this.program,name);gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,2,gl.FLOAT,false,16,offset);}this.texture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,this.texture);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);gl.uniform1i(gl.getUniformLocation(this.program,'image'),0);gl.disable(gl.BLEND);},
    clear(){this.grid=null;this.source=null;this.pixels=null;if(this.gl){this.gl.clearColor(0,0,0,0);this.gl.clear(this.gl.COLOR_BUFFER_BIT);}else this.context.clearRect(0,0,this.canvas.width,this.canvas.height);},
    update(entry){
      if(!entry||!projection)return;
      const rain24=this.view.key==='rain24',rolling=rain24?rain24Cache.get(entry):null,monsoon=this.view.key==='monsoon',cold=this.view.key==='cold',terrain=this.view.key==='terrain',trigger=this.view.key==='trigger',lifting=terrain||trigger?decodeTrigger(entry):null,wind=monsoon?decodeWind(entry):null,cooling=cold?decodeCold(entry):null;
      if(rain24&&!rolling||monsoon&&!wind||cold&&!cooling||(terrain||trigger)&&!lifting){this.clear();return;}
      this.grid=monsoon?entry.windGrid:cold?entry.coldGrid:terrain||trigger?entry.triggerGrid:entry.grid;
      const n=this.grid.nx*this.grid.ny,fields=rain24||monsoon||cold||terrain||trigger?null:decode(entry);
      this.pixels=new Uint8Array(n*4);
      for(let i=0;i<n;i++){
        let color,alpha=235;
        if(rain24){if(rolling[i]<.1)continue;color=rain24Color(rolling[i]);}
        else if(monsoon){const speed=Math.hypot(wind.u[i],wind.v[i]);if(!Number.isFinite(speed))continue;color=windColors[Math.min(300,Math.round(speed*10))];alpha=210;}
        else if(terrain||trigger){const value=terrain?lifting.lift[i]:lifting.gate[i];if(value<(terrain?5:.005))continue;color=liftColor(value,terrain?600:1);alpha=235;}
        else if(cold){if(cooling.depth[i]<5||cooling.deficit[i]<.05)continue;color=coldColor(cooling.deficit[i]);alpha=Math.round(235*Math.min(1,cooling.depth[i]/40));}
        else{const encoded=fields.composite[i];if(encoded===255)continue;const value=encoded*.5-10;if(value<5)continue;color=radarColors[encoded];}
        const k=i*4;this.pixels[k]=color[0];this.pixels[k+1]=color[1];this.pixels[k+2]=color[2];this.pixels[k+3]=alpha;
      }
      if(this.gl){const gl=this.gl;gl.bindTexture(gl.TEXTURE_2D,this.texture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,this.grid.nx,this.grid.ny,0,gl.RGBA,gl.UNSIGNED_BYTE,this.pixels);}
      else{this.source=document.createElement('canvas');this.source.width=this.grid.nx;this.source.height=this.grid.ny;this.source.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(this.pixels.buffer),this.grid.nx,this.grid.ny),0,0);}
      this.draw();
    },
    draw(){if(this.view.disposed||this.map._animatingZoom)return;const size=this.map.getSize(),dpr=Math.min(2,devicePixelRatio||1);if(this.canvas.width!==size.x*dpr||this.canvas.height!==size.y*dpr){this.canvas.width=size.x*dpr;this.canvas.height=size.y*dpr;this.canvas.style.width=size.x+'px';this.canvas.style.height=size.y+'px';}this.topLeft=this.map.containerPointToLatLng([0,0]);this.drawZoom=this.map.getZoom();L.DomUtil.setTransform(this.canvas,this.map.containerPointToLayerPoint([0,0]),1);if(!this.grid||!projection)return;const w=this.grid.width,h=this.grid.height,nx=24,ny=18,verts=[],screen=[];
      for(let y=0;y<=ny;y++)for(let x=0;x<=nx;x++){const lonlat=projection.inverse([x/nx*w-w/2,y/ny*h-h/2]),p=this.map.latLngToContainerPoint([lonlat[1],lonlat[0]]);screen.push([p.x,p.y,x/nx,y/ny]);}
      const triangles=[];for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){const a=y*(nx+1)+x,b=a+1,c=a+nx+1,d=c+1;triangles.push([a,b,c],[b,d,c]);}
      if(this.gl){const gl=this.gl;for(const tri of triangles)for(const index of tri){const p=screen[index];verts.push(2*p[0]/size.x-1,1-2*p[1]/size.y,p[2],p[3]);}gl.viewport(0,0,this.canvas.width,this.canvas.height);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);gl.useProgram(this.program);gl.bindBuffer(gl.ARRAY_BUFFER,this.buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(verts),gl.DYNAMIC_DRAW);gl.uniform1f(gl.getUniformLocation(this.program,'opacity'),+$('opacity').value);gl.drawArrays(gl.TRIANGLES,0,verts.length/4);}else if(this.source){const ctx=this.context;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,size.x,size.y);ctx.globalAlpha=+$('opacity').value;for(const tri of triangles){const p=tri.map(i=>screen[i]),s=p.map(p=>[p[2]*this.source.width,p[3]*this.source.height]),den=s[0][0]*(s[1][1]-s[2][1])+s[1][0]*(s[2][1]-s[0][1])+s[2][0]*(s[0][1]-s[1][1]);if(!den)continue;const coeff=axis=>[(p[0][axis]*(s[1][1]-s[2][1])+p[1][axis]*(s[2][1]-s[0][1])+p[2][axis]*(s[0][1]-s[1][1]))/den,(p[0][axis]*(s[2][0]-s[1][0])+p[1][axis]*(s[0][0]-s[2][0])+p[2][axis]*(s[1][0]-s[0][0]))/den,(p[0][axis]*(s[1][0]*s[2][1]-s[2][0]*s[1][1])+p[1][axis]*(s[2][0]*s[0][1]-s[0][0]*s[2][1])+p[2][axis]*(s[0][0]*s[1][1]-s[1][0]*s[0][1]))/den],a=coeff(0),b=coeff(1);ctx.save();ctx.beginPath();ctx.moveTo(p[0][0],p[0][1]);ctx.lineTo(p[1][0],p[1][1]);ctx.lineTo(p[2][0],p[2][1]);ctx.closePath();ctx.clip();ctx.transform(a[0],b[0],a[1],b[1],a[2],b[2]);ctx.drawImage(this.source,0,0);ctx.restore();}}},
    onRemove(){this.map.off('move zoom resize zoomend',this.redraw);this.map.off('zoomanim',this.animate);if(this.gl){this.gl.deleteTexture(this.texture);this.gl.deleteBuffer(this.buffer);this.gl.deleteProgram(this.program);this.gl.getExtension('WEBGL_lose_context')?.loseContext();}this.canvas.remove();}
  });

  // Match the interaction contract used by StormSim's simulation-v2.js.
  const SmoothMap=L.Map.extend({
    setZoomAround(point,zoom,options){return L.Map.prototype.setZoomAround.call(this,point,zoom,{animate:true,...options});},
    panBy(offset,options){
      if(this._animatingZoom)return this;
      // Clamp the animation target too: keyboard pans and inertia must not show
      // empty areas before Leaflet's moveend boundary correction runs.
      const b=this.options.maxBounds;
      if(b&&this._loaded){const z=this.getZoom(),half=this.getSize().divideBy(2),a=this.project(b.getNorthWest(),z).add(half),c=this.project(b.getSouthEast(),z).subtract(half),now=this.project(this.getCenter(),z),next=now.add(L.point(offset));
        offset=L.point(Math.max(a.x,Math.min(c.x,next.x)),Math.max(a.y,Math.min(c.y,next.y))).subtract(now);}
      return L.Map.prototype.panBy.call(this,offset,options);
    }
  });
  class MapView {
    constructor(card,key,index,center,zoom){
      this.card=card;this.key=key;this.element=card.querySelector('.weather-map');
      this.element.id=index===0?'weather-map':'weather-map-'+index;
      this.element.setAttribute('role','region');
      this.map=new SmoothMap(this.element,{preferCanvas:false,renderer:L.svg({padding:.35}),zoomControl:true,zoomAnimation:true,markerZoomAnimation:true,zoomAnimationThreshold:10,minZoom:5,maxZoom:14,maxBounds:REGION,maxBoundsViscosity:1,zoomSnap:.25,zoomDelta:.5,wheelPxPerZoomLevel:140,wheelDebounceTime:70,inertia:true}).setView(REGION.getCenter(),6);
      L.control.scale({imperial:false,maxWidth:90}).addTo(this.map);
      this.map.createPane('vacationRadar');this.map.getPane('vacationRadar').style.zIndex='450';this.map.getPane('vacationRadar').style.pointerEvents='none';
      this.map.createPane('vacationVectors');this.map.getPane('vacationVectors').style.zIndex='460';this.map.getPane('vacationVectors').style.pointerEvents='none';
      this.vectors=L.polyline([],{pane:'vacationVectors',color:'#445c7b',weight:1.3,opacity:.85,interactive:false}).addTo(this.map);
      this.markers=L.layerGroup().addTo(this.map);
      this.coast=L.polyline(coastlines,{color:'#8e9b9d',weight:1,opacity:.65,interactive:false}).addTo(this.map);
      this.raster=new Raster(this).addTo(this.map);this.setBase();
      this.limitView(true);if(center){this.map.setView(center,zoom,{animate:false});this.constrainView();}
      this.map.on('zoomstart',()=>{this.zooming=true;});
      this.map.on('zoomend',()=>{this.zooming=false;this.constrainView();});
      this.map.on('zoomanim',e=>{if(!this.disposed&&!this.following&&!syncing)this.syncView(e.center,e.zoom);});
      this.map.on('movestart',()=>{if(this.disposed||syncing||this.following)return;syncing=true;try{views.forEach(v=>{if(v!==this&&!v.disposed){cancelAnimationFrame(v.syncRAF);v.syncRAF=null;}});}finally{syncing=false;}});
      this.map.on('move',()=>{if(this.disposed||syncing||this.following||this.zooming||this.syncRAF)return;this.syncRAF=requestAnimationFrame(()=>{this.syncRAF=null;this.syncView();});});
      this.map.on('moveend',()=>{if(this.disposed)return;if(this.following){this.following=false;const pending=this.pendingView;this.pendingView=null;if(pending){const locked=syncing;syncing=true;try{this.followView(pending.center,pending.zoom);}finally{syncing=locked;}}this.queueVectors();return;}if(syncing)return;cancelAnimationFrame(this.syncRAF);this.syncRAF=null;this.syncView();views.forEach(v=>v.queueVectors());});
      this.map.on('click',e=>{if(!picking){const selected=this.nearestStation(e);if(selected)selectPoint(selected);return;}point={id:'custom',name:'自选观测点',lon:e.latlng.lng,lat:e.latlng.lat};setPicking(false);selectPoint(point);});
      this.lastSize=this.map.getSize();this.resize=new ResizeObserver(()=>{if(this.disposed)return;const size=L.point(this.element.clientWidth,this.element.clientHeight);if(size.equals(this.lastSize))return;this.lastSize=size;const resize=()=>{if(this.disposed)return;this.map.invalidateSize({pan:false});this.limitView();this.queueVectors();};if(this.zooming)this.map.once('zoomend',resize);else resize();});this.resize.observe(this.element);
      this.updateMarkers();this.legend();
    }
    setBase(){
      if(this.base)this.map.removeLayer(this.base);if(this.baseFallback)this.map.removeLayer(this.baseFallback);
      const name=$('basemap').value;this.vectors.setStyle({color:name==='satellite'?'#f6f7ff':'#344866'});
      this.base=null;this.baseFallback=null;if(name==='none')return;
      const satellite=name==='satellite';
      const url=satellite?'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}':'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
      const options={maxZoom:15,bounds:REGION,noWrap:true,keepBuffer:3,updateWhenZooming:false,updateWhenIdle:true};
      this.baseFallback=L.tileLayer(url,{...options,minNativeZoom:6,maxNativeZoom:6,zIndex:1}).addTo(this.map);
      this.base=L.tileLayer(url,{...options,zIndex:2,attribution:satellite?'Tiles © Esri — Esri, Maxar, Earthstar Geographics':'© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(this.map);
      const active=this.base;this.base.on('tileerror',()=>{if(this.base===active)$('map-status').textContent='在线底图暂时无法加载，可切换底图；模拟风场与回波仍可显示。';});
    }
    syncView(center=this.map.getCenter(),zoom=this.map.getZoom()){if(this.disposed||syncing)return;syncing=true;try{for(const view of views)if(view!==this&&!view.disposed)view.followView(center,zoom);}finally{syncing=false;}}
    followView(center,zoom){if(this.following||this.zooming){this.pendingView={center,zoom};return;}if(this.map.getZoom()!==zoom){this.following=true;this.map.setView(center,zoom,{animate:true});return;}const delta=this.map.project(center,zoom).subtract(this.map.project(this.map.getCenter(),zoom));if(Math.abs(delta.x)>.5||Math.abs(delta.y)>.5)this.map.panBy(delta,{animate:false});}
    queueVectors(){cancelAnimationFrame(this.vectorRAF);this.vectorRAF=requestAnimationFrame(()=>{if(!this.disposed&&!this.zooming&&!this.following)this.drawVectors();});}
    constrainView(){this.map.panInsideBounds(REGION,{animate:false});this.map.dragging.enable();}
    limitView(reset=false){
      // The viewport must fit inside the data, even in a wide or tall window.
      // Ceil to the existing StormSim quarter-zoom grid, never expand bounds.
      const m=this.map,size=m.getSize(),span=m.project(REGION.getSouthEast(),0).subtract(m.project(REGION.getNorthWest(),0));
      const min=Math.ceil(Math.log2(Math.max(size.x/Math.abs(span.x),size.y/Math.abs(span.y)))/.25)*.25;
      m.setMaxZoom(Math.max(14,min));
      // setMinZoom auto-animates if the current zoom is smaller. Complete this
      // resize synchronously so a queued initial zoom cannot swallow user input.
      if(m.getZoom()<min)m.setView(m.getCenter(),min,{animate:false});
      m.setMinZoom(min);
      if(reset)m.setView(REGION.getCenter(),min,{animate:false});
      this.constrainView();
    }
    nearestStation(e){if(!$('show-stations').checked)return null;const touch=matchMedia('(pointer: coarse)').matches||e.originalEvent?.pointerType==='touch',pixel=e.containerPoint||this.map.latLngToContainerPoint(e.latlng);let radius=touch?22:14,nearest=null;for(const s of stations){const d=pixel.distanceTo(this.map.latLngToContainerPoint([s.lat,s.lon]));if(d<radius){radius=d;nearest=s;}}return nearest;}
    updateMarkers(){
      this.markers.clearLayers();if(!$('show-stations').checked)return;
      for(const station of [...stations,...(point.id==='custom'?[point]:[])]){
        const selected=station.id===point.id;
        L.circleMarker([station.lat,station.lon],{radius:selected?6:3.5,color:'#fff',weight:selected?2:1,fillColor:selected?'#aa527e':'#7863b6',fillOpacity:.95,bubblingMouseEvents:false})
          .bindTooltip(document.createTextNode(station.name)).on('click',()=>{if(picking){selectPoint({...station,id:'custom',name:'自选观测点'});setPicking(false);}else selectPoint(station);}).addTo(this.markers);
      }
    }
    legend(){
      const spec=LAYERS[this.key];this.element.setAttribute('aria-label',spec.name+'地图');
      const colors=Array.from({length:13},(_,i)=>this.key==='rain24'?interpolate(rainPalette,i/12):this.key==='radar'?radarColor(5+i*5):this.key==='cold'?coldColor(i*2.5/12):this.key==='terrain'||this.key==='trigger'?liftColor(i/12,1):windColor(i*2.5));
      this.card.querySelector('.legend-colors').replaceChildren(...colors.map(color=>{const e=document.createElement('span');e.style.background='rgb('+color.join(',')+')';return e;}));
      this.card.querySelector('.legend-labels').replaceChildren(...spec.labels.map(label=>{const e=document.createElement('span');e.textContent=label;return e;}));
    }
    draw(){this.raster.update(frame);this.drawVectors();this.card.querySelector('.map-time').textContent=frame?day(frame.simTime)+' '+clock(frame.simTime):'等待开始';}
    drawVectors(){
      const lines=[];
      if((this.key==='monsoon'&&frame?.windGrid||this.key==='cold'&&frame?.coldGrid)&&projection){
        const size=this.map.getSize();
        for(let y=28;y<size.y;y+=56)for(let x=28;x<size.x;x+=56){
          const ll=this.map.containerPointToLatLng([x,y]),wind=this.key==='cold'?coldAt(frame,ll.lng,ll.lat):windAt(frame,ll.lng,ll.lat);if(!wind||this.key==='cold'&&wind.depth<40||Math.hypot(wind.u,wind.v)<.5)continue;
          const a=Math.atan2(-wind.v,wind.u),ex=x+Math.cos(a)*19,ey=y+Math.sin(a)*19,toLL=p=>this.map.containerPointToLatLng(p);
          lines.push([[x,y],[ex,ey],[ex-5*Math.cos(a-.5),ey-5*Math.sin(a-.5)]].map(toLL),[[ex,ey],[ex-5*Math.cos(a+.5),ey-5*Math.sin(a+.5)]].map(toLL));
        }
      }
      this.vectors.setLatLngs(lines);
    }
    clear(){this.raster.clear();this.vectors.setLatLngs([]);this.card.querySelector('.map-time').textContent='等待开始';}
    destroy(){this.disposed=true;this.pendingView=null;this.resize.disconnect();cancelAnimationFrame(this.syncRAF);cancelAnimationFrame(this.vectorRAF);this.map.stop();if(this.zooming)this.map.once('zoomend',()=>this.map.remove());else this.map.remove();}
  }
  function maps(count){
    const previous=views,center=previous[0]?.map.getCenter(),zoom=previous[0]?.map.getZoom();views=[];
    previous.forEach(view=>view.destroy());$('map-grid').replaceChildren();$('map-grid').className='map-grid layout-'+count;
    document.querySelectorAll('[data-layout]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.layout)===count)));
    for(let i=0;i<count;i++){
      const card=document.createElement('article');card.className='map-card';
      card.innerHTML='<header><select aria-label="选择气象图 '+(i+1)+'"></select><time class="map-time"></time></header><div class="weather-map vacation-map"></div><div class="legend"><div class="legend-colors"></div><div class="legend-labels"></div></div>';
      const select=card.querySelector('select');for(const [key,spec]of Object.entries(LAYERS)){const option=document.createElement('option');option.value=key;option.textContent=spec.name;select.append(option);}select.value=choices[i];
      $('map-grid').append(card);const view=new MapView(card,choices[i],i,center,zoom);views.push(view);view.draw();
      select.onchange=()=>{choices[i]=view.key=select.value;view.legend();view.draw();};
    }
    setPicking(picking);
  }
  function setPicking(value){picking=value;$('add-on-map').setAttribute('aria-pressed',String(value));$('add-on-map').textContent=value?'点击地图选择观测点':'＋ 地图选点';for(const view of views)view.element.classList.toggle('picking',value);}
  function stationOptions(){
    const query=$('station-search').value.trim().toLowerCase();
    const options=stations.filter(s=>(s.name+(s.stationName||'')+s.id+(s.province||'')).toLowerCase().includes(query));
    $('station-select').replaceChildren(...options.map(s=>{const o=document.createElement('option');o.value=s.id;o.textContent=s.name+' · '+s.id;o.selected=s.id===point.id;return o;}));
  }
  function selectPoint(selected){point={...selected};$('station-select').value=point.id;for(const view of views)view.updateMarkers();updatePoint();}
  function updatePoint(){
    $('point-name').textContent=point.name;$('point-id').textContent=point.id==='custom'?'自选':point.id;
    $('point-coordinates').textContent=point.lon.toFixed(2)+'°E · '+point.lat.toFixed(2)+'°N';$('point-time').textContent=frame?day(frame.simTime)+' '+clock(frame.simTime):'';
    const ids=['point-z','point-wind','point-direction','point-rain','point-total','point-rain24'];
    if(!frame||!projection){for(const id of ids)$(id).textContent='—';return;}
    const xy=projection.forward([point.lon,point.lat]),g=frame.grid,x=xy[0]+g.width/2,y=xy[1]+g.height/2;
    if(x<0||y<0||x>=g.width||y>=g.height){for(const id of ids)$(id).textContent='域外';return;}
    const k=Math.floor(y/g.dx)*g.nx+Math.floor(x/g.dx),f=decode(frame),wind=windAt(frame,point.lon,point.lat),speed=wind?Math.hypot(wind.u,wind.v):NaN;
    $('point-z').textContent=f.composite[k]===255?'无回波':(f.composite[k]*.5-10).toFixed(1);
    $('point-rain').textContent=(f.rain[k]*.1).toFixed(1);$('point-total').textContent=(f.total[k]*.01).toFixed(1);
    $('point-wind').textContent=Number.isFinite(speed)?speed.toFixed(1):'—';
    $('point-direction').textContent=speed>=.1?((Math.atan2(-wind.u,-wind.v)*180/Math.PI+360)%360).toFixed(0):'—';
    const rolling=rain24Cache.get(frame);$('point-rain24').textContent=rolling?rolling[k].toFixed(1):'计算中';
  }
  function updateTimeProgress(){if(config)$('clock-progress').textContent='10 分钟/步 · 已计算 '+(coreTime/3600).toFixed(2)+' / '+config.hours+' 小时 · 可回放至 '+(latestTime/3600).toFixed(2)+' 小时 · 当前画面 '+((frame?.simTime||0)/3600).toFixed(2)+' 小时';}
  function show(entry){const renderBegin=performance.now();
    if(!entry)return;frame=entry;ensureRain24(entry);for(const view of views)view.draw();updatePoint();
    $('clock').textContent=clock(entry.simTime);$('day').textContent=day(entry.simTime)+' · 北京时间';
    updateTimeProgress();
    $('cell-count').textContent=entry.metrics.cells;$('max-rain').textContent=entry.metrics.maxRate.toFixed(1)+' mm/h';$('max-total').textContent=entry.metrics.maxTotal.toFixed(1)+' mm';
    $('welcome').hidden=true;$('loading').hidden=true;$('replay-bar').hidden=false;setState(state);updateHistory();updateDiagnostics();
    renderMs=performance.now()-renderBegin;
  }
  function updateHistory(){
    if(!store)return;const entries=store.index;$('timeline').disabled=entries.length<2;$('timeline').max=Math.max(0,entries.length-1);
    $('timeline').value=Math.max(0,entries.findIndex(e=>e.seq===frame?.seq));
    $('timeline-end').textContent=entries.length?day(entries[0].simTime)+' '+clock(entries[0].simTime)+' — '+day(entries.at(-1).simTime)+' '+clock(entries.at(-1).simTime):'尚未生成';
    $('history-status').textContent=(replaying?'正在回看。继续时将返回最新已算状态。':state==='complete'?'本轮已完成，可回看已生成时段。':'计算与显示正在同步推进。')+' 整轮已生成时段均可回放。';
    $('toggle-replay').disabled=entries.length<2;$('toggle-replay').textContent=replayPlaying?'暂停回放':replaying&&frame?.seq===entries.at(-1)?.seq?'重新播放':'播放回放';$('live').hidden=!replaying;$('timeline-title').textContent=replaying?'回看 · '+clock(frame.simTime):'回顾本轮';
  }
  function updateDiagnostics(){
    if($('diagnostics').hidden)return;const a=frame?.metrics||{};
    $('diagnostic-text').textContent=JSON.stringify({model:V.MODEL_VERSION,backend:liveStats.backend,seed:config?.seed,coreTime,confirmedCoreTime,replayAvailableUntil:latestTime,displayTime:frame?.simTime,displayPlayhead:displayTime,actualCoreState,lastRequestedControl,lastReceivedControl,lastAppliedControl,firstFrameMs,worker:liveStats,pageTiming:{renderMs,cacheWriteMs},replay:{frames:store?.index.length||0,RAM_MiB:(store?.bytes||0)/1048576,pendingWrites:store?.pending||0},water:{relativeResidual:a.relativeResidual,activityResidual:a.activityResidual},births:frame?.stats?.births,coldPoolBirths:frame?.stats?.coldBirths,lastError},null,2);
  }
  async function start(override={},checkpoint=null,history=null){await initialized;if(state==='initializing')return;if(worker&&state!=='complete')return;worker?.terminate();store?.close();runId=crypto.randomUUID();frame=latest=null;for(const view of views)view.clear();updatePoint();$('replay-bar').hidden=true;seqCount=0;displayTime=latestTime=coreTime=checkpoint?.t||0;lastError=null;isPaused=false;replaying=false;replayPlaying=false;paintTask=null;seekRevision++;pending.clear();runLog=[];confirmedCoreTime=coreTime;lastRequestedControl=lastReceivedControl=lastAppliedControl=null;actualCoreState='initializing';liveStats={state:actualCoreState,simTime:coreTime};firstFrameMs=null;startWall=performance.now();config=checkpoint?.config||{preset:'monsoon',quality:$('quality').value,geography:'real',...override};if(!checkpoint&&config.seed===undefined&&config.windTurnStart===undefined){let storage=null;try{storage=localStorage;}catch{}config.windTurnStart=VacationRandom.nextWindStart(storage,()=>crypto.getRandomValues(new Uint32Array(1))[0]&1);if(!config.weatherRegion||config.weatherRegion==='auto')config.weatherRegion=VacationRandom.nextJetRegion(storage,()=>crypto.getRandomValues(new Uint32Array(1))[0]/4294967296);}
    $('restore').hidden=true;$('loading').hidden=false;$('loading-text').textContent='正在准备本机回放存储…';$('welcome').hidden=true;setState('initializing');store=new VacationStore(()=>setStatus('正在切换本机备用存储，继续保存整轮回放。'),STORAGE_NAME);const initializingRun=runId,initializingStore=store;await initializingStore.open(initializingRun,{resume:history});if(initializingRun!==runId){initializingStore.close();return;}const owned=new Worker('assets/scripts/vacation-worker.js?v='+V.RESOURCE_VERSION);worker=owned;setState('initializing');owned.onerror=e=>fail(e.message);owned.onmessage=async({data})=>{if(worker!==owned||data.runId!==runId)return;try{if(data.type==='STATUS'){$('loading-text').textContent=data.message;setStatus(data.message);}else if(data.type==='READY'){if(data.version!==V.MODEL_VERSION)throw Error('页面与计算内核版本不一致，请刷新页面');config=data.config;liveStats={...liveStats,backend:data.backend};coreTime=data.simTime;confirmedCoreTime=coreTime;actualCoreState='running';$('loading-text').textContent='地形已就绪，正在生成首帧…';setStatus('环境已就绪，正在推进第一个天气状态…');setState('running');sendCommand('SAVE');}else if(data.type==='SNAPSHOT'){
          const original=data.buffer;coreTime=Math.max(coreTime,data.simTime);seqCount++;const cacheBegin=performance.now(),entry=await store.put(data);cacheWriteMs=performance.now()-cacheBegin;if(worker!==owned||data.runId!==runId)return;latestTime=Math.max(latestTime,entry.simTime);latest=entry;if(firstFrameMs===null){firstFrameMs=performance.now()-startWall;displayTime=entry.simTime;show(entry);setStatus('天气正在演变。你可以随时暂停或回看。');}else if(!replaying&&!isPaused&&displayTime>=entry.simTime)show(entry);post('RECYCLE',{seq:data.seq,buffer:original},[original]);updateHistory();updateTimeProgress();
        }else if(data.type==='STATS'){const pausedFence=lastAppliedControl?.command==='PAUSE';if(!pausedFence)coreTime=Math.max(coreTime,data.simTime);actualCoreState=actualCoreState==='complete'?'complete':pausedFence?'paused':data.state;liveStats={...data,state:actualCoreState,simTime:coreTime};updateTimeProgress();updateDiagnostics();}else if(data.type==='COMMAND_RECEIVED'){lastReceivedControl={...data,receivedAtPage:performance.now()};runLog.push(lastReceivedControl);updateDiagnostics();}else if(data.type==='COMMAND_ACK'){const begin=pending.get(data.commandId);pending.delete(data.commandId);runLog.push({...data,latencyMs:begin?performance.now()-begin:null});const effective=data.actualEffectiveTime??data.t_core;if(Number.isFinite(effective)){coreTime=Math.max(coreTime,effective);confirmedCoreTime=Math.max(confirmedCoreTime,effective);}if(data.command==='PAUSE'||data.command==='RESUME'){if(!lastAppliedControl||data.commandId>=lastAppliedControl.commandId){lastAppliedControl={...data};actualCoreState=data.workerState||(data.command==='PAUSE'?'paused':'running');if(!lastRequestedControl||data.commandId>=lastRequestedControl.commandId)isPaused=data.command==='PAUSE';liveStats={...liveStats,state:actualCoreState,simTime:coreTime};setState(actualCoreState==='complete'?'complete':actualCoreState);}}updateTimeProgress();updateDiagnostics();}else if(data.type==='CHECKPOINT'){const ok=await store.saveCheckpoint(data.checkpoint);$('save-status').textContent=ok?'进度已保存':'无法持久保存';if(ok){restorable=data.checkpoint;restorableHistory={runId:store.runId,version:data.checkpoint.version,simTime:data.checkpoint.t,index:store.index.filter(e=>e.simTime<=data.checkpoint.t).map(e=>({...e}))};}}else if(data.type==='COMPLETE'){coreTime=Math.max(coreTime,data.simTime);confirmedCoreTime=coreTime;actualCoreState='complete';liveStats={...liveStats,state:'complete',simTime:coreTime};updateTimeProgress();setState('complete');setStatus('本轮计算已完成，画面会继续播放至终点。');}else if(data.type==='ERROR'){runLog.push({type:'ERROR',simTime:data.simTime,stack:data.stack});fail(data.message)};}catch(e){fail(e.message);}};
    owned.postMessage({type:'INIT',runId,schemaVersion:SCHEMA,expectedVersion:V.MODEL_VERSION,config,checkpoint});
  }
  function fail(message){actualCoreState='error';liveStats={...liveStats,state:'error'};lastError=message;worker?.terminate();worker=null;$('loading').hidden=true;if(!frame)$('welcome').hidden=false;setState('error');setStatus('模拟已停止：'+message+'。已生成时段仍可回看。');updateTimeProgress();updateHistory();updateDiagnostics();}
  function pause(){if(!worker)return;replayPlaying=false;seekRevision++;isPaused=!isPaused;if(isPaused)sendCommand('PAUSE');else{if(replaying){replaying=false;displayTime=latestTime;show(latest);}sendCommand('RESUME');lastTick=performance.now();}setState(state);}
  function stop(){if(!worker&&state!=='initializing')return;const old=worker;worker=null;runId=null;old?.terminate();pending.clear();replayPlaying=false;seekRevision++;isPaused=true;actualCoreState='stopped';liveStats={...liveStats,state:'stopped',simTime:coreTime};$('loading').hidden=true;setState('stopped');setStatus('本轮已结束，已生成的天气可以继续回看。');updateTimeProgress();updateDiagnostics();}
  function entryAt(time){const entries=store?.index||[];let lo=0,hi=entries.length-1,best=null;while(lo<=hi){const mid=(lo+hi)>>1;if(entries[mid].simTime<=time+.001){best=entries[mid];lo=mid+1;}else hi=mid-1;}return best;}
  async function tick(now){
    requestAnimationFrame(tick);const dt=Math.min(.25,(now-lastTick)/1000);lastTick=now;
    if(!frame||!(replayPlaying||!isPaused&&!replaying))return;
    displayTime=Math.min(latestTime,displayTime+dt*+$('speed').value);const desired=entryAt(displayTime);
    if(desired&&desired.seq!==frame.seq&&now-lastPaint>30&&!paintTask){
      lastPaint=now;const activeStore=store,run=runId,revision=seekRevision,task={};paintTask=task;
      try{const entry=await activeStore.get(desired.seq);if(activeStore===store&&run===runId&&revision===seekRevision&&(replayPlaying||!isPaused&&!replaying))show(entry);}
      catch(e){if(activeStore===store){replayPlaying=false;isPaused=true;setStatus(e.message);updateHistory();}}
      finally{if(paintTask===task)paintTask=null;}
    }
    if(!replaying&&now-lastProgress>100){post('DISPLAY_PROGRESS',{simTime:frame.simTime});lastProgress=now;}
    if(replayPlaying&&frame.seq===store.index.at(-1)?.seq){replayPlaying=false;updateHistory();setStatus('回放已到本轮最新时刻，可拖动时间轴或重新播放。');}
    if(!replaying&&state==='complete'&&frame.simTime>=coreTime){isPaused=true;setState(state);setStatus('这一场天气结束了。可以回看，也可以开始新一轮天气。');}
  }
  async function toggleReplay(){
    if(!store||store.index.length<2)return;seekRevision++;
    if(replayPlaying){replayPlaying=false;updateHistory();return;}
    if(worker&&!isPaused&&!['complete','stopped','error'].includes(state))sendCommand('PAUSE');
    isPaused=true;replaying=true;const activeStore=store,revision=seekRevision;
    try{if(!frame||frame.seq===store.index.at(-1).seq){const entry=await activeStore.get(store.index[0].seq);if(activeStore!==store||revision!==seekRevision)return;show(entry);}displayTime=frame.simTime;replayPlaying=true;lastTick=performance.now();setState(state);updateHistory();}
    catch(e){setStatus(e.message);}
  }

  document.querySelectorAll('[data-layout]').forEach(b=>b.onclick=()=>maps(Number(b.dataset.layout)));
  $('start').onclick=()=>start().catch(e=>fail(e.message));$('pause').onclick=pause;$('stop').onclick=stop;
  $('opacity').oninput=()=>views.forEach(view=>view.raster.draw());
  $('basemap').onchange=()=>{$('map-status').textContent='';views.forEach(view=>view.setBase());};
  $('show-stations').onchange=()=>views.forEach(view=>view.updateMarkers());
  $('region').onclick=()=>{const view=views[0];if(view)view.map.setView(REGION.getCenter(),view.map.getMinZoom(),{animate:true});};
  $('prd').onclick=()=>views[0]?.map.setView([22.65,113.7],9,{animate:true});
  $('add-on-map').onclick=()=>setPicking(!picking);
  $('station-search').oninput=stationOptions;
  $('station-select').onchange=()=>{const selected=stations.find(s=>s.id===$('station-select').value);if(selected)selectPoint(selected);};
  $('station-center').onclick=()=>views[0]?.map.setView([point.lat,point.lon],10,{animate:true});
  let seekRevision=0;
  $('timeline').oninput=async()=>{if(!store?.index.length)return;const revision=++seekRevision,activeStore=store;replayPlaying=false;if(!isPaused){isPaused=true;if(worker&&!['complete','stopped','error'].includes(state))sendCommand('PAUSE');}replaying=true;try{const entry=await activeStore.get(activeStore.index[+$('timeline').value]?.seq);if(revision===seekRevision&&activeStore===store&&entry){displayTime=entry.simTime;show(entry);}}catch(e){setStatus(e.message);}setState(state);updateHistory();};
  $('toggle-replay').onclick=toggleReplay;
  $('live').onclick=()=>{seekRevision++;replayPlaying=false;replaying=false;displayTime=latestTime;show(latest);setState(state);};
  $('save').onclick=()=>{$('save-status').textContent='正在保存…';sendCommand('SAVE');};
  $('restore').onclick=()=>{if(restorable)start({},restorable,restorableHistory).catch(e=>fail(e.message));};
  $('diagnostics-toggle').onclick=()=>{$('diagnostics').hidden=!$('diagnostics').hidden;$('diagnostics-toggle').setAttribute('aria-expanded',String(!$('diagnostics').hidden));updateDiagnostics();};
  $('about').onclick=()=>$('about-dialog').showModal();$('close-about').onclick=()=>$('about-dialog').close();$('about-dialog').onclick=e=>{if(e.target===$('about-dialog'))$('about-dialog').close();};
  $('export').onclick=()=>{
    const record={model:V.MODEL_VERSION,numericalBackend:liveStats.backend,config,generatedUntil:coreTime,coreComputedUntil:coreTime,coreConfirmedUntil:confirmedCoreTime,replayAvailableUntil:latestTime,actualCoreState,timeSemantics:{coreComputedUntil:'most recently observed complete core step; PAUSE ACK supplies its exact stopping endpoint',coreConfirmedUntil:'latest command/complete-confirmed core step',replayAvailableUntil:'last stored snapshot endpoint',displayedAt:'currently displayed snapshot time',generatedUntil:'alias of coreComputedUntil'},displayedAt:frame?.simTime,operations:runLog,metrics:frame?.metrics,stats:frame?.stats,selectedPoint:point,terrain:meta?.binarySha256,metricsAtSnapshot:frame?.simTime,performance:{firstFrameMs,worker:liveStats},limitations:'降阶机制实验，非实况、非业务预报。'};
    const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='vacation-'+config.seed+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&worker&&!isPaused&&state!=='complete'){isPaused=true;sendCommand('PAUSE');setState(state);}});
  window.addEventListener('pagehide',()=>worker?.terminate());
  async function initialize(){
    stationOptions();
    if(location.protocol==='file:'){$('start').disabled=true;setStatus('请通过项目中的本地预览启动器打开本页，或使用本地 HTTP 服务。');return;}
    try{
      meta=await VacationResource.json('assets/data/vacation-terrain.json?v='+V.RESOURCE_VERSION,{cache:'no-cache'});projection=proj4('EPSG:4326',meta.projection);
      const bounds=VacationMapDomain.bounds(meta,projection);REGION=L.latLngBounds([bounds.south,bounds.west],[bounds.north,bounds.east]);maps(2);
      const results=await Promise.allSettled([
        VacationResource.json('assets/data/vacation-coastlines.json?v='+V.RESOURCE_VERSION).then(data=>{coastlines=data.coordinates.map(line=>line.map(xy=>{const p=projection.inverse(xy);return [p[1],p[0]];}));for(const view of views)view.coast.setLatLngs(coastlines);}),
        VacationResource.json('assets/data/simulator-stations.json').then(data=>{stations=VacationMapDomain.stations(data,meta,projection,majorCities);point=stations.find(s=>s.id==='59493')||point;stationOptions();for(const view of views)view.updateMarkers();updatePoint();})
      ]);
      if(results[1].status==='rejected')$('point-kind').textContent='参考点';
      const initial=new VacationStore(null,STORAGE_NAME);await initial.open('inspection');const saved=await initial.latestCheckpointRecord();restorable=saved?.checkpoint||null;restorableHistory=saved?.replay?.simTime===restorable?.t&&saved?.replay?.version===V.MODEL_VERSION?saved.replay:null;
      const resume=V.checkpointPreflight(restorable);$('restore').hidden=!resume.eligible;if(!resume.eligible){if(restorable)setStatus(resume.reason==='version'?'上次进度属于旧版本，已保留；可以开始新过程。':'上次进度的元数据不完整，无法恢复；可以开始新过程。');restorable=null;}initial.close();
    }catch(e){setStatus('地图资源暂不可用：'+e.message);}
  }
  async function disposeTestStorage(){
    if(!testRun?.startsWith('acceptance'))throw Error('仅验收页面可清理测试存储');
    stop();const owned=store;store=null;
    if(owned){await Promise.allSettled([owned._writes,owned._checkpoints]);owned.close();}
    await new Promise((resolve,reject)=>{const r=indexedDB.deleteDatabase(STORAGE_NAME);r.onsuccess=resolve;r.onerror=()=>reject(r.error);r.onblocked=()=>reject(Error('测试存储仍被占用'));});
    if(window.caches)await caches.delete(STORAGE_NAME+'-complete-replay-v2');
  }
  window.VacationSimulator={start,pause,stop,...(testRun?.startsWith('acceptance')?{disposeTestStorage}:{}),getState:()=>({modelVersion:V.MODEL_VERSION,numericalBackend:liveStats.backend,state,isPaused,replaying,replayPlaying,runId,config,seqCount,displayTime:frame?.simTime||0,latestTime,coreTime,confirmedCoreTime,actualCoreState,lastRequestedControl,lastReceivedControl,lastAppliedControl,firstFrameMs,lastError,errorDetails:runLog.filter(e=>e.type==='ERROR').at(-1),metrics:frame?.metrics,stats:frame?.stats,worker:liveStats,pageTiming:{renderMs,cacheWriteMs},historyFrames:store?.index.length||0,historyStart:store?.index[0]?.simTime??null,historyEnd:store?.index.at(-1)?.simTime??null,archiveBackend:store?.backend,archiveBytes:store?.diskBytes||0,ramBytes:store?.bytes||0,pendingCommands:pending.size,commandLatencies:runLog.filter(e=>e.type==='COMMAND_ACK').map(e=>({command:e.command,latencyMs:e.latencyMs,receivedAtWorker:e.receivedAtWorker,appliedAtWorker:e.appliedAtWorker,workerBoundaryWaitMs:e.workerBoundaryWaitMs})).slice(-80),triggerGrid:frame?.triggerGrid?{nx:frame.triggerGrid.nx,ny:frame.triggerGrid.ny,bytes:frame.triggerGrid.buffer.byteLength}:null,windGrid:frame?.windGrid?{nx:frame.windGrid.nx,ny:frame.windGrid.ny,bytes:frame.windGrid.buffer.byteLength}:null,mapViews:views.map(v=>({key:v.key,bounds:{west:v.map.getBounds().getWest(),east:v.map.getBounds().getEast(),south:v.map.getBounds().getSouth(),north:v.map.getBounds().getNorth()},simulationCovered:!!projection&&VacationMapDomain.covered({west:v.map.getBounds().getWest(),east:v.map.getBounds().getEast(),south:v.map.getBounds().getSouth(),north:v.map.getBounds().getNorth()},meta,projection),center:{lat:v.map.getCenter().lat,lon:v.map.getCenter().lng},zoom:v.map.getZoom(),minZoom:v.map.getMinZoom(),maxZoom:v.map.getMaxZoom(),zooming:!!v.zooming,dragging:v.map.dragging.enabled(),interaction:{zoomSnap:v.map.options.zoomSnap,zoomDelta:v.map.options.zoomDelta,wheelPxPerZoomLevel:v.map.options.wheelPxPerZoomLevel,wheelDebounceTime:v.map.options.wheelDebounceTime,inertia:v.map.options.inertia,zoomAnimation:v.map.options.zoomAnimation},rasterPixels:v.raster.pixels?.length||0,vectorPaths:v.vectors.getLatLngs().length,webgl:v.raster.gl?{error:v.raster.gl.getError()}:null}))}),decode};
  initialized=initialize();requestAnimationFrame(tick);
})();
