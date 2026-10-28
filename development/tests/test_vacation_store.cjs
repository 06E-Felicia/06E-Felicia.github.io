'use strict';
const assert=require('node:assert/strict');
const cachesByName=new Map();
function cache(){const data=new Map();return {data,async put(key,response){data.set(typeof key==='string'?key:key.url,response.clone());},async match(key){return data.get(typeof key==='string'?key:key.url)?.clone();},async delete(key){return data.delete(typeof key==='string'?key:key.url);},async keys(){return [...data.keys()].map(url=>({url}));}};}
globalThis.location={href:'http://localhost/Vacation.html'};globalThis.caches={async open(name){if(!cachesByName.has(name))cachesByName.set(name,cache());return cachesByName.get(name);}};
require('../../assets/scripts/vacation-store.js');const Store=globalThis.VacationStore;
function frame(i,t=i*3600,n=256){const buffer=new ArrayBuffer(n*8),wind=new ArrayBuffer(n*8),cold=new ArrayBuffer(n*16),trigger=new ArrayBuffer(n*12);new Float32Array(trigger)[0]=i+200;new Uint32Array(buffer)[0]=i;new Float32Array(wind)[0]=i+.5;new Float32Array(cold)[0]=i+100;new Float32Array(cold)[1]=NaN;return {seq:i,simTime:t,buffer,grid:{nx:n,ny:1},windGrid:{nx:n,ny:1,buffer:wind},coldGrid:{nx:n,ny:1,buffer:cold},triggerGrid:{nx:n,ny:1,buffer:trigger},special:{missing:undefined,nan:NaN,infinite:Infinity},cells:[]};}
(async()=>{
 const full=new Store(null,'store-full-test');full.limit=16384;await full.open('five-days');
 for(let i=0;i<=120;i++)await full.put(frame(i));
 assert.equal(full.index.length,121);assert.equal(full.index[0].simTime,0);assert.equal(full.index.at(-1).simTime,120*3600);assert(full.bytes<=full.limit);assert(!full.ram.has(0));
 for(const i of [0,60,120]){const f=await full.get(i);assert.equal(new Uint32Array(f.buffer)[0],i);assert.equal(new Float32Array(f.windGrid.buffer)[0],i+.5);assert.equal(new Float32Array(f.coldGrid.buffer)[0],i+100);assert(Number.isNaN(new Float32Array(f.coldGrid.buffer)[1]));assert.equal(new Float32Array(f.triggerGrid.buffer)[0],i+200);assert(Object.hasOwn(f.special,'missing'));assert.equal(f.special.missing,undefined);assert(Number.isNaN(f.special.nan));assert.equal(f.special.infinite,Infinity);}
 const source=frame(121);const owned=await full.put(source);new Uint32Array(source.buffer)[0]=999;new Float32Array(source.triggerGrid.buffer)[0]=999;assert.equal(new Float32Array(owned.triggerGrid.buffer)[0],321);assert.equal(new Uint32Array(owned.buffer)[0],121);
 console.log('PASS complete 120-hour range, lossless binary and metadata, independent ownership, bounded decoded RAM');
 const large=new Store(null,'store-large-test');large.limit=16*1024*1024;await large.open('large');
 for(let i=0;i<65;i++)await large.put(frame(i,i*300,262144));
 assert(large.index.reduce((n,e)=>n+e.bytes,0)>512*1024*1024);assert.equal(large.index.length,65);assert.equal(new Uint32Array((await large.get(0)).buffer)[0],0);assert(large.bytes<=large.limit);
 console.log('PASS more than 512 MiB raw frame data without deleting the beginning');
 const C=require('../../assets/scripts/vacation-model.js'),{physical}=require('./vacation-fixtures.cjs');const m=new C.Model({geography:'idealized',width:80000,height:80000,hours:1,seed:42,computeBackend:'js'});m.step();m.step();const cp=m.checkpoint();
 const before=new Store(null,'store-resume-test');await before.open('original');for(const t of [0,600,1200])await before.put(frame(t/600,t));assert(await before.saveCheckpoint(cp));await before.put(frame(3,1800));before.close();
 const inspect=new Store(null,'store-resume-test');await inspect.open('inspection');const saved=await inspect.latestCheckpointRecord();assert.equal(saved.replay.index.length,3);assert.deepEqual(saved.checkpoint,cp);const restored=C.Model.restore(saved.checkpoint);m.step();restored.step();physical(m,restored);inspect.close();
 const after=new Store(null,'store-resume-test');await after.open('new-worker',{resume:saved.replay});assert.equal(after.index[0].simTime,0);assert.equal(after.index.at(-1).simTime,1200);const appended=await after.put(frame(0,1800));assert.equal(appended.seq,3);await after.put(frame(1,1800));assert.equal(after.index.length,4);assert.equal(after.nextSeq,4);assert.deepEqual(after.index.map(e=>e.simTime),[0,600,1200,1800]);assert.equal(new Uint32Array((await after.get(0)).buffer)[0],0);
 console.log('PASS physical checkpoint and exact history prefix restore together, append without sequence collision');
 after.backend='idb';after.transaction=async()=>{throw Error('QuotaExceededError');};await after.put(frame(0,2400));assert.equal(after.backend,'cache');assert.equal(after.index.length,5);
 const archive=after.cache,originalPut=archive.put;archive.put=async()=>{throw Error('QuotaExceededError');};await assert.rejects(after.put(frame(0,3000)),/无法保存完整回放/);assert.equal(after.index.length,5);assert.equal((await after.get(0)).simTime,0);archive.put=originalPut;
 console.log('PASS write fallback and total storage failure retain the existing replay index');
 assert(await after.saveCheckpoint(m.checkpoint()));after.close();const fresh=new Store(null,'store-resume-test');await fresh.open('fresh-round');assert.equal(await fresh.latestCheckpointRecord(),null);assert.equal(fresh.index.length,0);fresh.close();console.log('PASS new round releases the previous checkpoint together with its history');for(const s of [full,large])s.close();
})().catch(e=>{console.error(e);process.exitCode=1;});
