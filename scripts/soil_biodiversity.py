#!/usr/bin/env python3
"""
Soil biodiversity for the Culprits map: SPUN's Underground Atlas, the global
maps of mycorrhizal fungal richness and endemism at about 1 km (Van Nuland,
Kiers et al., "Global hotspots of mycorrhizal fungal richness are poorly
protected", Nature 2025; 2.8 billion fungal DNA sequences from 130 countries),
from the paper's data and code record on Zenodo (10.5281/zenodo.14871588),
CC BY 4.0:

  https://zenodo.org/records/14871588/files/myc_richness.zip

Every GeoTIFF in the record is drawn, none left out: each becomes web squares
(zoom 0 to MAXZOOM, the map enlarges the last zoom closer in) in a light-to-
dark ramp of 12 steps between the file's own 2nd and 98th percentiles, with
values past either end in the end steps; cells with no value are clear. Each
file is one choice in the map's row, named from its file name, with its steps
and their value ranges as its key. What the record holds is written to
soil/spun_contents.json, the choices to soil/spun_choices.json.

Built once; SOIL_REBUILD=1 builds again.
"""
import io, json, os, pathlib, re, subprocess, sys, tempfile, time, urllib.request, zipfile

URL = "https://zenodo.org/records/14871588/files/myc_richness.zip?download=1"
BASE = "https://welcometoyourgalaxy.github.io/culprits-tiles-more/"
OUT = pathlib.Path("soil")
MAXZOOM = int(os.environ.get("SOIL_MAXZOOM", "7"))
LIMIT = 90 * 1024 * 1024
WORLD = 20037508.342789244
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
# Light cyan to deep violet, the map's own range.
RAMP = ["#D4F1F4", "#B3E3EC", "#8FD2E4", "#6CBFDC", "#52A8D6", "#4A8FD0", "#4A76C8", "#4D5EBD", "#5249AE", "#56389A", "#552A84", "#4E1F6C"]


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
                while True:
                    b = r.read(1 << 22)
                    if not b:
                        break
                    fo.write(b)
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


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", pathlib.Path(name).stem.lower()).strip("_")


def label(name):
    return re.sub(r"[_\-]+", " ", pathlib.Path(name).stem).strip()


