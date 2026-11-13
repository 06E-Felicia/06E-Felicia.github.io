// Fare boundaries are editorial facts supported by each pass's official scope.
// A company interface, viewport edge or line junction is never evidence of one.
export function officialStationPins(pass,stations) {
 if(!pass)return [];
 const operators=new Set(pass.selectors.flatMap(s=>s.operators));
 return (pass.stationPins?.stations||[]).flatMap(pin=>{
  const candidates=stations.filter(s=>s[0]===pin.name);
  candidates.sort((a,b)=>{
   const score=s=>Number(s[3]===pin.operator)*4+Number(s[4]===pin.line)*2+Number(operators.has(s[3]));
   return score(b)-score(a);
  });
  return candidates[0]?[{...pin,station:candidates[0]}]:[];
 });
}

// These are known company interfaces, not inferred fare boundaries. Only
// show an interface when at least one matching displayed side reaches it.
export function companyStationPins(boundaries,features,stations) {
 const lines=new Map();
 for(const f of features){const p=f.properties,key=p.operator+'|'+p.name+'|'+p.kind;if(!lines.has(key))lines.set(key,[]);lines.get(key).push(f);}
 function touchesSide(f,side) {
  const [lon,lat]=side.point,scale=111320,cos=Math.cos(lat*Math.PI/180);
  const paths=f.geometry.type==='LineString'?[f.geometry.coordinates]:f.geometry.coordinates;
  return paths.some(path=>path.some((q,i)=>{
   if(!i)return false;
   const p=path[i-1],ax=(p[0]-lon)*scale*cos,ay=(p[1]-lat)*scale,bx=(q[0]-lon)*scale*cos,by=(q[1]-lat)*scale;
   const dx=bx-ax,dy=by-ay,t=Math.max(0,Math.min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy||1)));
   return Math.hypot(ax+t*dx,ay+t*dy)<150;
  }));
 }
 return boundaries.flatMap(b=>{
  const sides=b.sides.filter(s=>(lines.get(s.operator+'|'+s.line+'|'+s.kind)||[]).some(f=>touchesSide(f,s)));
  if(!sides.length)return [];
  const station=stations.filter(s=>s[0]===b.name).sort((a,c)=>{
   const score=s=>Number(sides.some(t=>t.operator===s[3]&&t.line===s[4]))*10-Math.hypot(s[1]-b.lat,s[2]-b.lon);
   return score(c)-score(a);
  })[0];
  if(!station)return [];
  return [{name:b.name,role:'company',companyJunction:true,station,sides:b.sides,note:'JR 公司运营局界：'+b.sides.map(s=>s.operator+' · '+s.line).join(' ／ ')+'。运营局界本身不表示 Pass 的适用边界。'}];
 });
}

export function stationAnnotations(farePins,companyPins) {
 const remaining=new Map(companyPins.map(p=>[p.name,p]));
 const result=farePins.map(pin=>{
  const company=remaining.get(pin.name);if(!company)return pin;
  remaining.delete(pin.name);
  return {...pin,companyJunction:true,junctionNote:company.note,note:pin.note+' '+company.note};
 });
 return result.concat([...remaining.values()]);
}
