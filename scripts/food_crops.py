#!/usr/bin/env python3
"""
Soy and maize (corn): the four pressures of growing them, food and feed
together, mapped for 2017 by Halpern et al. 2022, "The environmental footprint
of global food production" (Nature Sustainability), from their data package
(Frazier et al., Global food system pressure data, KNB doi:10.5063/F1V69H1B).

From crops_food_feed_raw.zip, as its listing gives them (scripts/food_list.py):
  gall_peter_land_{soyb,maiz}_crop_produce_{ghg,water,nutrient,disturbance}_per_cell.tif
each is turned into a raster archive the map draws square by square:
  tiles/food_{soyb,maiz}_{ghg,water,nutrient,disturbance}.pmtiles
and its colour steps into food/<same name>.key.json (the package's own figure
at each step, so the map can say what a colour stands for).

Only those eight files are read out of the 271 MB zip (by byte range, where KNB
allows it). The rasters are in Gall-Peters; each square of the map is warped
from them to web mercator at zooms 0 to 6, the largest value in the square
kept, so a strong spot does not disappear wider out. Colours go from dark plum
to bone on a log scale, cut at the values' own quantiles; empty and zero cells
are left clear. Nothing is dropped.

By hand only (Actions tab, "food_crops"); the package is a fixed 2017 release.
"""
import io, json, math, os, pathlib, struct, subprocess, sys, urllib.request, zlib

ZIP = "https://knb.ecoinformatics.org/knb/d1/mn/v2/object/urn%3Auuid%3A50cdc537-c52d-4b1c-8a51-2ba72fc36b27"
CROPS = {"soyb": "soy", "maiz": "maize (corn)"}
PRESSURES = ["ghg", "water", "nutrient", "disturbance"]
MAXZOOM = 6
RAMP = [(0x2E, 0x24, 0x33), (0x4F, 0x34, 0x4A), (0x74, 0x4A, 0x5E), (0x9A, 0x6C, 0x78), (0xC0, 0x9E, 0x9A), (0xE6, 0xD9, 0xC8)]
UA = {"User-Agent": "Culprits atlas (food pressure rasters)"}
WORLD = 20037508.342789244


def need():
    try:
        import numpy, rasterio, pmtiles, PIL  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "numpy", "rasterio", "pmtiles", "pillow"], check=True)


def get(url, rng=None):
    h = dict(UA, Range=f"bytes={rng[0]}-{rng[1]}") if rng else UA
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=600) as r:
        return r.status, r.read()


def members(wanted):
    """The wanted files' bytes, read out of the zip by byte range."""
    req = urllib.request.Request(ZIP, headers=UA, method="HEAD")
    with urllib.request.urlopen(req, timeout=120) as r:
        size = int(r.headers["Content-Length"])
    st, tail = get(ZIP, (size - 65536, size - 1))
    if st != 206:
        raise RuntimeError("KNB does not answer byte ranges")
    at = tail.rfind(b"PK\x05\x06")
    cd_size, cd_off = struct.unpack("<II", tail[at + 12:at + 20])
    _, cd = get(ZIP, (cd_off, cd_off + cd_size - 1))
    out, i = {}, 0
    while cd[i:i + 4] == b"PK\x01\x02":
        method = struct.unpack("<H", cd[i + 10:i + 12])[0]
        csize, usize = struct.unpack("<II", cd[i + 20:i + 28])
        n, e, c = struct.unpack("<HHH", cd[i + 28:i + 34])
        off = struct.unpack("<I", cd[i + 42:i + 46])[0]
        name = cd[i + 46:i + 46 + n].decode("utf-8", "replace")
        i += 46 + n + e + c
        base = name.rsplit("/", 1)[-1]
        if base not in wanted:
            continue
        _, lh = get(ZIP, (off, off + 29))
        ln, le = struct.unpack("<HH", lh[26:30])
        start = off + 30 + ln + le
        _, raw = get(ZIP, (start, start + csize - 1))
        data = zlib.decompressobj(-15).decompress(raw) if method == 8 else raw
        if len(data) != usize:
            raise RuntimeError(f"{base}: read {len(data)} bytes, the zip says {usize}")
        out[base] = data
        print(f"  read {base} ({usize / 1e6:.1f} MB)", flush=True)
    return out


def tile_bounds(z, x, y):
    n = 2 ** z
    size = 2 * WORLD / n
    return -WORLD + x * size, WORLD - (y + 1) * size, -WORLD + (x + 1) * size, WORLD - y * size


