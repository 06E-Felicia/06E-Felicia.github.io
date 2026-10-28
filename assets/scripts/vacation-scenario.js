/* Shared production scenario generation for the Worker and archive recorder. */
(function(root){
  'use strict';
  const C=root.VacationCore||(typeof require==='function'?require('./vacation-model.js'):null);
  function generate(config,entropy){
    const seed=config.seed??entropy;
    if(!Number.isInteger(seed))throw Error('缺少有效的后台随机种子');
    const rng=C.random(C.hash(seed,'scenario'));
    // The automatic experience targets warm-sector training. The contrasting
    // afternoon and fast-line regimes remain available as explicit configurations.
    const groups=['coastal','terrain'],group=config.scenarioGroup||groups[C.hash(seed,'group')%groups.length];
    return {...config,weatherRegion:config.weatherRegion||'auto',scenarioGroup:group,seed,hours:config.hours??72,controls:config.controls||{flow:.8+.4*rng(),humidity:-.035+.07*rng()}};
  }
  root.VacationScenario={generate};if(typeof module!=='undefined')module.exports={generate};
})(typeof self!=='undefined'?self:globalThis);
