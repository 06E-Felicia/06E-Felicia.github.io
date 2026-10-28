/* Preserve small PRD hills from the existing 250 m DEM without changing mean
 * terrain used by transport. Requires Python + numpy; optional --python PATH. */
'use strict';
const fs=require('node:fs'),path=require('node:path'),cp=require('node:child_process'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'../..'),source=path.join(root,'assets/data/simulation-terrain-detail.npz'),file=path.join(root,'assets/data/vacation-terrain.json');
const python=process.argv.includes('--python')?process.argv[process.argv.indexOf('--python')+1]:'python3';
const data=JSON.parse(cp.execFileSync(python,['-c',"import numpy as np,json,sys; d=np.load(sys.argv[1]); print(json.dumps({'bounds':d['bounds'].tolist(),'km':float(d['grid_km']),'height':d['height'].tolist()}))",source],{maxBuffer:32*1024*1024}));
const meta=JSON.parse(fs.readFileSync(file)),projection=require('../../assets/vendor/proj4/proj4.js')('EPSG:4326',meta.projection),[west,south,,north]=data.bounds,dy=data.km/111.195,dx=dy/Math.cos((south+north)/2*Math.PI/180),cells=new Map();
for(let j=0;j<data.height.length;j++)for(let i=0;i<data.height[j].length;i++){
 const q=projection.forward([west+i*dx,south+j*dy]),x=Math.floor((q[0]-meta.origin[0])/meta.dx),y=Math.floor((q[1]-meta.origin[1])/meta.dy);
 if(x<0||y<0||x>=meta.nx||y>=meta.ny)continue;
 const k=y*meta.nx+x,z=Math.max(0,data.height[j][i]),c=cells.get(k)||[0,0,0];c[0]=Math.max(c[0],z);c[1]+=z>0?1:0;c[2]++;cells.set(k,c);
}
meta.subgridTerrain={generator:'development/scripts/prepare_vacation_subgrid.cjs',source:'simulation-terrain-detail.npz',sourceSha256:crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex'),description:'250 m DEM peaks and land fraction; forcing-grid index, peak metres, land fraction. Does not replace transport mean elevation.',cells:[...cells].filter(([,c])=>c[0]>0).sort((a,b)=>a[0]-b[0]).map(([k,c])=>[k,Math.round(c[0]),Math.round(c[1]/c[2]*1000)/1000])};
fs.writeFileSync(file,JSON.stringify(meta,null,2)+'\n');
console.log(JSON.stringify({cells:meta.subgridTerrain.cells.length,bytes:fs.statSync(file).size}));