def build_one(tif, row, np, rasterio, Resampling, WarpedVRT, Image, zxy_to_tileid, TileType, Compression, Writer):
    from rasterio.transform import from_bounds as tf_bounds
    with rasterio.open(tif) as ds:
        info = {"size": [ds.width, ds.height], "crs": str(ds.crs), "dtype": ds.dtypes[0], "nodata": ds.nodata}
        if not ds.overviews(1):
            pass
    if not info["size"] or min(info["size"]) < 2:
        return None
    with rasterio.open(tif, "r+") as ds:
        if not ds.overviews(1):
            ds.build_overviews([2, 4, 8, 16, 32, 64], Resampling.nearest)
    with rasterio.open(tif) as ds:
        f = max(1, max(ds.width, ds.height) // 4000)
        sample = ds.read(1, out_shape=(max(1, ds.height // f), max(1, ds.width // f)), masked=True, resampling=Resampling.nearest)
        vals = sample.compressed()
        vals = vals[np.isfinite(vals)]
        if not vals.size:
            print(f"  {tif.name}: no values", flush=True)
            return None
        lo, hi = float(np.percentile(vals, 2)), float(np.percentile(vals, 98))
        if hi <= lo:
            hi = lo + 1e-9
        factors, src_res, nodata = ds.overviews(1), None, ds.nodata
    edges = [lo + (hi - lo) * i / len(RAMP) for i in range(len(RAMP) + 1)]
    pal = [0, 0, 0] + [int(c[k:k + 2], 16) for c in RAMP for k in (1, 3, 5)]
    by_zoom = {z: [] for z in range(MAXZOOM + 1)}
    filled = set()

    def source_for(z):
        with rasterio.open(tif) as full:
            # Coarsest overview still finer than the square's pixels, judged on
            # the file's width against the world's width at this zoom.
            want = full.width / (256 * 2 ** z)
        best = None
        for i, fct in enumerate(factors):
            if fct <= want:
                best = i
        return rasterio.open(tif, overview_level=best) if best is not None else rasterio.open(tif)

    for z in range(MAXZOOM + 1):
        n = 2 ** z
        with source_for(z) as src:
            for x in range(n):
                for y in range(n):
                    if z and (z - 1, x // 2, y // 2) not in filled:
                        continue
                    w, s, e, nn = tile_bounds(z, x, y)
                    with WarpedVRT(src, crs="EPSG:3857", transform=tf_bounds(w, s, e, nn, 256, 256), width=256, height=256,
                                   resampling=Resampling.nearest, src_nodata=nodata, nodata=nodata if nodata is not None else 0) as vrt:
                        a = vrt.read(1, masked=True).astype("float64")
                    m = np.ma.getmaskarray(a) | ~np.isfinite(a.filled(np.nan))
                    if m.all():
                        continue
                    idx = np.clip(np.digitize(a.filled(lo), edges[1:-1]) + 1, 1, len(RAMP)).astype("uint8")
                    idx[m] = 0
                    filled.add((z, x, y))
                    buf = io.BytesIO()
                    im = Image.fromarray(idx, "P")
                    im.putpalette(pal)
                    im.save(buf, "PNG", optimize=True, transparency=0)
                    by_zoom[z].append((zxy_to_tileid(z, x, y), buf.getvalue()))
        size = sum(len(b) for _, b in by_zoom[z])
        print(f"  {tif.name} zoom {z}: {len(by_zoom[z]):,} squares, {size / 1e6:.1f} MB", flush=True)
        if size > LIMIT:
            by_zoom[z] = []
            print(f"  zoom {z} alone is over GitHub's limit; stops at zoom {z - 1}, drawn larger closer in", flush=True)
            break
    zooms = [z for z in by_zoom if by_zoom[z]]
    runs, cur, size = [], [], 0
    for z in zooms:
        zs = sum(len(b) for _, b in by_zoom[z])
        if cur and size + zs > LIMIT:
            runs.append(cur)
            cur, size = [], 0
        cur.append(z)
        size += zs
    if cur:
        runs.append(cur)
    tiles_dir = pathlib.Path("tiles")
    tiles_dir.mkdir(exist_ok=True)
    files = []
    for i, zs in enumerate(runs):
        name = f"{row}.pmtiles" if i == 0 else f"{row}_z{zs[0]}.pmtiles"
        with open(tiles_dir / name, "wb") as fo:
            wr = Writer(fo)
            for tid, b in sorted(t for z in zs for t in by_zoom[z]):
                wr.write_tile(tid, b)
            wr.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": zs[0], "max_zoom": zs[-1],
                         "min_lon_e7": -1800000000, "min_lat_e7": -850511287, "max_lon_e7": 1800000000, "max_lat_e7": 850511287,
                         "center_zoom": 1, "center_lon_e7": 0, "center_lat_e7": 0},
                        {"name": row, "attribution": "SPUN Underground Atlas (Van Nuland et al. 2025), CC BY 4.0"})
        files.append({"file": name, "from": zs[0], "to": zs[-1]})
    fmt = (lambda v: f"{v:,.2f}") if hi - lo < 10 else (lambda v: f"{v:,.0f}")
    key = [[RAMP[i], (f"{fmt(edges[i])} to {fmt(edges[i + 1])}" if 0 < i < len(RAMP) - 1 else
                      (f"up to {fmt(edges[1])}" if i == 0 else f"{fmt(edges[-2])} and over"))] for i in range(len(RAMP))]
    return {"info": info, "files": files, "p2": lo, "p98": hi, "key": key}


def main():
    stamp = OUT / "spun_choices.json"
    if stamp.exists() and not os.environ.get("SOIL_REBUILD"):
        print("soil biodiversity: already built; SOIL_REBUILD=1 to build again")
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
    z = work / "myc_richness.zip"
    print("soil biodiversity: downloading the Underground Atlas record", flush=True)
    download(z)
    zf = zipfile.ZipFile(z)
    members = [{"name": i.filename, "bytes": i.file_size} for i in zf.infolist()]
    OUT.mkdir(exist_ok=True)
    (OUT / "spun_contents.json").write_text(json.dumps({"record": "https://doi.org/10.5281/zenodo.14871588", "files": members}, indent=1))
    tifs = [m["name"] for m in members if re.search(r"\.tiff?$", m["name"], re.I) and not m["name"].startswith("__MACOSX")]
    print(f"  {len(members)} files in the record, {len(tifs)} GeoTIFFs", flush=True)
    choices, skipped = [], []
    for name in tifs:
        row = "soil_spun_" + slug(name)
        path = work / pathlib.Path(name).name
        with zf.open(name) as fi, open(path, "wb") as fo:
            while True:
                b = fi.read(1 << 22)
                if not b:
                    break
                fo.write(b)
        try:
            got = build_one(path, row, np, rasterio, Resampling, WarpedVRT, Image, zxy_to_tileid, TileType, Compression, Writer)
        except Exception as e:  # noqa: BLE001
            print(f"  {name}: not drawn ({e})", flush=True)
            got = None
            skipped.append({"file": name, "why": str(e)})
        path.unlink(missing_ok=True)
        if not got:
            continue
        ch = {"label": label(name), "file": name, "archive": BASE + "tiles/" + got["files"][0]["file"], "key": got["key"],
              "range_2nd_to_98th_percentile": [got["p2"], got["p98"]], "source": got["info"]}
        if len(got["files"]) > 1:
            ch["parts"] = got["files"]
        choices.append(ch)
    if not choices:
        sys.exit("soil biodiversity: nothing drawn")
    stamp.write_text(json.dumps({"record": "https://doi.org/10.5281/zenodo.14871588", "choices": choices, "not_drawn": skipped}, ensure_ascii=False, indent=1))
    print(f"soil biodiversity: {len(choices)} maps drawn, {len(skipped)} not drawn")


if __name__ == "__main__":
    main()
