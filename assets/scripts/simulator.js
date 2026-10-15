(function(){
    'use strict';
    const $=id=>document.getElementById(id),M=StormModel,R=StormRender,G=StormGeo;
    const STORAGE='felicia-simulator-points-v1';
    const controls=[
        ['month','春季背景月份',3,5,1,'月','理想化的 3–5 月温湿背景，并非当月实况。'],
        ['moisture','暖湿输送',.55,1.4,.05,'×','控制露点与两轮之间的环境恢复。'],
        ['jet','低空急流',.4,1.6,.05,'×','影响水汽补给、夜间低层风与引导气流。'],
        ['shear','垂直风切变',.2,1.8,.05,'×','影响单体组织和飑线维持。'],
        ['trough','南支槽扰动',0,1.6,.05,'×','第一轮的槽前触发与中层降温。'],
        ['front','冷锋强度',.2,1.6,.05,'×','锋面触发与锋后冷气团降温。'],
        ['frontSpeed','冷锋推进速度',.8,1.2,.05,'×','改变第二轮时间与完整模拟时长。'],
        ['terrain','山地作用',0,1.5,.05,'×','改变概化山高、冷池阻滞与入流抑制。'],
        ['estuary','珠江口稳定化',0,1.5,.05,'×','较冷水面及东岸海洋入流的稳定化。'],
        ['seaContrast','海陆温差',0,7,.5,'℃','温差越大，跨珠江口时低层抑制越明显。']
    ];
    let national=[],custom=[],stations=[],selected=null,frame=null,series=[],worker=null;
    let p={...M.DEFAULTS},request=0,busy=false,playing=false,lastTick=0,views=[],layout=2,picking=false;
    let radar={lon:114,lat:22.54,name:'深圳',elevation:.5};
    const view={lon:111.15,lat:23.25,zoom:1};
    const defaultLayers=['composite','velocity','lowwind','upperwind'];
    const chosenLayers=[...defaultLayers];
    function message(value){$('runtime-status').textContent=value;}
    function allStations(){stations=[...national,...custom];}
    function pause(){playing=false;$('play').textContent='▶ 继续模拟';}
    function flags(){return {stations:$('show-stations').checked,fronts:$('show-fronts').checked,
        terrain:$('show-terrain').checked,labels:$('show-labels').checked,fold:$('fold-velocity').checked};}
    function drawMaps(){if(frame&&selected)views.forEach(v=>v.draw(frame,view,stations,selected,radar,flags()));}
    function setLegend(card,layer){
        const spec=R.layers[layer];card.querySelector('.legend-bar').style.background=`linear-gradient(90deg,${spec.colors.join(',')})`;
        const labels=card.querySelector('.legend-text');labels.replaceChildren();
        for(const text of [layer==='velocity'?`${spec.scale[0]} 靠近`:spec.scale[0],...spec.scale.slice(1,-1),`${spec.scale.at(-1)} ${spec.unit}${layer==='velocity'?' 远离':''}`]){const s=document.createElement('span');s.textContent=text;labels.append(s);}
        card.querySelector('.legend').title=layer==='velocity'?'负值靠近雷达，正值远离雷达；无有效回波处不显示速度':spec.name+' · 合成数据';
    }
    function buildMaps(count){
        layout=count;views=[];$('map-grid').replaceChildren();$('map-grid').className='map-grid layout-'+count;
        document.querySelectorAll('[data-layout]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.layout)===count)));
        for(let i=0;i<count;i++){
            const card=document.createElement('article');card.className='map-card';
            card.innerHTML='<header><select aria-label="选择视窗气象图层"></select><time class="map-time"></time></header><canvas role="img" tabindex="0"></canvas><div class="legend"><div class="legend-bar"></div><div class="legend-text"></div></div>';
            const select=card.querySelector('select'),canvas=card.querySelector('canvas');
            for(const [key,value]of Object.entries(R.layers)){const option=document.createElement('option');option.value=key;option.textContent=value.name;select.append(option);}
            select.value=chosenLayers[i];canvas.setAttribute('aria-label',R.layers[select.value].name+'，可拖动、缩放或点击观测站');
            const renderer=new R.MapView(canvas,select.value);views.push(renderer);
            select.addEventListener('change',()=>{renderer.layer=select.value;chosenLayers[i]=select.value;canvas.setAttribute('aria-label',R.layers[select.value].name);setLegend(card,select.value);drawMaps();});
            setLegend(card,select.value);$('map-grid').append(card);bindMap(canvas,renderer);
        }
        if(frame){document.querySelectorAll('.map-time').forEach(e=>e.textContent=R.clock(frame.t));drawMaps();}
    }
    function bindMap(canvas,renderer){
        let start=null,drag=false;
        canvas.addEventListener('pointerdown',e=>{if(!renderer.proj)return;const r=canvas.getBoundingClientRect();start={x:e.clientX-r.left,y:e.clientY-r.top,lon:view.lon,lat:view.lat,scale:renderer.proj.scale};drag=false;canvas.setPointerCapture(e.pointerId);});
        canvas.addEventListener('pointermove',e=>{
            if(!renderer.proj)return;const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
            if(start&&Math.hypot(x-start.x,y-start.y)>4){drag=true;view.lon=G.clamp(start.lon-(x-start.x)/start.scale/102,104.3,118);view.lat=G.clamp(start.lat+(y-start.y)/start.scale/111,19.8,26.7);drawMaps();}
            const [lon,lat]=renderer.proj.from(x,y);let text=`${lon.toFixed(3)}°E / ${lat.toFixed(3)}°N`;
            if(frame&&['reflectivity','velocity'].includes(renderer.layer)){const gate=M.radarGate(frame,lon,lat,radar);text+=` · 距虚拟雷达 ${gate.range.toFixed(0)} km · 波束高度 ${gate.height.toFixed(1)} km`;
                if(gate.valid){const folded=((gate.velocity+25)%50+50)%50-25;text+=` · ${gate.dbz.toFixed(1)} dBZ · 径向速度 ${gate.velocity.toFixed(1)} m/s${flags().fold?' · 折叠显示 '+folded.toFixed(1)+' m/s':''}`;}
                else text+=' · 无有效回波 / 超出范围 / 地形遮挡';}
            $('map-readout').textContent=text;
        });
        canvas.addEventListener('pointerup',e=>{
            if(!start)return;const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
            if(!drag){
                if(picking){const [lon,lat]=renderer.proj.from(x,y);if(G.inDomain(lon,lat)){
                    $('custom-lon').value=lon.toFixed(4);$('custom-lat').value=lat.toFixed(4);document.querySelector('.custom-station').open=true;
                    $('custom-name').focus();$('station-message').textContent='位置已填入，请命名后点击“添加并观测”。';setPicking(false);
                }else message('请选择两广模拟范围内的位置。');}
                else{const station=renderer.hit(x,y);if(station)selectStation(station.id);}
            }start=null;
        });
        canvas.addEventListener('pointercancel',()=>{start=null;});
        canvas.addEventListener('wheel',e=>{if(!renderer.proj)return;e.preventDefault();const r=canvas.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;
            const before=renderer.proj.from(x,y);view.zoom=G.clamp(view.zoom*(e.deltaY<0?1.16:1/1.16),1,12);
            const after=R.projection(r.width,r.height,view).from(x,y);view.lon=G.clamp(view.lon+before[0]-after[0],104.3,118);view.lat=G.clamp(view.lat+before[1]-after[1],19.8,26.7);drawMaps();},{passive:false});
        canvas.addEventListener('keydown',e=>{if(e.key==='+'||e.key==='='){e.preventDefault();zoom(1.25);}else if(e.key==='-'){e.preventDefault();zoom(.8);}});
    }
    function setPicking(value){picking=value;$('add-on-map').textContent=value?'点击地图选择位置…':'＋ 地图选点';views.forEach(v=>v.canvas.classList.toggle('picking',value));}
    function zoom(factor){view.zoom=G.clamp(view.zoom*factor,1,12);drawMaps();}
    function stationOptions(){
        const query=$('station-search').value.trim().toLowerCase(),select=$('station-select');select.replaceChildren();
        for(const s of stations.filter(s=>(s.id+' '+s.name+' '+s.province).toLowerCase().includes(query))){
            const option=document.createElement('option');option.value=s.id;option.textContent=s.kind==='custom'?`${s.name} · 自定义`:`${s.name} · ${s.id} · ${s.province}`;option.selected=s.id===selected?.id;select.append(option);
        }
        if(!select.options.length){const option=document.createElement('option');option.textContent='没有匹配的站点';option.disabled=true;select.append(option);}
    }
    function send(time,init=false){
        if(!worker||!selected)return;busy=true;request++;$('compute-progress').hidden=false;$('compute-progress').value=0;message(init?'正在重建场景与观测历史…':'正在计算同步画面…');
        worker.postMessage({type:init?'init':'seek',time,p,stations,station:selected.id,request});
    }
    function selectStation(id){const s=stations.find(x=>x.id===id);if(!s)return;selected=s;stationOptions();send(frame?.t||0);}
    function format(value,digits=1){return Number.isFinite(value)?value.toFixed(digits):'—';}
    function direction(deg){return ['北','北东北','东北','东东北','东','东东南','东南','南东南','南','南西南','西南','西西南','西','西西北','西北','北西北'][Math.round(deg/22.5)%16];}
    function updateUI(){
        if(!frame||!selected)return;
        const o=frame.observations[selected.id];if(!o)return;
        const clock=R.clock(frame.t),frontTime=72/frame.p.frontSpeed,relative=frame.t-frontTime;
        $('sim-clock').textContent=clock;$('relative-clock').textContent=`${frame.p.month} 月场景 · 参考冷锋抵深${relative<0?'前':'后'} ${Math.abs(relative).toFixed(1)} 小时`;
        $('phase-title').textContent=frame.stage.title;$('phase-detail').textContent=frame.stage.detail;
        const phase=frame.t<8?1:frame.t<28?2:frame.t<frontTime-13?3:frame.t<frontTime+3?4:5;
        $('phase-index').textContent=`0${phase} / 05`;$('timeline').max=frame.duration;$('timeline').value=frame.t;
        document.querySelectorAll('.map-time').forEach(e=>e.textContent=clock);
        $('cell-count').textContent=`活跃单体 ${frame.summary.cells} · 强单体 ${frame.summary.strong}`;
        $('station-name').textContent=selected.name;$('station-id').textContent=selected.kind==='custom'?'自定义观测点':`${selected.id} · ${selected.province}国家站`;
        $('station-coordinates').textContent=`${selected.lon.toFixed(3)}°E / ${selected.lat.toFixed(3)}°N`;$('station-time').textContent=clock;
        for(const [id,key,digits]of [['obs-temp','temp',1],['obs-dew','dew',1],['obs-rh','humidity',0],['obs-pressure','pressure',1],['obs-wind','wind',1],['obs-gust','gust',1],['obs-rain','rain',1],['obs-hour','rain1h',1],['obs-total','total',1],['obs-cape','cape',0],['obs-cin','cin',0]])$(id).textContent=format(o[key],digits);
        $('obs-direction').textContent=o.wind<.2?'静风':direction(o.direction);$('obs-degrees').textContent=o.wind<.2?'':format(o.direction,0)+'°';
        $('delete-station').hidden=selected.kind!=='custom';$('diagnostic-place').textContent=selected.name;
        $('terrain-loss').textContent=format(o.terrainLoss*100,0)+'%';$('terrain-meter').value=o.terrainLoss*100;
        $('estuary-loss').textContent=format(o.estuaryLoss*100,0)+'%';$('estuary-meter').value=o.estuaryLoss*100;
        $('cold-anomaly').textContent=format(o.cold)+' K';
        const reasons=[];
        if(o.terrainLoss>.15)reasons.push(`概化山地高度约 ${Math.round(o.height)} m，冷池推进和低层入流受到限制。`);
        if(o.estuaryLoss>.1)reasons.push('珠江口较冷下垫面与海洋入流抬高低层稳定度，使过江回波更易减弱或断裂。');
        if(o.cold>.5)reasons.push(`雷暴自身冷池造成约 ${o.cold.toFixed(1)} K 的近地面降温，正消耗局地不稳定能量。`);
        if(o.coldAir>.6)reasons.push('地面冷锋冷气团已控制本站，持续偏北风与稳定层结抑制后续深对流。');
        else if(o.cape>1000)reasons.push(`仍有 ${Math.round(o.cape)} J/kg 的模拟 CAPE；若辐合触发足以克服 ${Math.round(o.cin)} J/kg 的 CIN，仍可新生单体。`);
        else reasons.push('当前可利用不稳定能量偏低，单有抬升也未必形成强回波。');
        $('mechanism-text').textContent=reasons.join('');
        $('radar-name').textContent='虚拟雷达：'+radar.name;
        drawMaps();R.stationChart($('station-chart'),series);R.profileChart($('profile-chart'),o,frame.p,frame.t);R.sectionChart($('section-chart'),frame,selected);
    }
    function controlsUI(){
        for(const [key,name,min,max,step,unit,help]of controls){
            const box=document.createElement('div');box.className='parameter';
            const top=document.createElement('div'),label=document.createElement('label'),output=document.createElement('output'),input=document.createElement('input'),small=document.createElement('small');
            label.htmlFor='param-'+key;label.textContent=name;output.id='value-'+key;input.id='param-'+key;input.type='range';input.min=min;input.max=max;input.step=step;input.value=p[key];small.textContent=help;
            const display=()=>{output.value=Number(input.value).toFixed(key==='month'?0:unit==='℃'?1:2)+' '+unit;};input.addEventListener('input',display);display();top.append(label,output);box.append(top,input,small);$('parameter-controls').append(box);
        }
    }
    function readParameters(){const value={seed:Number($('seed').value)};controls.forEach(([key])=>value[key]=Number($('param-'+key).value));return M.parameters(value);}
    function writeParameters(value){controls.forEach(([key])=>{$('param-'+key).value=value[key];$('param-'+key).dispatchEvent(new Event('input'));});$('seed').value=value.seed;}
    function applyParameters(){pause();p=readParameters();$('parameter-status').textContent='已应用参数，正在从初始环境重算至当前模拟时刻。';send(frame?.t||0,true);}
    function saveCustom(){try{localStorage.setItem(STORAGE,JSON.stringify(custom));return true;}catch(_){$('station-message').textContent='浏览器存储不可用，自定义点在本次页面中有效。';return false;}}
    function exportStation(){
        if(!frame||!series.length)return;
        const columns=['simulation_hour','station_id','station_name','longitude','latitude','temperature_C','dewpoint_C','relative_humidity_percent','sea_level_pressure_hPa','wind_speed_ms','wind_from_degrees','gust_estimate_ms','rain_rate_mm_h','past_hour_rain_mm','process_rain_mm','CAPE_J_kg','CIN_J_kg'];
        const safe=value=>{let s=String(value??'');if(/^[=+@\-\t\r]/.test(s)&&typeof value!=='number')s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
        const lines=[['TEACHING SIMULATION ONLY — NOT OBSERVATIONS'],columns];
        for(const o of series)lines.push([o.t,selected.id,selected.name,selected.lon,selected.lat,o.temp,o.dew,o.humidity,o.pressure,o.wind,o.direction,o.gust,o.rain,o.rain1h,o.total,o.cape,o.cin].map(v=>typeof v==='number'?Number(v.toFixed(3)):v));
        const blob=new Blob(['\ufeff'+lines.map(r=>r.map(safe).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`simulation-${selected.id}-${frame.t.toFixed(1)}h.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    function tick(now){
        if(playing&&!busy&&frame&&now-lastTick>200){const elapsed=Math.min(.8,(now-lastTick)/1000);lastTick=now;
            if(frame.t>=frame.duration){pause();message('完整过程已结束，可拖动时间轴回放。');}
            else send(Math.min(frame.duration,frame.t+Math.max(.1,Number($('speed').value)*elapsed)));
        }requestAnimationFrame(tick);
    }
    async function init(){
        controlsUI();buildMaps(2);
        try{const saved=JSON.parse(localStorage.getItem(STORAGE)||'[]');if(Array.isArray(saved)){const ids=new Set();custom=saved.slice(0,50).map(M.validateCustom).filter(s=>{if(!s||ids.has(s.id))return false;ids.add(s.id);return true;});}}catch(_){custom=[];}
        try{
            const response=await fetch('assets/data/simulator-stations.json');if(!response.ok)throw Error('HTTP '+response.status);
            const catalog=await response.json();national=catalog.stations.filter(s=>s.kind==='national'&&/^\d{5}$/.test(s.id)&&typeof s.name==='string'&&G.inDomain(s.lon,s.lat));
            $('station-source').textContent=`CMA 公开台站表：广东 ${national.filter(s=>s.province==='广东').length} 站 / 广西 ${national.filter(s=>s.province==='广西').length} 站。资料表元数据日期 2023-10-27，非最新完整在役名录。显示值均为模拟值。`;
        }catch(error){$('station-source').textContent='台站资料加载失败，仅提供自定义观测点。请通过网站地址或本地 HTTP 服务打开。';custom.unshift({id:'custom-reference',name:'深圳参考点',province:'自定义',kind:'custom',lon:114,lat:22.54});}
        allStations();selected=stations.find(s=>s.id==='59493')||stations[0];stationOptions();
        try{worker=new Worker('assets/scripts/simulator-worker.js?v=20261013');}
        catch(error){message('浏览器无法启动模拟，请使用支持 Web Worker 的浏览器，通过 HTTP/HTTPS 打开页面。');return;}
        worker.onerror=()=>{busy=false;pause();message('模拟线程启动失败，请刷新页面；本地预览需使用 HTTP 服务。');$('compute-progress').hidden=true;};
        worker.onmessage=({data})=>{
            if(data.request!==request)return;
            if(data.type==='progress'){$('compute-progress').value=data.value;return;}
            if(data.type==='error'){busy=false;pause();message('计算失败：'+data.message);$('compute-progress').hidden=true;return;}
            frame=data.frame;series=data.series;busy=false;$('compute-progress').hidden=true;$('play').disabled=false;$('timeline').disabled=false;
            $('parameter-status').textContent='当前场景参数已生效。所有视窗与观测使用同一模拟状态。';message('同步完成 · '+(playing?'正在播放':'已暂停，可选择图层或观测点'));updateUI();
        };
        send(0,true);requestAnimationFrame(tick);
    }
    $('play').addEventListener('click',()=>{if(!frame)return;if(playing)pause();else{if(frame.t>=frame.duration)send(0);playing=true;lastTick=performance.now();$('play').textContent='Ⅱ 暂停';}});
    $('reset').addEventListener('click',()=>{pause();send(0);});
    $('timeline').addEventListener('input',()=>{pause();send(Number($('timeline').value));});
    document.querySelectorAll('[data-time]').forEach(b=>b.addEventListener('click',()=>{pause();let time=Number(b.dataset.time);if(time>=71)time+=72/p.frontSpeed-72;send(time);}));
    document.querySelectorAll('[data-layout]').forEach(b=>b.addEventListener('click',()=>buildMaps(Number(b.dataset.layout))));
    for(const id of ['show-stations','show-fronts','show-terrain','show-labels','fold-velocity'])$(id).addEventListener('change',drawMaps);
    $('radar-elevation').addEventListener('change',()=>{radar.elevation=Number($('radar-elevation').value);drawMaps();});
    $('view-region').addEventListener('click',()=>{Object.assign(view,{lon:111.15,lat:23.25,zoom:1});drawMaps();});
    $('view-prd').addEventListener('click',()=>{Object.assign(view,{lon:113.62,lat:22.68,zoom:5.6});drawMaps();});
    $('zoom-in').addEventListener('click',()=>zoom(1.35));$('zoom-out').addEventListener('click',()=>zoom(1/1.35));
    $('add-on-map').addEventListener('click',()=>setPicking(!picking));
    $('station-search').addEventListener('input',stationOptions);$('station-select').addEventListener('change',()=>selectStation($('station-select').value));
    $('station-center').addEventListener('click',()=>{if(selected){Object.assign(view,{lon:selected.lon,lat:selected.lat,zoom:5.6});drawMaps();}});
    $('station-radar').addEventListener('click',()=>{if(selected){Object.assign(radar,{lon:selected.lon,lat:selected.lat,name:selected.name});$('radar-name').textContent='虚拟雷达：'+radar.name;drawMaps();}});
    $('station-form').addEventListener('submit',e=>{e.preventDefault();if(custom.length>=50){$('station-message').textContent='最多保存 50 个自定义点，请先删除不需要的点。';return;}
        const point=M.validateCustom({id:'custom-'+Date.now()+'-'+Math.random().toString(36).slice(2,7),name:$('custom-name').value,lon:Number($('custom-lon').value),lat:Number($('custom-lat').value)});
        if(!point){$('station-message').textContent='请输入名称和模拟范围内的有效经纬度。';return;}
        custom.push(point);const saved=saveCustom();allStations();selected=point;$('station-search').value='';stationOptions();pause();send(frame?.t||0,true);
        $('station-message').textContent='已添加观测点；正在补算从过程开始到当前时刻的完整观测记录。'+(saved?'':'浏览器存储不可用，此点仅在本次页面中有效。');
    });
    $('delete-station').addEventListener('click',()=>{if(selected?.kind!=='custom')return;if(stations.length===1){$('station-message').textContent='请先添加另一个观测点，再删除最后一个参考点。';return;}custom=custom.filter(s=>s.id!==selected.id);const saved=saveCustom();allStations();selected=national.find(s=>s.id==='59493')||stations[0];$('station-search').value='';stationOptions();pause();send(frame?.t||0,true);$('station-message').textContent='自定义点已删除。'+(saved?'':'浏览器存储不可用，无法保存本次删除。');});
    $('export-station').addEventListener('click',exportStation);
    $('parameters-form').addEventListener('submit',e=>{e.preventDefault();applyParameters();});
    $('restore-parameters').addEventListener('click',()=>{writeParameters(M.DEFAULTS);applyParameters();});
    $('flat-terrain').addEventListener('click',()=>{$('param-terrain').value=0;$('param-terrain').dispatchEvent(new Event('input'));applyParameters();});
    $('no-estuary').addEventListener('click',()=>{$('param-estuary').value=0;$('param-estuary').dispatchEvent(new Event('input'));applyParameters();});
    let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(updateUI,100);});
    document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
    document.addEventListener('keydown',e=>{if(e.key==='Escape')setPicking(false);});
    // Read-only diagnostics for reproducibility and browser regression checks.
    window.Simulator={getState:()=>({frame,selected,radar:{...radar},view:{...view},busy,playing,stationCount:stations.length,layers:views.map(v=>v.layer),series})};
    init();
})();
