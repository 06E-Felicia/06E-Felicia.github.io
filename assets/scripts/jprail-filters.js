import {JR_OPERATORS,isSeikanShared} from './jprail-colors.js?v=20261113-seikan18';

export const ROUTE_GRADES = {
 highspeed:'新干线',main:'本线（含转交区段）',branch:'地方／其他 JR 线',private:'私铁线'
};
const key = f => f.properties.operator+'|'+f.properties.name;
const rad = Math.PI/180,KM=111.195;

export function createRouteFilters(data,colors,metroRanges) {
 const families=new Map(data.families.map(f=>[f.id,f])),metros=new Map(data.metros.map(m=>[m.id,m]));
 const members=new Map();
 for(const family of data.families){
  for(const op of Object.keys(JR_OPERATORS))for(const name of family.jrNames)members.set(op+'|'+name,family);
  for(const [op,name] of family.transfers)members.set(op+'|'+name,family);
 }
 const familyOf=f=>members.get(key(f));
 const highspeed=f=>f.properties.kind==='1'||isSeikanShared(f);
 const gradeOf=f=>!colors.isRailway(f)?null:highspeed(f)?'highspeed':familyOf(f)?'main':Object.hasOwn(JR_OPERATORS,f.properties.operator)?'branch':'private';
 const active=f=>Boolean(f.grade||f.line||f.metro||f.operators?.length);
 const matches=(feature,filter={})=>{
  if(!active(filter))return true;
  if(!colors.isRailway(feature))return false;
  if(filter.metro&&highspeed(feature))return false;
  const op=colors.operatorOf(feature.properties.operator),grade=gradeOf(feature);
  if(filter.operators?.length&&!filter.operators.some(value=>colors.matchesOperator(feature,value)))return false;
  if(filter.grade==='private'){
   if(Object.hasOwn(JR_OPERATORS,op)||highspeed(feature))return false;
  }else if(filter.grade&&grade!==filter.grade)return false;
  return !filter.line||familyOf(feature)?.id===filter.line;
 };
 const contains=(lng,lat,metroId)=>{
  const metro=metros.get(metroId);if(!metro)return true;
  return metro.circles.some(c=>((lng-c.lng)*KM*Math.cos(c.lat*rad))**2+((lat-c.lat)*KM)**2<=c.km**2+1e-7);
 };
 const metroRange=(id,level='overview')=>metroRanges.metros[id]?.[level]||[];
 const metroStations=id=>metroRanges.metros[id]?.stations||[];
 const apply=(features,filter,level='overview')=>{
  if(!metros.has(filter.metro))return features.filter(f=>matches(f,filter));
  const keys=new Set(features.map(key));
  return metroRange(filter.metro,level).filter(f=>keys.has(key(f))&&matches(f,filter));
 };
 return {data,families,metros,familyOf,gradeOf,highspeed,active,matches,contains,apply,metroRange,metroStations};
}

