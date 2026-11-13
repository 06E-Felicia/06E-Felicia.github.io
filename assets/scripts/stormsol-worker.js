'use strict';
importScripts('stormsol-model.js?v=6','stormsol-frame.js?v=4');
let ack,active=false;
self.onmessage=async({data})=>{
  if(data.type==='ack'){ack?.();return;}
  if(data.type!=='start'||active)return;
  active=true;
  try{
    const hours=Number(data.controls.hours);
    if(!Number.isInteger(hours)||hours<1||hours>96)throw Error('过程时长须为 1–96 整小时');
    const seed=Number.isInteger(data.seed)&&data.seed>0&&data.seed<2147483647?data.seed:crypto.getRandomValues(new Uint32Array(1))[0]%2147483646+1;
    postMessage({type:'status',text:'正在载入华南地形与槽前环境…'});
    const res=await fetch('../data/stormsol-terrain.u16');if(!res.ok)throw Error('地形载入失败 '+res.status);
    const model=new StormSol.Model(seed,new Uint16Array(await res.arrayBuffer()));
    postMessage({type:'manifest',manifest:StormSolFrame.manifest(model,seed,hours)});
    const start=performance.now();let integrationMs=0,snapshotMs=0,storageMs=0;
    for(let i=0;i<=hours*6;i++){
      let time=performance.now();if(i)model.advance();integrationMs+=performance.now()-time;
      time=performance.now();const raw=JSON.stringify(StormSolFrame.snapshot(model));snapshotMs+=performance.now()-time;
      time=performance.now();const saved=new Promise(resolve=>{ack=resolve;});
      postMessage({type:'frame',index:i,hour:i/6,raw});await saved;ack=null;storageMs+=performance.now()-time;
      postMessage({type:'progress',hour:i/6,hours,elapsed:(performance.now()-start)/1000});
    }
    postMessage({type:'complete',elapsed:(performance.now()-start)/1000,timing:{integrationMs,snapshotMs,storageMs}});
  }catch(e){postMessage({type:'error',text:e.message});}
};
