/* Same Python core as Actions, isolated from the map/UI thread. */
'use strict';
const RUNTIME=new URL('../vendor/pyodide/',self.location.href).href;
importScripts('simulation-advection.js?v=3.8.0');
self.simulationAdvectionKernel=SimulationAdvection.pythonKernel;
self.simulationMoistKernel=SimulationAdvection.moistPythonKernel;
let active=false,acknowledge=null;
self.onmessage=async({data})=>{
  if(data.type==='ack'){acknowledge?.();acknowledge=null;return;}
  if(data.type!=='start'||active)return;active=true;
  const send=(type,payload={})=>self.postMessage({type,...payload});
  try{
    send('status',{text:'正在准备计算组件，首次加载可能需要稍候…'});
    importScripts(RUNTIME+'pyodide.js');
    const py=await loadPyodide({indexURL:RUNTIME});
    await py.loadPackage(['numpy','scipy']);
    await py.runPythonAsync('import numpy, scipy'); // loadPackage can report a download failure without rejecting
    const base=new URL('../../',self.location.href);
    const files=['simulation/__init__.py','simulation/core.py','simulation/coldpool.py','simulation/numerics.py','simulation/thermo.py','simulation/terrain.py','simulation/run.py','simulation/config.json','simulation/experiment.py','simulation/browser.py','assets/data/simulation-terrain.npz'];
    await Promise.all(files.map(async path=>{const response=await fetch(new URL(path,base),{cache:'no-cache'});if(!response.ok)throw Error('无法载入 '+path+' ('+response.status+')');const bytes=new Uint8Array(await response.arrayBuffer());const destination='/home/pyodide/'+path;py.FS.mkdirTree(destination.slice(0,destination.lastIndexOf('/')));py.FS.writeFile(destination,bytes);}));
    await py.runPythonAsync('from js import simulationAdvectionKernel, simulationMoistKernel\nfrom simulation.numerics import install_accelerator\nfrom simulation.thermo import install_accelerator as install_moist_accelerator\ninstall_accelerator(simulationAdvectionKernel)\ninstall_moist_accelerator(simulationMoistKernel)');
    // Fresh cryptographic seed is generated INSIDE each new worker, not on
    // page load; refreshing/replaying old results is never a new experiment.
    const seed=crypto.getRandomValues(new Uint32Array(1))[0]%2147483646+1;
    py.globals.set('browser_seed',seed);py.globals.set('browser_controls',JSON.stringify(data.controls));
    send('status',{text:'正在生成新环境与地形…'});
    const manifest=JSON.parse(await py.runPythonAsync('from simulation.browser import initialize, advance, snapshot\ninitialize(browser_seed, browser_controls)'));
    send('manifest',{manifest});
    const hours=manifest.config.hours,interval=manifest.config.frame_minutes/60;
    const targets=[];for(let hour=0;hour<hours-1e-8;hour+=interval)targets.push(hour);targets.push(hours);
    const start=performance.now();let lastProgress=0,integrationMs=0,snapshotMs=0,storageMs=0;
    for(let index=0;index<targets.length;index++){
      const hour=targets[index];py.globals.set('browser_target',hour*3600);let time=0;
      // This is an isolated Worker, not the UI thread. No artificial timer
      // between integration batches: timer throttling in background tabs must
      // not pace the physics. Frame acknowledgements still yield to messages;
      // cancellation terminates the Worker immediately from the page.
      while(time<hour*3600-1e-6){const stepStart=performance.now();time=await py.runPythonAsync('advance(browser_target)');const now=performance.now();integrationMs+=now-stepStart;if(now-lastProgress>500){send('progress',{hour:time/3600,hours,elapsed:(now-start)/1000});lastProgress=now;}}
      const snapshotStart=performance.now(),raw=await py.runPythonAsync('snapshot()');snapshotMs+=performance.now()-snapshotStart;
      // Compute the ENTIRE experiment without display pacing. Back-pressure
      // waits only for validation + disk persistence, not map rendering.
      const storageStart=performance.now(),saved=new Promise(resolve=>{acknowledge=resolve;});send('frame',{index,hour,raw});await saved;storageMs+=performance.now()-storageStart;
    }
    send('complete',{elapsed:(performance.now()-start)/1000,timing:{integrationMs,snapshotMs,storageMs}});
  }catch(error){send('error',{text:String(error.message||error)});}
};
