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
