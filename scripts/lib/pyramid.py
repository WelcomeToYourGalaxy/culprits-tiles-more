"""
Shared by the round 90b builds (human_modification, wilderness, critical_habitat,
reforestation, mangroves, cropland_expansion): a worldwide grid of class codes
turned into a PMTiles archive of coloured 256-pixel squares, zooms 0 to TOP.

Kept in scripts/lib/ so the refresh workflow, which runs every scripts/*.py as
its own job, does not run it on its own.

The grid is a numpy uint8 array in plain longitude/latitude (EPSG:4326): row 0
is the north edge, each cell `res` degrees, 0 meaning nothing there. Each map
pixel takes the cells under it, either the largest code ("max", so a sparse
thing such as a mangrove fringe still shows from the world view) or the mean
of the codes that are not 0 ("mean", for amounts). Codes are coloured through
`palette` {code: (r, g, b, a)}; a square with nothing in it is not written.
"""
import io, json, math, os, pathlib, subprocess, sys, time

N = 256


def need(*extra):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "numpy", "pillow", "pmtiles", *extra], check=True)


def download(url, path, label):
    import urllib.request
    path = pathlib.Path(path)
    if path.exists() and path.stat().st_size > 0:
        return path
    print(f"{label}: downloading {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy)"})
    tmp = path.with_suffix(path.suffix + ".part")
    with urllib.request.urlopen(req, timeout=3600) as r, open(tmp, "wb") as f:
        got = 0
        while True:
            b = r.read(1 << 22)
            if not b:
                break
            f.write(b)
            got += len(b)
    os.replace(tmp, path)
    print(f"{label}: {got / 1e6:.0f} MB", flush=True)
    return path


def lat_of(ty, z):
    n = math.pi - 2 * math.pi * ty / 2 ** z
    return math.degrees(math.atan(math.sinh(n)))


def _edges(lo, hi, origin, res, count, flip):
    import numpy as np
    e = np.linspace(lo, hi, N + 1)
    idx = ((origin - e) / res) if flip else ((e - origin) / res)
    return idx


def square(grid, west, north, res, z, x, y, how):
    """One map square as a (256, 256) uint8 array of codes, or None if empty."""
    import numpy as np
    H, W = grid.shape
    lon = -180 + 360 * np.arange(N + 1) / N / 2 ** z + 360 * x / 2 ** z
    lat = np.array([lat_of(y + j / N, z) for j in range(N + 1)])
    cols = (lon - west) / res
    rows = (north - lat) / res
    c0, c1 = int(max(0, math.floor(cols[0]))), int(min(W, math.ceil(cols[-1])))
    r0, r1 = int(max(0, math.floor(rows[0]))), int(min(H, math.ceil(rows[-1])))
    if c1 <= c0 or r1 <= r0:
        return None
    sub = grid[r0:r1, c0:c1]
    if not sub.any():
        return None
    # Start of each pixel's run of cells, relative to the window; a pixel
    # narrower than a cell takes the cell it falls in.
    ci = np.clip(np.floor(cols[:-1]).astype(int) - c0, 0, sub.shape[1] - 1)
    ri = np.clip(np.floor(rows[:-1]).astype(int) - r0, 0, sub.shape[0] - 1)
    ci = np.maximum.accumulate(ci)
    ri = np.maximum.accumulate(ri)
    inside_c = (cols[1:] > 0) & (cols[:-1] < W)
    inside_r = (rows[1:] > 0) & (rows[:-1] < H)
    if how == "max":
        a = np.maximum.reduceat(sub, ri, axis=0)
        a = np.maximum.reduceat(a, ci, axis=1)
        out = a.astype(np.uint8)
    else:
        v = sub.astype(np.float32)
        n = (sub > 0).astype(np.float32)
        s = np.add.reduceat(np.add.reduceat(v, ri, axis=0), ci, axis=1)
        k = np.add.reduceat(np.add.reduceat(n, ri, axis=0), ci, axis=1)
        out = np.where(k > 0, np.round(s / np.maximum(k, 1)), 0).astype(np.uint8)
    out[~inside_r, :] = 0
    out[:, ~inside_c] = 0
    return out if out.any() else None


def encode(codes, palette):
    from PIL import Image
    im = Image.fromarray(codes, "P")
    pal, alpha = [], []
    for c in range(256):
        r, g, b, a = palette.get(c, (0, 0, 0, 0))
        pal += [r, g, b]
        alpha.append(a if c else 0)
    im.putpalette(pal)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True, transparency=bytes(alpha))
    return buf.getvalue()


def build(grid, west, north, res, palette, out, top, how="max", attribution="", name="", meta=None, label=None):
    """Writes out (a .pmtiles path) and out with .build.json beside it. If the
    archive would pass GitHub's 95 MB limit, it is made again one zoom lower."""
    while True:
        try:
            return _build(grid, west, north, res, palette, out, top, how, attribution, name, meta, label)
        except TooBig as e:
            if top <= 3:
                raise SystemExit(str(e))
            print(f"{e}; trying again to zoom {top - 1}", flush=True)
            top -= 1


