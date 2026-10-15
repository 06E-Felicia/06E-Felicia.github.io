/* Disk-backed local frames. RAM remains bounded to the viewer's two-frame cache. */
(function(root){
 'use strict';
 let opening;
 function database(){return opening||(opening=new Promise((resolve,reject)=>{const r=indexedDB.open('felicia-local-simulation-v1',1);r.onupgradeneeded=()=>r.result.createObjectStore('frames');r.onsuccess=()=>resolve(r.result);r.onerror=()=>{opening=null;reject(r.error);};}));}
 async function transact(mode,operation){const db=await database();return new Promise((resolve,reject)=>{const tx=db.transaction('frames',mode),r=operation(tx.objectStore('frames'));tx.oncomplete=()=>resolve(r.result);tx.onerror=tx.onabort=()=>reject(tx.error||Error('模拟帧存储失败'));});}
 async function putRaw(run,index,raw){const data=await new Response(new Blob([raw]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();return transact('readwrite',s=>s.put({encoding:'gzip',data},run+':'+index));}
 async function getRaw(run,index){const stored=await transact('readonly',s=>s.get(run+':'+index));if(typeof stored==='string')return stored;if(stored?.encoding!=='gzip')throw Error('本轮回看数据不可用');return new Response(new Blob([stored.data]).stream().pipeThrough(new DecompressionStream('gzip'))).text();}
 root.SimulationFrameStore={putRaw,getRaw,put:(run,index,raw)=>transact('readwrite',s=>s.put(raw,run+':'+index)),get:(run,index)=>transact('readonly',s=>s.get(run+':'+index)),remove:run=>transact('readwrite',s=>s.delete(IDBKeyRange.bound(run+':',run+':\uffff')))};
})(window);
