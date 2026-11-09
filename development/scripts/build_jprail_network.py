"""Build a compact passenger rail atlas from MLIT N02 GeoJSON (CC BY 4.0).
Usage: python build_jprail_network.py /path/to/N02-25_GML/UTF-8
The source archive and intermediate files belong in a task-specific temp dir.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[2]

def build(source, target):
    raw=json.loads(next(source.glob('*RailroadSection.geojson')).read_text())
    groups=defaultdict(list)
    for feature in raw['features']:
        p=feature['properties']
        groups[(p['N02_004'],p['N02_003'],p['N02_002'])].append(shape(feature['geometry']))
    features=[]
    for (operator,name,kind),items in sorted(groups.items()):
        geom=unary_union(items).simplify(.00045,preserve_topology=False)
        features.append({'type':'Feature','properties':{'operator':operator,'name':name,'kind':kind},'geometry':mapping(geom)})
    atlas={'type':'FeatureCollection','source':'国土数値情報 N02-25 / 2025-12-31','features':features}
    target.mkdir(parents=True,exist_ok=True)
    text=json.dumps(atlas,ensure_ascii=False,separators=(',',':'))
    import re
    text=re.sub(r'-?\d+\.\d{5,}',lambda m:format(float(m[0]),'.5f').rstrip('0').rstrip('.'),text)
    (target/'network.geojson').write_text(text)
    result=build_stations(source,target)
    print(f'{len(features)} operator/line groups, {len(result)} station entries; network {len(text.encode()):,} bytes')

def build_stations(source,target):
    stations=json.loads(next(source.glob('*Station.geojson')).read_text())
    result=[];seen=set()
    for f in stations['features']:
        p=f['properties'];c=shape(f['geometry']).centroid
        # Preserve operator and line identities at shared stations. Dropping
        # these previously lost shinkansen labels and chose wrong boundaries.
        key=(p['N02_005'],p['N02_004'],p['N02_003'],round(c.x,5),round(c.y,5))
        if key in seen:continue
        seen.add(key)
        result.append([p['N02_005'],round(c.y,5),round(c.x,5),p['N02_004'],p['N02_003']])
    (target/'stations.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--output',type=Path,default=ROOT/'assets/data/jprail');p.add_argument('--stations-only',action='store_true');a=p.parse_args();(build_stations if a.stations_only else build)(a.source,a.output)
