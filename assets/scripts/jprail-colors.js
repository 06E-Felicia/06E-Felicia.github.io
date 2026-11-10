// Railway-only color policy. Keep this independent of fare-range selection:
// applying a color must never add, remove or join a pass's geometry.
export const JR_OPERATORS = {'北海道旅客鉄道':'JR 北海道','東日本旅客鉄道':'JR 东日本','東海旅客鉄道':'JR 东海','西日本旅客鉄道':'JR 西日本','四国旅客鉄道':'JR 四国','九州旅客鉄道':'JR 九州'};

export function createRailColors(data) {
 const valid = value => /^#[0-9a-f]{6}$/i.test(value);
 for (const item of [data.jr, data.shinkansen, ...Object.values(data.operators)]) {
  if (!valid(item.color)) throw new Error('Invalid railway palette color');
 }
 for (const target of Object.values(data.aliases)) {
  if (!Object.hasOwn(data.operators,target)) throw new Error('Unknown railway operator alias');
 }
 const operatorOf = value => data.aliases[value] || value;
 const exclusions = new Map(Object.entries(data.excludedLines).map(([op,lines])=>[op,new Set(lines)]));
 const isRailway = feature => {
  const p=feature.properties,op=operatorOf(p.operator);
  return (Object.hasOwn(JR_OPERATORS,op)||Object.hasOwn(data.operators,op)) && !exclusions.get(op)?.has(p.name);
 };
 const forFeature = feature => {
  if (!isRailway(feature)) return null;
  const p=feature.properties,op=operatorOf(p.operator);
  // N02 kind 1 identifies the shinkansen. An underground segment or a
  // third-sector operator's name containing "高速" does not make a subway.
  if (p.kind==='1') return {...data.shinkansen,id:'shinkansen',label:'新干线',operator:op};
  if (Object.hasOwn(JR_OPERATORS,op)) return {...data.jr,id:'jr',label:'JR 普速线路',operator:op};
  return {...data.operators[op],id:'operator:'+op,label:op,operator:op};
 };
 const matchesOperator = (feature,value) => {
  if (!value) return true;
  if (!isRailway(feature)) return false;
  const op=operatorOf(feature.properties.operator);
  return value==='jr' ? Object.hasOwn(JR_OPERATORS,op) : value==='private' ? !Object.hasOwn(JR_OPERATORS,op) : op===operatorOf(value);
 };
 return {operatorOf,isRailway,forFeature,matchesOperator};
}
