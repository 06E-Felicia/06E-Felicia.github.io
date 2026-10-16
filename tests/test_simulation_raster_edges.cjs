/* Synthetic display fixture only. No model, Pyodide or weather integration. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
function field(value,volume=false){const shape=volume?[14,6,8]:[6,8],data=Buffer.alloc(shape.reduce((a,b)=>a*b,1)*2);for(let i=0;i<data.length;i+=2)data.writeInt16LE(1,i);return {shape,scale:1,offset:value-1,data:data.toString('base64')};}
const fields=Object.fromEntries(['temperature','dewpoint','rainrate','rain_total','rain_hour','sbcape','mlcape','mucape','cin','terrain','coldair','u10','v10','gust','composite'].map(k=>[k,field(k==='temperature'?24:k==='composite'?40:k==='rainrate'?.5:k==='coldair'?.5:0)]));
for(const k of ['t3','q3','p3','u3','v3','w3','dbz3'])fields[k]=field(k==='p3'?1000:0,true);
const manifest={schema:2,config:{hours:1,month:4,frame_minutes:60,bounds:[104.3,19.8,111.3,24.8]},grid:{nx:8,ny:6,west:104.3,south:19.8,dlon:1,dlat:1,nominal_km:100,z_agl_m:[30,150,350,650,1000,1500,2200,3200,4500,6000,8000,10500,13500,16500]},frames:[]};
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.TEST_BROWSER_CHANNEL||'chrome'});
 try{
  for(const file of ['simulator.html','simulator-sol.html']){
   const context=await browser.newContext(),page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   await context.addInitScript(({manifest,fields})=>{window.Worker=class{
    constructor(){this.index=0;}
    emit(){this.onmessage({data:{type:'frame',index:this.index,hour:this.index,raw:JSON.stringify({schema:2,hour:this.index,fields})}});}
    postMessage(m){if(m.type==='start'){this.onmessage({data:{type:'manifest',manifest}});this.emit();}else if(m.type==='ack'){if(++this.index<2)this.emit();else this.onmessage({data:{type:'complete'}});}}
    terminate(){}
   };},{manifest,fields});
   const root=path.resolve(__dirname,'..');await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.origin!=='http://127.0.0.1:14331')return route.abort();const file=path.resolve(root,'.'+u.pathname);if(!file.startsWith(root+path.sep)||!fs.existsSync(file))return route.fulfill({status:404,body:''});return route.fulfill({path:file});});
   await page.goto('http://127.0.0.1:14331/'+file);await page.waitForFunction(()=>window.Simulator&&!document.querySelector('#start-simulation').disabled);
   await page.locator('#local-hours').fill('1');await page.locator('#flow-rate').selectOption('0');await page.locator('#basemap').selectOption('none');await page.locator('#start-simulation').click();
   await page.waitForFunction(()=>Simulator.getState().playbackState==='ended');
   for(const key of ['temperature','rainrate']){
    await page.locator('.map-card select').first().selectOption(key);
    const result=await page.locator('.weather-raster').first().evaluate(async image=>{await image.decode();const canvas=document.createElement('canvas');canvas.width=image.naturalWidth;canvas.height=image.naturalHeight;const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data,edge=[],inside=[];for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++)(x===0||y===0||x===canvas.width-1||y===canvas.height-1?edge:inside).push(pixels[(y*canvas.width+x)*4+3]);return {width:canvas.width,height:canvas.height,edge,inside};});
    assert.equal(result.width,16);assert.equal(result.height,12);assert.ok(result.edge.every(a=>a===0),'outside-domain pixels must be no-data');assert.ok(result.inside.every(a=>a===255),'valid interior light rain must NOT be hidden');
   }
   assert.deepEqual(errors,[]);await context.close();
  }
  console.log('PASS Astra/Sol: exterior half-cells transparent, interior legitimate drizzle retained, no stretching; synthetic display only');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
