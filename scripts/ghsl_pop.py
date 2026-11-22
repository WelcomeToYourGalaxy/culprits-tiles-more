#!/usr/bin/env python3
"""
Population density worldwide as numbers the map can raise into relief (round
83b, asked 27 September: "make the population density layer hypsometric, not
in altitude, by density").

The row drew Climate TRACE's coloured picture of GHSL's population, from which
no number can be read back. This builds the same data from its source, the
European Commission's Global Human Settlement Layer: GHS-POP, epoch 2020,
release R2023A, 30 arc-seconds (about 1 km), WGS84 (CC BY 4.0; cite Schiavina,
Freire, Carioli and MacManus 2023, GHS-POP R2023A, European Commission JRC,
doi:10.2905/2FF68A52-5B5B-4A22-8F40-C41DA8332CFE).

  tiles/ghsl_pop.pmtiles   zooms 0 to 6, 256-pixel squares, each pixel people
                           per square km coded as a height tile (Mapbox's
                           code: value = -10000 + (R*65536 + G*256 + B) / 10);
                           zoom 6 is read from the source (each map pixel the
                           average of the source cells under it, divided by the
                           cell's own area at its latitude); wider zooms are the
                           average of the four squares under them
  tiles/ghsl_pop.build.json  what it was built from

Built once (the release is fixed); GHSL_REBUILD=1 builds it again.
"""
import io, json, math, os, pathlib, subprocess, sys, tempfile, time, urllib.request, zipfile

URL = ("https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/"
       "GHS_POP_E2020_GLOBE_R2023A_4326_30ss/V1-0/GHS_POP_E2020_GLOBE_R2023A_4326_30ss_V1_0.zip")
OUT = pathlib.Path("tiles/ghsl_pop.pmtiles")
STAMP = pathlib.Path("tiles/ghsl_pop.build.json")
TOP = 6
N = 256
CELL_KM = 30 / 3600 * 111.32          # a 30 arc-second cell's side at the equator, km


def lat_of(ty, z):
    n = math.pi - 2 * math.pi * ty / 2 ** z
    return math.degrees(math.atan(math.sinh(n)))


def encode(d, np, Image):
    code = np.round((np.clip(d, 0, 1_600_000) + 10000) * 10).astype(np.uint32)
    rgb = np.stack([(code >> 16) & 255, (code >> 8) & 255, code & 255], axis=-1).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(buf, "PNG", optimize=True)
    return buf.getvalue()


def main():
    if OUT.exists() and STAMP.exists() and not os.environ.get("GHSL_REBUILD"):
        print("ghsl_pop: already built")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "rasterio", "numpy", "pillow", "pmtiles"], check=True)
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.windows import from_bounds
    from PIL import Image
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer
    work = pathlib.Path(tempfile.mkdtemp())
    zpath = work / "pop.zip"
    print("ghsl_pop: downloading GHS-POP 2020 (about 460 MB)", flush=True)
    with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Culprits atlas build"}), timeout=3600) as r, open(zpath, "wb") as f:
        while True:
            b = r.read(1 << 22)
            if not b:
                break
            f.write(b)
    tif = [n for n in zipfile.ZipFile(zpath).namelist() if n.lower().endswith(".tif")][0]
    src = rasterio.open(f"/vsizip/{zpath}/{tif}")
    nodata = src.nodata
    level = {}
    t0 = time.time()
    for ty in range(2 ** TOP):
        top, bot = lat_of(ty, TOP), lat_of(ty + 1, TOP)
        # The latitude of each map pixel's middle in this row of squares.
        lats = np.array([lat_of(ty + (j + 0.5) / N, TOP) for j in range(N)])
        H = 4 * N
        area = (CELL_KM ** 2) * np.cos(np.radians(lats))
        for tx in range(2 ** TOP):
            lon0, lon1 = -180 + 360 * tx / 2 ** TOP, -180 + 360 * (tx + 1) / 2 ** TOP
            win = from_bounds(lon0, max(bot, -90), lon1, min(top, 90), src.transform)
            a = src.read(1, window=win, out_shape=(H, N), resampling=Resampling.average, boundless=True, fill_value=0).astype(np.float32)
            if nodata is not None:
                a[a == nodata] = 0
            a[a < 0] = 0
            if not a.any():
                continue
            rows = np.clip(((top - lats) / (top - bot) * H).astype(int), 0, H - 1)
            d = a[rows, :] / area[:, None]
            level[(tx, ty)] = d.astype(np.float32)
        if ty % 8 == 7:
            print(f"  zoom {TOP}: row {ty + 1} of {2 ** TOP}, {len(level)} squares with people, {time.time() - t0:.0f} s", flush=True)
    tiles = {zxy_to_tileid(TOP, x, y): encode(d, np, Image) for (x, y), d in level.items()}
    for z in range(TOP - 1, -1, -1):
        up = {}
        for (x, y), d in level.items():
            px, py = x // 2, y // 2
            out = up.setdefault((px, py), np.zeros((N, N), np.float32))
            small = d.reshape(N // 2, 2, N // 2, 2).mean(axis=(1, 3))
            ox, oy = (x % 2) * (N // 2), (y % 2) * (N // 2)
            out[oy:oy + N // 2, ox:ox + N // 2] = small
        level = up
        for (x, y), d in level.items():
            tiles[zxy_to_tileid(z, x, y)] = encode(d, np, Image)
        print(f"  zoom {z}: {len(level)} squares", flush=True)
    OUT.parent.mkdir(exist_ok=True)
    tmp = work / "ghsl_pop.pmtiles"
    with open(tmp, "wb") as f:
        w = Writer(f)
        for tid in sorted(tiles):
            w.write_tile(tid, tiles[tid])
        w.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": 0, "max_zoom": TOP,
                    "min_lon_e7": -1800000000, "min_lat_e7": -850000000, "max_lon_e7": 1800000000, "max_lat_e7": 850000000,
                    "center_zoom": 1, "center_lon_e7": 0, "center_lat_e7": 0},
                   {"attribution": "GHS-POP R2023A, European Commission JRC (CC BY 4.0)", "name": "ghsl_pop", "encoding": "mapbox"})
    size = tmp.stat().st_size
    if size > 95 * 1024 * 1024:
        sys.exit(f"ghsl_pop: {size / 1e6:.0f} MB is over GitHub's limit; nothing saved")
    os.replace(tmp, OUT)
    STAMP.write_text(json.dumps({"from": URL, "epoch": 2020, "to_zoom": TOP, "squares": len(tiles), "bytes": size,
                                 "unit": "people per square km", "encoding": "mapbox"}, indent=1))
    print(f"ghsl_pop: {len(tiles)} squares, {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
