#!/usr/bin/env python3
"""
Livestock density as numbers the map can raise into relief (round 95b, asked 27
September: "make the livestock density layer hypsometric not by altitude but
density"), as ghsl_pop.py does for people.

Source: FAO, Gridded Livestock of the World 4, 2020, 10 km (the D-DA mapset:
head, or birds, per square km; CC BY 4.0), one GeoTIFF per animal:
https://storage.googleapis.com/fao-gismgr-glw4-2020-data/DATA/GLW4-2020/MAPSET/D-DA/GLW4-2020.D-DA.<CODE>.tif
CTL cattle, BFL buffaloes, SHP sheep, GTS goats, PGS pigs, CHK chickens.

  tiles/glw_<code>.pmtiles   zooms 0 to 5, 256-pixel squares, each pixel the
                             animals per square km coded as a height tile
                             (Mapbox's code: -10000 + (R*65536 + G*256 + B)/10)
  tiles/glw_relief.build.json  each animal's file and its 99th percentile

Built once; GLW_REBUILD=1 builds again.
"""
import io, json, math, os, pathlib, sys, tempfile, urllib.request

BASE = "https://storage.googleapis.com/fao-gismgr-glw4-2020-data/DATA/GLW4-2020/MAPSET/D-DA/GLW4-2020.D-DA.{}.tif"
KINDS = ["CTL", "BFL", "SHP", "GTS", "PGS", "CHK"]
TOP = 5
N = 256
STAMP = pathlib.Path("tiles/glw_relief.build.json")


def lat_of(ty, z):
    n = math.pi - 2 * math.pi * ty / 2 ** z
    return math.degrees(math.atan(math.sinh(n)))


def main():
    if STAMP.exists() and not os.environ.get("GLW_REBUILD"):
        print("glw_relief: already built")
        return
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "rasterio", "numpy", "pillow", "pmtiles"], check=True)
    import numpy as np
    import rasterio
    from PIL import Image
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer
    stamp = {}
    for code in KINDS:
        url = BASE.format(code)
        tmp = pathlib.Path(tempfile.gettempdir()) / f"glw_{code}.tif"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Culprits atlas build"}), timeout=900) as r:
            tmp.write_bytes(r.read())
        with rasterio.open(tmp) as src:
            a = src.read(1).astype(np.float32)
            nod = src.nodata
            t = src.transform
        if nod is not None:
            a[a == nod] = 0
        a[~np.isfinite(a) | (a < 0)] = 0
        west, north, res_x, res_y = t.c, t.f, t.a, -t.e
        H, W = a.shape
        tiles = {}
        for z in range(TOP + 1):
            n = 2 ** z
            for ty in range(n):
                lats = np.array([lat_of(ty + (j + 0.5) / N, z) for j in range(N)])
                rows = np.clip(((north - lats) / res_y).astype(int), 0, H - 1)
                inside_r = (lats <= north) & (lats >= north - H * res_y)
                for tx in range(n):
                    lons = -180 + 360 * (tx + (np.arange(N) + 0.5) / N) / n
                    cols = np.clip(((lons - west) / res_x).astype(int), 0, W - 1)
                    d = a[rows][:, cols]
                    d[~inside_r, :] = 0
                    if not d.any():
                        continue
                    code_ = np.round((np.clip(d, 0, 1_600_000) + 10000) * 10).astype(np.uint32)
                    rgb = np.stack([(code_ >> 16) & 255, (code_ >> 8) & 255, code_ & 255], axis=-1).astype(np.uint8)
                    buf = io.BytesIO()
                    Image.fromarray(rgb, "RGB").save(buf, "PNG", optimize=True)
                    tiles[zxy_to_tileid(z, tx, ty)] = buf.getvalue()
        out = pathlib.Path("tiles") / f"glw_{code.lower()}.pmtiles"
        with open(out, "wb") as f:
            w = Writer(f)
            for tid in sorted(tiles):
                w.write_tile(tid, tiles[tid])
            w.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": 0, "max_zoom": TOP,
                        "min_lon_e7": -1800000000, "min_lat_e7": -850000000, "max_lon_e7": 1800000000, "max_lat_e7": 850000000,
                        "center_zoom": 1, "center_lon_e7": 0, "center_lat_e7": 0},
                       {"attribution": "FAO GLW4 2020 (CC BY 4.0)", "name": out.stem, "encoding": "mapbox"})
        pos = a[a > 0]
        stamp[code] = {"from": url, "squares": len(tiles), "bytes": out.stat().st_size,
                       "p99": float(np.percentile(pos, 99)) if pos.size else 0, "max": float(pos.max()) if pos.size else 0}
        print(f"glw_relief: {code}: {len(tiles)} squares, 99th percentile {stamp[code]['p99']:.0f} per km2", flush=True)
    STAMP.write_text(json.dumps(stamp, indent=1))


if __name__ == "__main__":
    main()
