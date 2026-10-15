const assert=require('node:assert/strict');
const M=require('../assets/scripts/simulator-model.js');
const G=require('../assets/scripts/simulator-geo.js');
const catalog=require('../assets/data/simulator-stations.json');
const stations=catalog.stations;
assert.equal(stations.length,160);
assert.equal(new Set(stations.map(s=>s.id)).size,160);
assert.equal(stations.filter(s=>s.province==='广东').length,86);
assert.equal(stations.filter(s=>s.province==='广西').length,74);
assert.ok(stations.every(s=>G.inDomain(s.lon,s.lat)&&/^\d{5}$/.test(s.id)));
assert.equal(stations.find(s=>s.id==='59493').lon,114);
assert.equal(M.validateCustom({name:'outside',lon:0,lat:0}),null);
assert.equal(M.validateCustom({name:'',lon:114,lat:22.5}),null);
assert.equal(M.validateCustom({name:'珠江口',lon:113.74,lat:22.55}).kind,'custom');

const selected=stations.filter(s=>['59493','59488','59287','59431','59663','59265'].includes(s.id));
const baseline=new M.Model({},selected),repeat=new M.Model({},[...selected].reverse());
let total=0,rolling=[],early=0,late=0,earlyTemp=0;
for(let i=0;i<840;i++){
    baseline.step();repeat.step();
    const o=baseline.records.get('59493').obs;
    assert.deepEqual(o,repeat.records.get('59493').obs,'station order must not alter weather or random draws');
    for(const [key,value]of Object.entries(o))if(typeof value==='number')assert.ok(Number.isFinite(value),key);
    assert.ok(o.rain>=0&&o.cape>=0&&o.cin>=0&&o.wind>=0&&o.humidity>=0&&o.humidity<=100);
    assert.ok(o.direction>=0&&o.direction<360);
    total+=o.rain*M.DT;rolling.push(o.rain*M.DT);if(rolling.length>10)rolling.shift();
    assert.ok(Math.abs(o.total-total)<1e-8);assert.ok(Math.abs(o.rain1h-rolling.reduce((a,b)=>a+b,0))<1e-8);
    if(baseline.t<35)early=Math.max(early,baseline.cells.filter(c=>c.family==='trough').length);
    else late=Math.max(late,baseline.cells.filter(c=>c.family==='front').length);
    if(i===50)earlyTemp=o.temp;
}
assert.ok(early>10&&late>10,'default generates two independent convective populations');
assert.ok(baseline.records.get('59493').obs.temp<earlyTemp-3);
assert.ok(baseline.records.get('59493').obs.cape<500,'post-front stable air must reduce CAPE');
assert.deepEqual(baseline.snapshot().cells,repeat.snapshot().cells);

const noTrough=new M.Model({trough:0},selected);
for(let i=0;i<310;i++)noTrough.step();
assert.equal(noTrough.cells.filter(c=>c.family==='trough').length,0);
const marine=G.surface(113.74,22.55),normal=M.parameters({}),noBay=M.parameters({estuary:0});
const bay=M.background(113.74,22.55,24,normal,marine),noMarine=M.background(113.74,22.55,24,noBay,marine);
assert.ok(bay.estuaryLoss>noMarine.estuaryLoss&&bay.cape<noMarine.cape&&bay.temp<noMarine.temp);
const mountain=G.surface(111.18,22.62);
assert.ok(M.background(111.18,22.62,20,normal,mountain).terrainLoss>.3);
assert.equal(M.background(111.18,22.62,20,M.parameters({terrain:0}),mountain).terrainLoss,0);
const fresh=M.background(114,22.54,15,normal),cooled=M.background(114,22.54,15,normal,G.surface(114,22.54),4,.7);
assert.ok(cooled.cape<fresh.cape&&cooled.cin>fresh.cin,'cold pools remove available surface instability');

const radarFrame={t:24,p:M.parameters({terrain:0}),cells:[{lon:114,lat:22.5,shape:1,strength:1,top:12}],coldGrid:new Uint8Array(60*32)};
const westRadar={lon:113.7,lat:22.5,elevation:.5},eastRadar={lon:114.3,lat:22.5,elevation:.5};
const away=M.radarGate(radarFrame,114,22.5,westRadar),toward=M.radarGate(radarFrame,114,22.5,eastRadar);
assert.ok(away.valid&&toward.valid&&away.velocity>0&&toward.velocity<0,'radial sign is radar-relative');
assert.ok(Math.abs(away.velocity-away.u*Math.cos(.5*Math.PI/180))<1e-6);
assert.equal(M.radarGate(radarFrame,114,22.5,{lon:114,lat:22.5}).valid,false,'near-radar blind gate');
assert.equal(M.radarGate(radarFrame,110,22.5,westRadar).valid,false,'out of range');
assert.equal(M.radarGate({...radarFrame,cells:[]},114,22.5,westRadar).valid,false,'no echo means no valid velocity');
const high=M.radarGate(radarFrame,114,22.5,{...westRadar,elevation:2.4});assert.ok(high.height>away.height);
console.log('PASS: 160 source stations, two rounds, deterministic state, rainfall accounting, cooling/recovery, terrain/bay effects, radar geometry and Doppler sign.');
