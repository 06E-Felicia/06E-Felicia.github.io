/* Deterministic mainland shoreline coordinates. No weather fields enter this module. */
(function(root){
  'use strict';
  const smooth=x=>{x=Math.max(0,Math.min(1,x));return x*x*(3-2*x);};
  function project(p,a,b){const dx=b.x-a.x,dy=b.y-a.y,l2=dx*dx+dy*dy,t=Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/l2)),x=a.x+t*dx,y=a.y+t*dy;return {x,y,t,d2:(p.x-x)**2+(p.y-y)**2};}
  function shoreline(g,land,mainland,anchor,tangent){
    const edges=[],starts=new Map(),ends=new Map(),key=(x,y)=>x+','+y;
    const add=(x0,y0,x1,y1)=>{const e={id:edges.length,a:{x:x0*g.dx,y:y0*g.dx},b:{x:x1*g.dx,y:y1*g.dx},start:key(x0,y0),end:key(x1,y1)};edges.push(e);for(const [map,k]of [[starts,e.start],[ends,e.end]]){if(!map.has(k))map.set(k,[]);map.get(k).push(e);}};
    for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++)if(mainland[j*g.nx+i]){
      // Inland is on the left of every directed edge. Domain boundaries and
      // other land (including islands) are never substituted for open water.
      if(j>0&&land[(j-1)*g.nx+i]<.5)add(i,j,i+1,j);
      if(i+1<g.nx&&land[j*g.nx+i+1]<.5)add(i+1,j,i+1,j+1);
      if(j+1<g.ny&&land[(j+1)*g.nx+i]<.5)add(i+1,j+1,i,j+1);
      if(i>0&&land[j*g.nx+i-1]<.5)add(i,j+1,i,j);
    }
    if(!edges.length)throw Error('曲线海岸缺少大陆/水面边界');
    let first=null,best=Infinity;for(const e of edges){const p=project(anchor,e.a,e.b);if(p.d2<best){best=p.d2;first=e;}}
    if(best>7500**2)throw Error('入流锚点距真实岸链超过7.5km');
    const used=new Set([first.id]);
    function walk(back){const out=[];let current=first;for(let n=0;n<edges.length;n++){
      const choices=(back?ends.get(current.start):starts.get(current.end))||[];
      const available=choices.filter(e=>!used.has(e.id));if(!available.length)break;
      // At a diagonal saddle take the largest left turn, keeping a component
      // boundary on the same mainland side rather than jumping across water.
      const dx=current.b.x-current.a.x,dy=current.b.y-current.a.y;
      available.sort((a,b)=>{const turn=e=>{const ex=e.b.x-e.a.x,ey=e.b.y-e.a.y;return Math.atan2(back?ex*dy-ey*dx:dx*ey-dy*ex,dx*ex+dy*ey);};return turn(b)-turn(a)||a.id-b.id;});
      current=available[0];used.add(current.id);out.push(current);
    }return out;}
    const forward=walk(false),backward=walk(true).reverse(),chain=[...backward,first,...forward],raw=[chain[0].a,...chain.map(e=>e.b)];
    const arc=[0];for(let i=1;i<raw.length;i++)arc.push(arc[i-1]+Math.hypot(raw[i].x-raw[i-1].x,raw[i].y-raw[i-1].y));
    const firstIndex=backward.length,at=project(anchor,first.a,first.b),s0=arc[firstIndex]+at.t*g.dx;
    const ahead=rawAt(s0+10000),behind=rawAt(s0-10000),direction=((ahead.x-behind.x)*tangent.x+(ahead.y-behind.y)*tangent.y)>=0?1:-1;
    function rawAt(s){s=Math.max(0,Math.min(arc.at(-1),s));let lo=0,hi=arc.length-1;while(hi-lo>1){const mid=(lo+hi)>>1;if(arc[mid]<=s)lo=mid;else hi=mid;}const f=(s-arc[lo])/(arc[hi]-arc[lo]);return {x:raw[lo].x+(raw[hi].x-raw[lo].x)*f,y:raw[lo].y+(raw[hi].y-raw[lo].y)*f};}
    const lo=Math.max(-250000,direction>0?-s0:s0-arc.at(-1)),hi=Math.min(250000,direction>0?arc.at(-1)-s0:s0),nodes=[];
    for(let s=lo;s<=hi;s+=2500){let p=rawAt(s0+direction*s);
      for(const sigma of [5000,2500]){let x=0,y=0,w=0;for(let d=-3*sigma;d<=3*sigma;d+=1250){const q=rawAt(s0+direction*(s+d)),a=Math.exp(-d*d/(2*sigma*sigma));x+=a*q.x;y+=a*q.y;w+=a;}const candidate={x:x/w,y:y/w};if(Math.hypot(candidate.x-p.x,candidate.y-p.y)<=5000){p=candidate;break;}}
      nodes.push({...p,s});
    }
    if(nodes.length<3)throw Error('有效岸链过短');
    for(let i=0;i<nodes.length;i++){const a=nodes[Math.max(0,i-1)],b=nodes[Math.min(nodes.length-1,i+1)],l=Math.hypot(b.x-a.x,b.y-a.y);nodes[i].nx=-direction*(b.y-a.y)/l;nodes[i].ny=direction*(b.x-a.x)/l;}
    return {schema:'mainland-shore-coordinates-1',nodes,direction,anchorProjection:{x:at.x,y:at.y,distanceM:Math.sqrt(best)},lengthM:hi-lo,sourceSegments:chain.length};
  }
  function at(chain,s){const a=chain.nodes;if(s<a[0].s||s>a.at(-1).s)return null;let lo=0,hi=a.length-1;while(hi-lo>1){const m=(lo+hi)>>1;if(a[m].s<=s)lo=m;else hi=m;}const f=(s-a[lo].s)/(a[hi].s-a[lo].s),x=a[lo].x+f*(a[hi].x-a[lo].x),y=a[lo].y+f*(a[hi].y-a[lo].y),nx=a[lo].nx+f*(a[hi].nx-a[lo].nx),ny=a[lo].ny+f*(a[hi].ny-a[lo].ny),l=Math.hypot(nx,ny);return {x,y,nx:nx/l,ny:ny/l};}
  function nearest(chain,x,y){let best=Infinity,result=null;const nodes=chain.nodes;
    for(let i=0;i<nodes.length-1;i++){const a=nodes[i],b=nodes[i+1],p=project({x,y},a,b);if(p.d2>=best)continue;best=p.d2;let nx=a.nx+p.t*(b.nx-a.nx),ny=a.ny+p.t*(b.ny-a.ny),l=Math.hypot(nx,ny);nx/=l;ny/=l;const dot=(x-p.x)*nx+(y-p.y)*ny;result={s:a.s+p.t*(b.s-a.s),n:Math.sign(dot)*Math.sqrt(best),nx,ny};}
    result.weight=smooth((result.s-nodes[0].s)/10000)*smooth((nodes.at(-1).s-result.s)/10000)*smooth((240000-Math.abs(result.n))/40000);return result;
  }
  function field(chain,g,halo=6){
    const nx=g.nx+2*halo,ny=g.ny+2*halo,n=nx*ny,s=new Float64Array(n),d=new Float64Array(n),weight=new Float64Array(n);
    for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){const k=j*nx+i,p=nearest(chain,(i-halo+.5)*g.dx,(j-halo+.5)*g.dx);s[k]=p.s;d[k]=p.n;weight[k]=p.weight;}
    const kernel=Array.from({length:13},(_,i)=>Math.exp(-(((i-6)*g.dx)**2)/(2*5000**2))),total=kernel.reduce((a,b)=>a+b,0),temp=new Float64Array(n),blur=new Float64Array(n);
    for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){let v=0;for(let q=-6;q<=6;q++)v+=kernel[q+6]*d[j*nx+Math.max(0,Math.min(nx-1,i+q))];temp[j*nx+i]=v/total;}
    for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){let v=0;for(let q=-6;q<=6;q++)v+=kernel[q+6]*temp[Math.max(0,Math.min(ny-1,j+q))*nx+i];blur[j*nx+i]=v/total;}
    const normalX=new Float64Array(n),normalY=new Float64Array(n);
    for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){const k=j*nx+i,gx=(blur[j*nx+Math.min(nx-1,i+1)]-blur[j*nx+Math.max(0,i-1)])/((i>0&&i<nx-1?2:1)*g.dx),gy=(blur[Math.min(ny-1,j+1)*nx+i]-blur[Math.max(0,j-1)*nx+i])/((j>0&&j<ny-1?2:1)*g.dx),l=Math.hypot(gx,gy);weight[k]*=smooth((l-.1)/.4);if(l>.1){normalX[k]=gx/l;normalY[k]=gy/l;}}
    return {nx,ny,halo,dx:g.dx,s,n:d,normalX,normalY,weight};
  }
  const api={shoreline,at,nearest,field};root.VacationCoast=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
