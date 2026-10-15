(function(root){
    'use strict';
    const G=StormGeo,M=StormModel,{clamp,bounds}=G;
    const layers={
        composite:{name:'区域合成雷达回波',unit:'dBZ',scale:[10,20,30,40,50,60],colors:['#3057b7','#38bce2','#38c77a','#e6db50','#ef934b','#d7425e','#d590e8']},
        reflectivity:{name:'单站雷达 · 反射率',unit:'dBZ',scale:[10,20,30,40,50,60],colors:['#3057b7','#38bce2','#38c77a','#e6db50','#ef934b','#d7425e','#d590e8']},
        velocity:{name:'单站雷达 · 径向速度',unit:'m/s',scale:[-30,-20,-10,0,10,20,30],colors:['#3654d3','#42bdce','#68d9aa','#233745','#deb783','#f08467','#e24462']},
        lowwind:{name:'低空风 · 925 hPa',unit:'m/s',scale:[0,5,10,15,20,25],colors:['#142d3e','#24606a','#51b19a','#a1c97b','#e3c676','#d18566']},
        upperwind:{name:'高空风 · 300 hPa',unit:'m/s',scale:[0,10,20,30,40,50],colors:['#18253b','#394f80','#5b70ad','#8497d3','#b4a0db','#e3b5df']},
        midwind:{name:'中层风 · 500 hPa',unit:'m/s',scale:[0,10,20,30,40,50],colors:['#18253b','#394f80','#5b70ad','#8497d3','#b4a0db','#e3b5df']},
        cape:{name:'对流有效位能 · CAPE',unit:'J/kg',scale:[0,500,1000,2000,3000,4000],colors:['#172c3a','#305d76','#418b94','#9fb78a','#e1bf77','#e07968']},
        temperature:{name:'地面温度',unit:'℃',scale:[10,15,20,25,30,35],colors:['#4364a7','#5c9cb3','#8bbcb2','#d6c898','#e8a66f','#d96156']},
        coldpool:{name:'雷暴冷池 · 降温幅度',unit:'K',scale:[0,1,2,3,5,7],colors:['#122738','#235273','#307dac','#5dabd2','#9cdce8','#defaff']},
        terrain:{name:'概化地形与珠江口',unit:'m',scale:[0,200,500,800,1200,1800],colors:['#213f3e','#3e5c4d','#637256','#8b8a63','#aeaa82','#d3cdae']}
    };
    function clock(t){const minutes=Math.round((8+t)*60),day=Math.floor(minutes/1440)+1;return `第 ${day} 天 ${String(Math.floor(minutes%1440/60)).padStart(2,'0')}:${String(minutes%60).padStart(2,'0')}`;}
    function setup(canvas){
        const rect=canvas.getBoundingClientRect(),dpr=Math.min(devicePixelRatio||1,2);
        const w=Math.max(1,rect.width),h=Math.max(1,rect.height);
        if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
        const c=canvas.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);return {c,w,h,dpr};
    }
    function projection(w,h,view){
        const scale=Math.min(w/((bounds.east-bounds.west)*102),h/((bounds.north-bounds.south)*111))*view.zoom;
        return {scale,to:(lon,lat)=>[w/2+(lon-view.lon)*102*scale,h/2-(lat-view.lat)*111*scale],
            from:(x,y)=>[view.lon+(x-w/2)/scale/102,view.lat-(y-h/2)/scale/111]};
    }
    function rgb(hex){return [1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));}
    const palettes=Object.fromEntries(Object.entries(layers).map(([key,v])=>[key,v.colors.map(rgb)]));
    function color(layer,value){
        const ls=layers[layer],n=ls.scale.length-1;
        const f=clamp((value-ls.scale[0])/(ls.scale[n]-ls.scale[0]))*(ls.colors.length-1),i=Math.min(ls.colors.length-2,Math.floor(f)),a=f-i;
        return palettes[layer][i].map((v,k)=>Math.round(v+(palettes[layer][i+1][k]-v)*a));
    }
    function line(c,points,proj,colorValue,width=1,dash=[]){
        c.beginPath();points.forEach(([x,y],i)=>{const p=proj.to(x,y);if(i)c.lineTo(...p);else c.moveTo(...p);});
        c.strokeStyle=colorValue;c.lineWidth=width;c.setLineDash(dash);c.stroke();c.setLineDash([]);
    }
    function arrow(c,x,y,u,v,length=14,colorValue='#d3edea'){
        const mag=Math.hypot(u,v);if(mag<.1)return;
        const a=Math.atan2(-v,u),ex=x+Math.cos(a)*length,ey=y+Math.sin(a)*length;
        c.strokeStyle=colorValue;c.lineWidth=1.1;c.beginPath();c.moveTo(x,y);c.lineTo(ex,ey);
        c.moveTo(ex-5*Math.cos(a-.55),ey-5*Math.sin(a-.55));c.lineTo(ex,ey);c.lineTo(ex-5*Math.cos(a+.55),ey-5*Math.sin(a+.55));c.stroke();
    }
    class MapView{
        constructor(canvas,layer){this.canvas=canvas;this.layer=layer;this.cacheKey='';this.base=null;this.raster=document.createElement('canvas');}
        draw(frame,view,stations,selected,radar,flags){
            const {c,w,h}=setup(this.canvas),p=projection(w,h,view);this.proj=p;
            c.clearRect(0,0,w,h);c.fillStyle='#0b1c29';c.fillRect(0,0,w,h);
            const key=[w,h,view.lon,view.lat,view.zoom,frame.p.terrain].join(':');
            const rw=Math.min(260,Math.round(w/2.5)),rh=Math.max(45,Math.round(rw*h/w));
            if(this.cacheKey!==key){
                this.cacheKey=key;this.raster.width=rw;this.raster.height=rh;this.sites=[];
                this.base=new Uint8ClampedArray(rw*rh*4);
                for(let y=0;y<rh;y++)for(let x=0;x<rw;x++){
                    const [lon,lat]=p.from((x+.5)/rw*w,(y+.5)/rh*h),g=G.surface(lon,lat);this.sites.push({lon,lat,g});
                    const height=g.height*frame.p.terrain;
                    const shade=clamp(height/1600),k=(y*rw+x)*4;
                    const col=g.water?[11,31,46]:[24+shade*40,46+shade*45,47+shade*35];
                    this.base.set([...col.map(Math.round),255],k);
                }
            }
            const pixels=new Uint8ClampedArray(this.base),rain=new Float32Array(rw*rh);
            const radarLayer=['reflectivity','velocity'].includes(this.layer),echoLayer=radarLayer||this.layer==='composite';
            if(echoLayer){
                for(const cell of frame.cells){
                    const [px,py]=p.to(cell.lon,cell.lat),rx=90*p.scale/w*rw,ry=70*p.scale/h*rh;
                    const cx=px/w*rw,cy=py/h*rh;
                    for(let y=Math.max(0,Math.floor(cy-ry));y<Math.min(rh,Math.ceil(cy+ry));y++)
                        for(let x=Math.max(0,Math.floor(cx-rx));x<Math.min(rw,Math.ceil(cx+rx));x++){
                            const s=this.sites[y*rw+x];let z=0;
                            if(radarLayer){const distance=Math.hypot((s.lon-radar.lon)*102,(s.lat-radar.lat)*111);z=.06+distance*Math.sin(radar.elevation*Math.PI/180)+distance*distance/16989;}
                            rain[y*rw+x]+=M.echoRain(cell,s.lon,s.lat,z);
                        }
                }
            }
            for(let i=0;i<this.sites.length;i++){
                const {lon,lat,g}=this.sites[i];if(!G.inDomain(lon,lat))continue;
                let value=0,opacity=.68;
                if(echoLayer){
                    if(rain[i]<.05)continue;
                    value=10*Math.log10(200*rain[i]**1.6);
                    if(radarLayer){const gate=M.radarGate(frame,lon,lat,radar,rain[i]);if(!gate.valid)continue;
                        if(this.layer==='velocity'){value=gate.velocity;if(flags.fold)value=((value+25)%50+50)%50-25;}
                    }
                    if(this.layer!=='velocity'&&value<10)continue;opacity=.88;
                }else if(this.layer==='terrain'){if(g.water)continue;value=g.height*frame.p.terrain;opacity=.82;}
                else if(this.layer==='coldpool'){value=M.compactSample(frame.coldGrid,lon,lat,.03);if(value<.12)continue;opacity=.78;}
                else if(this.layer.endsWith('wind')){
                    const z=this.layer==='lowwind'? .8:this.layer==='midwind'?5.5:9;
                    const coldAir=1/(1+Math.exp(clamp((M.frontLatitude(lon,frame.t,frame.p)-lat)*111/13,-50,50)));
                    const f=M.windAt(lon,lat,frame.t,z,frame.p,coldAir,g);value=Math.hypot(f.u,f.v);
                }else{
                    const cold=M.compactSample(frame.coldGrid,lon,lat,.03),used=M.compactSample(frame.usedGrid,lon,lat,1/255);
                    const e=M.background(lon,lat,frame.t,frame.p,g,cold,used);value=this.layer==='cape'?e.cape:e.temp;
                }
                const col=color(this.layer,value),k=i*4;
                for(let j=0;j<3;j++)pixels[k+j]=pixels[k+j]*(1-opacity)+col[j]*opacity;
            }
            this.raster.getContext('2d').putImageData(new ImageData(pixels,rw,rh),0,0);
            c.imageSmoothingEnabled=true;c.drawImage(this.raster,0,0,w,h);
            c.font='10px ui-sans-serif';c.lineWidth=.5;
            for(let lon=Math.ceil(bounds.west);lon<bounds.east;lon++){
                line(c,[[lon,bounds.south],[lon,bounds.north]],p,'#8bb1c318',.6);
                const [x]=p.to(lon,view.lat);if(x>15&&x<w-30){c.fillStyle='#93b0c477';c.fillText(lon+'°E',x+3,h-8);}
            }
            for(let lat=20;lat<27;lat++)line(c,[[bounds.west,lat],[bounds.east,lat]],p,'#8bb1c318',.6);
            if(flags.terrain)line(c,G.coast,p,'#809eab',1.2);
            if(flags.fronts){
                const front=[];for(let lon=104;lon<=119;lon+=.2)front.push([lon,M.frontLatitude(lon,frame.t,frame.p)]);
                line(c,front,p,'#80bcff',2);
                for(let lon=104.8;lon<118;lon+=.55){const [x,y]=p.to(lon,M.frontLatitude(lon,frame.t,frame.p));c.fillStyle='#80bcff';c.beginPath();c.moveTo(x-5,y-2);c.lineTo(x+5,y-2);c.lineTo(x+2,y+7);c.closePath();c.fill();}
                if(frame.t<35){const x=M.troughLongitude(frame.t);line(c,[[x-.5,21],[x,23],[x+.3,26]],p,'#d69bdf',1.8,[6,5]);}
                // Broken arcs mark individual cold-pool gust fronts, not the synoptic front.
                c.strokeStyle='#9ce9d599';c.lineWidth=.8;
                for(const cell of frame.cells.filter(x=>x.strength>.48&&x.age>.3)){
                    const [x,y]=p.to(cell.lon,cell.lat);c.beginPath();c.arc(x,y,(16+cell.age*4)*p.scale,-1.1,1.1);c.stroke();
                }
            }
            if(this.layer.endsWith('wind')){
                const z=this.layer==='lowwind'?.8:this.layer==='midwind'?5.5:9;
                for(let y=30;y<h-20;y+=42)for(let x=25;x<w-20;x+=46){
                    const [lon,lat]=p.from(x,y),coldAir=1/(1+Math.exp(clamp((M.frontLatitude(lon,frame.t,frame.p)-lat)*111/13,-50,50)));
                    const flow=M.windAt(lon,lat,frame.t,z,frame.p,coldAir);arrow(c,x,y,flow.u,flow.v,12+Math.hypot(flow.u,flow.v)*.3);
                }
            }
            if(radarLayer){
                const [x,y]=p.to(radar.lon,radar.lat);c.strokeStyle='#cadfec88';c.lineWidth=.7;c.setLineDash([3,5]);
                for(const km of [50,100,150,230]){c.beginPath();c.arc(x,y,km*p.scale,0,Math.PI*2);c.stroke();}
                c.setLineDash([]);c.fillStyle='#fbdfad';c.fillRect(x-3,y-3,6,6);c.font='10px ui-sans-serif';c.fillText('虚拟雷达',x+8,y-6);
            }
            if(flags.labels){
                c.textAlign='center';c.font='12px ui-sans-serif';c.fillStyle='#cfdecd77';
                for(const label of [['广西',108.3,24.7],['广东',114.1,24.5],['南海',114.4,21.1],['珠江口',113.73,22.35]]){const [x,y]=p.to(label[1],label[2]);c.fillText(label[0],x,y);}
                if(flags.terrain&&view.zoom>1.2){c.font='10px ui-sans-serif';c.fillStyle='#c6cba591';for(const [name,x,y]of G.ridges){const xy=p.to(x,y);c.fillText(name,...xy);}}
                c.textAlign='left';
            }
            this.hits=[];
            if(flags.stations)for(const station of stations){
                const [x,y]=p.to(station.lon,station.lat);if(x<0||x>w||y<0||y>h)continue;
                const active=station.id===selected.id,custom=station.kind==='custom';
                c.fillStyle=active?'#ffe0a3':custom?'#ba9cf7':'#d1e9e4';c.strokeStyle='#06151c';c.lineWidth=1;
                c.beginPath();c.arc(x,y,active?5:custom?3.3:2.4,0,Math.PI*2);c.fill();c.stroke();
                if(active){c.strokeStyle='#ffe0a3';c.beginPath();c.arc(x,y,9,0,Math.PI*2);c.stroke();}
                const notable=['59493','59287','59488','59431','57957','59265','59663','59658'].includes(station.id);
                if(active||(flags.labels&&(view.zoom>3||notable))){c.font=`${active?'bold ':''}10px ui-sans-serif`;c.strokeStyle='#0a1b27';c.lineWidth=3;c.strokeText(station.name,x+8,y-7);c.fillStyle=active?'#ffe0a3':'#c4d9df';c.fillText(station.name,x+8,y-7);}
                this.hits.push({x,y,station});
            }
            c.fillStyle='#b2c7d588';c.font='9px ui-sans-serif';c.fillText('教学模拟 · 概化地理',10,15);
            const bar=Math.max(10,Math.round(80/(p.scale*50))*50);c.strokeStyle='#c0d7e6';c.lineWidth=2;c.beginPath();c.moveTo(12,h-24);c.lineTo(12+bar*p.scale,h-24);c.stroke();c.fillStyle='#c0d7e6';c.fillText(bar+' km',12,h-31);
        }
        hit(x,y){return (this.hits||[]).filter(a=>Math.hypot(a.x-x,a.y-y)<12).sort((a,b)=>Math.hypot(a.x-x,a.y-y)-Math.hypot(b.x-x,b.y-y))[0]?.station;}
    }
    function axes(canvas,xlabel,ylabel){
        const {c,w,h}=setup(canvas);c.clearRect(0,0,w,h);c.fillStyle='#0b1b27';c.fillRect(0,0,w,h);c.font='10px ui-sans-serif';c.fillStyle='#8ca6b8';
        c.fillText(ylabel,8,14);c.fillText(xlabel,w-90,h-6);return {c,w,h,left:38,right:w-20,top:28,bottom:h-25};
    }
    function stationChart(canvas,series){
        const {c,w,h,left,right,top,bottom}=axes(canvas,'模拟小时','℃ / mm·h⁻¹');if(!series.length)return;
        const end=Math.max(1,series.at(-1).t),temps=series.map(o=>o.temp).filter(Number.isFinite);
        const min=Math.floor(Math.min(...temps)-2),max=Math.ceil(Math.max(...temps)+2),maxRain=Math.max(10,...series.map(o=>o.rain||0));
        c.font='9px ui-sans-serif';c.fillStyle='#8ca6b8';c.fillText(max+'°',3,top+5);c.fillText(min+'°',3,bottom);c.fillText('0',left,h-8);c.fillText(end.toFixed(1),right-20,h-8);
        c.fillStyle='#6eafff65';for(let i=0;i<series.length;i++){const o=series[i],x=left+o.t/end*(right-left),y=bottom-(o.rain||0)/maxRain*(bottom-top);c.fillRect(x,y,Math.max(1,(right-left)/series.length),bottom-y);}
        c.strokeStyle='#ffc18b';c.lineWidth=1.7;c.beginPath();series.forEach((o,i)=>{const x=left+o.t/end*(right-left),y=bottom-(o.temp-min)/(max-min)*(bottom-top);if(i)c.lineTo(x,y);else c.moveTo(x,y);});c.stroke();
        c.fillStyle='#6eafff';c.fillText(maxRain.toFixed(0)+' mm/h',right-57,top+5);
    }
    function profileChart(canvas,obs,p,t){
        const {c,w,h,left,right,top,bottom}=axes(canvas,'温度 ℃','高度 km');if(!obs)return;
        const plotRight=right-60,levels=M.sounding(obs.temp,obs.dew,p,obs.cooling,obs.stabilization).levels;
        for(let z=0;z<=15;z+=3){const y=bottom-z/15*(bottom-top);c.fillStyle='#849db1';c.fillText(String(z),8,y+3);c.strokeStyle='#233e50';c.beginPath();c.moveTo(left,y);c.lineTo(right,y);c.stroke();}
        const X=t=>left+(t+75)/115*(plotRight-left),Y=z=>bottom-z/15*(bottom-top);
        for(const [key,col,dash]of [['temp','#ffc18b',[]],['dew','#63e0be',[]],['parcel','#c8b0ff',[4,3]]]){
            c.strokeStyle=col;c.lineWidth=1.5;c.setLineDash(dash);c.beginPath();levels.forEach((l,i)=>{if(i)c.lineTo(X(l[key]),Y(l.z));else c.moveTo(X(l[key]),Y(l.z));});c.stroke();
        }c.setLineDash([]);
        for(const l of levels.filter((_,i)=>i%2===0)){const f=M.windAt(obs.lon,obs.lat,t,l.z,p,obs.coldAir);arrow(c,right-30,Y(l.z),f.u,f.v,17);}
        c.font='9px ui-sans-serif';c.fillStyle='#8ca6b8';for(const t of [-60,-30,0,30])c.fillText(t+'',X(t),h-8);
        c.fillText('水平风',right-47,top-10);
    }
    function sectionChart(canvas,frame,station){
        const {c,w,h,left,right,top,bottom}=axes(canvas,'相对距离 km','高度 km');
        const X=lon=>left+((lon-station.lon)*102+180)/360*(right-left),Y=z=>bottom-z/15*(bottom-top);
        for(let z=0;z<=15;z+=3){const y=Y(z);c.fillStyle='#849db1';c.fillText(z+'',7,y+3);c.strokeStyle='#233e50';c.beginPath();c.moveTo(left,y);c.lineTo(right,y);c.stroke();}
        for(const cell of frame.cells){
            if(Math.abs(cell.lat-station.lat)*111>35||Math.abs(cell.lon-station.lon)*102>210)continue;
            const x=X(cell.lon),col=color('composite',30+cell.strength*25);c.fillStyle=`rgba(${col.join(',')},.65)`;
            c.beginPath();c.ellipse(x,(Y(cell.top)+bottom)/2,Math.max(3,cell.shape*16/360*(right-left)),(bottom-Y(cell.top))/2,0,0,Math.PI*2);c.fill();
            arrow(c,x,bottom-10,0,1,Math.min(45,cell.strength*45),'#a9f1d3');
        }
        c.beginPath();c.moveTo(left,bottom);
        for(let x=left;x<=right;x+=3){const lon=station.lon+((x-left)/(right-left)*360-180)/102;const g=G.surface(lon,station.lat);c.lineTo(x,Y(g.height*frame.p.terrain/1000));}
        c.lineTo(right,bottom);c.closePath();c.fillStyle='#7b8c65';c.fill();
        for(let x=left;x<right;x+=3){const lon=station.lon+((x-left)/(right-left)*360-180)/102,cold=M.compactSample(frame.coldGrid,lon,station.lat,.03);if(cold>.2){c.fillStyle=`rgba(96,179,241,${clamp(cold/5)})`;c.fillRect(x,Y(.7+cold*.1),3,bottom-Y(.7+cold*.1));}}
        for(let x=left+10;x<right-20;x+=55)for(const z of [2,6,10]){const lon=station.lon+((x-left)/(right-left)*360-180)/102,env=M.background(lon,station.lat,frame.t,frame.p),f=M.windAt(lon,station.lat,frame.t,z,frame.p,env.coldAir);arrow(c,x,Y(z),f.u,f.v,15,'#c4d8e788');}
        c.strokeStyle='#ffd598';c.setLineDash([3,4]);c.beginPath();c.moveTo(X(station.lon),top);c.lineTo(X(station.lon),bottom);c.stroke();c.setLineDash([]);
        c.fillStyle='#ffd598';c.font='10px ui-sans-serif';c.fillText(station.name,X(station.lon)+5,top+10);
        c.fillStyle='#8ca6b8';for(const km of [-180,-90,0,90])c.fillText(km+'',left+(km+180)/360*(right-left),h-8);
    }
    root.StormRender={MapView,layers,clock,projection,stationChart,profileChart,sectionChart};
})(globalThis);
