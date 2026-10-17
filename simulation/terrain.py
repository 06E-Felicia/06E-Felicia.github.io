"""Real, cached Mapzen/AWS Terrarium elevations. Never invent missing terrain."""
import argparse
import concurrent.futures
import io
import json
import math
import time
import urllib.request
from pathlib import Path
import numpy as np

SOURCE = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'


class TerrainField(np.ndarray):
    """Mean dynamical elevation with unresolved real-DEM relief metadata.

    NumPy consumers still receive an elevation array. Model initialization
    explicitly reads the optional moments before converting to plain arrays;
    a caller-provided flat/synthetic DEM has no hidden geographic obstacles.
    """
    def __new__(cls,height,relief,peak,coverage,land_fraction):
        obj=np.asarray(height).view(cls)
        obj.relief=relief;obj.peak=peak;obj.coverage=coverage;obj.land_fraction=land_fraction
        return obj

    def __array_finalize__(self,obj):
        if obj is not None:
            for name in ['relief','peak','coverage','land_fraction']:setattr(self,name,getattr(obj,name,None))


def coastal_detail(height,lon,lat,km,path):
    """Aggregate cached fine DEM into cell means, relief and peak moments.

    Peak height is NOT installed as a solid grid-cell wall. Its finite land
    coverage/height variance enter subgrid obstruction; mean elevation alone
    is used by the resolved terrain-following solver. No named-city damping.
    """
    path=Path(path)
    if not path.is_file():return height,None
    with np.load(path,allow_pickle=False) as data:
        fine=np.maximum(data['height'],0);b=data['bounds'];resolution=float(data['grid_km'])
        flon,flat=grid(b,resolution)
        if fine.shape!=flon.shape:raise ValueError('Fine DEM coordinates/shape mismatch')
        dx=float(lon[0,1]-lon[0,0]);dy=float(lat[1,0]-lat[0,0])
        ix=np.floor((flon-lon[0,0])/dx+.5).astype(int);iy=np.floor((flat-lat[0,0])/dy+.5).astype(int)
        valid=(ix>=0)&(ix<lon.shape[1])&(iy>=0)&(iy<lon.shape[0])
        bins=(iy[valid]*lon.shape[1]+ix[valid]).ravel();values=fine[valid].ravel();size=lon.size
        count=np.bincount(bins,minlength=size);mean=np.bincount(bins,weights=values,minlength=size)/np.maximum(count,1)
        second=np.bincount(bins,weights=values**2,minlength=size)/np.maximum(count,1)
        cover=np.bincount(bins,weights=values>50,minlength=size)/np.maximum(count,1)
        land=np.bincount(bins,weights=values>0,minlength=size)/np.maximum(count,1)
        peak=np.zeros(size);np.maximum.at(peak,bins,values)
        # Only fully covered cells replace the mean/receive moments; partial
        # boundary samples cannot turn a corner of a fine tile into a ridge.
        full=(lon-dx/2>=b[0])&(lon+dx/2<=b[2])&(lat-dy/2>=b[1])&(lat+dy/2<=b[3])
        full&=count.reshape(lon.shape)>0
        result=np.where(full,mean.reshape(lon.shape),height)
        relief=np.where(full,np.sqrt(np.maximum(second-mean**2,0)).reshape(lon.shape),0)
        peak=np.where(full,peak.reshape(lon.shape),np.maximum(height,0))
        coverage=np.where(full,cover.reshape(lon.shape),0)
        land_fraction=np.where(full,land.reshape(lon.shape),height>0)
        import hashlib
        meta={'source':str(data['source']),'zoom':int(data['zoom']),'grid_km':resolution,
              'bounds':b.tolist(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
              'aggregation':'cell mean, height standard deviation, maximum and >50m fraction; peaks are not full-cell walls'}
        return TerrainField(result,relief,peak,coverage,land_fraction),meta


def grid(bounds, km):
    west, south, east, north = bounds
    dy = km/111.195; dx = km/(111.195*math.cos(math.radians((north+south)/2)))
    lon = np.arange(west, east+dx*.01, dx)
    lat = np.arange(south, north+dy*.01, dy)
    return np.meshgrid(lon, lat)


def mercator(lon, lat, zoom):
    n = 2**zoom
    return (lon+180)/360*n, (1-np.arcsinh(np.tan(np.radians(lat)))/np.pi)/2*n


def download(bounds, km, output, zoom=7):
    lon, lat = grid(bounds, km); tx, ty = mercator(lon, lat, zoom)
    pixels = np.zeros((*lon.shape, 3), dtype=np.uint8)
    tiles = sorted(set(zip(tx.astype(int).ravel(), ty.astype(int).ravel())))
    def fetch(tile):
        from PIL import Image  # only needed to refresh the DEM, not to simulate
        x,y=tile
        for attempt in range(3):
            try:
                req=urllib.request.Request(SOURCE.format(z=zoom,x=x,y=y), headers={'User-Agent':'FeliciaWeatherLab/2.0'})
                with urllib.request.urlopen(req, timeout=40) as res:
                    image=np.asarray(Image.open(io.BytesIO(res.read())).convert('RGB'))
                if image.shape != (256,256,3): raise ValueError('Unexpected DEM tile size')
                return tile,image
            except Exception:
                if attempt==2: raise
                time.sleep(attempt+1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for (x,y), tile in pool.map(fetch, tiles):
            mask=(tx.astype(int)==x)&(ty.astype(int)==y)
            pixels[mask]=tile[np.minimum(255,((ty[mask]-y)*256).astype(int)),np.minimum(255,((tx[mask]-x)*256).astype(int))]
    height=pixels[...,0].astype(float)*256+pixels[...,1]+pixels[...,2]/256-32768
    # Elevation <= 0 is only a coarse sea mask, not a hydrological shoreline.
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output, height=height.astype('float32'),bounds=bounds,grid_km=km,
                        source=SOURCE,zoom=zoom)
    print(json.dumps({'tiles':len(tiles),'shape':height.shape,'range_m':[float(height.min()),float(height.max())],'output':str(output)}))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--config',default='simulation/config.json');ap.add_argument('--output',default='assets/data/simulation-terrain.npz')
    args=ap.parse_args();cfg=json.loads(Path(args.config).read_text());download(cfg['bounds'],cfg['grid_km'],args.output)
