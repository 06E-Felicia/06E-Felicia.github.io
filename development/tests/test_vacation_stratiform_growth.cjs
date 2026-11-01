'use strict';
const assert=require('node:assert/strict'),C=require('../../assets/scripts/vacation-model.js');
const m=Object.create(C.Model.prototype);m.config={stratiformOutflow:true};m.stats={sources:{detrained:0}};m.recordWater=()=>{};let deposited;
m.depositPrecip=function*(array,x,y,major,minor,angle,mass){deposited={major,minor,mass}};m.precipWater={qa:new Float64Array(961),upper_detrained:new Float64Array(961)};
const c={M:123,major:5000,minor:4000,x:10000,y:10000,angle:0};for(const unused of m.detrainCell(c)){}assert.equal(deposited.mass,123);assert.equal(c.M,0);assert(deposited.major<10000&&deposited.minor<10000,'no 28 km instant halo, including dying cells');
m.precip={nx:31,ny:31,n:961,dx:2000};m.cold={index:()=>0};m._buffers=new Map();m.background=()=>({windAngle:0});m._coldMaturity=()=>0;m.precipWater.qa[480]=1;
const moment=()=>m.precipWater.qa.reduce((s,v,k)=>s+v*((k%31-15)**2+(Math.floor(k/31)-15)**2),0);
for(const unused of m._spreadStratiform()){}const young=moment();assert(Math.abs(m.precipWater.qa.reduce((a,b)=>a+b,0)-1)<1e-12);assert(m.precipWater.qa.every(v=>v>=0));
m.precipWater.qa.fill(0);m.precipWater.qa[480]=1;m._coldMaturity=()=>1;for(const unused of m._spreadStratiform()){}const mature=moment();assert(young<mature*.2,'new clouds expand gradually before mature outflow');assert(m.precipWater.qa[481]>m.precipWater.qa[511],'spreading is anisotropic');console.log(JSON.stringify({pass:true,initialDetrainFootprintM:deposited,youngSpreadMoment:young,matureSpreadMoment:mature,condensateConserved:true}));
