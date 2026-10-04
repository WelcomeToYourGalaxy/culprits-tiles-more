#!/usr/bin/env python3
"""
EPA's facility points as pictures for the zooms wider out (round 81, asked 27
September: "that all EPA sites layer still loads too slow").

The row "Every US site EPA holds a record for" drew its 2,994,625 points from
tiles/epa_efpoints_z0.pmtiles ... _z6.pmtiles: every point, none merged. At the
world view the one square that holds the United States is 16 MB of points, and
the browser has to read and draw all of them before anything shows.

This reads every point from the zoom-6 file (it holds every point, unmerged,
with the EPA layer each belongs to) and, for zooms 0 to 5, draws each EPA layer
as a picture: every point counted into the pixel it falls in, the pixel's
colour and strength rising with how many points are in it. No point is left
out; a picture square of the whole country is a few kilobytes. From zoom 6 the
map draws the points themselves as before, so every one can still be clicked.

  tiles/epa_density_<layer id>.pmtiles   one picture archive per EPA layer
  tiles/epa_density.json                 the layers, their names and counts,
                                         the count steps of the colour key

Rebuilt when the zoom-6 file is newer than the pictures (epa_efpoints.py
renews it every four weeks), or with EPA_DENSITY_REBUILD=1.
"""
import gzip, io, json, math, os, pathlib, subprocess, sys, time, urllib.request

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pmtiles", "pillow", "numpy", "mapbox-vector-tile"], check=True)
import numpy as np  # noqa: E402
import mapbox_vector_tile  # noqa: E402
from PIL import Image  # noqa: E402
from pmtiles.reader import MmapSource, Reader, all_tiles  # noqa: E402
from pmtiles.tile import Compression, TileType, zxy_to_tileid  # noqa: E402
from pmtiles.writer import Writer  # noqa: E402

TILES = pathlib.Path("tiles")
SRC = TILES / "epa_efpoints_z6.pmtiles"
SRC_URL = "https://welcometoyourgalaxy.github.io/culprits-tiles-more/tiles/epa_efpoints_z6.pmtiles"
BUILD = TILES / "epa_efpoints.build.json"
INDEX = TILES / "epa_density.json"
TOP = 5
SIZE = 256
# Colour by the number of points in a pixel: neon blue for one point through
# cyan to neon green and pale mint where hundreds share a pixel (round 82b: the
# owner's 80s neon greens and blues; was indigo to cyan).
STEPS = [1, 3, 10, 30, 100, 300]
# Round 85b (asked 27 September): teal to blue, no green (was neon green at the top).
RAMP = [(11, 46, 107, 190), (23, 71, 184, 205), (47, 107, 255, 220), (26, 159, 214, 232), (20, 168, 160, 242), (207, 239, 242, 250)]
PALETTE = "teal-blue-1"


def source_path():
    if SRC.exists():
        return SRC
    tmp = pathlib.Path("/tmp/epa_efpoints_z6.pmtiles")
    print(f"epa_density: reading {SRC_URL}", flush=True)
    with urllib.request.urlopen(urllib.request.Request(SRC_URL, headers={"User-Agent": "Culprits atlas build"}), timeout=900) as r, open(tmp, "wb") as f:
        f.write(r.read())
    return tmp


