/* Rolling rainfall uses existing cumulative replay frames: no 144-grid ring. */
(function(root){
 'use strict';
 async function calculate(entry,index,get,decode,windowSeconds=86400){
  const current=decode(entry).total,n=current.length,target=entry.simTime-windowSeconds,out=new Float32Array(n);
  if(target<=0){for(let i=0;i<n;i++)out[i]=current[i]*.01;return out;}
  let lo=0,hi=index.length-1;
  while(lo<=hi){const mid=(lo+hi)>>1;if(index[mid].simTime<=target)lo=mid+1;else hi=mid-1;}
  if(hi<0)throw Error('缺少 滑动前的累计降水记录');
  const left=index[hi],right=left.simTime===target?left:index[hi+1];
  if(!right||right.simTime<target)throw Error('滑动降水历史不完整');
  const a=await get(left.seq),b=right===left?a:await get(right.seq);
  if(!a||!b||a.grid.nx!==entry.grid.nx||a.grid.ny!==entry.grid.ny||a.grid.dx!==entry.grid.dx||b.grid.dx!==entry.grid.dx||b.grid.nx!==entry.grid.nx||b.grid.ny!==entry.grid.ny)throw Error('滑动降水网格不匹配');
  const av=decode(a).total,bv=decode(b).total,w=right===left?0:(target-left.simTime)/(right.simTime-left.simTime);
  for(let i=0;i<n;i++){const value=(current[i]-(av[i]+w*(bv[i]-av[i])))*.01;if(value<-.02)throw Error('累计降水记录逆序');out[i]=Math.max(0,value);}
  return out;
 }
 const api={calculate};root.VacationRain24=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
