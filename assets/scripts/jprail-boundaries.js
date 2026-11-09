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
