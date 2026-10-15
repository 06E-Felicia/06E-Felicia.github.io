/* Conceptual coastal/terrain geometry, NOT a surveyed DEM or boundary map. */
(function (root) {
    'use strict';
    const bounds = { west: 104.3, east: 118, south: 19.8, north: 26.7 };
    const coast = [[104.3,19.8],[106.1,20.3],[107.4,21.2],[108,21.52],[108.55,21.8],
        [109.15,21.5],[109.6,21.5],[109.78,21.2],[109.85,20.35],[110.16,20.18],
        [110.5,20.55],[110.55,21.18],[110.95,21.45],[111.45,21.5],[111.98,21.8],
        [112.5,21.86],[113.02,22.02],[113.6,22.22],[113.6,22.45],[113.54,22.65],
        [113.6,22.83],[113.72,22.88],[113.79,22.69],[113.88,22.53],[114.03,22.49],
        [114.1,22.28],[114.3,22.23],[114.45,22.46],[114.68,22.65],[115.35,22.75],
        [115.85,22.82],[116.4,23.05],[116.75,23.32],[117.2,23.6],[118,24.05]];
    const land = [...coast, [118,26.7], [104.3,26.7]];
    const ridges = [
        ['桂西山地',105.9,24.5,1.1,.8,25,1050], ['九万大山',108.5,25.0,.95,.33,35,1200],
        ['大瑶山',110.15,24.12,.65,.28,55,1350], ['十万大山',107.85,22.08,.78,.19,20,1000],
        ['大容山',110.25,22.82,.44,.22,35,1000], ['云开大山',111.18,22.62,.8,.27,40,1300],
        ['天露山',112.4,22.65,.5,.15,35,850], ['南岭',112.9,25.05,2.3,.36,8,1450],
        ['莲花山脉',115.05,23.43,1.5,.23,35,1100], ['深圳东部山地',114.4,22.63,.34,.11,20,640]
    ];
    const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
    function inside(lon, lat, polygon = land) {
        let yes = false;
        for (let i=0,j=polygon.length-1;i<polygon.length;j=i++) {
            const [x,y]=polygon[i], [xj,yj]=polygon[j];
            if (((y>lat)!==(yj>lat)) && lon<(xj-x)*(lat-y)/(yj-y)+x) yes=!yes;
        }
        return yes;
    }
    function gaussian(lon, lat, x, y, sx, sy, angle=0) {
        const r=angle*Math.PI/180, dx=lon-x, dy=lat-y;
        return Math.exp(-.5*(((dx*Math.cos(r)+dy*Math.sin(r))/sx)**2
            +((-dx*Math.sin(r)+dy*Math.cos(r))/sy)**2));
    }
    function surface(lon, lat) {
        const water=!inside(lon,lat);
        let height=0;
        if (!water) {
            height=28;
            for (const [,x,y,sx,sy,a,h] of ridges) height+=h*gaussian(lon,lat,x,y,sx,sy,a);
            height*=1-.82*gaussian(lon,lat,113.2,22.9,.7,.45);
            height*=1-.85*gaussian(lon,lat,113.92,22.57,.30,.13);
        }
        const estuary=gaussian(lon,lat,113.74,22.55,.17,.27,-12);
        // A small east-bank marine influence represents low-level inflow from the bay.
        const marine=clamp(estuary + .36*gaussian(lon,lat,113.98,22.56,.22,.18));
        return {water,height,estuary,marine};
    }
    function inDomain(lon,lat) {
        return Number.isFinite(lon)&&Number.isFinite(lat)&&lon>=bounds.west&&lon<=bounds.east
            &&lat>=bounds.south&&lat<=bounds.north;
    }
    const api={bounds,coast,land,ridges,clamp,inside,gaussian,surface,inDomain};
    root.StormGeo=api;
    if(typeof module!=='undefined') module.exports=api;
})(globalThis);
