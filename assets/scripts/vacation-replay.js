/* File://-compatible image replay. This page never imports or runs a physics model. */
(function(){
  'use strict';
  const $=id=>document.getElementById(id),archive=window.VACATION_REPLAY;
  let index=-1,requested=0,playing=false,timer=null,revision=0,manifest=null,base=null;
  function pause(){playing=false;clearTimeout(timer);timer=null;$('replay-play').textContent='播放';}
  function path(relative){const url=new URL(relative,base);if(!url.href.startsWith(base))throw Error('归档路径无效');return url.href;}
  function stamp(t){const time=VacationVersion.simulationTime(t,manifest.config);return time.day+' '+time.clock;}
  async function seek(target){
    if(!manifest)return;requested=Math.max(0,Math.min(manifest.frames.length-1,Math.round(target)));const current=++revision,entry=manifest.frames[requested],image=new Image();
    $('replay-status').textContent='正在读取第 '+(requested+1)+' 帧…';
    try{await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('回放图像缺失：'+entry.image));image.src=path(entry.image);});
      if(current!==revision)return;index=requested;$('replay-image').src=image.src;$('replay-image').hidden=false;$('replay-slider').value=index;
      $('replay-clock').textContent=stamp(entry.simTime);$('replay-frame').textContent='第 '+(index+1)+' / '+manifest.frames.length+' 帧';$('replay-progress').textContent='已演变 '+(entry.simTime/3600).toFixed(2)+' / '+manifest.config.hours+' 小时';
      $('replay-status').textContent='正在查看已完成的实际模拟输出。';$('replay-prev').disabled=index===0;$('replay-next').disabled=index===manifest.frames.length-1;
      if(playing){if(index===manifest.frames.length-1)pause();else timer=setTimeout(()=>seek(index+1),+$('replay-speed').value);}
    }catch(error){pause();$('replay-status').textContent=error.message;}
  }
  $('replay-play').onclick=()=>{if(playing){pause();return;}playing=true;$('replay-play').textContent='暂停';seek(index>=manifest.frames.length-1?0:index+1);};
  $('replay-prev').onclick=()=>{pause();seek(index-1);};$('replay-next').onclick=()=>{pause();seek(index+1);};$('replay-slider').oninput=()=>{pause();seek(+$('replay-slider').value);};
  $('replay-speed').onchange=()=>{if(playing){clearTimeout(timer);timer=setTimeout(()=>seek(index+1),+$('replay-speed').value);}};
  document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
  try{
    manifest=archive?.manifest;base=archive?.base;
    if(!manifest||manifest.status!=='complete'||manifest.renderStatus!=='complete'||manifest.verificationStatus!=='complete'||manifest.schema!=='vacation-replay-v1')throw Error('还没有完整的回放归档，请先运行“development/launchers/生成放假模拟回放.command”。');
    if(!manifest.frames?.length||manifest.frames[0].simTime!==0||manifest.frames.at(-1).simTime!==manifest.config.hours*3600)throw Error('归档缺少起始或结束时刻。');
    $('replay-config').textContent='模型 '+manifest.model+' · '+manifest.config.hours+' 小时 · '+manifest.frames.length+' 帧 · 每 '+manifest.frameIntervalSeconds/60+' 分钟一帧 · 种子 '+manifest.config.seed;
    for(const id of ['replay-play','replay-slider','replay-next'])$(id).disabled=false;$('replay-slider').max=manifest.frames.length-1;
    for(const [name,relative]of [['AI 阅读说明','AI_REVIEW.md'],['累计雨量分布（固定 0–500 mm）',manifest.visuals.rainfall],...(manifest.visuals.rainfallDiagnostic?[['雨量诊断（固定 0–120 mm）',manifest.visuals.rainfallDiagnostic]]:[]),['过程诊断图',manifest.visuals.diagnostics],['完整视频',manifest.visuals.video],['原始归档清单','manifest.json'],['运行报告','report.json'],['站点时序','stations.csv'],['单体触发事件','births.ndjson'],...(manifest.lifecycleFiles?[['单体死亡与去向',manifest.lifecycleFiles.deaths],['强迫实际生效事件',manifest.lifecycleFiles.forcingEvents]]:[])]){const a=document.createElement('a');a.href=path(relative);a.textContent=name;a.target='_blank';a.rel='noopener';$('replay-links').append(a);}
    for(const [i,relative]of manifest.visuals.contacts.entries()){const a=document.createElement('a'),img=document.createElement('img'),label=document.createElement('span');a.href=path(relative);a.target='_blank';img.src=a.href;img.alt='第 '+(i+1)+' 个 24 小时时段的等间隔雷达时序';img.loading='lazy';label.textContent='第 '+(i+1)+' 个 24 小时时段';a.append(img,label);$('replay-contacts').append(a);}
    $('replay-video').src=path(manifest.visuals.video);$('replay-video').poster=path(manifest.frames[0].image);
    const query=new URLSearchParams(location.search),hour=Number(query.get('hour')),frame=Number(query.get('frame'));
    let target=0;if(query.has('frame')&&Number.isFinite(frame))target=frame;else if(query.has('hour')&&Number.isFinite(hour))target=manifest.frames.reduce((best,f,i)=>Math.abs(f.simTime-hour*3600)<Math.abs(manifest.frames[best].simTime-hour*3600)?i:best,0);
    seek(target);
  }catch(error){$('replay-status').textContent=error.message;}
  window.VacationReplay={getState:()=>({index,requested,playing,total:manifest?.frames?.length||0,simTime:manifest?.frames?.[index]?.simTime??null,status:manifest?.status||'missing',imageReady:!$('replay-image').hidden})};
})();
