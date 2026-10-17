/* Probe disk storage BEFORE Python starts. Safari may leave IDB pending. */
(function(root){
 'use strict';
 let opening,ready,backend,cache;
 const WAIT=8000,CACHE='stormsim-frames-v2';
 function timed(promise,label,abort){return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{abort?.();reject(Error(label+'超时'));},WAIT);Promise.resolve(promise).then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});}
 function database(){if(opening)return opening;let expired=false;return opening=timed(new Promise((resolve,reject)=>{
   if(!root.indexedDB){reject(Error('IndexedDB 不可用'));return;}
   const r=indexedDB.open('felicia-local-simulation-v1',1);
   r.onupgradeneeded=()=>{if(!r.result.objectStoreNames.contains('frames'))r.result.createObjectStore('frames');};
   r.onsuccess=()=>{if(expired)r.result.close();else{r.result.onversionchange=()=>{r.result.close();opening=null;};resolve(r.result);}};
   r.onerror=()=>{expired=true;reject(r.error||Error('无法打开本机存储'));};r.onblocked=()=>{expired=true;reject(Error('本机存储被其他页面占用'));};
 }),'打开本机存储',()=>{expired=true;}).catch(e=>{opening=null;throw e;});}
 async function transact(mode,operation){const db=await database();let tx;return timed(new Promise((resolve,reject)=>{tx=db.transaction('frames',mode);const r=operation(tx.objectStore('frames'));tx.oncomplete=()=>resolve(r.result);tx.onerror=tx.onabort=()=>reject(tx.error||Error('模拟帧存储失败'));}),'保存模拟帧',()=>{try{tx?.abort();}catch(_){}});}
 const key=(run,index)=>new URL('__stormsim_frames__/'+encodeURIComponent(run)+'/'+index,location.href).href;
 async function prepare(){return ready||(ready=(async()=>{
   const probe='probe-'+crypto.randomUUID();
   try{await transact('readwrite',s=>s.put('ready',probe));if(await transact('readonly',s=>s.get(probe))!=='ready')throw Error('存储校验失败');await transact('readwrite',s=>s.delete(probe));backend='idb';}
   catch(error){
     if(!root.caches)throw Error('本机存储不可用，请退出隐私模式或允许网站存储：'+error.message);
     cache=await timed(caches.open(CACHE),'打开备用存储');const url=key(probe,0);
     await timed(cache.put(url,new Response('ready')),'检查备用存储');const check=await timed(cache.match(url),'读取备用存储');if(await check?.text()!=='ready')throw Error('备用存储校验失败');await cache.delete(url);backend='cache';
   }
   return backend;
 })().catch(e=>{ready=null;throw e;}));}
 async function encode(raw){
   if(typeof CompressionStream!=='function'||typeof DecompressionStream!=='function')return {encoding:'text',data:raw};
   try{return {encoding:'gzip',data:await timed(new Response(new Blob([raw]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer(),'压缩模拟帧')};}
   catch(_){return {encoding:'text',data:raw};}
 }
 async function put(run,index,stored){await prepare();if(backend==='idb')return transact('readwrite',s=>s.put(stored,run+':'+index));return timed(cache.put(key(run,index),new Response(typeof stored==='string'?stored:stored.data,{headers:{'X-StormSim-Encoding':typeof stored==='string'?'text':stored.encoding}})),'保存备用模拟帧');}
 async function get(run,index){await prepare();if(backend==='idb')return transact('readonly',s=>s.get(run+':'+index));const response=await timed(cache.match(key(run,index)),'读取备用模拟帧');if(!response)throw Error('本轮数据不存在');return {encoding:response.headers.get('X-StormSim-Encoding'),data:await response.arrayBuffer()};}
 async function getRaw(run,index){const stored=await get(run,index);if(typeof stored==='string')return stored;if(stored?.encoding==='text')return typeof stored.data==='string'?stored.data:new TextDecoder().decode(stored.data);if(stored?.encoding!=='gzip')throw Error('本轮回看数据不可用');return timed(new Response(new Blob([stored.data]).stream().pipeThrough(new DecompressionStream('gzip'))).text(),'解压模拟帧');}
 async function remove(run){if(!run)return;await prepare();if(backend==='idb')return transact('readwrite',s=>s.delete(IDBKeyRange.bound(run+':',run+':\uffff')));const prefix=key(run,'');for(const request of await timed(cache.keys(),'清理旧模拟帧'))if(request.url.startsWith(prefix))await timed(cache.delete(request),'清理旧模拟帧');}
 root.SimulationFrameStore={prepare,putRaw:async(run,index,raw)=>put(run,index,await encode(raw)),getRaw,put,get,remove,getBackend:()=>backend};
})(window);
