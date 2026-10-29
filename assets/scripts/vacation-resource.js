/* Bounded resource reads shared by page and worker, including response bodies. */
(function(root){
 'use strict';
 async function bytes(url,{timeoutMs=120000,idleMs=20000,maxBytes=40000000,onProgress,expectedBytes,cache='default'}={}){
  const controller=new AbortController();let idle,expired=false,reader;
  const expire=()=>{expired=true;controller.abort();};
  const totalTimer=setTimeout(expire,timeoutMs),reset=()=>{clearTimeout(idle);idle=setTimeout(expire,idleMs);};reset();
  try{
   const response=await fetch(url,{signal:controller.signal,cache});if(!response.ok)throw Error('HTTP '+response.status+'：'+new URL(url,root.location?.href||'http://localhost/').pathname);
   const total=expectedBytes||Number(response.headers.get('content-length'))||0;
   if(total>maxBytes)throw Error('资源大小超出限制');
   if(!response.body){const buffer=await response.arrayBuffer();if(buffer.byteLength>maxBytes)throw Error('资源大小超出限制');onProgress?.(buffer.byteLength,total);return buffer;}
   reader=response.body.getReader();const chunks=[];let length=0;
   while(true){const {done,value}=await reader.read();if(done)break;reset();length+=value.byteLength;if(length>maxBytes)throw Error('资源大小超出限制');chunks.push(value);onProgress?.(length,total);}
   const buffer=new Uint8Array(length);let offset=0;for(const chunk of chunks){buffer.set(chunk,offset);offset+=chunk.byteLength;}return buffer.buffer;
  }catch(error){if(expired)throw Error('资源下载超时，请重试或检查网络');throw error;}
  finally{clearTimeout(totalTimer);clearTimeout(idle);controller.abort();if(reader)reader.cancel().catch(()=>{});}
 }
 async function json(url,options={}){return JSON.parse(new TextDecoder().decode(await bytes(url,{maxBytes:8000000,timeoutMs:30000,...options})));}
 const api={bytes,json};root.VacationResource=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
