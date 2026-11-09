// N02 company interfaces are shown only when the selected coverage reaches
// exactly one side. Covering both companies must not create an internal edge.
function reaches(features,side) {
 const [x,y]=side.point,scale=Math.cos(y*Math.PI/180),limit=160/111320;
 for(const f of features) {
  const p=f.properties;if(p.operator!==side.operator||p.name!==side.line||p.kind!==side.kind)continue;
  const lines=f.geometry.type==='LineString'?[f.geometry.coordinates]:f.geometry.coordinates;
  for(const line of lines)for(let i=1;i<line.length;i++) {
   const a=line[i-1],b=line[i];if(Math.min(a[1],b[1])>y+limit||Math.max(a[1],b[1])<y-limit)continue;
   const ax=(a[0]-x)*scale,ay=a[1]-y,bx=(b[0]-x)*scale,by=b[1]-y,dx=bx-ax,dy=by-ay;
   const t=Math.max(0,Math.min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy||1)));
   if(Math.hypot(ax+t*dx,ay+t*dy)<=limit)return true;
  }
 }
 return false;
}
export function companyBoundaryPins(boundaries,features) {
 return boundaries.flatMap(boundary=>{
  const sides=boundary.sides.filter(side=>reaches(features,side));if(sides.length!==1)return [];
  const side=sides[0];
  return [{name:boundary.name,role:'boundary',boundaryKind:'company',station:[boundary.name,side.point[1],side.point[0],side.operator,side.line],note:`${boundary.sides.map(s=>s.operator).join('／')}运营区间交接站；当前匹配范围只覆盖一侧。具体乘车条件以官方范围为准。`}];
 });
}