def main():
    # The points' build list names every file and its size; the pictures are
    # made again only when that changes.
    sig = PALETTE + (BUILD.read_text() if BUILD.exists() else "")
    try:
        was = json.loads(INDEX.read_text()).get("from", None) if INDEX.exists() else None
    except Exception:  # noqa: BLE001
        was = None
    if was is not None and was == sig and not os.environ.get("EPA_DENSITY_REBUILD"):
        print("epa_density: the points have not changed since the pictures were made; kept")
        return
    names = {}
    path = source_path()
    xs, ys, lids = [], [], []
    with open(path, "rb") as fh:
        rd = Reader(MmapSource(fh))
        for (z, x, y), data in all_tiles(rd.get_bytes):
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            layers = mapbox_vector_tile.decode(data, default_options={"y_coord_down": True})
            for lay in layers.values():
                ext = lay.get("extent", 4096)
                for f in lay["features"]:
                    g = f.get("geometry") or {}
                    if g.get("type") != "Point":
                        continue
                    px, py = g["coordinates"][:2]
                    # The buffer round each square repeats its neighbours' points.
                    if not (0 <= px < ext and 0 <= py < ext):
                        continue
                    pr = f.get("properties") or {}
                    lid = pr.get("_lid")
                    if lid is None:
                        continue
                    lid = int(lid)
                    if lid not in names and pr.get("_layer"):
                        names[lid] = str(pr.get("_layer"))
                    xs.append((x + px / ext) / 2 ** z)
                    ys.append((y + py / ext) / 2 ** z)
                    lids.append(lid)
    if not xs:
        raise SystemExit("epa_density: no points read from the zoom-6 file; nothing built")
    X, Y, L = np.array(xs), np.array(ys), np.array(lids)
    print(f"epa_density: {len(X):,} points in {len(set(lids))} EPA layers", flush=True)
    made = []
    for lid in sorted(set(lids)):
        sel = L == lid
        lx, ly = X[sel], Y[sel]
        out = TILES / f"epa_density_{lid}.pmtiles"
        tiles = {}
        for z in range(0, TOP + 1):
            n = SIZE * 2 ** z
            gx = np.clip((lx * n).astype(np.int64), 0, n - 1)
            gy = np.clip((ly * n).astype(np.int64), 0, n - 1)
            key = gy * n + gx
            u, c = np.unique(key, return_counts=True)
            ux, uy = u % n, u // n
            tx, ty = ux // SIZE, uy // SIZE
            order = np.lexsort((ty, tx))
            ux, uy, c, tx, ty = ux[order], uy[order], c[order], tx[order], ty[order]
            cut = np.flatnonzero(np.diff(tx * (2 ** z) + ty)) + 1
            for part in np.split(np.arange(len(c)), cut):
                if not len(part):
                    continue
                img = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
                px, py, cc = ux[part] % SIZE, uy[part] % SIZE, c[part]
                step = np.searchsorted(STEPS, cc, side="right") - 1
                img[py, px] = np.array(RAMP, dtype=np.uint8)[np.clip(step, 0, len(RAMP) - 1)]
                buf = io.BytesIO()
                Image.fromarray(img, "RGBA").save(buf, "PNG", optimize=True)
                tiles[zxy_to_tileid(z, int(tx[part[0]]), int(ty[part[0]]))] = buf.getvalue()
        with open(out, "wb") as f:
            w = Writer(f)
            for tid in sorted(tiles):
                w.write_tile(tid, tiles[tid])
            w.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": 0, "max_zoom": TOP,
                        "min_lon_e7": -1800000000, "min_lat_e7": -850000000, "max_lon_e7": 1800000000, "max_lat_e7": 850000000,
                        "center_zoom": 3, "center_lon_e7": -980000000, "center_lat_e7": 390000000},
                       {"attribution": "US EPA Envirofacts", "name": f"epa_density_{lid}"})
        made.append({"lid": lid, "name": names.get(lid, ""), "points": int(sel.sum()), "file": out.name,
                     "squares": len(tiles), "bytes": out.stat().st_size})
        print(f"  layer {lid} {names.get(lid, '')}: {int(sel.sum()):,} points, {len(tiles)} squares, {out.stat().st_size / 1e6:.2f} MB", flush=True)
    INDEX.write_text(json.dumps({"from": sig, "built": time.strftime("%Y-%m-%d", time.gmtime()), "to_zoom": TOP, "points": int(len(X)),
                                 "steps": STEPS, "colours": ["#%02X%02X%02X" % c[:3] for c in RAMP], "layers": made}, indent=1))
    print(f"epa_density: {len(made)} picture archives written")


if __name__ == "__main__":
    main()
