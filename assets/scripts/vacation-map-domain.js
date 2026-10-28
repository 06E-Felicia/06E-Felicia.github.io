/* Geographic view limits strictly inside the projected physical grid. */
(function(root){
  'use strict';
  function bounds(meta,projection){
    const w=meta.nx*meta.dx,h=meta.ny*meta.dy,pad=Math.max(meta.dx,meta.dy),x=w/2-pad,y=h/2-pad;
    if(!(x>0&&y>0))throw Error('模拟地图范围无效');
    let west=-Infinity,east=Infinity,south=-Infinity,north=Infinity;
    // AEQD edges are curved in Web Mercator. The enclosing geographic box is
    // unsafe: use the intersection of the four sampled physical edge limits.
    for(let i=0;i<=256;i++){
      const f=2*i/256-1;
      west=Math.max(west,projection.inverse([-x,f*y])[0]);
      east=Math.min(east,projection.inverse([x,f*y])[0]);
      south=Math.max(south,projection.inverse([f*x,-y])[1]);
      north=Math.min(north,projection.inverse([f*x,y])[1]);
    }
    const result={west,east,south,north};
    if(!covered(result,meta,projection))throw Error('地图边界超出模拟网格');
    return result;
  }
  function covered(b,meta,projection){
    if(!b||![b.west,b.east,b.south,b.north].every(Number.isFinite))return false;
    const w=meta.nx*meta.dx,h=meta.ny*meta.dy;
    for(let i=0;i<=64;i++){
      const lon=b.west+(b.east-b.west)*i/64,lat=b.south+(b.north-b.south)*i/64;
      for(const p of [[lon,b.south],[lon,b.north],[b.west,lat],[b.east,lat]]){
        const [x,y]=projection.forward(p);
        if(!Number.isFinite(x+y)||Math.abs(x)>=w/2||Math.abs(y)>=h/2)return false;
      }
    }
    return true;
  }
  function stations(data,meta,projection,labels={}){
    return data.stations.filter(s=>{const [x,y]=projection.forward([s.lon,s.lat]);return Math.abs(x)<meta.nx*meta.dx/2&&Math.abs(y)<meta.ny*meta.dy/2;})
      .map(s=>({...s,name:labels[s.id]||s.name,stationName:s.name}))
      .sort((a,b)=>a.province.localeCompare(b.province,'zh')||a.name.localeCompare(b.name,'zh'));
  }
  const api={bounds,covered,stations};root.VacationMapDomain=api;
  if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
