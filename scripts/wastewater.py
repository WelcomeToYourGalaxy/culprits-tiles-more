#!/usr/bin/env python3
"""
The Global Wastewater Model's five map layers (Tuholske et al. 2021), copied once
into tiles/wastewater_<layer>.pmtiles. Its server hands out its pictures but does
not let other websites draw them, so Culprits draws this copy instead. The model
is a fixed 2021 release, so it is built once; set WASTEWATER_REBUILD=1 to redo it.

Every square down to zoom 3 is copied; below that, a square's four children are
copied only where the square itself shows something, down to zoom 7 (about
1.2 km a pixel at the equator, the model's own grid is about 1 km), so the empty ocean is not fetched square by square.
"""
import io, os, pathlib, subprocess, sys, time, urllib.error, urllib.request

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pmtiles", "pillow"], check=True)
from PIL import Image  # noqa: E402
from pmtiles.tile import Compression, TileType, zxy_to_tileid  # noqa: E402
from pmtiles.writer import Writer  # noqa: E402

BASE = "https://mazu.nceas.ucsb.edu/wastewater"
LAYERS = ["N_effluent", "N_effluent_treated", "N_effluent_septic", "N_effluent_open", "N_plumes"]
OUT = pathlib.Path("tiles")
FULL_TO, MAX_Z = 3, 7
LIMIT = 95 * 1024 * 1024          # GitHub refuses files over 100 MB


def fetch(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Culprits atlas copy (github.com/WelcomeToYourGalaxy/culprits)"})
            return urllib.request.urlopen(req, timeout=60).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
    return None


def shows_something(png):
    try:
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        return im.getchannel("A").getextrema()[1] > 0
    except Exception:  # noqa: BLE001
        return True


def build(layer):
    path = OUT / f"wastewater_{layer}.pmtiles"
    if path.exists() and not os.environ.get("WASTEWATER_REBUILD"):
        print(f"wastewater {layer}: already built")
        return
    tiles, todo, asked = {}, [(0, 0, 0)], 0
    while todo:
        z, x, y = todo.pop()
        png = fetch(f"{BASE}/{layer}/{z}/{x}/{y}.png")
        asked += 1
        if png is None:
            continue
        full = shows_something(png)
        if full:
            tiles[zxy_to_tileid(z, x, y)] = png
        if z < MAX_Z and (z < FULL_TO or full):
            todo.extend((z + 1, 2 * x + dx, 2 * y + dy) for dx in (0, 1) for dy in (0, 1))
        time.sleep(0.02)
    if not tiles:
        print(f"wastewater {layer}: nothing came back ({asked} squares asked)", file=sys.stderr)
        return
    OUT.mkdir(exist_ok=True)
    for top in range(MAX_Z, -1, -1):
        keep = {t: d for t, d in tiles.items() if t < zxy_to_tileid(top + 1, 0, 0)}
        with open(path, "wb") as f:
            w = Writer(f)
            for tid in sorted(keep):
                w.write_tile(tid, keep[tid])
            w.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": 0, "max_zoom": top,
                        "min_lon_e7": -1800000000, "min_lat_e7": -850000000, "max_lon_e7": 1800000000, "max_lat_e7": 850000000,
                        "center_zoom": 1, "center_lon_e7": 0, "center_lat_e7": 0},
                       {"attribution": "Tuholske et al. 2021, Global Wastewater Model", "name": layer})
        if path.stat().st_size <= LIMIT:
            break
        print(f"wastewater {layer}: {path.stat().st_size / 1e6:.0f} MB to zoom {top} is over the limit; trying one level less")
    print(f"wastewater {layer}: {len(tiles)} squares kept of {asked} asked ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    for layer in LAYERS:
        build(layer)
