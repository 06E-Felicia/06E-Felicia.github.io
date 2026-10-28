'use strict';
importScripts('vacation-version.js?v='+encodeURIComponent(new URL(self.location.href).searchParams.get('v')||''));
importScripts(...['vacation-wasm-meta.js','vacation-wasm.js','vacation-cold-layer.js','vacation-coast.js','vacation-model.js','vacation-scenario.js'].map(name=>name+'?v='+VacationVersion.RESOURCE_VERSION));
const C=VacationCore, SCHEMA=1,taskChannel=new MessageChannel();taskChannel.port1.onmessage=()=>tick();
let runId=null,model=null,state='initializing',timer=null,iterator=null,phase='step',seq=0,nextOutput=0,displayTime=0,free=[],unack=new Set(),commands=[],wantPause=false,wantSave=false,lastStats=0,stepStarted=0,stepTimes=[],snapshotTimes=[],phaseStarted=0,scheduledAt=0;
const timing={maxGeneratorNextMs:0,stepComputeMs:0,snapshotComputeMs:0,queueWaitMs:0,queueSamples:0,checkpointMs:0,lastStepComputeMs:0};
const send=(type,payload={},transfer=[])=>postMessage(Object.assign({type,runId,schemaVersion:SCHEMA},payload),transfer);
async function loadTerrain(){
  const response=await fetch('../data/vacation-terrain.json',{cache:'no-cache'});if(!response.ok)throw Error('无法载入地形说明');const meta=await response.json();
  const binary=await fetch('../data/'+meta.binary+'?sha256='+encodeURIComponent(meta.binarySha256));if(!binary.ok)throw Error('无法载入真实地形');const buffer=await binary.arrayBuffer();if(buffer.byteLength!==meta.binaryBytes)throw Error('地形资源长度不匹配');
  if(crypto.subtle){const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),v=>v.toString(16).padStart(2,'0')).join('');if(digest!==meta.binarySha256)throw Error('地形资源校验失败');}
  const read=fields=>Object.fromEntries(Object.entries(fields).map(([key,spec])=>[key,new Float32Array(buffer,spec.offsetBytes,spec.count)]));return {meta,fields:read(meta.fields),extended:read(meta.extendedFields)};
}
function schedule(){if(timer===null){timer=1;scheduledAt=performance.now();taskChannel.port2.postMessage(0);}}
function ack(command,status='applied'){const applied=performance.now();send('COMMAND_ACK',{commandId:command.commandId,command:command.type,status,receivedAtWorker:command.receivedAtWorker,appliedAtWorker:applied,workerBoundaryWaitMs:applied-command.receivedAtWorker,appliedAtCompleteStep:true,workerState:state,backend:model?.backendInfo(),t_core:model?.t||0,actualEffectiveTime:model?.t||0});}
function atBoundary(){
  for(const command of commands.splice(0)){if(command.type==='UPDATE_SCENARIO'){model.update(command.controls,command.commandId);ack(command);}else if(command.type==='PAUSE'){wantPause=true;if(state!=='complete')state='paused';ack(command);}else if(command.type==='RESUME'){wantPause=false;if(state!=='complete')state='running';ack(command);}else if(command.type==='SAVE'){wantSave=true;ack(command);}}
  if(wantSave){const begin=performance.now(),checkpoint=model.checkpoint();send('CHECKPOINT',{checkpoint},Object.values(checkpoint.arrays).map(a=>a.buffer));timing.checkpointMs+=performance.now()-begin;wantSave=false;}
}
function tick(){if(scheduledAt){timing.queueWaitMs+=performance.now()-scheduledAt;timing.queueSamples++;scheduledAt=0;}timer=null;if(!model||state==='error')return;if(state==='complete'){atBoundary();return;}const start=performance.now();let completed=0;
  try{
    while(performance.now()-start<8&&completed<2){
      if(!iterator){atBoundary();if(wantPause){state='paused';return;}
        const due=seq===0||model.t>=nextOutput||model.t>=model.config.hours*3600;
        if(due){if(unack.size>=2||free.length===0){state='waiting-credit';return;}if(model.t-displayTime>Math.max(600,2*model.interval)){state='waiting-playback';return;}phase='snapshot';phaseStarted=performance.now();iterator=model.snapshot(free.pop());}
        else if(model.t>=model.config.hours*3600){state='complete';send('COMPLETE',{simTime:model.t,stats:model.stats,audit:model.audit()});return;}
        else{phase='step';timing.lastStepComputeMs=0;stepStarted=performance.now();iterator=model.advance();state='running';}
      }
      const nextBegin=performance.now(),result=iterator.next(),nextMs=performance.now()-nextBegin;timing.maxGeneratorNextMs=Math.max(timing.maxGeneratorNextMs,nextMs);if(phase==='step'){timing.stepComputeMs+=nextMs;timing.lastStepComputeMs+=nextMs;}else timing.snapshotComputeMs+=nextMs;if(!result.done)continue;iterator=null;
      if(phase==='snapshot'){const snapshot=result.value,now=performance.now();snapshotTimes.push(now-phaseStarted);if(snapshotTimes.length>1000)snapshotTimes.shift();const current=seq++;unack.add(current);send('SNAPSHOT',Object.assign(snapshot,{seq:current,grid:{nx:model.output.nx,ny:model.output.ny,dx:model.output.dx,width:model.config.width,height:model.config.height},encoding:{bytesPerPixel:8,low:{type:'Uint8',offset:-10,scale:.5,noEcho:255},composite:{type:'Uint8',offset:-10,scale:.5,noEcho:255},rain:{type:'Uint16',scale:.1,missing:65535},total:{type:'Uint32',scale:.01,missing:4294967295}},cells:model.cells.map(c=>({id:c.id,x:c.x,y:c.y,a:c.a,age:c.age,source:c.source})),weatherHour:(model.preset.hour+model.t/3600)%24}),[snapshot.buffer,snapshot.windGrid.buffer,snapshot.coldGrid.buffer,snapshot.triggerGrid.buffer]);nextOutput=(Math.floor(model.t/model.interval)+1)*model.interval;
        if(model.t>=model.config.hours*3600){state='complete';send('COMPLETE',{simTime:model.t,stats:model.stats,audit:model.audit()});return;}
      }else{stepTimes.push(performance.now()-stepStarted);if(stepTimes.length>1000)stepTimes.shift();completed++;if(model.t%(model.config.hours>24?3600:1800)===0)wantSave=true;}
      if(performance.now()-lastStats>1000){const sorted=stepTimes.slice().sort((a,b)=>a-b),p=n=>sorted[Math.min(sorted.length-1,Math.floor(sorted.length*n))]||0;send('STATS',{simTime:model.t,state,backend:model.backendInfo(),timing:{...timing,meanQueueWaitMs:timing.queueWaitMs/Math.max(1,timing.queueSamples)},pendingCommands:commands.length,stepP50:p(.5),stepP95:p(.95),stepMax:sorted.at(-1)||0,snapshotMean:snapshotTimes.reduce((a,b)=>a+b,0)/Math.max(1,snapshotTimes.length),inFlight:unack.size,bufferPool:free.length,lead:model.t-displayTime,coldSubsteps:model.stats.coldSubsteps,coldRejected:model.stats.coldRejected,rootCalls:model.stats.rootCalls});lastStats=performance.now();}
    }
    schedule();
  }catch(error){state='error';send('ERROR',{message:error.message,simTime:model?.t||0,stack:error.stack});}
}
onmessage=async({data})=>{
  if(data.type==='INIT'){
    if(model)return;runId=data.runId;const started=performance.now();try{if(data.expectedVersion&&data.expectedVersion!==C.VERSION)throw Error('页面与计算内核版本不一致，请刷新页面');send('STATUS',{message:'正在准备计算内核…'});await C.prepareBackend();if(!data.checkpoint){data.config=VacationScenario.generate(data.config,crypto.getRandomValues(new Uint32Array(1))[0]||1);}send('STATUS',{message:'正在载入华南地形…'});const terrain=data.config.geography==='idealized'?null:await loadTerrain();model=data.checkpoint?C.Model.restore(data.checkpoint,terrain):new C.Model(data.config,terrain);nextOutput=model.t;displayTime=model.t;const size=model.output.n*8;free=Array.from({length:3},()=>new ArrayBuffer(size));state='running';send('READY',{version:C.VERSION,config:model.config,physicsMesh:model.physicsMesh,productMesh:model.productMesh,projection:terrain?.meta.projection||null,terrainVersion:terrain?.meta.binarySha256||'idealized',grid:{nx:model.output.nx,ny:model.output.ny,dx:model.output.dx,width:model.config.width,height:model.config.height},simTime:model.t,initializationMs:performance.now()-started,backend:model.backendInfo()});schedule();}catch(error){state='error';send('ERROR',{message:error.message,stack:error.stack});}return;
  }
  if(data.runId!==runId||data.schemaVersion!==SCHEMA)return;
  if(data.type==='RECYCLE'){if(unack.delete(data.seq)&&data.buffer?.byteLength===model?.output.n*8&&free.length<3)free.push(data.buffer);schedule();}
  else if(data.type==='DISPLAY_PROGRESS'){displayTime=Math.max(displayTime,Math.min(model?.t||0,data.simTime));schedule();}
  else if(['PAUSE','RESUME','UPDATE_SCENARIO','SAVE'].includes(data.type)){data.receivedAtWorker=performance.now();send('COMMAND_RECEIVED',{commandId:data.commandId,command:data.type,receivedAtWorker:data.receivedAtWorker,simTime:model?.t||0,insideStep:!!iterator,applied:false});commands.push(data);if(data.type==='PAUSE')wantPause=true;if(data.type==='RESUME')wantPause=false;schedule();}
};
