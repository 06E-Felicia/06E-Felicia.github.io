"""Compile official named intervals without rectangular cuts or invented links.

Use one detailed topology for both zoom levels. Every alternative railway path
on a station-to-station interval is retained (parallel tracks / real loops).
Dead-end branches must be declared independently or included as a whole line.
Requires Shapely and networkx; performs no downloads.
"""
from pathlib import Path
from collections import defaultdict
from functools import lru_cache
import json
import math
import networkx as nx
from shapely.geometry import LineString, Point, mapping
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'assets/data/jprail'

def build(network_path=DATA/'network-detail.geojson',output_path=DATA/'pass-ranges-detail.json',simplify=0):
    atlas=json.loads(network_path.read_text())
    passes=json.loads((DATA/'passes.json').read_text())['passes']
    stations=json.loads((DATA/'stations.json').read_text())
    features={(f['properties']['operator'],f['properties']['name']):f for f in atlas['features']}
    @lru_cache(None)
    def topology(op,name):
        f=features[op,name];g=nx.Graph()
        lines=f['geometry']['coordinates'] if f['geometry']['type']=='MultiLineString' else [f['geometry']['coordinates']]
        for line in lines:
            for u,v in zip(line,line[1:]):
                raw_u,raw_v=tuple(u),tuple(v)
                # N02 adjoining features differ in sub-metre precision. This
                # key only joins their shared node; it never adds a bridge.
                u,v=tuple(round(x,5) for x in u),tuple(round(x,5) for x in v)
                if u!=v:g.add_edge(u,v,weight=math.dist(raw_u,raw_v),coords=[raw_u,raw_v])
        blocks=list(nx.biconnected_components(g));tree=nx.Graph();membership=defaultdict(list)
        for i,block in enumerate(blocks):
            for node in block:membership[node].append(i)
        for node,ids in membership.items():
            if len(ids)>1:
                for i in ids:tree.add_edge(('cut',node),('block',i))
        return g,blocks,tree,membership,list(nx.connected_components(g))
    @lru_cache(None)
    def section_geometry(op,name,a,b):
        g,blocks,tree,membership,components=topology(op,name)
        # A station may have disconnected platform/gauge geometries in N02.
        # Choose a pair on the same real component; never bridge components.
        def station_rows(name):
            return [s for s in stations if s[0]==name and s[3]==op] or [s for s in stations if s[0]==name]
        options=[]
        for component in components:
            da,start=min((math.dist(n,(s[2],s[1])),n) for s in station_rows(a) for n in component)
            db,end=min((math.dist(n,(s[2],s[1])),n) for s in station_rows(b) for n in component)
            if da<.01 and db<.01 and start!=end:options.append((da+db,start,end))
        if not options:
            raise ValueError(f'No actual N02 component connects stations {a}–{b}')
        _,start,end=min(options)
        def tree_node(n):return ('cut',n) if len(membership[n])>1 else ('block',membership[n][0])
        st,en=tree_node(start),tree_node(end)
        path=[st] if st==en else nx.shortest_path(tree,st,en)
        selected=set()
        for kind,i in path:
            if kind=='block':
                for u,v in g.subgraph(blocks[i]).edges():selected.add(tuple(sorted((u,v))))
        if not selected:raise ValueError(f'No connected interval: {name} {a}–{b}')
        geom=unary_union([LineString(g[u][v]['coords']) for u,v in selected])
        return geom
    result={};errors=[]
    for p in passes:
        sections=p.get('railSections') or p.get('railOverrides')
        if not sections:continue
        selected=defaultdict(list)
        for op,name,a,b in sections:
            try:selected[op,name].append(section_geometry(op,name,a,b))
            except Exception as e:errors.append(f'{p["id"]}: {op} {name} {a}–{b}: {e}')
        output=[];station_keys=[]
        for key,parts in selected.items():
            geom=unary_union(parts)
            for s in stations:
                if (s[3],s[4])==key and geom.distance(Point(s[2],s[1]))<.0018:station_keys.append('|'.join([s[3],s[4],s[0]]))
            # linemerge prevents making every raw N02 edge a separate painted
            # fragment. Simplification uses the same connected route at both LODs.
            from shapely.ops import linemerge
            if geom.geom_type=='MultiLineString':geom=linemerge(geom)
            if simplify:geom=geom.simplify(simplify,preserve_topology=True)
            output.append({'type':'Feature','properties':features[key]['properties'],'geometry':mapping(geom)})
        result[p['id']]={'partial':bool(p.get('railOverrides')),'features':output,'stationKeys':sorted(set(station_keys)),'source':p['stationPins']['source'],'method':'官方命名区间；N02 实际拓扑中的全部通路，分支另行声明；不作直线补接'}
    if errors:raise ValueError('\n'.join(errors))
    output_path.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print({k:len(v['features']) for k,v in result.items()})

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--network',type=Path,default=DATA/'network-detail.geojson');parser.add_argument('--output',type=Path,default=DATA/'pass-ranges-detail.json');parser.add_argument('--simplify',type=float,default=0);args=parser.parse_args();build(args.network,args.output,args.simplify)
