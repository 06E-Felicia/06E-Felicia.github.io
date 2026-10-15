/* Run real-browser A/B timings sequentially, not competing with each other. */
'use strict';
const {spawnSync}=require('node:child_process'),fs=require('node:fs');
const cases=[['accurate-10',false,'10'],['compact-10',true,'10'],['accurate-30',false,'30'],['compact-30',true,'30']],results=[];
for(const [name,compact,interval]of cases){
 const env={...process.env,BENCH_INTERVAL:interval};delete env.CHECK_KERNEL;delete env.BENCH_BACKEND;delete env.BENCH_COMPACT;
 if(compact)env.BENCH_COMPACT='1';
 const child=spawnSync(process.execPath,['tests/test_simulation_performance.cjs'],{env,encoding:'utf8',timeout:650000,maxBuffer:2*1024**2});
 process.stdout.write(child.stdout||'');process.stderr.write(child.stderr||'');
 if(child.status!==0)process.exit(child.status||1);
 const match=child.stdout.match(/PASS real-WASM benchmark (\{.*\})/);
 if(!match)throw Error('Missing benchmark result: '+name);
 results.push({case:name,...JSON.parse(match[1])});
}
const output=process.env.BENCH_OUTPUT||'/private/tmp/felicia-v33-performance.json';
fs.writeFileSync(output,JSON.stringify({sequential:true,results},null,2));
console.log('SAVED',output);
