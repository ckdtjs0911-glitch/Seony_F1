"""Fit attributed map pit-lane geometry to a session's arbitrary telemetry frame."""
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GEOMETRY=ROOT/'reports'/'geometry'


def sample_closed(points,n=256):
    import numpy as np
    p=np.asarray(points,dtype=float)
    if not np.allclose(p[0],p[-1]):p=np.vstack([p,p[0]])
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(p,axis=0),axis=1))]
    target=np.linspace(0,lengths[-1],n,endpoint=False)
    return np.column_stack([np.interp(target,lengths,p[:,i]) for i in range(2)])


def fit_outline(source,target):
    import numpy as np
    a=sample_closed(source);b=sample_closed(target);best=None
    for reverse in [False,True]:
        src=a[::-1] if reverse else a
        center=src.mean(axis=0);x=src-center
        for shift in range(len(b)):
            dst=np.roll(b,shift,axis=0);y=dst-dst.mean(axis=0)
            u,s,v=np.linalg.svd(x.T@y);rotation=u@v
            scale=s.sum()/(x*x).sum();offset=dst.mean(axis=0)-center@rotation*scale
            error=float(np.sqrt(np.mean(np.sum((src@rotation*scale+offset-dst)**2,axis=1))))
            if best is None or error<best[0]:best=(error,rotation,scale,offset)
    return best


def mapped_pit(snapshot,track):
    session=snapshot.get('session',{})
    code='us-2023' if session.get('location')=='Las Vegas' else 'br-1940' if session.get('country_name')=='Brazil' else None
    if not code or len(track)<12:return None
    import numpy as np
    path=GEOMETRY/f'{code}-pit-osm.json';outline=GEOMETRY/f'{code}-circuit.geojson'
    if not path.exists() or not outline.exists():return None
    circuit=json.loads(outline.read_text(encoding='utf-8'))['features'][0]['geometry']['coordinates']
    lon,lat=circuit[0];cos=math.cos(math.radians(lat))
    def project(p):return [(p[0]-lon)*111320*cos,(p[1]-lat)*111320]
    source=[project(p) for p in circuit]
    error,rotation,scale,offset=fit_outline(source,track)
    extent=float(np.linalg.norm(np.ptp(np.asarray(track),axis=0)))
    if not extent:return None
    normalized=error/extent
    if not np.isfinite(normalized) or normalized>.015:return {'error':normalized,'segments':[]}
    raw=json.loads(path.read_text(encoding='utf-8'));segments=[];ways=[]
    for way in raw['elements']:
        if way.get('tags',{}).get('highway')!='raceway':continue
        pts=np.asarray([project([p['lon'],p['lat']]) for p in way['geometry']]);mapped=pts@rotation*scale+offset
        segments.append(mapped.tolist());ways.append(f'https://www.openstreetmap.org/way/{way["id"]}')
    return {'segments':segments,'error':normalized,'source':ways,'attribution':'© OpenStreetMap contributors · ODbL 1.0','license':'https://www.openstreetmap.org/copyright','outline_source':f'https://github.com/bacinger/f1-circuits/blob/master/circuits/{code}.geojson','note':'지도 경로를 세션 좌표에 근사 정합한 참고선이며 실제 차량의 피트 이동 궤적이 아닙니다.'}


def enrich_mapped_pit(snapshot,value):
    result=mapped_pit(snapshot,value.get('track',[]))
    if result and result.get('segments'):
        value['pit_reference']=result
    return bool(result and result.get('segments'))
