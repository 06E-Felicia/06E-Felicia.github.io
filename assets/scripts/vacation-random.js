/* Balanced automatic opening regimes; random order in every two-run bag. */
(function(root){
 'use strict';
 function nextWindStart(storage,randomBit){
  let remaining=[];try{const value=JSON.parse(storage?.getItem('vacation-wind-opening-bag')||'[]');if(Array.isArray(value)&&value.length===1&&['west','south'].includes(value[0]))remaining=value;}catch{}
  if(!remaining.length)remaining=randomBit()?['west','south']:['south','west'];
  const opening=remaining.shift();try{storage?.setItem('vacation-wind-opening-bag',JSON.stringify(remaining));}catch{}
  return opening;
 }
 function nextJetRegion(storage,random){
  const regions=['west_guangdong','pearl_river','east_guangdong'];let bag=[];
  try{const value=JSON.parse(storage?.getItem('vacation-jet-region-bag')||'null');if(Array.isArray(value)&&value.length<3&&new Set(value).size===value.length&&value.every(x=>regions.includes(x)))bag=value;}catch{}
  if(!bag.length){bag=regions.slice();for(let i=bag.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[bag[i],bag[j]]=[bag[j],bag[i]];}}
  const region=bag.shift();try{storage?.setItem('vacation-jet-region-bag',JSON.stringify(bag));}catch{}return region;
 }
 const api={nextWindStart,nextJetRegion};root.VacationRandom=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