// Native details + checkboxes allow mouse, touch and keyboard multi-selection.
// Keep the select as the serializable state (and support old single-op URLs).
export function createOperatorPicker(select,picker,colors,network,onChange) {
 const $=id=>document.getElementById(id),summary=picker.querySelector('summary'),list=$('railOperatorList');
 const operators=[...new Set(network.features.filter(colors.isRailway).map(f=>colors.operatorOf(f.properties.operator)))];
 operators.sort((a,b)=>(Object.hasOwn(JR_OPERATORS,b)-Object.hasOwn(JR_OPERATORS,a))||a.localeCompare(b,'ja'));
 select.replaceChildren(new Option('全部运营方',''),new Option('JR 六家公司','jr'),new Option('私铁／第三部门','private'),...operators.map(op=>new Option(JR_OPERATORS[op]||op,op)));
 const rows=new Map(),groups=new Map();
 for(const [group,label] of [['jr','JR 六家公司'],['private','私铁／第三部门／公营铁路']]){
  const section=document.createElement('fieldset'),legend=document.createElement('legend');legend.textContent=label;section.append(legend);
  for(const op of operators.filter(op=>(group==='jr')===Object.hasOwn(JR_OPERATORS,op))){
   const row=document.createElement('label'),input=document.createElement('input'),span=document.createElement('span');
   input.type='checkbox';input.value=op;input.dataset.railOperator=op;span.textContent=JR_OPERATORS[op]||op;
   row.append(input,span);section.append(row);rows.set(op,{row,input});
   input.addEventListener('change',()=>{const next=new Set(expanded());input.checked?next.add(op):next.delete(op);set([...next]);onChange();});
  }
  list.append(section);groups.set(group,section);
 }
 const values=()=>[...select.selectedOptions].map(o=>o.value).filter(Boolean);
 const expanded=()=>operators.filter(op=>values().some(v=>v===op||v==='jr'&&Object.hasOwn(JR_OPERATORS,op)||v==='private'&&!Object.hasOwn(JR_OPERATORS,op)));
 function sync(){
  const selected=new Set(expanded());for(const [op,{input}] of rows)input.checked=selected.has(op);
  const labels=[...selected].map(op=>JR_OPERATORS[op]||op);
  summary.querySelector('span').textContent=labels.length===0?'全部运营方':labels.length===1?labels[0]:`已选 ${labels.length} 家运营方`;
  summary.title=labels.join('、')||'全部运营方';
 }
 function set(next){for(const option of select.options)option.selected=next.includes(option.value);sync();}
 const urlValues=()=>{
  const selected=new Set(expanded()),include=[],exclude=[];
  for(const group of ['jr','private']){
   const targets=operators.filter(op=>(group==='jr')===Object.hasOwn(JR_OPERATORS,op));
   const chosen=targets.filter(op=>selected.has(op));
   if(chosen.length>targets.length/2){include.push(group);exclude.push(...targets.filter(op=>!selected.has(op)));}
   else include.push(...chosen);
  }
  return {include,exclude};
 };
 $('railOperatorSearch').addEventListener('input',e=>{
  const normalize=s=>s.replace(/\s/g,'').toLocaleLowerCase(),q=normalize(e.target.value);let count=0;
  for(const [op,{row}] of rows){row.hidden=!normalize([op,JR_OPERATORS[op]||''].join(' ')).includes(q);if(!row.hidden)count++;}
  for(const section of groups.values())section.hidden=![...section.querySelectorAll('label')].some(row=>!row.hidden);
  $('railOperatorEmpty').hidden=count>0;
 });
 for(const button of picker.querySelectorAll('[data-operator-group]'))button.addEventListener('click',()=>{
  const next=new Set(expanded()),group=button.dataset.operatorGroup,targets=operators.filter(op=>group==='all'||(group==='jr')===Object.hasOwn(JR_OPERATORS,op));
  const remove=targets.every(op=>next.has(op));for(const op of targets)remove?next.delete(op):next.add(op);set([...next]);onChange();
 });
 $('railOperatorClear').addEventListener('click',()=>{set([]);onChange();});
 select.addEventListener('change',()=>{sync();onChange();});
 const positionMenu=()=>{
  if(!picker.open)return;
  const bar=picker.closest('.rail-filter-bar').getBoundingClientRect(),anchor=picker.getBoundingClientRect(),menu=picker.querySelector('.operator-menu');
  const width=Math.min(420,bar.width-16),left=Math.max(bar.left+8,Math.min(anchor.left,bar.right-width-8));
  menu.style.width=width+'px';menu.style.left=(left-anchor.left)+'px';
 };
 picker.addEventListener('toggle',positionMenu);
 new ResizeObserver(positionMenu).observe(picker.closest('.rail-filter-bar'));
 picker.addEventListener('keydown',e=>{if(e.key==='Escape'){picker.open=false;summary.focus();}});
 document.addEventListener('pointerdown',e=>{if(!picker.contains(e.target))picker.open=false;});
 sync();return {values,set,sync,urlValues,operators};
}
