/* Vacation 1.37.0 — reduced warm-sector mechanism model; no live weather input. */
(function (root) {
  'use strict';
  const Runtime=root.VacationVersion||(typeof require==='function'?require('./vacation-version.js'):null);if(!Runtime)throw Error('版本约定尚未加载');
  const VERSION=Runtime.MODEL_VERSION, DT=600, ALPHA=2.5e6/(1.15*1004), THETA=2.5;
  const ColdLayer=root.VacationColdLayer||(typeof require==='function'?require('./vacation-cold-layer.js'):null);if(!ColdLayer)throw Error('冷层算子尚未加载');
  const Numeric=root.VacationWasm||(typeof require==='function'?require('./vacation-wasm.js'):null);
  const Coast=root.VacationCoast||(typeof require==='function'?require('./vacation-coast.js'):null);
  const clip=x=>Math.max(0,Math.min(1,x)), pos=x=>Math.max(0,x), sum=a=>{let s=0;for(let i=0;i<a.length;i++)s+=a[i];return s;};
  function hash(seed,...keys){let h=seed>>>0;for(const key of keys){const s=String(key);for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);h^=h>>>13;}}return h>>>0;}
  function random(seed){let a=seed>>>0;return ()=>{a+=0x6D2B79F5;let t=a;t=Math.imul(t^t>>>15,t|1);t^=t+Math.imul(t^t>>>7,t|61);return ((t^t>>>14)>>>0)/4294967296;};}
  function poisson(mu,rng){if(mu<=0)return 0;let p=1,n=0,l=Math.exp(-mu);do{n++;p*=rng();}while(p>l);return n-1;}
  function saturation(T,m=1400,p=95000){const e=611.2*Math.exp(17.67*(T-273.15)/(T-29.65));return m*.622*e/(p-e);}
  function evaporationCapacity(w,h,q,request,alpha=ALPHA){
    const temp=e=>298-(q+alpha*e)/Math.max(1200,h+alpha*e/THETA);
    const f=e=>w+e-saturation(temp(e));
    if(f(0)>1e-8)throw Error('蒸发源入口超饱和，检查更新顺序');
    if(request<=0)return 0;
    let lo=0,hi=Math.min(request,Math.max(0,-f(0)));
    if(f(hi)<=0)return hi;
    for(let n=0;n<48;n++){const mid=(lo+hi)/2;if(f(mid)<=0)lo=mid;else hi=mid;if(hi-lo<=1e-8)return lo;}
    throw Error('联立蒸发求解未收敛');
  }
  class Grid {
    constructor(width,height,dx){this.dx=dx;this.nx=Math.round(width/dx);this.ny=Math.round(height/dx);this.n=this.nx*this.ny;this.area=dx*dx;this.width=width;this.height=height;}
    index(x,y){if(x<0||y<0||x>=this.width||y>=this.height)return -1;return Math.floor(y/this.dx)*this.nx+Math.floor(x/this.dx);}
    sample(a,x,y){const xx=Math.max(0,Math.min(this.nx-1,x/this.dx-.5)),yy=Math.max(0,Math.min(this.ny-1,y/this.dx-.5)),i=Math.floor(xx),j=Math.floor(yy),u=xx-i,v=yy-j,k=j*this.nx+i,i1=Math.min(i+1,this.nx-1),j1=Math.min(j+1,this.ny-1);return (a[k]*(1-u)+a[j*this.nx+i1]*u)*(1-v)+(a[j1*this.nx+i]*(1-u)+a[j1*this.nx+i1]*u)*v;}
  }
  const PRODUCTS={low:{dx:4000,interval:600},standard:{dx:2000,interval:600},high:{dx:1000,interval:600}};
  function validateGridExtent(width,height,dx){
    if(![width,height,dx].every(Number.isFinite)||Math.min(width,height,dx)<=0||!Number.isInteger(width/dx)||!Number.isInteger(height/dx))throw Error('域必须精确覆盖网格，不能取整错位');
  }
  function sameMesh(actual,expected){return actual&&Object.keys(actual).length===Object.keys(expected).length&&Object.keys(expected).every(k=>actual[k]===expected[k]);}
  function validateProjection(source,target){
    for(const g of [source,target]){if(!g||typeof g!=='object')throw Error('投影网格对象非法');validateGridExtent(g.width,g.height,g.dx);if(![g.nx,g.ny,g.n].every(x=>Number.isSafeInteger(x)&&x>0)||g.nx*g.dx!==g.width||g.ny*g.dx!==g.height||g.n!==g.nx*g.ny)throw Error('投影网格尺寸不一致');if(!Number.isFinite(g.area)||g.area!==g.dx*g.dx)throw Error('投影网格面积须等于dx²');if(g.origin!==undefined&&(!Array.isArray(g.origin)||g.origin.length!==2||!g.origin.every(Number.isFinite)))throw Error('投影网格原点非法');}
    const a=source.origin??[0,0],b=target.origin??[0,0];if(source.width!==target.width||source.height!==target.height||a[0]!==b[0]||a[1]!==b[1])throw Error('投影要求相同物理域和原点');
  }
  // Read-only area means of piecewise-constant cells. Scale is applied before summation.
  function* areaMeanSteps(values,source,target,scale=1){
    validateProjection(source,target);if(values.length!==source.n||!Number.isFinite(scale))throw Error('投影字段尺寸或单位非法');
    const out=new Float64Array(target.n),same=source.dx===target.dx;
    for(let j=0;j<target.ny;j++)for(let i=0;i<target.nx;i++){
      const k=j*target.nx+i;if(same)out[k]=values[k]*scale;
      else{
        const x0=i*target.dx,x1=x0+target.dx,y0=j*target.dx,y1=y0+target.dx;let value=0;
        for(let y=Math.floor(y0/source.dx);y<Math.ceil(y1/source.dx);y++)for(let x=Math.floor(x0/source.dx);x<Math.ceil(x1/source.dx);x++){
          const area=(Math.min(x1,(x+1)*source.dx)-Math.max(x0,x*source.dx))*(Math.min(y1,(y+1)*source.dx)-Math.max(y0,y*source.dx));value+=(values[y*source.nx+x]*scale)*(area/target.area);
        }out[k]=value;
      }if(k%2048===2047)yield;
    }return out;
  }
  function areaMean(values,source,target,scale=1){const it=areaMeanSteps(values,source,target,scale);let r;do{r=it.next();}while(!r.done);return r.value;}
  const CHECKPOINT_CORE_ARRAYS=['h','q','rainStep','convectiveStep','rainTotal','cvx','cvy','coutx','couty','Px','Py','coldRhsH','coldRhsQ','coldWaveLX','coldWaveRX','coldWaveLY','coldWaveRY','coldPhaseX','coldPhaseY','coldPhaseRawX','coldPhaseRawY','coldPhaseControlX','coldPhaseControlY'];
  const CHECKPOINT_STATE_KEYS=['t','initialWater','initialColdVolume','initialColdHeat','stats','controls','targets','operationLog','triggerSources','cells','events','lifeEvents','forcingEvents','forcingEventStates','frontTotals','windowTotals','coldMomentumLedger','ledger','heatBudget','convectiveEnergyBudget'];
  const CHECKPOINT_OPTIONAL_KEYS=['triggerDiagnostics','supplyDiagnostics','frontDiagnostics','windowDiagnostics','coldKinematicDiagnostics','convectiveEnergyDiagnostics','forcingInterpolation'];
  const checkpointFail=(path,reason)=>{throw Error('检查点接口 '+path+': '+reason);};
  function checkpointRecord(value,path){if(!value||Object.prototype.toString.call(value)!=='[object Object]')checkpointFail(path,'需要对象');return value;}
  function checkpointNumber(value,path,min=-Infinity){if(!Number.isFinite(value)||value<min)checkpointFail(path,'需要合法有限数值');}
  function checkpointFiniteTree(value,path,seen=new Set()){
    if(typeof value==='number'){checkpointNumber(value,path);return;}
    if(value===null||value===undefined||['string','boolean'].includes(typeof value))return;
    if(typeof value!=='object'||seen.has(value))checkpointFail(path,'非法类型或循环引用');
    if(!Array.isArray(value))checkpointRecord(value,path);seen.add(value);
    for(const key of Object.keys(value))checkpointFiniteTree(value[key],path+'.'+key,seen);seen.delete(value);
  }
  function checkpointShape(value,template,path){
    if(template===null||template===undefined)return;
    if(typeof template==='boolean'){if(typeof value!=='boolean')checkpointFail(path,'需要布尔值');return;}
    if(typeof template==='number'){checkpointNumber(value,path);return;}
    if(typeof template==='string'){if(typeof value!=='string')checkpointFail(path,'需要字符串');return;}
    if(Array.isArray(template)){if(!Array.isArray(value)||value.length!==template.length)checkpointFail(path,'数组结构不匹配');}
    else checkpointRecord(value,path);
    for(const key of Object.keys(template)){if(!Object.hasOwn(value,key))checkpointFail(path+'.'+key,'缺少必需项');checkpointShape(value[key],template[key],path+'.'+key);}
  }
  function checkpointArrayTargets(model){return Object.fromEntries([
    ...Object.entries(model.fields).map(([key,a])=>['field_'+key,a]),
    ...CHECKPOINT_CORE_ARRAYS.map(key=>[key,model[key]]),
    ...Object.entries(model.precipWater).map(([key,a])=>['precip_'+key,a])]);}
  function checkpointArray(a,length,path,min=-Infinity){
    if(!ArrayBuffer.isView(a)||Object.prototype.toString.call(a)!=='[object Float64Array]')checkpointFail(path,'需要原生Float64Array');
    if(a.length!==length)checkpointFail(path,'数组尺寸不匹配');
    for(let i=0;i<a.length;i++)checkpointNumber(a[i],path+'['+i+']',min);
  }
  function mechanismLength(key,m){
    if(/^stage_(h|q|px|py|rhs_h|rhs_q|carrier_x|carrier_y)$/.test(key))return m.cold.n;
    if(/^phase_[XY]_(validConstraint|gradientX|gradientY|normalX|normalY|fdot|alpha|UcX|UcY|rawX|rawY|usedX|usedY|normalRaw|normalUsed|projectedWaveL|projectedWaveR|residualRaw|residualUsed|oneSidedSamples|isolatedTangentSamples)$/.test(key))return key.startsWith('phase_X_')?m.cvx.length:m.cvy.length;
    const faces={wind_environment_u_face:m.eu.length,wind_environment_v_face:m.ev.length,wind_cold_u_face:m.cu.length,wind_cold_v_face:m.cv.length};
    if(Object.hasOwn(faces,key))return faces[key];
    if(/^wind_((background|jet|breeze|mesoscale|processing|total)_[uv]|G|E)$/.test(key))return m.forcing.n;
    checkpointFail('arrays.mechanism_'+key,'未知机制字段');
  }
  function validateCheckpoint(c,m){
    checkpointRecord(c.arrays,'arrays');const targets=checkpointArrayTargets(m);
    for(const [key,a]of Object.entries(targets)){
      if(!Object.hasOwn(c.arrays,key))checkpointFail('arrays.'+key,'缺少必需物理数组');
      const nonnegative=/^precip_|^field_(wl|wm|ls|qcL|qcM|h|q)$|^(q|rainStep|convectiveStep|rainTotal)$/.test(key);
      checkpointArray(c.arrays[key],a.length,'arrays.'+key,key==='h'?-1e-9:nonnegative?-1e-8:-Infinity);
    }
    for(const key of Object.keys(c.arrays))if(!Object.hasOwn(targets,key)){
      if(!key.startsWith('mechanism_')||!m.config.mechanismEvidence)checkpointFail('arrays.'+key,'未知或未启用的数组');
      checkpointArray(c.arrays[key],mechanismLength(key.slice(10),m),'arrays.'+key);
    }
    for(let k=0;k<m.cold.n;k++)if(c.arrays.q[k]>THETA*c.arrays.h[k]+1e-7)checkpointFail('arrays.q['+k+']','超出冷层比例界限');
    for(const key of CHECKPOINT_STATE_KEYS){if(!Object.hasOwn(c,key)||c[key]===undefined)checkpointFail(key,'缺少必需状态');checkpointFiniteTree(c[key],key);}
    for(const key of CHECKPOINT_OPTIONAL_KEYS)if(Object.hasOwn(c,key)){if(c[key]!==null&&c[key]!==undefined)checkpointRecord(c[key],key);checkpointFiniteTree(c[key],key);}
    checkpointShape(c.config,m.config,'config');
    for(const key of ['physicsMesh','productMesh'])if(!sameMesh(c.config[key],m[key]))checkpointFail('config.'+key,'网格元数据不匹配');
    checkpointShape(c.stats,m.stats,'stats');
    if(!Number.isSafeInteger(c.stats.steps)||c.stats.steps<0)checkpointFail('stats.steps','需要非负整数');
    if(!Number.isSafeInteger(c.t)||c.t<0||c.t!==c.stats.steps*DT||c.t>Math.ceil(m.config.hours*3600/DT)*DT)checkpointFail('t','必须是合法完整步终点并与stats.steps一致');
    for(const key of ['initialWater','initialColdVolume','initialColdHeat'])checkpointNumber(c[key],key,0);
    for(const key of ['controls','targets']){checkpointRecord(c[key],key);for(const name of ['flow','humidity'])checkpointNumber(c[key][name],key+'.'+name);}
    for(const key of ['frontTotals','windowTotals','heatBudget','convectiveEnergyBudget','coldMomentumLedger','ledger'])checkpointShape(c[key],m[key],key);
    for(const key of ['initial','initialEnvironment','initialConvective','in','out'])checkpointNumber(c.heatBudget[key],'heatBudget.'+key,0);
    const flowMap=(flows,path)=>{checkpointRecord(flows,path);for(const [name,v]of Object.entries(flows))checkpointNumber(v,path+'.'+name,0);};
    flowMap(c.heatBudget.flows,'heatBudget.flows');flowMap(c.convectiveEnergyBudget.deathByReason,'convectiveEnergyBudget.deathByReason');flowMap(c.stats.deathReasons,'stats.deathReasons');
    for(const [name,b]of Object.entries(c.ledger))flowMap(b.flows,'ledger.'+name+'.flows');
    for(const key of ['births','candidates','deaths'])if(!Number.isSafeInteger(c.stats[key])||c.stats[key]<0)checkpointFail('stats.'+key,'需要非负整数');
    for(const [key,b]of Object.entries(c.ledger)){if(!Object.hasOwn(m.ledger,key))checkpointFail('ledger.'+key,'未知水库');for(const name of ['initial','in','out'])checkpointNumber(b[name],'ledger.'+key+'.'+name,0);}
    for(const key of ['initial','sourceJ','sourceLowJ','sourceMidJ','ventilationTopJ','deathVentilationTopJ','columnBoundaryJ','updates'])checkpointNumber(c.convectiveEnergyBudget[key],'convectiveEnergyBudget.'+key,0);
    if(!Number.isSafeInteger(c.convectiveEnergyBudget.updates))checkpointFail('convectiveEnergyBudget.updates','需要整数');
    for(const key of ['triggerSources','cells','events','lifeEvents','forcingEvents','operationLog'])if(!Array.isArray(c[key]))checkpointFail(key,'需要数组');
    const sourceIds=new Set();for(const source of c.triggerSources){
      checkpointRecord(source,'triggerSources');
      if(typeof source.id!=='string'||!source.id||sourceIds.has(source.id))checkpointFail('triggerSources.id','需要唯一源ID');sourceIds.add(source.id);
      for(const key of ['x','y','activated','lastBirth'])checkpointNumber(source[key],'triggerSources.'+key,0);
      if(m.env.index(source.x,source.y)<0||source.activated>source.lastBirth||source.lastBirth>c.t)checkpointFail('triggerSources','源位置或时刻非法');
    }
    checkpointRecord(c.forcingEventStates,'forcingEventStates');
    for(const [id,state]of Object.entries(c.forcingEventStates)){checkpointRecord(state,'forcingEventStates.'+id);if(typeof state.active!=='boolean')checkpointFail('forcingEventStates.'+id+'.active','需要布尔值');if(Object.hasOwn(state,'lastActiveStep'))checkpointNumber(state.lastActiveStep,'forcingEventStates.'+id+'.lastActiveStep',0);}
    for(const key of ['forcingEvents','operationLog'])for(let i=0;i<c[key].length;i++){const e=c[key][i],p=key+'['+i+']';checkpointRecord(e,p);if(key==='forcingEvents'){if(typeof e.id!=='string'||!['activation','deactivation'].includes(e.type))checkpointFail(p,'非法强迫事件');for(const name of ['actualStepStart','scheduledStart','scheduledEnd'])checkpointNumber(e[name],p+'.'+name,0);}else{checkpointNumber(e.t,p+'.t',0);checkpointRecord(e.controls,p+'.controls');for(const name of ['flow','humidity'])checkpointNumber(e.controls[name],p+'.controls.'+name);}}
    const ids=new Set();for(let i=0;i<c.cells.length;i++){
      const cell=c.cells[i],p='cells['+i+']';checkpointRecord(cell,p);
      if(typeof cell.id!=='string'||!cell.id||ids.has(cell.id))checkpointFail(p+'.id','需要唯一真实ID');ids.add(cell.id);
      for(const key of ['born','age','T','x','y','major','minor','updraftArea','starvedSeconds','supplyRatio','a','M','layer','angle','phase','convectivePhaseEnergyJ'])checkpointNumber(cell[key],p+'.'+key);
      for(const key of ['born','age','updraftArea','starvedSeconds','supplyRatio','convectivePhaseEnergyJ'])checkpointNumber(cell[key],p+'.'+key,0);
      if(cell.T<=0||cell.major<=0||cell.minor<=0||cell.M< -1e-7||![0,1].includes(cell.layer))checkpointFail(p,'非法单体尺度/质量/层');
      if(typeof cell.source!=='string'||cell.retired)checkpointFail(p+'.source','非法在生单体状态');
      if(m.config.convectiveHeating==='local_latent'&&cell.convectivePhaseEnergyJ!==0)checkpointFail(p+'.convectivePhaseEnergyJ','local_latent必须为0');
      checkpointShape(cell.convectiveEnergyStep,{at:null,sourceJ:0,latentConvertedJ:0,suppliedLowKg:0,suppliedMidKg:0,ventilationTopJ:0,deathVentilationTopJ:0,columnBoundaryJ:0,tauSeconds:null,tauSource:null,arithmeticResidualJ:0},p+'.convectiveEnergyStep');
      for(const key of ['at','tauSeconds'])if(cell.convectiveEnergyStep[key]!==null)checkpointNumber(cell.convectiveEnergyStep[key],p+'.convectiveEnergyStep.'+key,0);
      if(cell.convectiveEnergyStep.tauSource!==null&&typeof cell.convectiveEnergyStep.tauSource!=='string')checkpointFail(p+'.convectiveEnergyStep.tauSource','非法周转来源');
      for(const key of ['sourceJ','latentConvertedJ','suppliedLowKg','suppliedMidKg','ventilationTopJ','deathVentilationTopJ','columnBoundaryJ'])checkpointNumber(cell.convectiveEnergyStep[key],p+'.convectiveEnergyStep.'+key,0);
      if(m.config.cellLifecycle==='pulse'&&(c.t>0||cell.pulse!==undefined)){
        checkpointShape(cell.pulse,{Hc:0,Nend:0,Ngrow:0,Ndecay:0,N:0,L:0,wturn:0},p+'.pulse');
        for(const key of ['Hc','Nend','Ngrow','Ndecay'])if(cell.pulse[key]<=0)checkpointFail(p+'.pulse.'+key,'需要正值');
        for(const key of ['N','L','wturn'])checkpointNumber(cell.pulse[key],p+'.pulse.'+key,0);
      }
      if(c.t>0&&cell.born<c.t)for(const key of ['vx','vy','updraftVelocity','requestedKgThisStep','suppliedKgThisStep','suppliedLKgThisStep','suppliedMKgThisStep','lastSupplyStepEnd'])checkpointNumber(cell[key],p+'.'+key);
    }
    for(const key of ['events','lifeEvents'])for(let i=0;i<c[key].length;i++){
      const e=c[key][i],p=key+'['+i+']';checkpointRecord(e,p);if(typeof e.id!=='string')checkpointFail(p+'.id','需要ID');for(const name of ['t','x','y'])checkpointNumber(e[name],p+'.'+name);
      if(e.convectiveHeating!==m.config.convectiveHeating)checkpointFail(p+'.convectiveHeating','缺少或不匹配的能量模式');
      if(key==='events'){for(const name of ['initialMassKg','initialConvectivePhaseEnergyJ'])checkpointNumber(e[name],p+'.'+name,0);}
      else{if(e.type!=='death'||typeof e.reason!=='string')checkpointFail(p+'.reason','非法死亡事件');checkpointShape(e.transfer,{destination:'',massKg:0},p+'.transfer');checkpointNumber(e.transfer.massKg,p+'.transfer.massKg',0);checkpointShape(e.convectiveEnergyTransfer,{joules:0,units:'',process:'',destination:'',mode:''},p+'.convectiveEnergyTransfer');const v=e.convectiveEnergyTransfer;checkpointNumber(v.joules,p+'.convectiveEnergyTransfer.joules',0);if(v.units!=='J'||v.mode!==m.config.convectiveHeating||v.process!==(e.reason==='domain_exit'?'convectiveColumnBoundary':'convectiveDeathVentilationTop'))checkpointFail(p+'.convectiveEnergyTransfer','非法能量去向');}
    }
    return targets;
  }
  function validateRestoredInventories(m){
    const a=m.sourceAudit(),within=(residual,initial,inventory,activity,path,tol=1e-7)=>{if(!Number.isFinite(residual)||Math.abs(residual)>8*Number.EPSILON*Math.max(1,Math.abs(initial),Math.abs(inventory))+tol*Math.max(1,activity))checkpointFail(path,'只读库存/来源账不一致');};
    for(const key of Object.keys(m.ledger)){const b=a[key];within(b.residual,b.initial,b.inventory,b.in+b.out,'ledger.'+key);}
    const total=m.audit();within(total.residual,total.expected,total.water,m.stats.condensed+m.stats.evaporated+m.stats.ground+m.stats.inflow+m.stats.outflow+m.stats.surface,'initialWater/stats');
    within(total.coldVolumeResidual,m.initialColdVolume,sum(m.h)*m.cold.area,Math.abs(m.stats.coldVolumeSource)+Math.abs(m.stats.coldVolumeLoss),'initialColdVolume/stats');
    within(total.coldHeatResidual,m.initialColdHeat,sum(m.q)*m.cold.area,Math.abs(m.stats.coldHeatSource)+Math.abs(m.stats.coldHeatLoss),'initialColdHeat/stats');
    const h=a.heat;within(h.residual,h.initial,h.inventory,h.in+h.out+h.phaseHeating+h.phaseCooling,'heatBudget');
    for(const [name,b]of [...Object.entries(m.ledger),['heatBudget',m.heatBudget]])for(const direction of ['in','out']){let recorded=0;for(const [flow,value]of Object.entries(b.flows)){if(!/:(in|out)$/.test(flow))checkpointFail(name+'.flows.'+flow,'非法流量方向');if(flow.endsWith(':'+direction))recorded+=value;}within(recorded-b[direction],0,b[direction],b.in+b.out,name+'.flows.'+direction);}
    within(a.total.groundSumResidual,0,m.stats.ground,m.stats.ground,'stats.sources.ground');
    const e=a.convectiveEnergy;within(e.residual,e.initial,e.inventory,e.activity,'convectiveEnergyBudget',1e-8);
    const p=a.coldMomentum;for(const key of ['x','y'])within(p.residual[key],m.coldMomentumLedger.initial[key],p.inventory[key],m.coldMomentumLedger.transportActivity+m.coldMomentumLedger.sourceActivity,'coldMomentumLedger.'+key);
  }
  const PRESETS={monsoon:{hour:0,rhL:.9,rhM:.75,eL:.8,eM:.6,iL:4,iM:8,day:2,night:2},coast:{hour:22,rhL:.92,rhM:.82,eL:.85,eM:.65,iL:2,iM:5,day:1.5,night:2},hills:{hour:0,rhL:.94,rhM:.85,eL:.90,eM:.65,iL:2,iM:6,day:1,night:2.5},afternoon:{hour:11,rhL:.84,rhM:.72,eL:.5,eM:.45,iL:4,iM:10,day:3,night:0},decay:{hour:0,rhL:.94,rhM:.85,eL:.90,eM:.65,iL:2,iM:6,day:1,night:2.5}};
  class Model {
    constructor(config={},terrain=null){
      this.config=Object.assign({seed:104729,preset:'coast',quality:'standard',hours:6,geography:'real',width:960000,height:720000,controls:{flow:1,humidity:0},surfaceAccessMode:'consistent',cellLifecycle:'pulse',boundaryInitiationMode:'flux',boundaryFluxEfficiency:.05,coldDynamics:'inertial',frontClosure:'head_work',coldDampingSeconds:900,frontKinematics:'levelset_2d',coastalWindModel:'finite_jet',mechanismEvidence:false,convectiveHeating:'carried_export'},config);
      if(this.config.geography==='real'&&terrain){this.config.width=config.width??terrain.meta.nx*terrain.meta.dx;this.config.height=config.height??terrain.meta.ny*terrain.meta.dy;if(this.config.width!==terrain.meta.nx*terrain.meta.dx||this.config.height!==terrain.meta.ny*terrain.meta.dy)throw Error('模拟域与真实地形尺寸不一致');}
      this.config.initiationModel??='focused_lift';
      this.config.persistentInitiation??=this.config.initiationModel==='focused_lift';
      this.config.weatherRegion??='auto';
      this.config.jetExitControl??=this.config.geography==='real'&&this.config.preset==='monsoon';
      this.config.jetExitGeometry??='coast_following';
      this.config.upstreamSourceBlocking??=this.config.jetExitControl;
      this.config.longTrainingPulse??=this.config.jetExitControl;
      this.config.connectedTrainingFeed??=this.config.jetExitControl;
      this.config.directionalCoastalTrigger??=this.config.jetExitControl;
      this.config.monsoon925??=this.config.jetExitControl;
      this.config.terrainBoundTrigger??=this.config.jetExitControl;
      this.config.boundedMonsoon??=this.config.monsoon925;
      this.config.hillJetBraking??=this.config.monsoon925;
      this.config.slowMonsoonTurn??=this.config.monsoon925;
      this.config.trainingInflowFan??=this.config.monsoon925;
      this.config.stratiformOutflow??=this.config.monsoon925;
      this.config.organizedWarmSector??=this.config.monsoon925;
      if(this.config.windTurnStart!==undefined&&!['west','south'].includes(this.config.windTurnStart))throw Error('季风开场方向非法');
      if(this.config.monsoon925&&config.coldDampingSeconds===undefined)this.config.coldDampingSeconds=21600;
      this.config.coldVolumeMixingSeconds??=this.config.monsoon925?64800:5400;
      this.config.coldThermalMixingSeconds??=this.config.monsoon925?64800:3600;
      this.config.coldHorizontalMixing??=this.config.monsoon925?60000:0;
      if(!Number.isFinite(this.config.coldHorizontalMixing)||this.config.coldHorizontalMixing<0||this.config.coldHorizontalMixing>100000)throw Error('冷层水平混合参数非法');
      for(const key of ['coldVolumeMixingSeconds','coldThermalMixingSeconds'])if(!Number.isFinite(this.config[key])||this.config[key]<=0)throw Error('冷层耗散参数非法 '+key);
      if(!['auto','guangxi','west_guangdong','pearl_river','east_guangdong'].includes(this.config.weatherRegion))throw Error('天气区域非法');
      this.config.varyMonsoonDirection??=true;
      this.config.terrainSteering??=this.config.geography==='real'&&this.config.preset==='monsoon';
      this.config.diurnalBoundaryLayer??=this.config.geography==='real'&&this.config.preset==='monsoon';
      if(!['focused_lift','area_lift'].includes(this.config.initiationModel))throw Error('对流触发模式非法');
      this.config.coldMomentumCoupling??='surface_drag';
      this.config.coldSourceGeometry??='rain_footprint';
      // Preserve the existing wind geometry. Curved coast is an explicit experiment;
      // the fixed-seed audit did not establish a regeneration improvement.
      this.config.coastalConvergenceGeometry??='planar';
      if(!['ambient_relative','surface_drag'].includes(this.config.coldMomentumCoupling)||!['environment_mean','rain_footprint'].includes(this.config.coldSourceGeometry))throw Error('冷池源或动量耦合模式非法');
      if(!['planar','curvilinear'].includes(this.config.coastalConvergenceGeometry))throw Error('沿岸辐合几何模式非法');
      if(!PRESETS[this.config.preset])throw Error('未知天气预设');
      if(!['low','standard','high'].includes(this.config.quality))throw Error('未知数值档位');
      if(!Number.isInteger(this.config.seed)||!Number.isFinite(this.config.hours)||this.config.hours<=0||this.config.hours>120)throw Error('种子或时长无效');
      if(!['legacy','consistent'].includes(this.config.surfaceAccessMode)||!['legacy','pulse'].includes(this.config.cellLifecycle))throw Error('未知地面访问或生命周期模式');
      if(!['area','flux'].includes(this.config.boundaryInitiationMode)||!Number.isFinite(this.config.boundaryFluxEfficiency)||this.config.boundaryFluxEfficiency<0||this.config.boundaryFluxEfficiency>.1)throw Error('边界新生模式或效率非法');
      if(!['legacy','inertial'].includes(this.config.coldDynamics)||!['point','head_work'].includes(this.config.frontClosure)||!Number.isFinite(this.config.coldDampingSeconds)||this.config.coldDampingSeconds<0)throw Error('冷层动力或头部闭合参数非法');
      if(!['face_1d','levelset_2d'].includes(this.config.frontKinematics)||!['legacy','finite_jet'].includes(this.config.coastalWindModel))throw Error('轮廓或沿岸风场模式非法');
      if(!['local_latent','carried_export'].includes(this.config.convectiveHeating))throw Error('对流加热模式非法');
      this.terrain=terrain;this.preset=PRESETS[this.config.preset];if(this.config.preset==='monsoon'){const r=random(hash(this.config.seed,'monsoon-environment'));this.monsoon=this.config.environment||{hour:Math.floor(r()*24),rhL:.79+.17*r(),rhM:.62+.25*r(),eL:.5+.45*r(),eM:.35+.4*r(),iL:1+8*r(),iM:4+12*r(),day:1+2.5*r(),night:1+2.5*r(),baseV:6+7*r(),nightBoost:1+5*r(),axisAngle:(15+60*r())*Math.PI/180,axisX:-160000+320000*r(),axisY:-200000+140000*r(),width:80000+100000*r(),end:200000+280000*r(),endWidth:50000+60000*r(),steerSpeed:6+9*r(),steerOffset:(-25+45*r())*Math.PI/180,dayHeating:.05+.2*r()};if(!this.config.environment){const group=this.config.scenarioGroup||'coastal',p=this.monsoon;if(group==='coastal'){p.hour=22;p.rhL=.92;p.rhM=.81;p.iL=2.5;p.iM=7;p.steerOffset=-.45;p.steerSpeed=9;}else if(group==='terrain'){p.hour=2;p.rhL=.91;p.rhM=.80;p.iL=3;p.steerSpeed=6;p.width=140000;}else if(group==='afternoon'){p.hour=11;p.rhL=.86;p.rhM=.70;p.iL=4;p.dayHeating=.25;p.nightBoost=1;}else if(group==='fastline'){p.hour=20;p.rhL=.92;p.rhM=.82;p.iL=2;p.steerSpeed=17;p.steerOffset=.1;p.baseV=14;}}if(this.config.slowMonsoonTurn&&!this.config.environment){const turn=random(hash(this.config.seed,'three-day-wind-turn'));const startsWest=this.config.windTurnStart?this.config.windTurnStart==='west':turn()<.5;this.monsoon.axisAngle=(startsWest?15+5*turn():70+5*turn())*Math.PI/180;}if(this.config.organizedWarmSector&&!this.config.environment&&['coastal','terrain'].includes(this.config.scenarioGroup||'coastal')){const energy=random(hash(this.config.seed,'warm-sector-energy'));this.monsoon.eL=.84+.1*energy();this.monsoon.eM=.70+.1*energy();}const mr=random(hash(this.config.seed,'independent-midwind')),group=this.config.scenarioGroup||'coastal';this.monsoon.midDirection??=(group==='coastal'?10+35*mr():group==='terrain'?10+35*mr():group==='fastline'?-10+45*mr():360*mr())*Math.PI/180;this.monsoon.midSpeed??=(group==='fastline'?14+6*mr():6+8*mr());this.monsoon.hour=this.config.startHour??20;this.config.calendarOrigin??='previous_day';this.preset=this.monsoon;this.config.environment=Object.assign({},this.monsoon);this.config.startHour=this.monsoon.hour;}else this.config.startHour=this.preset.hour;this.t=0;this.triggerSources=[];this.cells=[];this.events=[];this.lifeEvents=[];this.forcingEvents=[];this.forcingEventStates={};this.operationLog=[];
      const product=PRODUCTS[this.config.quality],w=this.config.width,h=this.config.height;
      for(const dx of [5000,2500,2000,1000,product.dx])validateGridExtent(w,h,dx);
      this.interval=this.config.outputInterval??product.interval;
      if(!Number.isInteger(this.interval)||this.interval<DT||this.interval%DT!==0)throw Error('产品输出间隔须为600秒的正整数倍');
      this.physicsMesh={schema:'vacation-physics-mesh-1.12',lengthUnit:'m',timeUnit:'s',width:w,height:h,environmentDx:5000,coldDx:2500,forcingDx:2500,precipitationDx:2000,rainLedgerDx:1000,coreStepSeconds:DT};
      this.productMesh={schema:'vacation-product-mesh-1.12',lengthUnit:'m',quality:this.config.quality,width:w,height:h,dx:product.dx,intervalSeconds:this.interval,reconstruction:'piecewise_constant_linear_Z_area_mean'};
      for(const name of ['physicsMesh','productMesh']){if(this.config[name]&&!sameMesh(this.config[name],this[name]))throw Error('网格元数据不兼容 '+name);this.config[name]={...this[name]};}
      this.env=new Grid(w,h,5000);this.cold=new Grid(w,h,2500);this.forcing=new Grid(w,h,2500);this.precip=new Grid(w,h,2000);this.rain=new Grid(w,h,1000);this.output=new Grid(w,h,product.dx);
      this.fields={};for(const key of ['wl','wm','ls','el','em','xiL','xiM','rhL','rhM','sl','sm','q','h','z','zx','zy','land','u','v','upperDiv','tl','tm','qcL','qcM','um','vm','divL','airLM','airTop','KenvL','KenvM','CINL','CINM','coldFraction','warmAccessibleFraction','supplyCapL','supplyCapM','supplyUsedL','supplyUsedM','xiTerrain','xiConvergence','wTerrain','wConvergence','terrainRise','inflowFocus','lfcHeight','triggerLow','triggerMid'])this.fields[key]=new Float64Array(this.env.n);
      this.fields.warmAccessibleFraction.fill(1);
      this.h=new Float64Array(this.cold.n);this.q=new Float64Array(this.cold.n);this.cz=new Float64Array(this.cold.n);this.Px=new Float64Array(this.cold.n);this.Py=new Float64Array(this.cold.n);this.coldRhsH=new Float64Array(this.cold.n);this.coldRhsQ=new Float64Array(this.cold.n);
      this.rainStep=new Float64Array(this.rain.n);this.convectiveStep=new Float64Array(this.rain.n);this.rainTotal=new Float64Array(this.rain.n);
      this.eu=new Float64Array((this.env.nx+1)*this.env.ny);this.ev=new Float64Array(this.env.nx*(this.env.ny+1));this.cu=new Float64Array((this.cold.nx+1)*this.cold.ny);this.cv=new Float64Array(this.cold.nx*(this.cold.ny+1));
      this.cvx=new Float64Array(this.cu.length);this.cvy=new Float64Array(this.cv.length);this.coutx=new Float64Array(this.cu.length);this.couty=new Float64Array(this.cv.length);
      for(const [axis,n]of [['X',this.cu.length],['Y',this.cv.length]])for(const name of ['coldWaveL','coldWaveR','coldPhase','coldPhaseRaw','coldPhaseControl'])this[name+axis]=new Float64Array(n);
      this.mechanismFields={};this.windowDiagnostics=null;this.windowTotals={steps:0,seconds:0,windows:{}};this._buffers=new Map();this.boundaries=new Map();this.fronts=[];this.frontSegments=[];this.frontIndex=new Map();this.frontDiagnostics=null;this.frontTotals={steps:0,seconds:0,global:this._frontStat(),local:this._frontStat(),blocks:{}};this.activeRain=new Set();this.stats={births:0,candidates:0,environmentAccepted:0,spacingRejected:0,coldBirths:0,elevatedBirths:0,condensed:0,evaporated:0,ground:0,inflow:0,outflow:0,surface:0,coldVolumeSource:0,coldHeatSource:0,coldVolumeLoss:0,coldHeatLoss:0,coldSubsteps:0,coldRejected:0,maxStability:0,rootCalls:0,steps:0,maxRain:0,maxCells:0,repair:0,deaths:0,deathReasons:{}};
      const rng=random(hash(this.config.seed,'environment'));this.perturb={flow:.9+.2*rng(),humidity:-.02+.04*rng(),energy:-.05+.1*rng()};
      this.controls=Object.assign({flow:1,humidity:0},this.config.controls);this.targets=Object.assign({},this.controls);
      this._initTerrain();this._buildTerrainAnchors();this._buildTerrainSteering();this._normalizeCoastalWind();this._configureCoastalGeometry();this._configureCoastalWind();this._configureCurvedCoast();this._configureMesoscaleForcing();const bg=this.background();
      for(let i=0;i<this.env.n;i++){this.fields.tl[i]=298;this.fields.tm[i]=283;this.fields.sl[i]=saturation(298);this.fields.sm[i]=saturation(283,2600,75000);this.fields.wl[i]=clip(bg.rhL)*this.fields.sl[i];this.fields.wm[i]=clip(bg.rhM)*this.fields.sm[i];this.fields.el[i]=clip(bg.eL+this.perturb.energy);this.fields.em[i]=clip(bg.eM+this.perturb.energy);}
      for(let k=0;k<this.env.n;k++){const f=this.fields;f.rhL[k]=f.wl[k]/f.sl[k];f.rhM[k]=f.wm[k]/f.sm[k];f.CINL[k]=bg.iL+20*clip((.75-f.rhL[k])/.25);f.CINM[k]=bg.iM+20*clip((.65-f.rhM[k])/.25);}
      this.stats.sources={environmentCondensed:0,environmentEvaporated:0,cellCondensed:0,cellEvaporated:0,detrainedEvaporated:0,cellGround:0,detrainedGround:0,detrained:0,topIn:0,topOut:0,latentHeating:0,latentCooling:0};this.precipWater={};for(const key of ['qa','upper_core','lower_core','upper_detrained','lower_detrained','upper_boundary','lower_boundary'])this.precipWater[key]=new Float64Array(this.precip.n);this.initialWater=this.water();this.initialColdVolume=0;this.initialColdHeat=0;this.captureInitialState();if(this.config.geography==='real'&&this.config.coastalWindModel==='finite_jet'&&this.coastalGeometry)this._verifyCoastalInitialField();this._numericBackend=Numeric.create(this);this._backendStatus=this.config.computeBackend==='js'?{...Numeric.getStatus(),backend:'js',reason:'explicit JS reference'}:Numeric.getStatus();
    }
    buffer(key,n){let a=this._buffers.get(key);if(!a||a.length!==n){a=new Float64Array(n);this._buffers.set(key,a);}return a;}
    background(at=this.t){const p=this.preset,hour=(p.hour+at/3600)%24,N=.5*(1+Math.cos(2*Math.PI*(hour-4)/24)),D=Math.max(0,Math.sin(Math.PI*(hour-6)/12)),fade=clip((at-7200)/3600);let V=this.config.preset==='monsoon'?p.baseV+p.nightBoost*N:this.config.preset==='coast'?9+5*N:this.config.preset==='afternoon'?7:8+3*N;let eL=this.config.preset==='afternoon'?.5+.3*D:this.config.preset==='monsoon'?clip(p.eL+(p.dayHeating||.12)*D):p.eL;const nightHumidity=this.config.organizedWarmSector ? .10*(N-1) : 0;let rhL=p.rhL+nightHumidity;if(this.config.preset==='decay'){V=V*(1-fade)+4*fade;eL=eL*(1-fade)+.4*fade;rhL=rhL*(1-fade)+.72*fade;}let synoptic={flow:1,humidity:0,energy:0};if(this.config.hours>24){const span=21600,index=Math.floor(at/span),u=at/span-index,s=u*u*(3-2*u),a=random(hash(this.config.seed,'synoptic',index)),b=random(hash(this.config.seed,'synoptic',index+1)),blend=(lo,hi)=>{const av=lo+(hi-lo)*a(),bv=lo+(hi-lo)*b();return av+(bv-av)*s;};synoptic={flow:blend(.75,1.2),humidity:blend(-.05,.025),energy:blend(-.12,.05),axisAngle:blend(-.17,.17),axisOffset:blend(-80000,80000),axisEnd:blend(-50000,50000)};eL=clip(eL+synoptic.energy);}let axis=null;if(this.monsoon){const angle=p.axisAngle+(this.coastalGeometry?0:synoptic.axisAngle||0),ex=Math.cos(angle),ey=Math.sin(angle),shift=this.coastalGeometry?0:synoptic.axisOffset||0;axis={ex,ey,x:p.axisX-ey*shift,y:p.axisY+ex*shift,width:p.width,end:p.end+(this.coastalGeometry?0:synoptic.axisEnd||0),endWidth:p.endWidth};}return {atSeconds:at,N,D,axis,windAngle:this._monsoonAngle(at),V:V*this.perturb.flow*this.controls.flow*synoptic.flow*(this.coastalGeometry?this._coastalEnvelope(at,'supplyEndSeconds'):1),exitEnvelope:this.coastalGeometry?(this.coastalGeometry.options.disableExit?0:this._coastalEnvelope(at,'forcingEndSeconds')):1,eL,eM:clip(p.eM+synoptic.energy),rhL:clip(rhL+this.perturb.humidity+this.controls.humidity+synoptic.humidity),rhM:clip(p.rhM+.5*nightHumidity+this.perturb.humidity+this.controls.humidity+synoptic.humidity),iL:p.iL+(this.config.inhibitionOffset||0),iM:p.iM+(this.config.inhibitionOffset||0)};}
    _ideal(x,y){const a=(x/1000-320)/45,b=(y/1000-300)/20,c=(x/1000-450)/55,d=(y/1000-330)/25;return 400*Math.exp(-a*a-b*b)+600*Math.exp(-c*c-d*d);}
    _initTerrain(){
      const f=this.fields,fg=this.forcing,real=this.config.geography==='real';if(real&&!this.terrain)throw Error('真实地形资源尚未就绪');
      const fine={};for(const key of ['z','land','zs','zx','zy'])fine[key]=new Float64Array(fg.n);
      for(let j=0;j<fg.ny;j++)for(let i=0;i<fg.nx;i++){const k=j*fg.nx+i,x=(i+.5)*fg.dx,y=(j+.5)*fg.dx;if(real){for(const key of Object.keys(fine))fine[key][k]=this.terrain.fields[key][k];}else{const proto=this.config.coastalPrototype,coastY=typeof proto==='object'?(proto.coastY??this.config.height*.45):this.config.height*.45;fine.z[k]=fine.zs[k]=proto?0:this._ideal(x,y);fine.zx[k]=proto?0:(this._ideal(x+1250,y)-this._ideal(x-1250,y))/2500;fine.zy[k]=proto?0:(this._ideal(x,y+1250)-this._ideal(x,y-1250))/2500;fine.land[k]=y>=(proto?coastY:240000)?1:0;}}
      this.geometry=fine;for(const key of ['z','land','zx','zy'])this.aggregate(fine[key],fg,f[key],this.env);this.aggregate(fine.z,fg,this.cz,this.cold);
      if(real){const dx=this.terrain.meta.jetDirection||[.47,.88];this.jetDirection=dx;}else this.jetDirection=[0,1];
    }
    aggregate(source,sg,target,tg){const r=Math.round(tg.dx/sg.dx);if(r<1)throw Error('不可用的网格聚合');for(let j=0;j<tg.ny;j++)for(let i=0;i<tg.nx;i++){let value=0;for(let b=0;b<r;b++)for(let a=0;a<r;a++)value+=source[(j*r+b)*sg.nx+i*r+a];target[j*tg.nx+i]=value/(r*r);}}
    *updateForcing(at=this.t){
      const fg=this.forcing,bg=this.background(at),real=this.config.geography==='real',geo=real?this.terrain.extended:null,meta=real?this.terrain.meta:null;
      const mesoEvents=this.mesoscaleAt(at);
      const halo=6,offset=real?meta.extended.haloCells-halo:0,nx=real?fg.nx+2*halo:fg.nx,ny=real?fg.ny+2*halo:fg.ny,n=nx*ny;
      const rawU=this.buffer('forceRawU',n),rawV=this.buffer('forceRawV',n),u=this.buffer('fineU',fg.n),v=this.buffer('fineV',fg.n);
      const finite=this.coastalGeometry&&this.config.coastalWindModel==='finite_jet',sample=this.buffer('finiteWindSample',18),parts=this.config.mechanismEvidence?Object.fromEntries(['background_u','background_v','jet_u','jet_v','breeze_u','breeze_v','mesoscale_u','mesoscale_v','processing_u','processing_v','G','E'].map(key=>[key,this.buffer('windPart'+key,n)])):null;let blurWeights=null;
      for(let j=0;j<ny;j++){for(let i=0;i<nx;i++){const k=j*nx+i;if(real){if(finite){this._realFiniteRaw(i-halo,j-halo,bg,mesoEvents,sample);rawU[k]=sample[0];rawV[k]=sample[1];this._putWindParts(parts,k,sample[2],sample[3],sample[4],sample[5],sample[6],sample[7],sample[8],sample[9],sample[16],sample[17],sample[10],sample[11]);}else{const geoIndex=(j+offset)*meta.extended.nx+i+offset;const land=geo.ls[geoIndex],distance=Math.max(geo.signedDistance[geoIndex],0),rough=1-.4*land*(1-Math.exp(-distance/25000)),sea=(this.preset.day*bg.D-this.preset.night*bg.N)*Math.exp(-(geo.signedDistance[geoIndex]**2)/(2*40000**2));let legacyG=0,legacyE=1,J=geo.jetJ[geoIndex],ex=this.jetDirection[0],ey=this.jetDirection[1];if(bg.axis){const x=meta.extended.origin[0]+(i+offset+.5)*2500-bg.axis.x,y=meta.extended.origin[1]+(j+offset+.5)*2500-bg.axis.y,perp=-bg.axis.ey*x+bg.axis.ex*y,along=bg.axis.ex*x+bg.axis.ey*y;legacyG=Math.exp(-perp*perp/(2*bg.axis.width**2));legacyE=1-bg.exitEnvelope*.5*(1+Math.tanh((along-bg.axis.end)/bg.axis.endWidth));J=.6+.4*legacyG*legacyE;ex=bg.axis.ex;ey=bg.axis.ey;}const cg=this.coastalGeometry,opts=cg?.options||{},scale=bg.V/(this.preset.baseV||1),friction=opts.disableFriction?1:rough,breeze=opts.disableSeaBreeze?0:sea;let ux=(cg?scale*J*(cg.inletNormal*cg.normal.x+cg.inletAlong*cg.tangent.x):2+bg.V*J*ex)*friction+breeze*geo.coastX[geoIndex],vy=(cg?scale*J*(cg.inletNormal*cg.normal.y+cg.inletAlong*cg.tangent.y):bg.V*J*ey)*friction+breeze*geo.coastY[geoIndex];const delta=this._mesoscaleVelocity(meta.extended.origin[0]+(i+offset+.5)*2500+this.config.width/2,meta.extended.origin[1]+(j+offset+.5)*2500+this.config.height/2,mesoEvents);ux+=delta.u;vy+=delta.v;if(finite){this._finiteWindSample(meta.extended.origin[0]+(i+offset+.5)*2500+this.config.width/2,meta.extended.origin[1]+(j+offset+.5)*2500+this.config.height/2,bg,friction,geo.signedDistance[geoIndex],geo.coastX[geoIndex],geo.coastY[geoIndex],delta,sample);ux=sample[0];vy=sample[1];}const uphill=Math.max(0,ux*geo.normalX[geoIndex]+vy*geo.normalY[geoIndex])*geo.beta[geoIndex];rawU[k]=ux-uphill*geo.normalX[geoIndex];rawV[k]=vy-uphill*geo.normalY[geoIndex];if(finite)this._putWindParts(parts,k,sample[2],sample[3],sample[4],sample[5],sample[6],sample[7],sample[8],sample[9],-uphill*geo.normalX[geoIndex],-uphill*geo.normalY[geoIndex],sample[10],sample[11]);else{const bu=cg?scale*.6*(cg.inletNormal*cg.normal.x+cg.inletAlong*cg.tangent.x)*friction:(2+bg.V*J*ex)*friction,bv=cg?scale*.6*(cg.inletNormal*cg.normal.y+cg.inletAlong*cg.tangent.y)*friction:bg.V*J*ey*friction;this._putWindParts(parts,k,bu,bv,cg?scale*.4*legacyG*legacyE*(cg.inletNormal*cg.normal.x+cg.inletAlong*cg.tangent.x)*friction:0,cg?scale*.4*legacyG*legacyE*(cg.inletNormal*cg.normal.y+cg.inletAlong*cg.tangent.y)*friction:0,breeze*geo.coastX[geoIndex],breeze*geo.coastY[geoIndex],delta.u,delta.v,-uphill*geo.normalX[geoIndex],-uphill*geo.normalY[geoIndex],legacyG,legacyE);}}}else{const x=(i+.5)*fg.dx,y=(j+.5)*fg.dx,cg=this.coastalGeometry;
        if(cg?.kind==='straight-coast-prototype'){
          const axis=bg.axis,xx=x-this.config.width/2-axis.x,yy=y-this.config.height/2-axis.y,perp=-axis.ey*xx+axis.ex*yy,along=axis.ex*xx+axis.ey*yy,G=Math.exp(-perp*perp/(2*axis.width**2)),E=1-bg.exitEnvelope*.5*(1+Math.tanh((along-axis.end)/axis.endWidth)),J=.6+.4*G*E,proto=this.config.coastalPrototype,coastY=typeof proto==='object'?(proto.coastY??this.config.height*.45):this.config.height*.45,d=y-coastY,L=.5*(1+Math.tanh(d/8000)),rough=cg.options.disableFriction?1:1-.4*L*(1-Math.exp(-Math.max(d,0)/25000)),sea=cg.options.disableSeaBreeze?0:(this.preset.day*bg.D-this.preset.night*bg.N)*Math.exp(-d*d/(2*40000**2)),scale=bg.V/this.preset.baseV;
          const delta=this._mesoscaleVelocity(x,y,mesoEvents);rawU[k]=scale*J*(cg.inletNormal*cg.normal.x+cg.inletAlong*cg.tangent.x)*rough+sea*cg.normal.x+delta.u;rawV[k]=scale*J*(cg.inletNormal*cg.normal.y+cg.inletAlong*cg.tangent.y)*rough+sea*cg.normal.y+delta.v;if(finite){this._finiteWindSample(x,y,bg,rough,d,cg.normal.x,cg.normal.y,delta,sample);rawU[k]=sample[0];rawV[k]=sample[1];this._putWindParts(parts,k,sample[2],sample[3],sample[4],sample[5],sample[6],sample[7],sample[8],sample[9],0,0,sample[10],sample[11]);}else this._putWindParts(parts,k,scale*.6*(cg.inletNormal*cg.normal.x+cg.inletAlong*cg.tangent.x)*rough,scale*.6*(cg.inletNormal*cg.normal.y+cg.inletAlong*cg.tangent.y)*rough,scale*.4*G*E*(cg.inletNormal*cg.normal.x+cg.inletAlong*cg.tangent.x)*rough,scale*.4*G*E*(cg.inletNormal*cg.normal.y+cg.inletAlong*cg.tangent.y)*rough,sea*cg.normal.x,sea*cg.normal.y,delta.u,delta.v,0,0,G,E);
        }else{const L=.5*(1+Math.tanh((y-240000)/8000)),d=Math.max(y-240000,0),J=.6+.4*Math.exp(-(((x-380000)/150000)**2));rawU[k]=3;rawV[k]=bg.V*J*(1-.4*L*(1-Math.exp(-d/25000)))-this.preset.night*bg.N*L*Math.exp(-d/40000);this._putWindParts(parts,k,rawU[k],rawV[k],0,0,0,0,0,0,0,0);}}}if(j%16===15)yield;}
      if(real){const tmpU=this.buffer('blurU',n),tmpV=this.buffer('blurV',n),weights=[];let norm=0;for(let a=-6;a<=6;a++){const w=Math.exp(-.5*(a/2)**2);weights.push(w);norm+=w;}for(let a=0;a<weights.length;a++)weights[a]/=norm;blurWeights=weights;
        for(let j=0;j<ny;j++){for(let i=halo;i<nx-halo;i++){const k=j*nx+i;let a=weights[6]*rawU[k],b=weights[6]*rawV[k];for(let d=1;d<=6;d++){a+=weights[d+6]*(rawU[k-d]+rawU[k+d]);b+=weights[d+6]*(rawV[k-d]+rawV[k+d]);}tmpU[k]=a;tmpV[k]=b;}if(j%16===15)yield;}
        const pad=halo;for(let j=0;j<fg.ny;j++){for(let i=0;i<fg.nx;i++){const k=(j+pad)*nx+i+pad;let a=weights[6]*tmpU[k],b=weights[6]*tmpV[k];for(let d=1;d<=6;d++){a+=weights[d+6]*(tmpU[k-d*nx]+tmpU[k+d*nx]);b+=weights[d+6]*(tmpV[k-d*nx]+tmpV[k+d*nx]);}u[j*fg.nx+i]=a;v[j*fg.nx+i]=b;}if(j%16===15)yield;}
      }else{u.set(rawU);v.set(rawV);}
      yield*this._finishWindEvidence(parts,nx,ny,real,halo,blurWeights,u,v);
      this.fineU=u;this.fineV=v;
      for(const item of [[this.env,this.eu,this.ev],[this.cold,this.cu,this.cv]]){const [g,ux,vy]=item,r=Math.round(g.dx/fg.dx);for(let j=0;j<g.ny;j++){for(let i=0;i<=g.nx;i++){let a=0;for(let k=0;k<r;k++){const row=j*r+k,left=Math.max(0,i*r-1),right=Math.min(fg.nx-1,i*r);a+=(u[row*fg.nx+left]+u[row*fg.nx+right])*.5;}ux[j*(g.nx+1)+i]=a/r;}if(j%24===23)yield;}for(let j=0;j<=g.ny;j++){for(let i=0;i<g.nx;i++){let a=0;for(let k=0;k<r;k++){const col=i*r+k,below=Math.max(0,j*r-1),above=Math.min(fg.ny-1,j*r);a+=(v[below*fg.nx+col]+v[above*fg.nx+col])*.5;}vy[j*g.nx+i]=a/r;}if(j%24===23)yield;}}
      const f=this.fields,g=this.env;for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++){const k=j*g.nx+i;f.u[k]=(this.eu[j*(g.nx+1)+i]+this.eu[j*(g.nx+1)+i+1])*.5;f.v[k]=(this.ev[j*g.nx+i]+this.ev[(j+1)*g.nx+i])*.5;const mid=this.steer(at),xx=(i+.5)*g.dx/g.width-.5,yy=(j+.5)*g.dx/g.height-.5;const guided=this._terrainSteer(k,this.config.monsoon925?f.u[k]:mid[0]+2*yy,this.config.monsoon925?f.v[k]:mid[1]-1.5*xx);f.um[k]=guided[0];f.vm[k]=guided[1];f.divL[k]=(this.eu[j*(g.nx+1)+i+1]-this.eu[j*(g.nx+1)+i]+this.ev[(j+1)*g.nx+i]-this.ev[j*g.nx+i])/g.dx;f.airLM[k]=-1400*f.divL[k];f.airTop[k]=f.airLM[k];f.upperDiv[k]=real?this._upperDiv((i+.5)*g.dx,(j+.5)*g.dx,bg):5e-5;}
      if(this.config.mechanismEvidence){this._mechanismBuffer('wind_environment_u_face',this.eu.length).set(this.eu);this._mechanismBuffer('wind_environment_v_face',this.ev.length).set(this.ev);this._mechanismBuffer('wind_cold_u_face',this.cu.length).set(this.cu);this._mechanismBuffer('wind_cold_v_face',this.cv.length).set(this.cv);}
    }
    steer(at=this.t){
      if(this.monsoon){const p=this.monsoon,span=10800,k=Math.floor(at/span),u=at/span-k,w=u*u*(3-2*u),a=random(hash(this.config.seed,'midwind',k)),b=random(hash(this.config.seed,'midwind',k+1)),angle=p.midDirection+((a()-.5)*.4*(1-w)+(b()-.5)*.4*w),speed=p.midSpeed*((.8+.4*a())*(1-w)+(.8+.4*b())*w);return [speed*Math.cos(angle),speed*Math.sin(angle)];}
      const angle=(this.config.steerRotation||0)*Math.PI/180;return [8*Math.cos(angle)-6*Math.sin(angle),8*Math.sin(angle)+6*Math.cos(angle)];
    }
    _upperDiv(x,y,bg){const axis=bg?.axis,c=axis?[axis.x+axis.ex*axis.end,axis.y+axis.ey*axis.end]:this.terrain.meta.upperCenter||[0,0],rx=x-this.config.width/2-c[0],ry=y-this.config.height/2-c[1],r2=(rx*rx+ry*ry)/(2*350000**2);return 5e-5*Math.exp(-r2)*(1-r2);}
    *coldRhs(h,q,prefix){
      const g=this.cold,dh=this.buffer(prefix+'h',g.n),dq=this.buffer(prefix+'q',g.n),aq=this.buffer(prefix+'aq',g.n),ah=this.buffer(prefix+'ah',g.n);dh.fill(0);dq.fill(0);aq.fill(0);ah.fill(0);let volumeOut=0,heatOut=0;
      const face=(left,right,wind,axis,k)=>{
        if(this.config.coldBoundary==='closed'&&(left<0||right<0))return;
        const ql=left<0?0:q[left],qr=right<0?0:q[right];if(ql===0&&qr===0&&(left<0||h[left]===0)&&(right<0||h[right]===0)){if(axis===0){this.cvx[k]=this.coutx[k]=0;}else{this.cvy[k]=this.couty[k]=0;}return;}const qf=(ql+qr)/2,delta=qr-ql,B=Math.sqrt(delta*delta+(qf*g.dx/5000)**2+1e-12),c=(this.config.kappa||.8)*Math.sqrt(2*9.81*qf/300),cp=-c*delta/B;
        let vbg=0,vcp=0;
        for(let channel=0;channel<2;channel++){const u=channel?cp:wind,d=u>=0?left:right,r=u>=0?right:left;if(d<0||h[d]<=0)continue;const b=clip(1-Math.max((r<0?this.cz[d]:this.cz[r])-this.cz[d],0)/Math.max(h[d],10)),v=b*u,Fh=v*h[d],Fq=v*q[d];if(channel)vcp=v;else vbg=v;
          if(left>=0){dh[left]-=Fh/g.dx;dq[left]-=Fq/g.dx;}if(right>=0){dh[right]+=Fh/g.dx;dq[right]+=Fq/g.dx;}
          if(left<0){volumeOut-=Fh*g.dx;heatOut-=Fq*g.dx;}if(right<0){volumeOut+=Fh*g.dx;heatOut+=Fq*g.dx;}
          if(left>=0)ah[left]+=Math.max(v,0)/g.dx;if(right>=0)ah[right]+=Math.max(-v,0)/g.dx;
          if(!channel){if(left>=0)aq[left]+=Math.max(v,0)/g.dx;if(right>=0)aq[right]+=Math.max(-v,0)/g.dx;}
        }
        let bcp=1;if(delta!==0){const donor=cp>=0?left:right,receiver=cp>=0?right:left;bcp=donor<0||h[donor]<=0?0:clip(1-Math.max((receiver<0?this.cz[donor]:this.cz[receiver])-this.cz[donor],0)/Math.max(h[donor],10));}
        const D=qf===0?0:bcp*c*Math.max(ql,qr)*g.dx/B;if(left>=0)aq[left]+=D/g.dx**2;if(right>=0)aq[right]+=D/g.dx**2;
        if(axis===0){this.cvx[k]=vbg+vcp;this.coutx[k]=vcp;}else{this.cvy[k]=vbg+vcp;this.couty[k]=vcp;}
      };
      for(let j=0;j<g.ny;j++){for(let i=0;i<=(this.config.coldBoundary==='periodic'?g.nx-1:g.nx);i++)face(i?j*g.nx+i-1:this.config.coldBoundary==='periodic'?j*g.nx+g.nx-1:-1,i<g.nx?j*g.nx+i:-1,this.cu[j*(g.nx+1)+i],0,j*(g.nx+1)+i);if(j%12===11)yield;}
      for(let j=0;j<=(this.config.coldBoundary==='periodic'?g.ny-1:g.ny);j++){for(let i=0;i<g.nx;i++)face(j?(j-1)*g.nx+i:this.config.coldBoundary==='periodic'?(g.ny-1)*g.nx+i:-1,j<g.ny?j*g.nx+i:-1,this.cv[j*g.nx+i],1,j*g.nx+i);if(j%12===11)yield;}
      let rate=0;for(let i=0;i<g.n;i++)rate=Math.max(rate,aq[i],ah[i]);return {dh,dq,rate,volumeOut,heatOut};
    }
    *advanceCold(mix=true){
      if(this.config.disableCold)return;let remaining=DT;const g=this.cold,h1=this.buffer('coldStageH',g.n),q1=this.buffer('coldStageQ',g.n);
      while(remaining>1e-9){const a=yield* this.coldRhs(this.h,this.q,'coldA');let dt=Math.min(remaining,a.rate>0?.8/a.rate:remaining),b;
        for(let retry=0;retry<=20;retry++){for(let i=0;i<g.n;i++){h1[i]=this.h[i]+dt*a.dh[i];q1[i]=this.q[i]+dt*a.dq[i];}b=yield* this.coldRhs(h1,q1,'coldB');if(dt*b.rate<=.8+1e-13)break;if(retry===20)throw Error('冷池联合步长无法收敛');dt*=.5;this.stats.coldRejected++;}
        for(let i=0;i<g.n;i++){this.h[i]=.5*(this.h[i]+h1[i]+dt*b.dh[i]);this.q[i]=.5*(this.q[i]+q1[i]+dt*b.dq[i]);if(this.h[i]<-1e-9||this.q[i]<-1e-8)throw Error('冷池输送产生负值');}
        this.stats.coldVolumeLoss+=.5*dt*(a.volumeOut+b.volumeOut);this.stats.coldHeatLoss+=.5*dt*(a.heatOut+b.heatOut);this.stats.maxStability=Math.max(this.stats.maxStability,dt*a.rate,dt*b.rate);this.stats.coldSubsteps++;remaining-=dt;
      }
      if(!mix)return;
      const hm=Math.exp(-DT/this.config.coldVolumeMixingSeconds),qm=Math.exp(-DT*(1/this.config.coldVolumeMixingSeconds+1/this.config.coldThermalMixingSeconds));for(let i=0;i<g.n;i++){const oldH=this.h[i],oldQ=this.q[i];let h=oldH*hm,q=oldQ*qm;if(h>1200){const drained=h-(h-1200)*(1-Math.exp(-DT/600));q*=drained/h;h=drained;}this.h[i]=h;this.q[i]=q;this.stats.coldVolumeLoss+=(oldH-h)*g.area;this.stats.coldHeatLoss+=(oldQ-q)*g.area;}
    }
    surfaceAccess(x,y){
      const index=this.cold.index(x,y),inDomain=index>=0;if(!inDomain)return {inDomain:false,index:-1,h:null,Q:null,qOverH:null,cold:false,warmAccessible:false,status:'outside',sampling:'cold finite-volume cell, piecewise constant'};
      const h=this.h[index],Q=this.q[index],qOverH=h>0?Q/h:0,cold=h>=40&&Q>=20&&qOverH>=.3;
      return {inDomain,index,h,Q,qOverH,cold,warmAccessible:!cold,status:cold?'cold':h<=0&&Q<=0?'no_cold_air':'weak_or_shallow_cooling',sampling:'cold finite-volume cell, piecewise constant'};
    }
    isCold(x,y){return this.surfaceAccess(x,y).cold;}
    *updateSurfaceFractions(){
      const g=this.env,cg=this.cold,f=this.fields,r=g.dx/cg.dx;
      for(let j=0;j<g.ny;j++){for(let i=0;i<g.nx;i++){let blocked=0,accessible=0;for(let b=0;b<r;b++)for(let a=0;a<r;a++){const x=(i*r+a+.5)*cg.dx,y=(j*r+b+.5)*cg.dx,s=this.surfaceAccess(x,y);if(s.cold)blocked++;accessible+=this._columnSupplyFraction(s,x,y);}const k=j*g.nx+i;f.coldFraction[k]=blocked/(r*r);f.warmAccessibleFraction[k]=accessible/(r*r);}if(j%24===23)yield;}
    }
    *supplyFootprint(x,y,major,minor,angle){
      if(this.config.surfaceAccessMode==='legacy')return (yield*this.kernel(this.env,x,y,major,minor,angle,false)).map(([i,a])=>[i,a,i>=0&&this.fields.q[i]<20?a:0]);
      // Integrate the same phi at 1.25 km quadrature in every quality, weighted by each owning cold FV cell's available column fraction.
      const fine=yield*this.kernel(this.cold,x,y,major,minor,angle,false),rows=new Map(),cg=this.cold,g=this.env,r=g.dx/cg.dx;
      for(const [k,a]of fine){if(k<0)continue;const ci=k%cg.nx,cj=Math.floor(k/cg.nx),i=Math.floor(cj/r)*g.nx+Math.floor(ci/r),row=rows.get(i)||[i,0,0],x=(ci+.5)*cg.dx,y=(cj+.5)*cg.dx;row[1]+=a;row[2]+=a*this._columnSupplyFraction(this.surfaceAccess(x,y),x,y);rows.set(i,row);}return Array.from(rows.values()).sort((a,b)=>a[0]-b[0]);
    }
    _ensurePulse(c){
      if(this.config.cellLifecycle==='legacy')return;
      if(!c.pulse){const rng=random(hash(this.config.seed,'cell-pulse-1.7',c.id)),Hc=4500+2000*rng(),Nend=c.triggerSourceId&&this.config.jetExitControl?(this.config.longTrainingPulse?6.8+3.4*rng():5+2*rng()):3+1.2*rng();c.pulse={Hc,Nend,Ngrow:.35,Ndecay:(c.triggerSourceId&&this.config.longTrainingPulse ? .72 : .60)*Nend,N:0,L:0,wturn:3,parameterization:'seeded finite engineering convection pulse'};}
      c.physicalUpdraftArea??=c.updraftArea??Math.PI*1000**2;c.pulseEnvelope??=c.pulse.L;c.effectiveUpdraftArea??=c.physicalUpdraftArea*c.pulseEnvelope;c.updraftAirMassFlux??=0;
    }
    _advancePulse(c,thermal,dt=DT){
      this._ensurePulse(c);if(this.config.cellLifecycle==='legacy'){c.pulseEnvelope=1;return false;}
      const p=c.pulse,smooth=x=>{const u=clip(x);return u*u*(3-2*u);},old=p.N;
      if(old>=p.Nend){c.pulseEnvelope=0;return true;}
      p.wturn=Math.max(3,Math.min(8,1+7*Math.sqrt(thermal)));const dn=dt*p.wturn/p.Hc;
      // Composite midpoint quadrature of the bounded growth/decay envelope;
      // this is a source integral, not repeated 30-second model advances.
      let mean=0;for(let j=0;j<16;j++){const n=old+dn*(j+.5)/16;mean+=smooth(n/p.Ngrow)*(1-smooth((n-p.Ndecay)/(p.Nend-p.Ndecay)))/16;}
      p.N=old+dn;p.L=smooth(p.N/p.Ngrow)*(1-smooth((p.N-p.Ndecay)/(p.Nend-p.Ndecay)));c.pulseEnvelope=mean;return false;
    }
    *buildBoundaries(){
      this._coldKinematicsReady=false;yield*this.prepareColdKinematics();this.boundaries.clear();this._beginFrontStep();const layerStat=()=>({attempts:0,eligible:0,rejected:0,reasons:{outside:0,relativeNormal:0,humidity:0,energy:0,cold:0,noWarmSample:0},pathStops:{outside:0,humidity:0,energy:0,cold:0}});
      const D={edges:0,warmRejected:0,thermoRejected:0,inflowRejected:0,eligible:0,byLayer:{low:layerStat(),mid:layerStat()},local:{edges:0,byLayer:{low:layerStat(),mid:layerStat()}},edgeSamples:[],samplePolicy:'First 24 edges in deterministic row order; all-edge counts are complete.',edgeSums:{x:0,y:0,vx:0,vy:0,insideQ:0,outsideQ:0}};this.boundaryDiagnostics=D;
      const g=this.cold,f=this.fields,dirs=[[1,0],[-1,0],[0,1],[0,-1]],cold=i=>i>=0&&this.h[i]>=40&&this.q[i]>=20&&this.q[i]/this.h[i]>=.3;
      for(let j=0;j<g.ny;j++){for(let i=0;i<g.nx;i++){
        const k=j*g.nx+i;if(!cold(k))continue;
        for(const [di,dj]of dirs){const ii=i+di,jj=j+dj;if(ii<0||jj<0||ii>=g.nx||jj>=g.ny||cold(jj*g.nx+ii))continue;D.edges++;
          const b={x:(i+.5+.5*di)*g.dx,y:(j+.5+.5*dj)*g.dx,nx:di,ny:dj,geometricNormal:{x:di,y:dj},id:k*4+(di===1?0:di===-1?1:dj===1?2:3)};
          const gx=this.q[j*g.nx+Math.max(0,i-1)]-this.q[j*g.nx+Math.min(g.nx-1,i+1)],gy=this.q[Math.max(0,j-1)*g.nx+i]-this.q[Math.min(g.ny-1,j+1)*g.nx+i],length=Math.hypot(gx,gy);
          if(length>1e-7&&gx/length*di+gy/length*dj>.3&&!this.isCold(b.x+gx/length*g.dx,b.y+gy/length*g.dx)){b.nx=gx/length;b.ny=gy/length;}
          b.smoothedNormal={x:b.nx,y:b.ny};if(this.config.frontClosure==='head_work'){b.nx=di;b.ny=dj;}b.head=this._coldHeadSupport(b);
          const inner=this.surfaceAccess(b.x-b.nx*g.dx,b.y-b.ny*g.dx);b.q=this.config.surfaceAccessMode==='legacy'?g.sample(this.q,b.x-b.nx*g.dx,b.y-b.ny*g.dx):inner.Q;b.h=this.config.surfaceAccessMode==='legacy'?g.sample(this.h,b.x-b.nx*g.dx,b.y-b.ny*g.dx):inner.h;b.head.pointH=b.h;b.head.pointQ=b.q;
          const vx=di?this.cvx[j*(g.nx+1)+i+(di>0?1:0)]:.5*(this.cvx[j*(g.nx+1)+i]+this.cvx[j*(g.nx+1)+i+1]),vy=dj?this.cvy[(j+(dj>0?1:0))*g.nx+i]:.5*(this.cvy[j*g.nx+i]+this.cvy[(j+1)*g.nx+i]);
          b.carrierVelocity={x:vx,y:vy};b.phase=this._coldFrontPhase(k,jj*g.nx+ii,di,dj);b.velocity=this.config.coldDynamics==='inertial'?b.phase.velocity:{x:vx,y:vy};const boundaryVx=b.velocity.x,boundaryVy=b.velocity.y;b.feeds={};b.paths={};b.pathStops={};b.inlets={};b.relativeWinds={};b.rejections={};b.local=this._organizationContains(b.x,b.y);
          b.inside=this._edgeState(b.x-b.nx*g.dx*.5,b.y-b.ny*g.dx*.5);b.outside=this._edgeState(b.x+b.nx*g.dx*.5,b.y+b.ny*g.dx*.5);
          if(b.local)D.local.edges++;for(const [key,value]of Object.entries({x:b.x,y:b.y,vx:boundaryVx,vy:boundaryVy,insideQ:b.inside.q,outsideQ:b.outside.q}))D.edgeSums[key]+=value;
          for(const layer of ['low','mid']){
            const records=[D.byLayer[layer],...(b.local?[D.local.byLayer[layer]]:[])];for(const record of records)record.attempts++;
            const mark=(kind,reason)=>{if(kind==='pathStops')b.pathStops[layer]=reason;for(const record of records)record[kind][reason]++;};
            const uk=layer==='low'?'u':'um',vk=layer==='low'?'v':'vm',rh=layer==='low'?'rhL':'rhM',energy=layer==='low'?'el':'em',rx=this.env.sample(f[uk],b.x,b.y)-boundaryVx,ry=this.env.sample(f[vk],b.x,b.y)-boundaryVy,speed=Math.hypot(rx,ry),normal=-(rx*b.nx+ry*b.ny),path=[];
            b.paths[layer]=path;b.relativeWinds[layer]={x:rx,y:ry,normalInflow:Math.max(0,normal)};
            let reason=null;
            if(speed<1||normal<2)reason='relativeNormal';else for(let distance=5000;distance<=Math.min(20000,this.config.warmSourceMax||20000);distance+=2500){
              const x=b.x-distance*rx/speed,y=b.y-distance*ry/speed,e=this.env.index(x,y);if(e<0){reason='outside';mark('pathStops',reason);break;}
              const access=this.surfaceAccess(x,y),fineCold=access.cold,fineQ=this.config.surfaceAccessMode==='legacy'?this.cold.sample(this.q,x,y):access.Q,blocked=layer==='low'&&(this.config.surfaceAccessMode==='legacy'?(fineCold||fineQ>=20):!access.warmAccessible),sample={x,y,distance,rh:f[rh][e],energy:f[energy][e],surfaceAccess:access,accessMode:this.config.surfaceAccessMode,coldBlocked:blocked,fineCold,fineQ,environmentMeanQ:f.q[e],environmentColdFraction:f.coldFraction[e]};path.push(sample);
              if(blocked){reason='cold';mark('pathStops',reason);break;}
              if(f[rh][e]<(layer==='low'?.75:.55)){reason='humidity';mark('pathStops',reason);break;}
              if(f[energy][e]<(layer==='low'?.25:.2)){reason='energy';mark('pathStops',reason);break;}
              if(b.feeds[layer]===undefined){b.feeds[layer]=e;b.inlets[layer]=sample;}
            }
            if(b.feeds[layer]!==undefined){for(const record of records)record.eligible++;}else{reason=reason||'noWarmSample';b.rejections[layer]=reason;for(const record of records)record.rejected++;mark('reasons',reason);}
          }
          b.geometricNormal={x:di,y:dj};b.lengthM=g.dx;b.fluxInside={index:k,h:this.h[k],Q:this.q[k]};yield*this._observeFront(b,D.edgeSamples.length<24);
          if(D.edgeSamples.length<24)D.edgeSamples.push(b);
          if(b.feeds.low===undefined&&b.feeds.mid===undefined){D.warmRejected++;continue;}
          b.feed=b.feeds.low??b.feeds.mid;b.warmInlet=b.inlets.low??b.inlets.mid;b.inflow=(b.relativeWinds.low?.normalInflow)||0;D.eligible++;
          const key=Math.floor(b.x/10000)+','+Math.floor(b.y/10000);if(!this.boundaries.has(key))this.boundaries.set(key,[]);this.boundaries.get(key).push(b);
        }
      }if(j%8===7)yield;}
      D.meanEdge=D.edges?Object.fromEntries(Object.entries(D.edgeSums).map(([key,value])=>[key,value/D.edges])):null;
      D.surfaceAccessMode=this.config.surfaceAccessMode;D.ruleDifference=this.config.surfaceAccessMode==='consistent'?'Shared piecewise-constant cold FV access: h>=40,Q>=20,Q/h>=0.3; candidate and actual inlet use local Q CIN; low supply integrates accessible footprint and shared warm-area capacity.':'Legacy ablation: candidate fine mask; low path fine mask OR interpolated Q>=20; low supply whole env-mean Q<20.';
    }
    gate(x,y,layer,bg,environmentOnly=false){
      if(this.config.initiationModel==='focused_lift')return this._focusedGate(x,y,layer,bg,environmentOnly);
      const f=this.fields,g=this.env,i=g.index(x,y);if(i<0)return {F:0,power:0,coldPower:0,CIN:0,rejection:'outside'};
      const value=(k,power,px,py)=>{const rh=layer?f.rhM[k]:f.rhL[k],energy=layer?f.em[k]:f.el[k],access=this.surfaceAccess(px,py),Qlocal=this.config.surfaceAccessMode==='legacy'?f.q[k]:(access.Q??0),CIN=layer?bg.iM+20*clip((.65-rh)/.25):bg.iL+20*clip((.75-rh)/.25)+.08*Qlocal;return {F:clip((rh-(layer?.45:.65))/(layer?.35:.25))*clip((energy-.15)/.65)*clip((power-CIN)/15),CIN,rh,energy,Qlocal,surfaceAccess:access,position:{x:px,y:py},accessMode:this.config.surfaceAccessMode};},envPower=.08*(layer?f.xiM[i]:f.xiL[i]),environment=value(i,envPower,x,y);
      if(!layer&&this.isCold(x,y))return {F:0,power:envPower,coldPower:0,CIN:environment.CIN,rejection:'fineCold',evidence:{...environment,F:0,Kenv:envPower,Kcp:0,triggerLayer:'low',position:{x,y},fineCold:true}};
      let best={...environment,source:'environment',power:envPower,coldPower:0,parent:null,evidence:{...environment,triggerLayer:layer?'mid':'low',Kenv:envPower,Kcp:0,position:{x,y}}};
      if(environmentOnly)return best;
      if(!this.config.disableCold){const ix=Math.floor(x/10000),iy=Math.floor(y/10000);for(let yy=iy-1;yy<=iy+1;yy++)for(let xx=ix-1;xx<=ix+1;xx++)for(const b of this.boundaries.get(xx+','+yy)||[]){const dx=x-b.x,dy=y-b.y,normal=dx*b.nx+dy*b.ny,tangent=Math.abs(-dx*b.ny+dy*b.nx);if(normal<0||normal>4000||tangent>this.cold.dx*.8)continue;const name=layer?'mid':'low',feed=b.feeds[name],relative=b.relativeWinds[name];if(feed===undefined||!relative)continue;
        const lift=this._coldLift(b,layer,relative.normalInflow),power=lift.Kcp,inlet=b.inlets[name],metric=value(feed,envPower+power,inlet.x,inlet.y);
        if(metric.F>best.F)best={...metric,source:'coldPool',power:envPower,coldPower:power,parent:b.id,evidence:{...metric,boundaryId:b.id,normal:{x:b.nx,y:b.ny},boundaryVelocity:b.velocity,carrierVelocity:b.carrierVelocity,phase:b.phase,head:b.head,lift,relativeWind:relative,normalInflow:relative.normalInflow,warmInlet:b.inlets[name],warmPath:b.paths[name],inside:b.inside,outside:b.outside,Kenv:envPower,Kcp:power,triggerLayer:name,probabilityBoost:metric.F-environment.F,coldDominant:power>envPower}};
      }}return best;
    }
    *initiate(){
      const diagnostic={stepSeconds:DT,byLayer:{low:this._triggerLayerDiagnostic(),mid:this._triggerLayerDiagnostic()},local:{byLayer:{low:{...this._triggerLayerDiagnostic(),poissonMean:null},mid:{...this._triggerLayerDiagnostic(),poissonMean:null}}},expectedDefinition:'Area: sum F at actual Poisson points. Flux: sum F at actual line proposals. Conditional acceptance expectation; spacing excluded.'};this.triggerDiagnostics=diagnostic;
      const tile=10000,bg=this.background(),events=[],step=Math.round(this.t/DT),nx=Math.ceil(this.config.width/tile),ny=Math.ceil(this.config.height/tile),lambda=this.config.lambda0??1e-5,flux=this.config.boundaryInitiationMode==='flux';
      const propose=(x,y,layer,gate,accept,priority,id,channel,segment=null)=>{
        const local=this._organizationContains(x,y),d=diagnostic.byLayer[layer?'mid':'low'],ld=diagnostic.local.byLayer[layer?'mid':'low'],inBand=!segment&&!!this._areaFrontExposure(x,y);
        this.stats.candidates++;this._recordTriggerGate(d,gate);if(local)this._recordTriggerGate(ld,gate);this._recordFrontCandidate(x,y,channel,'candidates',1);this._recordFrontCandidate(x,y,channel,'conditionalExpected',gate.F);if(inBand){this._recordFrontCandidate(x,y,channel,'inBandCandidates',1);this._recordFrontCandidate(x,y,channel,'inBandConditionalExpected',gate.F);}
        if(accept<gate.F){events.push({x,y,layer,gate,id,priority,channel,segmentKey:segment?.key??null,physicalFaceId:segment?.boundary.faceId??null,inBand});if(segment)this.stats.boundaryAccepted=(this.stats.boundaryAccepted||0)+1;else this.stats.environmentAccepted++;d.acceptedBeforeSpacing++;if(local)ld.acceptedBeforeSpacing++;this._recordFrontCandidate(x,y,channel,'acceptedBeforeSpacing',1);if(inBand)this._recordFrontCandidate(x,y,channel,'inBandAcceptedBeforeSpacing',1);}
        else{this._recordFrontCandidate(x,y,channel,'thinningRejected',1);this._recordFrontGateRejection(x,y,channel,gate.F>0?'randomThinning':gate.rejection||(gate.power+gate.coldPower<=(gate.CIN??0)?'inhibition':gate.rh<=(layer?.45:.65)?'humidity':gate.energy<=.15?'energy':'zeroGate'));}
      };
      // A successful source stays at its birth location. Subsequent towers are
      // deterministic once per physical step, until the CURRENT local gate closes.
      // Existing moving cells neither move this root nor keep a shut root alive.
      if(this.config.persistentInitiation){
        const active=[];
        const ordered=this.triggerSources.slice().sort((a,b)=>this._sourceOrder(a,b,bg));
        for(const source of ordered){
          // Established sources retain their own verified inlet; a newly
          // adjacent source is not sufficient evidence that supply was cut.
          const gate=this._persistentSourceGate(source,bg);
          if(!(gate.F>0)){this.stats.closedTriggerSources=(this.stats.closedTriggerSources||0)+1;this.stats.sourceClosureReasons??={};const reason=gate.rejection||'environment';this.stats.sourceClosureReasons[reason]=(this.stats.sourceClosureReasons[reason]||0)+1;continue;}
          active.push(source);
          const born=source.lastBirth+DT;if(born>=this.t+DT)continue;
          const continued={...gate,F:1,evidence:{...gate.evidence,persistentSource:{id:source.id,activationGate:gate.F,rule:'continue while local environment remains eligible'}}};
          propose(source.x,source.y,0,continued,0,-1,source.id+':'+step,gate.source==='coldPool'?'boundaryLow':'areaLow');
          Object.assign(events.at(-1),{triggerSource:source,born});
        }
        this.triggerSources=active;
      }
      for(let j=0;j<ny;j++){for(let i=0;i<nx;i++)for(let layer=0;layer<2;layer++){
        const rng=random(hash(this.config.seed,'birth',step,i,j,layer)),w=Math.min(tile,this.config.width-i*tile),h=Math.min(tile,this.config.height-j*tile),mu=lambda*(layer?.3:1)*w*h/1e6*DT,count=poisson(mu,rng);diagnostic.byLayer[layer?'mid':'low'].poissonMean+=mu;
        for(let k=0;k<count;k++){const x=i*tile+rng()*w,y=j*tile+rng()*h,gate=this.gate(x,y,layer,bg,flux&&!layer),accept=rng(),priority=rng(),id=[step,i,j,layer,k].join(':');propose(x,y,layer,gate,accept,priority,id,layer?'areaMid':'areaLow');}
      }if(j%12===11)yield;}
      // Stratified coverage of an eligible exit belt: ordinary domain-wide
      // Poisson proposals can repeatedly miss its narrow mountain/island parts.
      // Every proposal still passes the same thermodynamic/site/cold gate.
      if(this.config.organizedWarmSector&&this.config.jetExitControl&&lambda>0){
        const g=this.env;
        for(let j=0;j<g.ny;j++){for(let i=0;i<g.nx;i++){
          const x=(i+.5)*g.dx,y=(j+.5)*g.dx,belt=this._jetExitAccess(x,y,bg);if(belt.factor<=0||belt.ascent<=.02)continue;
          const rng=random(hash(this.config.seed,'exit-belt',step,i,j)),gate=this.gate(x,y,0,bg,flux),probability=-Math.expm1(-3*lambda*g.area/1e6*DT);
          if(rng()<probability)propose(x,y,0,gate,rng(),rng(),'belt:'+step+':'+i+':'+j,'areaLow');
        }if(j%12===11)yield;}
      }
      if(flux)for(const segment of this.frontSegments){
        const mu=segment.eligibleMu;if(mu<=0)continue;const rng=random(hash(this.config.seed,'boundary-flux-low-1.8',step,segment.key)),count=poisson(mu,rng);diagnostic.byLayer.low.poissonMean+=mu;this.stats.boundaryCandidates=(this.stats.boundaryCandidates||0)+count;this._recordFrontCandidate((segment.x0+segment.x1)/2,(segment.y0+segment.y1)/2,'boundaryLow','poissonSegments',1);if(count>1)this._recordFrontCandidate((segment.x0+segment.x1)/2,(segment.y0+segment.y1)/2,'boundaryLow','multiProposalSegments',1);
        for(let k=0;k<count;k++){const {x,y}=this._boundaryPosition(segment,rng(),rng()),gate=this._boundaryEventGate(segment.boundary,x,y,bg),accept=rng(),priority=rng(),id='flux:'+step+':'+segment.key+':'+k;propose(x,y,0,gate,accept,priority,id,'boundaryLow',segment);if(k%32===31)yield;}yield;
      }
      events.sort((a,b)=>this.config.upstreamSourceBlocking?(this._sourceOrder(a,b,bg)||a.priority-b.priority):a.priority-b.priority||(flux?a.id.localeCompare(b.id):0));
      const recent=new Map(),bin=4000,add=c=>{const key=Math.floor(c.x/bin)+','+Math.floor(c.y/bin);if(!recent.has(key))recent.set(key,[]);recent.get(key).push(c);};for(const c of this.cells)if(c.age<600)add(c);
      for(const e of events){
        if(!this._birthRegionAllowed(e.x,e.y))continue;
        if(!e.triggerSource&&this._southernColdBarrier(e.x,e.y)){this.stats.southernColdBlockedBirths=(this.stats.southernColdBlockedBirths||0)+1;continue;}
        if(!e.triggerSource&&this._upstreamSource(e.x,e.y,bg)){
          this.stats.upstreamBlockedBirths=(this.stats.upstreamBlockedBirths||0)+1;
          
          continue;
        }
        const sourceBlocked=!e.triggerSource&&!e.layer&&this.config.persistentInitiation&&this.triggerSources.some(s=>(s.x-e.x)**2+(s.y-e.y)**2<8000**2),ix=Math.floor(e.x/bin),iy=Math.floor(e.y/bin);let blocked=sourceBlocked;for(let yy=iy-1;yy<=iy+1&&!blocked;yy++)for(let xx=ix-1;xx<=ix+1&&!blocked;xx++)for(const c of recent.get(xx+','+yy)||[])if((c.x-e.x)**2+(c.y-e.y)**2<bin*bin){blocked=true;break;}
        if(blocked&&!e.triggerSource){this.stats.spacingRejected++;diagnostic.byLayer[e.layer?'mid':'low'].spacingRejected++;if(this._organizationContains(e.x,e.y))diagnostic.local.byLayer[e.layer?'mid':'low'].spacingRejected++;this._recordFrontCandidate(e.x,e.y,e.channel,'spacingRejected',1);if(e.inBand)this._recordFrontCandidate(e.x,e.y,e.channel,'inBandSpacingRejected',1);continue;}
        const rng=random(hash(this.config.seed,'cell',e.id)),c={id:e.id,born:e.born??(this.t+DT*random(hash(this.config.seed,'birth-time',e.id))()),age:0,x:e.x,y:e.y,T:9360,major:1800,minor:1200,updraftArea:Math.PI*1000**2,starvedSeconds:0,supplyRatio:0,a:0,M:0,convectivePhaseEnergyJ:0,layer:e.layer,source:e.gate.source,parent:e.gate.parent,channel:e.channel,segmentKey:e.segmentKey,physicalFaceId:e.physicalFaceId,angle:Math.atan2(...this.steer().slice().reverse()),phase:rng()*Math.PI*2};
        if(this.config.monsoon925){const k=this.env.index(c.x,c.y);c.vx=this.fields.um[k];c.vy=this.fields.vm[k];c.angle=Math.atan2(c.vy,c.vx);}
        if(!e.layer&&this.config.persistentInitiation){
          const source=e.triggerSource||{id:'root:'+c.id,x:c.x,y:c.y,activated:c.born,lastBirth:c.born};
          if(!e.triggerSource)this.triggerSources.push(source);else this.stats.persistentBirths=(this.stats.persistentBirths||0)+1;
          source.lastBirth=c.born;c.triggerSourceId=source.id;
        }
        if(c.triggerSourceId&&this.config.connectedTrainingFeed)c.phase=random(hash(this.config.seed,'train-phase',c.triggerSourceId))()*2*Math.PI;
        this._ensurePulse(c);this.cells.push(c);add(c);this.stats.births++;diagnostic.byLayer[e.layer?'mid':'low'].births++;if(this._organizationContains(c.x,c.y))diagnostic.local.byLayer[e.layer?'mid':'low'].births++;if(c.source==='coldPool')this.stats.coldBirths++;if(e.layer)this.stats.elevatedBirths++;this._recordFrontCandidate(e.x,e.y,e.channel,'births',1);if(e.inBand)this._recordFrontCandidate(e.x,e.y,e.channel,'inBandBirths',1);
        this.events.push({id:c.id,triggerSourceId:c.triggerSourceId??null,t:c.born,x:c.x,y:c.y,layer:c.layer,source:c.source,channel:c.channel,segmentKey:c.segmentKey,physicalFaceId:c.physicalFaceId,initialMassKg:0,initialConvectivePhaseEnergyJ:0,convectiveHeating:this.config.convectiveHeating,Kenv:e.gate.power,Kcp:e.gate.coldPower,parent:c.parent,triggerEvidence:e.gate.evidence,pulse:c.pulse?{...c.pulse}:null,cellLifecycle:this.config.cellLifecycle,coldDominant:e.gate.coldPower>e.gate.power,vx:this.fields.um[this.env.index(c.x,c.y)],vy:this.fields.vm[this.env.index(c.x,c.y)]});
      }
      this.stats.triggerTotals??={low:{poissonMean:0,candidates:0,expectedAcceptedGivenCandidates:0,acceptedBeforeSpacing:0,spacingRejected:0,births:0},mid:{poissonMean:0,candidates:0,expectedAcceptedGivenCandidates:0,acceptedBeforeSpacing:0,spacingRejected:0,births:0}};for(const layer of ['low','mid'])for(const key of Object.keys(this.stats.triggerTotals[layer]))this.stats.triggerTotals[layer][key]+=diagnostic.byLayer[layer][key];while(this.events.length>20000)this.events.splice(0,1000);
    }
    *kernel(grid,x,y,major,minor,angle,normalize=true){const ca=Math.cos(angle),sa=Math.sin(angle),radius=2*Math.max(major,minor),i0=Math.floor((x-radius)/grid.dx),i1=Math.floor((x+radius)/grid.dx),j0=Math.floor((y-radius)/grid.dx),j1=Math.floor((y+radius)/grid.dx),items=[];let total=0;
      let kernelYieldAt=performance.now();for(let j=j0;j<=j1;j++){for(let i=i0;i<=i1;i++){let p=0;const samples=grid.dx>=5000?4:grid.dx>=2500?2:1;for(let b=0;b<samples;b++)for(let a=0;a<samples;a++){const dx=(i+(a+.5)/samples)*grid.dx-x,dy=(j+(b+.5)/samples)*grid.dx-y,s=ca*dx+sa*dy,n=-sa*dx+ca*dy,r=(s/major)**2+(n/minor)**2;if(r<=4)p+=Math.exp(-4*Math.LN2*r)/(samples*samples);}if(p===0)continue;total+=p*grid.area;const k=i>=0&&j>=0&&i<grid.nx&&j<grid.ny?j*grid.nx+i:-1;items.push([k,p*grid.area]);}if(j%8===7||performance.now()-kernelYieldAt>4){kernelYieldAt=performance.now();yield;}}if(normalize)for(const item of items)item[1]/=total;return items;
    }
    *evolveCells(){
      this._beginConvectiveEnergyStep();
      yield*this.updateSurfaceFractions();
      const bucket=()=>({potentialKg:0,eligibleWeightKg:0,requestedKg:0,suppliedKg:0,areaPhiM2:0}),aggregate={requestedKg:0,suppliedKg:0,unallocatedDemandKg:0,lowCold:bucket(),lowWarm:bucket(),midCold:bucket(),midWarm:bucket()};this.supplyDiagnostics={schema:'surface-supply-1.7',stepSeconds:DT,global:aggregate,surfaceAccessMode:this.config.surfaceAccessMode,cellLifecycle:this.config.cellLifecycle,bucketMeaning:this.config.surfaceAccessMode==='consistent'?'lowWarm/midWarm = accessible phi footprint; lowCold/midCold = inaccessible phi footprint, middle supply is not vetoed by surface access.':'Legacy whole-environment-cell Q classification.',rule:this.config.surfaceAccessMode==='consistent'?'Available-column weights share capacity; demand fractions use the full low/mid potential. Blocked low demand is unallocated, never reassigned to the middle layer. Surface-fed cells lose support after sustained warm-feed cutoff.':'Legacy env-mean Q<20 weights and whole-cell capacity.'};
      const g=this.env,f=this.fields,fallback=this.steer(this.t+DT/2),requests=[],totalL=this.buffer('demandL',g.n),totalM=this.buffer('demandM',g.n),living=[];
      totalL.fill(0);totalM.fill(0);
      for(const c of this.cells){
        const dt=Math.min(DT,Math.max(0,this.t+DT-c.born));c.activeStepSeconds=dt;if(dt===0){living.push(c);continue;}
        const at=g.index(c.x,c.y),relax=1-Math.exp(-dt/420),u=at<0?fallback[0]:f.um[at],v=at<0?fallback[1]:f.vm[at],oldU=c.vx??fallback[0],oldV=c.vy??fallback[1];
        c.stepStartX=c.x;c.stepStartY=c.y;c.x+=u*dt+(oldU-u)*420*relax;c.y+=v*dt+(oldV-v)*420*relax;
        c.vx=oldU+(u-oldU)*relax;c.vy=oldV+(v-oldV)*relax;c.age+=dt;c.angle=Math.atan2(c.vy,c.vx);
        if(g.index(c.x,c.y)<0){this._recordDeath(c,'domain_exit',c.M,{destination:'domain_boundary',massKg:c.M});this.stats.outflow+=c.M;this.stats.sources.coreBoundaryOut=(this.stats.sources.coreBoundaryOut||0)+c.M;this.recordWater('core','out','boundary',c.M);c.M=0;c.a=0;c.lifecycle='dead';continue;}
        if(c.age>=c.T||(c.starvedSeconds||0)>=1200){const reason=c.age>=c.T?'maximum_age_protection':(c.supportLostSeconds||0)>=1200?'thermal_or_updraft_support_lost':'starvation';this._recordDeath(c,reason,c.M,{destination:'fine_grid_Qa',massKg:c.M});yield*this.detrainCell(c);c.lifecycle='dead';c.a=0;continue;}
        const local=g.index(c.x,c.y),rx=f.u[local]-c.vx,ry=f.v[local]-c.vy,speed=Math.hypot(rx,ry);let ix=c.x-(speed>=1?8000*rx/speed:0),iy=c.y-(speed>=1?8000*ry/speed:0),angle=speed>=1?Math.atan2(ry,rx):c.angle;
        const connected=c.triggerSourceId&&this.config.connectedTrainingFeed?this._movingTrainingFeed(c):null;
        if(connected?.accessible){ix=connected.x;iy=connected.y;angle=connected.angle;}
        c.supplyInlet={x:ix,y:iy,relativeWind:{x:rx,y:ry},samplingAngle:angle,connectedFeed:connected,footMajor:30000,footMinor:18000,surfaceAccess:this.surfaceAccess(ix,iy),accessMode:this.config.surfaceAccessMode};
        const foot=yield*this.supplyFootprint(ix,iy,30000,18000,angle),chiL=c.layer?.2:.8,chiM=1-chiL,eligible=[];
        const footprint={lowCold:bucket(),lowWarm:bucket(),midCold:bucket(),midWarm:bucket(),meanFineColdFraction:0,unallocatedDemandKg:0};c.supplyBreakdown=footprint;let weight=0,potentialWeight=0,lowPotential=0,lowAccessible=0,area=0,energy=0,humidity=0,qin=0;
        for(const [i,a,aw]of foot){if(i<0)continue;area+=a;energy+=a*(chiL*f.el[i]+chiM*f.em[i]);humidity+=a*(chiL*f.rhL[i]+chiM*f.rhM[i]);qin+=a*(chiL*f.wl[i]/1400+chiM*f.wm[i]/2600);
          const excessL=Math.max(f.wl[i]-.65*f.sl[i],0),excessM=Math.max(f.wm[i]-.45*f.sm[i],0),l=f.el[i]>=.15?chiL*aw*excessL:0,m=f.em[i]>=.15?chiM*a*excessM:0;
          for(const [cold,ap]of [[false,aw],[true,Math.max(0,a-aw)]]){const low=footprint[cold?'lowCold':'lowWarm'],mid=footprint[cold?'midCold':'midWarm'],lp=cold?0:l,mp=m*ap/a;low.potentialKg+=chiL*ap*excessL;mid.potentialKg+=chiM*ap*excessM;low.eligibleWeightKg+=lp;mid.eligibleWeightKg+=mp;low.areaPhiM2+=ap;mid.areaPhiM2+=ap;if(lp+mp>0)eligible.push([i,lp,mp,cold]);}
          footprint.meanFineColdFraction+=a*f.coldFraction[i];weight+=l+m;potentialWeight+=chiL*a*excessL+chiM*a*excessM;lowPotential+=chiL*a*excessL;lowAccessible+=chiL*aw*excessL;
        }
        footprint.meanFineColdFraction=area?footprint.meanFineColdFraction/area:0;energy=area?energy/area:0;humidity=area?humidity/area:0;qin=area?qin/area:0;
        const thermal=clip((energy-.15)/.65)*clip((humidity-.5)/.4),seedArea=Math.PI*1000**2;
        c.updraftArea=c.updraftArea??seedArea;
        c.updraftVelocity=thermal>0?1+(this.config.organizedWarmSector?20:this.config.jetExitControl?16:12)*Math.sqrt(thermal):0;c.thermalPotential=thermal;
        if(this._advancePulse(c,thermal,dt)){c.effectiveUpdraftArea=0;c.updraftAirMassFlux=0;this._recordDeath(c,'pulse_completed',c.M,{destination:'fine_grid_Qa',massKg:c.M});yield*this.detrainCell(c);continue;}
        c.physicalUpdraftArea=c.updraftArea;c.effectiveUpdraftArea=c.physicalUpdraftArea*c.pulseEnvelope;
        c.updraftAirMassFlux=c.effectiveUpdraftArea*c.updraftVelocity; // rho = 1 kg/m3
        c.requestedKgThisStep=c.updraftAirMassFlux*Math.max(qin-saturation(273.15,1,75000),0)*dt;
        c.suppliedKgThisStep=0;c.requestedLKgThisStep=0;c.requestedMKgThisStep=0;c.suppliedLKgThisStep=0;c.suppliedMKgThisStep=0;c.thermalPotential=thermal;c.shear=Math.hypot(rx,ry);
        if(weight>0)for(const [i,l,m,cold]of eligible){const dl=c.requestedKgThisStep*l/potentialWeight,dm=c.requestedKgThisStep*m/potentialWeight;totalL[i]+=dl;totalM[i]+=dm;requests.push([c,i,dl,dm,cold]);c.requestedLKgThisStep+=dl;c.requestedMKgThisStep+=dm;footprint[cold?'lowCold':'lowWarm'].requestedKg+=dl;footprint[cold?'midCold':'midWarm'].requestedKg+=dm;}footprint.unallocatedDemandKg=c.requestedKgThisStep*(potentialWeight>0?1-clip(weight/potentialWeight):1);c.lowWarmAccessFraction=lowPotential>0?clip(lowAccessible/lowPotential):0;
        living.push(c);yield;
      }
      this.cells=living;
      const scaleL=this.buffer('scaleL',g.n),scaleM=this.buffer('scaleM',g.n),fraction=1-Math.exp(-DT/600);
      for(let i=0;i<g.n;i++){
        f.supplyCapL[i]=g.area*(this.config.surfaceAccessMode==='consistent'?f.warmAccessibleFraction[i]:1)*Math.max(f.wl[i]-.65*f.sl[i],0)*fraction;f.supplyCapM[i]=g.area*Math.max(f.wm[i]-.45*f.sm[i],0)*fraction;
        scaleL[i]=totalL[i]>0?Math.min(1,f.supplyCapL[i]/totalL[i]):0;
        scaleM[i]=totalM[i]>0?Math.min(1,f.supplyCapM[i]/totalM[i]):0;
      }
      const usedL=this.buffer('usedL',g.n),usedM=this.buffer('usedM',g.n);usedL.fill(0);usedM.fill(0);
      let count=0;for(const [c,i,l,m,cold]of requests){const a=l*scaleL[i],b=m*scaleM[i];usedL[i]+=a;usedM[i]+=b;c.M+=a+b;c.suppliedKgThisStep+=a+b;c.suppliedLKgThisStep+=a;c.suppliedMKgThisStep+=b;c.supplyBreakdown[cold?'lowCold':'lowWarm'].suppliedKg+=a;c.supplyBreakdown[cold?'midCold':'midWarm'].suppliedKg+=b;c.supplied=(c.supplied||0)+a+b;if(++count%2000===0)yield;}
      for(const c of living){const dt=c.activeStepSeconds;if(!dt)continue;
        this._advanceConvectiveEnergy(c,dt);
        const ratio=c.requestedKgThisStep>0?clip(c.suppliedKgThisStep/c.requestedKgThisStep):0;
        c.instantSupplyRatio=ratio;c.supplyRatio=ratio+((c.supplyRatio??0)-ratio)*Math.exp(-dt/360);
        const surfaceFeedLost=c.layer===0&&(c.lowWarmAccessFraction<.1||(c.supplyInlet?.connectedFeed&&!c.supplyInlet.connectedFeed.accessible));
        c.starvedSeconds=ratio<.2||surfaceFeedLost?(c.starvedSeconds||0)+dt:Math.max(0,(c.starvedSeconds||0)-2*dt);c.starved=c.starvedSeconds;
        const pulseDecay=this.config.cellLifecycle==='pulse'&&c.pulse.N>=c.pulse.Ndecay;
        c.lifecycle=c.starvedSeconds>=600||pulseDecay?'decaying':this.config.cellLifecycle==='pulse'?(c.pulse.N<c.pulse.Ngrow?'growing':'mature'):c.age<600?'growing':'mature';
        const target=c.starvedSeconds>=600?0:c.thermalPotential*c.supplyRatio*c.pulseEnvelope*(this.config.cellLifecycle==='legacy'?Math.min(1,c.age/600):1);
        c.a=target+(c.a-target)*Math.exp(-dt/(target>c.a?180:240));
        const areaTarget=Math.PI*1000**2+((this.config.organizedWarmSector?1.55:1)*Math.PI*(this.config.organizedWarmSector?1900+5200*c.thermalPotential:1500+4000*c.thermalPotential)**2-Math.PI*1000**2)*clip(c.a*c.supplyRatio);
        c.updraftArea=areaTarget+(c.updraftArea-areaTarget)*Math.exp(-dt/180);
        const growth=Math.sqrt(clip(c.a*c.supplyRatio)),stretch=1+.4*clip(c.shear/15),major=(1800+5200*growth)*stretch,minor=(this.config.organizedWarmSector?2600:1200)+(this.config.organizedWarmSector?6200:3000)*growth;
        c.major=major+(c.major-major)*Math.exp(-dt/180);c.minor=minor+(c.minor-minor)*Math.exp(-dt/180);
        c.supportLostSeconds=surfaceFeedLost||c.thermalPotential<=0||c.updraftVelocity<=0?(c.supportLostSeconds||0)+dt:0;c.lastSupplyStepEnd=this.t+DT;c.condensationRate=c.suppliedKgThisStep/dt;aggregate.requestedKg+=c.requestedKgThisStep;aggregate.suppliedKg+=c.suppliedKgThisStep;aggregate.unallocatedDemandKg+=c.supplyBreakdown.unallocatedDemandKg;for(const name of ['lowCold','lowWarm','midCold','midWarm'])for(const key of Object.keys(aggregate[name]))aggregate[name][key]+=c.supplyBreakdown[name][key];
      }
      for(let i=0;i<g.n;i++){
        f.supplyUsedL[i]=usedL[i];f.supplyUsedM[i]=usedM[i];const l=usedL[i]/g.area,m=usedM[i]/g.area;f.wl[i]-=l;f.wm[i]-=m;if(this.config.convectiveHeating==='local_latent'){f.tl[i]+=2.5e6*l/(1004*1400);f.tm[i]+=2.5e6*m/(1004*2600);}
        this.recordWater('vaporL','out','cellCondensation',usedL[i]);this.recordWater('vaporM','out','cellCondensation',usedM[i]);this.recordWater('core','in','cellCondensation',usedL[i]+usedM[i]);
        this.stats.sources.cellCondensed+=usedL[i]+usedM[i];this.stats.sources.latentHeating+=(usedL[i]+usedM[i])*2.5e6;
        // Dimensionless instability recovers with incoming air; condensation
        // still removes its exact water and carries the corresponding latent heat.
        f.el[i]=Math.max(0,f.el[i]-l/(this.config.jetExitControl?24:12));f.em[i]=Math.max(0,f.em[i]-m/(this.config.jetExitControl?20:10));this.stats.condensed+=usedL[i]+usedM[i];f.sl[i]=saturation(f.tl[i]);f.sm[i]=saturation(f.tm[i],2600,75000);f.rhL[i]=f.wl[i]/f.sl[i];f.rhM[i]=f.wm[i]/f.sm[i];
      }
      this.stats.supplyTotals??={requestedKg:0,suppliedKg:0,unallocatedDemandKg:0,requestedLowKg:0,requestedMidKg:0,suppliedLowKg:0,suppliedMidKg:0};for(const key of ['requestedKg','suppliedKg','unallocatedDemandKg'])this.stats.supplyTotals[key]+=aggregate[key];this.stats.supplyTotals.requestedLowKg+=aggregate.lowCold.requestedKg+aggregate.lowWarm.requestedKg;this.stats.supplyTotals.requestedMidKg+=aggregate.midCold.requestedKg+aggregate.midWarm.requestedKg;this.stats.supplyTotals.suppliedLowKg+=aggregate.lowCold.suppliedKg+aggregate.lowWarm.suppliedKg;this.stats.supplyTotals.suppliedMidKg+=aggregate.midCold.suppliedKg+aggregate.midWarm.suppliedKg;this.stats.maxCells=Math.max(this.stats.maxCells,this.cells.length);
    }
    addRain(index,mass,convective=false){if(index<0){this.stats.outflow+=mass;return;}this.rainStep[index]+=mass/this.rain.area;if(convective)this.convectiveStep[index]+=mass/this.rain.area;this.activeRain.add(index);this.stats.ground+=mass;}
    *advance(){
      if(this.t>=this.config.hours*3600)return;
      for(const key of ['flow','humidity'])this.controls[key]=this.targets[key]+(this.controls[key]-this.targets[key])*Math.exp(-DT/600);
      for(const i of this.activeRain){this.rainStep[i]=0;this.convectiveStep[i]=0;}this.activeRain.clear();
      this._coldKinematicsReady=false;this._updateMesoscaleLifecycle();yield* this.updateForcing();yield* this.transportWater();yield* this.advanceCold();yield* this.diagnoseEnvironment(true);yield* this.buildBoundaries();yield*this._diagnoseTriggerWindows();if(!this.config.disableBirths)yield* this.initiate();this._commitFrontDiagnostics();yield* this.evolveCells();yield* this.release();this.t+=DT;this.stats.steps++;this._commitTriggerWindows();
      this.check();
    }
    step(){const it=this.advance();while(!it.next().done){}return this.t;}
    water(){const f=this.fields;let mass=0;for(let i=0;i<this.env.n;i++)mass+=(f.wl[i]+f.wm[i]+f.ls[i]+f.qcL[i]+f.qcM[i])*this.env.area;for(const c of this.cells)mass+=c.M;return mass;}
    audit(){const water=this.water(),expected=this.initialWater+this.stats.inflow+this.stats.surface-this.stats.outflow-this.stats.ground+this.stats.repair,residual=water-expected,denominator=this.initialWater+this.stats.inflow+this.stats.surface,volume=sum(this.h)*this.cold.area,heat=sum(this.q)*this.cold.area;return {water,expected,residual,relativeResidual:Math.abs(residual)/Math.max(1,denominator),activityResidual:Math.abs(residual)/Math.max(1,this.stats.condensed+this.stats.evaporated+this.stats.ground+this.stats.inflow+this.stats.outflow),coldVolumeResidual:volume-this.initialColdVolume-this.stats.coldVolumeSource+this.stats.coldVolumeLoss,coldHeatResidual:heat-this.initialColdHeat-this.stats.coldHeatSource+this.stats.coldHeatLoss};}
    check(){if(this.config.coldDynamics==='inertial'){for(let k=0;k<this.cold.n;k++)if(!Number.isFinite(this.Px[k])||!Number.isFinite(this.Py[k]))throw Error('冷层动量非有限');const a=ColdLayer.audit(this._coldState(),this.cold,this.coldMomentumLedger),scale=1+this.coldMomentumLedger.transportActivity+this.coldMomentumLedger.sourceActivity;if(Math.abs(a.residual.x)+Math.abs(a.residual.y)>1e-7*scale)throw Error('等效冷层动量账超限');}for(const key of ['wl','wm','ls','qcL','qcM'])for(const x of this.fields[key])if(!Number.isFinite(x)||x<-1e-8)throw Error(key+'非负性检查失败');for(let i=0;i<this.cold.n;i++)if(!Number.isFinite(this.q[i])||this.q[i]<-1e-8||this.h[i]<-1e-9||this.q[i]>THETA*this.h[i]+1e-7)throw Error('冷池比例/非负性失败');for(let i=0;i<this.env.n;i++)if(this.fields.wl[i]>this.fields.sl[i]+1e-8)throw Error('联立源后超饱和');for(const c of this.cells){if(c.M<-1e-7||!Number.isFinite(c.M))throw Error('单体质量非法');if(!Number.isFinite(c.convectivePhaseEnergyJ)||c.convectivePhaseEnergyJ<0)throw Error('对流柱能量非法');}const ec=this.convectiveEnergyAudit();if(ec.relativeResidual>1e-8)throw Error('对流柱能量子过程账超限 '+ec.residual);const a=this.audit();if(a.relativeResidual>1e-6)throw Error('水量收支超限 '+a.relativeResidual);return a;}
    update(controls,commandId){for(const key of ['flow','humidity'])if(Number.isFinite(controls[key]))this.targets[key]=key==='flow'?Math.max(.4,Math.min(1.8,controls[key])):Math.max(-.2,Math.min(.1,controls[key]));this.operationLog.push({t:this.t,commandId,controls:Object.assign({},this.targets)});return this.t;}
    productGrid(qualityOrDx=this.config.quality){const dx=PRODUCTS[qualityOrDx]?.dx??qualityOrDx;validateGridExtent(this.config.width,this.config.height,dx);return new Grid(this.config.width,this.config.height,dx);}
    *projectProducts(productGrid=this.output){
      validateProjection(this.precip,productGrid);const pg=this.precip,P=this.precipWater,zlow=new Float64Array(pg.n),zcomp=new Float64Array(pg.n);
      for(let k=0;k<pg.n;k++){const low=P.lower_core[k]+P.lower_detrained[k]+P.lower_boundary[k],high=P.upper_core[k]+P.upper_detrained[k]+P.upper_boundary[k];zlow[k]=liquidReflectivity(low);zcomp[k]=Math.max(zlow[k],liquidReflectivity(high));if(k%2048===2047)yield;}
      const lowZ=yield*areaMeanSteps(zlow,pg,productGrid),compositeZ=yield*areaMeanSteps(zcomp,pg,productGrid),rainRate=yield*areaMeanSteps(this.rainStep,this.rain,productGrid,3600/DT),rainTotal=yield*areaMeanSteps(this.rainTotal,this.rain,productGrid);
      return {grid:productGrid,lowZ,compositeZ,rainRate,rainTotal};
    }
    *snapshot(buffer,productGrid=this.output){
      const products=yield*this.projectProducts(productGrid),g=productGrid,n=g.n;if(!buffer||buffer.byteLength!==8*n)buffer=new ArrayBuffer(8*n);
      const low=new Uint8Array(buffer,0,n),composite=new Uint8Array(buffer,n,n),rain=new Uint16Array(buffer,2*n,n),total=new Uint32Array(buffer,4*n,n);let maxRate=0,maxTotal=0,wetArea=0,strongArea=0;
      for(let k=0;k<n;k++){
        const rate=products.rainRate[k],acc=products.rainTotal[k],z=products.lowZ[k],cz=products.compositeZ[k],dbz=z>0?10*Math.log10(z):-Infinity,upper=cz>0?10*Math.log10(cz):-Infinity;
        if(rate>6553.4||acc>42949672.94||dbz>117||upper>117)throw Error('输出产品超出编码范围');low[k]=dbz>=-10?Math.round((dbz+10)*2):255;composite[k]=upper>=-10?Math.round((upper+10)*2):255;rain[k]=Math.round(rate*10);total[k]=Math.round(acc*100);maxRate=Math.max(maxRate,rate);maxTotal=Math.max(maxTotal,acc);if(rate>=.1)wetArea+=g.area/1e6;if(dbz>=40)strongArea+=g.area/1e6;if(k%2048===2047)yield;
      }
      const windBuffer=new ArrayBuffer(this.env.n*8),windU=new Float32Array(windBuffer,0,this.env.n),windV=new Float32Array(windBuffer,this.env.n*4,this.env.n);windU.set(this.fields.u);windV.set(this.fields.v);const windGrid={nx:this.env.nx,ny:this.env.ny,dx:this.env.dx,width:this.config.width,height:this.config.height,buffer:windBuffer};
      const cg=this.cold,cn=cg.n,coldBuffer=new ArrayBuffer(cn*16),depth=new Float32Array(coldBuffer,0,cn),deficit=new Float32Array(coldBuffer,cn*4,cn),outflowU=new Float32Array(coldBuffer,cn*8,cn),outflowV=new Float32Array(coldBuffer,cn*12,cn);let coldArea=0;
      depth.set(this.h);for(let k=0;k<cn;k++){deficit[k]=this.h[k]>0?this.q[k]/this.h[k]:0;const A=this.q[k]/THETA;outflowU[k]=A>=ColdLayer.DRY?this.Px[k]/A:0;outflowV[k]=A>=ColdLayer.DRY?this.Py[k]/A:0;if(this.h[k]>=40&&this.q[k]>=20&&deficit[k]>=.3)coldArea+=cg.area/1e6;if(k%4096===4095)yield;}
      const coldGrid={nx:cg.nx,ny:cg.ny,dx:cg.dx,width:cg.width,height:cg.height,buffer:coldBuffer,encoding:'Float32 depth_m, deficit_K, relative_outflow_u_ms, relative_outflow_v_ms; sequential arrays'};
      const triggerBuffer=new ArrayBuffer(this.env.n*12),triggerGrid={nx:this.env.nx,ny:this.env.ny,dx:this.env.dx,width:this.config.width,height:this.config.height,buffer:triggerBuffer,encoding:'Float32 elevation_m, windward_displacement_m, environment_initiation_probability; sequential arrays'};
      const elevation=new Float32Array(triggerBuffer,0,this.env.n),terrainLift=new Float32Array(triggerBuffer,this.env.n*4,this.env.n),trigger=new Float32Array(triggerBuffer,this.env.n*8,this.env.n);elevation.set(this.fields.z);const bg=this.background();
      for(let k=0;k<this.env.n;k++){terrainLift[k]=this.fields.xiTerrain[k]*this.fields.inflowFocus[k];trigger[k]=this.gate((k%this.env.nx+.5)*this.env.dx,(Math.floor(k/this.env.nx)+.5)*this.env.dx,0,bg,true).F;if(k%2048===2047)yield;}
      const wind=[];for(let j=4;j<this.env.ny;j+=Math.max(1,Math.round(60000/this.env.dx)))for(let i=4;i<this.env.nx;i+=Math.max(1,Math.round(60000/this.env.dx))){const k=j*this.env.nx+i;wind.push([(i+.5)*this.env.dx,(j+.5)*this.env.dx,this.fields.u[k],this.fields.v[k]]);}return {buffer,wind,windGrid,coldGrid,triggerGrid,simTime:this.t,physicsMesh:{...this.physicsMesh},productMesh:{...this.productMesh,dx:g.dx,quality:g.dx===this.output.dx?this.config.quality:'explicit'},metrics:{maxRate,maxTotal,wetArea,strongArea,coldArea,cells:this.cells.length,births:this.stats.births,coldBirths:this.stats.coldBirths,...this.audit()},stats:Object.assign({},this.stats),convectiveEnergy:this.convectiveEnergyAudit()};
    }
    getSnapshot(buffer,productGrid=this.output){const it=this.snapshot(buffer,productGrid);let r;do{r=it.next();}while(!r.done);return r.value;}
    checkpoint(){const arrays={};for(const [key,a]of Object.entries(this.fields))arrays['field_'+key]=a.slice();for(const [key,a]of Object.entries(this.mechanismFields))arrays['mechanism_'+key]=a.slice();arrays.h=this.h.slice();arrays.q=this.q.slice();arrays.rainStep=this.rainStep.slice();arrays.convectiveStep=this.convectiveStep.slice();arrays.rainTotal=this.rainTotal.slice();for(const k of ['cvx','cvy','coutx','couty','Px','Py','coldRhsH','coldRhsQ','coldWaveLX','coldWaveRX','coldWaveLY','coldWaveRY','coldPhaseX','coldPhaseY','coldPhaseRawX','coldPhaseRawY','coldPhaseControlX','coldPhaseControlY'])arrays[k]=this[k].slice();return Object.assign(structuredClone({version:VERSION,config:this.config,physicsMesh:this.physicsMesh,productMesh:this.productMesh,t:this.t,initialWater:this.initialWater,initialColdVolume:this.initialColdVolume,initialColdHeat:this.initialColdHeat,stats:this.stats,controls:this.controls,targets:this.targets,operationLog:this.operationLog,triggerSources:this.triggerSources,cells:this.cells,events:this.events,lifeEvents:this.lifeEvents,forcingEvents:this.forcingEvents,forcingEventStates:this.forcingEventStates,triggerDiagnostics:this.triggerDiagnostics,supplyDiagnostics:this.supplyDiagnostics,frontDiagnostics:this.frontDiagnostics,frontTotals:this.frontTotals,windowDiagnostics:this.windowDiagnostics,windowTotals:this.windowTotals,coldMomentumLedger:this.coldMomentumLedger,coldKinematicDiagnostics:this.coldKinematicDiagnostics,ledger:this.ledger,heatBudget:this.heatBudget,convectiveEnergyBudget:this.convectiveEnergyBudget,convectiveEnergyDiagnostics:this.convectiveEnergyDiagnostics,forcingInterpolation:this.forcingInterpolation}),{arrays,terrainHash:this.terrain?.meta.binarySha256||'idealized'});}
    static restore(checkpoint,terrain){
      checkpointRecord(checkpoint,'checkpoint');
      if(checkpoint.version!==VERSION)throw Error('检查点模型版本不匹配');
      if(typeof checkpoint.terrainHash!=='string')checkpointFail('terrainHash','缺少地形指纹');
      if(checkpoint.terrainHash!==(terrain?.meta.binarySha256||'idealized'))throw Error('检查点地形版本不匹配');
      checkpointRecord(checkpoint.config,'config');checkpointFiniteTree(checkpoint.config,'config');
      // Constructor normalization must never mutate a failed caller-owned checkpoint.
      const model=new Model(structuredClone(checkpoint.config),terrain);
      for(const name of ['physicsMesh','productMesh'])if(!sameMesh(checkpoint[name],model[name]))throw Error('检查点网格版本不匹配 '+name);
      const targets=validateCheckpoint(checkpoint,model);model.mechanismFields={};
      for(const [key,target]of Object.entries(targets))target.set(checkpoint.arrays[key]);
      for(const [key,a]of Object.entries(checkpoint.arrays))if(key.startsWith('mechanism_'))model._mechanismBuffer(key.slice(10),a.length).set(a);
      for(const key of CHECKPOINT_STATE_KEYS)model[key]=structuredClone(checkpoint[key]);
      for(const key of CHECKPOINT_OPTIONAL_KEYS)model[key]=Object.hasOwn(checkpoint,key)?structuredClone(checkpoint[key]):null;
      validateRestoredInventories(model);if(model.t>0)model._initialForcingCache=null;
      for(let i=0;i<model.rainStep.length;i++)if(model.rainStep[i]>0)model.activeRain.add(i);
      return model;
    }
  }

  Model.prototype._coldState=function(){return {h:this.h,q:this.q,px:this.Px,py:this.Py};};
  // Evaporation is accepted by the existing thermodynamic solve. Only its spatial
  // deposition and the horizontal momentum of descending air are handled here.
  Model.prototype._addColdSource=function(k,dh,dQ,e){
    this.h[k]+=dh;this.q[k]+=dQ;
    if(this.config.coldDynamics!=='inertial'||this.config.coldMomentumCoupling!=='surface_drag')return;
    const g=this.cold,i=k%g.nx,j=Math.floor(k/g.nx),u=.5*(this.cu[j*(g.nx+1)+i]+this.cu[j*(g.nx+1)+i+1]),v=.5*(this.cv[j*g.nx+i]+this.cv[(j+1)*g.nx+i]);
    const px=dQ/THETA*(this.fields.um[e]-u),py=dQ/THETA*(this.fields.vm[e]-v);
    this.Px[k]+=px;this.Py[k]+=py;this.coldMomentumLedger.source.x+=px*g.area;this.coldMomentumLedger.source.y+=py*g.area;this.coldMomentumLedger.sourceActivity+=(Math.abs(px)+Math.abs(py))*g.area;
  };
  Model.prototype._depositColdEvaporation=function*(requests,accepted,envIndex){
    const pg=this.precip,cg=this.cold;
    if(!this._coldRainOverlap){
      const index=new Int32Array(pg.n*4).fill(-1),area=new Float64Array(pg.n*4);
      for(let k=0;k<pg.n;k++){
        const x0=k%pg.nx*pg.dx,y0=Math.floor(k/pg.nx)*pg.dx,x1=x0+pg.dx,y1=y0+pg.dx;let slot=4*k;
        for(let j=Math.floor(y0/cg.dx);j<Math.ceil(y1/cg.dx);j++)for(let i=Math.floor(x0/cg.dx);i<Math.ceil(x1/cg.dx);i++){
          index[slot]=j*cg.nx+i;area[slot]=(Math.min(x1,(i+1)*cg.dx)-Math.max(x0,i*cg.dx))*(Math.min(y1,(j+1)*cg.dx)-Math.max(y0,j*cg.dx));slot++;
        }
        if(k%2048===2047)yield;
      }this._coldRainOverlap={index,area};
    }
    const {index,area}=this._coldRainOverlap;
    for(let k=0;k<pg.n;k++){
      const e=envIndex[k],slot=7*k,mass=(requests[slot+2]+requests[slot+4]+requests[slot+6])*accepted[e];
      if(mass>0){const qArea=ALPHA*mass/pg.area;for(let j=4*k;j<4*k+4;j++)if(index[j]>=0){const dQ=qArea*area[j]/cg.area;this._addColdSource(index[j],dQ/THETA,dQ,e);}}
      if(k%2048===2047)yield;
    }
  };
  Model.prototype._coldSolverFor=function(){if(!this._coldSolver)this._coldSolver=new ColdLayer.Solver(this.cold,this.cz,this.cu,this.cv,{boundary:this.config.coldBoundary||'open',backend:this._numericBackend});this._coldSolver.options.boundary=this.config.coldBoundary||'open';return this._coldSolver;};
  const advanceColdLegacy=Model.prototype.advanceCold;
  Model.prototype.advanceCold=function*(mix=true){
    this._coldKinematicsReady=false;this._coldIntegratedUntil=this.t+DT;if(this.config.coldDynamics==='legacy'){yield*advanceColdLegacy.call(this,mix);return;}if(this.config.disableCold)return;
    const result=yield*this._coldSolverFor().advance(this._coldState(),DT,this.coldMomentumLedger),g=this.cold,b=this.coldMomentumLedger;
    this.stats.coldVolumeLoss+=result.volumeOut-result.roundoffH;this.stats.coldHeatLoss+=result.heatOut-result.roundoffQ;this.stats.coldSubsteps+=result.substeps;this.stats.coldRejected+=result.rejected;this.stats.coldWaveMaxCFL=Math.max(this.stats.coldWaveMaxCFL||0,result.maxCFL);
    if(result.empty)return;
    const mixing=mix&&this.config.coldMixing!==false,hm=mixing?Math.exp(-DT/this.config.coldVolumeMixingSeconds):1,qm=mixing?Math.exp(-DT*(1/this.config.coldVolumeMixingSeconds+1/this.config.coldThermalMixingSeconds)):1,damping=this.config.coldDampingSeconds>0?Math.exp(-DT/this.config.coldDampingSeconds):1;
    for(let i=0;i<g.n;i++){const oldH=this.h[i],oldQ=this.q[i];let h=oldH*hm,q=oldQ*qm;if(mixing&&h>1200){const drained=h-(h-1200)*(1-Math.exp(-DT/600));q*=drained/h;h=drained;}const ratio=oldQ>0?q/oldQ:1,px=this.Px[i],py=this.Py[i];this.Px[i]*=ratio;this.Py[i]*=ratio;b.decayRemoval.x+=(px-this.Px[i])*g.area;b.decayRemoval.y+=(py-this.Py[i])*g.area;const x=this.Px[i],y=this.Py[i];
      if(this.config.coldMomentumCoupling==='surface_drag'&&damping<1){const ci=i%g.nx,cj=Math.floor(i/g.nx),A=q/THETA,u=.5*(this.cu[cj*(g.nx+1)+ci]+this.cu[cj*(g.nx+1)+ci+1]),v=.5*(this.cv[cj*g.nx+ci]+this.cv[(cj+1)*g.nx+ci]);this.Px[i]=(x+A*u)*damping-A*u;this.Py[i]=(y+A*v)*damping-A*v;}
      else{this.Px[i]*=damping;this.Py[i]*=damping;}b.dampingRemoval.x+=(x-this.Px[i])*g.area;b.dampingRemoval.y+=(y-this.Py[i])*g.area;this.h[i]=h;this.q[i]=q;this.stats.coldVolumeLoss+=(oldH-h)*g.area;this.stats.coldHeatLoss+=(oldQ-q)*g.area;if(i%4096===4095)yield;}
    if(mixing)yield*this._spreadColdLayer();
    const round=this._coldSolverFor().clean(this._coldState(),b);this.stats.coldVolumeLoss-=round.h;this.stats.coldHeatLoss-=round.q;
  };
  // Unresolved lateral exchange of the density current. Pair fluxes transport
  // volume, heat deficit and momentum together; no cold air is created. Terrain
  // reduces cross-ridge exchange. Explicit positivity substeps retain a 600 s
  // physical step, and the existing open-boundary solver handles export.
  Model.prototype._spreadColdLayer=function*(){
    const K=this.config.coldHorizontalMixing;if(!K)return;
    const g=this.cold,steps=Math.ceil(DT*K/(.2*g.dx*g.dx)),a=DT*K/(steps*g.dx*g.dx),fields=[this.h,this.q,this.Px,this.Py],delta=fields.map((_,i)=>this.buffer('coldSpread'+i,g.n));
    for(let step=0;step<steps;step++){
      for(const d of delta)d.fill(0);
      for(let k=0;k<g.n;k++)for(const j of [k%g.nx+1<g.nx?k+1:-1,k+g.nx<g.n?k+g.nx:-1]){
        if(j<0||this.h[k]+this.h[j]===0)continue;
        const conductance=Math.exp(-Math.abs(this.cz[k]-this.cz[j])/Math.max(60,(this.h[k]+this.h[j])*.5));
        for(let n=0;n<fields.length;n++){const flux=a*conductance*(fields[n][k]-fields[n][j]);delta[n][k]-=flux;delta[n][j]+=flux;}
      }
      for(let n=0;n<fields.length;n++)for(let k=0;k<g.n;k++)fields[n][k]+=delta[n][k];yield;
    }
  };
  Model.prototype.prepareColdKinematics=function*(){
    if(this._coldKinematicsReady)return;if(this.config.coldDynamics==='legacy'){this.coldKinematicDiagnostics={mode:'legacy',definition:'1.8 carrier proxy retained; inertial contour/wave state is not applied.'};this._coldKinematicsReady=true;return;}
    const before={x:this.coldMomentumLedger.dryRemoval.x,y:this.coldMomentumLedger.dryRemoval.y},r=yield*this._coldSolverFor().rhs(this._coldState(),'diagnostic');
    this.coldRhsH.set(r.out.h);this.coldRhsQ.set(r.out.q);if(this.config.mechanismEvidence){for(const [key,array]of Object.entries({stage_h:this.h,stage_q:this.q,stage_px:this.Px,stage_py:this.Py,stage_rhs_h:r.out.h,stage_rhs_q:r.out.q}))this._mechanismBuffer(key,this.cold.n).set(array);for(const [key,array]of Object.entries(this.mechanismFields))if(key.startsWith('phase_'))array.fill(0);const sx=this._mechanismBuffer('stage_carrier_x',this.cold.n),sy=this._mechanismBuffer('stage_carrier_y',this.cold.n);for(let j=0;j<this.cold.ny;j++)for(let i=0;i<this.cold.nx;i++){const k=j*this.cold.nx+i,A=this.q[k]/THETA;sx[k]=(A>=ColdLayer.DRY?this.Px[k]/A:0)+.5*(this.cu[j*(this.cold.nx+1)+i]+this.cu[j*(this.cold.nx+1)+i+1]);sy[k]=(A>=ColdLayer.DRY?this.Py[k]/A:0)+.5*(this.cv[j*this.cold.nx+i]+this.cv[(j+1)*this.cold.nx+i]);}}this.cvx.set(r.faces.u);this.cvy.set(r.faces.v);this.coutx.set(r.faces.relativeU);this.couty.set(r.faces.relativeV);this.coldWaveLX.set(r.faces.sLX);this.coldWaveRX.set(r.faces.sRX);this.coldWaveLY.set(r.faces.sLY);this.coldWaveRY.set(r.faces.sRY);for(const key of ['coldPhaseX','coldPhaseY','coldPhaseRawX','coldPhaseRawY','coldPhaseControlX','coldPhaseControlY'])this[key].fill(0);
    this.coldKinematicDiagnostics={mode:'inertial',frontKinematics:this.config.frontKinematics,evidenceEnabled:this.config.mechanismEvidence,rhsAt:this._coldIntegratedUntil??this.t,physicalStepStart:this.t,stage:'post_cold_transport_mix_before_precip_evap',rate:r.rate,readOnly:true,definition:'Post-mix conservative transport/pressure RHS only; no evaporation/mixing source and no duplicate budget commit.',mechanicalEnergyProxy:ColdLayer.mechanicalEnergy(this._coldState(),this.cold,this.cz),momentum:ColdLayer.audit(this._coldState(),this.cold,this.coldMomentumLedger)};
    if(before.x!==this.coldMomentumLedger.dryRemoval.x||before.y!==this.coldMomentumLedger.dryRemoval.y)throw Error('只读冷层诊断意外记账');this._coldKinematicsReady=true;
  };
  Model.prototype._coldCarrierAt=function(x,y){const g=this.cold,k=g.index(x,y);if(k<0)return {relativeX:0,relativeY:0,x:0,y:0};const A=this.q[k]/THETA,relativeX=A>=ColdLayer.DRY?this.Px[k]/A:0,relativeY=A>=ColdLayer.DRY?this.Py[k]/A:0,i=k%g.nx,j=Math.floor(k/g.nx);return {relativeX,relativeY,x:relativeX+.5*(this.cu[j*(g.nx+1)+i]+this.cu[j*(g.nx+1)+i+1]),y:relativeY+.5*(this.cv[j*g.nx+i]+this.cv[(j+1)*g.nx+i])};};
  Model.prototype._coldFrontPhase=function(cold,warm,di,dj){
    if(this.config.coldDynamics==='legacy')return {available:false,definition:'Legacy carrier velocity is retained for this ablation.'};
    const g=this.cold,i=cold%g.nx,j=Math.floor(cold/g.nx),axis=di?'X':'Y',face=di?j*(g.nx+1)+i+(di>0?1:0):(j+(dj>0?1:0))*g.nx+i,sign=di||dj,wl=this['coldWaveL'+axis][face],wr=this['coldWaveR'+axis][face],waveL=sign>0?wl:-wr,waveR=sign>0?wr:-wl,carrier=this._coldCarrierAt((i+.5)*g.dx,(j+.5)*g.dx),carrierNormal=carrier.x*di+carrier.y*dj;
    const fc=[this.h[cold]-40,this.q[cold]-20,this.q[cold]-.3*this.h[cold]],fw=[this.h[warm]-40,this.q[warm]-20,this.q[warm]-.3*this.h[warm]],dc=[this.coldRhsH[cold],this.coldRhsQ[cold],this.coldRhsQ[cold]-.3*this.coldRhsH[cold]],dw=[this.coldRhsH[warm],this.coldRhsQ[warm],this.coldRhsQ[warm]-.3*this.coldRhsH[warm]];let alpha=Infinity,control=-1;
    for(let n=0;n<3;n++)if(fc[n]>=0&&fw[n]<0){const a=fc[n]/(fc[n]-fw[n]);if(a<alpha){alpha=a;control=n;}}
    let fallback=null,raw=carrierNormal;if(control<0){alpha=.5;fallback='no_valid_crossing';}else if(Math.abs(fw[control]-fc[control])/g.dx<1e-12)fallback='degenerate_gradient';else{const fdot=(1-alpha)*dc[control]+alpha*dw[control];raw=-fdot/((fw[control]-fc[control])/g.dx);if(!Number.isFinite(raw)){raw=carrierNormal;fallback='nonfinite_phase';}}
    const used=Math.max(waveL,Math.min(waveR,raw)),limited=Math.abs(used-raw)>1e-12,velocity={x:carrier.x+(used-carrierNormal)*di,y:carrier.y+(used-carrierNormal)*dj};this['coldPhase'+axis][face]=used*sign;this['coldPhaseRaw'+axis][face]=raw*sign;this['coldPhaseControl'+axis][face]=control+1;
    return {available:true,raw,used,waveL,waveR,limited,fallback,alpha,constraint:['h40','Q20','Qminus03h'][control]||'fallback',carrierNormal,carrierCold:carrier,velocity,contour:{x:(i+.5)*g.dx+alpha*g.dx*di,y:(j+.5)*g.dx+alpha*g.dx*dj},definition:'Level-set phase estimate from read-only post-mix RHS; normal clipped to HLLE waves, tangential cold-side carrier proxy. Not rain advection.'};
  };
  Model.prototype._mechanismBuffer=function(key,n){if(!this.config.mechanismEvidence)return null;this.mechanismFields??={};let a=this.mechanismFields[key];if(!a||a.length!==n)a=this.mechanismFields[key]=new Float64Array(n);return a;};
  const coldFrontFace1D=Model.prototype._coldFrontPhase;
  Model.prototype._coldFrontPhase=function(cold,warm,di,dj){
    if(this.config.coldDynamics==='legacy'||this.config.frontKinematics==='face_1d'){const result=coldFrontFace1D.call(this,cold,warm,di,dj);result.mode=this.config.coldDynamics==='legacy'?'not_applicable_legacy_dynamics':'face_1d';return result;}
    return this._coldLevelsetPhase(cold,warm,di,dj);
  };
  Model.prototype._coldPhaseScalar=function(control,k){return control===0?this.h[k]-40:control===1?this.q[k]-20:this.q[k]-.3*this.h[k];};
  Model.prototype._coldPhaseRate=function(control,k){return control===0?this.coldRhsH[k]:control===1?this.coldRhsQ[k]:this.coldRhsQ[k]-.3*this.coldRhsH[k];};
  Model.prototype._coldLevelsetPhase=function(cold,warm,di,dj,scale=1){
    if(!(scale>0&&Number.isFinite(scale)))throw Error('轮廓重标须为有限正常数');
    const g=this.cold,i=cold%g.nx,j=Math.floor(cold/g.nx),tx=-dj,ty=di,axis=di?'X':'Y',face=di?j*(g.nx+1)+i+(di>0?1:0):(j+(dj>0?1:0))*g.nx+i;
    let alpha=Infinity,control=-1;for(let c=0;c<3;c++){const fc=this._coldPhaseScalar(c,cold)*scale,fw=this._coldPhaseScalar(c,warm)*scale;if(fc>=0&&fw<0){const a=fc/(fc-fw);if(a<alpha){alpha=a;control=c;}}}
    let fallback=null,oneSidedSamples=0,isolatedTangentSamples=0;if(control<0){alpha=.5;fallback='no_valid_crossing';}
    const tangentSlope=k=>{const x=k%g.nx,y=Math.floor(k/g.nx),mi=x-tx,mj=y-ty,pi=x+tx,pj=y+ty,minus=mi>=0&&mi<g.nx&&mj>=0&&mj<g.ny?mj*g.nx+mi:-1,plus=pi>=0&&pi<g.nx&&pj>=0&&pj<g.ny?pj*g.nx+pi:-1,f=this._coldPhaseScalar(control,k)*scale;
      if(minus<0&&plus<0){isolatedTangentSamples++;return 0;}if(minus<0){oneSidedSamples++;return (this._coldPhaseScalar(control,plus)*scale-f)/g.dx;}if(plus<0){oneSidedSamples++;return (f-this._coldPhaseScalar(control,minus)*scale)/g.dx;}
      const a=(f-this._coldPhaseScalar(control,minus)*scale)/g.dx,b=(this._coldPhaseScalar(control,plus)*scale-f)/g.dx;return a*b>0?Math.sign(a)*Math.min(Math.abs(a),Math.abs(b)):0;
    };
    let gx=0,gy=0,fdot=null,fc=0,fw=0;if(control>=0){fc=this._coldPhaseScalar(control,cold)*scale;fw=this._coldPhaseScalar(control,warm)*scale;const gn=(fw-fc)/g.dx,gt=(1-alpha)*tangentSlope(cold)+alpha*tangentSlope(warm);gx=gn*di+gt*tx;gy=gn*dj+gt*ty;fdot=((1-alpha)*this._coldPhaseRate(control,cold)+alpha*this._coldPhaseRate(control,warm))*scale;}
    const cl=this._coldCarrierAt((i+.5)*g.dx,(j+.5)*g.dx),wi=warm%g.nx,wj=Math.floor(warm/g.nx),cr=this._coldCarrierAt((wi+.5)*g.dx,(wj+.5)*g.dx),Uc={x:cl.x+(cr.x-cl.x)*alpha,y:cl.y+(cr.y-cl.y)*alpha},norm=Math.hypot(gx,gy);
    if(control>=0&&(!Number.isFinite(norm)||!Number.isFinite(fdot)))fallback='nonfinite_gradient_or_rate';else if(control>=0&&norm*g.dx<=1e-10*Math.max(scale,Math.abs(fc),Math.abs(fw)))fallback='degenerate_gradient';
    const nf=!fallback?{x:-gx/norm,y:-gy/norm}:{x:di,y:dj},carrierNormal=Uc.x*nf.x+Uc.y*nf.y,UL=cl.x*nf.x+cl.y*nf.y,UR=cr.x*nf.x+cr.y*nf.y,AL=this.q[cold]/THETA,AR=this.q[warm]/THETA,cL=Math.sqrt(9.81*Math.max(this.q[cold],0)/300),cR=Math.sqrt(9.81*Math.max(this.q[warm],0)/300);
    let waveL=Math.min(UL-cL,UR-cR),waveR=Math.max(UL+cL,UR+cR);if(AL>0&&AR===0){waveL=UL-cL;waveR=UL+2*cL;}else if(AR>0&&AL===0){waveL=UR-2*cR;waveR=UR+cR;}
    const raw=fallback?carrierNormal:fdot/norm,used=Math.max(waveL,Math.min(waveR,raw)),rawVelocity={x:Uc.x+(raw-carrierNormal)*nf.x,y:Uc.y+(raw-carrierNormal)*nf.y},velocity={x:Uc.x+(used-carrierNormal)*nf.x,y:Uc.y+(used-carrierNormal)*nf.y},residualRaw=!fallback?fdot+rawVelocity.x*gx+rawVelocity.y*gy:null,residualUsed=!fallback?fdot+velocity.x*gx+velocity.y*gy:null,limited=Math.abs(used-raw)>1e-12;
    this['coldPhase'+axis][face]=di?velocity.x:velocity.y;this['coldPhaseRaw'+axis][face]=di?rawVelocity.x:rawVelocity.y;this['coldPhaseControl'+axis][face]=control+1;
    const result={available:true,mode:'levelset_2d',raw,used,waveL,waveR,limited,fallback,alpha,constraint:['h40','Q20','Qminus03h'][control]||'fallback',constraintUnits:control===0?'m':control>=0?'K*m':null,gradient:{x:gx,y:gy,units:control===0?'m/m':control>=0?'K*m/m':'unavailable'},normal:nf,geometricNormal:{x:di,y:dj},fdot,Uc,carrierNormal,carrierCold:cl,carrierWarm:cr,rawVelocity,velocity,residualRaw,residualUsed,oneSidedSamples,isolatedTangentSamples,contour:{x:(i+.5)*g.dx+alpha*g.dx*di,y:(j+.5)*g.dx+alpha*g.dx*dj},definition:'Same-stage 2D gradient projection. Raw satisfies fdot+V.grad=0; used normal is limited along true contour normal. FV geometry remains separate; not rain advection.'};
    if(this.config.mechanismEvidence){const n=di?(g.nx+1)*g.ny:g.nx*(g.ny+1),values={validConstraint:!fallback?1:0,gradientX:gx,gradientY:gy,normalX:nf.x,normalY:nf.y,fdot:fdot??0,alpha,UcX:Uc.x,UcY:Uc.y,rawX:rawVelocity.x,rawY:rawVelocity.y,usedX:velocity.x,usedY:velocity.y,normalRaw:raw,normalUsed:used,projectedWaveL:waveL,projectedWaveR:waveR,residualRaw:residualRaw??0,residualUsed:residualUsed??0,oneSidedSamples,isolatedTangentSamples};for(const [key,value]of Object.entries(values))this._mechanismBuffer('phase_'+axis+'_'+key,n)[face]=value;}
    return result;
  };

  Model.prototype._coldHeadSupport=function(b){let h=0,q=0,supportedLengthM=0;const n=b.geometricNormal||{x:b.nx,y:b.ny};for(let s=625;s<10000;s+=1250){const a=this.surfaceAccess(b.x-n.x*s,b.y-n.y*s);if(!a.inDomain||!a.cold)break;h+=a.h*1250;q+=a.Q*1250;supportedLengthM+=1250;}return {Hhead:h/10000,Qhead:q/10000,supportedLengthM,windowM:10000,samplingM:1250,pointH:b.h??null,pointQ:b.q??null};};
  Model.prototype._coldLift=function(b,layer,Urel){
    if(this.config.frontClosure==='head_work'){const head=b.head||this._coldHeadSupport(b),energyLimit=.25*Urel**2+.5*(9.81/300)*head.Qhead,Hlift=Math.max(1.5*head.Hhead-(layer?1500:0),0),heightLimit=.08*Hlift;return {Kcp:Math.min(energyLimit,heightLimit),energyLimit,heightLimit,Hlift,...head,closure:'head_work'};}
    const energyLimit=.25*Urel**2+.5*9.81*b.q/300,Hlift=Math.max(1.5*b.h-(layer?1500:100),0),factor=clip(Hlift/300);return {Kcp:energyLimit*factor,energyLimit,heightLimit:energyLimit*factor,Hlift,pointH:b.h,pointQ:b.q,closure:'point'};
  };

  // 1.8 line/flux diagnostics: all extensive quantities are accumulated during physical steps.
  Model.prototype._frontStat=function(){
    const counts=()=>({candidates:0,conditionalExpected:0,acceptedBeforeSpacing:0,thinningRejected:0,spacingRejected:0,births:0,inBandCandidates:0,inBandConditionalExpected:0,inBandAcceptedBeforeSpacing:0,inBandSpacingRejected:0,inBandBirths:0,poissonSegments:0,multiProposalSegments:0,rejections:{}});
    return {lengthTimeMSeconds:0,lowAvailableLengthTimeMSeconds:0,midAvailableLengthTimeMSeconds:0,rejectLengthTimeMSeconds:{low:{},mid:{}},pathStopLengthTimeMSeconds:{low:{},mid:{}},phase:{oneSidedSamples:0,isolatedTangentSamples:0,residuals:{h40:{raw:0,used:0,absRaw:0,absUsed:0,lengthTime:0},Q20:{raw:0,used:0,absRaw:0,absUsed:0,lengthTime:0},Qminus03h:{raw:0,used:0,absRaw:0,absUsed:0,lengthTime:0}},faceSteps:0,limitedFaceSteps:0,fallbackFaceSteps:0,lengthTimeMSeconds:0,absRawMinusUsedLengthTime:0,limitedLengthTimeMSeconds:0,fallbackLengthTimeMSeconds:0,rawMinusUsedLengthTime:0,carrierNormalLengthTime:0,usedNormalLengthTime:0,waveLowerLengthTime:0,waveUpperLengthTime:0,controls:{},fallbacks:{}},head:{HheadLengthTime:0,QheadLengthTime:0,supportLengthTime:0,energyLimitLengthTime:0,heightLimitLengthTime:0,KcpLengthTime:0,midEnergyLimitLengthTime:0,midHeightLimitLengthTime:0,midKcpLengthTime:0},phiVolumeM3:0,eligiblePhiVolumeM3:0,rawMu:0,eligibleMu:0,referenceMu005:0,referenceThinnedMu005:0,thinnedMuQuadrature:0,activeSamplingMu:0,gateFLengthTimeBins:new Array(9).fill(0),gateZeroLengthTimeByReason:{},gateMetricLengthTimeWeights:{geometricUrel:0,hInside:0,QInside:0,warmQ:0,CIN:0,Kenv:0,Kcp:0,F:0},gateLengthTimeMoments:{geometricUrel:0,hInside:0,QInside:0,warmQ:0,CIN:0,Kenv:0,Kcp:0,F:0},channels:{areaLow:counts(),areaMid:counts(),boundaryLow:counts()}};
  };
  Model.prototype._beginFrontStep=function(){
    this.fronts=[];this.frontSegments=[];this.frontIndex.clear();this._frontFaceKeys=new Set();this._frontSegmentKeys=new Set();this._frontWork=0;this._frontBackground=this.background();
    this.frontDiagnostics={schema:'front-initiation-1.10',stepStart:this.t,stepEnd:this.t+DT,stepSeconds:DT,mode:this.config.boundaryInitiationMode,efficiency:this.config.boundaryFluxEfficiency,VseedM3:Math.PI*1000**2*200,warmProposalWidthM:2000,canonicalSegmentM:2500,coldDynamics:this.config.coldDynamics,frontKinematics:this.config.frontKinematics,coastalWindModel:this.config.coastalWindModel,effectiveModes:this.effectiveModes,frontClosure:this.config.frontClosure,physicalFaceCount:0,canonicalSegmentCount:0,global:this._frontStat(),local:this._frontStat(),blocks:{},definitions:{region:'|along coast|<=50 km and |normal|<=20 km about audited crossing; domain-center axes if no coastal geometry. Diagnostic region only.',blocks:'Fixed physical 10 km along-coast bins; lengths clipped to the rectangle and bin, Phi is midpoint quadrature on canonical 2.5 km segments.',integrals:'Length*moments are integrated over each 600 s step. Divide last-step lengthTimeMSeconds by stepSeconds for length. phiVolumeM3 is integral(Phi dt). All numeric totals/deltas are additive.',F:'Deterministic 2 along x 2 warm-offset quadrature per canonical segment; not exact F integral. Actual proposal F is recorded separately in channel conditionalExpected.',sampling:'First 24 physical faces have readable samples; all faces contribute to aggregates.',normals:'Phi/proposals use geometric normal. head_work uses geometric path/Kcp too; point retains smooth path/Kcp. Inertial front velocity is a bounded contour phase, precipitation uses resolved carrier.',rates:'Flux engineering event rate, no added air or water inventory. Reference raw and thinned mu use epsilon=.05 even when configured efficiency is zero. activeSamplingMu=0 in area/disabled-birth/disabled-cold mode.'}};
  };
  Model.prototype._frontCoordinates=function(x,y){const c=this.coastalGeometry,dx=x-(c?.crossing.x??this.config.width/2),dy=y-(c?.crossing.y??this.config.height/2),t=c?.tangent||{x:1,y:0},n=c?.normal||{x:0,y:1};return {s:dx*t.x+dy*t.y,n:dx*n.x+dy*n.y};};
  Model.prototype._frontLocation=function(x,y){const p=this._frontCoordinates(x,y);return {local:Math.abs(p.s)<=50000&&Math.abs(p.n)<=20000,block:String(Math.floor(p.s/10000)),...p};};
  Model.prototype._frontLocalParts=function(segment){
    const a=this._frontCoordinates(segment.x0,segment.y0),b=this._frontCoordinates(segment.x1,segment.y1);let lo=0,hi=1;
    for(const [v,d,L]of [[a.s,b.s-a.s,50000],[a.n,b.n-a.n,20000]]){if(Math.abs(d)<1e-12){if(Math.abs(v)>L)return [];}else{const u=(-L-v)/d,w=(L-v)/d;lo=Math.max(lo,Math.min(u,w));hi=Math.min(hi,Math.max(u,w));}}if(hi-lo<=1e-12)return [];
    const cuts=[lo,hi],ds=b.s-a.s;if(Math.abs(ds)>1e-12)for(let edge=-50000;edge<=50000;edge+=10000){const u=(edge-a.s)/ds;if(u>lo+1e-12&&u<hi-1e-12)cuts.push(u);}cuts.sort((x,y)=>x-y);const parts=[];for(let k=1;k<cuts.length;k++){const u=(cuts[k]+cuts[k-1])/2;parts.push({fraction:cuts[k]-cuts[k-1],block:String(Math.floor((a.s+ds*u)/10000))});}return parts;
  };
  Model.prototype._frontTargets=function(segment){
    const D=this.frontDiagnostics,targets=[[D.global,1]];for(const part of this._frontLocalParts(segment)){D.blocks[part.block]??=this._frontStat();targets.push([D.local,part.fraction],[D.blocks[part.block],part.fraction]);}return targets;
  };
  Model.prototype._frontCandidateTargets=function(x,y){const D=this.frontDiagnostics;if(!D)return [];const p=this._frontLocation(x,y),targets=[D.global];if(p.local){D.blocks[p.block]??=this._frontStat();targets.push(D.local,D.blocks[p.block]);}return targets;};
  Model.prototype._recordFrontCandidate=function(x,y,channel,key,value){for(const target of this._frontCandidateTargets(x,y))target.channels[channel][key]+=value;};
  Model.prototype._recordFrontGateRejection=function(x,y,channel,reason){for(const target of this._frontCandidateTargets(x,y)){const r=target.channels[channel].rejections;r[reason]=(r[reason]||0)+1;}};
  Model.prototype._areaFrontExposure=function(x,y){
    const ix=Math.floor(x/10000),iy=Math.floor(y/10000);for(let yy=iy-1;yy<=iy+1;yy++)for(let xx=ix-1;xx<=ix+1;xx++)for(const b of this.frontIndex.get(xx+','+yy)||[]){const n=b.geometricNormal,dx=x-b.x,dy=y-b.y,d=dx*n.x+dy*n.y,tangent=Math.abs(-dx*n.y+dy*n.x);if(d>=0&&d<=2000&&tangent<=b.lengthM/2)return b;}return null;
  };
  Model.prototype._boundaryPosition=function(segment,along,warmFraction,width=2000){return {x:segment.x0+(segment.x1-segment.x0)*along+segment.boundary.geometricNormal.x*width*warmFraction,y:segment.y0+(segment.y1-segment.y0)*along+segment.boundary.geometricNormal.y*width*warmFraction};};
  Model.prototype._boundaryEventGate=function(b,x,y,bg){
    const f=this.fields,k=this.env.index(x,y),access=this.surfaceAccess(x,y),Kenv=k>=0?.08*f.xiL[k]:0,inlet=b.inlets.low,feed=b.feeds.low,relative=b.relativeWinds.low,inletAccess=inlet?this.surfaceAccess(inlet.x,inlet.y):null,hasInlet=feed!==undefined&&inletAccess?.inDomain,rh=hasInlet?f.rhL[feed]:null,energy=hasInlet?f.el[feed]:null,Qlocal=hasInlet?(this.config.surfaceAccessMode==='legacy'?f.q[feed]:inletAccess.Q):null,CIN=hasInlet?bg.iL+20*clip((.75-rh)/.25)+.08*Qlocal:null,lift=this._coldLift(b,0,relative?.normalInflow??0),Kcp=relative?lift.Kcp:0;
    const result={F:0,source:'coldPool',power:Kenv,coldPower:Kcp,parent:b.id,CIN,Qlocal,rh,energy,surfaceAccess:access,evidence:{position:{x,y},surfaceAccess:access,accessMode:this.config.surfaceAccessMode,boundaryId:b.id,physicalFaceId:b.faceId,geometricNormal:b.geometricNormal,smoothedNormal:b.smoothedNormal||{x:b.nx,y:b.ny},boundaryVelocity:b.velocity,carrierVelocity:b.carrierVelocity,phase:b.phase,head:b.head,lift,relativeWind:relative??null,warmInlet:inlet?{...inlet,surfaceAccess:inletAccess}:null,warmPath:b.paths.low,inside:b.inside,outside:b.outside,Kenv,Kcp,CIN,Qlocal,coldDominant:Kcp>Kenv,triggerLayer:'low',channel:'boundaryLow'}};
    const reject=reason=>({...result,rejection:reason,evidence:{...result.evidence,F:0,rejection:reason}});
    if(k<0)return reject('outside');if(!this._birthRegionAllowed(x,y))return reject('excludedSouthernRegion');if(!access.warmAccessible)return reject('fineCold');
    const dx=x-b.x,dy=y-b.y,d=dx*b.nx+dy*b.ny,tangent=Math.abs(-dx*b.ny+dy*b.nx);if(d<0||d>4000||tangent>this.cold.dx*.8)return reject('warmSideGeometry');
    if(this.config.disableCold)return reject('coldDisabled');if(!hasInlet||!relative)return reject(b.rejections.low||'noWarmSample');if(!inletAccess.warmAccessible)return reject('inletCold');
    if(relative.normalInflow<2)return reject('relativeNormal');if(rh<.75)return reject('humidity');if(energy<.25)return reject('energy');
    const focused=this.config.initiationModel==='focused_lift'?this._liftAccess(k,x,y,0,bg,lift.Hlift,inlet):null;
    result.evidence.focusedLift=focused;
    const F=clip((rh-.65)/.25)*clip((energy-.15)/.65)*clip((Kenv+Kcp-CIN)/15)*(focused?.factor??1)*this._newInitiationMoisture(x,y),reason=F>0?null:focused?.factor===0?focused.reason:Kenv+Kcp<=CIN?'inhibition':'zeroGate';return {...result,F,rejection:reason,evidence:{...result.evidence,F,rejection:reason}};
  };
  Model.prototype._observeFront=function*(b,readable){
    const n=b.geometricNormal,vertical=n.x!==0,constant=vertical?b.x:b.y,start=(vertical?b.y:b.x)-b.lengthM/2,sign=vertical?n.x:n.y,axis=vertical?'v':'h';b.faceId=[axis,constant,start,b.lengthM,sign].join(':');
    if(this._frontFaceKeys.has(b.faceId))throw Error('重复冷暖物理面 '+b.faceId);this._frontFaceKeys.add(b.faceId);this.fronts.push(b);this.frontDiagnostics.physicalFaceCount++;
    const bin=Math.floor(b.x/10000)+','+Math.floor(b.y/10000);if(!this.frontIndex.has(bin))this.frontIndex.set(bin,[]);this.frontIndex.get(bin).push(b);if(readable)b.fluxSamples=[];
    for(let offset=0;offset<b.lengthM;offset+=2500){
      const length=Math.min(2500,b.lengthM-offset),along=start+offset,key=[axis,constant,along,length,sign].join(':');if(this._frontSegmentKeys.has(key))throw Error('重复公共前缘段 '+key);this._frontSegmentKeys.add(key);
      const segment={key,boundary:b,lengthM:length,x0:vertical?constant:along,y0:vertical?along:constant,x1:vertical?constant:along+length,y1:vertical?along+length:constant},x=(segment.x0+segment.x1)/2,y=(segment.y0+segment.y1)/2,rx=this.env.sample(this.fields.u,x,y)-b.velocity.x,ry=this.env.sample(this.fields.v,x,y)-b.velocity.y,Urel=Math.max(0,-rx*n.x-ry*n.y),heff=Math.min(this.config.frontClosure==='head_work'?b.head.Hhead:b.fluxInside.h,1200),Phi=Urel*heff*length,rawMu=this.config.boundaryFluxEfficiency*Phi*DT/(Math.PI*1000**2*200),lowReason=Urel<2?'geometricRelativeNormal':b.feeds.low===undefined?(b.rejections.low||'noWarmSample'):null,eligible=!lowReason&&!this.config.disableCold;
      Object.assign(segment,{Urel,heff,Phi,rawMu,eligibleMu:eligible?rawMu:0});this.frontSegments.push(segment);this.frontDiagnostics.canonicalSegmentCount++;
      const bg=this._frontBackground,samples=[];for(const at of [.25,.75])for(const distance of [500,1500]){const px=segment.x0+(segment.x1-segment.x0)*at+n.x*distance,py=segment.y0+(segment.y1-segment.y0)*at+n.y*distance,gate=this._boundaryEventGate(b,px,py,bg);samples.push({x:px,y:py,gate});}
      for(const [target,fraction]of this._frontTargets(segment)){
        const measure=length*DT*fraction;target.lengthTimeMSeconds+=measure;const phase=b.phase,lift=this._coldLift(b,0,b.relativeWinds.low?.normalInflow??0);if(phase?.available){const p=target.phase;p.oneSidedSamples+=(phase.oneSidedSamples||0)*length/b.lengthM*fraction;p.isolatedTangentSamples+=(phase.isolatedTangentSamples||0)*length/b.lengthM*fraction;if(Number.isFinite(phase.residualRaw)){const r=p.residuals[phase.constraint];r.raw+=phase.residualRaw*measure;r.absRaw+=Math.abs(phase.residualRaw)*measure;r.used+=phase.residualUsed*measure;r.absUsed+=Math.abs(phase.residualUsed)*measure;r.lengthTime+=measure;}p.faceSteps+=length/b.lengthM*fraction;p.limitedFaceSteps+=(phase.limited?length/b.lengthM*fraction:0);p.fallbackFaceSteps+=(phase.fallback?length/b.lengthM*fraction:0);p.absRawMinusUsedLengthTime+=Math.abs(phase.raw-phase.used)*measure;p.lengthTimeMSeconds+=measure;p.limitedLengthTimeMSeconds+=(phase.limited?measure:0);p.fallbackLengthTimeMSeconds+=(phase.fallback?measure:0);p.rawMinusUsedLengthTime+=(phase.raw-phase.used)*measure;p.carrierNormalLengthTime+=phase.carrierNormal*measure;p.usedNormalLengthTime+=phase.used*measure;p.waveLowerLengthTime+=phase.waveL*measure;p.waveUpperLengthTime+=phase.waveR*measure;p.controls[phase.constraint]=(p.controls[phase.constraint]||0)+measure;if(phase.fallback)p.fallbacks[phase.fallback]=(p.fallbacks[phase.fallback]||0)+measure;}for(const [key,value]of Object.entries({HheadLengthTime:b.head.Hhead,QheadLengthTime:b.head.Qhead,supportLengthTime:b.head.supportedLengthM,energyLimitLengthTime:lift.energyLimit,heightLimitLengthTime:lift.heightLimit,KcpLengthTime:lift.Kcp,midEnergyLimitLengthTime:this._coldLift(b,1,b.relativeWinds.mid?.normalInflow??0).energyLimit,midHeightLimitLengthTime:this._coldLift(b,1,b.relativeWinds.mid?.normalInflow??0).heightLimit,midKcpLengthTime:this._coldLift(b,1,b.relativeWinds.mid?.normalInflow??0).Kcp}))target.head[key]+=value*measure;if(eligible)target.lowAvailableLengthTimeMSeconds+=measure;else{const reason=this.config.disableCold?'coldDisabled':lowReason;target.rejectLengthTimeMSeconds.low[reason]=(target.rejectLengthTimeMSeconds.low[reason]||0)+measure;}
        if(b.feeds.mid!==undefined)target.midAvailableLengthTimeMSeconds+=measure;else{const reason=b.rejections.mid||'noWarmSample';target.rejectLengthTimeMSeconds.mid[reason]=(target.rejectLengthTimeMSeconds.mid[reason]||0)+measure;}
        for(const layer of ['low','mid'])if(b.feeds[layer]!==undefined&&b.pathStops[layer]){const reason=b.pathStops[layer];target.pathStopLengthTimeMSeconds[layer][reason]=(target.pathStopLengthTimeMSeconds[layer][reason]||0)+measure;}
        target.phiVolumeM3+=Phi*DT*fraction;target.eligiblePhiVolumeM3+=(eligible?Phi:0)*DT*fraction;target.rawMu+=rawMu*fraction;target.eligibleMu+=segment.eligibleMu*fraction;target.referenceMu005+=.05*Phi*DT/(Math.PI*1000**2*200)*fraction;target.referenceThinnedMu005+=(eligible?.05*Phi*DT/(Math.PI*1000**2*200):0)*samples.reduce((a,p)=>a+p.gate.F,0)/4*fraction;target.thinnedMuQuadrature+=segment.eligibleMu*samples.reduce((a,p)=>a+p.gate.F,0)/4*fraction;target.activeSamplingMu+=this.config.boundaryInitiationMode==='flux'&&!this.config.disableBirths?segment.eligibleMu*fraction:0;
        for(const {gate}of samples){const weight=measure/4;let index=0;while(index<8&&gate.F>[0,.01,.05,.1,.25,.5,.75,1][index])index++;target.gateFLengthTimeBins[index]+=weight;if(gate.F===0){const r=gate.rejection||'zeroGate';target.gateZeroLengthTimeByReason[r]=(target.gateZeroLengthTimeByReason[r]||0)+weight;}
          for(const [name,value]of Object.entries({geometricUrel:Urel,hInside:b.fluxInside.h,QInside:b.fluxInside.Q,warmQ:gate.Qlocal,CIN:gate.CIN,Kenv:gate.surfaceAccess.inDomain?gate.power:null,Kcp:gate.coldPower,F:gate.F}))if(Number.isFinite(value)){target.gateLengthTimeMoments[name]+=value*weight;target.gateMetricLengthTimeWeights[name]+=weight;}
        }
      }
      if(readable)b.fluxSamples.push({key,lengthM:length,geometricUrel:Urel,heff,PhiM3S:Phi,rawMu,eligibleMu:segment.eligibleMu,geometricNormal:n,smoothedNormal:b.smoothedNormal||{x:b.nx,y:b.ny},quadrature:samples.map(({x,y,gate})=>({x,y,F:gate.F,CIN:gate.CIN,Kenv:gate.power,Kcp:gate.coldPower,Qlocal:gate.Qlocal??null,rejection:gate.rejection??null,inlet:gate.evidence?.warmInlet??null}))});
      if(++this._frontWork%24===0)yield;
    }
  };
  Model.prototype._commitFrontDiagnostics=function(){
    if(!this.frontDiagnostics)return;const merge=(target,source)=>{for(const [key,value]of Object.entries(source)){if(typeof value==='number')target[key]=(target[key]||0)+value;else if(value&&typeof value==='object'){target[key]??=Array.isArray(value)?[]:{};merge(target[key],value);}}};
    this.frontTotals.steps++;this.frontTotals.seconds+=DT;merge(this.frontTotals.global,this.frontDiagnostics.global);merge(this.frontTotals.local,this.frontDiagnostics.local);merge(this.frontTotals.blocks,this.frontDiagnostics.blocks);
  };

  // Coupled phase equilibrium: signed x is condensation; cloud evaporation is capped.
  function phaseAdjustment(w,T,m,p,cloud=0){
    const f=x=>w-x-saturation(T+2.5e6*x/(1004*m),m,p);
    let lo=-cloud,hi=w;
    if(f(lo)<0)return {water:w+cloud,temperature:T-2.5e6*cloud/(1004*m),cloud:0,condensed:0,evaporated:cloud};
    for(let n=0;n<60;n++){const x=(lo+hi)/2;if(f(x)>0)lo=x;else hi=x;}
    const x=(lo+hi)/2;return {water:w-x,temperature:T+2.5e6*x/(1004*m),cloud:cloud+x,condensed:Math.max(x,0),evaporated:Math.max(-x,0)};
  }
  Model.prototype.transportWater=function*(){
    const g=this.env,f=this.fields,bg=this.background(),mL=1400,mM=2600;
    const ul=this.buffer('airUL',this.eu.length),vl=this.buffer('airVL',this.ev.length),um=this.buffer('airUM',this.eu.length),vm=this.buffer('airVM',this.ev.length);
    ul.set(this.eu);vl.set(this.ev);
    for(let j=0;j<g.ny;j++)for(let i=0;i<=g.nx;i++){
      const k=j*(g.nx+1)+i,x=i*g.dx,y=(j+.5)*g.dx,ci=Math.min(this.cold.nx,Math.round(x/this.cold.dx)),cj=Math.min(this.cold.ny-1,Math.floor(y/this.cold.dx));
      if(this.config.coldDynamics==='legacy')ul[k]+=Math.min(this.cold.sample(this.h,x,y)/1200,1)*this.coutx[cj*(this.cold.nx+1)+ci];um[k]=.5*(f.um[j*g.nx+Math.max(0,i-1)]+f.um[j*g.nx+Math.min(g.nx-1,i)]);
    }
    for(let j=0;j<=g.ny;j++)for(let i=0;i<g.nx;i++){
      const k=j*g.nx+i,x=(i+.5)*g.dx,y=j*g.dx,ci=Math.min(this.cold.nx-1,Math.floor(x/this.cold.dx)),cj=Math.min(this.cold.ny,Math.round(y/this.cold.dx));
      if(this.config.coldDynamics==='legacy')vl[k]+=Math.min(this.cold.sample(this.h,x,y)/1200,1)*this.couty[cj*this.cold.nx+ci];vm[k]=.5*(f.vm[Math.max(0,j-1)*g.nx+i]+f.vm[Math.min(g.ny-1,j)*g.nx+i]);
    }
    const F=this.buffer('airLM',g.n),top=this.buffer('airTop',g.n),dL=this.buffer('airDL',g.n),dM=this.buffer('airDM',g.n);
    let rate=0;if(this._numericBackend)rate=yield*this._numericBackend.envAir(g,ul,vl,um,vm,F,top,dL,dM);else for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++){
      const k=j*g.nx+i,l=j*(g.nx+1)+i,b=j*g.nx+i;
      dL[k]=(ul[l+1]-ul[l]+vl[b+g.nx]-vl[b])/g.dx;dM[k]=(um[l+1]-um[l]+vm[b+g.nx]-vm[b])/g.dx;F[k]=-mL*dL[k];top[k]=F[k]-mM*dM[k];
      const outL=Math.max(-ul[l],0)+Math.max(ul[l+1],0)+Math.max(-vl[b],0)+Math.max(vl[b+g.nx],0),outM=Math.max(-um[l],0)+Math.max(um[l+1],0)+Math.max(-vm[b],0)+Math.max(vm[b+g.nx],0);
      rate=Math.max(rate,outL/g.dx+Math.max(F[k],0)/mL,outM/g.dx+(Math.max(-F[k],0)+Math.max(top[k],0))/mM);
    }
    this.airFlux={interface:F,top,dL,dM};f.divL.set(dL);f.airLM.set(F);f.airTop.set(top);
    const steps=Math.max(1,Math.ceil(DT*rate/.45)),dt=DT/steps;
    const keys=['wl','wm','qcL','qcM','tl','tm','ls'];
    const rhs=function*(state,prefix){const out={};let incoming=0,outgoing=0,topIn=0,topOut=0,heatIn=0,heatOut=0;const records=[];
      for(const key of keys){const a=state[key],r=this.buffer(prefix+key,g.n);r.fill(0);out[key]=r;const low=['wl','qcL','tl'].includes(key),temp=key==='tl'||key==='tm',cloud=key==='qcL'||key==='qcM',mass=low?mL:mM,u=low?ul:um,v=low?vl:vm,boundary=temp?(low?298:283):cloud||key==='ls'?0:(this.config.uniformMixingRatio!==undefined?this.config.uniformMixingRatio*mass:low?bg.rhL*saturation(298):bg.rhM*saturation(283,2600,75000));
        const owner={wl:'vaporL',wm:'vaporM',qcL:'cloudL',qcM:'cloudM',ls:'detrained'}[key];let horizontalIn=0,horizontalOut=0,interfaceIn=0,interfaceOut=0,topInput=0,topOutput=0;
        if(this._numericBackend){const faceResult=yield*this._numericBackend.envFaces(g,a,r,u,v,boundary,temp,temp?1004*mass:cloud||key==='ls'?0:2.5e6,{incoming,outgoing,heatIn,heatOut});({incoming,outgoing,horizontalIn,horizontalOut,heatIn,heatOut}=faceResult);}else {
        const face=(aidx,bidx,vel)=>{const donor=vel>=0?aidx:bidx,flux=vel*(donor<0?boundary:a[donor]);if(aidx>=0)r[aidx]-=flux/g.dx;if(bidx>=0)r[bidx]+=flux/g.dx;if(aidx>=0&&bidx>=0)return;const net=((aidx<0?-flux:0)+(bidx<0?flux:0))*g.dx;if(!temp){incoming+=Math.max(-net,0);outgoing+=Math.max(net,0);horizontalIn+=Math.max(-net,0);horizontalOut+=Math.max(net,0);}const hnet=net*(temp?1004*mass:cloud||key==='ls'?0:2.5e6);heatIn+=Math.max(-hnet,0);heatOut+=Math.max(hnet,0);};
        for(let j=0;j<g.ny;j++){for(let i=0;i<=g.nx;i++)face(i?j*g.nx+i-1:-1,i<g.nx?j*g.nx+i:-1,u[j*(g.nx+1)+i]);if(j%8===7)yield;}
        for(let j=0;j<=g.ny;j++){for(let i=0;i<g.nx;i++)face(j?(j-1)*g.nx+i:-1,j<g.ny?j*g.nx+i:-1,v[j*g.nx+i]);if(j%8===7)yield;}
        }
        if(key==='ls'){records.push({owner,horizontalIn,horizontalOut,interfaceIn,interfaceOut,topInput,topOutput});continue;}
        const other=state[temp?(low?'tm':'tl'):cloud?(low?'qcM':'qcL'):(low?'wm':'wl')];
        for(let k=0;k<g.n;k++){
          const l=low?a[k]:other[k],m=low?other[k]:a[k],flow=F[k],qface=temp?(flow>=0?l:m):(flow>=0?l/mL:m/mM),interfaceFlux=flow*qface;
          const signed=low?-interfaceFlux:interfaceFlux;r[k]+=signed/(temp?mass:1);if(!temp){interfaceIn+=Math.max(signed,0)*g.area;interfaceOut+=Math.max(-signed,0)*g.area;}
          if(!low){const qtop=top[k]>=0?(temp?a[k]:a[k]/mM):temp?283:cloud?0:(this.config.topMixingRatio??bg.rhM*saturation(283,2600,75000)/mM),flux=top[k]*qtop;r[k]-=flux/(temp?mass:1);if(!temp){topIn+=Math.max(-flux,0)*g.area;topOut+=Math.max(flux,0)*g.area;topInput+=Math.max(-flux,0)*g.area;topOutput+=Math.max(flux,0)*g.area;}const hnet=flux*g.area*(temp?1004:cloud?0:2.5e6);heatIn+=Math.max(-hnet,0);heatOut+=Math.max(hnet,0);}
          if(k%2048===2047)yield;
          // Intensive temperature horizontal divergence correction; vertical air terms above close fixed mass.
          // Horizontal conservative transport and vertical air exchange cancel a uniform intensive temperature.
        }
        if(!temp)records.push({owner,horizontalIn,horizontalOut,interfaceIn,interfaceOut,topInput,topOutput});
      }
      return {out,incoming:incoming+topIn,outgoing:outgoing+topOut,topIn,topOut,records,heatIn,heatOut};
    }.bind(this);
    for(let sub=0;sub<steps;sub++){
      const a=(yield*rhs(f,'coupledA')),stage={};for(const key of keys)stage[key]=this.buffer('coupledStage'+key,g.n);
      if(this._numericBackend)yield*this._numericBackend.vectorLists(keys.map(k=>f[k]),keys.map(k=>a.out[k]),keys.map(k=>stage[k]),g.n,dt);else for(const key of keys)for(let k=0;k<g.n;k++)stage[key][k]=f[key][k]+dt*a.out[key][k];yield;
      const b=yield*rhs(stage,'coupledB');if(this._numericBackend)yield*this._numericBackend.vectorLists(keys.map(k=>f[k]),keys.map(k=>b.out[k]),keys.map(k=>f[k]),g.n,dt,keys.map(k=>stage[k]));else for(const key of keys)for(let k=0;k<g.n;k++)f[key][k]=.5*(f[key][k]+stage[key][k]+dt*b.out[key][k]);for(const key of keys)for(let k=0;k<g.n;k++)if(f[key][k]<-1e-9)throw Error('耦合输送非负性失败 '+key);
      this.stats.inflow+=dt*.5*(a.incoming+b.incoming);this.stats.outflow+=dt*.5*(a.outgoing+b.outgoing);this.stats.sources.topIn+=dt*.5*(a.topIn+b.topIn);this.stats.sources.topOut+=dt*.5*(a.topOut+b.topOut);
      for(const stage of [a,b]){const weight=dt*.5;for(const r of stage.records){for(const [name,direction]of [['horizontalIn','in'],['horizontalOut','out'],['interfaceIn','in'],['interfaceOut','out'],['topInput','in'],['topOutput','out']])this.recordWater(r.owner,direction,name.replace(/In$|Out$|Input$|Output$/,''),r[name]*weight);}this.recordHeat('in','transportBoundary',stage.heatIn*weight);this.recordHeat('out','transportBoundary',stage.heatOut*weight);}yield;
    }
    for(const key of ['el','em','xiL','xiM','xiConvergence']){const old=this.buffer('proxyOld',g.n);old.set(f[key]);const low=key==='el'||key==='xiL'||key==='xiConvergence';for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++){const k=j*g.nx+i,x=(i+.5)*g.dx-(low?f.u[k]:f.um[k])*DT,y=(j+.5)*g.dx-(low?f.v[k]:f.vm[k])*DT;f[key][k]=x<0||y<0||x>=g.width||y>=g.height?(key==='el'?bg.eL:key==='em'?bg.eM:0):g.sample(old,x,y);}yield;}
  };
  // Reduced parcel displacement, not a prognostic 3-D cloud model. Terrain lift
  // is diagnosed from net windward relief; convergence is accumulated along the
  // low-level flow with signed descent and 15-minute entrainment. Broad upper divergence alone cannot initiate a cell.
  // SW flow points 15..75 degrees north of east: meteorological FROM 195..255.
  // Local terrain/breeze/cold outflows can still turn the resulting local wind.
  Model.prototype._monsoonAngle=function(at){
    const c=this.coastalGeometry,initial=c?Math.atan2(c.axisDirection.y,c.axisDirection.x):(this.monsoon?.axisAngle??Math.PI/4);
    if(!this.config.varyMonsoonDirection||!this.monsoon)return initial;
    if(this.config.slowMonsoonTurn){const r=random(hash(this.config.seed,'three-day-wind-end')),end=(initial<Math.PI/4?70+5*r():15+5*r())*Math.PI/180;return initial+(end-initial)*clip(at/(72*3600));}
    const phase=Math.asin(Math.max(-1,Math.min(1,(initial-Math.PI/4)/(Math.PI/6))));
    return Math.PI/4+Math.PI/6*Math.sin(2*Math.PI*at/86400+phase);
  };
  // Smoothed DEM slope tensor: the minor eigenvector follows the ridge.
  // This is a terrain-conditioned steering closure, not a city/direction table.
  // Static 7.5 km neighborhood relief from the actual DEM. City names are not
  // masks: plains fail, nearby foothills pass, including the inland mountain row.
  Model.prototype._buildTerrainAnchors=function(){
    this._terrainAnchors=null;if(!this.terrain)return;
    const g=this.env,fg=this.forcing,z=this.terrain.fields.z,peaks=Float64Array.from(z),land=Float64Array.from(this.terrain.fields.land),peak=new Float64Array(g.n),relief=new Float64Array(g.n),factor=new Float64Array(g.n);
    for(const [k,h,fraction] of this.terrain.meta.subgridTerrain?.cells||[]){peaks[k]=Math.max(peaks[k],h);land[k]=Math.max(land[k],fraction);}
    // Trigger relief and aerodynamic obstruction are different quantities.
    // A narrow island peak must not obstruct the whole surrounding sea cell.
    const obstruction=new Float64Array(fg.n);
    for(let k=0;k<fg.n;k++){const effectiveHeight=.75*z[k]+.25*peaks[k]*land[k];obstruction[k]=.85*clip((effectiveHeight-80)/350)*clip(land[k]/.6);}
    this._subgridTerrain={peaks,land,obstruction};
    const offsets=[];for(let j=-4;j<=4;j++)for(let i=-4;i<=4;i++)if(i*i+j*j<=9)offsets.push([i*2500,j*2500]);
    for(let k=0;k<g.n;k++){
      const x=(k%g.nx+.5)*g.dx,y=(Math.floor(k/g.nx)+.5)*g.dx;let lo=Infinity,hi=0;
      for(const [dx,dy]of offsets){const i=fg.index(x+dx,y+dy);if(i<0)continue;lo=Math.min(lo,z[i]);hi=Math.max(hi,peaks[i]);}
      peak[k]=hi;relief[k]=hi-lo;factor[k]=hi>=150&&hi-lo>=120?clip((hi-lo-80)/150):0;
    }
    this._terrainAnchors={peak,relief,factor};
  };
  Model.prototype._terrainAnchor=function(x,y){
    const k=this.env.index(x,y),a=this._terrainAnchors;
    if(k<0||!a)return {factor:0,peakM:0,reliefM:0};
    // Keep the mountain neighborhood, but require local hill support as well:
    // a distant peak must not turn an adjacent plain into a terrain trigger.
    const western=this.config.terrainBoundTrigger&&this._approxLongitude(x)<112.65;
    let localPeak=0;for(const dy of [-2500,0,2500])for(const dx of [-2500,0,2500]){const i=this.forcing.index(x+dx,y+dy);if(i>=0)localPeak=Math.max(localPeak,this._subgridTerrain.peaks[i]);}
    const valid=localPeak>=60&&(!western||(a.peak[k]>=180&&a.relief[k]>=140));
    return {factor:valid?a.factor[k]:0,peakM:a.peak[k],reliefM:a.relief[k],localPeakM:localPeak};
  };
  Model.prototype._buildTerrainSteering=function(){
    this._ridge=null;if(!this.config.terrainSteering)return;
    const g=this.env,f=this.fields,weights=Array.from({length:17},(_,i)=>Math.exp(-.5*((i-8)/4)**2)),norm=weights.reduce((a,b)=>a+b,0);
    const blur=input=>{const tmp=new Float64Array(g.n),out=new Float64Array(g.n);
      for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++)for(let d=-8;d<=8;d++)tmp[j*g.nx+i]+=weights[d+8]/norm*input[j*g.nx+Math.max(0,Math.min(g.nx-1,i+d))];
      for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++)for(let d=-8;d<=8;d++)out[j*g.nx+i]+=weights[d+8]/norm*tmp[Math.max(0,Math.min(g.ny-1,j+d))*g.nx+i];return out;};
    const xx=blur(Float64Array.from(f.zx,v=>v*v)),yy=blur(Float64Array.from(f.zy,v=>v*v)),xy=blur(Float64Array.from(f.zx,(v,k)=>v*f.zy[k]));
    const x=new Float64Array(g.n),y=new Float64Array(g.n),strength=new Float64Array(g.n);
    for(let k=0;k<g.n;k++){const trace=xx[k]+yy[k],coherence=Math.hypot(xx[k]-yy[k],2*xy[k])/Math.max(trace,1e-20),angle=.5*Math.atan2(2*xy[k],xx[k]-yy[k])+Math.PI/2;
      x[k]=Math.cos(angle);y[k]=Math.sin(angle);strength[k]=Math.min(.85,2*coherence)*clip(Math.sqrt(trace)/.01);}
    if(this.config.jetExitControl)for(let k=0;k<g.n;k++){
      const lon=this._approxLongitude((k%g.nx+.5)*g.dx),east=clip((lon-113.9)/1.4),blend=east*east*(3-2*east),sign=x[k]<0?-1:1;
      const ax=(1-blend)*x[k]+blend*sign,ay=(1-blend)*y[k],norm=Math.hypot(ax,ay);x[k]=ax/norm;y[k]=ay/norm;
      const relief=Math.sqrt(xx[k]+yy[k]);
      // Flat, weakly organized delta terrain stays nearly direction neutral.
      strength[k]=Math.min(.94,Math.max(strength[k],blend*.94))*clip((relief-.003)/.007);
    }
    this._ridge={x,y,strength};
  };
  Model.prototype._terrainSteer=function(k,u,v){
    if(!this._ridge)return [u,v];const r=this._ridge,speed=Math.hypot(u,v);if(speed<1e-9)return [u,v];
    const sign=u*r.x[k]+v*r.y[k]<0?-1:1,w=.25*r.strength[k]*(this.config.monsoon925?clip(2.5*(this._terrainAnchors?.factor[k]??0)):1),x=(1-w)*u/speed+w*sign*r.x[k],y=(1-w)*v/speed+w*sign*r.y[k],length=Math.hypot(x,y);
    return [speed*x/length,speed*y/length]; // redirect; do not slow cells to fake training
  };
  Model.prototype._applyDiurnalBoundaryLayer=function(k){
    if(!this.config.diurnalBoundaryLayer)return;
    const f=this.fields,land=f.land[k];if(land<=0)return;
    const daylight=at=>Math.max(0,Math.sin(Math.PI*(((this.preset.hour+at/3600)%24)-8)/12)),a=daylight(this.t),b=daylight(this.t+DT);
    // Daytime warming lowers RH at fixed water; sensible heat has an explicit
    // external budget. The cycle peaks at 14:00 local time and cools thereafter.
    const dT=3.5*land*(b-a),heat=1004*1400*dT*this.env.area;f.tl[k]+=dT;
    this.recordHeat(heat>=0?'in':'out','diurnalSensible',Math.abs(heat));
    // Exact exchange of vapor mixing ratios between fixed layer air masses.
    // Moisture is moved to the middle layer, never deleted to force a dry spell.
    const transfer=(f.wl[k]/1400-f.wm[k]/2600)*(1400*2600/4000)*(-Math.expm1(-land*(a+b)*.5*DT/10800));
    f.wl[k]-=transfer;f.wm[k]+=transfer;const mass=Math.abs(transfer)*this.env.area;
    this.recordWater(transfer>=0?'vaporL':'vaporM','out','diurnalEntrainment',mass);
    this.recordWater(transfer>=0?'vaporM':'vaporL','in','diurnalEntrainment',mass);
  };
  Model.prototype._approxLongitude=function(x){return (this.terrain?.meta.center[0]??112)+(x-this.config.width/2)/(111195*Math.cos((this.terrain?.meta.center[1]??22.5)*Math.PI/180));};
  // User-requested new-initiation exclusions; transported echoes remain valid.
  // Existing precipitation and cold outflow are still transported through here.
  Model.prototype._birthRegionAllowed=function(x,y){
    if(this.config.geography!=='real'||!this.config.organizedWarmSector)return true;
    const lon=this._approxLongitude(x),lat=(this.terrain?.meta.center[1]??22.5)+(y-this.config.height/2)/111195;
    const longmen=((lon-114.25)/.40)**2+((lat-23.78)/.32)**2<1;
    const northernDelta=lon>=112.95&&lon<=114.65&&lat>=22.83;
    return !(northernDelta||longmen||(lon>=108.5&&lon<=112&&lat<20.35)||(lon>=110.35&&lon<=112&&lat<21.65));
  };
  // Smooth humidity response for NEW parcels only. No clock threshold: real
  // moisture transport, night-time inflow humidification and daytime drying
  // decide how rapidly the probabilities rise or fall at different locations.
  Model.prototype._newInitiationMoisture=function(x,y){
    if(!this.config.organizedWarmSector)return 1;
    const k=this.env.index(x,y);if(k<0)return 0;
    const smooth=v=>{v=clip(v);return v*v*(3-2*v);};
    return smooth((this.fields.rhL[k]-.8)/.15)**2*smooth((this.fields.rhM[k]-.55)/.3);
  };
  Model.prototype._jetCoastWindow=function(x){
    if(!this.config.jetExitControl||this.config.geography!=='real')return 1;
    const lon=this._approxLongitude(x),smooth=x=>{x=clip(x);return x*x*(3-2*x);};
    return smooth((lon-110.15)/.25)*smooth((117.15-lon)/.25);
  };
  Model.prototype._jetFrame=function(bg){
    const c=this.coastalGeometry,angle=bg.windAngle??Math.atan2(c.axisDirection.y,c.axisDirection.x),at=bg.atSeconds??this.t;
    if(this._jetFrameCache?.owner===c&&this._jetFrameCache.angle===angle&&this._jetFrameCache.at===at)return this._jetFrameCache;
    const e={x:Math.cos(angle),y:Math.sin(angle)},t={x:e.y,y:-e.x};
    let sampled=c.sampledExitOffset??c.exitOffset,exit=c.exitOffset;
    if(this.config.jetExitControl){
      // Reproducible daily displacement; interpolate continuously so persistent
      // sources can survive for hours rather than jumping every physical step.
      if(c.options.exitOffset===undefined){const day=Math.floor(at/86400),f=at/86400-day,u=f*f*(3-2*f),value=n=>n===0?c.sampledExitOffset:-80000+160000*random(hash(this.config.seed,'jet-exit-day',n))();sampled=value(day)*(1-u)+value(day+1)*u;}
      exit=sampled;
    }else if(this.config.varyMonsoonDirection&&c.kind!=='straight-coast-prototype'&&this.config.coastalForcing?.exitOffset===undefined)exit=this._terrainJetExit(c.crossing,e,t).distance;
    return this._jetFrameCache={owner:c,angle,at,e,exit,sampledExit:sampled,placement:sampled<0?'offshore':'inland'};
  };
  Model.prototype._directionalJetShift=function(bg){
    if(!this.terrain||!this.config.organizedWarmSector)return {x:0,y:0};
    const angle=bg.windAngle??this._monsoonAngle(this.t),sw=clip((angle*180/Math.PI-28)/25),s=sw*sw*(3-2*sw);
    const jitter=(random(hash(this.config.seed,'directional-jet-target'))()-.5)*.6;
    const south=clip((angle*180/Math.PI-55)/20),ss=south*south*(3-2*south);
    const lon=((111.75+jitter)*s+(114.25+jitter)*(1-s))*(1-ss)+(113.65+jitter)*ss,lat=(21.85*s+22.45*(1-s))*(1-ss)+22.2*ss;
    const x=this.config.width/2+(lon-this.terrain.meta.center[0])*111195*Math.cos(this.terrain.meta.center[1]*Math.PI/180),y=this.config.height/2+(lat-this.terrain.meta.center[1])*111195;
    return {x:x-this.coastalGeometry.crossing.x,y:y-this.coastalGeometry.crossing.y};
  };
  // Shore-normal distance makes the same deceleration zone follow coastal bends.
  // Wind, lifting and moisture access share these coordinates.
  Model.prototype._jetCoordinates=function(x,y,bg,d,nx,ny){
    const c=this.coastalGeometry,frame=this._jetFrame(bg),e=frame.e,dx=x-c.crossing.x,dy=y-c.crossing.y;
    let along=dx*e.x+dy*e.y;
    if(this.config.jetExitControl&&this.config.jetExitGeometry==='coast_following'&&this.terrain){
      const f=this.terrain.fields,g=this.forcing;
      d??=g.sample(f.signedDistance,x,y);
      // The seeded offset is a coast-normal penetration distance. Dividing
      // by a near-tangential coast normal displaced western foothills far beyond
      // the drawn exit and favored estuaries instead of the actual mountain row.
      along=d;
    }
    // Shift the seeded WSW eastern deceleration distribution shoreward,
    // not the cells themselves. Wind, moisture and lifting use the SAME exit.
    // Signed/random daily offsets retain offshore, inland and southward tracks.
    const east=this.terrain&&this.config.organizedWarmSector?clip((this._approxLongitude(x)-114.65)/.5)*clip((48-frame.angle*180/Math.PI)/15):0;
    const exit=frame.exit*(1-.35*east),shift=this._directionalJetShift(bg);return {along,exit,cross:-(dx-shift.x)*e.y+(dy-shift.y)*e.x};
  };
  // An upstream active root intercepts the same low-level feed corridor.
  // Other coastal lanes remain free; existing travelling cells keep their physics.
  Model.prototype._sourceOrder=function(a,b,bg){
    if(this.config.organizedWarmSector&&this.terrain){const g=this.forcing,d=this.terrain.fields.signedDistance;return g.sample(d,a.x,a.y)-g.sample(d,b.x,b.y);}
    const e=this.coastalGeometry?this._jetFrame(bg).e:{x:0,y:1};return (a.x-b.x)*e.x+(a.y-b.y)*e.y;
  };
  Model.prototype._upstreamSource=function(x,y,bg,sources=this.triggerSources){
    if(!this.config.upstreamSourceBlocking)return null;
    const coastal=this.config.organizedWarmSector&&this.terrain,e=coastal?this._coastInward(x,y):this._jetFrame(bg).e;
    for(const source of sources){const dx=x-source.x,dy=y-source.y,along=dx*e.x+dy*e.y,cross=Math.abs(-dx*e.y+dy*e.x);
      if(along>(coastal?10000:4000)&&along<160000&&cross<(coastal?22000+.1*along:this.config.organizedWarmSector?14000+.08*along:22000+.12*along))return source;
    }
    return null;
  };
  Model.prototype._coastInward=function(x,y){
    const f=this.terrain?.fields,g=this.forcing;if(!f)return {x:0,y:1};
    const nx=g.sample(f.coastX,x,y),ny=g.sample(f.coastY,x,y),norm=Math.hypot(nx,ny);
    return norm>.1?{x:nx/norm,y:ny/norm}:{x:0,y:1};
  };
  // A continuous southern cold strip blocks NEW roots farther inland. It does
  // not veto an existing root supplied by an independently verified warm flank.
  Model.prototype._southernColdBarrier=function(x,y){
    if(!this.config.organizedWarmSector||!this.terrain)return false;
    const n=this._coastInward(x,y);let run=0;
    for(let d=5000;d<=60000;d+=5000){const a=this.surfaceAccess(x-n.x*d,y-n.y*d);
      run=a.inDomain&&a.cold&&a.h>=100?run+5000:0;if(run>=15000)return true;
    }return false;
  };
  // User-specified regional response: SSW/SW favors the NE-oriented western
  // coastal ranges, WSW favors the eastern coastal belt. PRD remains accessible.
  // This directional envelope is explicit parameterization, not inferred DEM data.
  Model.prototype._coastalDirectionAccess=function(x,bg){
    if(!this.config.directionalCoastalTrigger)return 1;
    const smooth=x=>{x=clip(x);return x*x*(3-2*x);},lon=this._approxLongitude(x),angle=(bg.windAngle??this._monsoonAngle(this.t))*180/Math.PI;
    const west=1-smooth((lon-112.6)/.7),east=smooth((lon-113.9)/.8),sw=smooth((angle-30)/25);
    const prd=smooth((lon-112.65)/.4)*(1-smooth((lon-114.5)/.4));
    const preference=Math.max(west*sw+east*(1-sw)+(1-west-east)*.65,.92*prd);
    return preference<.12?0:preference;
  };
  Model.prototype._trainingBarrier=function(a,speed){
    if(!a.inDomain)return true;if(!a.cold)return false;
    const coldSpeed=Math.sqrt(2*9.81*a.Q/300);
    return this.config.monsoon925&&this.config.organizedWarmSector?a.h>=1200||(a.h>450&&speed<.85*coldSpeed):a.h>=1400||speed<1.25*coldSpeed;
  };
  // The low-layer water inventory spans 1400 m. Surface cooling blocks new
  // surface roots, but does not erase the entire warm column above a shallow
  // cold layer. Every plume competes for this same fractional water capacity.
  Model.prototype._columnSupplyFraction=function(a,x,y){
    if(!a.inDomain)return 0;if(!a.cold)return 1;
    if(!this.config.monsoon925||!this.config.organizedWarmSector)return 0;
    const k=this.env.index(x,y);if(k<0)return 0;
    if(this._trainingBarrier(a,Math.hypot(this.fields.u[k],this.fields.v[k])))return 0;
    return clip(1-a.h/1400);
  };
  // Trace the actual low-level inflow toward a warm intake. A shallow cold layer
  // can be overrun only if inflow kinetic energy exceeds its density-current head.
  // Only the remaining column above shallow cold air is accessible; supplyFootprint
  // and the global capacity ledger use the same fractional water budget.
  Model.prototype._trainingFeed=function(x,y,moving=false){
    const k=this.env.index(x,y);if(k<0)return {accessible:false,reason:'outside'};
    const u=this.fields.u[k],v=this.fields.v[k],speed=Math.hypot(u,v),ex=u/Math.max(speed,1e-9),ey=v/Math.max(speed,1e-9),angle=Math.atan2(v,u);
    if(speed<3)return {accessible:false,reason:'weakInflow',speed};
    const offsets=this.config.trainingInflowFan?[0,-Math.PI/6,Math.PI/6,-Math.PI/3,Math.PI/3]:[0],limit=moving&&this.config.organizedWarmSector?45000:this.config.trainingInflowFan?120000:60000;
    let rejected={accessible:false,reason:'noConnectedWarmIntake',speed,maxColdSpeed:0},best=null;
    for(const offset of offsets){
      const ax=Math.cos(angle+offset),ay=Math.sin(angle+offset);let headLift=0,maxColdSpeed=0,warmRun=0;
      for(let distance=0;distance<=limit;distance+=2500){
        const px=x-ax*distance,py=y-ay*distance,a=this.surfaceAccess(px,py),i=this.env.index(px,py);
        if(!a.inDomain||i<0)break;
        if(a.cold){
          const coldSpeed=Math.sqrt(2*9.81*a.Q/300);maxColdSpeed=Math.max(maxColdSpeed,coldSpeed);
          if(this._trainingBarrier(a,speed)){rejected={accessible:false,reason:'coldBarrier',speed,maxColdSpeed,distance};break;}
          warmRun=this._columnSupplyFraction(a,px,py)>=.4?warmRun+2500:0;
          headLift=Math.max(headLift,Math.min(250,a.h));
        }else warmRun+=2500;
        if(distance>=10000&&warmRun>=7500){
          const rh=this.fields.rhL[i],energy=this.fields.el[i],candidate={accessible:rh>.75&&energy>.25,reason:rh<=.75?'dryInflow':energy<=.25?'weakEnergy':null,x:px,y:py,angle,speed,distance,offset,headLift,maxColdSpeed,rh,energy};
          if(candidate.accessible&&moving&&this.config.organizedWarmSector){const bg=this.background(),focus=this._inflowFocus(px,py,bg),brake=this._hillBrake(px,py,bg);if(focus<.3||brake>.8){candidate.accessible=false;candidate.reason='outsideFedJet';}}
          if(candidate.accessible){if(!best||distance<best.distance)best=candidate;break;}
          rejected=candidate;
          // A depleted nearby parcel is not the end of an open inflow path.
          // Keep searching farther upstream until a real barrier or domain edge.
        }
      }
    }
    return best||rejected;
  };
  Model.prototype._movingTrainingFeed=function(cell){
    const local=this._trainingFeed(cell.x,cell.y,true);
    if(local.accessible||!this.config.organizedWarmSector)return local;
    const source=this.triggerSources.find(s=>s.id===cell.triggerSourceId);
    if(!source)return local;
    const k=this.env.index(source.x,source.y),u=this.fields.um[k],v=this.fields.vm[k],speed=Math.hypot(u,v),dx=cell.x-source.x,dy=cell.y-source.y,distance=Math.hypot(dx,dy),along=(dx*u+dy*v)/Math.max(1,speed),cross=Math.abs(dx*v-dy*u)/Math.max(1,speed);
    if(along<0||distance>108000||cross>25000+.1*along)return local;
    const feed=this._trainingFeed(source.x,source.y);if(!feed.accessible)return local;
    // Same source, same finite water budget. A detached core cannot find a new
    // interior donor or cross a deep blocking pool to prolong its life.
    const segments=Math.max(1,Math.ceil(distance/5000));
    for(let j=0;j<=segments;j++){const f=j/segments,a=this.surfaceAccess(source.x+dx*f,source.y+dy*f);
      if(this._trainingBarrier(a,feed.speed))return {...local,accessible:false,reason:'sourceCorridorBlocked'};
    }
    return {...feed,sourceId:source.id,sourceDistanceM:distance,sharedSourceCorridor:true};
  };
  Model.prototype._persistentSourceGate=function(source,bg){
    const ordinary=this.gate(source.x,source.y,0,bg,false);
    if(!this.config.connectedTrainingFeed||!this._birthRegionAllowed(source.x,source.y))return ordinary;
    const inlet=this._trainingFeed(source.x,source.y);
    if(!inlet.accessible)return {...ordinary,F:0,rejection:inlet.reason,evidence:{...ordinary.evidence,connectedFeed:inlet}};
    if(this.config.organizedWarmSector&&this.config.jetExitControl){
      const k=this.env.index(source.x,source.y),f=this.fields,jet=this._jetExitAccess(source.x,source.y,bg),focus=this._inflowFocus(inlet.x,inlet.y,bg),rh=inlet.rh,energy=inlet.energy;
      // A previously lifted plume does not have to overcome the complete new-
      // parcel LFC every ten minutes. Maintenance still needs connected moisture,
      // a live exit/hill region and resolved convergence; no unlimited memory.
      const lifting=jet.ascent>.008||f.wConvergence[k]>.025||f.wTerrain[k]>.025;
      const lfc=70+1200*Math.max(0,1-rh)+10*Math.max(0,bg.iL),plumeLift=lifting?300:0,displacement=f.xiL[k]+inlet.headLift+plumeLift;
      const support=lifting&&jet.factor>0?clip(jet.factor/.08)*clip(focus/.3)*clip((displacement-.65*lfc)/100):0;
      const F=clip((rh-.72)/.2)*clip((energy-.22)/.6)*support;
      return {...ordinary,F,rh,energy,CIN:bg.iL,power:.08*displacement,rejection:F>0?null:'maintenanceEnvironment',evidence:{...ordinary.evidence,F,connectedFeed:inlet,maintenance:{resolvedLifting:lifting,jetFactor:jet.factor,focus,plumeLiftM:plumeLift,displacementM:displacement,lfcM:lfc}}};
    }
    // A fed, established plume needs less displacement than a brand-new parcel;
    // support is bounded and disappears when resolved lifting or the intake closes.
    const k=this.env.index(source.x,source.y),f=this.fields,ongoingLift=this.config.jetExitControl?this._jetExitAccess(source.x,source.y,bg).ascent>.02:(f.wConvergence[k]>.045||f.wTerrain[k]>.025||inlet.headLift>0),plumeLift=ongoingLift?200*clip((this.t-source.activated)/1800):0,lift=this._liftAccess(k,source.x,source.y,0,bg,inlet.headLift+plumeLift,inlet),rh=inlet.rh,energy=inlet.energy,CIN=bg.iL+20*clip((.75-rh)/.25),power=.08*(f.xiL[k]+inlet.headLift+plumeLift);
    const F=clip((rh-.65)/.25)*clip((energy-.15)/.65)*clip((power-CIN)/15)*lift.factor;
    return {...ordinary,F,rh,energy,CIN,power,rejection:F>0?null:lift.reason||'inhibition',evidence:{...ordinary.evidence,F,connectedFeed:inlet,establishedPlumeLiftM:plumeLift,focusedLift:lift}};
  };
  Model.prototype._monsoonSpeeds=function(bg){
    const p=this.config.coastalWindParameters,S=Math.max(0,bg.V/this.preset.baseV);
    if(S===0)return {background:0,jet:0};
    const background=Math.max(10,Math.min(13,Math.hypot(p.backgroundAlong,p.backgroundNormal)+1.2*Math.tanh(2*(S-1))));
    return {background,jet:Math.max(13,Math.min(15,background+Math.hypot(p.jetExcessAlong,p.jetExcessNormal)))};
  };
  // The actual hill footprint brakes flow locally. A decaying downstream wake
  // must not project neighborhood peaks onto offshore water or exhaust every
  // later mountain front. Flat shoreline alone produces no obstruction.
  Model.prototype._hillBrakeField=function(bg){
    if(!this.config.hillJetBraking||!this._terrainAnchors)return null;
    const angle=bg.windAngle??this._monsoonAngle(this.t);
    if(this._hillBrakeCache?.angle===angle)return this._hillBrakeCache.field;
    const g=this.env,fg=this.forcing,obstacle=this._subgridTerrain.obstruction,e={x:Math.cos(angle),y:Math.sin(angle)},field=new Float64Array(g.n);
    for(let k=0;k<g.n;k++){
      const x=(k%g.nx+.5)*g.dx,y=(Math.floor(k/g.nx)+.5)*g.dx;let brake=0;
      for(const distance of [0,2500,5000,10000,20000,35000,50000,65000]){
        const px=x-e.x*distance,py=y-e.y*distance;if(fg.index(px,py)<0)continue;
        brake=Math.max(brake,fg.sample(obstacle,px,py)*Math.exp(-distance/25000));
      }
      field[k]=brake;
    }
    this._hillBrakeCache={angle,field};return field;
  };
  Model.prototype._hillBrake=function(x,y,bg){
    const field=this._hillBrakeField(bg);return field&&this.env.index(x,y)>=0?this.env.sample(field,x,y):0;
  };
  // Yangchun–Enping: the eastern flank of the range combines windward lifting
  // with channel-like acceleration. A completely enclosed valley is optional;
  // the rain-bearing corridor should remain east of the resolved western ridge.
  Model.prototype._westernSlopeChannel=function(x,y,bg){
    if(!this.terrain||!this.config.terrainBoundTrigger)return {factor:0,coastalWeight:1};
    const lon=this._approxLongitude(x),g=this.forcing,z=this.terrain.fields.z,d=g.sample(this.terrain.fields.signedDistance,x,y),smooth=v=>{v=clip(v);return v*v*(3-2*v);};
    const region=smooth((lon-111.25)/.25)*smooth((112.65-lon)/.3);
    if(!region)return {factor:0,coastalWeight:1};
    // Rain-bearing foothills SW of Yangchun station and NE of Yangjiang station.
    // Spatial eligibility narrows the terrain mechanism; it never creates rain.
    const lat=(this.terrain.meta.center[1])+(y-this.config.height/2)/111195;
    const corridor=(cx,cy)=>{const dx=(lon-cx)*102700,dy=(lat-cy)*111195,along=(dx+dy)/Math.SQRT2,cross=(dy-dx)/Math.SQRT2;return Math.exp(-.5*((along/26000)**2+(cross/13000)**2));};
    const foothills=Math.max(corridor(111.65,22.03),corridor(112.14,22.01))*smooth((22.32-lat)/.20)*smooth((lat-21.82)/.12),corridorWeight=1-region+region*foothills;
    const angle=bg.windAngle??this._monsoonAngle(this.t),nx=-Math.sin(angle),ny=Math.cos(angle),floor=g.sample(z,x,y),flanks=[];
    for(const side of [-1,1]){let peak=0;for(const distance of [7500,15000,22500]){const px=x+side*nx*distance,py=y+side*ny*distance;if(g.index(px,py)>=0)peak=Math.max(peak,g.sample(z,px,py));}flanks.push(peak);}
    let westernRidge=0,easternTerrain=0;
    for(const offset of [-7500,0,7500])for(const distance of [7500,15000,22500]){westernRidge=Math.max(westernRidge,g.sample(z,x-distance,y+offset));easternTerrain=Math.max(easternTerrain,g.sample(z,x+distance,y+offset));}
    const relief=Math.min(...flanks)-floor,eastRelief=westernRidge-floor,inland=smooth((d-14000)/16000)*(1-smooth((d-55000)/20000));
    const easternFlank=smooth((eastRelief-40)/160)*smooth((westernRidge-easternTerrain+100)/220),channel=smooth((relief-40)/140)*smooth((Math.min(...flanks)-100)/120);
    return {factor:region*foothills*inland*Math.max(easternFlank,channel*(.3+.7*easternFlank)),coastalWeight:corridorWeight*(1-region*(1-smooth((d-12000)/16000))),reliefM:Math.max(relief,eastRelief),flankHeightsM:flanks,westernRidgeM:westernRidge,easternFlank,channel};
  };
  Model.prototype._jetExitAccess=function(x,y,bg){
    if(!this.config.jetExitControl)return {factor:1,ascent:0,alignment:1};
    if(!this.coastalGeometry)return {factor:0,ascent:0,alignment:1};
    const c=this.coastalGeometry,p=this.config.coastalWindParameters,frame=this._jetFrame(bg),coord=this._jetCoordinates(x,y,bg),l=coord.along-coord.exit,cross=coord.cross;
    const eastWeight=this.terrain&&this.config.organizedWarmSector?clip((this._approxLongitude(x)-114.65)/.5)*clip((48-frame.angle*180/Math.PI)/15):0,exitSupport=1-eastWeight*(1-Math.exp(-.5*(l/(1.25*p.exitLength))**2));
    const across=Math.exp(-.5*(cross/p.sigmaJet)**2)*this._jetCoastWindow(x),along=clip(1-(l/(2*p.exitLength))**2)**2;
    const distance=this.terrain?this.forcing.sample(this.terrain.fields.signedDistance,x,y):y-c.crossing.y;
    const land=this.terrain?this.forcing.sample(this.terrain.fields.land,x,y):distance>=0?1:0,anchor=this._terrainAnchor(x,y);
    const mainland=!this._coastalMainland||this._coastalMainland[this.forcing.index(x,y)]===1;
    const own=this.forcing.index(x,y),subgrid=this._subgridTerrain,island=own>=0&&subgrid&&subgrid.peaks[own]>=150&&subgrid.land[own]>=.08&&Math.abs(distance)<40000;
    const slopeChannel=this._westernSlopeChannel(x,y,bg);
    const prdLon=this._approxLongitude(x),prd=prdLon>=112.7&&prdLon<=114.65;
    const lat=(this.terrain?.meta.center[1]??22.5)+(y-this.config.height/2)/111195;
    const coastCap=prd?clip((22.83-lat)/.19)*clip((45000-distance)/25000):1;
    const terrainSite=coastCap*(this.config.terrainBoundTrigger?((mainland&&land>=.45)||island?Math.max(anchor.factor*slopeChannel.coastalWeight,slopeChannel.factor):0):(distance>=0?1:0)),seaSite=land<.5&&!island&&distance<=0?1:0;
    const site=frame.placement==='offshore'?seaSite:terrainSite,remainingJet=1-bg.exitEnvelope*.5*(1+Math.tanh(l/p.exitLength));
    const k=this.env.index(x,y),r=this._ridge,speed=Math.hypot(frame.e.x,frame.e.y),parallel=k>=0&&r?Math.abs((r.x[k]*frame.e.x+r.y[k]*frame.e.y)/speed):1;
    const longitude=this._approxLongitude(x),deltaNeutral=longitude>=112.7&&longitude<=114.35;
    const alignment=deltaNeutral?1:k>=0&&r?1-r.strength[k]*(1-parallel*parallel):1;
    const speeds=this.config.boundedMonsoon?this._monsoonSpeeds(bg):null,contrast=speeds?speeds.jet-speeds.background:Math.min(5,Math.hypot(p.jetExcessAlong,p.jetExcessNormal))*Math.min(1,Math.max(0,bg.V/this.preset.baseV));
    const brake=this._hillBrake(x,y,bg),up=this._hillBrake(x-frame.e.x*7500,y-frame.e.y*7500,bg),down=this._hillBrake(x+frame.e.x*7500,y+frame.e.y*7500,bg),hillFront=clip((Math.max(brake,down)-up)/.25);
    const gradient=contrast*bg.exitEnvelope*(1-Math.tanh(l/p.exitLength)**2)/(2*p.exitLength)*(1-brake);
    // Actual residual inflow decides whether a mountain front is reachable.
    // A nearby offshore exit does not switch off every coastal hill by label;
    // a distant offshore exit still cuts the jet off before it reaches land.
    const hillEligible=terrainSite>0&&remainingJet>.28&&distance<=coord.exit+2*p.exitLength;
    const slopeGate=hillEligible?slopeChannel.factor*remainingJet:0;
    const hillAscent=hillEligible?1800*(contrast+1.5)*remainingJet*Math.max(0,Math.max(brake,down)-up)/15000:0;
    const slopeAscent=slopeGate*Math.min(.3,(speeds?.jet??13)*Math.max(0,slopeChannel.reliefM||0)/15000);
    // Front-side hills can lift a southerly inflow before the sampled broad exit.
    // Require local relief and a reachable jet; never extend this inland.
    const coastalPrd=(prd&&lat<22.72||prdLon>=114.9&&prdLon<=116.6&&Math.abs(l)<p.exitLength)&&distance<30000;
    const hillGate=hillEligible?Math.max(hillFront,coastalPrd?.55:0)*terrainSite*remainingJet:0;
    const prdLift=coastalPrd&&hillEligible ? .13*terrainSite*remainingJet*clip(anchor.reliefM/160):0;
    return {factor:clip(Math.max(along*(1-brake)*site,hillGate)+.6*slopeGate)*across*exitSupport*this._coastalDirectionAccess(x,bg),siteFactor:Math.max(site,hillEligible?terrainSite:0),directionAccess:this._coastalDirectionAccess(x,bg),terrainAnchor:anchor,slopeChannel,hillBrake:brake,hillFront,ascent:(Math.max(1800*gradient,hillAscent,prdLift)+.6*slopeAscent)*across,alignment,placement:frame.placement,sampledExitM:frame.sampledExit,exitM:coord.exit,distanceFromExitM:l,crossAxisM:cross};
  };
  Model.prototype._inflowFocus=function(x,y,bg){
    const c=this.coastalGeometry;
    if(c){const frame=this._jetFrame(bg),coord=this._jetCoordinates(x,y,bg),p=coord.cross;
      const l=coord.along,end=coord.exit,termination=1-bg.exitEnvelope*.5*(1+Math.tanh((l-end)/this.config.coastalWindParameters.exitLength));
      return clip((Math.exp(-.5*(p/this.config.coastalWindParameters.sigmaJet)**2)*termination*(1-.35*this._hillBrake(x,y,bg))-.12)/.68);}
    if(bg.axis){const a=bg.axis,dx=x-this.config.width/2-a.x,dy=y-this.config.height/2-a.y,p=-a.ey*dx+a.ex*dy;
      return clip((Math.exp(-.5*(p/a.width)**2)-.2)/.65);}
    return 1;
  };
  Model.prototype._advanceLiftColumn=function(k,x,y,div,bg){
    const f=this.fields,g=this.env,u=f.u[k],v=f.v[k],speed=Math.hypot(u,v),ex=u/Math.max(speed,1),ey=v/Math.max(speed,1);
    const upstream=g.sample(f.z,x-20000*ex,y-20000*ey),downstream=g.sample(f.z,x+5000*ex,y+5000*ey),z=f.z[k];
    // Use net windward relief over 20 km; isolated tiny slopes are insufficient.
    f.terrainRise[k]=this.config.disableTerrainLift?0:Math.max(0,z-upstream);
    const terrain=this.config.disableTerrainLift?0:.65*(u*f.zx[k]+v*f.zy[k]);
    const jet=this._jetExitAccess(x,y,bg),convergence=this.config.jetExitControl?Math.max(-1200*div,jet.ascent):-1200*div,tau=this.config.jetExitControl?2700:900,e=Math.exp(-DT/tau);
    f.wTerrain[k]=Math.max(-.8,Math.min(.8,terrain));f.wConvergence[k]=Math.max(-.8,Math.min(.8,convergence));
    f.xiTerrain[k]=this.config.disableTerrainLift?0:.65*f.terrainRise[k];
    f.xiConvergence[k]=Math.max(0,f.xiConvergence[k]*e+tau*(f.wConvergence[k]+Math.min(0,f.wTerrain[k]))*(1-e));
    // Descent erodes the accumulated parcel displacement, including the other source.
    f.xiL[k]=Math.max(0,f.xiTerrain[k]+f.xiConvergence[k]);
    const midAscent=Math.min(.5,Math.max(0,convergence)*.6+Math.max(0,2000*f.upperDiv[k])*.15);
    f.xiM[k]=Math.max(0,f.xiM[k]*e+tau*midAscent*(1-e));
    f.inflowFocus[k]=this._inflowFocus(x-u*1800,y-v*1800,bg);
    const cin=bg.iL+20*clip((.75-f.rhL[k])/.25);
    f.lfcHeight[k]=70+1200*Math.max(0,1-f.rhL[k])+10*Math.max(0,cin);
    const terrainActive=!this.config.jetExitControl&&f.terrainRise[k]>60&&terrain>.025&&downstream>upstream;
    const convergenceActive=convergence>.045;
    f.triggerLow[k]=(terrainActive||convergenceActive)?clip((f.xiL[k]*jet.alignment-f.lfcHeight[k])/140)*f.inflowFocus[k]*jet.factor:0;
    f.triggerMid[k]=convergence>.12?clip((f.xiM[k]-(300+800*Math.max(0,1-f.rhM[k])))/160)*f.inflowFocus[k]:0;
  };
  Model.prototype._liftAccess=function(k,x,y,layer,bg,headLift=0,inlet=null){
    if(k<0)return {factor:0,reason:'outside'};
    const f=this.fields,g=this.env,feed=inlet?g.index(inlet.x,inlet.y):k;
    if(feed<0)return {factor:0,reason:'noWarmFeed'};
    const rh=layer?f.rhM[feed]:f.rhL[feed],cin=layer?bg.iM:bg.iL;
    const lfc=layer?300+800*Math.max(0,1-rh)+10*Math.max(0,cin):70+1200*Math.max(0,1-rh)+10*Math.max(0,cin);
    const jet=this._jetExitAccess(x,y,bg),displacement=((layer?f.xiM[k]:f.xiL[k])+Math.max(0,headLift))*jet.alignment,focus=f.inflowFocus[feed];
    const active=this.config.jetExitControl?(jet.ascent>.02?1:0):headLift>0?1:layer?(f.wConvergence[k]>.12?1:0):((f.wTerrain[k]>.025&&f.terrainRise[k]>60)||f.wConvergence[k]>.045?1:0);
    const factor=active*focus*jet.factor*clip((displacement-lfc)/(this.config.organizedWarmSector?100:140));
    return {factor,jetExit:jet,reason:!jet.factor?'outsideJetExit':!focus?'outsideMoistInflow':!active?'noLocalLifting':displacement<=lfc?'belowLFC':null,lfcM:lfc,parcelDisplacementM:displacement,terrainDisplacementM:f.xiTerrain[k],convergenceDisplacementM:f.xiConvergence[k],terrainRiseM:f.terrainRise[k],terrainVelocityMS:f.wTerrain[k],convergenceVelocityMS:f.wConvergence[k],inflowFocus:focus,headLiftM:headLift};
  };
  Model.prototype._focusedGate=function(x,y,layer,bg,environmentOnly){
    if(!this._birthRegionAllowed(x,y))return {F:0,power:0,coldPower:0,CIN:0,rejection:'excludedSouthernRegion'};
    const f=this.fields,k=this.env.index(x,y);
    if(k<0)return {F:0,power:0,coldPower:0,CIN:0,rejection:'outside'};
    const rh=layer?f.rhM[k]:f.rhL[k],energy=layer?f.em[k]:f.el[k],access=this.surfaceAccess(x,y),CIN=(layer?bg.iM:bg.iL)+20*clip(((layer?.65:.75)-rh)/.25)+(layer?0:.08*access.Q),power=.08*(layer?f.xiM[k]:f.xiL[k]);
    const lift=this._liftAccess(k,x,y,layer,bg),wetness=this._newInitiationMoisture(x,y),F=(!layer&&!access.warmAccessible)?0:clip((rh-(layer?.45:.65))/(layer?.35:.25))*clip((energy-.15)/.65)*clip((power-CIN)/15)*lift.factor*wetness;
    let result={F,power,coldPower:0,CIN,rh,energy,Qlocal:access.Q,source:'environment',parent:null,rejection:F>0?null:!access.warmAccessible&&!layer?'fineCold':lift.reason||'inhibition',evidence:{F,Kenv:power,Kcp:0,CIN,rh,energy,surfaceAccess:access,position:{x,y},triggerLayer:layer?'mid':'low',focusedLift:lift,mechanism:f.xiTerrain[k]>f.xiConvergence[k]?'terrain':'convergence'}};
    if(!environmentOnly&&!layer&&!this.config.disableCold){const b=this._areaFrontExposure(x,y);if(b){const front=this._boundaryEventGate(b,x,y,bg);if(front.F>F)result=front;}}
    return result;
  };

  Model.prototype.diagnoseEnvironment=function*(recover){
    const f=this.fields,g=this.env,bg=this.background();yield*this.updateSurfaceFractions();this.aggregate(this.h,this.cold,f.h,g);this.aggregate(this.q,this.cold,f.q,g);
    for(let j=0;j<g.ny;j++){for(let i=0;i<g.nx;i++){
      const k=j*g.nx+i;if(recover){this._applyDiurnalBoundaryLayer(k);const surface=(.08*(1-f.land[k])+.02*f.land[k])*DT/3600;f.wl[k]+=surface;this.stats.surface+=surface*g.area;this.recordWater('vaporL','in','surface',surface*g.area);this.recordHeat('in','surfaceVapor',surface*g.area*2.5e6);}
      for(const [w,t,c,m,p]of [['wl','tl','qcL',1400,95000],['wm','tm','qcM',2600,75000]]){const r=phaseAdjustment(f[w][k],f[t][k],m,p,f[c][k]);this.stats.rootCalls++;f[w][k]=r.water;f[t][k]=r.temperature;f[c][k]=r.cloud;this.stats.condensed+=r.condensed*g.area;this.stats.evaporated+=r.evaporated*g.area;this.stats.sources.environmentCondensed+=r.condensed*g.area;this.stats.sources.environmentEvaporated+=r.evaporated*g.area;this.stats.sources.latentHeating+=r.condensed*g.area*2.5e6;this.stats.sources.latentCooling+=r.evaporated*g.area*2.5e6;const vapor=w==='wl'?'vaporL':'vaporM',cloud=w==='wl'?'cloudL':'cloudM';this.recordWater(vapor,'out','cloudCondensation',r.condensed*g.area);this.recordWater(cloud,'in','cloudCondensation',r.condensed*g.area);this.recordWater(cloud,'out','cloudEvaporation',r.evaporated*g.area);this.recordWater(vapor,'in','cloudEvaporation',r.evaporated*g.area);}
      f.sl[k]=saturation(f.tl[k]);f.sm[k]=saturation(f.tm[k],2600,75000);f.rhL[k]=f.wl[k]/f.sl[k];f.rhM[k]=f.wm[k]/f.sm[k];
      if(recover){const gl=clip((f.rhL[k]-.45)/.45)*Math.exp(-f.q[k]/300),gm=clip((f.rhM[k]-.35)/.5);const tauL=this.config.jetExitControl?Math.min(7200,30000/Math.max(1,Math.hypot(f.u[k],f.v[k]))):7200,tauM=this.config.jetExitControl?Math.min(7200,30000/Math.max(1,Math.hypot(f.um[k],f.vm[k]))):7200;f.el[k]=bg.eL+(f.el[k]-bg.eL)*Math.exp(-gl*DT/tauL);f.em[k]=bg.eM+(f.em[k]-bg.eM)*Math.exp(-gm*DT/tauM);
        const div=this.airFlux?.dL[k]??f.divL[k];
        if(this.config.initiationModel==='focused_lift')this._advanceLiftColumn(k,(i+.5)*g.dx,(j+.5)*g.dx,div,bg);
        else {const wL=Math.min(.8,1200*Math.max(-div,0)+.4*Math.max(f.u[k]*f.zx[k]+f.v[k]*f.zy[k],0)),wM=Math.min(.5,2000*Math.max(f.upperDiv[k],0)),e=Math.exp(-DT/600);f.xiL[k]=f.xiL[k]*e+600*wL*(1-e);f.xiM[k]=f.xiM[k]*e+600*wM*(1-e);}
      }
      f.KenvL[k]=.08*f.xiL[k];f.KenvM[k]=.08*f.xiM[k];f.CINL[k]=bg.iL+20*clip((.75-f.rhL[k])/.25)+.08*f.q[k];f.CINM[k]=bg.iM+20*clip((.65-f.rhM[k])/.25);
    }if(j%32===31)yield;}
  };


  // Mesoscale anvil outflow: conservative mixing of DETRAINED condensate only.
  // Flux pairs conserve mass; the CFL bound preserves positivity at the 600 s
  // physical step. Advective export, evaporation and fallout retain their ledgers.
  Model.prototype._spreadStratiform=function*(){
    if(!this.config.stratiformOutflow)return;
    const g=this.precip,K=45000,steps=Math.ceil(DT*K/(.24*g.dx*g.dx)),a=DT*K/(steps*g.dx*g.dx),delta=this.buffer('stratiformMix',g.n);
    for(const water of [this.precipWater.qa,this.precipWater.upper_detrained]){
      if(!water.some(v=>v>0))continue;
      for(let step=0;step<steps;step++){
        delta.fill(0);
        for(let k=0;k<g.n;k++){
          if(k%g.nx<g.nx-1){const flux=a*(water[k]-water[k+1]);delta[k]-=flux;delta[k+1]+=flux;}
          if(k+g.nx<g.n){const flux=a*(water[k]-water[k+g.nx]);delta[k]-=flux;delta[k+g.nx]+=flux;}
        }
        for(let k=0;k<g.n;k++)water[k]+=delta[k];yield;
      }
    }
  };
  Model.prototype.release=function*(){
    const pg=this.precip,g=this.env,f=this.fields,P=this.precipWater,origins=['core','detrained','boundary'],S=this.stats.sources;
    const coreSource=this.buffer('continuousCoreRelease',pg.n);coreSource.fill(0);this._continuousCoreRelease=coreSource;
    yield 'cells';
    for(const c of this.cells){const dt=c.activeStepSeconds??DT;if(!dt||c.M<=0)continue;
      const rate=(.5+.5*clip(c.a))/360,decay=1-Math.exp(-dt*rate),supplied=Math.min(c.M,c.suppliedKgThisStep||0),amount=Math.max(0,c.M-supplied)*decay+supplied*(1-decay/(dt*rate)),detachFraction=(this.config.stratiformOutflow ? .22 : .12)+.30*(1-clip(c.supplyRatio??0)),detach=amount*detachFraction,core=amount-detach;c.M-=amount;
      S.detrained+=detach;this.recordWater('core','out','detrainment',detach);this.recordWater('detrained','in','detrainment',detach);
      c.releasedKgThisStep=core;c.detrainedKgThisStep=detach;c.releaseRate=core/dt;c.detrainmentRate=detach/dt;c.lastRain=0;
      const maturity=clip(c.age/1200)*clip(c.supplyRatio??0),count=maturity>.7?4:maturity>.25?3:2,raw=Array.from({length:count},(_,j)=>1+.3*Math.cos((c.phase||0)+j*2.1+c.age/900)+.15*clip((c.shear||0)/15)*(j/(count-1)-.5)),norm=raw.reduce((a,b)=>a+b,0);
      const carrier=g.index(c.x,c.y),sourceX=c.x-(carrier<0?0:f.um[carrier]*DT),sourceY=c.y-(carrier<0?0:f.vm[carrier]*DT);
      // Partition the parent updraft area with the water weights. Giving each
      // child the full parent radius artificially dilutes the strong echoes.
      c.subcores=[];let assigned=0;
      for(let j=0;j<count;j++){
        const weight=j===count-1?1-assigned:raw[j]/norm;assigned+=weight;
        const broad=this.config.organizedWarmSector,aspect=broad?1.55:1;
        const phase=(c.phase||0)+j*2.1,along=(j-(count-1)/2)*c.major*.6,across=c.minor*(broad?Math.sin(phase+c.age/900)*.25+(j%2?1:-1)*.18:Math.sin(phase+c.age/900)*(c.triggerSourceId&&this.config.connectedTrainingFeed ? .10 : .35)),x=sourceX+Math.cos(c.angle)*along-Math.sin(c.angle)*across,y=sourceY+Math.sin(c.angle)*along+Math.cos(c.angle)*across,width=Math.max(800,Math.min(c.minor,Math.sqrt((c.updraftArea||Math.PI*1000**2)/(Math.PI*aspect)))*Math.sqrt(weight));
        c.subcores.push({x:x+c.x-sourceX,y:y+c.y-sourceY,width,minor:width*aspect,weight});yield*this.depositPrecip(coreSource,x,y,width*(1+.3*clip((c.shear||0)/15)),width*aspect,c.angle,core*weight,'core');
      }
      yield*this.depositPrecip(P.qa,sourceX-(c.vx||0)*300,sourceY-(c.vy||0)*300,Math.max(c.major*1.8,this.config.stratiformOutflow?28000:3000),Math.max(c.minor*1.5,this.config.stratiformOutflow?28000:2000),c.angle,detach,'detrained');yield;
    }
    yield 'qa_import';
    // Legacy Qa import: positive limited slopes preserve each environment-cell mean exactly.
    const minmod=(a,b)=>a*b>0?Math.sign(a)*Math.min(Math.abs(a),Math.abs(b)):0;
    for(let j=0;j<g.ny;j++){for(let i=0;i<g.nx;i++){
      const k=j*g.nx+i,value=f.ls[k];if(value<=0)continue;
      let sx=minmod(value-f.ls[j*g.nx+Math.max(0,i-1)],f.ls[j*g.nx+Math.min(g.nx-1,i+1)]-value),sy=minmod(value-f.ls[Math.max(0,j-1)*g.nx+i],f.ls[Math.min(g.ny-1,j+1)*g.nx+i]-value),limit=Math.min(1,2*value/Math.max(1e-30,Math.abs(sx)+Math.abs(sy)));sx*=limit;sy*=limit;
      const x0=i*g.dx,y0=j*g.dx,x1=x0+g.dx,y1=y0+g.dx;
      for(let y=Math.floor(y0/pg.dx);y<Math.ceil(y1/pg.dx);y++)for(let x=Math.floor(x0/pg.dx);x<Math.ceil(x1/pg.dx);x++){
        const left=Math.max(x0,x*pg.dx),right=Math.min(x1,(x+1)*pg.dx),bottom=Math.max(y0,y*pg.dx),top=Math.min(y1,(y+1)*pg.dx),mean=value+sx*((left+right)/2-(x0+x1)/2)/g.dx+sy*((bottom+top)/2-(y0+y1)/2)/g.dx;
        P.qa[y*pg.nx+x]+=mean*(right-left)*(top-bottom)/pg.area;
      }
    }if(j%2===1)yield;}
    f.ls.fill(0);
    yield 'low_carrier';
    const lowU=this.buffer('precipLowCenterU',g.n),lowV=this.buffer('precipLowCenterV',g.n),airU=this._buffers.get('airUL'),airV=this._buffers.get('airVL');
    for(let j=0;j<g.ny;j++){for(let i=0;i<g.nx;i++){const k=j*g.nx+i;lowU[k]=airU?.length===this.eu.length?.5*(airU[j*(g.nx+1)+i]+airU[j*(g.nx+1)+i+1]):f.u[k];lowV[k]=airV?.length===this.ev.length?.5*(airV[j*g.nx+i]+airV[(j+1)*g.nx+i]):f.v[k];}if(j%2===1)yield;}
    if(this.config.coldDynamics==='inertial'){
      if(!this._precipCarrierIndex){const indices=new Int32Array(g.n);for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++){const k=j*g.nx+i;indices[k]=this.cold.index((i+.5)*g.dx,(j+.5)*g.dx);if(k%1024===1023)yield;}this._precipCarrierIndex=indices;}
      for(let j=0;j<g.ny;j++){for(let i=0;i<g.nx;i++){const k=j*g.nx+i,c=this._precipCarrierIndex[k],A=this.q[c]/THETA;lowU[k]+=A>=ColdLayer.DRY?this.Px[c]/A:0;lowV[k]+=A>=ColdLayer.DRY?this.Py[c]/A:0;}if(j%2===1)yield;}
    }
    yield 'face_winds';
    // Grid.sample's one-dimensional clamping/indices/weights depend only on fixed grids.
    if(!this._precipWindGeometry){
      const axis=(count,offset,limit)=>{const lower=new Int32Array(count),upper=new Int32Array(count),weight=new Float64Array(count);for(let i=0;i<count;i++){const x=Math.max(0,Math.min(limit-1,(i+offset)*pg.dx/g.dx-.5)),lo=Math.floor(x);lower[i]=lo;upper[i]=Math.min(lo+1,limit-1);weight[i]=x-lo;}return {lower,upper,weight};};
      this._precipWindGeometry={xFace:axis(pg.nx+1,0,g.nx),xCenter:axis(pg.nx,.5,g.nx),yFace:axis(pg.ny+1,0,g.ny),yCenter:axis(pg.ny,.5,g.ny)};
    }
    const wg=this._precipWindGeometry,winds={};let maxRate=0;
    for(const level of ['low','mid']){
      const u=this.buffer('precipU'+level,(pg.nx+1)*pg.ny),v=this.buffer('precipV'+level,pg.nx*(pg.ny+1)),sourceU=level==='low'?lowU:f.um,sourceV=level==='low'?lowV:f.vm;let umax=0,vmax=0;
      for(let j=0;j<pg.ny;j++){const y=wg.yCenter,j0=y.lower[j]*g.nx,j1=y.upper[j]*g.nx,b=y.weight[j],x=wg.xFace;for(let i=0;i<=pg.nx;i++){const i0=x.lower[i],i1=x.upper[i],a=x.weight[i],value=(sourceU[j0+i0]*(1-a)+sourceU[j0+i1]*a)*(1-b)+(sourceU[j1+i0]*(1-a)+sourceU[j1+i1]*a)*b;u[j*(pg.nx+1)+i]=value;umax=Math.max(umax,Math.abs(value));}if(j%2===1)yield;}
      for(let j=0;j<=pg.ny;j++){const y=wg.yFace,j0=y.lower[j]*g.nx,j1=y.upper[j]*g.nx,b=y.weight[j],x=wg.xCenter;for(let i=0;i<pg.nx;i++){const i0=x.lower[i],i1=x.upper[i],a=x.weight[i],value=(sourceV[j0+i0]*(1-a)+sourceV[j0+i1]*a)*(1-b)+(sourceV[j1+i0]*(1-a)+sourceV[j1+i1]*a)*b;v[j*pg.nx+i]=value;vmax=Math.max(vmax,Math.abs(value));}if(j%2===1)yield;}
      maxRate=Math.max(maxRate,(umax+vmax)/pg.dx);winds[level]={u,v};yield;
    }
    yield 'transport';
    const ns=Math.max(1,Math.ceil(DT*maxRate/.4)),dt=DT/ns;
    const jsRhs=function*(a,out,wind){out.fill(0);let loss=0;const face=(left,right,vel)=>{const donor=vel>=0?left:right,flux=donor<0?0:vel*a[donor];if(left>=0)out[left]-=flux/pg.dx;if(right>=0)out[right]+=flux/pg.dx;if(left<0)loss-=flux*pg.dx;if(right<0)loss+=flux*pg.dx;};
      for(let j=0;j<pg.ny;j++){for(let i=0;i<=pg.nx;i++)face(i?j*pg.nx+i-1:-1,i<pg.nx?j*pg.nx+i:-1,wind.u[j*(pg.nx+1)+i]);if(j%2===1)yield;}
      for(let j=0;j<=pg.ny;j++){for(let i=0;i<pg.nx;i++)face(j?(j-1)*pg.nx+i:-1,j<pg.ny?j*pg.nx+i:-1,wind.v[j*pg.nx+i]);if(j%2===1)yield;}return loss;};
    const rhs=this._numericBackend?(a,out,wind)=>this._numericBackend.precipRhs(a,out,wind,pg):jsRhs;
    for(const [key,a]of [...Object.entries(P),['source_core',coreSource]]){
      if(!a.some(x=>x>0))continue;const wind=winds[key.startsWith('lower_')?'low':'mid'],r0=this.buffer('precipR0',pg.n),r1=this.buffer('precipR1',pg.n),stage=this.buffer('precipStage',pg.n),origin=key==='qa'?'detrained':key.split('_')[1];
      for(let n=0;n<ns;n++){const loss0=yield*rhs(a,r0,wind);if(this._numericBackend)yield*this._numericBackend.precipVector(a,r0,stage,dt);else for(let k=0;k<pg.n;k++){stage[k]=a[k]+dt*r0[k];if(k%2048===2047)yield;}const loss1=yield*rhs(stage,r1,wind);if(this._numericBackend)yield*this._numericBackend.precipVector(a,r1,a,dt,stage);else for(let k=0;k<pg.n;k++){a[k]=.5*(a[k]+stage[k]+dt*r1[k]);if(k%2048===2047)yield;}const loss=dt*.5*(loss0+loss1);this.stats.outflow+=loss;S[origin+'BoundaryOut']=(S[origin+'BoundaryOut']||0)+loss;this.recordWater(origin,'out','boundary',loss);}yield;
    }
    yield*this._spreadStratiform();
    yield 'evap_candidates';
    // Disposable geometry only: original row-major env ownership and four rain overlaps.
    if(!this._precipReleaseGeometry){
      const envIndex=new Int32Array(pg.n),rainIndex=new Int32Array(pg.n*4),rainArea=new Float64Array(pg.n*4);
      for(let k=0;k<pg.n;k++){
        const i=k%pg.nx,j=Math.floor(k/pg.nx);envIndex[k]=g.index((i+.5)*pg.dx,(j+.5)*pg.dx);
        const x0=i*pg.dx,y0=j*pg.dx,x1=x0+pg.dx,y1=y0+pg.dx;let q=k*4;
        for(let ry=Math.floor(y0/1000);ry<Math.ceil(y1/1000);ry++)for(let rx=Math.floor(x0/1000);rx<Math.ceil(x1/1000);rx++){
          rainIndex[q]=ry*this.rain.nx+rx;rainArea[q]=Math.max(0,Math.min(x1,(rx+1)*1000)-Math.max(x0,rx*1000))*Math.max(0,Math.min(y1,(ry+1)*1000)-Math.max(y0,ry*1000));q++;
        }
        if(q!==k*4+4)throw Error('固定2km降水到1km雨账几何不匹配');if(k%2048===2047)yield;
      }
      this._precipReleaseGeometry={envIndex,rainIndex,rainArea};
    }
    const {envIndex,rainIndex,rainArea}=this._precipReleaseGeometry;
    const demands={low:this.buffer('evapLowDemand',g.n),mid:this.buffer('evapMidDemand',g.n)},accepted={low:this.buffer('evapLowFraction',g.n),mid:this.buffer('evapMidFraction',g.n)};demands.low.fill(0);demands.mid.fill(0);accepted.low.fill(0);accepted.mid.fill(0);
    // Every slot is overwritten/cleared each physical step; kg requests are not persistent state.
    const requests=this.buffer('precipEvapRequests',pg.n*7);requests.fill(0);
    const qaFactor=this.buffer('precipQaEvapFactor',g.n),keMid=this.buffer('precipKeMid',g.n),rateMid=this.buffer('precipRateMid',g.n),factorMid=this.buffer('precipFactorMid',g.n),keLow=this.buffer('precipKeLow',g.n),rateLow=this.buffer('precipRateLow',g.n),factorLow=this.buffer('precipFactorLow',g.n),cascade=this.buffer('precipCascade',g.n),sourceUpper=this.buffer('precipSourceUpper',g.n),sourceLower=this.buffer('precipSourceLower',g.n),detRate=this.buffer('stratiformRate',g.n),detFactor=this.buffer('stratiformFactor',g.n),detCascade=this.buffer('stratiformCascade',g.n),detFall=this.buffer('stratiformFall',g.n),kf=1/300;
    for(let e=0;e<g.n;e++){
      qaFactor[e]=1-Math.exp(-DT*clip(1-f.rhM[e])/1800);keMid[e]=clip(1-f.rhM[e])/600;rateMid[e]=kf+keMid[e];factorMid[e]=1-Math.exp(-DT*(kf+keMid[e]));keLow[e]=clip(1-f.rhL[e])/300;rateLow[e]=kf+keLow[e];factorLow[e]=1-Math.exp(-DT*rateLow[e]);const a=rateMid[e],b=rateLow[e];cascade[e]=Math.abs(b-a)<1e-10?kf*DT*Math.exp(-a*DT):kf*(Math.exp(-a*DT)-Math.exp(-b*DT))/(b-a);sourceUpper[e]=factorMid[e]/(a*DT);sourceLower[e]=Math.max(0,kf/(a*DT)*(factorLow[e]/b-cascade[e]/kf));detFall[e]=this.config.stratiformOutflow?1/1800:kf;detRate[e]=detFall[e]+keMid[e];detFactor[e]=1-Math.exp(-DT*detRate[e]);detCascade[e]=Math.abs(b-detRate[e])<1e-10?detFall[e]*DT*Math.exp(-detRate[e]*DT):detFall[e]*(Math.exp(-detRate[e]*DT)-Math.exp(-b*DT))/(b-detRate[e]);if(e%512===511)yield;
    }
    // Integrate the core source continuously through the two-layer cascade.
    // Only source quadrature is added here; the physical clock still advances once by 600 s.
    for(let k=0;k<pg.n;k++)P.upper_core[k]+=coreSource[k];
    // The former 0.1 kg/m2 cutoff trapped dilute anvil water forever outside
    // cores. Gradual hydrometeor growth now operates throughout fed stratiform
    // condensate; dry-column evaporation still limits the resulting rain shield.
    const qaFraction=this.config.stratiformOutflow?0:1-Math.exp(-DT/1200);
    if(this.config.stratiformOutflow){const fraction=1-Math.exp(-DT/1800);for(let k=0;k<pg.n;k++){const converted=P.qa[k]*fraction;P.qa[k]-=converted;P.upper_detrained[k]+=converted;}}
    // Fixed descriptors are resolved once, never constructed per positive request.
    const rows=[{array:P.qa,fraction:accepted.mid,origin:'detrained',level:'mid',evaporated:'detrainedEvaporated',layerEvaporated:'detrainedEvaporatedMid',coldHeat:'detrainedColdHeatSource',ledger:this.ledger.detrained,flow:'evaporationmid:out',process:'evaporationmid'}],originRows=[];
    for(const origin of origins){const ledger=this.ledger[origin],upper=P['upper_'+origin],lower=P['lower_'+origin];originRows.push({origin,upper,lower,ground:origin+'Ground',ledger,convective:origin==='core'});for(const level of ['mid','low'])rows.push({array:level==='mid'?upper:lower,fraction:accepted[level],origin,level,evaporated:origin+'Evaporated',layerEvaporated:origin+'Evaporated'+(level==='low'?'Low':'Mid'),coldHeat:origin+'ColdHeatSource',ledger,flow:'evaporation'+level+':out',process:'evaporation'+level});}
    if(this._numericBackend)yield*this._numericBackend.collect(this,demands,requests,[qaFactor,keMid,rateMid,factorMid,keLow,rateLow,factorLow,cascade,sourceUpper,sourceLower,detRate,detFactor,detCascade,detFall],qaFraction);else for(let j=0;j<pg.ny;j++){for(let i=0;i<pg.nx;i++){
      const k=j*pg.nx+i;if(P.qa[k]+P.upper_core[k]+P.lower_core[k]+P.upper_detrained[k]+P.lower_detrained[k]+P.upper_boundary[k]+P.lower_boundary[k]===0)continue;
      const e=envIndex[k],slot=k*7,converted=Math.max(P.qa[k]-.1,0)*qaFraction;P.qa[k]-=converted;P.upper_detrained[k]+=converted;
      const qaMass=P.qa[k]*qaFactor[e]*pg.area;if(qaMass>0){demands.mid[e]+=qaMass;requests[slot]=qaMass;}
      for(let o=0;o<3;o++){const row=originRows[o],upper=row.upper,lower=row.lower;if(upper[k]+lower[k]===0)continue;
        const source=o===0?coreSource[k]:0,oldUpper=Math.max(0,upper[k]-source),oldLower=lower[k],keM=keMid[e],upperRate=o===1?detRate[e]:rateMid[e],upperFall=o===1?detFall[e]:kf,upperFactor=o===1?detFactor[e]:factorMid[e],outUpper=oldUpper*upperFactor+source*(1-sourceUpper[e]),fall=outUpper*upperFall/upperRate,evapUpper=outUpper*keM/upperRate;upper[k]-=fall;lower[k]+=fall;const upperMass=evapUpper*pg.area;if(upperMass>0){demands.mid[e]+=upperMass;requests[slot+1+2*o]=upperMass;}
        const ke=keLow[e],rate=rateLow[e],out=Math.max(0,oldLower+fall-(oldLower*(1-factorLow[e])+oldUpper*(o===1?detCascade[e]:cascade[e])+source*sourceLower[e])),ground=out*kf/rate,evap=out*ke/rate;lower[k]-=ground;
        if(ground>0){const mass=ground*pg.area;S[row.ground]=(S[row.ground]||0)+mass;recordWaterFixed(row.ledger,'ground:out',mass,row.origin,'ground');for(let q=k*4;q<k*4+4;q++)this.addRain(rainIndex[q],ground*rainArea[q],row.convective);}
        const lowerMass=evap*pg.area;if(lowerMass>0){demands.low[e]+=lowerMass;requests[slot+2+2*o]=lowerMass;}
      }
    }if(j%2===1)yield;}
    yield 'evap_adjustment';
    for(const level of ['low','mid']){
      const w=level==='low'?'wl':'wm',t=level==='low'?'tl':'tm',sl=level==='low'?'sl':'sm',rh=level==='low'?'rhL':'rhM',m=level==='low'?1400:2600,p=level==='low'?95000:75000;
      for(let k=0;k<g.n;k++){if(k%512===511)yield;if(demands[level][k]<=0)continue;const phase=phaseAdjustment(f[w][k],f[t][k],m,p,demands[level][k]/g.area),evap=phase.evaporated;this.stats.rootCalls++;accepted[level][k]=evap*g.area/demands[level][k];f[w][k]+=evap;f[t][k]-=2.5e6*evap/(1004*m);f[sl][k]=saturation(f[t][k],m,p);f[rh][k]=f[w][k]/f[sl][k];this.stats.evaporated+=evap*g.area;S.latentCooling+=evap*g.area*2.5e6;this.recordWater(level==='low'?'vaporL':'vaporM','in','precipEvaporation',evap*g.area);
        // Midlevel evaporation cools TM only. No unresolved instantaneous downdraft-to-surface conversion.
        if(level==='low'&&!this.config.disableCold){const dQ=ALPHA*evap,dh=dQ/THETA;
          if(this.config.coldSourceGeometry==='environment_mean'){const ix=k%g.nx,iy=Math.floor(k/g.nx),ratio=g.dx/this.cold.dx;for(let b=0;b<ratio;b++)for(let a=0;a<ratio;a++){const ci=(iy*ratio+b)*this.cold.nx+ix*ratio+a;this._addColdSource(ci,dh,dQ,k);}}
          this.stats.coldHeatSource+=dQ*g.area;this.stats.coldVolumeSource+=dh*g.area;
        }
      }yield;
    }
    if(!this.config.disableCold&&this.config.coldSourceGeometry==='rain_footprint')yield*this._depositColdEvaporation(requests,accepted.low,envIndex);
    yield 'evap_accounting';
    if(this._numericBackend)yield*this._numericBackend.account(this,requests,accepted);else {let accounted=0;for(let k=0;k<pg.n;k++){
      const e=envIndex[k],slot=k*7;for(let q=0;q<7;q++){
        const mass=requests[slot+q];if(mass<=0)continue;const row=rows[q],used=mass*row.fraction[e];row.array[k]-=used/pg.area;S[row.evaporated]=(S[row.evaporated]||0)+used;S[row.layerEvaporated]=(S[row.layerEvaporated]||0)+used;recordWaterFixed(row.ledger,row.flow,used,row.origin,row.process);if(row.level==='low'&&!this.config.disableCold)S[row.coldHeat]=(S[row.coldHeat]||0)+ALPHA*used;if(++accounted%2048===0)yield;
      }
      if(k%4096===4095)yield;
    }
    }
    yield 'rain_ledger';
    this._limitCoreRain();
    let rainCount=0;for(const i of this.activeRain){this.rainTotal[i]+=this.rainStep[i];this.stats.maxRain=Math.max(this.stats.maxRain,this.rainStep[i]*3600/DT);if(++rainCount%2048===0)yield;}
  };
  // Bound combined surface core rain without deleting water or clipping only
  // the display. Excess core fallout stays in the lower precipitation reservoir
  // and may advect, evaporate or fall in a later ten-minute step (JS and WASM).
  Model.prototype._limitCoreRain=function(){
    if(!this.config.organizedWarmSector)return;
    const cap=100*DT/3600,rg=this.rain,pg=this.precip;let returned=0;
    for(const i of this.activeRain){
      const core=this.convectiveStep[i],other=Math.max(0,this.rainStep[i]-core),excess=Math.max(0,core-Math.max(0,cap-other));
      if(!excess)continue;
      const x=(i%rg.nx+.5)*rg.dx,y=(Math.floor(i/rg.nx)+.5)*rg.dx,k=pg.index(x,y),mass=excess*rg.area;
      if(k<0)continue;this.precipWater.lower_core[k]+=mass/pg.area;this.rainStep[i]-=excess;this.convectiveStep[i]-=excess;returned+=mass;
    }
    if(!returned)return;
    this.stats.ground-=returned;this.stats.sources.coreGround-=returned;this.ledger.core.out-=returned;this.ledger.core.flows['ground:out']=(this.ledger.core.flows['ground:out']||0)-returned;
    this.stats.coreFalloutDeferred=(this.stats.coreFalloutDeferred||0)+returned;
  };
  // One canonical reservoir order for initialization, total inventory and water().
  Model.prototype.water=function(){return sum(Object.values(this.waterInventories()));};
  const oldCheckpoint=Model.prototype.checkpoint;
  Model.prototype.checkpoint=function(){const result=oldCheckpoint.call(this);for(const [k,a]of Object.entries(this.precipWater))result.arrays['precip_'+k]=a.slice();return result;};
  const oldCheck=Model.prototype.check;
  Model.prototype.check=function(){for(const [key,a]of Object.entries(this.precipWater))for(const x of a)if(!Number.isFinite(x)||x<-1e-8)throw Error('降水库非负性 '+key);return oldCheck.call(this);};

  Model.prototype.waterInventories=function(){
    const f=this.fields,P=this.precipWater,A=this.precip.area,E=this.env.area;
    return {vaporL:sum(f.wl)*E,vaporM:sum(f.wm)*E,cloudL:sum(f.qcL)*E,cloudM:sum(f.qcM)*E,core:this.cells.reduce((n,c)=>n+c.M,0)+(sum(P.upper_core)+sum(P.lower_core))*A,detrained:(sum(P.qa)+sum(P.upper_detrained)+sum(P.lower_detrained))*A+sum(f.ls)*E,boundary:(sum(P.upper_boundary)+sum(P.lower_boundary))*A};
  };
  Model.prototype.atmosphericHeat=function(){return this.env.area*(1004*(1400*sum(this.fields.tl)+2600*sum(this.fields.tm))+2.5e6*(sum(this.fields.wl)+sum(this.fields.wm)));};
  Model.prototype.captureInitialState=function(){
    if(this.t!==0||this.stats.steps!==0)throw Error('初始账只能在 t=0、第一物理步前建立');
    this.ledger=Object.fromEntries(Object.entries(this.waterInventories()).map(([key,initial])=>[key,{initial,in:0,out:0,flows:{}}]));
    for(const c of this.cells)this._ensureConvectiveEnergy(c);
    const environment=this.atmosphericHeat(),convective=this.convectiveEnergy();
    this.convectiveEnergyBudget={initial:convective,sourceJ:0,sourceLowJ:0,sourceMidJ:0,ventilationTopJ:0,deathVentilationTopJ:0,columnBoundaryJ:0,arithmeticResidualJ:0,updates:0,deathByReason:{}};this.convectiveEnergyDiagnostics=null;
    this.heatBudget={initial:environment+convective,initialEnvironment:environment,initialConvective:convective,in:0,out:0,flows:{},definition:this.config.convectiveHeating==='local_latent'?'cp*m*T + Lv*Wv; liquid sensible heat and potential energy excluded':'Henv(cp*m*T + Lv*Wv) + sum(cell.convectivePhaseEnergyJ); unresolved upper-layer export is an explicit boundary; liquid sensible heat and full potential/kinetic energy excluded'};
    this.initialWater=this.water();this.initialColdVolume=sum(this.h)*this.cold.area;this.initialColdHeat=sum(this.q)*this.cold.area;this.coldMomentumLedger=ColdLayer.initialLedger(this._coldState(),this.cold);this._coldKinematicsReady=false;
  };
  // Same validation and per-mass addition order as recordWater, with resolved out-flow keys.
  function recordWaterFixed(b,flow,mass,origin,process){
    if(!Number.isFinite(mass)||mass<-1e-8)throw Error('来源通量非法 '+origin+':'+process);if(mass<=0)return;
    b.out+=mass;b.flows[flow]=(b.flows[flow]||0)+mass;
  }
  Model.prototype.recordWater=function(key,direction,process,mass){
    if(!Number.isFinite(mass)||mass<-1e-8)throw Error('来源通量非法 '+key+':'+process);if(mass<=0)return;
    const b=this.ledger[key];b[direction]+=mass;const name=process+':'+direction;b.flows[name]=(b.flows[name]||0)+mass;
  };
  Model.prototype.recordHeat=function(direction,process,joules){if(!Number.isFinite(joules)||joules<0)throw Error('热量通量非法 '+process);if(joules===0)return;const b=this.heatBudget;b[direction]+=joules;const name=process+':'+direction;b.flows[name]=(b.flows[name]||0)+joules;};

  // A declared reduced upper-column energy account, separate from water and CAPE proxies.
  function convectiveEnergyStep(old,source,dt,tau){
    if(![old,source,dt,tau].every(Number.isFinite)||old<0||source<0||dt<=0||tau<=0)throw Error('对流能量解析更新参数非法');
    const x=dt/tau,oneMinusR=-Math.expm1(-x),r=Math.exp(-x);
    // Stable constant-source ventilation fraction, including dt/tau << 1.
    const ventFraction=x<1e-3?x*(.5+x*(-1/6+x*(1/24+x*(-1/120+x/720)))):1-oneMinusR/x;
    const retention=x<1e-3?1-ventFraction:oneMinusR/x;
    const energy=old*r+source*retention,vent=old*oneMinusR+source*ventFraction;
    return {energy,vent,arithmeticResidual:old+source-energy-vent};
  }
  Model.prototype._ensureConvectiveEnergy=function(c){
    c.convectivePhaseEnergyJ??=0;
    if(!Number.isFinite(c.convectivePhaseEnergyJ)||c.convectivePhaseEnergyJ<0||this.config.convectiveHeating==='local_latent'&&c.convectivePhaseEnergyJ!==0)throw Error('对流柱能量或模式非法');
    c.convectiveEnergyStep??={at:null,sourceJ:0,latentConvertedJ:0,suppliedLowKg:0,suppliedMidKg:0,ventilationTopJ:0,deathVentilationTopJ:0,columnBoundaryJ:0,tauSeconds:null,tauSource:null,arithmeticResidualJ:0};
  };
  Model.prototype.convectiveEnergy=function(){let total=0;for(const c of this.cells){const e=c.convectivePhaseEnergyJ??0;if(!Number.isFinite(e)||e<0)throw Error('对流柱能量库存非法');total+=e;}return total;};
  Model.prototype.convectiveEnergyAudit=function(){
    const b=this.convectiveEnergyBudget,inventory=this.convectiveEnergy(),outJ=b.ventilationTopJ+b.deathVentilationTopJ+b.columnBoundaryJ,residual=b.initial+b.sourceJ-outJ-inventory,activity=b.sourceJ+outJ;
    return {...b,deathByReason:{...b.deathByReason},mode:this.config.convectiveHeating,inventory,outJ,residual,activity,relativeResidual:Math.abs(residual)/Math.max(1,activity),layerSourceSumResidual:b.sourceJ-b.sourceLowJ-b.sourceMidJ,definition:'J; nonnegative unresolved-column converted energy; Rconv=initial+actual condensation source-all column outputs-current inventory. Internal source is not external heat input.'};
  };
  Model.prototype._beginConvectiveEnergyStep=function(){
    this.convectiveEnergyDiagnostics={at:this.t+DT,stepSeconds:DT,mode:this.config.convectiveHeating,sourceJ:0,sourceLowJ:0,sourceMidJ:0,ventilationTopJ:0,deathVentilationTopJ:0,columnBoundaryJ:0,arithmeticResidualJ:0,updates:0,deathByReason:{}};
    for(const c of this.cells){this._ensureConvectiveEnergy(c);const d=c.convectiveEnergyStep;d.at=this.t+DT;d.sourceJ=0;d.latentConvertedJ=0;d.suppliedLowKg=0;d.suppliedMidKg=0;d.ventilationTopJ=0;d.deathVentilationTopJ=0;d.columnBoundaryJ=0;d.arithmeticResidualJ=0;d.tauSeconds=null;d.tauSource=null;}
  };
  Model.prototype._advanceConvectiveEnergy=function(c,dt=DT){
    this._ensureConvectiveEnergy(c);const d=c.convectiveEnergyStep,low=c.suppliedLKgThisStep||0,mid=c.suppliedMKgThisStep||0,actual=c.suppliedKgThisStep||0;
    if(![low,mid,actual].every(Number.isFinite)||Math.min(low,mid,actual)<0)throw Error('实际凝结供给非法');
    const latent=2.5e6*actual;d.at=this.t+DT;d.latentConvertedJ=latent;d.suppliedLowKg=low;d.suppliedMidKg=mid;
    if(this.config.convectiveHeating==='local_latent')return;
    let tau;if(this.config.cellLifecycle==='pulse'){
      if(!c.pulse||!Number.isFinite(c.pulse.Hc)||!Number.isFinite(c.pulse.wturn)||c.pulse.Hc<=0||c.pulse.wturn<0)throw Error('对流柱周转参数非法');
      tau=c.pulse.Hc/Math.max(c.pulse.wturn,1);d.tauSource='pulse_Hc_wturn';
    }else{tau=5000/Math.max(1,Math.min(8,c.updraftVelocity||0));d.tauSource='legacy_Hc5000_bounded_updraft';}
    const r=convectiveEnergyStep(c.convectivePhaseEnergyJ,latent,dt,tau);c.convectivePhaseEnergyJ=r.energy;d.sourceJ=latent;d.ventilationTopJ=r.vent;d.tauSeconds=tau;d.arithmeticResidualJ=r.arithmeticResidual;
    for(const b of [this.convectiveEnergyBudget,this.convectiveEnergyDiagnostics])if(b){b.sourceJ+=latent;b.sourceLowJ+=2.5e6*low;b.sourceMidJ+=2.5e6*mid;b.ventilationTopJ+=r.vent;b.arithmeticResidualJ+=r.arithmeticResidual;b.updates++;}
    this.recordHeat('out','convectiveVentilationTop',r.vent);
  };
  Model.prototype._retireConvectiveEnergy=function(c,reason){
    this._ensureConvectiveEnergy(c);const joules=c.convectivePhaseEnergyJ,boundary=reason==='domain_exit',key=boundary?'columnBoundaryJ':'deathVentilationTopJ',process=boundary?'convectiveColumnBoundary':'convectiveDeathVentilationTop';
    this.recordHeat('out',process,joules);c.convectivePhaseEnergyJ=0;c.convectiveEnergyStep[key]+=joules;
    for(const b of [this.convectiveEnergyBudget,this.convectiveEnergyDiagnostics])if(b){b[key]+=joules;b.deathByReason[reason]=(b.deathByReason[reason]||0)+joules;}
    return {joules,units:'J',process,destination:boundary?'domain_boundary':'unresolved_upper_boundary',mode:this.config.convectiveHeating};
  };
  Model.prototype.depositPrecip=function*(array,x,y,major,minor,angle,mass,origin){
    if(mass<=0)return;const kernel=yield*this.kernel(this.precip,x,y,major,minor,angle);
    for(const [k,w]of kernel){const amount=mass*w;if(k<0){this.stats.outflow+=amount;const key=origin+'BoundaryOut';this.stats.sources[key]=(this.stats.sources[key]||0)+amount;this.recordWater(origin,'out','boundary',amount);}else array[k]+=amount/this.precip.area;}
  };
  Model.prototype.detrainCell=function*(c){
    const mass=c.M;if(mass<=0)return;this.stats.sources.detrained+=mass;this.recordWater('core','out','detrainment',mass);this.recordWater('detrained','in','detrainment',mass);
    yield*this.depositPrecip(this.precipWater.qa,c.x,c.y,Math.max(c.major,this.config.stratiformOutflow?28000:2000),Math.max(c.minor,this.config.stratiformOutflow?28000:1500),c.angle,mass,'detrained');c.M=0;c.a=0;c.lifecycle='dead';
  };
  Model.prototype.sourceAudit=function(){
    const inventory=this.waterInventories(),result={};let initial=0,incoming=0,outgoing=0,final=0;
    for(const key of Object.keys(inventory)){
      const b=this.ledger[key],actual=inventory[key],residual=b.initial+b.in-b.out-actual,activity=b.in+b.out;
      result[key]={...structuredClone(b),inventory:actual,residual,activity,relativeResidual:Math.abs(residual)/Math.max(1,activity)};
      initial+=b.initial;incoming+=b.in;outgoing+=b.out;final+=actual;
    }
    const S=this.stats.sources,ground=(S.coreGround||0)+(S.detrainedGround||0)+(S.boundaryGround||0),H=this.heatBudget,environmentHeat=this.atmosphericHeat(),convective=this.convectiveEnergyAudit(),heat=environmentHeat+convective.inventory,residual=H.initial+H.in-H.out-heat;
    result.coldMomentum={mode:this.config.coldDynamics,...ColdLayer.audit(this._coldState(),this.cold,this.coldMomentumLedger)};
    result.total={canonicalReduction:'waterInventories property order; per-reservoir spatial sum then reservoir sum',activity:incoming+outgoing,budgetMode:incoming+outgoing===0?'zero_activity':'actual_activity',initial,in:incoming,out:outgoing,inventory:final,residual:initial+incoming-outgoing-final,inventorySumResidual:final-this.water(),groundSumResidual:ground-this.stats.ground};
    result.convectiveEnergy=convective;
    result.heat={...structuredClone(H),mode:this.config.convectiveHeating,environmentInventory:environmentHeat,convectiveInventory:convective.inventory,combinedInventory:heat,absoluteRoundoffEnvelopeJ:8*Number.EPSILON*Math.max(1,Math.abs(H.initial),Math.abs(heat)),environmentResidual:H.initialEnvironment+H.in-(H.out-convective.outJ)-convective.sourceJ-environmentHeat,inventory:heat,residual,relativeResidual:Math.abs(residual)/Math.max(1,H.in+H.out+S.latentHeating+S.latentCooling),phaseHeating:S.latentHeating,phaseCooling:S.latentCooling};
    result.environmentCloud={inventory:inventory.cloudL+inventory.cloudM,condensed:S.environmentCondensed,evaporated:S.environmentEvaporated,residual:result.cloudL.residual+result.cloudM.residual};result.fluxes={...S};return result;
  };

  // Slowly varying forcing is sampled every two minutes, then linearly interpolated.
  // Cache is disposable: recomputing the bracket after checkpoint restore is deterministic.
  const forcingExact=Model.prototype.updateForcing;
  Model.prototype.updateForcing=function*(){
    const span=120,base=Math.floor(this.t/span)*span;let start=base,end=base+span;for(const e of this.mesoscaleSchedule?.events||[])if(e.A>0)for(const boundary of [e.t0,e.end]){if(boundary<=this.t&&boundary>start)start=boundary;if(boundary>this.t&&boundary<end)end=boundary;}const controlKey=JSON.stringify(this.controls),key=start+'|'+end+'|'+controlKey,keys=['eu','ev','cu','cv','fineU','fineV'],fields=['u','v','um','vm','upperDiv','divL','airLM','airTop'];
    const capture=()=>({arrays:Object.fromEntries(keys.map(k=>[k,this[k].slice()])),fields:Object.fromEntries(fields.map(k=>[k,this.fields[k].slice()])),mechanismWind:Object.fromEntries(Object.entries(this.mechanismFields).filter(([key])=>key.startsWith('wind_')).map(([key,value])=>[key,value.slice()]))});
    if(!this._forcingBracket||this._forcingBracket.key!==key){
      let a=this._forcingBracket?.end===start&&this._forcingBracket.controlKey===controlKey?this._forcingBracket.b:null;
      if(!a&&start===0&&this._initialForcingCache?.controlKey===controlKey){a=this._initialForcingCache;this._initialForcingCache=null;}
      if(!a){yield*forcingExact.call(this,start);a=capture();}
      yield*forcingExact.call(this,end);const b=capture();this._forcingBracket={start,end,key,controlKey,a,b};
    }
    const {a,b}=this._forcingBracket,weight=(this.t-start)/(end-start);this.forcingInterpolation={start,end,at:this.t,weight,fromEvents:this.mesoscaleAt(start),toEvents:this.mesoscaleAt(end)};
    for(const k of keys){const out=this[k];for(let i=0;i<out.length;i++)out[i]=a.arrays[k][i]+weight*(b.arrays[k][i]-a.arrays[k][i]);}
    for(const k of fields){const out=this.fields[k];for(let i=0;i<out.length;i++)out[i]=a.fields[k][i]+weight*(b.fields[k][i]-a.fields[k][i]);}
    for(const [key,from]of Object.entries(a.mechanismWind)){const out=this._mechanismBuffer(key,from.length),to=b.mechanismWind[key];for(let i=0;i<out.length;i++)out[i]=from[i]+weight*(to[i]-from[i]);}
  };

  Model.prototype._normalizeCoastalWind=function(){
    const rng=random(hash(this.config.seed,'finite-jet-speed')),defaults={backgroundNormal:0,backgroundAlong:9+3*rng(),jetExcessNormal:0,jetExcessAlong:2+3*rng(),sigmaJet:this.config.jetExitControl?225000:this.config.initiationModel==='focused_lift'?115000:35000,exitLength:16000,breezeDay:1.5,breezeNight:1},p={...defaults,...this.config.coastalWindParameters};for(const key of Object.keys(defaults))if(!Number.isFinite(p[key])||((key==='sigmaJet'||key==='exitLength')&&p[key]<=0))throw Error('有限急流参数非法 '+key);this.config.coastalWindParameters=p;
  };
  Model.prototype._configureCoastalWind=function(){
    this.effectiveModes={frontKinematics:this.config.coldDynamics==='legacy'?'not_applicable_legacy_dynamics':this.config.frontKinematics,coastalWindModel:this.coastalGeometry?this.config.coastalWindModel:'not_applicable_without_audited_coast'};this.config.effectiveModes={...this.effectiveModes};
  };
  // Fixed scalar layout: raw U/V, background U/V, jet U/V, breeze U/V, mesoscale U/V, G,E,l,p,S,rough.
  Model.prototype._finiteWindSample=function(x,y,bg,rough,d,nx,ny,delta,out){
    if(this.config.monsoon925)rough=1;
    const c=this.coastalGeometry,p=this.config.coastalWindParameters,frame=this._jetFrame(bg),e=frame.e,t=c.tangent,n=c.normal,coord=this._jetCoordinates(x,y,bg,d,nx,ny),l=coord.along,perp=coord.cross,exit=coord.exit,G=Math.exp(-perp*perp/(2*p.sigmaJet**2)),E=1-bg.exitEnvelope*.5*(1+Math.tanh((l-exit)/p.exitLength)),S=bg.V/this.preset.baseV,normalLength=Math.hypot(nx,ny),breeze=(this.config.monsoon925||c.options.disableSeaBreeze)?0:(p.breezeDay*bg.D-p.breezeNight*bg.N)*Math.exp(-d*d/(2*40000**2));
    if(this.config.boundedMonsoon){
      const speeds=this._monsoonSpeeds(bg),brake=this._hillBrake(x,y,bg),core=clip((G-.15)/.55)*E*(1-brake),base=speeds.background===0?0:Math.max(10,speeds.background-1.5*brake),extra=(speeds.jet-speeds.background)*core;
      out[2]=base*e.x;out[3]=base*e.y;out[4]=extra*e.x;out[5]=extra*e.y;out[6]=out[7]=0;
      let u=out[2]+out[4]+delta.u,v=out[3]+out[5]+delta.v;const speed=Math.hypot(u,v),target=speeds.background===0?speed:Math.max(10+3*core,Math.min(13+2*core,speed));
      if(speed>0){u*=target/speed;v*=target/speed;}
      out[8]=u-out[2]-out[4];out[9]=v-out[3]-out[5];out[0]=u;out[1]=v;out[10]=G;out[11]=E;out[12]=l;out[13]=perp;out[14]=S;out[15]=rough;return out;
    }
    const baseSpeed=Math.hypot(p.backgroundAlong,p.backgroundNormal),jetSpeed=Math.min(5,Math.hypot(p.jetExcessAlong,p.jetExcessNormal)),jetScale=Math.min(1,Math.max(0,S));out[2]=rough*S*baseSpeed*e.x;out[3]=rough*S*baseSpeed*e.y;out[4]=rough*jetScale*G*E*jetSpeed*e.x;out[5]=rough*jetScale*G*E*jetSpeed*e.y;out[6]=normalLength>1e-12?breeze*nx/normalLength:0;out[7]=normalLength>1e-12?breeze*ny/normalLength:0;out[8]=delta.u;out[9]=delta.v;out[0]=out[2]+out[4]+out[6]+out[8];out[1]=out[3]+out[5]+out[7]+out[9];out[10]=G;out[11]=E;out[12]=l;out[13]=perp;out[14]=S;out[15]=rough;return out;
  };
  Model.prototype._putWindParts=function(parts,k,bu,bv,ju,jv,su,sv,mu,mv,tu,tv,G=0,E=1){if(!parts)return;parts.background_u[k]=bu;parts.background_v[k]=bv;parts.jet_u[k]=ju;parts.jet_v[k]=jv;parts.breeze_u[k]=su;parts.breeze_v[k]=sv;parts.mesoscale_u[k]=mu;parts.mesoscale_v[k]=mv;parts.processing_u[k]=tu;parts.processing_v[k]=tv;parts.G[k]=G;parts.E[k]=E;};
  Model.prototype._finishWindEvidence=function*(parts,nx,ny,real,halo,weights,u,v){
    if(!parts)return;const fg=this.forcing;for(const [name,raw]of Object.entries(parts)){const dest=this._mechanismBuffer('wind_'+name,fg.n);if(!real){dest.set(raw);continue;}const pad=halo;if(name==='G'||name==='E'){for(let j=0;j<fg.ny;j++)for(let i=0;i<fg.nx;i++)dest[j*fg.nx+i]=raw[(j+pad)*nx+i+pad];continue;}
      const tmp=this.buffer('windEvidenceBlur',nx*ny);for(let j=0;j<ny;j++){for(let i=halo;i<nx-halo;i++){const k=j*nx+i;let value=weights[6]*raw[k];for(let d=1;d<=6;d++)value+=weights[d+6]*(raw[k-d]+raw[k+d]);tmp[k]=value;}if(j%16===15)yield;}for(let j=0;j<fg.ny;j++){for(let i=0;i<fg.nx;i++){const k=(j+pad)*nx+i+pad;let value=weights[6]*tmp[k];for(let d=1;d<=6;d++)value+=weights[d+6]*(tmp[k-d*nx]+tmp[k+d*nx]);dest[j*fg.nx+i]=value;}if(j%16===15)yield;}
    }this._mechanismBuffer('wind_total_u',fg.n).set(u);this._mechanismBuffer('wind_total_v',fg.n).set(v);
  };

  // The finite real-grid raw cell is shared by local admission and the full applied field.
  Model.prototype._realFiniteRaw=function(i,j,bg,events,out){
    const meta=this.terrain.meta,geo=this.terrain.extended,h=meta.extended.haloCells,k=(j+h)*meta.extended.nx+i+h,c=this.coastalGeometry;
    const land=geo.ls[k],distance=Math.max(geo.signedDistance[k],0),rough=1-.4*land*(1-Math.exp(-distance/25000)),friction=c.options.disableFriction?1:rough;
    const x=meta.extended.origin[0]+(i+h+.5)*2500+this.config.width/2,y=meta.extended.origin[1]+(j+h+.5)*2500+this.config.height/2,delta=this._mesoscaleVelocity(x,y,events);
    this._finiteWindSample(x,y,bg,friction,geo.signedDistance[k],geo.coastX[k],geo.coastY[k],delta,out);
    const uphill=Math.max(0,out[0]*geo.normalX[k]+out[1]*geo.normalY[k])*geo.beta[k]*(this.config.monsoon925?clip((geo.zs[k]-80)/400):1);out[16]=-uphill*geo.normalX[k];out[17]=-uphill*geo.normalY[k];const rawU=out[0],rawV=out[1];out[0]-=uphill*geo.normalX[k];out[1]-=uphill*geo.normalY[k];
    if(this.config.boundedMonsoon&&out[14]>0){
      // Bound the along-flow component as well as the speed. Vector averaging
      // across terrain turns then cannot depress the background below 10 m/s.
      const e=this._jetFrame(bg).e,along=Math.max(10,Math.min(15,out[0]*e.x+out[1]*e.y)),limit=Math.sqrt(Math.max(0,225-along*along)),cross=Math.max(-limit,Math.min(limit,-out[0]*e.y+out[1]*e.x));out[0]=along*e.x-cross*e.y;out[1]=along*e.y+cross*e.x;
    }
    out[16]=out[0]-rawU;out[17]=out[1]-rawV;return out;
  };
  Model.prototype._coastalWindSampler=function(){
    const fg=this.forcing,g=this.env,bg=this.background(0),events=[],raw=new Map(),horizontal=new Map(),fine=new Map(),environment=new Map(),out=new Float64Array(18),weights=[];let norm=0;
    for(let a=-6;a<=6;a++){const w=Math.exp(-.5*(a/2)**2);weights.push(w);norm+=w;}for(let a=0;a<weights.length;a++)weights[a]/=norm;
    const rawAt=(i,j)=>{const key=(j+6)*(fg.nx+12)+i+6;let v=raw.get(key);if(!v){this._realFiniteRaw(i,j,bg,events,out);v=[out[0],out[1]];raw.set(key,v);}return v;};
    const horizontalAt=(i,j)=>{const key=(j+6)*fg.nx+i;let v=horizontal.get(key);if(!v){const a=rawAt(i,j);let x=weights[6]*a[0],y=weights[6]*a[1];for(let d=1;d<=6;d++){const l=rawAt(i-d,j),r=rawAt(i+d,j);x+=weights[d+6]*(l[0]+r[0]);y+=weights[d+6]*(l[1]+r[1]);}v=[x,y];horizontal.set(key,v);}return v;};
    const fineAt=(i,j)=>{const key=j*fg.nx+i;let v=fine.get(key);if(!v){const a=horizontalAt(i,j);let x=weights[6]*a[0],y=weights[6]*a[1];for(let d=1;d<=6;d++){const l=horizontalAt(i,j-d),r=horizontalAt(i,j+d);x+=weights[d+6]*(l[0]+r[0]);y+=weights[d+6]*(l[1]+r[1]);}v=[x,y];fine.set(key,v);}return v;};
    const xFace=(i,j)=>{let a=0;const r=g.dx/fg.dx;for(let k=0;k<r;k++){const row=j*r+k,left=Math.max(0,i*r-1),right=Math.min(fg.nx-1,i*r);a+=(fineAt(left,row)[0]+fineAt(right,row)[0])*.5;}return a/r;};
    const yFace=(i,j)=>{let a=0;const r=g.dx/fg.dx;for(let k=0;k<r;k++){const col=i*r+k,below=Math.max(0,j*r-1),above=Math.min(fg.ny-1,j*r);a+=(fineAt(col,below)[1]+fineAt(col,above)[1])*.5;}return a/r;};
    const envAt=(i,j)=>{const key=j*g.nx+i;let v=environment.get(key);if(!v){v=[(xFace(i,j)+xFace(i+1,j))*.5,(yFace(i,j)+yFace(i,j+1))*.5];environment.set(key,v);}return v;};
    const sample=(get,grid,x,y)=>{const xx=Math.max(0,Math.min(grid.nx-1,x/grid.dx-.5)),yy=Math.max(0,Math.min(grid.ny-1,y/grid.dx-.5)),i=Math.floor(xx),j=Math.floor(yy),u=xx-i,v=yy-j,i1=Math.min(i+1,grid.nx-1),j1=Math.min(j+1,grid.ny-1),a=get(i,j),b=get(i1,j),c=get(i,j1),d=get(i1,j1);return {x:(a[0]*(1-u)+b[0]*u)*(1-v)+(c[0]*(1-u)+d[0]*u)*v,y:(a[1]*(1-u)+b[1]*u)*(1-v)+(c[1]*(1-u)+d[1]*u)*v};};
    return {environment:(x,y)=>sample(envAt,g,x,y),fine:(x,y)=>sample(fineAt,fg,x,y),work:()=>({rawCells:raw.size,fineCells:fine.size,environmentCells:environment.size})};
  };
  Model.prototype._auditCoastalFlow=function(sampler,mainland){
    const c=this.coastalGeometry,g=this.forcing,at=p=>{const k=g.index(p.x,p.y);return {inDomain:k>=0,water:k>=0&&this.geometry.land[k]<.5,island:k>=0&&this.geometry.land[k]>=.5&&!mainland[k],mainland:k>=0&&mainland[k]>0,signedDistance:k>=0?g.sample(this.terrain.fields.signedDistance,p.x,p.y):null};};
    const crossingEnvironment=sampler.environment(c.crossing.x,c.crossing.y),crossingFine=sampler.fine(c.crossing.x,c.crossing.y),speed=Math.hypot(crossingEnvironment.x,crossingEnvironment.y);
    const result={atSeconds:0,windStage:'frozen t0 after terrain, friction, breeze, Gaussian blur, FV faces and environment-center bilinear sampling',crossingEnvironment,crossingFine,accepted:false,reason:null,stepM:2500};
    if(crossingEnvironment.y<=0||crossingEnvironment.x<-.25*speed){result.reason='appliedDirection';return result;}
    const walk=(sign,length)=>{let p={...c.crossing},distance=0;const points=[];while(true){const state=at(p);if(!state.inDomain)return {valid:false,reason:'trajectoryDomain',points};const velocity=sampler.environment(p.x,p.y),s=Math.hypot(velocity.x,velocity.y);if(s<.1)return {valid:false,reason:'trajectoryStagnant',points};const point={...p,distance,velocity,...state};points.push(point);if(distance>=length)break;const ds=Math.min(2500,length-distance),mid={x:p.x+sign*.5*ds*velocity.x/s,y:p.y+sign*.5*ds*velocity.y/s};if(!at(mid).inDomain)return {valid:false,reason:'trajectoryDomain',points};const mv=sampler.environment(mid.x,mid.y),ms=Math.hypot(mv.x,mv.y);if(ms<.1)return {valid:false,reason:'trajectoryStagnant',points};point.midpoint={...mid,velocity:mv};p={x:p.x+sign*ds*mv.x/ms,y:p.y+sign*ds*mv.y/ms};distance+=ds;}return {valid:true,points};};
    result.upstream=walk(-1,c.offshoreRun);if(!result.upstream.valid){result.reason=result.upstream.reason;return result;}
    result.downstream=walk(1,40000);if(!result.downstream.valid){result.reason=result.downstream.reason;return result;}
    const start=result.upstream.points.at(-1);result.actualUpstreamStart={...start};if(!start.water||start.signedDistance>=-30000){result.reason='trajectoryOffshoreStart';return result;}
    if(result.upstream.points.some(p=>p.distance>10000&&p.mainland)){result.reason='trajectoryEarlyMainland';return result;}
    const samples=result.downstream.points.filter(p=>p.distance<40000);let hits=0,first=0,gap=0,maxGap=0;for(const p of samples){if(p.mainland){hits++;gap=0;if(p.distance<10000)first++;}else{gap+=2500;maxGap=Math.max(maxGap,gap);}}
    result.downstreamCoverage={hits,total:samples.length,first10kmHits:first,maxWaterGapM:maxGap};if(hits<13||first<3||maxGap>5000){result.reason='trajectoryContinuousLand';return result;}
    const entry=[...result.upstream.points].reverse().find(p=>p.mainland)||result.downstream.points.find(p=>p.mainland);result.firstActualMainlandEntry=entry?{x:entry.x,y:entry.y,anchorOffsetM:Math.hypot(entry.x-c.crossing.x,entry.y-c.crossing.y)}:null;
    if(!entry||result.firstActualMainlandEntry.anchorOffsetM>7500){result.reason='trajectoryCrossingOffset';return result;}
    result.upstreamTerrainCounts={water:result.upstream.points.filter(p=>p.water).length,island:result.upstream.points.filter(p=>p.island).length,mainland:result.upstream.points.filter(p=>p.mainland).length};result.accepted=true;return result;
  };
  Model.prototype._verifyCoastalInitialField=function(){
    const c=this.coastalGeometry,local=this._acceptedWindSampler||this._coastalWindSampler(),localAudit=c.appliedAdmission||this._auditCoastalFlow(local,this._coastalMainland);
    const it=forcingExact.call(this,0);while(!it.next().done){}const full={environment:(x,y)=>({x:this.env.sample(this.fields.u,x,y),y:this.env.sample(this.fields.v,x,y)}),fine:(x,y)=>({x:this.forcing.sample(this.fineU,x,y),y:this.forcing.sample(this.fineV,x,y)})};
    const verified=this._auditCoastalFlow(full,this._coastalMainland);let maxDifference=0;const points=[c.crossing,...(localAudit.upstream?.points||[]),...(localAudit.downstream?.points||[])];for(const p of [...points,...points.flatMap(p=>p.midpoint?[p.midpoint]:[])])for(const kind of ['environment','fine']){const a=local[kind](p.x,p.y),b=full[kind](p.x,p.y);maxDifference=Math.max(maxDifference,Math.abs(a.x-b.x),Math.abs(a.y-b.y));}
    if(!verified.accepted||maxDifference>1e-6)throw Error('沿海实际全域风复核失败 '+JSON.stringify({reason:verified.reason,maxDifference}));
    c.appliedAdmission=verified;c.appliedUpstreamStart={...verified.actualUpstreamStart};c.globalVerification={atSeconds:0,maxVelocityDifferenceMS:maxDifference,accepted:true};this.config.coastalGeometry=structuredClone(c);this._acceptedWindSampler=null;
    this._initialForcingCache={controlKey:JSON.stringify(this.controls),arrays:Object.fromEntries(['eu','ev','cu','cv','fineU','fineV'].map(k=>[k,this[k].slice()])),fields:Object.fromEntries(['u','v','um','vm','upperDiv','divL','airLM','airTop'].map(k=>[k,this.fields[k].slice()])),mechanismWind:Object.fromEntries(Object.entries(this.mechanismFields).filter(([k])=>k.startsWith('wind_')).map(([k,a])=>[k,a.slice()]))};
  };
  Model.prototype._terrainJetExit=function(crossing,axis,tangent){
    const g=this.forcing,z=this.geometry.zs,mean=s=>[-10000,0,10000].reduce((a,d)=>a+g.sample(z,crossing.x+axis.x*s+tangent.x*d,crossing.y+axis.y*s+tangent.y*d),0)/3;
    const coastHeight=mean(0);
    for(let s=20000;s<=100000;s+=5000){if(g.index(crossing.x+axis.x*s,crossing.y+axis.y*s)<0)break;const h=mean(s);
      if(h-coastHeight>=200&&h-mean(s-15000)>=80)return {distance:Math.max(15000,s-7500),reason:'first_windward_barrier',barrierHeightM:h,coastHeightM:coastHeight,barrierDistanceM:s};}
    return {distance:60000,reason:'frictional_inland_termination',coastHeightM:coastHeight};
  };
  Model.prototype._configureCoastalGeometry=function(){
    const proto=this.config.coastalPrototype,coastal=this.config.preset==='monsoon'&&(this.config.initiationModel==='focused_lift'?['coastal','terrain','fastline'].includes(this.config.scenarioGroup||'coastal'):(this.config.scenarioGroup||'coastal')==='coastal');
    if(!proto&&(!coastal||this.config.geography!=='real'))return;
    const flat=!!proto;if(flat&&this.config.geography!=='idealized')throw Error('平直海岸原型需 geography=idealized');
    const options={...(typeof proto==='object'?proto:{}),...(this.config.coastalForcing||{})},fg=this.forcing,rng=random(hash(this.config.seed,'mainland-coast-150'));
    const bounded=(key,fallback,lo,hi)=>{const v=options[key]??fallback;if(!Number.isFinite(v)||v<lo||v>hi)throw Error('沿海参数越界 '+key);return v;};
    const normalSpeed=bounded('inletNormal',6+6*rng(),1,20),alongSpeed=bounded('inletAlong',3+6*rng(),-15,20),midAlong=bounded('midAlong',this.config.initiationModel==='focused_lift'?10+6*rng():6+8*rng(),-20,25),midNormal=bounded('midNormal',this.config.initiationModel==='focused_lift'?-1+3*rng():-3+7*rng(),-15,15),exitWidth=bounded('exitWidth',20000,5000,100000),exitOffset=bounded('exitOffset',this.config.jetExitControl?-80000+160000*random(hash(this.config.seed,'jet-exit-placement'))():-10000+50000*rng(),-100000,100000),offshoreRun=bounded('offshoreRun',60000+60000*rng(),40000,120000);
    const terrainHash=flat?'idealized-straight-coast':this.terrain?.meta.binarySha256+':'+(this.terrain?.meta.subgridTerrain?.sourceSha256||''),finite=this.config.coastalWindModel==='finite_jet',parameters=this.config.coastalWindParameters,bg0=this.background(0),axisAngle=this.monsoon.axisAngle,seedAxis={x:Math.cos(axisAngle),y:Math.sin(axisAngle)};
    const canonical=v=>v&&typeof v==='object'?(Array.isArray(v)?v.map(canonical):Object.fromEntries(Object.keys(v).sort().map(k=>[k,canonical(v[k])]))):v;
    const cacheKey=JSON.stringify(canonical({schema:'coastal-geometry-1.37',initiationModel:this.config.initiationModel,weatherRegion:this.config.weatherRegion,varyMonsoonDirection:this.config.varyMonsoonDirection,terrainLiftDisabled:!!this.config.disableTerrainLift,jetExitControl:this.config.jetExitControl,jetExitGeometry:this.config.jetExitGeometry,monsoon925:this.config.monsoon925,boundedMonsoon:this.config.boundedMonsoon,hillJetBraking:this.config.hillJetBraking,slowMonsoonTurn:this.config.slowMonsoonTurn,windTurnStart:this.config.windTurnStart,organizedWarmSector:this.config.organizedWarmSector,terrainHash,mode:this.config.coastalWindModel,parameters,options,seed:this.config.seed,width:this.config.width,height:this.config.height,controls:this.controls,N:bg0.N,D:bg0.D,V:bg0.V}));
    if(this.config.coastalGeometry){
      if(this.config.coastalGeometry.schema!=='coastal-geometry-1.37'||this.config.coastalGeometry.cacheKey!==cacheKey)throw Error('沿海几何缓存模式/有效风/配置版本不匹配');
      if(this.config.coastalGeometry.terrainHash!==terrainHash)throw Error('沿海几何地形版本不匹配');
      this.coastalGeometry=structuredClone(this.config.coastalGeometry);
      const c=this.coastalGeometry;if(c.windMode!==this.config.coastalWindModel||!sameMesh(c.effectiveWindParameters,parameters))throw Error('沿海几何缓存有效风参数不匹配');
      if(finite&&(!Number.isFinite(c.axisDirection.x+c.axisDirection.y)||Math.abs(seedAxis.x-c.axisDirection.x)>1e-12||Math.abs(seedAxis.y-c.axisDirection.y)>1e-12))throw Error('沿海几何缓存与随机急流轴不一致');
    }else{
      let mainland=null,coastFields=null,candidates=[];
      if(flat){const y=typeof proto==='object'?(proto.coastY??this.config.height*.45):this.config.height*.45;
        if(!(y>30000&&y<this.config.height-30000))throw Error('原型海岸需在域内并保留两侧空间');
        candidates=[{x:this.config.width*.5,y,nx:0,ny:1}];
      }else{
        coastFields=this.terrain.fields;const seen=new Uint8Array(fg.n),queue=new Int32Array(fg.n);let best=[],bestNorth=false;
        for(let root=0;root<fg.n;root++){
          if(seen[root]||this.geometry.land[root]<.5)continue;let head=0,tail=1,north=false;queue[0]=root;seen[root]=1;const component=[];
          while(head<tail){const k=queue[head++],x=k%fg.nx,y=Math.floor(k/fg.nx);component.push(k);if(y===fg.ny-1)north=true;
            for(const q of [x>0?k-1:-1,x<fg.nx-1?k+1:-1,y>0?k-fg.nx:-1,y<fg.ny-1?k+fg.nx:-1])if(q>=0&&!seen[q]&&this.geometry.land[q]>=.5){seen[q]=1;queue[tail++]=q;}
          }
          if((north&&!bestNorth)||(north===bestNorth&&component.length>best.length)){best=component;bestNorth=north;}
        }
        if(best.length<400||!bestNorth)throw Error('沿海场景找不到足够大的持续大陆连通块');
        mainland=new Uint8Array(fg.n);for(const k of best)mainland[k]=1;this._coastalMainland=mainland;
        for(let j=8;j<fg.ny-8;j+=2)for(let i=8;i<fg.nx-8;i+=2){
          const k=j*fg.nx+i;if(!mainland[k]||Math.abs(coastFields.signedDistance[k])>5000)continue;
          let nx=coastFields.coastX[k],ny=coastFields.coastY[k],length=Math.hypot(nx,ny);if(length<.3)continue;nx/=length;ny/=length;
          let x=(i+.5)*fg.dx,y=(j+.5)*fg.dx,front=fg.index(x+10000*nx,y+10000*ny),back=fg.index(x-10000*nx,y-10000*ny);
          if((front>=0?mainland[front]:0)<(back>=0?mainland[back]:0)){nx=-nx;ny=-ny;}
          x-=coastFields.signedDistance[k]*nx;y-=coastFields.signedDistance[k]*ny;candidates.push({x,y,nx,ny});
        }
        // Seeded ranking is independent of quality and does not use place names.
        const regionalLon={guangxi:this.config.jetExitControl?110.8:108.0,west_guangdong:111.3,pearl_river:113.5,east_guangdong:115.8}[this.config.weatherRegion]??(110.4+6.2*random(hash(this.config.seed,'guangdong-inflow-longitude'))()),openingSW=clip((axisAngle*180/Math.PI-28)/25),targetLon=this.config.organizedWarmSector?111.75*openingSW+114.25*(1-openingSW):regionalLon,jitteredLon=targetLon+(this.config.weatherRegion==='auto'?0:(random(hash(this.config.seed,'coast-sector-jitter'))()-.5)*.8),targetX=fg.width/2+(jitteredLon-this.terrain.meta.center[0])*111195*Math.cos(this.terrain.meta.center[1]*Math.PI/180);
        if(this.config.jetExitControl)candidates=candidates.filter(p=>{const lon=this._approxLongitude(p.x);return lon>=110.35&&lon<=116.85;});
        candidates=candidates.map((p,i)=>({...p,rank:Math.abs(p.x-targetX)/150000+hash(this.config.seed,'coast-candidate',i)/4294967296*.35})).sort((a,b)=>a.rank-b.rank);
      }
      const landAt=(x,y)=>{const k=fg.index(x,y);return k>=0&&(flat?y>=candidates[0].y:mainland[k]>0);};
      const distanceAt=(x,y)=>flat?y-candidates[0].y:fg.sample(coastFields.signedDistance,x,y);
      let chosen=null;const rejected={domain:0,offshore:0,continuousLand:0,crossing:0,direction:0};
      // Rejection-sample the initial random direction when a shallow approach
      // cannot reach open sea and continuous mainland. Never invent a trigger
      // coordinate or relax the geographic admission checks.
      const attempts=flat?candidates:candidates.flatMap(candidate=>Array.from({length:8},(_,attempt)=>({...candidate,axisAngle:attempt===0?axisAngle:((this.config.slowMonsoonTurn?(axisAngle<Math.PI/4?15:55):15)+(this.config.slowMonsoonTurn?20:60)*random(hash(this.config.seed,'axis-retry',attempt))())*Math.PI/180})));
      for(const candidate of attempts){
        const n={x:candidate.nx,y:candidate.ny},t={x:n.y,y:-n.x},vx=normalSpeed*n.x+alongSpeed*t.x,vy=normalSpeed*n.y+alongSpeed*t.y,js=Math.min(5,Math.hypot(parameters.jetExcessNormal,parameters.jetExcessAlong)),directionAngle=candidate.axisAngle??axisAngle,jx=js*Math.cos(directionAngle),jy=js*Math.sin(directionAngle),speed=Math.hypot(vx,vy),dir=finite?{x:Math.cos(directionAngle),y:Math.sin(directionAngle)}:{x:vx/speed,y:vy/speed};
        if(!flat&&!finite&&(vy<=0||vx<-.25*speed)){rejected.direction++;continue;}
        // A southwesterly warm-sector steering flow must run along, rather than
        // across/backward along, the chosen coastal reach. Reserve 60 km downstream;
        // requiring a whole lifetime here incorrectly excluded eastern Guangdong.
        if(!flat&&finite&&!this.config.monsoon925&&this.config.initiationModel==='focused_lift'){
          const largeScale={x:Math.cos(this.monsoon.midDirection),y:Math.sin(this.monsoon.midDirection)};
          if(t.x*largeScale.x+t.y*largeScale.y<Math.cos(Math.PI/6)){rejected.direction++;continue;}
          const run=60000,endX=candidate.x+t.x*run,endY=candidate.y+t.y*run;
          if(endX<25000||endY<25000||endX>fg.width-25000||endY>fg.height-25000){rejected.domain++;continue;}
        }
        let crossing=null;
        for(let s=-20000;s<=30000;s+=2500){
          const x=candidate.x+dir.x*s,y=candidate.y+dir.y*s;if(!landAt(x,y))continue;
          let hits=0,first=0,maxGap=0,gap=0;
          for(let d=0;d<40000;d+=2500){const yes=landAt(x+dir.x*d,y+dir.y*d);if(yes){hits++;gap=0;if(d<10000)first++;}else{gap+=2500;maxGap=Math.max(maxGap,gap);}}
          if(hits>=13&&first>=3&&maxGap<=5000){crossing={x,y};break;}
        }
        if(!crossing){rejected.continuousLand++;continue;}
        if(Math.abs(distanceAt(crossing.x,crossing.y))>7500){rejected.crossing++;continue;}
        const terrainExit=this.config.jetExitControl?{distance:exitOffset,sampledDistance:exitOffset,reason:exitOffset<0?'seeded_offshore_deceleration':'seeded_inland_deceleration'}:this.config.initiationModel==='focused_lift'&&!flat&&options.exitOffset===undefined?this._terrainJetExit(crossing,dir,t):{distance:exitOffset,reason:'prescribed'},actualExit=terrainExit.distance;
        // Shallow SW angles need a longer offshore reach to obtain the same
        // 30 km marine clearance. Keep the random direction, extend the fetch.
        let actualOffshoreRun=offshoreRun;
        if(!flat&&options.offshoreRun===undefined)while(actualOffshoreRun<200000&&distanceAt(crossing.x-dir.x*actualOffshoreRun,crossing.y-dir.y*actualOffshoreRun)>=-30000)actualOffshoreRun+=5000;
        const start={x:crossing.x-dir.x*actualOffshoreRun,y:crossing.y-dir.y*actualOffshoreRun},exit={x:crossing.x+dir.x*actualExit,y:crossing.y+dir.y*actualExit};
        if(fg.index(start.x,start.y)<0||fg.index(exit.x,exit.y)<0){rejected.domain++;continue;}
        const startDistance=distanceAt(start.x,start.y);if(startDistance>=-30000){rejected.offshore++;continue;}
        let earlyMainland=false,offshoreSamples=[];
        for(let d=0;d<actualOffshoreRun-10000;d+=5000){const x=start.x+dir.x*d,y=start.y+dir.y*d,land=landAt(x,y);offshoreSamples.push({x,y,mainland:land});if(land)earlyMainland=true;}
        if(earlyMainland){rejected.offshore++;continue;}
        chosen={schema:'coastal-geometry-1.37',cacheKey,windMode:this.config.coastalWindModel,effectiveWindParameters:{...parameters},legacyReferenceWind:{x:vx,y:vy},jetExcessVector:{x:jx,y:jy},jetPresent:js>0,axisDefinition:finite?'seeded monsoon direction; independent of coastline orientation':'legacy inlet vector',terrainHash,kind:flat?'straight-coast-prototype':'largest-north-connected-mainland',coordinates:'model x/y metres from southwest domain corner',crossingDefinition:'first sampled entry whose next 40 km is persistent mainland; not an exact surveyed shoreline',proxyResolutionM:fg.dx,start,crossing,exit,normal:n,tangent:t,axisDirection:dir,inletNormal:normalSpeed,inletAlong:alongSpeed,midAlong,midNormal,offshoreRun:actualOffshoreRun,exitOffset:actualExit,sampledExitOffset:exitOffset,terrainExit,exitWidth,jetWidth:this.monsoon?.width||100000,startSignedDistance:startDistance,crossingSignedDistance:distanceAt(crossing.x,crossing.y),exitSignedDistance:distanceAt(exit.x,exit.y),mainlandSamples:Array.from({length:16},(_,i)=>{const d=i*2500,x=crossing.x+dir.x*d,y=crossing.y+dir.y*d;return {x,y,distanceAlong:d,mainland:landAt(x,y),signedDistance:distanceAt(x,y)};}),continuousLandLengthM:40000,minimumMainlandCoverage:13/16,maximumWaterGapM:5000,offshoreSamples,rejected,options:{...options},limitations:['Coast and mainland use the model DEM-derived proxy, not surveyed or observed coastline.','The 2.5 km geometry and smoothed normal limit crossing precision.']};
        chosen.jetAxisStart={...start};if(!flat&&finite){const previous=this.coastalGeometry;this.coastalGeometry=chosen;const sampler=this._coastalWindSampler(),audit=this._auditCoastalFlow(sampler,mainland);this.coastalGeometry=previous;if(!audit.accepted){rejected[audit.reason]=(rejected[audit.reason]||0)+1;chosen=null;continue;}chosen.appliedAdmission=audit;chosen.localSamplingWork=sampler.work();this._acceptedWindSampler=sampler;}break;
      }
      if(!chosen)throw Error('无法构造满足外海起点和持续大陆跨岸段的沿海场景 '+JSON.stringify(rejected));
      this.coastalGeometry=chosen;this.config.coastalGeometry=structuredClone(chosen);
    }
    if(!flat&&!this._coastalMainland){const g=this.forcing,mask=new Uint8Array(g.n),queue=new Int32Array(g.n);let h=0,t=0,root=g.index(this.coastalGeometry.crossing.x,this.coastalGeometry.crossing.y);if(root>=0&&this.geometry.land[root]>=.5){mask[root]=1;queue[t++]=root;}while(h<t){const k=queue[h++],i=k%g.nx,j=Math.floor(k/g.nx);for(const q of [i?k-1:-1,i+1<g.nx?k+1:-1,j?k-g.nx:-1,j+1<g.ny?k+g.nx:-1])if(q>=0&&!mask[q]&&this.geometry.land[q]>=.5){mask[q]=1;queue[t++]=q;}}this._coastalMainland=mask;}
    const c=this.coastalGeometry,p=this.monsoon;
    if(!p)throw Error('沿海原型需 preset=monsoon');
    p.axisX=c.start.x-this.config.width/2;p.axisY=c.start.y-this.config.height/2;p.axisAngle=Math.atan2(c.axisDirection.y,c.axisDirection.x);p.end=c.offshoreRun+c.exitOffset;p.endWidth=c.exitWidth;
    if(flat){p.midDirection=Math.atan2(c.midAlong*c.tangent.y+c.midNormal*c.normal.y,c.midAlong*c.tangent.x+c.midNormal*c.normal.x);p.midSpeed=Math.hypot(c.midAlong,c.midNormal);}
    if(flat)for(const key of ['rhL','rhM','iL','iM','eL','eM'])if(options[key]!==undefined){if(!Number.isFinite(options[key]))throw Error('原型热力参数非法 '+key);p[key]=options[key];}
    this.config.environment={...p};
  };
  Model.prototype._coastalEnvelope=function(at,key){
    const options=this.coastalGeometry?.options||{},end=options[key];if(end===undefined)return 1;if(!Number.isFinite(end)||end<0)throw Error('沿海控制时刻非法 '+key);const x=clip((at-end)/900);return 1-x*x*(3-2*x);
  };

  Model.prototype._triggerRegionMembership=function(x,y){const p=this._frontCoordinates(x,y),a=Math.abs(p.s)<=50000&&Math.abs(p.n)<=20000,b=Math.abs(p.s)<=90000&&Math.abs(p.n)<=50000;return ['domain',a?'central100x40':'outside100x40',b?'central180x100':'outside180x100'];};
  Model.prototype._diagnoseTriggerWindows=function*(){
    if(!this.config.mechanismEvidence){this.windowDiagnostics=null;return;}const stat=()=>({sampleAreaKm2:0,lowActiveAreaKm2:0,midActiveAreaKm2:0,lowGateIntegralKm2:0,midGateIntegralKm2:0,expectedEnvironmentLow:0,expectedEnvironmentMid:0,births:{},activeIds:[]}),windows=Object.fromEntries(['domain','central100x40','outside100x40','central180x100','outside180x100'].map(key=>[key,stat()])),g=this.cold,f=this.fields,bg=this.background(),lambda=this.config.lambda0??1e-5,area=g.area/1e6;
    for(let j=0;j<g.ny;j++){for(let i=0;i<g.nx;i++){const k=j*g.nx+i,x=(i+.5)*g.dx,y=(j+.5)*g.dx,e=this.env.index(x,y),cold=this.h[k]>=40&&this.q[k]>=20&&this.q[k]/this.h[k]>=.3,cinL=bg.iL+20*clip((.75-f.rhL[e])/.25)+.08*(this.config.surfaceAccessMode==='consistent'?this.q[k]:f.q[e]),cinM=bg.iM+20*clip((.65-f.rhM[e])/.25),fl=this.config.initiationModel==='focused_lift'?this.gate(x,y,0,bg,true).F:cold?0:clip((f.rhL[e]-.65)/.25)*clip((f.el[e]-.15)/.65)*clip((.08*f.xiL[e]-cinL)/15),fm=this.config.initiationModel==='focused_lift'?this.gate(x,y,1,bg,true).F:clip((f.rhM[e]-.45)/.35)*clip((f.em[e]-.15)/.65)*clip((.08*f.xiM[e]-cinM)/15);for(const key of this._triggerRegionMembership(x,y)){const w=windows[key];w.sampleAreaKm2+=area;w.lowActiveAreaKm2+=(fl>0?area:0);w.midActiveAreaKm2+=(fm>0?area:0);w.lowGateIntegralKm2+=fl*area;w.midGateIntegralKm2+=fm*area;w.expectedEnvironmentLow+=lambda*fl*area*DT;w.expectedEnvironmentMid+=lambda*.3*fm*area*DT;}}if(j%16===15)yield;}
    this.windowDiagnostics={schema:'trigger-windows-1.10',stepStart:this.t,stepEnd:this.t+DT,birthsAtStart:this.stats.births,stage:'post-mix/environment-diagnosis before initiation',quadrature:'Cold FV center area quadrature of environment-only gate, no CP boost; actual points for births/IDs. Windows are diagnostic only.',windows};
  };
  Model.prototype._commitTriggerWindows=function(){
    const d=this.windowDiagnostics;if(!d)return;const count=this.stats.births-d.birthsAtStart;if(count>0)for(const e of this.events.slice(-count))for(const key of this._triggerRegionMembership(e.x,e.y)){const w=d.windows[key];w.births[e.channel||'historicalArea']=(w.births[e.channel||'historicalArea']||0)+1;}
    for(const c of this.cells)for(const key of this._triggerRegionMembership(c.x,c.y))d.windows[key].activeIds.push(c.id);
    this.windowTotals??={steps:0,seconds:0,windows:{}};this.windowTotals.steps++;this.windowTotals.seconds+=DT;for(const [key,w]of Object.entries(d.windows)){const t=this.windowTotals.windows[key]??={sampleAreaTimeKm2Seconds:0,lowActiveAreaTimeKm2Seconds:0,midActiveAreaTimeKm2Seconds:0,lowGateAreaTimeKm2Seconds:0,midGateAreaTimeKm2Seconds:0,expectedEnvironmentLow:0,expectedEnvironmentMid:0,births:{},activeCellTimeSeconds:0};t.sampleAreaTimeKm2Seconds+=w.sampleAreaKm2*DT;t.lowActiveAreaTimeKm2Seconds+=w.lowActiveAreaKm2*DT;t.midActiveAreaTimeKm2Seconds+=w.midActiveAreaKm2*DT;t.lowGateAreaTimeKm2Seconds+=w.lowGateIntegralKm2*DT;t.midGateAreaTimeKm2Seconds+=w.midGateIntegralKm2*DT;t.expectedEnvironmentLow+=w.expectedEnvironmentLow;t.expectedEnvironmentMid+=w.expectedEnvironmentMid;t.activeCellTimeSeconds+=w.activeIds.length*DT;for(const [name,n]of Object.entries(w.births))t.births[name]=(t.births[name]||0)+n;}
  };
  Model.prototype._coastalWindDiagnostics=function(){const c=this.coastalGeometry;if(!c)return {requested:this.config.coastalWindModel,effective:this.effectiveModes.coastalWindModel};const x=c.crossing.x,y=c.crossing.y,components={};for(const [key,array]of Object.entries(this.mechanismFields))if(key.startsWith('wind_')&&!key.endsWith('_face'))components[key]=this.forcing.sample(array,x,y);return {requested:this.config.coastalWindModel,effective:this.effectiveModes.coastalWindModel,parameters:this.config.coastalWindParameters,geometry:{crossing:c.crossing,exit:c.exit,axis:c.axisDirection,tangent:c.tangent,normal:c.normal},actualCrossing:{environmentU:this.env.sample(this.fields.u,x,y),environmentV:this.env.sample(this.fields.v,x,y),fineU:this.fineU?this.forcing.sample(this.fineU,x,y):null,fineV:this.fineV?this.forcing.sample(this.fineV,x,y):null},componentsAtCrossing:components,forcingInterpolation:this.forcingInterpolation,meaning:'Measured applied wind/decomposition at latest forcing stage; G/E are interpolated analytic envelope samples before terrain/smoothing.'};};

  Model.prototype._organizationContains=function(x,y){const c=this.coastalGeometry;if(!c)return false;const dx=x-c.crossing.x,dy=y-c.crossing.y;return Math.abs(dx*c.tangent.x+dy*c.tangent.y)<=90000&&Math.abs(dx*c.normal.x+dy*c.normal.y)<=50000;};
  Model.prototype._edgeState=function(x,y){const k=this.env.index(x,y),access=this.surfaceAccess(x,y),legacy=this.config.surfaceAccessMode==='legacy',h=legacy?this.cold.sample(this.h,x,y):access.h,q=legacy?this.cold.sample(this.q,x,y):access.Q,bg=this.background(),rh=k>=0?this.fields.rhL[k]:null;return {x,y,inDomain:k>=0,h,q,qOverH:h>0?q/h:0,surfaceAccess:access,accessMode:this.config.surfaceAccessMode,fineCold:access.cold,legacyFineQCut:q>=20,envMeanQ:k>=0?this.fields.q[k]:null,envColdFraction:k>=0?this.fields.coldFraction[k]:null,KenvL:k>=0?this.fields.KenvL[k]:null,CINL:k>=0?bg.iL+20*clip((.75-rh)/.25)+.08*(legacy?this.fields.q[k]:q):null,envMeanCINL:k>=0?this.fields.CINL[k]:null,rhL:rh};};
  Model.prototype._triggerLayerDiagnostic=function(){return {poissonMean:0,candidates:0,expectedAcceptedGivenCandidates:0,acceptedBeforeSpacing:0,spacingRejected:0,births:0,fineColdRejected:0,layer:'',KminusCIN:{edges:[-40,-20,-10,-5,0,5,10,20,40],bins:new Array(10).fill(0),sum:0,min:null,max:null},Kcp:{edges:[0,.1,1,5,10,20,40,80],bins:new Array(9).fill(0),sum:0,min:null,max:null},F:{edges:[0,.01,.05,.1,.25,.5,.75,1],bins:new Array(9).fill(0),sum:0,min:null,max:null}};};
  Model.prototype._recordTriggerGate=function(d,gate){
    d.candidates++;d.expectedAcceptedGivenCandidates+=gate.F;d.fineColdRejected+=gate.rejection==='fineCold'?1:0;
    for(const [key,value]of [['KminusCIN',gate.power-(gate.CIN||0)],['Kcp',gate.coldPower||0],['F',gate.F]]){const h=d[key];let b=0;while(b<h.edges.length&&value>h.edges[b])b++;h.bins[b]++;h.sum+=value;h.min=h.min===null?value:Math.min(h.min,value);h.max=h.max===null?value:Math.max(h.max,value);}
  };
  Model.prototype._recordDeath=function(c,reason,mass,transfer){
    if(c.retired)return;const energyTransfer=this._retireConvectiveEnergy(c,reason);c.retired=true;this.stats.deaths++;this.stats.deathReasons[reason]=(this.stats.deathReasons[reason]||0)+1;
    this.lifeEvents.push({type:'death',id:c.id,t:this.t+DT,born:c.born,age:c.age,x:c.x,y:c.y,reason,conditions:{warmAccessFraction:c.lowWarmAccessFraction??null,connectedFeed:c.supplyInlet?.connectedFeed??null,thermalPotential:c.thermalPotential??null,outside:this.env.index(c.x,c.y)<0,starved:(c.starvedSeconds||0)>=1200,supportLost:(c.supportLostSeconds||0)>=1200,maxAge:c.age>=c.T,pulseCompleted:!!c.pulse&&c.pulse.N>=c.pulse.Nend},pulse:c.pulse?{...c.pulse}:null,cellLifecycle:this.config.cellLifecycle,pulseEnvelope:c.pulseEnvelope??null,effectiveUpdraftArea:c.effectiveUpdraftArea??null,physicalUpdraftArea:c.physicalUpdraftArea??c.updraftArea??0,a:c.a,lastSupplyStepEnd:c.lastSupplyStepEnd??null,requestedKgThisStep:c.requestedKgThisStep||0,suppliedKgThisStep:c.suppliedKgThisStep||0,supplyRatio:c.supplyRatio||0,starvedSeconds:c.starvedSeconds||0,supportLostSeconds:c.supportLostSeconds||0,updraftArea:c.updraftArea||0,remainingMassKg:mass,transfer,convectiveHeating:this.config.convectiveHeating,convectivePhaseEnergyJ:c.convectivePhaseEnergyJ,convectiveEnergyTransfer:energyTransfer,convectiveEnergyStep:c.convectiveEnergyStep?{...c.convectiveEnergyStep}:null,lineage:{birthId:c.id,triggerBoundaryId:c.parent,physicalFaceId:c.physicalFaceId??null,segmentKey:c.segmentKey??null,channel:c.channel??null,source:c.source,limitation:'Boundary index links trigger evidence; it is not a uniquely attributed parent-cell causal lineage.'}});
    if(this.lifeEvents.length>20000)this.lifeEvents.splice(0,1000);
  };

  Model.prototype._configureCurvedCoast=function(){
    const c=this.coastalGeometry;
    if(this.config.coastalConvergenceGeometry!=='curvilinear'||!c||c.kind==='straight-coast-prototype')return;
    if(!Coast)throw Error('曲线海岸模块尚未加载');
    this.coastChain=Coast.shoreline(this.forcing,this.geometry.land,this._coastalMainland,c.crossing,c.tangent);
    this.coastCoordinates=Coast.field(this.coastChain,this.forcing);
    this.config.coastChainInfo={schema:this.coastChain.schema,terrainHash:c.terrainHash,anchorProjection:this.coastChain.anchorProjection,lengthM:this.coastChain.lengthM,nodes:this.coastChain.nodes};
  };
  Model.prototype._coastCoordinate=function(x,y){
    const f=this.coastCoordinates;if(!f)return null;
    const xx=Math.max(0,Math.min(f.nx-1,x/f.dx-.5+f.halo)),yy=Math.max(0,Math.min(f.ny-1,y/f.dx-.5+f.halo)),i=Math.floor(xx),j=Math.floor(yy),i1=Math.min(i+1,f.nx-1),j1=Math.min(j+1,f.ny-1),a=xx-i,b=yy-j;
    const sample=v=>(v[j*f.nx+i]*(1-a)+v[j*f.nx+i1]*a)*(1-b)+(v[j1*f.nx+i]*(1-a)+v[j1*f.nx+i1]*a)*b;
    const nx=sample(f.normalX),ny=sample(f.normalY),l=Math.hypot(nx,ny);
    return {s:sample(f.s),n:sample(f.n),nx:l>.1?nx/l:0,ny:l>.1?ny/l:0,weight:l>.1?sample(f.weight):0};
  };
  Model.prototype._configureMesoscaleForcing=function(){
    const c=this.coastalGeometry;if(!c){this.mesoscaleSchedule={schema:'mesoscale-1.6',enabled:false,events:[],skipped:[],reason:'no audited coastal geometry'};return;}
    const option=this.config.coastalForcing?.mesoscale??c.options.mesoscale,explicit=this.config.mesoscaleEvents,flat=c.kind==='straight-coast-prototype',configurationKey=JSON.stringify({option,explicit,hours:this.config.hours,seed:this.config.seed,convergenceGeometry:this.config.coastalConvergenceGeometry,geometry:{cacheKey:c.cacheKey,kind:c.kind,crossing:c.crossing,normal:c.normal,tangent:c.tangent,axisDirection:c.axisDirection}});
    if(option!==undefined&&(option===null||!['boolean','object'].includes(typeof option)||Array.isArray(option)))throw Error('mesoscale 必须为布尔值或参数对象');
    if(this.config.mesoscaleSchedule?.configurationKey===configurationKey){this.mesoscaleSchedule=structuredClone(this.config.mesoscaleSchedule);return;}
    const schedule={schema:'mesoscale-1.6',enabled:option!==false,configurationKey,formula:'deltaUn=-A*envelope*exp(-ds^2/(2Ls^2))*tanh(dn/w)*exp(-dn^2/(2Ln^2)); deltaU=deltaUn*nHat',events:[],skipped:[],geometryTerrainHash:c.terrainHash,parameterMeaning:'Declared engineering weather forcing, not an observationally fitted dynamical law.'};
    if(option===false){this.mesoscaleSchedule=schedule;this.config.mesoscaleSchedule=structuredClone(schedule);return;}
    const validate=e=>{
      const defaults={id:'explicit-0',A:3,Ls:50000,w:10000,Ln:60000,s0:0,n0:0,t0:3600,rise:1800,hold:14400,fall:1800,alongDriftM:0,normalDriftM:0},x={...defaults,...e};
      for(const key of Object.keys(defaults))if(key!=='id'&&!Number.isFinite(x[key]))throw Error('中尺度事件参数非法 '+key);
      if(typeof x.id!=='string'||x.A<0||x.A>4||x.Ls<35000||x.Ls>70000||x.w<5000||x.w>15000||x.Ln<40000||x.Ln>80000||x.t0<0||x.rise<900||x.rise>1800||x.fall<900||x.fall>1800||x.hold<7200||x.hold>21600||Math.abs(x.alongDriftM)>10000||Math.abs(x.normalDriftM)>2000)throw Error('中尺度事件超出声明工程范围');
      x.end=x.t0+x.rise+x.hold+x.fall;return x;
    };
    const add=(raw,generated)=>{
      let e=validate(raw),audit=this._mesoscaleCoastAudit(e);
      // Geometric fit only; no weather/rain output is consulted to select a patch.
      if(generated&&!audit.valid){const r=random(hash(this.config.seed,'mesoscale-patch',e.id));for(let attempt=0;attempt<8&&!audit.valid;attempt++){e={...e,s0:-45000+90000*r(),Ls:Math.max(35000,e.Ls-5000)};audit=this._mesoscaleCoastAudit(e);}}
      if(!audit.valid){schedule.skipped.push({id:e.id,reason:'finite coastal segment failed proxy land/sea audit',parameters:e,audit});return;}
      schedule.events.push({...e,coastAudit:audit});
    };
    if(explicit!==undefined){if(!Array.isArray(explicit))throw Error('mesoscaleEvents 必须是事件数组');explicit.forEach((e,i)=>{if(!e||typeof e!=='object'||Array.isArray(e))throw Error('显式事件必须是参数对象');add({id:'explicit-'+i,...e},false);});}
    else if(flat)add({id:'prototype-0',...(typeof option==='object'?option:{})},false);
    else{
      if(typeof option==='object'&&['id','t0','end'].some(k=>k in option))throw Error('真实沿海时间覆盖请使用 mesoscaleEvents 显式事件表');
      let cursor=0,index=0;const total=this.config.hours*3600;
      while(cursor<total){const r=random(hash(this.config.seed,'mesoscale-weather',index)),t0=cursor+(1800+5400*r()),rise=900+900*r(),hold=7200+14400*r(),fall=900+900*r(),bg=this.background(t0),id='coastal-'+index;
        const raw={id,t0,rise,hold,fall,A:1+3*r(),Ls:35000+35000*r(),w:5000+10000*r(),Ln:40000+40000*r(),s0:-30000+60000*r(),n0:-5000+10000*r(),alongDriftM:-10000+20000*r(),normalDriftM:-2000+4000*r(),...(typeof option==='object'?option:{})};
        if(t0>=total)break;
        if(bg.rhL<.72||bg.eL<.35||bg.V<.25*this.preset.baseV||r()>.8)schedule.skipped.push({id,reason:'unfavorable background or seeded event absence',t0,background:{rhL:bg.rhL,eL:bg.eL,V:bg.V}});else add(raw,true);
        cursor=raw.t0+raw.rise+raw.hold+raw.fall+10800+14400*r();index++;
      }
    }
    schedule.events.sort((a,b)=>a.t0-b.t0);for(let i=1;i<schedule.events.length;i++)if(schedule.events[i].t0<schedule.events[i-1].end)throw Error('中尺度事件不应重叠；请显式保留事件间歇');
    const ids=new Set();for(const e of schedule.events){if(ids.has(e.id))throw Error('中尺度事件 ID 重复');ids.add(e.id);}
    this.mesoscaleSchedule=schedule;this.config.mesoscaleSchedule=structuredClone(schedule);
  };
  Model.prototype._mesoscaleCoastAudit=function(e){
    const c=this.coastalGeometry,g=this.forcing,flat=c.kind==='straight-coast-prototype',proto=this.config.coastalPrototype,coastY=typeof proto==='object'?(proto.coastY??this.config.height*.45):this.config.height*.45;
    if(!flat&&!this._mesoscaleMainland){const mask=new Uint8Array(g.n),queue=new Int32Array(g.n),root=g.index(c.crossing.x,c.crossing.y);let h=0,t=0;if(root>=0&&this.geometry.land[root]>=.5){queue[t++]=root;mask[root]=1;}while(h<t){const k=queue[h++],i=k%g.nx,j=Math.floor(k/g.nx);for(const q of [i?k-1:-1,i+1<g.nx?k+1:-1,j?k-g.nx:-1,j+1<g.ny?k+g.nx:-1])if(q>=0&&!mask[q]&&this.geometry.land[q]>=.5){mask[q]=1;queue[t++]=q;}}this._mesoscaleMainland=mask;}
    const points=[];let good=0;
    for(const fraction of [0,.5,1])for(const offset of [-1,-.5,0,.5,1]){
      const s=e.s0+fraction*e.alongDriftM+offset*e.Ls,n=e.n0+fraction*e.normalDriftM,shore=this.coastChain?Coast.at(this.coastChain,s):{x:c.crossing.x+c.tangent.x*s,y:c.crossing.y+c.tangent.y*s,nx:c.normal.x,ny:c.normal.y},states=[];
      if(!shore){points.push({timeFraction:fraction,alongOffset:offset,valid:false,reason:'shore_chain_endpoint',states});continue;}
      const x=shore.x+shore.nx*n,y=shore.y+shore.ny*n;
      for(const d of [-25000,-10000,10000,25000,40000]){const px=x+shore.nx*d,py=y+shore.ny*d,k=g.index(px,py),inDomain=k>=0,mainland=inDomain&&(flat?py>=coastY:this._mesoscaleMainland[k]!==0);states.push({normalOffset:d,x:px,y:py,inDomain,land:inDomain&&(flat?py>=coastY:this.geometry.land[k]>=.5),mainland,signedDistance:inDomain?(flat?py-coastY:g.sample(this.terrain.fields.signedDistance,px,py)):null});}
      const valid=states.every(p=>p.inDomain)&&states.slice(0,2).every(p=>!p.land)&&states.slice(2).filter(p=>p.mainland).length>=2;if(valid)good++;points.push({timeFraction:fraction,alongOffset:offset,x,y,valid,states});
    }
    return {valid:good>=12&&[0,.5,1].every(t=>points.filter(p=>p.timeFraction===t&&p.valid).length>=4),validCount:good,total:15,points,definition:'At start/middle/end drift and five alongshore positions over ±Ls: both offshore probes water, >=2/3 inland probes on audited mainland; >=4/5 valid at each time.',limitation:'Local planar normal and DEM proxy; Gaussian tails outside the audited ±Ls segment remain a declared approximation.'};
  };
  Model.prototype.mesoscaleAt=function(at=this.t){
    const smooth=x=>{const u=clip(x);return u*u*(3-2*u);},active=[];
    for(const e of this.mesoscaleSchedule?.events||[]){const amplitude=smooth((at-e.t0)/e.rise)*(1-smooth((at-(e.t0+e.rise+e.hold))/e.fall));if(amplitude<=0||e.A===0)continue;const f=clip((at-e.t0)/(e.end-e.t0));active.push({id:e.id,A:e.A,amplitude,Ls:e.Ls,w:e.w,Ln:e.Ln,s0:e.s0+e.alongDriftM*f,n0:e.n0+e.normalDriftM*f,t0:e.t0,end:e.end});}return active;
  };
  Model.prototype._updateMesoscaleLifecycle=function(){
    const active=new Set(this.mesoscaleAt(this.t).map(e=>e.id));
    for(const e of this.mesoscaleSchedule?.events||[]){const state=this.forcingEventStates[e.id]||{active:false};const now=active.has(e.id);if(now!==state.active){this.forcingEvents.push({id:e.id,type:now?'activation':'deactivation',actualStepStart:this.t,scheduledStart:e.t0,scheduledEnd:e.end,previousActiveStepStart:state.lastActiveStep??null,definition:'Actual physical-step forcing use; snapshot sampling does not create these events.'});this.stats.forcingTransitions=(this.stats.forcingTransitions||0)+1;}state.active=now;if(now)state.lastActiveStep=this.t;this.forcingEventStates[e.id]=state;}
  };
  Model.prototype._mesoscaleVelocity=function(x,y,events){
    const c=this.coastalGeometry;if(!c||events.length===0)return {u:0,v:0,normal:0};const dx=x-c.crossing.x,dy=y-c.crossing.y,s=dx*c.tangent.x+dy*c.tangent.y,n=dx*c.normal.x+dy*c.normal.y;let value=0;
    if(this.coastCoordinates){const p=this._coastCoordinate(x,y);for(const e of events){const ds=p.s-e.s0,dn=p.n-e.n0;value-=p.weight*e.A*e.amplitude*Math.exp(-ds*ds/(2*e.Ls**2))*Math.tanh(dn/e.w)*Math.exp(-dn*dn/(2*e.Ln**2));}return {u:value*p.nx,v:value*p.ny,normal:value};}
    for(const e of events){const ds=s-e.s0,dn=n-e.n0;value-=e.A*e.amplitude*Math.exp(-ds*ds/(2*e.Ls**2))*Math.tanh(dn/e.w)*Math.exp(-dn*dn/(2*e.Ln**2));}return {u:value*c.normal.x,v:value*c.normal.y,normal:value};
  };

  Model.prototype.organizationDiagnostics=function(){
    const c=this.coastalGeometry;if(!c)return {enabled:false};const g=this.env,f=this.fields,bg=this.background(),points=[];
    for(const along of [-60000,-30000,-10000,0,10000,30000,60000])for(const tangent of [-60000,0,60000]){
      const x=c.crossing.x+c.axisDirection.x*along+c.tangent.x*tangent,y=c.crossing.y+c.axisDirection.y*along+c.tangent.y*tangent,k=g.index(x,y);if(k<0)continue;
      const u=f.u[k],v=f.v[k],midU=f.um[k],midV=f.vm[k];points.push({x,y,alongFromCrossing:along,alongShore:tangent,u,v,inlandWind:u*c.normal.x+v*c.normal.y,alongShoreWind:u*c.tangent.x+v*c.tangent.y,midInlandWind:midU*c.normal.x+midV*c.normal.y,midAlongShoreWind:midU*c.tangent.x+midV*c.tangent.y,divL:f.divL[k],airLM:f.airLM[k],airTop:f.airTop[k],xiL:f.xiL[k],KenvL:f.KenvL[k],CINL:f.CINL[k],rhL:f.rhL[k],wl:f.wl[k],wm:f.wm[k],relativeToMidlayer:{x:u-midU,y:v-midV},vaporFluxL:{x:u*f.wl[k],y:v*f.wl[k]}});
    }
    const mask=new Uint8Array(g.n);let requested=0,supplied=0,mass=0,massX=0,massY=0;const localCold={areaKm2:0,envQCutAreaKm2:0,fineColdAreaKm2:0,KenvSum:0,CINsum:0},localSupply={lowCold:{requestedKg:0,suppliedKg:0},lowWarm:{requestedKg:0,suppliedKg:0},midCold:{requestedKg:0,suppliedKg:0},midWarm:{requestedKg:0,suppliedKg:0}};
    for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++){const x=(i+.5)*g.dx-c.crossing.x,y=(j+.5)*g.dx-c.crossing.y;mask[j*g.nx+i]=Math.abs(x*c.tangent.x+y*c.tangent.y)<=90000&&Math.abs(x*c.normal.x+y*c.normal.y)<=50000?1:0;}
    for(const cell of this.cells){const k=g.index(cell.x,cell.y);mass+=cell.M;massX+=cell.M*cell.x;massY+=cell.M*cell.y;if(k>=0&&mask[k]){requested+=cell.requestedKgThisStep||0;supplied+=cell.suppliedKgThisStep||0;for(const name of Object.keys(localSupply)){localSupply[name].requestedKg+=cell.supplyBreakdown?.[name]?.requestedKg||0;localSupply[name].suppliedKg+=cell.supplyBreakdown?.[name]?.suppliedKg||0;}}}
    const local={airInKgS:0,airOutKgS:0,vaporInKgS:0,vaporOutKgS:0,interfaceAirNetKgS:0,requestedKgThisStep:requested,suppliedKgThisStep:supplied};
    const u=this._buffers.get('airUL')||this.eu,v=this._buffers.get('airVL')||this.ev;
    const face=(left,right,speed)=>{
      const a=left>=0&&mask[left]!==0,b=right>=0&&mask[right]!==0;if(a===b)return;const donor=speed>=0?left:right,q=donor<0?bg.rhL*saturation(298):f.wl[donor],sign=a?1:-1,air=sign*speed*1400*g.dx,water=sign*speed*q*g.dx;
      local.airInKgS+=Math.max(-air,0);local.airOutKgS+=Math.max(air,0);local.vaporInKgS+=Math.max(-water,0);local.vaporOutKgS+=Math.max(water,0);
    };
    for(let j=0;j<g.ny;j++)for(let i=0;i<=g.nx;i++)face(i?j*g.nx+i-1:-1,i<g.nx?j*g.nx+i:-1,u[j*(g.nx+1)+i]);
    for(let j=0;j<=g.ny;j++)for(let i=0;i<g.nx;i++)face(j?(j-1)*g.nx+i:-1,j<g.ny?j*g.nx+i:-1,v[j*g.nx+i]);
    for(let k=0;k<g.n;k++)if(mask[k]){local.interfaceAirNetKgS+=f.airLM[k]*g.area;localCold.areaKm2+=g.area/1e6;localCold.envQCutAreaKm2+=(f.q[k]>=20?g.area/1e6:0);localCold.fineColdAreaKm2+=f.coldFraction[k]*g.area/1e6;localCold.KenvSum+=f.KenvL[k]*g.area/1e6;localCold.CINsum+=f.CINL[k]*g.area/1e6;}
    return {enabled:true,geometry:c,background:bg,points,coastalWind:this._coastalWindDiagnostics(),surfaceAccess:{mode:this.config.surfaceAccessMode,pointSampling:'Piecewise constant owning cold FV cell',CINLFieldMeaning:'Environment mean-Q engineering diagnostic; consistent gate uses actual candidate/inlet Q instead',supplyBuckets:this.supplyDiagnostics?.bucketMeaning},cellLifecycle:this.config.cellLifecycle,localSection:{...local,extent:'|along shore| <=90 km, |shore-normal| <=50 km about the audited crossing',fluxDefinition:'Instantaneous stored face wind with output-state upwind vapor; not an interval-integrated closed local water budget.'},coldRegion:{...localCold,meanKenv:localCold.areaKm2?localCold.KenvSum/localCold.areaKm2:0,meanCIN:localCold.areaKm2?localCold.CINsum/localCold.areaKm2:0},localCellSupply:{...localSupply,scope:'Cells centered in the local rectangle; physical footprints can cross its boundary.'},cellSystem:{massKg:mass,massCentroid:mass>0?{x:massX/mass,y:massY/mass}:null},globalTransportLedger:this.ledger,units:{wind:'m/s',divL:'s^-1',airLM:'kg/m2/s',vaporFlux:'kg/m/s',xiL:'m',KenvL:'J/kg engineering proxy',CINL:'J/kg engineering proxy'},mesoscale:{schedule:this.mesoscaleSchedule,activeAtOutput:this.mesoscaleAt(this.t),activeAtLastForcing:this.mesoscaleAt(this.forcingInterpolation?.at??Math.max(0,this.t-(this.stats.steps?DT:0))),forcingInterpolation:this.forcingInterpolation},stage:'Finite-duration mesoscale wind forcing plus retained jet exit; weather organization unvalidated.'};
  };

  function liquidReflectivity(columnWater,thickness=1500,occupancy=1){
    if(columnWater<=0)return 0;if(!(thickness>0&&occupancy>0&&occupancy<=1))throw Error('DSD 箱厚或占比非法');
    const W=1000*columnWater/(thickness*occupancy),lambda=(Math.PI*1e-3*8000/W)**.25;return occupancy*720*8000/lambda**7;
  }
  Model.prototype.backendInfo=function(){return this._numericBackend?this._numericBackend.info():{...this._backendStatus};};
  const api={prepareBackend:Numeric.prepare,prepareBackendSync:Numeric.prepareSync,VERSION,DT,ALPHA,THETA,Grid,Model,PRESETS,clip,hash,random,poisson,saturation,evaporationCapacity,phaseAdjustment,liquidReflectivity,convectiveEnergyStep,areaMean,validateProjection};root.VacationCore=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
