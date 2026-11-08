"""Attach OSM-tag railway grades to the MLIT passenger line atlas.
Read a Geofabrik Japan PBF from a task temp dir, never put it in the repository.
Requires pyosmium. No geometry is copied from PBF; name/operator tags are grouped.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
import osmium

ROOT=Path(__file__).resolve().parents[2]
JR={'JR北海道':'北海道旅客鉄道','JR東日本':'東日本旅客鉄道','JR東海':'東海旅客鉄道','JR西日本':'西日本旅客鉄道','JR四国':'四国旅客鉄道','JR九州':'九州旅客鉄道'}
BRANDS={'近鉄':'近畿日本鉄道','京阪':'京阪電気鉄道','南海':'南海電気鉄道','小田急':'小田急電鉄','西武':'西武鉄道','東武':'東武鉄道','阪急':'阪急電鉄','阪神':'阪神電気鉄道','京急':'京浜急行電鉄','京王':'京王電鉄','東急':'東急電鉄','京成':'京成電鉄','相鉄':'相模鉄道'}
@lru_cache(maxsize=16384)
def normalize(s):
    s=unicodedata.normalize('NFKC',s or '')
    s=re.sub(r'[（(].*?[)）]','',s)
    return re.sub(r'\s+','',s).replace('本線','線')
def operator(s,operators):
    n=normalize(s)
    for alias,op in {**JR,**BRANDS}.items():
        if normalize(alias) in n:return op
    for op in sorted(operators,key=len,reverse=True):
        if normalize(op) in n:return op
    return None
@lru_cache(maxsize=16384)
def line(s):
    n=normalize(s)
    for prefix in sorted([*JR,*BRANDS,*JR.values(),*BRANDS.values()],key=len,reverse=True):
        if n.startswith(normalize(prefix)):n=n[len(normalize(prefix)):];break
    return n

def enrich(pbf,atlas_path,report_path):
    reader=osmium.io.Reader(str(pbf));snapshot=reader.header().get('osmosis_replication_timestamp');reader.close()
    retrieved=datetime.now(timezone.utc).date().isoformat()
    atlas=json.loads(atlas_path.read_text());ops={f['properties']['operator'] for f in atlas['features']}
    resolve_operator=lru_cache(maxsize=4096)(lambda value:operator(value,ops))
    atlas_operators=defaultdict(set)
    for f in atlas['features']:atlas_operators[line(f['properties']['name'])].add(f['properties']['operator'])
    tagged_operators=defaultdict(set)
    groups=defaultdict(Counter);examples=defaultdict(list)
    class Handler(osmium.SimpleHandler):
        def way(self,w):
            rail=w.tags.get('railway');usage=w.tags.get('usage')
            if rail not in ('rail','tram','light_rail','subway','narrow_gauge'):return
            if w.tags.get('service'):return
            grade=('highspeed' if rail=='rail' and w.tags.get('highspeed')=='yes' else
                   rail if rail in ('tram','light_rail','subway') else
                   usage if usage in ('main','branch','industrial') else None)
            if not grade:return
            op=resolve_operator(w.tags.get('operator') or w.tags.get('owner') or '')
            names=set(line(w.tags.get(k,'')) for k in ('name','name:ja','official_name','alt_name'))-{''}
            for name in names:
                if op:tagged_operators[name].add(op)
                for key in ((op,name),(None,name)) if op else ((None,name),):
                    groups[key][grade]+=1
                    if len(examples[key])<3:examples[key].append(w.id)
    Handler().apply_file(str(pbf),locations=False,filters=[osmium.filter.KeyFilter('railway')])
    report=[]
    for f in atlas['features']:
        prop=f['properties'];name=line(prop['name']);key=(prop['operator'],name);counts=groups.get(key)
        if (not counts and name not in ('線','支線','空港線','連絡線') and len(name)>2
                and atlas_operators[name]=={prop['operator']}
                and tagged_operators[name]<={prop['operator']}):
            key=(None,name);counts=groups.get(key)
        if prop['kind']=='1':grade='highspeed';basis='MLIT 新干线种别'
        elif counts:
            grade,amount=counts.most_common(1)[0]
            if amount/sum(counts.values())<.95:grade='unclassified'
            basis='OSM 同名/同运营方标签归并' if key[0] else 'OSM 同名线路标签归并'
        else:grade='unclassified';basis='缺少可靠等级标签'
        prop['grade']=grade
        report.append({'operator':prop['operator'],'name':prop['name'],'grade':grade,'basis':basis,'counts':dict(counts or {}),'examples':examples.get(key,[])})
    atlas['grade_source']=f'Geofabrik Japan OpenStreetMap extract / {snapshot or retrieved}; named-line aggregation, conflicts left unclassified'
    atlas['license']='OSM-derived grade database: ODbL; MLIT geometry: CC BY 4.0'
    atlas_path.write_text(json.dumps(atlas,ensure_ascii=False,separators=(',',':')))
    report_path.write_text(json.dumps({'source':'https://download.geofabrik.de/asia/japan.html','retrieved':retrieved,'snapshot':snapshot,'license':'OSM ODbL; MLIT CC BY 4.0','method':'按运营方与标准化线名归并；按带标签股道段数量统计，最多等级占比须达到 95%；冲突或缺标签时不猜测。非逐股道等级。','lines':report},ensure_ascii=False,indent=2)+'\n')
    print(dict(Counter(f['properties']['grade'] for f in atlas['features'])))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('pbf',type=Path);p.add_argument('--atlas',type=Path,default=ROOT/'assets/data/jprail/network.geojson');p.add_argument('--report',type=Path,default=ROOT/'assets/data/jprail/grades.json');a=p.parse_args();enrich(a.pbf,a.atlas,a.report)
