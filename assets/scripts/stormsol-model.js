/* Reduced spring squall-line model. Distances in km, rain and vapour in mm,
 * cold pool in K, time in seconds. Arrays use cell-centred south-up rows. */
(function(root){
'use strict';
const WIDTH=1400, HEIGHT=770, DT=600, BOUNDS=[104.3,19.8,118,26.7];
const LEVELS=[30,150,350,650,1000,1500,2200,3200,4500,6000,8000,10500,13500,16500];
const KM_LON=111.195*Math.cos(23.25*Math.PI/180);
const clamp=(v,lo=0,hi=1)=>Math.max(lo,Math.min(hi,v));
function mesh(dx){
  const nx=WIDTH/dx,ny=HEIGHT/dx,dlon=(BOUNDS[2]-BOUNDS[0])/nx,dlat=(BOUNDS[3]-BOUNDS[1])/ny;
  return {nx,ny,nominal_km:dx,dlon,dlat,cellCentered:true,
    west:BOUNDS[0]+dlon/2,south:BOUNDS[1]+dlat/2,z_agl_m:LEVELS};
}
const grid=mesh(5), forcing=mesh(2.5), product=mesh(2), ledger=mesh(1);
function index(g,x,y){return clamp(Math.floor(y/g.nominal_km),0,g.ny-1)*g.nx+clamp(Math.floor(x/g.nominal_km),0,g.nx-1);}
const array=g=>new Float32Array(g.nx*g.ny);
function stream(seed){
  let state=seed>>>0;
  return ()=>{state=(state+0x6d2b79f5)>>>0;let n=Math.imul(state^(state>>>15),1|state);
    n^=n+Math.imul(n^(n>>>7),61|n);return ((n^(n>>>14))>>>0)/4294967296;};
}
function environment(seed){
  const r=stream(seed^0x297afeb3),direction=stream(seed^0x71df42b9);
  const env={cloudAngle:(direction()-.4)*.55,lowTurn:(direction()-.18)*1.42,month:3+Math.floor(3*r()),moisture:.85+.35*r(),jet:.7+.7*r(),shear:.65+.75*r(),
    trough:.5+.9*r(),reservoir:.65+.75*r(),phase:r()*Math.PI*2,troughLon:87+4*r(),troughLat:16+3*r(),frontStart:790+80*r(),
    pulses:Array.from({length:8},(_,d)=>({x:170+410*r(),y:190+205*r(),start:Math.floor(d/2)*24+(d%2)*12+1+5*r(),duration:5+3*r(),tilt:.25+.5*r()}))};
  // Seed the width and embedded wind-speed anomalies of the low-level inflow.
  // These are correlated air streams, not line endpoints or radar segments.
  const jet=stream(seed^0xb7d24c91);
  for(const pulse of env.pulses){
    pulse.inflowWidth=(62+108*jet())*Math.sqrt(env.jet*env.moisture);
    pulse.streams=[];
    for(let y=-120+jet()*45;y<HEIGHT+160;y+=37+38*jet())
      pulse.streams.push({y,width:10+11*jet(),speed:.68+.60*jet(),drift:1+2*jet()});
  }
  // Moist inflow corridors along the synoptic boundary have a finite
  // fetch and move along the front with the low-level flow.
  const frontal=stream(seed^0x1488ae35);
  env.frontalStreams=[];
  for(let x=-150;x<WIDTH+130;x+=55+85*frontal())
    env.frontalStreams.push({x,width:14+23*frontal(),strength:.55+.55*frontal()});
  return env;
}
// Low-level inflow maxima slide along the convergence zone rather than
// appearing independently each frame. Lower-speed air between them still feeds it.
function insetFlow(pulse,y,age){
  let stream=0;
  for(const lane of pulse.streams){
    const d=(y-lane.y-age*lane.drift)/lane.width;
    if(Math.abs(d)<3)stream+=lane.speed*Math.exp(-.5*d*d);
  }
  return Math.min(1.3,stream);
}
function convergenceEnvelope(pulse,y){
  return Math.exp(-.5*((y-pulse.y)/pulse.inflowWidth)**2);
}
// Cloud steering and radar diagnostics share the same trough-relative wind.
function wind(p,x,y,t,z,coldAir,height,axis){
  const lon=BOUNDS[0]+x/KM_LON,lat=BOUNDS[1]+y/111.195;
  const trough=Math.exp(-(((lon-p.troughLon-18)/13)**2+((lat-p.troughLat-6)/8)**2))*p.trough;
  const wave=Math.sin(x/210+t/16+p.phase);
  const low=Math.exp(-z/1850),jet=Math.exp(-((z-950)**2)/900000);
  const nocturnal=1+.16*Math.cos((t+5)*Math.PI/12);
  const drag=1-.4*low*clamp(height/800);
  const u=drag*((10+z*.0013)*p.shear+1.5*wave+trough+(6*jet*nocturnal-6*low)*p.jet-5*coldAir*low);
  const v=drag*(1+wave+2*trough+8*p.jet*jet*nocturnal-10*coldAir*low);
  const angle=p.cloudAngle+p.lowTurn*Math.exp(-z/2400);
  const background=axis==='u'?u*Math.cos(angle)-v*Math.sin(angle):u*Math.sin(angle)+v*Math.cos(angle);
  // Continental cold advection is earth-relative; do not rotate the northerly
  // together with the prefrontal hodograph. The cold wedge is shallow.
  const mix=clamp((coldAir-.18)/.64)*clamp((2700-z)/1500);
  return background*(1-mix)+mix*drag*(axis==='u'?1.3*wave-2:-5.5-3*p.reservoir);
}
// Local hodograph: directional turning and bulk shear separately influence
// whether a storm can keep its inflow separate from the precipitation shaft.
function organization(p,x,y,t,air,z){
  const u0=wind(p,x,y,t,400,air,z,'u'),v0=wind(p,x,y,t,400,air,z,'v');
  const u6=wind(p,x,y,t,6000,air,z,'u'),v6=wind(p,x,y,t,6000,air,z,'v');
  const turn=Math.atan2(v0*u6-u0*v6,u0*u6+v0*v6),shear=Math.hypot(u6-u0,v6-v0);
  return clamp((turn-.62)/.53)*clamp((shear-6)/8);

}
// Integrate positive buoyancy of surface and elevated source parcels.
function airTemperature(surface,stable,z){
  return surface-.00640*Math.min(z,11500)-.0008*Math.max(z-11500,0)+stable*(1-Math.exp(-z/800));
}
const profileHeights=[0,800,1500,3000,5000,8000,11000,14000];
function parcelEnergy(surface,dew,stable){
  let best=0;
  for(const start of [0,800]){
    const origin=airTemperature(surface,stable,start);
    const lcl=125*Math.max(.1,origin-(dew-.0035*start));
    let cape=0,lastB=0,previous=start;
    for(const z of profileHeights){
      if(z<=start)continue;
      const dz=z-start,parcel=origin-.0098*Math.min(dz,lcl)-.0057*Math.max(0,dz-lcl);
      const env=airTemperature(surface,stable,z),b=9.81*(parcel-env)/(273.15+env);
      cape+=(Math.max(0,lastB)+Math.max(0,b))*.5*(z-previous);previous=z;lastB=b;
    }
    best=Math.max(best,cape);
  }
  return best;
}
// Negative buoyancy work (J/kg) below free convection of the surface
// parcel. Split at the LCL to retain the dry ascent in shallow moist layers.
function surfaceInhibition(surface,dew,stable){
  const lcl=125*Math.max(.1,surface-dew);
  let work=0,last=0,previous=0;
  for(let n=0;n<=30;n++){
    const z=n===0?lcl:lcl+n*200;
    const env=airTemperature(surface,stable,z);
    const parcel=surface-.0098*lcl-.0057*(z-lcl);
    const deficit=9.81*(env-parcel)/(273.15+env);
    if(deficit<=0){
      if(last>0)work+=.5*last*(z-previous)*last/(last-deficit);
      break;
    }
    work+=.5*(last+deficit)*(z-previous);last=deficit;previous=z;
  }
  return work;
}
// 10-minute primary step; only transport/settling is split internally.
class Model {
  constructor(seed,terrain){
    if(!(terrain instanceof Uint16Array)||terrain.length!==forcing.nx*forcing.ny)throw Error('Sol 地形尺寸错误');
    this.terrain=terrain;this.config=environment(seed);this.rng=stream(seed^0xe291c445);this.steps=0;
    this.overturn=array(grid);this.water=new Float64Array(grid.nx*grid.ny);this.transport=new Float64Array(this.water.length);this.energy=array(grid);this.air=array(grid);this.temp=array(grid);this.dew=array(grid);
    this.cold=array(forcing);this.poolDepth=array(forcing);this.poolHeat=array(forcing);
    this.poolU=array(forcing);this.poolV=array(forcing);this.fluxX=array(forcing);this.fluxY=array(forcing);
    this.donorScale=array(forcing);this.dH=array(forcing);this.dQ=array(forcing);this.head=array(forcing);this.ice=array(product);this.nextIce=array(product);
    this.stormU=array(product);this.stormV=array(product);this.convRate=array(product);this.poolInput=array(forcing);this.rate=array(product);this.total=array(ledger);this.hour=array(ledger);
    this.last5=array(ledger);this.history=Array.from({length:6},()=>array(ledger));this.cells=[];
    this.terrainEnv=array(grid);this.fluxIn=0;this.exportedIce=0;this.rainMass=0;this.initialMass=0;this.front=new Float32Array(grid.nx);this.ridge=new Float32Array(grid.nx);
    this.frontLift=new Float32Array(forcing.nx);this.frontHead=array(forcing);
    this.boundaries=new Map();this.births={warm:0,front:0,outflow:0};
    for(let col=0;col<grid.nx;col++){
      this.front[col]=this.config.frontStart+22*Math.sin(col/35+this.config.phase);
      let highest=-1;
      for(let y=510;y<=680;y+=5){
        const z=terrain[index(forcing,(col+.5)*5,y)];
        if(z>highest){highest=z;this.ridge[col]=y;}
      }
    }
    for(let i=0;i<this.water.length;i++){
      this.terrainEnv[i]=terrain[index(forcing,(i%grid.nx+.5)*5,(Math.floor(i/grid.nx)+.5)*5)];
      this.water[i]=36*this.config.moisture-3*clamp(((i/grid.nx|0)*5-330)/350);this.energy[i]=1100*this.config.moisture;
      this.initialMass+=this.water[i]*25;
    }
    this.environmentStep(0);
  }
  environmentStep(seconds){
    const p=this.config,t=this.steps/6,solar=Math.sin((t+2)*Math.PI/12);
    const previous=this.front.slice();
    for(let col=0;col<grid.nx;col++){
      const x=(col+.5)*5,height=this.terrain[index(forcing,x,previous[col])];
      const crossed=clamp((this.ridge[col]-previous[col])/65);
      const barrier=this.terrain[index(forcing,x,previous[col]-15)]-height;
      const passage=clamp(1-barrier/1150,.45,1.45);
      const speed=passage*(2.20+2.45*crossed)*(.66+.36*p.reservoir)/(1+.00034*height+.085*p.jet);
      const bend=(previous[Math.max(0,col-1)]+previous[Math.min(grid.nx-1,col+1)]-2*previous[col])*.2;
      const frontY=this.front[col]=previous[col]+(bend-speed*seconds/1000)*(seconds>0);
      const wave=Math.sin(x/150+p.phase+t/18);
      for(let row=0;row<grid.ny;row++){
        const y=(row+.5)*5,i=row*grid.nx+col,z=this.terrainEnv[i];
        const coldAir=clamp(.5+(y-frontY)/70),cool=this.cold[index(forcing,x,y)];
        this.air[i]=coldAir;
        const target=clamp(38*p.moisture+4*wave-3*clamp((y-330)/350)-14*coldAir-.006*z,10,54);
        const before=this.water[i];
        this.water[i]+=(target-before)*seconds/24000;this.fluxIn+=(this.water[i]-before)*25;
        this.temp[i]=25+(p.month-4)*1.3+2.8*solar+.75*wave-.0058*z-7*coldAir-cool;
        this.dew[i]=Math.min(this.temp[i]-.3,8+.34*this.water[i]-.002*z);
        // Convective overturn outlasts the shallow temperature anomaly. A
        // mature cold layer can stabilize previously un-rained-on neighbours.
        const k=index(forcing,x,y),pool=clamp((this.poolDepth[k]-40)/330)*clamp(cool/2);
        const wake=this.overturn[i]=Math.max(this.overturn[i]*Math.exp(-seconds/25200),.86*pool);
        const capacity=(1-.84*wake)*parcelEnergy(this.temp[i],this.dew[i],7*coldAir+cool)*clamp(1-.85*coldAir);
        if(seconds===0)this.energy[i]=capacity;
        else this.energy[i]+=(capacity-this.energy[i])*seconds/(capacity<this.energy[i]?1800:18000+25200*wake);
      }
    }
  }
  transportWater(){
    // Two upwind passes, positive weights at the fastest sampled low-level jet.
    const p=this.config,angle=p.cloudAngle+p.lowTurn*.7,u=4+4*p.jet,v=2+3*p.jet;
    const vx=u*Math.cos(angle)-v*Math.sin(angle),vy=u*Math.sin(angle)+v*Math.cos(angle);
    const nx=grid.nx,ny=grid.ny;
    // Integrate face fluxes, including drier northerly inflow at the open
    // boundary. Each internal face has a single donor shared by both cells.
    for(let pass=0;pass<2;pass++){
      const q=this.water,next=this.transport;next.set(q);
      for(let i=0;i<q.length;i++){
        const x=i%nx,y=Math.floor(i/nx),east=x+1<nx,north=y+1<ny;
        const air=this.air[i],cx=clamp(((east?(air+this.air[i+1])*.5:air)-.18)/.64);
        const cy=clamp(((north?(air+this.air[i+nx])*.5:air)-.18)/.64);
        const u=(vx*(1-cx)-2*cx)*.06,v=(vy*(1-cy)-6.5*cy)*.06;
        const fx=u*(u>=0?q[i]:east?q[i+1]:30*p.moisture);
        const fy=v*(v>=0?q[i]:north?q[i+nx]:25*p.moisture);
        next[i]-=fx+fy;
        if(east)next[i+1]+=fx;else this.fluxIn-=25*fx;
        if(north)next[i+nx]+=fy;else this.fluxIn-=25*fy;
        if(!x||!y){
          const f=clamp((air-.18)/.64);
          if(!x){const w=.06*(vx*(1-f)-2*f),inlet=w*(w>=0?36*p.moisture:q[i]);next[i]+=inlet;this.fluxIn+=25*inlet;}
          if(!y){const w=.06*(vy*(1-f)-6.5*f),inlet=w*(w>=0?38*p.moisture:q[i]);next[i]+=inlet;this.fluxIn+=25*inlet;}
        }
      }
      [this.water,this.transport]=[next,q];
    }
  }
  coldInterior(k){
    return this.poolDepth[k]>=100 && this.cold[k]>=.65;
  }
  warmFraction(k){
    const load=Math.min(this.poolDepth[k]/100,this.cold[k]/.65);
    const f=clamp((1-load)/.65);return f*f*(3-2*f);
  }
  deepSupply(i){
    // CIN / cold-air intrusion and accessible energy bound the plume itself.
    // Strong mechanical ascent in the northern air mass cannot bypass this.
    return clamp((this.energy[i]-200)/1050)*clamp((.48-this.air[i])/.36);
  }
  overturnColumn(i,mm){
    // mm of condensed water per unit environment-cell area. Spend a fraction
    // of the remaining buoyancy, and retain the mixed layer after rain stops.
    const fraction=-Math.expm1(-mm/19);
    this.energy[i]*=1-.90*fraction;
    this.overturn[i]+=(1-this.overturn[i])*fraction;
  }
  condensation(requested,i,k,hours,groundIndex=i){
    // Shared 2 km updraft budget. Overlapping plumes and frontal lifting
    // must not each spend the same weak local buoyancy independently.
    const e=Math.min(this.energy[groundIndex],this.energy[i]);
    const ceiling=155*clamp((e-200)/1350)**1.3*clamp((.48-this.air[groundIndex])/.28);
    return Math.min(requested,this.water[i]*25/4,Math.max(0,ceiling-this.rate[k])*hours/.76);
  }
  // Test the undisturbed inflow, not CAPE already spent under the rain shaft.
  tryBirth(x,y,lift,kind){
    if(x<8||y<8||x>=WIDTH-12||y>=HEIGHT-6)return;
    const i=index(grid,x+8,y-5),k=index(forcing,x,y),pool=this.cold[k];
    const upslope=(this.terrain[k]-this.terrain[index(forcing,x-5,y-3)])/250;
    const inhibition=.34+.09*(this.temp[i]-this.dew[i])+.22*pool;
    if(this.coldInterior(k)||this.overturn[index(grid,x,y)]>.57||this.deepSupply(i)<.09||this.air[i]>.3||this.air[index(grid,x,y)]>.36||pool>2.0||this.energy[i]<290||lift+.22*clamp(upslope)<=inhibition)return;
    const org=organization(this.config,x,y,this.steps/6,this.air[i],this.terrain[k]);
    // Fast right-moving updrafts ingest air over a wider footprint; do not
    // spawn a second core inside that inflow. Straight profiles leave room
    // for repeated lifting on adjacent segments of the same gust front.
    if(this.rng()>clamp(this.energy[i]/1700,.12,.9)*.75*(1-org*(kind==='outflow' ? .96 : .78))||
       this.cells.some(c=>Math.hypot((c.x-x)/(13+41*org),(c.y-y)/(11+29*org))<1&&c.age<c.life-20))return;
    const r=this.rng;
    this.cells.push({kind,x,y,radius:5+3*r(),age:0,life:(kind==='outflow'?45:100)+55*r()+75*org,
      strength:0,spin:0,org,amplitude:.78+.42*r()});
    this.births[kind]++;
  }
  initiate(){
    const t=this.steps/6,p=this.config,pulse=p.pulses[Math.min(7,Math.floor(t/12))],r=this.rng;
    for(let j=0;j<16;j++){
      const x=r()*WIDTH,col=Math.floor(x/5),y=this.front[col]-9-r()*28;
      if(this.front[col]>HEIGHT||this.frontHead[index(forcing,x,y)]<.10)continue;
      this.tryBirth(x,y,2.3*this.frontHead[index(forcing,x,y)],'front');
    }
    const age=t-pulse.start;
    if(age>=0&&age<pulse.duration){
      // A moving, finite prefrontal convergence ribbon seeds a broken line.
      // A frontal outflow elsewhere cannot turn this warm-sector forcing off.
      for(let j=0;j<22;j++){
        const y=r()*HEIGHT,along=y-pulse.y;
        const inflow=convergenceEnvelope(pulse,y)*(.48+.74*insetFlow(pulse,y,age));
        if(r()>inflow)continue;
        const line=this.boundaries.get(pulse);
        const x=(line?line.x[Math.floor(y/2.5)]:pulse.x+age*23+along*pulse.tilt)+(r()-.5)*12;
        this.tryBirth(x,y,1.9*p.trough*inflow*Math.sin(Math.PI*age/pulse.duration),'warm');
      }
    }
    // Sample the *advancing* gust front. Interior holes and stalled
    // temperature gradients cannot act as new independent storm sources.
    const nx=forcing.nx,ny=forcing.ny;
    for(let by=4;by<ny-4;by+=8)for(let bx=5;bx<nx-10;bx+=12){
      let weight=0,selected=-1;
      for(let y=by;y<Math.min(ny-4,by+8);y+=2)for(let x=bx;x<Math.min(nx-10,bx+12);x+=2){
        const k=y*nx+x,a=this.head[k];
        if(a<.21||this.poolU[k-2]<1.5||this.cold[k-4]<.55||this.cold[k+4]>.40)continue;
        const xx=(x+.5)*2.5,yy=(y+.5)*2.5,i=index(grid,xx+12,yy),site=index(grid,xx,yy);
        if(this.overturn[site]>.22||this.overturn[i]>.20||this.deepSupply(i)<.32)continue;
        const w=a*(1-this.overturn[i])*clamp(this.poolU[k-2]/8);
        weight+=w;if(r()*weight<w)selected=k;
      }
      if(selected>=0&&r()<.28*clamp(weight/2)){
        const x=(selected%nx+.5)*2.5,y=((selected/nx|0)+.5)*2.5;
        this.tryBirth(x,y,1.25+this.head[selected], 'outflow');
      }
    }
  }
  rainHalf(minutes){
    const p=this.config,hours=minutes/60,stepMass=this.history[this.steps%6];
    this.last5.fill(0);this.rate.fill(0);this.convRate.fill(0);this.stormU.fill(0);this.stormV.fill(0);this.nextIce.fill(0);
    for(const c of this.cells){
      const env=index(grid,c.x,c.y),frontDistance=this.front[Math.min(grid.nx-1,Math.floor(c.x/5))]-c.y;
      const attached=Math.exp(-((frontDistance/32)**2));
      const u=wind(p,c.x,c.y,this.steps/6,4500,this.air[env],this.terrainEnv[env],'u')*.82;
      const v=wind(p,c.x,c.y,this.steps/6,4500,this.air[env],this.terrainEnv[env],'v')*(1-attached)-3.5*p.reservoir*attached;
      const speed=Math.max(1,Math.hypot(u,v)),ex=u/speed,ey=v/speed;
      // Rightward propagation increases as the storm-scale circulation develops.
      c.x+=(u+ey*5.5*c.spin)*minutes*.06;c.y+=(v-ex*5.5*c.spin)*minutes*.06;c.age+=minutes;
      const inletX=c.x+8*ex+ey*(5+8*c.spin),inletY=c.y+8*ey-ex*(5+8*c.spin);
      const intake=index(grid,inletX,inletY),cool=this.cold[index(forcing,inletX,inletY)];
      const feed=clamp(this.energy[intake]/850)*clamp((this.water[intake]-13)/15)*
        clamp(1-this.air[intake]*1.8)*clamp(1-cool/6,.12,1);
      c.spin+=(c.org*clamp(c.strength)*feed-c.spin)*minutes/25;
      const submerged=this.coldInterior(index(forcing,c.x,c.y));
      c.buried=submerged?(c.buried||0)+minutes:0;
      const wakeFeed=1-clamp(this.overturn[intake]/.78);
      c.starved=(submerged||feed*wakeFeed<.15)?(c.starved||0)+minutes:0;
      const target=(submerged?0:c.amplitude)*feed*wakeFeed*(1+.25*c.spin)*clamp(c.age/20)*clamp((c.life-c.age)/30);
      c.strength+=(target-c.strength)*(target>c.strength ? .48 : .22);
      const activity=submerged?0:c.strength;
      if(!activity)continue;
      const radius=c.radius,extent=radius*2.4;
      for(let row=Math.max(0,Math.floor((c.y-extent)/2));row<Math.min(product.ny,(c.y+extent)/2);row++){
        for(let col=Math.max(0,Math.floor((c.x-extent)/2));col<Math.min(product.nx,(c.x+extent)/2);col++){
          const x=col*2+1,y=row*2+1,i=index(grid,x,y),k=row*product.nx+col;
          if(this.coldInterior(index(forcing,x,y))||this.air[i]>=.48)continue;
          const supply=this.deepSupply(i);if(supply<=0)continue;
          const dx=x-c.x,dy=y-c.y;
          const along=(dx*ex+dy*ey)/radius,cross=(-dx*ey+dy*ex)/radius;
          // In veering shear the precipitation footprint fans downshear and
          // curves around the inflow flank. The same circulation feeds Doppler winds.
          const bend=c.spin*.32*clamp(along,-1.6,1.6)**2;
          const d2=(along/(1+.32*c.spin))**2+(cross-bend)**2;
          const swirl=22*c.spin*Math.exp(-.65*(along*along+cross*cross))/radius;
          this.stormU[k]-=dy*swirl;this.stormV[k]+=dx*swirl;
          const demand=hours*140*activity*supply*this.warmFraction(index(forcing,x,y))*Math.exp(-d2)*clamp(this.water[i]/26);
          const condensed=this.condensation(demand,i,k,hours);
          this.water[i]-=condensed*4/25;this.overturnColumn(i,condensed*4/25);
          this.ice[k]+=.24*condensed;this.rate[k]+=.76*condensed/hours;
        }
      }
    }
    this.cells=this.cells.filter(c=>c.buried<20&&c.starved<30&&c.age<c.life&&c.x<WIDTH&&c.y<HEIGHT&&c.y>=0);
    // Subgrid lifting is integrated over the actual 2 km rain area and
    // withdraws real vapour from the warm-side donor column. Downstream rain
    // and evaporation re-enter exactly the same ledgers as discrete plumes.
    for(let y=0;y<product.ny;y++)for(let x=0;x<product.nx;x++){
      const xx=x*2+1,yy=y*2+1,k=y*product.nx+x;
      const gx=clamp(xx/2.5-.5,0,forcing.nx-1.001),gy=clamp(yy/2.5-.5,0,forcing.ny-1.001);
      const ix=Math.floor(gx),iy=Math.floor(gy),j=iy*forcing.nx+ix,f=gx-ix,g=gy-iy,h=this.head;
      const a=((1-g)*((1-f)*h[j]+f*h[j+1])+g*((1-f)*h[j+forcing.nx]+f*h[j+forcing.nx+1]))*
        this.warmFraction(index(forcing,xx,yy));
      if(a<.035||this.coldInterior(index(forcing,xx,yy)))continue;
      const site=index(grid,xx,yy),fk=index(forcing,xx,yy);
      const frontal=this.frontHead[fk]>0 && this.frontHead[fk]>=.95*h[fk];
      const donor=frontal?index(grid,xx,yy-14):index(grid,xx+10,yy+2);
      const demand=hours*85*a*this.deepSupply(donor)*clamp((.47-this.air[index(grid,xx,yy)])/.31)*clamp(this.water[donor]/30);
      const mass=this.condensation(demand,donor,k,hours,index(grid,xx,yy));
      this.water[donor]-=mass*4/25;
      this.overturnColumn(donor,mass*4/25*.45);this.overturnColumn(site,mass*4/25*.55);
      this.rate[k]+=.72*mass/hours;this.ice[k]+=.28*mass;
    }
    this.convRate.set(this.rate);
    // Detrained ice settles more slowly and lags the convective head.
    for(let k=0;k<this.ice.length;k++){
      const ice=this.ice[k];if(!ice)continue;
      const col=k%product.nx,row=Math.floor(k/product.nx);
      const fallout=ice*.09,carry=ice-fallout;
      const rear=clamp(this.cold[index(forcing,col*2+1,row*2+1)]/2);
      if(col>0)this.nextIce[k-1]+=.40*rear*carry;else this.exportedIce+=4*.40*rear*carry;
      this.nextIce[k]+=.38*carry;
      if(col+1<product.nx)this.nextIce[k+1]+=.40*(1-rear)*carry;else this.exportedIce+=4*.40*(1-rear)*carry;
      if(row+1<product.ny)this.nextIce[k+product.nx]+=.22*carry;else this.exportedIce+=4*.22*carry;
      this.rate[k]+=fallout/hours;
    }
    [this.ice,this.nextIce]=[this.nextIce,this.ice];
    for(let k=0;k<this.rate.length;k++){
      if(this.rate[k]<=0)continue;
      const x=(k%product.nx)*2,y=Math.floor(k/product.nx)*2;
      const depth=this.rate[k]*hours,i=index(grid,x+1,y+1);
      const evap=depth*clamp((this.temp[i]-this.dew[i])*.015,0,.22);
      this.water[i]+=evap*4/25;
      // Precipitation loading and evaporatively cooled downdrafts are
      // displaced toward the trailing side of a sheared updraft. Deposit
      // their heat over the actual fractional 2.5 km footprint: nearest-cell
      // deposition between unlike grids creates false holes in the head.
      const conv=this.convRate[k]/Math.max(.01,this.rate[k]);
      const back=conv*(4+5*p.shear);
      const source=index(forcing,x+1,y+1);
      const frontal=this.frontHead[source]>.035 && this.frontHead[source]>=.95*this.head[source];
      const offsetX=frontal?0:-back*Math.cos(p.cloudAngle);
      const offsetY=frontal?back:-back*Math.sin(p.cloudAngle);
      const gx=clamp((x+1+offsetX)/2.5-.5,0,forcing.nx-1.001);
      const gy=clamp((y+1+offsetY)/2.5-.5,0,forcing.ny-1.001);
      const bx=Math.floor(gx),by=Math.floor(gy),tx=gx-bx,ty=gy-by,j=by*forcing.nx+bx,f=evap*4/6.25;
      this.poolInput[j]+=f*(1-tx)*(1-ty);this.poolInput[j+1]+=f*tx*(1-ty);
      this.poolInput[j+forcing.nx]+=f*(1-tx)*ty;this.poolInput[j+forcing.nx+1]+=f*tx*ty;
      const ground=depth-evap;this.rate[k]=ground/hours;this.rainMass+=ground*4;
      // Conservative linear subcell reconstruction. The four 1 km bins
      // average to this 2 km cell's actual landed mass.
      const slopeX=clamp((this.rate[k+(x+2<WIDTH?1:0)]-this.rate[k-(x?1:0)])*hours*.1,-ground*.4,ground*.4);
      const slopeY=clamp((this.rate[k+(y+2<HEIGHT?product.nx:0)]-this.rate[k-(y?product.nx:0)])*hours*.1,-ground*.4,ground*.4);
      for(let dy=0;dy<2;dy++)for(let dx=0;dx<2;dx++){
        const n=(y+dy)*WIDTH+x+dx,amount=ground+(2*dx-1)*slopeX+(2*dy-1)*slopeY;
        this.total[n]+=amount;stepMass[n]+=amount;this.hour[n]+=amount;this.last5[n]=amount;
      }
    }
  }
  advance(){
    const old=this.history[this.steps%6];
    for(let i=0;i<old.length;i++)this.hour[i]=Math.max(0,this.hour[i]-old[i]);
    old.fill(0);this.transportWater();
    // Apply the preceding five minutes of downdraft supply before diagnosing
    // each new set of plumes. The saved cold mask and instantaneous updraft
    // then refer to the same gust front, not opposite ends of a 10-min step.
    this.propagateCold(300);this.poolInput.fill(0);this.environmentStep(DT);
    this.updateHead();this.advanceBoundaries(0);this.frontalAscent();this.initiate();
    this.rainHalf(5);this.propagateCold(300);this.poolInput.fill(0);this.updateHead();this.advanceBoundaries(5);this.frontalAscent();this.rainHalf(5);
    this.steps++;
  }
  propagateCold(seconds=600){
    // A local-inertia shallow layer: h in m, q = h * temperature deficit
    // in K m, velocities live on east/north faces. A pressure gradient can
    // accelerate resting air in ANY direction, independently of cell motion.
    const nx=forcing.nx,n=this.cold.length,h=this.poolDepth,q=this.poolHeat,
      u=this.poolU,v=this.poolV,fx=this.fluxX,fy=this.fluxY,z=this.terrain;
    const p=this.config,dt=75,ratio=dt/2500,buoyancy=9.81/295;
    const bgX=3.4*p.shear*Math.cos(p.cloudAngle),bgY=1.0+3.4*p.shear*Math.sin(p.cloudAngle);
    for(let i=0;i<n;i++){
      const evap=this.poolInput[i];if(!evap)continue;
      // Effective heat deficit from evaporation (K m per mm); distribute
      // over descending and entrained air, rather than injecting a pixel of K.
      const supply=evap*1280,add=supply/(3.5+Math.min(2,evap));
      h[i]+=add;q[i]+=supply;
      if(h[i]>1700){q[i]*=1700/h[i];h[i]=1700;}
    }
    for(let step=0;step<seconds/dt;step++){
      const dh=this.dH,dq=this.dQ,scale=this.donorScale;
      dh.fill(0);dq.fill(0);
      for(let i=0;i<n;i++)this.cold[i]=q[i]/Math.max(55,h[i]);
      for(let i=0;i<n;i++){
        for(let axis=0;axis<2;axis++){
          const velocity=axis?v:u,flux=axis?fy:fx,j=i+(axis?nx:1);
          const edge=axis?j>=n:i%nx===nx-1;
          if(h[i]<.25&&(edge||h[j]<.25)){flux[i]=velocity[i]=0;continue;}
          const hr=edge?h[i]:h[j],rise=edge?0:z[j]-z[i];
          // Hydrostatic face reconstruction: only air above the sill flows.
          const left=Math.max(0,h[i]-Math.max(0,rise)),right=Math.max(0,hr+Math.min(0,rise));
          if(left+right<.1){flux[i]=velocity[i]=0;continue;}
          const cl=this.cold[i],cr=edge?cl:this.cold[j];
          const pressure=buoyancy*(left*cl-right*cr);
          const air=this.air[(i/nx>>1)*grid.nx+((i%nx)>>1)],post=clamp((air-.18)/.64);
          const bg=(axis?bgY:bgX)*(1-post)+(axis?-6.8:-1.6)*post;
          const w=velocity[i]=clamp((velocity[i]+ratio*pressure+dt/2700*bg)/
            (1+dt/2700+dt*.0015*Math.abs(velocity[i])/Math.max(60,(left+right)*.5)),-22,22);
          flux[i]=ratio*(w>=0?w*left:w*right);
          if(edge)flux[i]=Math.max(0,flux[i]); // outward radiation, no ghost source
        }
      }
      for(let i=0;i<n;i++){
        const escape=(i%nx===0?Math.max(0,-u[i]):0)+(i<nx?Math.max(0,-v[i]):0);
        const out=escape*ratio*h[i]+Math.max(0,fx[i])+Math.max(0,fy[i])+
          (i%nx?Math.max(0,-fx[i-1]):0)+(i>=nx?Math.max(0,-fy[i-nx]):0);
        scale[i]=out>h[i]*.85?h[i]*.85/out:1;
      }
      for(let i=0;i<n;i++){
        for(let axis=0;axis<2;axis++){
          const j=i+(axis?nx:1),inside=axis?j<n:i%nx<nx-1;
          if(inside&&(h[i]>1||h[j]>1)){
            const rise=z[j]-z[i],a=.026*Math.max(0,h[i]-Math.max(0,rise)),b=.026*Math.max(0,h[j]+Math.min(0,rise));
            const exchange=a-b,thermal=a*q[i]/Math.max(.001,h[i])-b*q[j]/Math.max(.001,h[j]);
            dh[i]-=exchange;dh[j]+=exchange;dq[i]-=thermal;dq[j]+=thermal;
          }
          const mass=(axis?fy:fx)[i];if(!mass)continue;
          const donor=mass>0?i:j;
          const moved=mass*scale[donor],heat=moved*q[donor]/Math.max(.00001,h[donor]);
          dh[i]-=moved;dq[i]-=heat;
          if(axis?j<n:i%nx<nx-1){dh[j]+=moved;dq[j]+=heat;}
        }
        // Symmetric open west/south edges, without wrapping rows.
        const escape=(i%nx===0?Math.max(0,-u[i]):0)+(i<nx?Math.max(0,-v[i]):0);
        if(escape){const f=escape*ratio*scale[i];dh[i]-=f*h[i];dq[i]-=f*q[i];}
      }
      for(let i=0;i<n;i++){
        const depth=Math.max(0,h[i]+dh[i]);
        // Turbulent entrainment thickens the spreading layer while diluting
        // its temperature deficit; it adds no buoyancy or cold area in dry cells.
        const entrain=depth>2?dt*clamp(depth/65)*clamp((q[i]+dq[i])/Math.max(1,depth)*1.55)*(.008+.004*Math.hypot(u[i]-bgX,v[i]-bgY)):0;
        // Surface heating acts on the base of the layer, not on its
        // whole volume at once. A deep merged pool retains its interior
        // after rain ends; shallow, isolated filaments mix out faster.
        const deep=clamp((depth-50)/270);
        h[i]=depth*(.995+.0015*deep)+entrain*(1-.30*deep);
        q[i]=Math.max(0,q[i]+dq[i])*(.992+.0045*deep);
        if(h[i]<.15){h[i]=q[i]=0;}
      }
    }
    for(let i=0;i<n;i++)this.cold[i]=q[i]/Math.max(55,h[i]);
  }
  frontalAscent(){
    // Follow warm parcels from ahead of the cold wedge. Relief along their
    // inflow path determines how much lift survives passage over a ridge.
    const p=this.config,t=this.steps/6,g=forcing;
    this.frontHead.fill(0);
    for(let col=1;col<g.nx-1;col++){
      const x=(col+.5)*2.5,j=Math.floor(x/5),front=this.front[j];
      if(front>HEIGHT||front<4){this.frontLift[col]=0;continue;}
      const donor=index(grid,x,front-35),height=this.terrainEnv[donor];
      const u=wind(p,x,front-35,t,850,0,height,'u'),v=wind(p,x,front-35,t,850,0,height,'v');
      const slope=(this.front[Math.min(grid.nx-1,j+1)]-this.front[Math.max(0,j-1)])/10;
      const inflow=(v-u*slope)/Math.hypot(1,slope)+3*p.reservoir;
      // Pass air streams through the open boundaries without letting
      // the last stream leave the entire front permanently starved.
      const period=WIDTH+280;
      let moistureFlux=0;
      for(const lane of p.frontalStreams){
        const delta=x-lane.x-t*7;
        const d=(delta-period*Math.round(delta/period))/lane.width;
        if(Math.abs(d)<3)moistureFlux+=lane.strength*Math.exp(-.5*d*d);
      }
      const jetSupply=clamp(moistureFlux);
      const centre=front-clamp(8+.73*inflow+9*jetSupply,9,36);
      const speed=Math.max(1,Math.hypot(u,v)),ux=u/speed,uy=v/speed;
      const siteZ=this.terrain[index(g,x,centre)];
      const upwind=this.terrain[index(g,x-16*ux,centre-16*uy)];
      const crest=Math.max(upwind,this.terrain[index(g,x-8*ux,centre-8*uy)]);
      const cap=surfaceInhibition(this.temp[donor],this.dew[donor],7*this.air[donor]+2*this.overturn[donor]);
      // Mechanical lifting work per kg, with a bounded contribution from
      // forced ascent and a loss from descent behind the upwind crest.
      const work=(.22+.34*jetSupply)*Math.max(0,inflow)**2+
        clamp(.105*(siteZ-upwind)-.14*Math.max(0,crest-siteZ),-130,95);
      const supply=this.deepSupply(donor)*clamp((this.water[donor]-22)/14);
      const target=supply*(.12+.88*jetSupply)*clamp((work-cap)/85);
      const response=target>this.frontLift[col] ? .32 : .60;
      const lift=this.frontLift[col]+=(target-this.frontLift[col])*response;
      const width=3.5+3*lift;
      for(let row=Math.max(0,Math.floor((centre-2*width)/2.5));row<Math.min(g.ny,(centre+2*width)/2.5);row++){
        const k=row*g.nx+col,y=(row+.5)*2.5;
        if(this.coldInterior(k))continue;
        const d=(y-centre)/width;
        const a=lift*Math.exp(-d*d)*this.warmFraction(k);
        this.frontHead[k]=a;this.head[k]=Math.max(this.head[k],a);
      }
    }
  }
  advanceBoundaries(offset){
    // Track the prefrontal surface convergence as interacting 2.5 km
    // segments. Prognose their displacement and updraft mass flux, not
    // reflectivity. Rain/wind/evaporative cooling still use the grid budget.
    const p=this.config,t=this.steps/6+offset/60,n=forcing.ny;
    for(const pulse of p.pulses){
      const age=t-pulse.start;if(age<0)continue;
      let line=this.boundaries.get(pulse);
      if(!line){
        if(age>pulse.duration)continue;
        line={surge:new Float32Array(n),x:new Float32Array(n),lift:new Float32Array(n),nextX:new Float32Array(n),nextLift:new Float32Array(n)};
        for(let y=0;y<n;y++)line.x[y]=pulse.x+((y+.5)*2.5-pulse.y)*pulse.tilt;
        this.boundaries.set(pulse,line);
      }
      const forcingAmplitude=age<pulse.duration?Math.sin(Math.PI*age/pulse.duration):0;
      if(!forcingAmplitude&&!line.lift.some(v=>v>.025)){this.boundaries.delete(pulse);continue;}
      for(let row=0;row<n;row++){
        const y=(row+.5)*2.5,x=line.x[row],state=line.lift[row];
        line.nextX[row]=x;line.nextLift[row]=0;
        if(x<12||x>=WIDTH-22)continue;
        const lane=insetFlow(pulse,y,age);
        const thermal=forcingAmplitude*convergenceEnvelope(pulse,y)*(.43+.9*lane);
        if(thermal<.04&&state<.005&&!(line.lift[row-1]>.05||line.lift[row+1]>.05)){
          // Carry dormant sections with the parent disturbance. Leaving them
          // behind makes long artificial spurs when adjacent sections revive.
          const background=wind(p,x,y,t,4000,0,this.terrain[index(forcing,x,y)],'u');
          const left=line.x[Math.max(0,row-1)],right=line.x[Math.min(n-1,row+1)];
          line.nextX[row]=x+.3*.70*background+.21*(left+right-2*x);
          line.surge[row]*=.91;continue;
        }
        const left=line.x[Math.max(0,row-1)],right=line.x[Math.min(n-1,row+1)];
        const slope=clamp((line.x[Math.min(n-1,row+3)]-line.x[Math.max(0,row-3)])/15,-1.6,1.6);
        const nx=1/Math.hypot(1,slope),ny=-slope*nx;
        const i=index(grid,x+15*nx,y+15*ny),ground=this.terrain[index(forcing,x,y)];
        const normalWind=z=>nx*wind(p,x,y,t,z,this.air[i],ground,'u')+
          ny*wind(p,x,y,t,z,this.air[i],ground,'v');
        const surfaceWind=normalWind(350),deepWind=normalWind(4000);
        const shear=normalWind(3000)-surfaceWind;
        let h=0,content=0,headSpeed=0,rain=0;
        // Sample along the moving segment's normal and tangent. Recent
        // downdrafts and the trailing precipitation provide independent
        // pressure and loading proxies for a lagged rear-inflow response.
        for(const side of [-8,0,8]){
          let heat=0,depth=0,flow=0,loading=0;
          for(const back of [2.5,8,16,28,40]){
            const xx=x-back*nx-side*ny,yy=y-back*ny+side*nx;
            const k=index(forcing,xx,yy),q=index(product,xx,yy);
            if(this.poolHeat[k]>heat){
              heat=this.poolHeat[k];depth=this.poolDepth[k];flow=nx*this.poolU[k]+ny*this.poolV[k];
            }
            loading=Math.max(loading,this.convRate[q]+2*this.ice[q]);
          }
          h+=depth/3;content+=heat/3;headSpeed+=flow/3;rain+=loading/3;
        }
        const gust=Math.sqrt(2*9.81/295*content);
        const focus=.55+.52*clamp(lane);
        const drive=clamp(gust/17)*clamp(rain/58)*10*focus;
        const rear=line.surge[row]+=(drive-line.surge[row])*(drive>line.surge[row] ? .20 : .09);
        const normalSpeed=clamp(.70*deepWind+.30*headSpeed+.22*gust+rear,3,32);
        // Advect the background flow in earth coordinates. Only the excess
        // normal propagation advances the intercept of a tilted front.
        const advect=.70*(wind(p,x,y,t,4000,this.air[i],ground,'u')-
          slope*wind(p,x,y,t,4000,this.air[i],ground,'v'));
        // Pressure communicates along the head over several adjacent
        // segments during five minutes, rounding cusps between surges.
        const lateral=.13*(line.x[Math.max(0,row-3)]+line.x[Math.min(n-1,row+3)]-2*x);
        line.nextX[row]=x+.3*clamp(advect+(normalSpeed-.70*deepWind)/nx,3,32)+
          .16*(left+right-2*x)+lateral;
        // The initiating impulse can end while the humid jet still feeds
        // its wake. Peripheral outflows entering drier air lose regeneration.
        const fetch=convergenceEnvelope(pulse,y);
        const feed=(.12+.88*fetch)*clamp((this.energy[i]-240)/680)*clamp((this.water[i]-15)/15)*
          clamp(1-3*this.air[i])*this.warmFraction(index(forcing,x+15*nx,y+15*ny));
        const org=organization(p,x,y,t,this.air[i],ground);
        const coupled=clamp((.94-org)/.35);
        // An excessive cold circulation undercuts the updraft. A rear jet
        // partially offsets it; an advancing head still needs warm inflow.
        const imbalance=gust-Math.max(0,shear)-.65*rear;
        const balance=1/(1+(imbalance/13)**2);
        const intake=clamp((normalSpeed-surfaceWind+2)/10);
        const pressureLift=2.1*clamp(gust/9)*clamp(h/120)*balance*intake*(1-this.overturn[i]);
        const cap=.12+.025*(this.temp[i]-this.dew[i]);
        const neighbours=.25*((line.lift[row-1]||0)+(line.lift[row+1]||0)+
          (line.lift[row-3]||0)+(line.lift[row+3]||0));
        const flankLift=0.2*neighbours*intake;
        const target=coupled*feed*clamp(thermal*p.trough*1.5+pressureLift+flankLift-cap)*(0.82+0.18*clamp(lane+.14*rear/12));
        const lift=line.nextLift[row]=clamp(.48*state+.14*neighbours+.38*target);
        if(lift<.025)continue;
        // Convert the mass flux through the sloping intake to an occupied
        // strip; deep merged outflows widen it slightly, never fill the wake.
        const width=(4.2+3*clamp(h/450))/nx;let centre=(x+line.nextX[row])*.5;
        if(this.coldInterior(index(forcing,centre,y))){
          // Follow the warm edge with finite propagation speed, rather
          // than teleporting the updraft to the first warm grid cell.
          const drift=clamp(headSpeed,0,14)*.3;
          centre+=drift;line.nextX[row]+=.5*drift;
        }
        for(let col=Math.max(0,Math.floor((centre-2*width)/2.5));col<Math.min(forcing.nx,(centre+2*width)/2.5);col++){
          const k=row*forcing.nx+col,d=((col+.5)*2.5-centre)/width;
          this.head[k]=Math.max(this.head[k],lift*Math.exp(-d*d));
        }
      }
      [line.x,line.nextX]=[line.nextX,line.x];[line.lift,line.nextLift]=[line.nextLift,line.lift];
    }
  }
  updateHead(){
    // Resolve continuous mass flux on a coherent warm-facing gust front.
    // Two along-front flanks must share deep cold air. Isolated rotating
    // cells can keep their own inflow until neighbouring outflows coalesce.
    const g=forcing,nx=g.nx,h=this.poolDepth,c=this.cold,head=this.head,p=this.config;
    head.fill(0);
    const by=Math.round(4*Math.sin(p.cloudAngle)),back=4+by*nx;
    for(let y=9;y<g.ny-9;y++)for(let x=8;x<nx-8;x++){
      const i=y*nx+x,k=i-back,a=i+back;
      const depth=h[k],jump=depth-h[a];
      let target=0;
      if(depth>75&&jump>40&&c[k]>.55){
        const side=Math.min(Math.max(h[k-5*nx],h[k-5*nx-2]),Math.max(h[k+5*nx],h[k+5*nx-2]));
        const dx=(x+.5)*2.5,dy=(y+.5)*2.5,env=index(grid,dx+10,dy+by*2.5);
        const u=this.poolU[i],relative=u*Math.cos(p.cloudAngle)+this.poolV[i]*Math.sin(p.cloudAngle);
        const frontal=clamp(jump/200)*clamp((relative+3)/10)*clamp((side-45)/170);
        // Head lifting uses warm-side intake, never a rain/echo stencil.
        target=frontal*(1-this.overturn[env])**2*clamp((this.energy[env]-200)/850)*clamp((this.water[env]-16)/16)*
          clamp(1-2*this.air[env])*clamp(1-c[a]/3);
        // Strongly veering profiles must build a deeper merged pool first.
        if(target>0){
          const org=organization(p,dx,dy,this.steps/6,this.air[env],this.terrain[i]);
          target*=1-org*(1-clamp((side-360)/420));
        }
      }
      head[i]=target;
    }
  }

}
const api={organization,wind,airTemperature,Model,grid,forcing,product,ledger,index,environment,LEVELS,DT,BOUNDS,WIDTH,HEIGHT,clamp};
root.StormSol=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
