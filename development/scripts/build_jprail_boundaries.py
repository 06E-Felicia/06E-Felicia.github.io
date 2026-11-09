"""Build JR company boundary station references from the bundled N02 atlas."""
import json,math
from pathlib import Path
from collections import Counter
D=Path(__file__).resolve().parents[2]/'assets/data/jprail'
a=json.loads((D/'network.geojson').read_text());stations=json.loads((D/'stations.json').read_text())
ops={'北海道旅客鉄道','東日本旅客鉄道','東海旅客鉄道','西日本旅客鉄道','四国旅客鉄道','九州旅客鉄道'}
ends=[]
for f in a['features']:
 p=f['properties']
 if p['operator'] not in ops or p['kind'] not in ['1','2']:continue
 lines=f['geometry']['coordinates'] if f['geometry']['type']=='MultiLineString' else [f['geometry']['coordinates']]
 count=Counter(tuple(round(v,5) for v in xy) for line in lines for xy in [line[0],line[-1]])
 for xy,n in count.items():
  ends.append((xy,p))
def dist(a,b):return math.hypot((a[0]-b[0])*math.cos(math.radians(a[1]))*111320,(a[1]-b[1])*111320)
found=[];seen=set()
for i,(xy,p) in enumerate(ends):
 for other,q in ends[:i]:
  if p['operator']==q['operator'] or p['kind']!=q['kind'] or (p['kind']!='1' and p['name']!=q['name']):continue
  if dist(xy,other)>250:continue
  station=min(stations,key=lambda s:dist(xy,[s[2],s[1]]))
  if dist(xy,[station[2],station[1]])>600:continue
  key=(station[0],*sorted([p['operator'],q['operator']]),p['kind'])
  if key in seen:continue
  seen.add(key)
  found.append({'name':station[0],'lat':station[1],'lon':station[2],'sides':[{'operator':p['operator'],'line':p['name'],'kind':p['kind'],'point':xy},{'operator':q['operator'],'line':q['name'],'kind':q['kind'],'point':other}]})
result={'source':a['source'],'license':'CC BY 4.0 (MLIT N02-25)','method':'N02 中 JR 公司线路端点邻接；同类铁路相接且最近车站在 600 米内。常规铁路要求线名相同，新干线允许在换乘站相接。不是逐股道或票价规则证明。','boundaries':found}
(D/'company-boundaries.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
print('JR operating boundaries:',len(found))
