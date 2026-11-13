"""Pack the existing Terrarium DEM as little-endian metres for the Sol Worker."""
from pathlib import Path
import numpy as np

root = Path(__file__).resolve().parents[2] / "assets/data"
with np.load(root / "simulation-terrain.npz") as base, np.load(root / "simulation-terrain-detail.npz") as detail:
    west, south, east, north = base["bounds"]
    lon_km = 111.195 * np.cos(np.deg2rad((north + south) / 2))
    x, y = np.meshgrid(west + (np.arange(560) + .5) * 2.5 / lon_km,
                       south + (np.arange(308) + .5) * 2.5 / 111.195)
    def sample(source):
        w, s, e, n = source["bounds"]
        step = float(source["grid_km"])
        h = source["height"]
        ix = np.clip((x-w)*111.195*np.cos(np.deg2rad((s+n)/2))/step, 0, h.shape[1]-1)
        iy = np.clip((y-s)*111.195/step, 0, h.shape[0]-1)
        i, j = ix.astype(int), iy.astype(int)
        ii, jj = np.minimum(i+1,h.shape[1]-1), np.minimum(j+1,h.shape[0]-1)
        return ((1-(ix-i))*((1-(iy-j))*h[j,i]+(iy-j)*h[jj,i])
                +(ix-i)*((1-(iy-j))*h[j,ii]+(iy-j)*h[jj,ii]))
    heights = sample(base)
    # Use the mean of the fine coastal DEM samples inside each forcing cell.
    w,s,e,n = detail["bounds"]
    dy,dx = np.indices(detail["height"].shape)
    col = ((w-west + dx*.25/(111.195*np.cos(np.deg2rad((s+n)/2))))*lon_km/2.5).astype(int)
    row = ((s-south + dy*.25/111.195)*111.195/2.5).astype(int)
    bins = (row*560+col).ravel()
    count = np.bincount(bins,minlength=heights.size)
    total = np.bincount(bins,weights=detail["height"].ravel(),minlength=heights.size)
    full = count>=90
    heights.flat[full] = total[full]/count[full]
    np.maximum(0,heights).round().astype("<u2").tofile(root/"stormsol-terrain.u16")
