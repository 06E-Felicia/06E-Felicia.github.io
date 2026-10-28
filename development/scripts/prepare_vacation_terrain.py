#!/usr/bin/env python3
"""Build the Vacation 1.2 fixed forcing geometry from real, attributed DEMs.

Requires numpy, scipy, pillow, pyproj and scikit-image. Existing NPZ caches are
reused; only uncovered samples fetch AWS Terrarium tiles. Downloads are cached
outside the repository by default. Missing downloads abort the build: they
never become ocean. Run from any directory; all repository paths are absolute.

python development/scripts/prepare_vacation_terrain.py --cache /tmp/vacation-terrain-tiles
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import math
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import CRS, Proj, Transformer
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.spatial import cKDTree
from skimage.measure import find_contours

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
AEQD = "+proj=aeqd +lat_0=22.5 +lon_0=112 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
DX = 2500.0
NX, NY, PAD = 512, 320, 60
EX, EY = NX + 2 * PAD, NY + 2 * PAD
X0, Y0 = -NX * DX / 2, -NY * DX / 2
EXT_X0, EXT_Y0 = X0 - DX * PAD, Y0 - DX * PAD


def cache_grid(path):
    with np.load(path, allow_pickle=False) as data:
        bounds = data["bounds"].tolist()
        dy = float(data["grid_km"]) / 111.195
        dx = dy / math.cos(math.radians((bounds[1] + bounds[3]) / 2))
        return {
            "height": data["height"].astype(np.float64), "bounds": bounds,
            "dx": dx, "dy": dy,
            "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }


def sample_cache(cache, lon, lat):
    west, south, east, north = cache["bounds"]
    x, y = (lon - west) / cache["dx"], (lat - south) / cache["dy"]
    ny, nx = cache["height"].shape
    valid = (x >= 0) & (x <= nx - 1) & (y >= 0) & (y <= ny - 1)
    # Cache bounds can extend beyond its last actual node; validity uses actual
    # node coverage, rather than silently extending the last row/column.
    result = np.full(lon.shape, np.nan)
    result[valid] = map_coordinates(cache["height"], [y[valid], x[valid]],
                                    order=1, mode="nearest")
    return result, valid


def mercator_pixels(lon, lat, zoom):
    size = 256 * 2 ** zoom
    return ((lon + 180) / 360 * size,
            (1 - np.arcsinh(np.tan(np.deg2rad(lat))) / np.pi) / 2 * size)


def fetch_tiles(lon, lat, zoom, directory):
    px, py = mercator_pixels(lon, lat, zoom)
    # Pixel values are samples at their centres; request both nodes for a
    # bilinear reconstruction, including neighbour tiles at tile boundaries.
    ix, iy = np.floor(px - .5).astype(int), np.floor(py - .5).astype(int)
    tile_ids = set()
    for ox, oy in [(0, 0), (1, 0), (0, 1), (1, 1)]:
        tile_ids.update(zip(((ix + ox) // 256).ravel(), ((iy + oy) // 256).ravel()))
    directory.mkdir(parents=True, exist_ok=True)

    def load(tile):
        tx, ty = map(int, tile)
        path = directory / f"{zoom}-{tx}-{ty}.png"
        if not path.is_file():
            for attempt in range(4):
                try:
                    request = urllib.request.Request(SOURCE.format(z=zoom, x=tx, y=ty),
                                                     headers={"User-Agent": "VacationTerrain/1.2"})
                    with urllib.request.urlopen(request, timeout=45) as response:
                        payload = response.read()
                    pixels = np.asarray(Image.open(io.BytesIO(payload)).convert("RGB"))
                    if pixels.shape != (256, 256, 3):
                        raise ValueError(f"Invalid terrain tile {tile}: {pixels.shape}")
                    path.write_bytes(payload)
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(attempt + 1)
        pixels = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
        height = pixels[..., 0] * 256 + pixels[..., 1] + pixels[..., 2] / 256 - 32768
        return (tx, ty), height, hashlib.sha256(path.read_bytes()).hexdigest()

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(load, sorted(tile_ids)))
    tiles = {key: height for key, height, _ in records}
    print(json.dumps({"downloaded_or_reused_terrarium_tiles": len(tiles), "zoom": zoom}), flush=True)
    wx, wy = px - .5 - ix, py - .5 - iy
    values = np.zeros(lon.shape)
    for ox, oy, weights in [(0, 0, (1 - wx) * (1 - wy)),
                            (1, 0, wx * (1 - wy)),
                            (0, 1, (1 - wx) * wy),
                            (1, 1, wx * wy)]:
        sx, sy = ix + ox, iy + oy
        tile_x, tile_y = sx // 256, sy // 256
        for (tx, ty), tile in tiles.items():
            mask = (tile_x == tx) & (tile_y == ty)
            values[mask] += weights[mask] * tile[sy[mask] % 256, sx[mask] % 256]
    manifests = [{"z": zoom, "x": key[0], "y": key[1], "sha256": checksum}
                 for key, _, checksum in records]
    return values, manifests


def geometry(z, land, xx, yy):
    # Input grid includes the required 150 km halo. Reflect only acts at the
    # external data boundary, at least 150 km from the simulation rectangle.
    ls = np.clip(gaussian_filter(land, 10000 / DX, mode="reflect", truncate=3), 0, 1)
    zs = gaussian_filter(z, 3500 / DX, mode="reflect", truncate=3)
    zy, zx = np.gradient(zs, DX, DX)
    ly, lx = np.gradient(ls, DX, DX)
    contours = find_contours(ls, .5)
    points, normals, lengths, lines, starts, ends = [], [], [], [], [], []
    degenerate = 0
    for line in contours:
        # Marching-squares vertices become linear coast segments; subdivide to
        # at most 2.5 km and evaluate normals at arc-length midpoints.
        coords = np.column_stack((EXT_X0 + (line[:, 1] + .5) * DX,
                                  EXT_Y0 + (line[:, 0] + .5) * DX))
        lines.append(np.round(coords, 1).tolist())
        for a, b in zip(coords[:-1], coords[1:]):
            distance = np.linalg.norm(b - a)
            count = max(1, int(np.ceil(distance / DX)))
            for index in range(count):
                start = a + (b - a) * index / count
                end = a + (b - a) * (index + 1) / count
                mid = (start + end) / 2
                gx = (mid[0] - EXT_X0) / DX - .5
                gy = (mid[1] - EXT_Y0) / DX - .5
                nx = map_coordinates(lx, [[gy], [gx]], order=1, mode="nearest")[0]
                ny = map_coordinates(ly, [[gy], [gx]], order=1, mode="nearest")[0]
                norm = math.hypot(nx, ny)
                starts.append(start)
                ends.append(end)
                if norm < 1e-8:
                    degenerate += 1
                    continue
                points.append(mid)
                normals.append([nx / norm, ny / norm])
                lengths.append(distance / count)
    coast_x = np.zeros_like(z)
    coast_y = np.zeros_like(z)
    weights = np.zeros_like(z)
    for point, normal, length in zip(points, normals, lengths):
        cx, cy = point
        left = max(0, int(np.floor((cx - 120000 - EXT_X0) / DX)))
        right = min(EX, int(np.ceil((cx + 120000 - EXT_X0) / DX)))
        bottom = max(0, int(np.floor((cy - 120000 - EXT_Y0) / DX)))
        top = min(EY, int(np.ceil((cy + 120000 - EXT_Y0) / DX)))
        distances2 = (xx[bottom:top, left:right] - cx) ** 2 + (yy[bottom:top, left:right] - cy) ** 2
        weight = np.exp(-distances2 / (2 * 40000 ** 2)) * length
        weight[distances2 > 120000 ** 2] = 0
        weights[bottom:top, left:right] += weight
        coast_x[bottom:top, left:right] += weight * normal[0]
        coast_y[bottom:top, left:right] += weight * normal[1]
    nonzero = weights > 0
    coast_x[nonzero] /= weights[nonzero]
    coast_y[nonzero] /= weights[nonzero]
    if starts:
        a, b = np.asarray(starts), np.asarray(ends)
        middle, delta = (a + b) / 2, b - a
        tree = cKDTree(middle)
        query = np.column_stack((xx.ravel(), yy.ravel()))
        # Eight closest short segments include the nearest coast segment for
        # this 2.5 km marching-squares geometry. Compute point-to-segment distance
        # (not distance to a raster node or coastline sample).
        _, candidates = tree.query(query, k=min(8, len(a)))
        if candidates.ndim == 1:
            candidates = candidates[:, None]
        target_a, target_delta = a[candidates], delta[candidates]
        position = query[:, None, :] - target_a
        fraction = np.clip(np.sum(position * target_delta, axis=-1) /
                           np.maximum(np.sum(target_delta ** 2, axis=-1), 1e-20), 0, 1)
        distance = np.sqrt(np.min(np.sum((position - fraction[..., None] * target_delta) ** 2,
                                        axis=-1), axis=1)).reshape(z.shape)
        signed_distance = distance * np.where(ls >= .5, 1, -1)
    else:
        signed_distance = np.full_like(z, 1e9 if np.all(ls >= .5) else -1e9)
    slope = np.hypot(zx, zy)
    normal_x = np.divide(zx, slope, out=np.zeros_like(z), where=slope >= 1e-6)
    normal_y = np.divide(zy, slope, out=np.zeros_like(z), where=slope >= 1e-6)
    beta = .55 * (1 - np.exp(-np.maximum(zs, 0) / 600)) * np.clip(slope / .015, 0, 1)
    beta[slope < 1e-6] = 0
    project = Transformer.from_crs("EPSG:4326", CRS.from_proj4(AEQD), always_xy=True)
    jet_a, jet_b = np.array(project.transform(111.8, 20)), np.array(project.transform(114.2, 24.2))
    jet_e = (jet_b - jet_a) / np.linalg.norm(jet_b - jet_a)
    cross = (xx - jet_a[0]) * -jet_e[1] + (yy - jet_a[1]) * jet_e[0]
    jet = .6 + .4 * np.exp(-cross ** 2 / (2 * 120000 ** 2))
    return ({"z": z, "land": land, "zs": zs, "zx": zx, "zy": zy,
             "signedDistance": signed_distance, "coastX": coast_x, "coastY": coast_y,
             "jetJ": jet, "beta": beta, "normalX": normal_x, "normalY": normal_y, "ls": ls},
            {"coastSegments": len(starts), "coastNormalSamples": len(points),
             "degenerateCoastNormalFraction": degenerate / max(1, len(starts)),
             "maxCoastVectorLength": float(np.max(np.hypot(coast_x, coast_y))),
             "jetA": jet_a.tolist(), "jetB": jet_b.tolist(), "jetDirection": jet_e.tolist(),
             "upperCenter": (jet_a + 400000 * jet_e).tolist()}, lines)


def build(args):
    inverse = Transformer.from_crs(CRS.from_proj4(AEQD), "EPSG:4326", always_xy=True)
    xx, yy = np.meshgrid(EXT_X0 + (np.arange(EX) + .5) * DX,
                         EXT_Y0 + (np.arange(EY) + .5) * DX)
    coarse = cache_grid(ROOT / "assets/data/simulation-terrain.npz")
    detail = cache_grid(ROOT / "assets/data/simulation-terrain-detail.npz")
    total_samples = args.supersample ** 2
    # Equal-area quadrature in the model projection. Sampling is explicitly a
    # quadrature of cached data, never a claim of new 625 m terrain resolution.
    offsets = ((np.arange(args.supersample) + .5) / args.supersample - .5) * DX
    sample_x = np.concatenate([(xx + ox).ravel() for oy in offsets for ox in offsets])
    sample_y = np.concatenate([(yy + oy).ravel() for oy in offsets for ox in offsets])
    lon, lat = inverse.transform(sample_x, sample_y)
    height, covered = sample_cache(coarse, lon, lat)
    sources = np.where(covered, 1, 0).astype(np.uint8)
    fine, fine_covered = sample_cache(detail, lon, lat)
    height[fine_covered] = fine[fine_covered]
    sources[fine_covered] = 2
    missing = ~np.isfinite(height)
    tile_manifest = []
    if missing.any():
        height[missing], tile_manifest = fetch_tiles(lon[missing], lat[missing], args.zoom, args.cache)
        sources[missing] = 4
    if not np.isfinite(height).all() or np.any(sources == 0):
        raise ValueError("Uncovered terrain samples remain; refusing to substitute ocean")
    z = np.maximum(height, 0).reshape(total_samples, EY, EX).mean(axis=0)
    land = (height > 0).reshape(total_samples, EY, EX).mean(axis=0)
    source_cells = np.bitwise_or.reduce(sources.reshape(total_samples, EY, EX), axis=0)
    fields, diagnostics, coastlines = geometry(z, land, xx, yy)
    fields["coverage"] = np.ones_like(z)
    fields["sourceMask"] = source_cells
    units = {"z": "m", "zs": "m", "zx": "m/m", "zy": "m/m", "signedDistance": "m"}
    output = ROOT / "assets/data/vacation-terrain.bin"
    position = 0
    main_fields, extended_fields = {}, {}
    with output.open("wb") as handle:
        for group, selection in [(main_fields, np.s_[PAD:PAD + NY, PAD:PAD + NX]),
                                 (extended_fields, np.s_[:, :])]:
            for name, values in fields.items():
                values = np.asarray(values[selection], dtype="<f4", order="C")
                count = values.size
                group[name] = {"offsetBytes": position, "offset": position // 4,
                               "count": count, "length": count, "units": units.get(name, "1")}
                handle.write(values.tobytes(order="C"))
                position += count * 4
    corners = []
    projection = Proj(AEQD)
    for x, y in [(X0, Y0), (-X0, Y0), (-X0, -Y0), (X0, -Y0)]:
        cl, ct = inverse.transform(x, y)
        factors = projection.get_factors(cl, ct)
        corners.append({"x": x, "y": y, "lon": cl, "lat": ct,
                        "meridionalScale": factors.meridional_scale,
                        "parallelScale": factors.parallel_scale,
                        "maxPrincipalScaleError": max(abs(factors.tissot_semimajor - 1),
                                                       abs(factors.tissot_semiminor - 1))})
    inside = np.s_[PAD:PAD + NY, PAD:PAD + NX]
    source_fractions = {name: float(np.mean(sources == code))
                        for name, code in [("existing4km", 1), ("existing025km", 2), ("newTerrarium", 4)]}
    metadata = {
        "schema": "vacation-terrain-1.2", "generator": "development/scripts/prepare_vacation_terrain.py",
        "description": "真实DEM生成的静态环境几何，非实况、非预报。海陆比例为DEM高程>0的代理。",
        "dtype": "Float32", "endian": "little", "layout": "row-major; rows south to north; x east, y north",
        "binary": "vacation-terrain.bin", "binaryBytes": position,
        "binarySha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "projection": AEQD, "center": [112, 22.5], "nx": NX, "ny": NY,
        "dx": DX, "dy": DX, "origin": [X0, Y0], "cellCentered": True,
        "fields": main_fields,
        "extended": {"nx": EX, "ny": EY, "dx": DX, "dy": DX,
                     "origin": [EXT_X0, EXT_Y0], "haloCells": PAD, "haloMeters": PAD * DX},
        "extendedFields": extended_fields, "corners": corners,
        "geoBounds": {"west": float(lon.min()), "east": float(lon.max()),
                      "south": float(lat.min()), "north": float(lat.max())},
        "mainGeoBounds": {"west": float(inverse.transform(xx[inside], yy[inside])[0].min()),
                          "east": float(inverse.transform(xx[inside], yy[inside])[0].max()),
                          "south": float(inverse.transform(xx[inside], yy[inside])[1].min()),
                          "north": float(inverse.transform(xx[inside], yy[inside])[1].max())},
        "smoothing": {"landSigmaM": 10000, "terrainSigmaM": 3500, "windSigmaM": 5000,
                      "coastSigmaM": 40000, "gaussianTruncateSigma": 3},
        "sourceMaskBits": {"1": "existing 4 km DEM", "2": "existing 0.25 km estuary DEM", "4": "new Terrarium samples"},
        "sourceFractionsByQuadratureSample": source_fractions,
        "coverage": {"validFraction": 1, "missingSampleCount": 0,
                     "sampleCount": len(height), "supersamplePerAxis": args.supersample},
        "sources": [{key: value for key, value in cache.items() if key not in ("height", "dx", "dy")}
                    for cache in [coarse, detail]],
        "terrariumSource": SOURCE, "newTerrariumZoom": args.zoom,
        "newTileManifest": tile_manifest,
        "attribution": "Mapzen/Tilezen; SRTM and GMTED2010 courtesy USGS; ETOPO1 NOAA",
        "licenseFile": "vacation-terrain-LICENSE.md",
        "limitations": ["Land fraction uses positive DEM height, not a hydrological coastline mask; inland lakes may appear as land.",
                        "4 km cache upsampling adds no terrain detail; source resolution changes in the halo are retained in sourceMask.",
                        "Cell means use 4 by 4 projected equal-area quadrature; source caches remain their original resolutions."],
        "jetDirection": diagnostics["jetDirection"],
        "upperCenter": diagnostics["upperCenter"],
        "diagnostics": diagnostics,
        "ranges": {name: [float(np.min(values[inside])), float(np.max(values[inside]))]
                   for name, values in fields.items()},
    }
    (ROOT / "assets/data/vacation-terrain.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "assets/data/vacation-coastlines.json").write_text(json.dumps({
        "projection": AEQD, "geometry": "smoothed DEM land-proxy 0.5 contours",
        "coordinates": coastlines,
    }, separators=(",", ":")) + "\n")
    print(json.dumps({"binaryBytes": position, "coverage": metadata["coverage"],
                      "sourceFractions": source_fractions, "diagnostics": diagnostics,
                      "ranges": metadata["ranges"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("/tmp/vacation-terrain-tiles"))
    parser.add_argument("--zoom", type=int, default=8)
    parser.add_argument("--supersample", type=int, default=4)
    build(parser.parse_args())
