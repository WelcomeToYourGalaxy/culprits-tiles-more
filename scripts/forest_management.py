#!/usr/bin/env python3
"""
The Global Forest Management Type Map at 100 m for 2020 (De Keersmaecker,
Zanaga, Van De Kerchove (VITO); Fritz, Duerauer, Yashchun, Romanchuk, See,
Lesiv (IIASA); Carter, Goldman (WRI)), CC BY 4.0, Zenodo record 20396072:

  https://zenodo.org/records/20396072/files/global_forest_management_2020_100m_v1.tif

drawn as web squares for the Culprits map, every class in its own colour:

  11  Unmanaged natural forests (including primary forests)
  20  Naturally regenerated forests with visible human activity
  31  Planted forest
  32  Plantation forest
  33  Rubber plantation
  40  Oil palm plantations
  50  Tree crops (monocultures)
  53  Agroforestry
  100 Other trees
  (0, no tree cover, is left clear)

The class names are the record's own. Squares from zoom 0 to MAXZOOM, each
pixel the class of the 100 m cell under its centre (nearest: a class map is
never averaged). Written as tiles/forest_management.pmtiles, or, where one
file would pass GitHub's limit, as several files each holding a run of zooms,
listed in tiles/forest_management.build.json with the classes and colours.

Built once (the record is a single 2020 release); FM_REBUILD=1 builds again.
"""
import io, json, os, pathlib, subprocess, sys, tempfile, time, urllib.request

URL = "https://zenodo.org/records/20396072/files/global_forest_management_2020_100m_v1.tif?download=1"
ROW = "forest_management"
OUT = pathlib.Path(f"tiles/{ROW}.pmtiles")
STAMP = OUT.with_suffix(".build.json")
MAXZOOM = int(os.environ.get("FM_MAXZOOM", "9"))
LIMIT = 90 * 1024 * 1024
WORLD = 20037508.342789244
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
# Muted, as the rest of the map: no orange, yellow or bright green.
CLASSES = [
    (11, "#4F6B55", "Unmanaged natural forests (including primary forests)"),
    (20, "#8C5A68", "Naturally regenerated forests with visible human activity"),
    (31, "#6E6A55", "Planted forest"),
    (32, "#8A7E6A", "Plantation forest"),
    (33, "#7A6A72", "Rubber plantation"),
    (40, "#B07F86", "Oil palm plantations"),
    (50, "#A39C92", "Tree crops (monocultures)"),
    (53, "#6F7F72", "Agroforestry"),
    (100, "#5E6D78", "Other trees"),
]


def need():
    try:
        import numpy, rasterio, pmtiles, PIL  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "numpy", "rasterio", "pmtiles", "pillow"], check=True)


def download(to):
    for i in range(5):
        try:
            done = to.stat().st_size if to.exists() else 0
            h = dict(UA, **({"Range": f"bytes={done}-"} if done else {}))
            with urllib.request.urlopen(urllib.request.Request(URL, headers=h), timeout=600) as r, open(to, "ab" if done else "wb") as fo:
                got = done
                while True:
                    b = r.read(1 << 22)
                    if not b:
                        break
                    fo.write(b)
                    got += len(b)
                    if got % (200 << 20) < (1 << 22):
                        print(f"    {got / 1e9:.2f} GB", flush=True)
            return
        except Exception as e:  # noqa: BLE001
            if i == 4:
                raise
            print(f"    download stopped ({e}); resuming in {30 * (i + 1)}s", flush=True)
            time.sleep(30 * (i + 1))


def tile_bounds(z, x, y):
    n = 2 ** z
    size = 2 * WORLD / n
    return -WORLD + x * size, WORLD - (y + 1) * size, -WORLD + (x + 1) * size, WORLD - y * size


