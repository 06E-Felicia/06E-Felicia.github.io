/* Sparse zero runs keep fine rainfall archives compact. Quantisation is for
 * display only; no encoded state is fed back into integration. */
(function(root){
'use strict';
const S=root.StormSol;
const schema={temp:[S.grid,.05],dew:[S.grid,.05],energy:[S.grid,1],air:[S.grid,.001],
  convRate:[S.product,.1],poolDepth:[S.forcing,1],poolU:[S.forcing,.2],poolV:[S.forcing,.2],stormU:[S.product,.1],stormV:[S.product,.1],cold:[S.forcing,.02],ice:[S.product,.01],rate:[S.product,.02],last5:[S.ledger,.01],
  hour:[S.ledger,.02],total:[S.ledger,.1]};
function base64(bytes){
  if(bytes.toBase64)return bytes.toBase64();
  let text='';for(let i=0;i<bytes.length;i+=16384)text+=String.fromCharCode(...bytes.subarray(i,i+16384));
  return btoa(text);
}
function encode(values,scale){
  const words=new Uint16Array(values.length*2+2);let end=0,zeros=0;
  function flush(){while(zeros){const count=Math.min(65535,zeros);words[end++]=0;words[end++]=count;zeros-=count;}}
  for(let i=0;i<values.length;i++){
    const n=Math.round(values[i]/scale);if(!n){zeros++;continue;}
    flush();words[end++]=S.clamp(n,-32767,32767)&65535;
  }
  flush();return base64(new Uint8Array(words.buffer,0,end*2));
}
function decode(text,size){
  const bytes=Uint8Array.fromBase64?Uint8Array.fromBase64(text):Uint8Array.from(atob(text),c=>c.charCodeAt(0));
  const words=new Uint16Array(bytes.buffer,bytes.byteOffset,bytes.length/2),out=new Int16Array(size);
  let pos=0;for(let j=0;j<words.length;j++){
    if(words[j])out[pos++]=words[j];else{if(!words[++j])throw Error('Sol 帧游程无效');pos+=words[j];}
  }
  if(pos!==size)throw Error('Sol 帧网格不完整');return out;
}
function snapshot(model){
  const fields={};for(const [key,[,scale]] of Object.entries(schema))fields[key]=encode(model[key],scale);
  return {schema:2,format:'stormsol-1',hour:model.steps/6,fields};
}
function manifest(model,seed,hours){
  return {schema:2,edition:'sol',engine:'stormsol-1',status:'running',simulation:true,execution:'browser',
    config:{...model.config,seed,hours,grid_km:2,frame_minutes:10,bounds:S.BOUNDS},
    physicsMesh:{environmentDx:5000,forcingDx:2500,coldDx:2500,precipitationDx:2000,rainLedgerDx:1000,coreStepSeconds:S.DT},
    grid:S.product,rain_grid:S.ledger,frames:[],terrain:encode(model.terrain,1)};
}
const terrainCache=new WeakMap();
function frame(raw,m){
  const decoded={};
  for(const [key,[g]] of Object.entries(schema))decoded[key]=decode(raw.fields[key],g.nx*g.ny);
  if(!terrainCache.has(m))terrainCache.set(m,decode(m.terrain,S.forcing.nx*S.forcing.ny));
  const heights=terrainCache.get(m),fields={},p=m.config;
  function onGrid(native,i){
    if(native===S.product)return i;
    return S.index(native,(i%S.product.nx+.5)*2,(Math.floor(i/S.product.nx)+.5)*2);
  }
  const level=S.LEVELS;
  const get=(key,i)=>decoded[key][onGrid(schema[key][0],i)]*schema[key][1];
  function field(name,read){fields[name]={read};}
  for(const [name,key] of Object.entries({temperature:'temp',dewpoint:'dew',rainrate:'rate',mucape:'energy',coldair:'air',coldpool:'cold',coldpool_depth:'poolDepth'}))
    field(name,i=>get(key,i));
  for(const [name,key] of Object.entries({rain5:'last5',rain_total:'total',rain_hour:'hour'})){
    const v=decoded[key],scale=schema[key][1];field('point_'+name,i=>v[i]*scale);field(name,i=>get(key,i));
  }
  field('terrain',i=>heights[onGrid(S.forcing,i)]);
  // Vertical samples are diagnostic columns anchored to the computed surface
  // and hydrometeors. Evaluate only the queried beam / sounding levels.
  function wind(i,z,axis){
    const base=S.wind(p,(i%S.product.nx+.5)*2,(Math.floor(i/S.product.nx)+.5)*2,
      raw.hour,z,get('air',i),fields.terrain.read(i),axis)+
      get(axis==='u'?'stormU':'stormV',i)*Math.exp(-(((z-2100)/2400)**2));
    const h=get('poolDepth',i),weight=S.clamp((h-25)/160)*S.clamp(1-z/Math.max(1,h))*(1-.75*S.clamp((get('air',i)-.18)/.64));
    return base*(1-weight)+weight*get(axis==='u'?'poolU':'poolV',i);
  }
  for(const [label,z] of Object.entries({10:10,925:800,500:5600,300:9300})){
    field('u'+label,i=>wind(i,z,'u'));field('v'+label,i=>wind(i,z,'v'));
  }
  field('gust',i=>Math.hypot(wind(i,10,'u'),wind(i,10,'v'))+4*Math.sqrt(get('cold',i)));
  field('u3',(i,k)=>wind(i,level[k],'u'));field('v3',(i,k)=>wind(i,level[k],'v'));
  const temp=(i,z)=>S.airTemperature(get('temp',i),7*get('air',i)+get('cold',i),z);
  const pressure=(i,z)=>1013*Math.exp(-(fields.terrain.read(i)+z)/8200);
  field('t3',(i,k)=>temp(i,level[k]));field('p3',(i,k)=>pressure(i,level[k]));
  field('q3',(i,k)=>{const z=level[k],td=Math.min(temp(i,z)-.2,get('dew',i)-.0068*z);
    const e=6.112*Math.exp(17.67*td/(td+243.5));return .622*e/(pressure(i,z)-e);});
  function reflectivity(rate){return rate>.015?10*Math.log10(200*rate**1.6):-30;}
  field('composite',i=>reflectivity(Math.max(get('rate',i),get('ice',i)*1.3)));
  field('dbz3',(i,k)=>{const z=level[k];return reflectivity(Math.max(get('rate',i)*Math.exp(-z/3800),get('ice',i)*1.3*Math.exp(-(((z-4800)/3200)**2))));});
  field('w3',(i,k)=>Math.min(18,Math.sqrt(get('convRate',i)))*Math.exp(-((level[k]-3600)**2)/8000000));
  field('fall3',(i,k)=>level[k]>4500?1:5);
  return {hour:raw.hour,fields};
}
root.StormSolFrame={manifest,snapshot,frame};
})(globalThis);
