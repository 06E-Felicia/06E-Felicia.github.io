'use strict';
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),zlib=require('node:zlib'),R=require('../../assets/scripts/vacation-resource.js');
(async()=>{
 const server=http.createServer((req,res)=>{if(req.url==='/stall'){res.writeHead(200);res.write('partial');return;}if(req.url==='/bad'){res.writeHead(404);res.end();return;}res.end('{"ready":true}');});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base='http://127.0.0.1:'+server.address().port;
 try{
  assert.deepEqual(await R.json(base),{ready:true});
  await assert.rejects(R.bytes(base+'/bad'),/404/);
  await assert.rejects(R.bytes(base+'/stall',{idleMs:50,timeoutMs:500}),/超时/);
  await assert.rejects(R.bytes(base,{maxBytes:2}),/大小/);
  const root=path.resolve(__dirname,'../..'),meta=JSON.parse(fs.readFileSync(path.join(root,'assets/data/vacation-terrain.json'))),packed=fs.readFileSync(path.join(root,'assets/data',meta.compressedBinary.file));
  const raw=zlib.gunzipSync(packed);assert.equal(raw.length,meta.binaryBytes);assert.equal(crypto.createHash('sha256').update(raw).digest('hex'),meta.binarySha256);assert.equal(crypto.createHash('sha256').update(packed).digest('hex'),meta.compressedBinary.sha256);
  console.log('PASS: bounded JSON/body loading, HTTP and size errors, stalled-body timeout; compressed terrain SHA256 matches original.');
 }finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
