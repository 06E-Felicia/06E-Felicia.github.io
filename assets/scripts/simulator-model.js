/* Educational reduced model. Background forcing + prognostic cells, cold pools,
 * recovery and rain accounting. No observational radar or operational forecast. */
(function(root) {
    'use strict';
    const G=root.StormGeo || (typeof require==='function' && require('./simulator-geo.js'));
    const {clamp,bounds}=G, NX=240, NY=128, DT=.1;
    const dx=(bounds.east-bounds.west)/(NX-1),dy=(bounds.north-bounds.south)/(NY-1);
    const DEFAULTS={month:4,moisture:1,jet:1,shear:1,trough:1,front:1,frontSpeed:1,
        terrain:1,estuary:1,seaContrast:4,seed:20260421};
    const limits={month:[3,5],moisture:[.55,1.4],jet:[.4,1.6],shear:[.2,1.8],
        trough:[0,1.6],front:[.2,1.6],frontSpeed:[.8,1.2],terrain:[0,1.5],estuary:[0,1.5],
        seaContrast:[0,7],seed:[1,2147483646]};
    function parameters(input={}) {
        const p={...DEFAULTS};
        for(const [k,[lo,hi]] of Object.entries(limits)) {
            if(input[k]!==undefined && Number.isFinite(Number(input[k]))) p[k]=clamp(Number(input[k]),lo,hi);
        }
        p.month=Math.round(p.month);p.seed=Math.round(p.seed);return p;
    }
    const bell=(v,s)=>Math.exp(-.5*(v/s)**2);
    const logistic=v=>1/(1+Math.exp(clamp(-v,-50,50)));
    function frontLatitude(lon,t,p) {return 22.54+.32*(lon-114)+.18*(72-t*p.frontSpeed);}
    function troughLongitude(t) {return 106.6+.43*(t-7);}
    function wind(z,p,coldAir=0) {
        const jet=13*p.jet*bell(z-1.1,.75);
        const u=3+jet*.7+z*1.5*p.shear;
        const v=2+jet*.65-z*.45*p.shear;
        const near=bell(z,.9)*coldAir;
        return {u:u*(1-near)+2*near, v:v*(1-near)-8*p.front*near};
    }
    function windAt(lon,lat,t,z,p,coldAir=0,ground=G.surface(lon,lat)) {
        const f=wind(z,p,coldAir),axis=troughLongitude(t),trough=bell(t-16,13)*p.trough;
        const influence=bell(lon-axis,3)*bell(z-5.5,4)*trough;
        f.v+=7*Math.tanh(lon-axis)*influence;f.u+=4*influence;
        const nocturnal=1+.18*Math.cos(((t+8)%24-3)/12*Math.PI);
        const low=bell(z-1,.9)*(1-coldAir);
        const factor=1+low*(nocturnal-1-ground.height*p.terrain/2600-ground.marine*p.estuary*.14);
        return {u:f.u*Math.max(.35,factor),v:f.v*Math.max(.35,factor)};
    }
    function sounding(temp,dew,p,cooling=0,stabilization=0) {
        const lcl=clamp((temp-dew)*.125,.08,3.5),levels=[];
        let cape=0,cin=0,positive=false,cloudTop=lcl;
        const heights=[0,.25,.5,.8,1,1.4,2,3,4,5.5,7,9,11,13,15];
        for(let i=0;i<heights.length;i++) {
            const z=heights[i];
            const env=temp-6.7*Math.min(z,11)-Math.max(0,z-11)*.7
                +1.6*bell(z-1.3,.35)-cooling*bell(z-5,2)+stabilization*(1-Math.exp(-z/.8));
            const parcel=temp-9.8*Math.min(z,lcl)-5.65*Math.max(0,z-lcl);
            const buoyancy=9.81*(parcel-env)/(env+273.15);
            if(i) {
                const prev=levels[i-1], dz=(z-prev.z)*1000;
                const avg=(buoyancy+prev.buoyancy)/2;
                if(avg>0&&z>lcl){cape+=avg*dz;positive=true;cloudTop=z;}
                else if(!positive)cin+=Math.max(0,-avg*dz);
            }
            const w=wind(z,p);
            levels.push({z,temp:env,dew:Math.min(env,dew-z*(z<2?1.6:2.5)),parcel,buoyancy,...w});
        }
        return {cape,cin,lcl,cloudTop,levels};
    }
    function background(lon,lat,t,p,ground=G.surface(lon,lat),cold=0,depleted=0) {
        const warmDistance=(frontLatitude(lon,t,p)-lat)*111;
        const coldAir=logistic(-warmDistance/13);
        const localHour=(8+t)%24, sun=Math.max(0,Math.sin((localHour-6)/12*Math.PI));
        const nearTrough=bell(lon-troughLongitude(t),1.7)*bell(t-16,12)*p.trough;
        const height=ground.height*p.terrain;
        const waterCooling=(ground.water?.4:0)+ground.marine*p.estuary;
        const temp=26.8+(p.month-4)*1.2+2.8*sun-.35*(lat-23)-height*.005
            -waterCooling*p.seaContrast-6.5*coldAir*p.front-cold-2.8*depleted;
        const dew=Math.min(temp-.15,22.3+(p.month-4)*1.1+(p.moisture-1)*12
            -.002*height-3.5*coldAir*p.front-depleted*.7);
        // Surface cooling cannot cool the whole free troposphere by the same
        // amount: retain the warmer air aloft so cold pools/fronts consume CAPE.
        const stabilization=6.5*coldAir*p.front+cold+2.8*depleted+waterCooling*p.seaContrast;
        const profile=sounding(temp,dew,p,nearTrough*2.3,stabilization);
        const w=windAt(lon,lat,t,.01,p,coldAir,ground);
        for(const l of profile.levels)Object.assign(l,windAt(lon,lat,t,l.z,p,coldAir,ground));
        const terrainLoss=clamp(height/1600,.0,.78);
        const estuaryLoss=clamp(ground.marine*p.estuary*p.seaContrast/6,0,.85);
        return {temp,dew,coldAir,cold,depleted,terrainLoss,estuaryLoss,height,stabilization,
            humidity:clamp(100*Math.exp(17.625*dew/(243.04+dew)-17.625*temp/(243.04+temp)),0,100),
            pressure:1008+4*coldAir*p.front+.75*cold-1.2*nearTrough,
            u:w.u,v:w.v,...profile,nearTrough};
    }
    function stage(t,p) {
        const f=72/p.frontSpeed;
        if(t<8)return {title:'暖区蓄能',detail:'低层暖湿输送持续，南支槽从西侧接近。'};
        if(t<28)return {title:'第一轮 · 南支槽锋前对流',detail:'槽前扰动与低层辐合触发单体，雷暴冷池推动新生单体组织发展。'};
        if(t<f-13)return {title:'间歇 · 环境恢复',detail:'第一轮冷池消退；日照和暖湿输送决定第二轮可利用的能量。'};
        if(t<f+3)return {title:'第二轮 · 冷锋推进',detail:'大尺度冷空气推进，锋面抬升与雷暴自身的阵风锋共同作用。'};
        return {title:'锋后 · 衰减与残留降水',detail:'暖湿入流减弱，冷空气控制；已生成的对流与层状降水逐渐衰减。'};
    }
    // Compact sampled state for synchronized radar and vertical-section diagnostics.
    const CX=60,CY=32;
    function compactSample(grid,lon,lat,scale) {
        if(!grid)return 0;
        const x=clamp((lon-bounds.west)/(bounds.east-bounds.west)*(CX-1),0,CX-1);
        const y=clamp((lat-bounds.south)/(bounds.north-bounds.south)*(CY-1),0,CY-1);
        const ix=Math.min(CX-2,Math.floor(x)),iy=Math.min(CY-2,Math.floor(y)),a=x-ix,b=y-iy,k=iy*CX+ix;
        return ((grid[k]*(1-a)+grid[k+1]*a)*(1-b)+(grid[k+CX]*(1-a)+grid[k+CX+1]*a)*b)*scale;
    }
    function echoRain(c,lon,lat,height=0) {
        if(height>c.top)return 0;
        const x=(lon-c.lon)*102,y=(lat-c.lat)*111;
        const core=Math.exp(-.5*((x/(12*c.shape))**2+(y/15)**2));
        const trailing=.12*Math.exp(-.5*(((x+20)/24)**2+(y/22)**2));
        const vertical=clamp((c.top-height)/Math.max(1,c.top-2),0,1);
        return 55*c.strength**1.7*(core+trailing)*vertical;
    }
    function radarGate(frame,lon,lat,radar,rainOverride) {
        const east=(lon-radar.lon)*111.195*Math.cos(radar.lat*Math.PI/180),north=(lat-radar.lat)*111.195;
        const range=Math.hypot(east,north), angle=(radar.elevation??.5)*Math.PI/180;
        const height=.06+range*Math.sin(angle)+range*range/(2*(4/3)*6371);
        if(range>230||range<2)return {valid:false,range,height};
        const ground=G.surface(lon,lat),coldAir=logistic(-(frontLatitude(lon,frame.t,frame.p)-lat)*111/13);
        let rain=rainOverride;
        if(rain===undefined)rain=frame.cells.reduce((sum,c)=>sum+echoRain(c,lon,lat,height),0);
        const dbz=rain>.01?10*Math.log10(200*Math.pow(rain,1.6)):0;
        const cold=compactSample(frame.coldGrid,lon,lat,.03);
        const cw=compactSample(frame.coldGrid,lon-.05,lat,.03),ce=compactSample(frame.coldGrid,lon+.05,lat,.03);
        const cs=compactSample(frame.coldGrid,lon,lat-.05,.03),cn=compactSample(frame.coldGrid,lon,lat+.05,.03);
        const w=windAt(lon,lat,frame.t,height,frame.p,coldAir,ground),surfaceWeight=Math.exp(-height/1.2);
        const u=w.u+(cw-ce)*2*surfaceWeight,v=w.v+(cs-cn)*2*surfaceWeight;
        const velocity=(u*east+v*north)/range*Math.cos(angle);
        // Coarse terrain blockage; high beam above the cloud top has no return.
        const blocked=ground.height*frame.p.terrain/1000>height;
        return {valid:dbz>=10&&!blocked,dbz,velocity,range,height,cold,blocked,u,v};
    }
    class Model {
        constructor(input={},stations=[]) {
            this.p=parameters(input);this.duration=Math.ceil(72/this.p.frontSpeed+12);
            this.t=0;this.tick=0;this.seed=this.p.seed;this.nextId=0;this.cells=[];
            this.cold=new Float32Array(NX*NY);this.nextCold=new Float32Array(NX*NY);
            this.used=new Float32Array(NX*NY);this.rain=new Float32Array(NX*NY);
            this.ground=new Array(NX*NY);
            for(let y=0;y<NY;y++)for(let x=0;x<NX;x++)this.ground[y*NX+x]=G.surface(bounds.west+x*dx,bounds.south+y*dy);
            // Symmetric face conductance: terrain gradients slow cold-pool mixing.
            this.mixEast=new Float32Array(NX*NY);this.mixNorth=new Float32Array(NX*NY);
            for(let y=0;y<NY;y++)for(let x=0;x<NX;x++){
                const k=y*NX+x,h=this.ground[k].height;
                if(x<NX-1)this.mixEast[k]=.12*Math.exp(-Math.abs(this.ground[k+1].height-h)*this.p.terrain/250);
                if(y<NY-1)this.mixNorth[k]=.12*Math.exp(-Math.abs(this.ground[k+NX].height-h)*this.p.terrain/250);
            }
            this.stations=stations.filter(s=>G.inDomain(s.lon,s.lat));
            this.records=new Map(this.stations.map(s=>[s.id,{total:0,steps:[],obs:null}]));
            this.observe(false);
        }
        random(){this.seed=(Math.imul(this.seed,1664525)+1013904223)>>>0;return this.seed/4294967296;}
        index(lon,lat){return clamp(Math.round((lat-bounds.south)/dy),0,NY-1)*NX+clamp(Math.round((lon-bounds.west)/dx),0,NX-1);}
        sample(field,lon,lat){
            const x=clamp((lon-bounds.west)/dx,0,NX-1),y=clamp((lat-bounds.south)/dy,0,NY-1);
            const ix=Math.min(NX-2,Math.floor(x)),iy=Math.min(NY-2,Math.floor(y)),a=x-ix,b=y-iy,k=iy*NX+ix;
            return (1-b)*(field[k]*(1-a)+field[k+1]*a)+b*(field[k+NX]*(1-a)+field[k+NX+1]*a);
        }
        environment(lon,lat){return background(lon,lat,this.t,this.p,G.surface(lon,lat),
            this.sample(this.cold,lon,lat),this.sample(this.used,lon,lat));}
        spawn(lon,lat,family,forcing=1) {
            if(!G.inDomain(lon,lat)||this.cells.length>=240)return;
            if(this.cells.some(c=>c.family===family&&c.age<.8&&Math.hypot((c.lon-lon)*102,(c.lat-lat)*111)<23))return;
            const e=this.environment(lon,lat);
            if(e.cape<180||e.cin>(family==='front'?420:170)||e.coldAir>.75)return;
            const chance=clamp(e.cape/1400)*forcing*(1-e.terrainLoss*.65)*(1-e.estuaryLoss*.7);
            if(this.random()>chance)return;
            this.cells.push({id:++this.nextId,lon,lat,age:0,strength:.16,family,forcing,
                shape:.8+this.random()*.4,child:false,top:3,terrainLoss:e.terrainLoss,estuaryLoss:e.estuaryLoss});
        }
        step() {
            this.tick++;this.t=Number((this.tick*DT).toFixed(5));
            const p=this.p,decay=Math.exp(-DT/2.8),recover=Math.exp(-DT/(7/Math.max(.25,p.moisture*p.jet)));
            // Stable positive diffusion of the storm-generated cold anomaly only.
            // The synoptic front remains a separate background air mass.
            for(let y=0;y<NY;y++)for(let x=0;x<NX;x++) {
                const k=y*NX+x,c=this.cold[k];
                let mixed=c;
                if(x>0)mixed+=this.mixEast[k-1]*(this.cold[k-1]-c);
                if(x<NX-1)mixed+=this.mixEast[k]*(this.cold[k+1]-c);
                if(y>0)mixed+=this.mixNorth[k-NX]*(this.cold[k-NX]-c);
                if(y<NY-1)mixed+=this.mixNorth[k]*(this.cold[k+NX]-c);
                this.nextCold[k]=Math.max(0,mixed*decay);
                this.used[k]*=recover;this.rain[k]=0;
            }
            [this.cold,this.nextCold]=[this.nextCold,this.cold];
            // No calendar gate: forcing location, instability and inhibition
            // decide whether convection can initiate, including earlier storms.
            if(p.trough>0) {
                const axis=107.1+.43*(this.t-7);
                for(let lat=21.45;lat<=25.1;lat+=.22) {
                    const lon=axis+.36*(lat-23)+.06*Math.sin(lat*11+this.t);
                    this.spawn(lon,lat,'trough',p.trough*bell(this.t-17,9));
                }
            }
            for(let lon=104.8;lon<117.6;lon+=.25) {
                const lat=frontLatitude(lon,this.t,p)-.25;
                this.spawn(lon,lat,'front',p.front*.9);
            }
            const children=[];
            for(const c of this.cells) {
                c.age+=DT;
                const e=this.environment(c.lon,c.lat);
                const shearOrganization=clamp(.2+p.shear*.72,.25,1.25);
                const energy=clamp(e.cape/1450,0,1.3)*clamp(p.moisture,.35,1.3);
                const terrainRetention=1-e.terrainLoss*.8,marineRetention=1-e.estuaryLoss*.82;
                const oldAge=Math.exp(-Math.max(0,c.age-1.25)*1.5);
                const target=clamp(energy*shearOrganization*c.forcing*terrainRetention*marineRetention
                    *(1-e.coldAir*.9)*oldAge,0,1.25);
                c.strength=clamp(c.strength+(target-c.strength)*.28,0,1.3);
                c.top=clamp(3+e.cloudTop*c.strength*.7,3,15);
                c.terrainLoss=e.terrainLoss;c.estuaryLoss=e.estuaryLoss;
                const flow=windAt(c.lon,c.lat,this.t,3,p,e.coldAir),coldPropagation=3.5*c.strength;
                const block=clamp(1-e.terrainLoss*.62,.3,1);
                c.lon+=(flow.u+coldPropagation)*3.6/102*DT*block;
                c.lat+=(c.family==='front'?-5.2*p.frontSpeed:flow.v*.2)*3.6/111*DT*block;
                if(!c.child&&c.age>.65&&c.strength>.5) {
                    c.child=true;
                    children.push([c.lon+.15*block,c.lat+(c.family==='front'?-.10:.02),c.family,c.forcing*.78]);
                }
                const cx=Math.round((c.lon-bounds.west)/dx),cy=Math.round((c.lat-bounds.south)/dy);
                for(let oy=-5;oy<=5;oy++)for(let ox=-6;ox<=6;ox++) {
                    const x=cx+ox,y=cy+oy;
                    if(x<0||x>=NX||y<0||y>=NY)continue;
                    const k=y*NX+x,rx=(bounds.west+x*dx-c.lon)*102,ry=(bounds.south+y*dy-c.lat)*111;
                    const core=Math.exp(-.5*((rx/(12*c.shape))**2+(ry/15)**2));
                    const trailing=.12*Math.exp(-.5*(((rx+20)/24)**2+(ry/22)**2));
                    const rate=55*c.strength**1.7*(core+trailing);
                    this.rain[k]+=rate;
                    this.cold[k]=Math.min(7,this.cold[k]+rate*DT*.025);
                    this.used[k]=Math.min(1,this.used[k]+rate*DT*.01);
                }
            }
            this.cells=this.cells.filter(c=>c.age<3.6&&c.strength>.025&&G.inDomain(c.lon,c.lat));
            for(const args of children)this.spawn(...args);
            this.observe(true);
        }
        observe(accumulate) {
            for(const s of this.stations) {
                const e=this.environment(s.lon,s.lat),record=this.records.get(s.id);
                const rain=this.sample(this.rain,s.lon,s.lat);
                if(accumulate){record.total+=rain*DT;record.steps.push(rain*DT);if(record.steps.length>10)record.steps.shift();}
                const coldWest=this.sample(this.cold,s.lon-.05,s.lat),coldEast=this.sample(this.cold,s.lon+.05,s.lat);
                const coldSouth=this.sample(this.cold,s.lon,s.lat-.05),coldNorth=this.sample(this.cold,s.lon,s.lat+.05);
                const u=e.u+(coldWest-coldEast)*2,v=e.v+(coldSouth-coldNorth)*2;
                const speed=Math.hypot(u,v),direction=(Math.atan2(-u,-v)*180/Math.PI+360)%360;
                record.obs={id:s.id,lon:s.lon,lat:s.lat,temp:e.temp,dew:e.dew,humidity:e.humidity,pressure:e.pressure,
                    wind:speed,direction,gust:speed+Math.sqrt(Math.max(0,rain))*1.3+e.cold*.5,
                    rain, rain1h:record.steps.reduce((a,b)=>a+b,0),total:record.total,
                    cape:e.cape,cin:e.cin,cold:e.cold,coldAir:e.coldAir,
                    terrainLoss:e.terrainLoss,estuaryLoss:e.estuaryLoss,cooling:e.nearTrough*2.3,
                    height:e.height,stabilization:e.stabilization};
            }
        }
        snapshot() {
            const coldGrid=new Uint8Array(CX*CY),usedGrid=new Uint8Array(CX*CY);
            for(let y=0;y<CY;y++)for(let x=0;x<CX;x++) {
                const lon=bounds.west+x/(CX-1)*(bounds.east-bounds.west),lat=bounds.south+y/(CY-1)*(bounds.north-bounds.south);
                coldGrid[y*CX+x]=Math.round(clamp(this.sample(this.cold,lon,lat)/.03,0,255));
                usedGrid[y*CX+x]=Math.round(clamp(this.sample(this.used,lon,lat))*255);
            }
            return {t:this.t,duration:this.duration,p:this.p,stage:stage(this.t,this.p),
                coldGrid,usedGrid,
                cells:this.cells.map(c=>({...c})),observations:Object.fromEntries([...this.records].map(([id,r])=>[id,{...r.obs}])),
                summary:{cells:this.cells.length,strong:this.cells.filter(c=>c.strength>.65).length,
                    maxRain:Math.max(0,...[...this.records.values()].map(r=>r.obs.rain)),
                    troughCells:this.cells.filter(c=>c.family==='trough').length,frontCells:this.cells.filter(c=>c.family==='front').length}};
        }
    }
    function validateCustom(value) {
        if(!value||typeof value.name!=='string'||!value.name.trim()||value.name.length>30
            ||!G.inDomain(Number(value.lon),Number(value.lat)))return null;
        return {id:String(value.id||'').startsWith('custom-')?String(value.id):'custom-'+Date.now(),
            name:value.name.trim(),lon:Number(value.lon),lat:Number(value.lat),province:'自定义',kind:'custom'};
    }
    const api={Model,DEFAULTS,parameters,background,sounding,wind,windAt,stage,frontLatitude,troughLongitude,
        validateCustom,radarGate,echoRain,compactSample,DT,NX,NY};
    root.StormModel=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
