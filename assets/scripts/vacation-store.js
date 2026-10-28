/* Complete per-round replay on disk; the decoded working set alone is bounded. */
(function(root){
  'use strict';
  const entryBytes=e=>e.buffer.byteLength+(e.windGrid?.buffer.byteLength||0)+(e.coldGrid?.buffer.byteLength||0)+(e.triggerGrid?.buffer.byteLength||0);
  const tag='__vacation_scalar__';
  const stringify=v=>JSON.stringify(v,(_k,x)=>x===undefined?{[tag]:'undefined'}:typeof x==='number'&&!Number.isFinite(x)?{[tag]:String(x)}:x);
  function revive(x){if(x&&typeof x==='object'){if(Object.keys(x).length===1&&Object.hasOwn(x,tag))return x[tag]==='undefined'?undefined:Number(x[tag]);for(const k of Object.keys(x))x[k]=revive(x[k]);}return x;}
  async function pack(metadata,parts,bytes){
    const header=new TextEncoder().encode(stringify({metadata,parts:parts.map(({path,type,buffer})=>({path,type,length:buffer.byteLength}))})),size=new Uint8Array(4);new DataView(size.buffer).setUint32(0,header.length,true);
    const blob=new Blob([size,header,...parts.map(p=>p.buffer)]);let codec='raw',payload;
    if(typeof root.CompressionStream==='function'&&typeof root.DecompressionStream==='function'){
      payload=await new Response(blob.stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer();codec='gzip';
    }else payload=await blob.arrayBuffer();
    return {format:2,codec,uncompressedBytes:blob.size,entryBytes:bytes,payload};
  }
  async function unpack(record){
    if(record.format!==2)return record; // Read existing uncompressed IndexedDB records.
    let raw=record.payload;if(record.codec==='gzip')raw=await new Response(new Blob([raw]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
    if(raw.byteLength!==record.uncompressedBytes||raw.byteLength<4)throw Error('回放帧长度不匹配');
    const length=new DataView(raw).getUint32(0,true);if(length>raw.byteLength-4)throw Error('回放帧描述损坏');
    const {metadata,parts}=revive(JSON.parse(new TextDecoder().decode(new Uint8Array(raw,4,length))));let offset=4+length;
    for(const p of parts){if(!Number.isSafeInteger(p.length)||p.length<0||offset+p.length>raw.byteLength)throw Error('回放字段长度不匹配');const buffer=raw.slice(offset,offset+p.length);offset+=p.length;let target=metadata;for(const key of p.path.slice(0,-1))target=target[key];target[p.path.at(-1)]=p.type==='Float64Array'?new Float64Array(buffer):buffer;}
    if(offset!==raw.byteLength)throw Error('回放帧包含多余字段');return metadata;
  }
  class Store {
    constructor(onFallback,databaseName='vacation-simulator'){
      this.databaseName=databaseName;this.onFallback=onFallback;this.ram=new Map();this.index=[];this.bytes=0;this.diskBytes=0;this.limit=64*1024*1024;
      this.db=null;this.cache=null;this.runId=null;this.pending=0;this.disabled=false;this.storageError=null;this.backend=null;this.nextSeq=0;this._writes=Promise.resolve();this._checkpoints=Promise.resolve();this.closed=false;
    }
    timeout(promise,abort){return new Promise((resolve,reject)=>{const t=setTimeout(()=>{abort?.();reject(Error('本机存储超时'));},8000);Promise.resolve(promise).then(v=>{clearTimeout(t);resolve(v);},e=>{clearTimeout(t);reject(e);});});}
    async database(){
      if(!root.indexedDB)throw Error('IndexedDB 不可用');let expired=false;
      this.db=await this.timeout(new Promise((resolve,reject)=>{const r=indexedDB.open(this.databaseName,1);r.onupgradeneeded=()=>{for(const name of ['frames','checkpoints'])if(!r.result.objectStoreNames.contains(name))r.result.createObjectStore(name);};r.onsuccess=()=>{if(expired)r.result.close();else resolve(r.result);};r.onerror=()=>reject(r.error);r.onblocked=()=>reject(Error('存档被另一页面占用'));}),()=>{expired=true;});
    }
    transaction(name,mode,fn){let tx;return this.timeout(new Promise((resolve,reject)=>{if(!this.db)return reject(Error('IndexedDB 不可用'));tx=this.db.transaction(name,mode);let result;try{result=fn(tx.objectStore(name));}catch(e){try{tx.abort();}catch(_){}reject(e);return;}tx.oncomplete=()=>resolve(result?.result);tx.onerror=tx.onabort=()=>reject(tx.error||Error('存储已中断'));}),()=>{try{tx?.abort();}catch(_){}});}
    async ensureCache(){if(!this.cache){if(!root.caches)throw Error('备用存储不可用');this.cache=await this.timeout(caches.open(this.databaseName+'-complete-replay-v2'));}return this.cache;}
    cacheKey(key){return new URL('__vacation_replay__/'+encodeURIComponent(this.databaseName)+'/'+encodeURIComponent(key),root.location.href).href;}
    async cachePut(key,record){const cache=await this.ensureCache();return this.timeout(cache.put(this.cacheKey(key),new Response(record.payload,{headers:{'X-Vacation-Format':String(record.format),'X-Vacation-Codec':record.codec,'X-Vacation-Size':String(record.uncompressedBytes),'X-Vacation-Bytes':String(record.entryBytes)}})));}
    async cacheGet(key){const cache=await this.ensureCache(),response=await this.timeout(cache.match(this.cacheKey(key)));if(!response)return null;return {format:Number(response.headers.get('X-Vacation-Format')),codec:response.headers.get('X-Vacation-Codec'),uncompressedBytes:Number(response.headers.get('X-Vacation-Size')),entryBytes:Number(response.headers.get('X-Vacation-Bytes')),payload:await response.arrayBuffer()};}
    async write(key,record,name='frames'){
      if(this.closed)throw Error('回放存储已关闭');
      if(this.backend==='idb')try{await this.transaction(name,'readwrite',s=>s.put(record,key));return 'idb';}catch(e){this.onFallback?.(e);}
      try{await this.cachePut(name+':'+key,record);this.backend='cache';return 'cache';}
      catch(e){this.disabled=true;this.storageError=e;throw Error('无法保存完整回放，请检查本机存储空间或网站存储权限。已保存时段仍可回看。');}
    }
    async read(key,backend,name='frames'){
      if(backend==='cache')return this.cacheGet(name+':'+key);
      if(this.db)return this.transaction(name,'readonly',s=>s.get(key));return null;
    }
    async open(runId,options={}){
      this.runId=runId;this.closed=false;
      try{await this.database();await this.transaction('frames','readwrite',s=>{s.put(true,'__storage_probe__');return s.delete('__storage_probe__');});this.backend='idb';}
      catch(e){this.db?.close();this.db=null;await this.ensureCache();await this.cachePut('__storage_probe__',{format:2,codec:'raw',uncompressedBytes:0,entryBytes:0,payload:new ArrayBuffer(0)});await this.cache.delete(this.cacheKey('__storage_probe__'));this.backend='cache';this.onFallback?.(e);}
      if(runId==='inspection')return;
      const resume=options.resume;
      if(resume?.runId&&Array.isArray(resume.index)){
        this.runId=resume.runId;this.index=resume.index.filter(e=>e.simTime<=resume.simTime).map(e=>({...e}));this.nextSeq=this.index.reduce((n,e)=>Math.max(n,e.seq+1),0);this.diskBytes=this.index.reduce((n,e)=>n+(e.storedBytes||0),0);return;
      }
      // A checkpoint must never refer to a previous round whose frames were released.
      if(this.db)await this.transaction('checkpoints','readwrite',s=>s.clear());
      if(root.caches){await this.ensureCache();await this.cache.delete(this.cacheKey('checkpoints:latest-v2'));}
      // Only starting a new round releases the previous round's frame archive.
      if(this.db)await this.transaction('frames','readwrite',s=>s.clear());
      if(root.caches){await this.ensureCache();for(const request of await this.cache.keys())if(new URL(request.url).pathname.includes('/frames%3A'))await this.cache.delete(request);}
    }
    retain(entry){
      const existing=this.ram.get(entry.seq);if(existing){this.bytes-=entryBytes(existing);this.ram.delete(entry.seq);}this.ram.set(entry.seq,entry);this.bytes+=entryBytes(entry);
      while(this.bytes>this.limit&&this.ram.size>1){const [seq,old]=this.ram.entries().next().value;this.ram.delete(seq);this.bytes-=entryBytes(old);}
    }
    put(message){
      const entry={...message,buffer:message.buffer.slice(0)};delete entry.cells;
      for(const key of ['windGrid','coldGrid','triggerGrid'])if(message[key])entry[key]={...message[key],buffer:message[key].buffer.slice(0)};
      this.pending++;
      const work=this._writes.then(async()=>{
        if(this.closed)throw Error('回放存储已关闭');const previous=this.index.at(-1),replace=previous?.simTime===entry.simTime;if(previous&&entry.simTime<previous.simTime)throw Error('回放时间顺序不匹配');entry.seq=replace?previous.seq:this.nextSeq;
        const metadata={...entry},parts=[{path:['buffer'],type:'ArrayBuffer',buffer:entry.buffer}];delete metadata.buffer;
        for(const key of ['windGrid','coldGrid','triggerGrid'])if(entry[key]){metadata[key]={...entry[key]};delete metadata[key].buffer;parts.push({path:[key,'buffer'],type:'ArrayBuffer',buffer:entry[key].buffer});}
        const bytes=entryBytes(entry),record=await pack(metadata,parts,bytes),backend=await this.write(this.runId+':'+entry.seq,record);
        if(this.closed)throw Error('回放存储已关闭');const descriptor={seq:entry.seq,simTime:entry.simTime,bytes,storedBytes:record.payload.byteLength,backend};if(replace){this.index[this.index.length-1]=descriptor;this.diskBytes-=previous.storedBytes||0;}else{this.nextSeq++;this.index.push(descriptor);}this.diskBytes+=record.payload.byteLength;this.retain(entry);return entry;
      }).finally(()=>{this.pending--;});this._writes=work.catch(()=>{});return work;
    }
    async get(seq){
      if(this.ram.has(seq)){const entry=this.ram.get(seq);this.ram.delete(seq);this.ram.set(seq,entry);return entry;}
      const descriptor=this.index.find(e=>e.seq===seq);if(!descriptor)return null;
      const record=await this.read(this.runId+':'+seq,descriptor.backend);if(!record)throw Error('该时刻的回放帧无法读取');const entry=await unpack(record);if(!this.closed)this.retain(entry);return entry;
    }
    saveCheckpoint(checkpoint){const work=this._checkpoints.then(()=>this.saveCheckpointNow(checkpoint));this._checkpoints=work.catch(()=>false);return work;}
    async saveCheckpointNow(checkpoint){
      try{
        await this._writes;if(this.closed)return false;
        const replay={runId:this.runId,version:checkpoint.version,simTime:checkpoint.t,index:this.index.filter(e=>e.simTime<=checkpoint.t).map(e=>({...e}))};
        const metadata={checkpoint:{...checkpoint,arrays:{}},replay,savedAt:Date.now()},parts=Object.entries(checkpoint.arrays).map(([key,a])=>({path:['checkpoint','arrays',key],type:'Float64Array',buffer:a.buffer.slice(a.byteOffset,a.byteOffset+a.byteLength)}));
        const record=await pack(metadata,parts,parts.reduce((n,p)=>n+p.buffer.byteLength,0));
        // Same packed record commits the physical checkpoint and its exact replay prefix.
        await this.write('latest-v2',record,'checkpoints');return true;
      }catch(e){return false;}
    }
    async latestCheckpointRecord(){
      let record=this.db?await this.transaction('checkpoints','readonly',s=>s.get('latest-v2')):null;
      if(root.caches)try{const cached=await this.cacheGet('checkpoints:latest-v2');if(cached){const value=await unpack(cached);const existing=record?await unpack(record):null;return !existing||(value.savedAt||0)>=(existing.savedAt||0)?value:existing;}}catch(e){if(!this.db)throw e;}
      if(record)return unpack(record);
      const legacy=this.db?await this.transaction('checkpoints','readonly',s=>s.get('latest')):null;return legacy?{checkpoint:legacy,replay:null}:null;
    }
    async latestCheckpoint(){return (await this.latestCheckpointRecord())?.checkpoint||null;}
    close(){this.closed=true;this.db?.close();this.db=null;this.ram.clear();this.index=[];this.bytes=0;}
  }
  root.VacationStore=Store;
})(globalThis);
