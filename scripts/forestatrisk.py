#!/usr/bin/env python3
"""
Where tropical forest is most at risk of being cleared: ForestAtRisk's map of
the probability of deforestation in 2020 (round 111b, 29 September; the
owner asked on 27 September, and Cirad answered on 29 September that it is
"in principle happy to support non-commercial educational use of the
prob_2020 map").

Source: Vieilledent G., C. Vancutsem, C. Bourgoin, P. Ploton, P. Verley and
F. Achard (2023), "Spatial scenario of tropical deforestation and carbon
emissions for the 21st century", bioRxiv, doi:10.1101/2022.03.22.485306;
Cirad and the European Commission's Joint Research Centre. Copyright 2021
Cirad, EC JRC, all rights reserved; shown with Cirad's permission for
non-commercial educational use. The rasters, one per continent, 30 m, in
Albers equal-area projections, as Cloud Optimized GeoTIFFs on the project's
own site (forestatrisk.cirad.fr/rasters.html):

  https://forestatrisk.cirad.fr/tropics/tif/prob_2020_AME_aea.tif  (America)
  https://forestatrisk.cirad.fr/tropics/tif/prob_2020_AFR_aea.tif  (Africa)
  https://forestatrisk.cirad.fr/tropics/tif/prob_2020_ASI_aea.tif  (Asia)

Each pixel is the modelled probability that the forest there is cleared,
written by the forestatrisk package as a whole number from 1 to 65535
(probability p stored as 1 + p x 65534; 0 = no forest or no data). Every
forest pixel is kept; each map pixel is coloured in one of ten equal steps of
probability (0 to 10%, 10 to 20%, ... 90 to 100%), light to dark in the
map's teal-to-cobalt ramp.

How it is built: each continent's file is warped by GDAL straight from the
site (using the file's own overviews) into web-map pixels at zoom MAXZOOM
(default 9, about 300 m at the equator; FAR_MAXZOOM=10 for about 150 m), the
pixel under each centre kept (nearest), then cut into web squares zoom by
zoom. Written like forest_management: tiles/forestatrisk.pmtiles, and, where
one file would pass GitHub's limit, more files each holding a run of zooms
or a strip, all listed in tiles/forestatrisk.build.json with the ten steps.

Built once; FAR_REBUILD=1 builds again.
"""
import io, json, math, os, pathlib, subprocess, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

ROW = "forestatrisk"
OUT = pathlib.Path(f"tiles/{ROW}.pmtiles")
STAMP = OUT.with_suffix(".build.json")
BASE = os.environ.get("FAR_BASE", "https://forestatrisk.cirad.fr/tropics/tif/")
CONTINENTS = [("AME", "America"), ("AFR", "Africa"), ("ASI", "Asia")]
MAXZOOM = int(os.environ.get("FAR_MAXZOOM", "9"))
LIMIT = 90 * 1024 * 1024
WORLD = 20037508.342789244
# Light to dark, teal to cobalt (the map's ten-step ramp): the darker, the likelier.
RAMP10 = ["#E4F3F8", "#C6E7F0", "#9CD6E6", "#6FC2DA", "#46AACB", "#2E8FBA", "#2275A8", "#1A5C92", "#13447A", "#0C2E5E"]
CLASSES = [(i + 1, RAMP10[i], f"{i * 10} to {(i + 1) * 10}% chance of being cleared") for i in range(10)]
ATTR = "ForestAtRisk, probability of deforestation 2020 (Vieilledent et al. 2023; Cirad, EC JRC), shown with permission for non-commercial educational use"
GDAL_ENV = {"GDAL_HTTP_MAX_RETRY": "10", "GDAL_HTTP_RETRY_DELAY": "10", "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif", "GDAL_HTTP_MULTIRANGE": "YES", "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
            "VSI_CACHE": "TRUE", "VSI_CACHE_SIZE": "1000000000", "GDAL_CACHEMAX": "2048", "GDAL_HTTP_TIMEOUT": "120",
            "GDAL_HTTP_USERAGENT": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}


def need():
    try:
        import numpy, rasterio, pmtiles, PIL  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "numpy", "rasterio", "pmtiles", "pillow"], check=True)


