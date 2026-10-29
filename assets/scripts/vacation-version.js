/* Lightweight shared runtime contract for the page, Worker and production model. */
(function(root){
 'use strict';
 const MODEL_VERSION='vacation-1.37.0',RESOURCE_VERSION='1.37.0-r1',NUMERIC_ABI=12203;
 function checkpointPreflight(c){
  if(!c)return {eligible:false,reason:'missing'};
  if(c.version!==MODEL_VERSION)return {eligible:false,reason:'version'};
  const cfg=c.config,s=c.stats,a=c.arrays,record=v=>v&&typeof v==='object'&&!Array.isArray(v)&&!ArrayBuffer.isView(v);
  if(![cfg,s,a,c.physicsMesh,c.productMesh,c.ledger,c.heatBudget,c.convectiveEnergyBudget].every(record)||!['real','idealized'].includes(cfg.geography)||!['monsoon','coast','hills','afternoon','decay'].includes(cfg.preset))return {eligible:false,reason:'metadata'};
  if(!cfg||!s||!a||!Number.isInteger(cfg.seed)||!['low','standard','high'].includes(cfg.quality)||!Number.isFinite(cfg.hours)||cfg.hours<=0||!Number.isSafeInteger(c.t)||c.t<0||!Number.isSafeInteger(s.steps)||s.steps<0||c.t!==s.steps*600||c.t>Math.ceil(cfg.hours*3600/600)*600||typeof c.terrainHash!=='string'||!c.physicsMesh||!c.productMesh||!Array.isArray(c.cells)||!Array.isArray(c.triggerSources)||!c.ledger||!c.heatBudget||!c.convectiveEnergyBudget||!['field_wl','field_wm','h','q','Px','Py','precip_upper_core','rainTotal'].every(k=>Object.hasOwn(a,k)))return {eligible:false,reason:'metadata'};
  return {eligible:true,reason:null}; // Full array/state/ledger validation belongs to Model.restore.
 }
 function simulationTime(t,config={}){
  const minutes=Math.round(t/60)+(config.startHour??20)*60,day=Math.floor(minutes/1440);
  return {clock:String(Math.floor(minutes/60)%24).padStart(2,'0')+':'+String(minutes%60).padStart(2,'0'),day:config.calendarOrigin==='previous_day'?(day===0?'前一日':'第 '+day+' 天'):'第 '+(day+1)+' 天'};
 }
 const api=Object.freeze({MODEL_VERSION,RESOURCE_VERSION,NUMERIC_ABI,checkpointPreflight,simulationTime});root.VacationVersion=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
