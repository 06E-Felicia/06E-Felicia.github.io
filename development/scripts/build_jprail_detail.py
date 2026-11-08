"""Retain the original N02 railway curves for close map views.
Raw archives belong in a task temp dir, not the repository.
"""
from pathlib import Path
from collections import defaultdict
from shapely.geometry import shape,mapping
from shapely.ops import unary_union
import zipfile,json
ROOT=Path(__file__).resolve().parents[2]
data=ROOT/'assets/data/jprail'
import argparse
parser=argparse.ArgumentParser();parser.add_argument('archive',type=Path);args=parser.parse_args()
with zipfile.ZipFile(args.archive) as z:
 name=next(n for n in z.namelist() if n.endswith('RailroadSection.geojson') and 'UTF-8' in n)
 raw=json.loads(z.read(name))
old=json.loads((data/'network.geojson').read_text());props={(f['properties']['operator'],f['properties']['name'],f['properties']['kind']):f['properties'] for f in old['features']}
groups=defaultdict(list)
for f in raw['features']:
 p=f['properties'];key=(p['N02_004'],p['N02_003'],p['N02_002']);groups[key].append(shape(f['geometry']))
features=[]
for key,items in sorted(groups.items()):
 geom=unary_union(items)
 f={'type':'Feature','properties':props[key],'bbox':list(geom.bounds),'geometry':mapping(geom)};features.append(f)
 if key[0]=='近畿日本鉄道' and key[1] in ('奈良線','橿原線','京都線'):
  lines=list(geom.geoms) if geom.geom_type=='MultiLineString' else [geom]
  print(key[1],'raw points',sum(len(l.coords) for l in lines),'segments',len(lines),flush=True)
atlas={'type':'FeatureCollection','source':old['source'],'grade_source':old.get('grade_source'),'license':old.get('license'),'geometryNote':'N02-25 source geometry retained without simplification; no interpolation','features':features}
text=json.dumps(atlas,ensure_ascii=False,separators=(',',':'))
# Source precision is retained to seven decimal places (sub-metre coordinates).
import re
text=re.sub(r'-?\d+\.\d{8,}',lambda m:format(float(m[0]),'.7f').rstrip('0').rstrip('.'),text)
(data/'network-detail.geojson').write_text(text)
print('Detailed atlas bytes',len(text.encode()),'features',len(features),flush=True)
