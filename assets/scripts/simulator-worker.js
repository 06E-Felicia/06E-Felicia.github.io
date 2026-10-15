'use strict';
importScripts('simulator-geo.js','simulator-model.js');
let model=null,history=[],revision=0,configuration=null;
self.onmessage=async ({data})=>{
    const rev=++revision;
    try {
        if(data.type==='init') {
            configuration={p:data.p,stations:data.stations};
            model=new StormModel.Model(data.p,data.stations);history=[model.snapshot()];
        }
        if(!model)return;
        const target=Math.min(Math.round((data.time||0)/StormModel.DT),Math.round(model.duration/StormModel.DT));
        while(history.length<=target) {
            for(let i=0;i<18&&history.length<=target;i++){model.step();history.push(model.snapshot());}
            if(rev!==revision)return;
            self.postMessage({type:'progress',request:data.request,value:(history.length-1)/Math.max(1,target)});
            await new Promise(resolve=>setTimeout(resolve,0));
            if(rev!==revision)return;
        }
        // Only send the selected station's series; all stations remain selectable.
        const id=data.station;
        const series=history.slice(0,target+1).map(f=>({t:f.t,...f.observations[id]}));
        self.postMessage({type:'frame',request:data.request,frame:history[target],series});
    } catch(error){self.postMessage({type:'error',request:data.request,message:error.message});}
};