def build(data, name, label):
    from rasterio.io import MemoryFile
    with MemoryFile(data) as mf, mf.open() as ds:
        src = ds.read(1).astype("float64")
        nod = ds.nodata
        src_t, src_crs = ds.transform, ds.crs
    build_array(src, src_t, src_crs, nod, name, label,
                "Halpern et al. 2022; Frazier et al., KNB doi:10.5063/F1V69H1B", "food")


def build_array(src, src_t, src_crs, nod, name, label, attribution, keydir, maxzoom=None):
    """Draw one raster (already read) into tiles/<name>.pmtiles and <keydir>/<name>.key.json."""
    import numpy as np
    from rasterio.transform import from_bounds
    from rasterio.warp import reproject, Resampling
    from PIL import Image
    from pmtiles.tile import zxy_to_tileid, TileType, Compression
    from pmtiles.writer import Writer
    top = MAXZOOM if maxzoom is None else maxzoom

    if nod is not None:
        src[src == nod] = np.nan
    pos = src[np.isfinite(src) & (src > 0)]
    if not pos.size:
        raise RuntimeError(f"{name}: no positive values")
    logs = np.log10(pos)
    cuts = list(np.quantile(logs, [0.05, 0.25, 0.5, 0.75, 0.95, 0.995]))
    ramp = np.array(RAMP, dtype="float64")
    key = [{"value": float(10 ** c), "colour": "#%02x%02x%02x" % RAMP[i]} for i, c in enumerate(cuts)]

    def colour(a):
        rgba = np.zeros(a.shape + (4,), dtype="uint8")
        ok = np.isfinite(a) & (a > 0)
        if not ok.any():
            return None
        lv = np.log10(a[ok])
        t = np.interp(lv, cuts, np.arange(len(cuts)))
        lo = np.floor(t).astype(int).clip(0, len(RAMP) - 2)
        f = (t - lo)[:, None]
        rgba[ok, :3] = (ramp[lo] * (1 - f) + ramp[lo + 1] * f).round().astype("uint8")
        rgba[ok, 3] = 225
        return rgba

    tiles, filled = [], set()
    for z in range(top + 1):
        for x in range(2 ** z):
            for y in range(2 ** z):
                # A square whose parent held nothing holds nothing either (the
                # parent kept the largest value under it); skipping those makes
                # a coastal raster quick.
                if z and (z - 1, x // 2, y // 2) not in filled:
                    continue
                w, s, e, n = tile_bounds(z, x, y)
                dst = np.full((256, 256), np.nan, dtype="float64")
                reproject(src, dst, src_transform=src_t, src_crs=src_crs, src_nodata=np.nan,
                          dst_transform=from_bounds(w, s, e, n, 256, 256), dst_crs="EPSG:3857", dst_nodata=np.nan,
                          resampling=Resampling.max)
                rgba = colour(dst)
                if rgba is None:
                    continue
                filled.add((z, x, y))
                buf = io.BytesIO()
                Image.fromarray(rgba, "RGBA").save(buf, "PNG", optimize=True)
                tiles.append((zxy_to_tileid(z, x, y), buf.getvalue()))
        print(f"  {name}: zoom {z} done, {len(tiles)} squares so far", flush=True)
    tiles.sort()
    out = pathlib.Path("tiles") / f"{name}.pmtiles"
    out.parent.mkdir(exist_ok=True)
    with open(out, "wb") as f:
        wr = Writer(f)
        for tid, b in tiles:
            wr.write_tile(tid, b)
        wr.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": 0, "max_zoom": top,
                     "min_lon_e7": -1800000000, "min_lat_e7": -850511287, "max_lon_e7": 1800000000, "max_lat_e7": 850511287,
                     "center_zoom": 1, "center_lon_e7": 0, "center_lat_e7": 0},
                    {"name": name, "attribution": attribution, "description": label})
    kdir = pathlib.Path(keydir)
    kdir.mkdir(exist_ok=True)
    (kdir / f"{name}.key.json").write_text(json.dumps({"name": label, "per": "the package's figure per cell",
                                                       "steps": key, "cells_with_a_value": int(pos.size)}, indent=1))
    print(f"{name}: {out} {out.stat().st_size / 1e6:.1f} MB, {len(tiles)} squares", flush=True)


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("food_crops: by hand only")
        return
    need()
    wanted = {f"gall_peter_land_{c}_crop_produce_{p}_per_cell.tif": (c, p) for c in CROPS for p in PRESSURES}
    got = members(set(wanted))
    missing = sorted(set(wanted) - set(got))
    if missing:
        sys.exit("food_crops: not in the zip: " + ", ".join(missing))
    for fname, (c, p) in wanted.items():
        build(got[fname], f"food_{c}_{p}", f"{CROPS[c]}: {p}, food and feed, 2017 (Halpern et al. 2022)")


if __name__ == "__main__":
    main()
