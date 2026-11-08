"""Build named station-to-station ranges for verified pass sections.
Uses the local N02 atlas only. Requires Shapely and networkx.
No clipping-box edge is treated as an official fare boundary.
"""
from pathlib import Path
from collections import defaultdict
import json
import math
import networkx as nx
from shapely.geometry import LineString,shape,mapping
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'assets/data/jprail'

def build(network_path=DATA/'network.geojson',output_path=DATA/'pass-ranges.json'):
    atlas=json.loads(network_path.read_text())
    passes=json.loads((DATA/'passes.json').read_text())['passes']
    stations=json.loads((DATA/'stations.json').read_text())
    result={}
    for p in passes:
        if not p.get('railSections'):continue
        selected=defaultdict(list);props={}
        for section in p['railSections']:
            op,name,a,b=section
            f=next(f for f in atlas['features'] if f['properties']['operator']==op and f['properties']['name']==name)
            g=nx.Graph()
            lines=f['geometry']['coordinates'] if f['geometry']['type']=='MultiLineString' else [f['geometry']['coordinates']]
            for line in lines:
                for u,v in zip(line,line[1:]):
                    raw_u,raw_v=tuple(u),tuple(v)
                    u,v=tuple(round(x,5) for x in u),tuple(round(x,5) for x in v)
                    if u!=v:g.add_edge(u,v,weight=math.dist(raw_u,raw_v),coords=[raw_u,raw_v])
            def station_node(station):
                candidates=[s for s in stations if s[0]==station and s[3]==op] or [s for s in stations if s[0]==station]
                matches=[(math.dist(n,(s[2],s[1])),n) for s in candidates for n in g]
                distance,node=min(matches)
                if distance>.01:raise ValueError(f'{p["id"]}: {station} too far from {name}')
                return node
            route=nx.shortest_path(g,station_node(a),station_node(b),weight='weight')
            if len(route)<2:raise ValueError(f'{p["id"]}: empty section {a}-{b}')
            key=(op,name);coords=[]
            for u,v in zip(route,route[1:]):
                edge=g[u][v]['coords']
                if tuple(round(x,5) for x in edge[0])!=u:edge=list(reversed(edge))
                if coords and coords[-1]==edge[0]:coords.extend(edge[1:])
                else:coords.extend(edge)
            selected[key].append(LineString(coords));props[key]=f['properties']
        features=[];station_keys=[]
        for key,parts in selected.items():
            geom=unary_union(parts)
            features.append({'type':'Feature','properties':props[key],'geometry':mapping(geom)})
            for s in stations:
                if (s[3],s[4])!=key:continue
                from shapely.geometry import Point
                if geom.distance(Point(s[2],s[1]))<.0018:station_keys.append('|'.join([s[3],s[4],s[0]]))
        result[p['id']]={'features':features,'stationKeys':station_keys,'source':p['stationPins']['source'],'method':'N02 线网内按官方列明起讫站取路径，非区域框裁切'}
    output_path.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print({k:len(v['features']) for k,v in result.items()})

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--network',type=Path,default=DATA/'network.geojson');parser.add_argument('--output',type=Path,default=DATA/'pass-ranges.json');args=parser.parse_args();build(args.network,args.output)
