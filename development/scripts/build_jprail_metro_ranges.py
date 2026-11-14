"""Compile metro browsing ranges as complete, real station-to-station paths.

Stations are projected onto their own N02 operator/line only. Outside stations
split the graph; retain the block-cut subtree joining at least two in-range
stations. This keeps real parallel paths without inventing bridges or cutting
tracks at an arbitrary radius. No downloads or scratch files in the project.
"""
from collections import defaultdict, deque
from pathlib import Path
import argparse
import json
import math
import networkx as nx
from shapely.geometry import LineString, Point, mapping
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'assets/data/jprail'
JR={'北海道旅客鉄道','東日本旅客鉄道','東海旅客鉄道','西日本旅客鉄道','四国旅客鉄道','九州旅客鉄道'}


def inside(station,metro):
    return any(math.hypot((station[2]-c['lng'])*111.195*math.cos(math.radians(c['lat'])),(station[1]-c['lat'])*111.195)<=c['km']+1e-8 for c in metro['circles'])


def node(point):
    return tuple(round(v,5) for v in point)


def station_graph(feature,stations):
    lines=feature['geometry']['coordinates'] if feature['geometry']['type']=='MultiLineString' else [feature['geometry']['coordinates']]
    raw=[(a,b) for line in lines for a,b in zip(line,line[1:]) if a!=b]
    geometries=[LineString(pair) for pair in raw];index=STRtree(geometries)
    splits=defaultdict(list);anchors=defaultdict(list)
    for station in stations:
        point=Point(station[2],station[1]);i=int(index.nearest(point));edge=geometries[i]
        if edge.distance(point)>.0018:
            raise ValueError('Station too far from its own line: '+str(station))
        t=edge.project(point,normalized=True);p=edge.interpolate(t,normalized=True)
        xy=(p.x,p.y);splits[i].append((t,xy));anchors[node(xy)].append(station)
    graph=nx.Graph();coords={}
    for i,(a,b) in enumerate(raw):
        points=[(0,tuple(a)),*splits[i],(1,tuple(b))];points.sort(key=lambda x:x[0])
        for (_,a),(_,b) in zip(points,points[1:]):
            u,v=node(a),node(b)
            if u==v:continue
            coords.setdefault(u,a);coords.setdefault(v,b)
            graph.add_edge(u,v,coords=[a,b])
    return graph,anchors,coords


def station_paths(graph,anchors,metro):
    allowed={n:[s for s in ss if inside(s,metro)] for n,ss in anchors.items()}
    eligible={n for n,ss in allowed.items() if ss}
    if len({s[0] for ss in allowed.values() for s in ss})<2:return set(),allowed
    remaining=graph.subgraph(set(graph)- (set(anchors)-eligible))
    selected=set()
    for component in nx.connected_components(remaining):
        terminals=eligible&component
        if len({s[0] for n in terminals for s in allowed[n]})<2:continue
        sub=remaining.subgraph(component);blocks=list(nx.biconnected_components(sub))
        membership=defaultdict(list);tree=nx.Graph()
        for i,block in enumerate(blocks):
            tree.add_node(('block',i))
            for n in block:membership[n].append(i)
        for n,ids in membership.items():
            if len(ids)>1:
                for i in ids:tree.add_edge(('cut',n),('block',i))
        required={('cut',n) if len(membership[n])>1 else ('block',membership[n][0]) for n in terminals if membership[n]}
        keep=set(tree);degree=dict(tree.degree());queue=deque(n for n in keep if degree[n]<=1 and n not in required)
        while queue:
            n=queue.popleft()
            if n not in keep:continue
            keep.remove(n)
            for other in tree[n]:
                degree[other]-=1
                if other in keep and degree[other]<=1 and other not in required:queue.append(other)
        for kind,i in keep:
            if kind=='block':
                selected.update(tuple(sorted((u,v))) for u,v in sub.subgraph(blocks[i]).edges())
    if selected:
        drawn=graph.edge_subgraph(selected)
        if any(n not in eligible for n,d in drawn.degree() if d==1):
            raise ValueError('A metro boundary did not end at a station')
    return selected,allowed


def build(output=DATA/'metro-ranges.json'):
    config=json.loads((DATA/'line-filters.json').read_text());palette=json.loads((DATA/'operator-colors.json').read_text())
    atlas=json.loads((DATA/'network-detail.geojson').read_text())
    stations=defaultdict(list)
    for s in json.loads((DATA/'stations.json').read_text()):stations[s[3],s[4]].append(s)
    result={m['id']:{'overview':[],'detail':[],'stations':[]} for m in config['metros']}
    for feature in atlas['features']:
        p=feature['properties'];op=palette['aliases'].get(p['operator'],p['operator'])
        if op not in JR|set(palette['operators']) or p['name'] in palette['excludedLines'].get(op,[]):continue
        ss=stations[p['operator'],p['name']]
        metros=[m for m in config['metros'] if len({s[0] for s in ss if inside(s,m)})>=2]
        if not metros:continue
        graph,anchors,coords=station_graph(feature,ss)
        for metro in metros:
            edges,allowed=station_paths(graph,anchors,metro)
            if not edges:continue
            lines=unary_union([LineString(graph[u][v]['coords']) for u,v in edges])
            if lines.geom_type=='MultiLineString':lines=linemerge(lines)
            record={'type':'Feature','properties':p,'geometry':mapping(lines)}
            item=result[metro['id']];item['detail'].append(record)
            item['overview'].append({**record,'geometry':mapping(lines.simplify(.001,preserve_topology=True))})
            drawn=graph.edge_subgraph(edges)
            seen=set()
            for n in drawn:
                for s in allowed.get(n,[]):
                    xy=coords[n];identity=(s[0],*xy,s[3],s[4])
                    if identity in seen:continue
                    seen.add(identity)
                    item['stations'].append([s[0],xy[1],xy[0],s[3],s[4],drawn.degree(n)==1])
    for item in result.values():
        item['stations'].sort(key=lambda s:(s[3],s[4],s[0],s[1],s[2]))
    document={'version':'2026-11-14-metro-reference','source':atlas['source'],'grade_source':atlas.get('grade_source'),'license':atlas.get('license'),'method':'保留新干线及车站资料供参考；范围内车站间的实际N02路径，遇范围外车站中断，不跨接缺口。站点投影到同运营方同线路原轨迹；两档共用一份拓扑，端点不随缩放改变。彩色匹配规则由筛选器单独决定。','metros':result}
    output.write_text(json.dumps(document,ensure_ascii=False,separators=(',',':'))+'\n')
    stats={k:{'routes':len(v['detail']),'stations':len(v['stations']),'ends':sum(s[5] for s in v['stations'])} for k,v in result.items()}
    print(json.dumps({'bytes':output.stat().st_size,'metros':stats},ensure_ascii=False),flush=True)
    return document


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DATA/'metro-ranges.json')
    build(parser.parse_args().output)