class TooBig(Exception):
    pass


def _build(grid, west, north, res, palette, out, top, how, attribution, name, meta, label):
    import numpy as np
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer
    out = pathlib.Path(out)
    label = label or out.stem
    t0 = time.time()
    tiles = {}
    # Only squares over the grid's own extent are visited.
    south = north - grid.shape[0] * res
    east = west + grid.shape[1] * res
    for z in range(top + 1):
        n = 2 ** z
        x0, x1 = max(0, int((west + 180) / 360 * n)), min(n - 1, int((east + 180) / 360 * n - 1e-9))
        ys = [ty for ty in range(n) if lat_of(ty + 1, z) < north and lat_of(ty, z) > south]
        for ty in ys:
            for tx in range(x0, x1 + 1):
                c = square(grid, west, north, res, z, tx, ty, how)
                if c is not None:
                    tiles[zxy_to_tileid(z, tx, ty)] = encode(c, palette)
        print(f"{label}: zoom {z}, {len(tiles)} squares so far, {time.time() - t0:.0f} s", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        w = Writer(f)
        for tid in sorted(tiles):
            w.write_tile(tid, tiles[tid])
        w.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": 0, "max_zoom": top,
                    "min_lon_e7": int(max(-180, west) * 1e7), "min_lat_e7": int(max(-85, south) * 1e7),
                    "max_lon_e7": int(min(180, east) * 1e7), "max_lat_e7": int(min(85, north) * 1e7),
                    "center_zoom": 1, "center_lon_e7": 0, "center_lat_e7": 0},
                   {"attribution": attribution, "name": name or out.stem})
    size = tmp.stat().st_size
    if size > 95 * 1024 * 1024:
        tmp.unlink()
        raise TooBig(f"{label}: {size / 1e6:.0f} MB at zoom {top} is over GitHub's limit")
    os.replace(tmp, out)
    stamp = dict(meta or {}, to_zoom=top, squares=len(tiles), bytes=size, how=how)
    out.with_suffix(".build.json").write_text(json.dumps(stamp, indent=1))
    print(f"{label}: {len(tiles)} squares, {size / 1e6:.1f} MB", flush=True)
    return size


def read_grid(path, res, bounds=(-180, -60, 180, 84), resampling="average", band=1, scale=None):
    """The source read onto a lon/lat grid of `res` degrees over bounds, as
    float32 (nan where the source has no data). A source in another projection
    is warped. Overviews in the file are used, so a remote COG read wide costs
    little."""
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT
    from rasterio.transform import from_origin
    w, s, e, n = bounds
    W, H = int(round((e - w) / res)), int(round((n - s) / res))
    tr = from_origin(w, n, res, res)
    rs = getattr(Resampling, resampling)
    with rasterio.Env(GDAL_HTTP_MAX_RETRY="6", GDAL_HTTP_RETRY_DELAY="5", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff,.zip"):
        with rasterio.open(path) as src:
            nod = src.nodata
            with WarpedVRT(src, crs="EPSG:4326", transform=tr, width=W, height=H, resampling=rs,
                           src_nodata=nod, nodata=np.nan if src.dtypes[band - 1].startswith("float") else nod) as v:
                a = v.read(band, out_dtype="float32")
                if v.nodata is not None and not (isinstance(v.nodata, float) and math.isnan(v.nodata)):
                    a[a == v.nodata] = np.nan
    if scale is not None:
        a = a * scale
    return a, w, n


# The map's teal-to-cobalt ramp, light to dark (no green, orange or yellow).
RAMP5 = ["#D6EEF6", "#8FD6E8", "#3FA9C2", "#1E6FA8", "#0E2F66"]
RAMP10 = ["#E4F3F8", "#C6E7F0", "#9CD6E6", "#6FC2DA", "#46AACB", "#2E8FBA", "#2275A8", "#1A5C92", "#13447A", "#0C2E5E"]
PAGES = "https://welcometoyourgalaxy.github.io/culprits-tiles-more/"


def rgba(h, a=255):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16), a)


def write_choices(row, choices):
    """tiles/<row>.choices.json: what the map's row offers once built, each
    choice {label, archive (a path under tiles/), key [[colour, words], ...]}."""
    out = pathlib.Path("tiles") / f"{row}.choices.json"
    for c in choices:
        if not c["archive"].startswith("http"):
            c["archive"] = PAGES + c["archive"]
    out.write_text(json.dumps({"choices": choices}, indent=1, ensure_ascii=False))
    print(f"{row}: {len(choices)} choice(s) written to {out}", flush=True)