def sh(*cmd):
    print("  $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env=dict(os.environ, **GDAL_ENV))


def lon_of(x, z):
    return x / 2 ** z * 360 - 180


def main():
    if STAMP.exists() and OUT.exists() and not os.environ.get("FAR_REBUILD"):
        print(f"{ROW}: already built; FAR_REBUILD=1 to build again")
        return
    need()
    os.environ.update(GDAL_ENV)  # read by GDAL, for rasterio's reads as for gdalwarp
    import mines
    mines.tools()  # gdalwarp
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from PIL import Image
    from pmtiles.tile import zxy_to_tileid, TileType, Compression
    from pmtiles.writer import Writer

    work = pathlib.Path(tempfile.mkdtemp())
    res = 2 * WORLD / (256 * 2 ** MAXZOOM)
    t0 = time.time()
    local, profiles = [], {}
    for cab, name in CONTINENTS:
        url = ("/vsicurl/" if BASE.startswith("http") else "") + f"{BASE}prob_2020_{cab}_aea.tif"
        with rasterio.open(url) as src:
            profiles[cab] = {"width": src.width, "height": src.height, "dtype": src.dtypes[0], "nodata": src.nodata,
                             "crs": src.crs.to_string() if src.crs else None, "overviews": src.overviews(1)}
            print(f"{ROW}: {name}: {profiles[cab]}", flush=True)
        if profiles[cab]["dtype"] != "uint16":
            STAMP.with_suffix(".failed.json").write_text(json.dumps(profiles, indent=1))
            raise SystemExit(f"{ROW}: {cab} is {profiles[cab]['dtype']}, not the 1 to 65535 whole numbers the package writes; "
                             "nothing is guessed (profile in tiles/forestatrisk.build.failed.json)")
        tif = work / f"{cab}.tif"
        # Web-map pixels at zoom MAXZOOM, the file's edges on the edges of
        # zoom-4 squares, so every zoom's squares fall on whole pixels.
        from rasterio.warp import transform_bounds
        with rasterio.open(url) as src:
            l, b, r, t = transform_bounds(src.crs, "EPSG:3857", *src.bounds, densify_pts=41)
        step = 2 * WORLD / 16
        l, r = -WORLD + math.floor((l + WORLD) / step) * step, -WORLD + math.ceil((r + WORLD) / step) * step
        b, t = WORLD - math.ceil((WORLD - b) / step) * step, WORLD - math.floor((WORLD - t) / step) * step
        b, t = max(b, -WORLD), min(t, WORLD)
        sh("gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:3857", "-te", repr(l), repr(b), repr(r), repr(t), "-tr", repr(res), repr(res),
           "-r", "near", "-ovr", "AUTO",
           "-srcnodata", "0", "-dstnodata", "0", "-ot", "UInt16", "-wm", "1024", "-multi", "-wo", "NUM_THREADS=ALL_CPUS",
           "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", "-co", "BIGTIFF=YES", url, str(tif))
        print(f"{ROW}: {name} warped, {tif.stat().st_size / 1e6:.0f} MB, {time.time() - t0:.0f} s", flush=True)
        # Overviews on the local copy (nearest), so wide squares read little.
        with rasterio.open(tif, "r+") as ds:
            ds.build_overviews([2, 4, 8, 16, 32, 64, 128, 256, 512], Resampling.nearest)
        local.append(tif)

    lut_edges = np.array([1 + 65534 * k / 10 for k in range(1, 10)])  # 10%, 20% ... 90%
    pal = [0, 0, 0]
    for _, c, _ in CLASSES:
        pal += [int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)]
    counts = np.zeros(11, dtype=np.int64)
    by_zoom = {z: {} for z in range(MAXZOOM + 1)}

    def put(z, x, y, codes):
        # A square two continents both reach (their files overlap at the
        # edges) keeps whichever has forest in each pixel.
        k = (x, y)
        if k in by_zoom[z]:
            old = by_zoom[z][k]
            codes = np.where(old > 0, old, codes)
        by_zoom[z][k] = codes

    for tif in local:
        with rasterio.open(tif) as ds:
            ox = round((ds.bounds.left + WORLD) / res)
            oy = round((WORLD - ds.bounds.top) / res)
            for z in range(MAXZOOM + 1):
                f = 2 ** (MAXZOOM - z)
                h, w = math.ceil(ds.height / f), math.ceil(ds.width / f)
                # The whole file at this zoom (its overviews serve the wide ones).
                arr = ds.read(1, out_shape=(h, w), resampling=Resampling.nearest)
                codes_all = np.where(arr > 0, np.searchsorted(lut_edges, arr, side="right") + 1, 0).astype(np.uint8)
                del arr
                if z == MAXZOOM:
                    counts += np.bincount(codes_all.ravel(), minlength=11)
                px0, py0 = ox // f, oy // f  # the file's corner in this zoom's pixels (whole: see the -te above)
                for ty in range(py0 // 256, (py0 + h - 1) // 256 + 1):
                    for tx in range(px0 // 256, (px0 + w - 1) // 256 + 1):
                        r0, c0 = ty * 256 - py0, tx * 256 - px0
                        block = np.zeros((256, 256), np.uint8)
                        rs, cs = max(0, r0), max(0, c0)
                        re_, ce = min(h, r0 + 256), min(w, c0 + 256)
                        if rs >= re_ or cs >= ce:
                            continue
                        sub = codes_all[rs:re_, cs:ce]
                        if not sub.any():
                            continue
                        block[rs - r0:re_ - r0, cs - c0:ce - c0] = sub
                        put(z, tx, ty, block)
                print(f"  {tif.stem} zoom {z}: {len(by_zoom[z]):,} squares so far, {time.time() - t0:.0f} s", flush=True)
                del codes_all
    # Squares to PNG, zoom by zoom.
    enc = {}
    for z in range(MAXZOOM + 1):
        enc[z] = []
        for (x, y), codes in by_zoom[z].items():
            buf = io.BytesIO()
            im = Image.fromarray(codes, "P")
            im.putpalette(pal)
            im.save(buf, "PNG", optimize=True, transparency=0)
            enc[z].append((zxy_to_tileid(z, x, y), buf.getvalue(), x))
        by_zoom[z] = None
        print(f"  zoom {z}: {len(enc[z]):,} squares, {sum(len(t[1]) for t in enc[z]) / 1e6:.1f} MB, {time.time() - t0:.0f} s", flush=True)
    by_zoom = enc

    # Runs of zooms under the limit; a zoom too big alone is cut west to east
    # into strips (as forest_management).
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
                        {"name": ROW, "attribution": ATTR, "description": "Probability of deforestation in 2020, tropics, from 30 m"})
        part = {"file": name, "from": zs[0], "to": zs[-1], "bytes": (OUT.parent / name).stat().st_size}
        if xs is not None:
            part["bounds"] = [round(west, 6), -85.051129, round(east, 6), 85.051129]
        parts.append(part)
    info = {"source": [f"{BASE}prob_2020_{c}_aea.tif" for c, _ in CONTINENTS], "page": "https://forestatrisk.cirad.fr/rasters.html",
            "citation": "Vieilledent G., Vancutsem C., Bourgoin C., Ploton P., Verley P., Achard F. (2023). Spatial scenario of tropical "
                        "deforestation and carbon emissions for the 21st century. bioRxiv. doi:10.1101/2022.03.22.485306",
            "rights": "Copyright 2021 Cirad, EC JRC, all rights reserved; shown with Cirad's permission (29 September 2026) for non-commercial educational use",
            "values": "1 + probability x 65534 (forestatrisk package); 0 = no forest or no data",
            "classes": [{"value": v, "colour": c, "name": nm} for v, c, nm in CLASSES], "max_zoom": MAXZOOM,
            "metres_per_pixel_at_equator": round(res), "profiles": profiles,
            "pixels_by_step_at_max_zoom": {nm: int(counts[v]) for v, _, nm in CLASSES},
            "squares": sum(len(v) for v in by_zoom.values()), "seconds": round(time.time() - t0)}
    if len(parts) > 1:
        info["parts"] = parts
    STAMP.write_text(json.dumps(info, indent=1))
    print(f"{ROW}: {info['squares']:,} squares, zooms 0 to {MAXZOOM}, in {len(parts)} file(s), {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
