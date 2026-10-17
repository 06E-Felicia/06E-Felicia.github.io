/* Static protocol shared by browser and tests. No private credentials. */
(function(root){
    'use strict';
    function validateManifest(m){
        if(m?.schema!==2||m.status!=='complete'||m.simulation!==true)throw Error('不是完整的 v2 模拟结果');
        const g=m.grid;
        if(!g||![g.nx,g.ny].every(n=>Number.isInteger(n)&&n>=2&&n<=1500)||g.nx*g.ny>600000)throw Error('网格大小无效');
        if(![g.west,g.south,g.dlon,g.dlat,g.nominal_km].every(Number.isFinite)||g.dlon<=0||g.dlat<=0)throw Error('网格坐标无效');
        if(!Array.isArray(g.z_agl_m)||g.z_agl_m.length>40||g.z_agl_m.some((z,i)=>!Number.isFinite(z)||z<0||(i&&z<=g.z_agl_m[i-1])))throw Error('垂直坐标无效');
        if(!Array.isArray(m.frames)||!m.frames.length||m.frames.length>600)throw Error('时间轴无效');
        m.frames.forEach((f,i)=>{if(!Number.isFinite(f.hour)||f.hour<0||(i&&f.hour<=m.frames[i-1].hour)||!/^frame-\d{4}\.json\.gz$/.test(f.file)||!/^[a-f0-9]{64}$/.test(f.sha256))throw Error('帧清单无效');});
        return m;
    }
    function unpack(v,g){
        const s=v.shape,n=s?.reduce((a,b)=>a*b,1);
        if(!Array.isArray(s)||![2,3].includes(s.length)||s.some(x=>!Number.isInteger(x)||x<=0)||s.at(-1)!==g.nx||s.at(-2)!==g.ny||(s.length===3&&s[0]!==g.z_agl_m.length)||!Number.isFinite(v.scale)||v.scale<=0||!Number.isFinite(v.offset)||typeof v.data!=='string'||v.data.length>g.nx*g.ny*40*3)throw Error('字段编码无效');
        const binary=typeof atob==='function'?atob(v.data):Buffer.from(v.data,'base64').toString('binary');
        if(binary.length!==n*2)throw Error('字段字节长度不匹配');
        const bytes=Uint8Array.from(binary,c=>c.charCodeAt(0)),dv=new DataView(bytes.buffer),data=new Int16Array(n);
        for(let i=0;i<n;i++)data[i]=dv.getInt16(i*2,true);
        return {shape:s,data,scale:v.scale,offset:v.offset};
    }
    function index(g,lon,lat){const x=(lon-g.west)/g.dlon,y=(lat-g.south)/g.dlat;return !Number.isFinite(x+y)||x<-1e-7||y<-1e-7||x>g.nx-1+1e-7||y>g.ny-1+1e-7?-1:Math.round(y)*g.nx+Math.round(x);}
    function value(f,i,k=0){if(!f||i<0)return NaN;const n=f.shape.at(-1)*f.shape.at(-2),raw=f.data[k*n+i];return raw===undefined||raw===32767?NaN:raw*f.scale+f.offset;}
    function sample(f,g,lon,lat,k=0){
        let x=(lon-g.west)/g.dlon,y=(lat-g.south)/g.dlat;
        if(!Number.isFinite(x+y)||x<-1e-7||y<-1e-7||x>g.nx-1+1e-7||y>g.ny-1+1e-7)return NaN;
        x=Math.max(0,Math.min(x,g.nx-1));y=Math.max(0,Math.min(y,g.ny-1));
        const x0=Math.floor(x),y0=Math.floor(y),x1=Math.min(x0+1,g.nx-1),y1=Math.min(y0+1,g.ny-1),fx=x-x0,fy=y-y0;
        let sum=0,weight=0;
        for(const [xx,yy,w]of [[x0,y0,(1-fx)*(1-fy)],[x1,y0,fx*(1-fy)],[x0,y1,(1-fx)*fy],[x1,y1,fx*fy]]){
            if(w<=1e-12)continue;const a=value(f,yy*g.nx+xx,k);if(!Number.isFinite(a))return NaN;sum+=a*w;weight+=w;
        }
        return weight?sum/weight:NaN;
    }
    function vertical(f,i,z,levels){if(z<levels[0]||z>levels.at(-1))return NaN;const k=Math.max(0,levels.findIndex(v=>v>=z)-1),a=(z-levels[k])/(levels[k+1]-levels[k]);return value(f,i,k)*(1-a)+value(f,i,k+1)*a;}
    function radar(frame,g,lon,lat,station,elevation=.5,fold=false){
        const i=index(g,lon,lat),east=(lon-station.lon)*111195*Math.cos(station.lat*Math.PI/180),north=(lat-station.lat)*111195,range=Math.hypot(east,north);
        if(i<0||range<2000||range>230000)return {valid:false};
        const angle=elevation*Math.PI/180,r=4/3*6371000,ri=index(g,station.lon,station.lat),rh=value(frame.terrain,ri)||0;
        const beam=rh+Math.sqrt(r*r+range*range+2*r*range*Math.sin(angle))-r,ground=value(frame.terrain,i),z=beam-ground;
        const samples=Math.ceil(range/(g.nominal_km*1000));
        for(let j=1;j<samples;j++){const f=j/samples,d=range*f,k=index(g,station.lon+(lon-station.lon)*f,station.lat+(lat-station.lat)*f),h=rh+Math.sqrt(r*r+d*d+2*r*d*Math.sin(angle))-r;if(value(frame.terrain,k)>h)return {valid:false,blocked:true};}
        const reflectivity=vertical(frame.dbz3,i,z,g.z_agl_m);
        if(!Number.isFinite(reflectivity)||reflectivity<5)return {valid:false};
        const u=vertical(frame.echo_u3||frame.u3,i,z,g.z_agl_m),v=vertical(frame.echo_v3||frame.v3,i,z,g.z_agl_m),w=vertical(frame.w3,i,z,g.z_agl_m),fall=frame.fall3?vertical(frame.fall3,i,z,g.z_agl_m):6,raw=(u*east+v*north)/range*Math.cos(angle)+(w-fall)*Math.sin(angle);
        return {valid:Number.isFinite(raw),dbz:reflectivity,velocity:fold?((raw+25)%50+50)%50-25:raw,range:range/1000,height:beam/1000};
    }
    const api={validateManifest,unpack,index,value,sample,vertical,radar};root.SimulationData=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
