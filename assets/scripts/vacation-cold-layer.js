/* Q/Theta equivalent-layer HLLE operator. This is relative engineering momentum, not atmospheric momentum. */
(function(root){
 'use strict';
 const THETA=2.5,G=9.81*THETA/300,DRY=1e-8,KEYS=['h','q','px','py'];
 const vector=()=>({x:0,y:0}),add=(a,x,y)=>{a.x+=x;a.y+=y;};
 function inventory(s,g){let x=0,y=0;for(let k=0;k<g.n;k++){x+=s.px[k]*g.area;y+=s.py[k]*g.area;}return {x,y};}
 function initialLedger(s,g){return {initial:inventory(s,g),boundaryAdvection:vector(),boundaryPressure:vector(),terrainImpulse:vector(),source:vector(),decayRemoval:vector(),dampingRemoval:vector(),dryRemoval:vector(),roundoffH:0,roundoffQ:0,transportActivity:0,sourceActivity:0,definition:'Integral(P dA), m4/s; equivalent relative layer momentum. External ambient wind and prescribed terrain are not a closed atmospheric momentum/energy system.'};}
 function audit(s,g,b){const actual=inventory(s,g),expected={};for(const key of ['x','y'])expected[key]=b.initial[key]-b.boundaryAdvection[key]-b.boundaryPressure[key]+b.terrainImpulse[key]+b.source[key]-b.decayRemoval[key]-b.dampingRemoval[key]-b.dryRemoval[key];return {inventory:actual,expected,residual:{x:actual.x-expected.x,y:actual.y-expected.y},ledger:b};}
 class Solver{
  constructor(grid,z,u,v,options={}){this.g=grid;this.z=z;this.u=u;this.v=v;this.options=options;this.backend=options.backend||null;this.buffers=new Map();this.counters={rhs:0,faces:0,zeroFaces:0,zeroAdvances:0,bufferAllocations:0,bufferBytes:0,temporaryFaceObjects:0};}
  buffer(key,n){let a=this.buffers.get(key);if(!a||a.length!==n){a=new Float64Array(n);this.buffers.set(key,a);this.counters.bufferAllocations++;this.counters.bufferBytes+=n*8;}return a;}
  state(prefix){return Object.fromEntries(KEYS.map(k=>[k,this.buffer(prefix+k,this.g.n)]));}
  sample(s,k,zGhost=0){if(k<0)return {h:0,q:0,px:0,py:0,A:0,vx:0,vy:0,p:0,z:zGhost};const A=s.q[k]/THETA,vx=A>=DRY?s.px[k]/A:0,vy=A>=DRY?s.py[k]/A:0;return {h:s.h[k],q:s.q[k],px:A>=DRY?s.px[k]:0,py:A>=DRY?s.py[k]:0,A,vx,vy,p:.5*G*A*A,z:this.z[k]};}
  isEmpty(s){for(let k=0;k<this.g.n;k++)if(s.h[k]!==0||s.q[k]!==0||s.px[k]!==0||s.py[k]!==0)return false;return true;}
  sampleInto(s,k,zGhost,out){if(k<0){out.fill(0);out[8]=zGhost;return;}const A=s.q[k]/THETA;out[0]=s.h[k];out[1]=s.q[k];out[2]=A>=DRY?s.px[k]:0;out[3]=A>=DRY?s.py[k]:0;out[4]=A;out[5]=A>=DRY?s.px[k]/A:0;out[6]=A>=DRY?s.py[k]/A:0;out[7]=.5*G*A*A;out[8]=this.z[k];}
  reconstructInto(src,out,z){const A=Math.max(0,src[4]+src[8]-z),ratio=src[4]>0?A/src[4]:1;out[0]=src[0]*ratio;out[1]=THETA*A;out[2]=src[2]*ratio;out[3]=src[3]*ratio;out[4]=A;out[5]=src[5];out[6]=src[6];out[7]=.5*G*A*A;out[8]=src[8];}
  *rhs(s,prefix='rhs'){
   if(this.backend)return yield*this.backend.coldRhs(this,s,prefix);
   this.counters.rhs++;const g=this.g,out=this.state(prefix),rates=this.buffer(prefix+'rates',g.n);for(const a of Object.values(out))a.fill(0);rates.fill(0);
   const nxfaces=(g.nx+1)*g.ny,nyfaces=g.nx*(g.ny+1),faces={};for(const [name,n]of Object.entries({u:nxfaces,v:nyfaces,relativeU:nxfaces,relativeV:nyfaces,sLX:nxfaces,sRX:nxfaces,sLY:nyfaces,sRY:nyfaces})){faces[name]=this.buffer(prefix+name,n);faces[name].fill(0);}
   const budget={volumeOut:0,heatOut:0,boundaryAdvection:vector(),boundaryPressure:vector(),terrainImpulse:vector(),momentumActivityRate:0};let work=0;
   const L=this.buffer('scratchL',9),R=this.buffer('scratchR',9),a=this.buffer('scratchA',9),b=this.buffer('scratchB',9);
   const face=(l,r,wind,axis,index)=>{
    this.counters.faces++;
    const emptyL=l<0||(s.h[l]===0&&s.q[l]===0&&s.px[l]===0&&s.py[l]===0),emptyR=r<0||(s.h[r]===0&&s.q[r]===0&&s.px[r]===0&&s.py[r]===0),wall=this.options.boundary==='closed'&&(l<0||r<0),normal=axis+2;
    if(emptyL&&emptyR){this.counters.zeroFaces++;const lo=wall?-Math.abs(wind):wind,hi=wall?Math.abs(wind):wind;faces[axis===0?'u':'v'][index]=wind;faces[axis===0?'sLX':'sLY'][index]=lo;faces[axis===0?'sRX':'sRY'][index]=hi;if(l>=0)rates[l]+=Math.max(hi,0)/g.dx;if(r>=0)rates[r]+=Math.max(-lo,0)/g.dx;return;}
    this.sampleInto(s,l,r>=0?this.z[r]:0,L);this.sampleInto(s,r,l>=0?this.z[l]:0,R);
    if(wall){const real=l>=0?L:R,ghost=l<0?L:R;ghost.set(real);ghost[axis+5]=-real[axis+5]-2*wind;ghost[normal]=ghost[4]*ghost[axis+5];}
    const z=Math.max(L[8],R[8]);this.reconstructInto(L,a,z);this.reconstructInto(R,b,z);
    const unL=wind+a[axis+5],unR=wind+b[axis+5],cL=Math.sqrt(G*a[4]),cR=Math.sqrt(G*b[4]);let sL=Math.min(unL-cL,unR-cR),sR=Math.max(unL+cL,unR+cR);if(a[4]>0&&b[4]===0){sL=unL-cL;sR=unL+2*cL;}else if(b[4]>0&&a[4]===0){sL=unR-2*cR;sR=unR+cR;}
    const vn=a[4]>=DRY&&b[4]>=DRY?(a[axis+5]+b[axis+5])*.5:a[4]>=DRY?a[axis+5]:b[4]>=DRY?b[axis+5]:0;
    faces[axis===0?'u':'v'][index]=wind+vn;faces[axis===0?'relativeU':'relativeV'][index]=vn;faces[axis===0?'sLX':'sLY'][index]=sL;faces[axis===0?'sRX':'sRY'][index]=sR;
    const pressure=sL>=0?a[7]:sR<=0?b[7]:sR>sL?(sR*a[7]-sL*b[7])/(sR-sL):0;
    for(let componentIndex=0;componentIndex<4;componentIndex++){const key=KEYS[componentIndex],fl=a[componentIndex]*unL,fr=b[componentIndex]*unR,adv=sL>=0?fl:sR<=0?fr:sR>sL?(sR*fl-sL*fr+sL*sR*(b[componentIndex]-a[componentIndex]))/(sR-sL):0,isNormal=componentIndex===normal,F=adv+(isNormal?pressure:0),leftF=F+(isNormal?L[7]-a[7]:0),rightF=F+(isNormal?R[7]-b[7]:0);
     if(l>=0)out[key][l]-=leftF/g.dx;if(r>=0)out[key][r]+=rightF/g.dx;
     if(componentIndex===0){if(l<0)budget.volumeOut-=F*g.dx;if(r<0)budget.volumeOut+=F*g.dx;}if(componentIndex===1){if(l<0)budget.heatOut-=F*g.dx;if(r<0)budget.heatOut+=F*g.dx;}
     if(componentIndex>=2){budget.momentumActivityRate+=(Math.abs(adv)+(isNormal?Math.abs(pressure)+Math.abs(L[7]-a[7])+Math.abs(R[7]-b[7]):0))*g.dx;const component=componentIndex===2?'x':'y';if(l<0){budget.boundaryAdvection[component]-=adv*g.dx;budget.boundaryPressure[component]-=(isNormal?pressure:0)*g.dx;}if(r<0){budget.boundaryAdvection[component]+=adv*g.dx;budget.boundaryPressure[component]+=(isNormal?pressure:0)*g.dx;}budget.terrainImpulse[component]+=((r>=0&&isNormal?R[7]-b[7]:0)-(l>=0&&isNormal?L[7]-a[7]:0))*g.dx;}
    }
    if(l>=0)rates[l]+=Math.max(sR,0)/g.dx;if(r>=0)rates[r]+=Math.max(-sL,0)/g.dx;
   };
   const periodic=this.options.boundary==='periodic';
   for(let j=0;j<g.ny;j++){for(let i=0;i<=(periodic?g.nx-1:g.nx);i++){face(i?j*g.nx+i-1:periodic?j*g.nx+g.nx-1:-1,i<g.nx?j*g.nx+i:-1,this.u[j*(g.nx+1)+i],0,j*(g.nx+1)+i);if(++work%1024===0)yield;}if(j%8===7)yield;}
   for(let j=0;j<=(periodic?g.ny-1:g.ny);j++){for(let i=0;i<g.nx;i++){face(j?(j-1)*g.nx+i:periodic?(g.ny-1)*g.nx+i:-1,j<g.ny?j*g.nx+i:-1,this.v[j*g.nx+i],1,j*g.nx+i);if(++work%1024===0)yield;}if(j%8===7)yield;}
   if(periodic){for(let j=0;j<g.ny;j++)for(const key of ['u','relativeU','sLX','sRX'])faces[key][j*(g.nx+1)+g.nx]=faces[key][j*(g.nx+1)];for(let i=0;i<g.nx;i++)for(const key of ['v','relativeV','sLY','sRY'])faces[key][g.ny*g.nx+i]=faces[key][i];}
   let rate=0;for(let j=0;j<g.ny;j++)for(let i=0;i<g.nx;i++){const k=j*g.nx+i,A=s.q[k]/THETA,c=Math.sqrt(G*Math.max(A,0)),vx=A>=DRY?s.px[k]/A:0,vy=A>=DRY?s.py[k]/A:0,ux=.5*(this.u[j*(g.nx+1)+i]+this.u[j*(g.nx+1)+i+1])+vx,uy=.5*(this.v[j*g.nx+i]+this.v[(j+1)*g.nx+i])+vy;rate=Math.max(rate,rates[k],(Math.abs(ux)+c+Math.abs(uy)+c)/g.dx);}
   return {out,faces,rate,budget};
  }
  valid(s){for(let k=0;k<this.g.n;k++){const h=s.h[k],q=s.q[k];if(!Number.isFinite(h)||!Number.isFinite(q)||!Number.isFinite(s.px[k])||!Number.isFinite(s.py[k])||h< -1e-10||q< -1e-10||q-THETA*h>1e-9)return false;}return true;}
  clean(s,ledger){let rh=0,rq=0;for(let k=0;k<this.g.n;k++){const h=Math.max(0,s.h[k]),q=Math.max(0,Math.min(s.q[k],THETA*h));rh+=h-s.h[k];rq+=q-s.q[k];s.h[k]=h;s.q[k]=q;if(q/THETA<DRY){add(ledger.dryRemoval,s.px[k]*this.g.area,s.py[k]*this.g.area);s.px[k]=0;s.py[k]=0;}}ledger.roundoffH+=rh*this.g.area;ledger.roundoffQ+=rq*this.g.area;return {h:rh*this.g.area,q:rq*this.g.area};}
  *advance(s,duration,ledger){
   if(this.isEmpty(s)){this.counters.zeroAdvances++;for(const key of KEYS)s[key].fill(0);return {volumeOut:0,heatOut:0,roundoffH:0,roundoffQ:0,substeps:0,rejected:0,maxCFL:0,empty:true};}
   if(!this.valid(s))throw Error('惯性冷层初态不合法');const initialRound=this.clean(s,ledger),summary={volumeOut:0,heatOut:0,roundoffH:initialRound.h,roundoffQ:initialRound.q,substeps:0,rejected:0,maxCFL:0};let left=duration;
   while(left>1e-9){const a=yield*this.rhs(s,'stageA'),stage=this.state('stage'),result=this.state('result');let dt=Math.min(left,a.rate>0?.4/a.rate:left),b,okay=false;
    for(let attempt=0;attempt<30;attempt++){if(this.backend)yield*this.backend.vector(s,a.out,stage,this.g.n,dt);else for(const key of KEYS)for(let k=0;k<this.g.n;k++)stage[key][k]=s[key][k]+dt*a.out[key][k];if(this.valid(stage)){b=yield*this.rhs(stage,'stageB');if(dt*b.rate<=.4+1e-12){if(this.backend)yield*this.backend.vector(s,b.out,result,this.g.n,dt,stage);else for(const key of KEYS)for(let k=0;k<this.g.n;k++)result[key][k]=.5*(s[key][k]+stage[key][k]+dt*b.out[key][k]);if(this.valid(result)){okay=true;break;}}}summary.rejected++;dt*=.5;yield;}
    if(!okay)throw Error('惯性冷层 RK/CFL 正性子步无法收敛');for(const key of KEYS)s[key].set(result[key]);const round=this.clean(s,ledger);summary.roundoffH+=round.h;summary.roundoffQ+=round.q;
    for(const stage of [a,b]){const w=.5*dt;summary.volumeOut+=w*stage.budget.volumeOut;summary.heatOut+=w*stage.budget.heatOut;ledger.transportActivity+=w*stage.budget.momentumActivityRate;for(const name of ['boundaryAdvection','boundaryPressure','terrainImpulse'])add(ledger[name],w*stage.budget[name].x,w*stage.budget[name].y);}
    summary.maxCFL=Math.max(summary.maxCFL,dt*a.rate,dt*b.rate);summary.substeps++;left-=dt;yield;
   }return summary;
  }
 }
 function mechanicalEnergy(s,g,z){let e=0;for(let k=0;k<g.n;k++){const A=s.q[k]/THETA;e+=(A>=DRY?.5*(s.px[k]**2+s.py[k]**2)/A:0)+.5*G*A*A+G*A*z[k];}return e*g.area;}
 const api={THETA,G,DRY,Solver,initialLedger,inventory,audit,mechanicalEnergy};root.VacationColdLayer=api;if(typeof module!=='undefined')module.exports=api;
})(typeof self!=='undefined'?self:globalThis);
