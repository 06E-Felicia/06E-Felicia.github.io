/* Fused float64 MUSCL / SSP-RK2, sharing the Python model's WASM buffers.
 * No different physical scheme, grid, timestep or single-precision shortcut.
 * float32 and non-contiguous inputs retain the NumPy reference path.
 */
(function(root){
 'use strict';
 const scratch=new Map();
 const minmod=(a,b)=>a*b>0?(a>0?Math.min(a,b):Math.max(a,b)):0;
 function storage(n,nfx,nfy){let s=scratch.get(n);if(!s||s.fx.length!==nfx||s.fy.length!==nfy){s={sx:new Float64Array(n),sy:new Float64Array(n),fx:new Float64Array(nfx),fy:new Float64Array(nfy),first:new Float64Array(n)};scratch.set(n,s);}return s;}
 function fused(a,ux,vy,div,out,dt,dx,boundary,conservative,nx,ny){
  const n=a.length,plane=nx*ny,nxface=ny*(nx+1),nyface=(ny+1)*nx,levels=n/plane;
  const s=storage(n,levels*nxface,levels*nyface),barray=ArrayBuffer.isView(boundary),none=boundary==null;
  function stage(f,second){
   // A NumPy zero-dimensional boundary is exposed as a one-element buffer.
   // It is a broadcast SCALAR, not an array to index by every grid cell.
   // Number also handles integer NumPy buffers without BigInt arithmetic.
   const ghost=(index)=>none?f[index]:barray?Number(boundary[boundary.length===1?0:index]):Number(boundary);
   for(let k=0;k<levels;k++){
    const base=k*plane,bx=k*nxface,by=k*nyface,wx=(k*nxface)%ux.length,wy=(k*nyface)%vy.length;
    for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
     const i=base+y*nx+x,value=f[i];
     s.sx[i]=minmod(value-(x?f[i-1]:ghost(i)),(x<nx-1?f[i+1]:ghost(i))-value);
     s.sy[i]=minmod(value-(y?f[i-nx]:ghost(i)),(y<ny-1?f[i+nx]:ghost(i))-value);
    }
    for(let y=0;y<ny;y++){
     const row=base+y*nx,fr=bx+y*(nx+1),wr=wx+y*(nx+1);
     let wind=ux[wr];s.fx[fr]=wind*(wind>=0?ghost(row):f[row]-s.sx[row]*.5);
     for(let x=1;x<nx;x++){const i=row+x;wind=ux[wr+x];s.fx[fr+x]=wind*(wind>=0?f[i-1]+s.sx[i-1]*.5:f[i]-s.sx[i]*.5);}
     const i=row+nx-1;wind=ux[wr+nx];s.fx[fr+nx]=wind*(wind>=0?f[i]+s.sx[i]*.5:ghost(i));
    }
    for(let x=0;x<nx;x++){const i=base+x,wind=vy[wy+x];s.fy[by+x]=wind*(wind>=0?ghost(i):f[i]-s.sy[i]*.5);}
    for(let y=1;y<ny;y++)for(let x=0;x<nx;x++){const i=base+y*nx+x,j=y*nx+x,wind=vy[wy+j];s.fy[by+j]=wind*(wind>=0?f[i-nx]+s.sy[i-nx]*.5:f[i]-s.sy[i]*.5);}
    for(let x=0;x<nx;x++){const i=base+(ny-1)*nx+x,wind=vy[wy+ny*nx+x];s.fy[by+ny*nx+x]=wind*(wind>=0?f[i]+s.sy[i]*.5:ghost(i));}
    for(let y=0;y<ny;y++)for(let x=0;x<nx;x++){
     const i=base+y*nx+x,ix=bx+y*(nx+1)+x,iy=by+y*nx+x;
     const tendency=-((s.fx[ix+1]-s.fx[ix])+(s.fy[iy+nx]-s.fy[iy]))/dx+(conservative?0:f[i]*div[i%div.length]);
     if(second)out[i]=.5*(a[i]+f[i]+dt*tendency);else s.first[i]=a[i]+dt*tendency;
    }
   }
  }
  stage(a,false);stage(s.first,true);
 }
 function pythonKernel(a,ux,vy,div,out,dt,dx,boundary,conservative,nx,ny){
  const proxies=[a,ux,vy,div,out],buffers=[];
  try{
   if(boundary&&typeof boundary.getBuffer==='function')proxies.push(boundary);
   for(const proxy of proxies)buffers.push(proxy.getBuffer());
   const view=(b)=>b.data.subarray(b.offset,b.offset+b.shape.reduce((n,x)=>n*x,1));
   const fields=buffers.map(view),ghost=buffers.length===6?fields[5]:boundary;
   fused(fields[0],fields[1],fields[2],fields[3],fields[4],dt,dx,ghost,conservative,nx,ny);
  }finally{
   for(const buffer of buffers)buffer.release();
   for(const proxy of proxies)proxy.destroy();
  }
 }
 function moistPythonKernel(t,lp,h,out,count,fractional=false){
  const proxies=[t,lp,h,out],buffers=[];
  const RD=287.05,CP=1004,EPS=.62195691,LV=2500840;
  function rate(temp,pressure){const e=611.2*Math.exp(17.67*(temp-273.15)/Math.max(temp-29.65,120)),r=EPS*e/Math.max(pressure-e,100);return (RD*temp+LV*r)/(CP+LV*LV*r*EPS/(RD*temp*temp));}
  try{
   for(const proxy of proxies)buffers.push(proxy.getBuffer());
   const fields=buffers.map(b=>b.data.subarray(b.offset,b.offset+b.shape.reduce((n,x)=>n*x,1)));
   for(let i=0;i<fields[0].length;i++){
    let value=fields[0][i],pressureLog=fields[1][i],step=fields[2][i],pressure=Math.exp(pressureLog);
    if(fractional){
     for(let j=0;j<count;j++)value+=(step/count)*rate(value,pressureLog*Math.exp(step*(j+.5)/count));
     fields[3][i]=value;continue;
    }
    for(let j=0;j<count;j++){
     const middle=Math.exp(pressureLog+step/2),end=Math.exp(pressureLog+step);
     const a=rate(value,pressure),b=rate(value+a*step/2,middle),c=rate(value+b*step/2,middle),d=rate(value+c*step,end);
     value=value+step*(a+2*b+2*c+d)/6;pressureLog+=step;pressure=end;
    }
    fields[3][i]=value;
   }
  }finally{for(const buffer of buffers)buffer.release();for(const proxy of proxies)proxy.destroy();}
 }
 root.SimulationAdvection={fused,pythonKernel,moistPythonKernel};
})(typeof self==='undefined'?globalThis:self);
