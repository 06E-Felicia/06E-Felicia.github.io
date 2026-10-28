/* Compact production integration evidence, consumable by the unchanged revision analyzer. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),zlib=require('node:zlib'),crypto=require('node:crypto'),v8=require('node:v8');
const ROOT=path.resolve(__dirname,'../..'),C=require('../../assets/scripts/vacation-model.js');
const drain=it=>{let r;do{r=it.next();}while(!r.done);return r.value;};
function run(config,out){
  C.prepareBackendSync();if(fs.existsSync(out))throw Error('Evidence directory already exists: '+out);
  fs.mkdirSync(path.join(out,'frames'),{recursive:true});
  const terrain=config.geography==='real'?require('./record_vacation_replay.cjs').terrain():null;
  if(config.terrainAblation==='flat')for(const part of [terrain.fields,terrain.extended])for(const [key,a]of Object.entries(part))if(['z','zs','zx','zy','normalX','normalY','beta'].includes(key))a.fill(0);
  const m=new C.Model(config,terrain);
  const json=(p,x)=>fs.writeFileSync(path.join(out,p),JSON.stringify(x,null,2)),sha=b=>crypto.createHash('sha256').update(b).digest('hex');
  const grid=g=>({nx:g.nx,ny:g.ny,dx:g.dx,width:g.width,height:g.height,origin:[-g.width/2,-g.height/2]});
  const manifest={schema:'vacation-replay-v1',metadataCodec:'gzip-json',status:'recording',model:C.VERSION,config:m.config,physicsMesh:m.physicsMesh,productMesh:m.productMesh,physicsStepSeconds:C.DT,frameIntervalSeconds:C.DT,projection:terrain?.meta.projection||'LOCAL:XY',grids:{radar:grid(m.output),environment:grid(m.env),coldPool:grid(m.cold),rainLedger:grid(m.rain)},frames:[],sourceSha256:{}};
  for(const name of ['vacation-model.js','vacation-cold-layer.js','vacation-version.js','vacation-wasm.js','vacation-wasm-meta.js','vacation-coast.js']){const p=path.join(ROOT,'assets/scripts',name);if(fs.existsSync(p)){const b=fs.readFileSync(p);manifest.sourceSha256[name]=sha(b);fs.mkdirSync(path.join(out,'source'),{recursive:true});fs.writeFileSync(path.join(out,'source',name),b);}}
  for(const name of ['assets/wasm/vacation-numeric.wasm','assets/data/vacation-terrain.json','assets/data/vacation-coastlines.json','development/scripts/analyze_vacation_revision.py','development/scripts/vacation_replay_data.py','development/scripts/validate_vacation_training.cjs']){const b=fs.readFileSync(path.join(ROOT,name)),key=path.basename(name);manifest.sourceSha256[key]=sha(b);fs.writeFileSync(path.join(out,'source',key),b);}
  manifest.fieldEncoding='Unquantized Float32 products from the production integrator; common 4 km area mean (linear Z before dBZ).';
  const births=fs.openSync(path.join(out,'births.ndjson'),'w'),deaths=fs.openSync(path.join(out,'deaths.ndjson'),'w');let nb=0,nd=0;
  const times=[],start=performance.now();
  function save(){
    const p=drain(m.projectProducts()),fields={},parts=[];let offset=0;
    const add=(key,a,g,units)=>{const b=Buffer.from(a.buffer,a.byteOffset,a.byteLength);fields[key]={dtype:'<f4',grid:g,offset,bytes:b.length,scale:1,addOffset:0,noData:null,units};parts.push(b);offset+=b.length;};
    add('reflectivity_composite',Float32Array.from(p.compositeZ,x=>x>0?10*Math.log10(x):NaN),'radar','dBZ');
    add('reflectivity_low',Float32Array.from(p.lowZ,x=>x>0?10*Math.log10(x):NaN),'radar','dBZ');
    add('rain_rate',Float32Array.from(p.rainRate),'radar','mm/h');add('rain_total',Float32Array.from(p.rainTotal),'radar','mm');
    for(const key of ['u','v','um','vm','rhL','divL','KenvL','z','land','xiTerrain','xiConvergence','wTerrain','wConvergence','inflowFocus','lfcHeight','triggerLow'])add(key,Float32Array.from(m.fields[key]),'environment','native');
    for(const [key,a]of [['cold_depth',m.h],['cold_heat',m.q],['cold_px',m.Px],['cold_py',m.Py]])add(key,Float32Array.from(a),'coldPool','native');
    const stem=String(manifest.frames.length).padStart(4,'0'),raw='frames/'+stem+'.bin.gz',data='frames/'+stem+'.json.gz',buf=zlib.gzipSync(Buffer.concat(parts));fs.writeFileSync(path.join(out,raw),buf);
    const cells=m.cells.map(c=>Object.fromEntries(['id','x','y','born','age','source','parent','a','M','vx','vy','suppliedKgThisStep','supplied','convectivePhaseEnergyJ'].map(k=>[k,c[k]])));
    const md={schema:manifest.schema,simTime:m.t,uncompressedBytes:offset,fields,cells,sourceAccounting:m.sourceAudit(),coldKinematics:m.coldKinematicDiagnostics,frontDiagnostics:{cumulative:m.frontTotals},stats:m.stats};
    const metadata=zlib.gzipSync(JSON.stringify(md));fs.writeFileSync(path.join(out,data),metadata);manifest.frames.push({simTime:m.t,raw,data,sha256:sha(buf),metadataSha256:sha(metadata)});json('manifest.json',manifest);
    if(m.t%3600===0)console.log(JSON.stringify({out:path.basename(out),hours:m.t/3600,cells:m.cells.length,births:m.stats.births,coldBirths:m.stats.coldBirths,seconds:(performance.now()-start)/1000}));
  }
  try{
    drain(m.updateForcing());save();while(m.t<config.hours*3600){const a=performance.now();m.step();times.push(performance.now()-a);
      const born=m.stats.births-nb,died=m.stats.deaths-nd;
      if(born>m.events.length||died>m.lifeEvents.length)throw Error('Event history truncated inside one physical step');
      if(born)for(const e of m.events.slice(-born))fs.writeSync(births,JSON.stringify(e)+'\n');nb=m.stats.births;
      if(died)for(const e of m.lifeEvents.slice(-died))fs.writeSync(deaths,JSON.stringify(e)+'\n');nd=m.stats.deaths;
      if(m.t%C.DT===0||m.t>=config.hours*3600)save();
    }
    fs.writeFileSync(path.join(out,'rain-total-1km.f32.gz'),zlib.gzipSync(Buffer.from(Float32Array.from(m.rainTotal).buffer)));
    fs.writeFileSync(path.join(out,'final.checkpoint.v8.gz'),zlib.gzipSync(v8.serialize(m.checkpoint())));
    times.sort((a,b)=>a-b);const report={status:'complete',model:C.VERSION,config:m.config,steps:m.stats.steps,frames:manifest.frames.length,elapsedSeconds:(performance.now()-start)/1000,stepP50:times[Math.floor(times.length*.5)],stepP95:times[Math.floor(times.length*.95)],audit:m.check(),sourceAccounting:m.sourceAudit(),stats:m.stats,frontDiagnostics:{cumulative:m.frontTotals},backend:m.backendInfo()};
    manifest.status='complete';json('report.json',report);json('manifest.json',manifest);return report;
  }catch(e){manifest.status='failed';manifest.error=e.stack;json('manifest.json',manifest);throw e;}finally{fs.closeSync(births);fs.closeSync(deaths);}
}
if(require.main===module)run(JSON.parse(fs.readFileSync(process.argv[2])),path.resolve(process.argv[3]));
module.exports={run,drain};