def main():
    if STAMP.exists() and not os.environ.get("FM_REBUILD"):
        print("forest_management: already built; FM_REBUILD=1 to build again")
        return
    need()
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    from PIL import Image
    from pmtiles.tile import zxy_to_tileid, TileType, Compression
    from pmtiles.writer import Writer

    work = pathlib.Path(tempfile.mkdtemp())
    tif = work / "gfm.tif"
    print("forest_management: downloading the 2.1 GB file", flush=True)
    download(tif)
    with rasterio.open(tif) as ds:
        print(f"  {ds.width} x {ds.height}, {ds.crs}, blocks {ds.block_shapes[0]}, overviews {ds.overviews(1)}, nodata {ds.nodata}", flush=True)
        have_ov = bool(ds.overviews(1))
    if not have_ov:
        # Squares wider out are read from overviews; without them every wide
        # square would read the full-resolution file under it.
        print("  building overviews (nearest)", flush=True)
        with rasterio.open(tif, "r+") as ds:
            ds.build_overviews([2, 4, 8, 16, 32, 64, 128, 256, 512], Resampling.nearest)

    # A palette picture: index 0 clear, then one index per class.
    lut = np.zeros(256, dtype="uint8")
    pal = [0, 0, 0]
    for i, (v, c, _) in enumerate(CLASSES, 1):
        lut[v] = i
        pal += [int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)]
    seen_values = set()
    by_zoom = {z: [] for z in range(MAXZOOM + 1)}
    filled = set()
    from rasterio.transform import from_bounds as tf_bounds
    with rasterio.open(tif) as full:
        factors = full.overviews(1)
        src_res = abs(full.res[0])
    # WarpedVRT does not read a file's overviews by itself: the run of 25
    # September asked for the whole 432,000 x 180,000 file under the first
    # square and ran out of memory (44 GB). Each zoom now opens the coarsest
    # overview still at least as fine as its squares.
    def source_for(z):
        want = 360.0 / (256 * 2 ** z) / src_res
        best = None
        for i, f in enumerate(factors):
            if f <= want:
                best = i
        return rasterio.open(tif, overview_level=best) if best is not None else rasterio.open(tif)
    for z in range(MAXZOOM + 1):
        n = 2 ** z
        with source_for(z) as src:
            print(f"  zoom {z}: reading {src.width} x {src.height}", flush=True)
            for x in range(n):
                for y in range(n):
                    if z and (z - 1, x // 2, y // 2) not in filled:
                        continue
                    w, s, e, nn = tile_bounds(z, x, y)
                    # One square: the file warped to it, nearest; the source's
                    # overviews serve the wide squares.
                    with WarpedVRT(src, crs="EPSG:3857", transform=tf_bounds(w, s, e, nn, 256, 256), width=256, height=256,
                                   resampling=Resampling.nearest, src_nodata=src.nodata if src.nodata is not None else 0, nodata=0) as vrt:
                        a = vrt.read(1)
                    if not a.any():
                        continue
                    seen_values.update(int(v) for v in np.unique(a))
                    idx = lut[a]
                    if not idx.any():
                        continue
                    filled.add((z, x, y))
                    buf = io.BytesIO()
                    im = Image.fromarray(idx, "P")
                    im.putpalette(pal)
                    im.save(buf, "PNG", optimize=True, transparency=0)
                    by_zoom[z].append((zxy_to_tileid(z, x, y), buf.getvalue(), x))
            print(f"  zoom {z}: {len(by_zoom[z]):,} squares, {sum(len(t[1]) for t in by_zoom[z]) / 1e6:.1f} MB", flush=True)
    unknown = sorted(v for v in seen_values if v not in {c[0] for c in CLASSES} and v != 0)
    if unknown:
        print(f"  values in the file with no class in the record's list (left clear): {unknown}", flush=True)

    # Runs of zooms, each file under the limit. A zoom that alone passes the
    # limit (zoom 9 is about 270 MB) is split west to east into strips, each
    # its own file with its own bounds, so no detail is dropped (26 September;
    # the first full build stopped there). Each file's header carries its
    # bounds, which the map reads, so a strip is only asked for where it is.
    def lon_of(x, z):
        return x / 2 ** z * 360 - 180
    runs, cur, size = [], [], 0
    for z in range(MAXZOOM + 1):
        zs = sum(len(t[1]) for t in by_zoom[z])
        if zs > LIMIT:
            if cur:
                runs.append({"zooms": cur, "xs": None})
                cur, size = [], 0
            cols = {}
            for t in by_zoom[z]:
                cols[t[2]] = cols.get(t[2], 0) + len(t[1])
            strip, ssize = [], 0
            for x in sorted(cols):
                if strip and ssize + cols[x] > LIMIT:
                    runs.append({"zooms": [z], "xs": (strip[0], strip[-1])})
                    strip, ssize = [], 0
                strip.append(x)
                ssize += cols[x]
            if strip:
                runs.append({"zooms": [z], "xs": (strip[0], strip[-1])})
            continue
        if cur and size + zs > LIMIT:
            runs.append({"zooms": cur, "xs": None})
            cur, size = [], 0
        cur.append(z)
        size += zs
    if cur:
        runs.append({"zooms": cur, "xs": None})
    OUT.parent.mkdir(exist_ok=True)
    for old in OUT.parent.glob(f"{ROW}_z*.pmtiles"):
        old.unlink()
    parts = []
    for i, run in enumerate(runs):
        zs, xs = run["zooms"], run["xs"]
        name = OUT.name if i == 0 else (f"{ROW}_z{zs[0]}.pmtiles" if xs is None else f"{ROW}_z{zs[0]}_x{xs[0]}.pmtiles")
        tiles = sorted((t[0], t[1]) for z in zs for t in by_zoom[z] if xs is None or xs[0] <= t[2] <= xs[1])
        west, east = (-180.0, 180.0) if xs is None else (lon_of(xs[0], zs[0]), lon_of(xs[1] + 1, zs[0]))
        with open(OUT.parent / name, "wb") as f:
            wr = Writer(f)
            for tid, b in tiles:
                wr.write_tile(tid, b)
            wr.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": zs[0], "max_zoom": zs[-1],
                         "min_lon_e7": int(round(west * 1e7)), "min_lat_e7": -850511287, "max_lon_e7": int(round(east * 1e7)), "max_lat_e7": 850511287,
                         "center_zoom": 1, "center_lon_e7": int(round((west + east) / 2 * 1e7)), "center_lat_e7": 0},
                        {"name": ROW, "attribution": "Global Forest Management Type Map 2020 (VITO, IIASA, WRI), CC BY 4.0",
                         "description": "Forest management types at 100 m, 2020"})
        part = {"file": name, "from": zs[0], "to": zs[-1], "bytes": (OUT.parent / name).stat().st_size}
        if xs is not None:
            part["bounds"] = [round(west, 6), -85.051129, round(east, 6), 85.051129]
        parts.append(part)
    info = {"source": URL.split("?")[0], "record": "https://zenodo.org/records/20396072", "licence": "CC BY 4.0",
            "classes": [{"value": v, "colour": c, "name": nm} for v, c, nm in CLASSES], "max_zoom": MAXZOOM,
            "squares": sum(len(v) for v in by_zoom.values()), "values_without_class": unknown}
    if len(parts) > 1:
        info["parts"] = parts
    STAMP.write_text(json.dumps(info, indent=1))
    print(f"forest_management: {info['squares']:,} squares, zooms 0 to {MAXZOOM}, in {len(parts)} file(s)")


if __name__ == "__main__":
    main()
