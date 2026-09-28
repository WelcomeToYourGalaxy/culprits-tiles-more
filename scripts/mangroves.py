#!/usr/bin/env python3
"""
Mangroves that show from the world view: the map's own copy of Global Mangrove
Watch (round 90b, asked 27 September: Global Safety Net's "Trees, mangrove"
layer was too small and faint to see from a global view).

Source: Global Mangrove Watch version 4.0.19, mangrove extent in 2020 at 10 m,
Zenodo record 12756047 (CC BY 4.0), gmw_mng_2020_v4019_gtiff.zip: GeoTIFF
squares of 1 degree, 1 where there is mangrove.

Each square is read onto a grid of 0.005 degrees (about 550 m), a cell marked
if any mangrove falls in it; wider out each map pixel is marked if any cell
under it is. So a coast's thin fringe of mangrove stays a visible line at every
zoom, which a picture that averages it away cannot give.

  tiles/own_mangroves.pmtiles        zooms 0 to 8
  tiles/own_mangroves.choices.json   the row's choice and its key

Built once; OWN_REBUILD=1 builds it again.
"""
import os, pathlib, sys, tempfile, time, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

URL = "https://zenodo.org/records/12756047/files/gmw_mng_2020_v4019_gtiff.zip"
ROW = "own_mangroves"
OUT = pathlib.Path("tiles") / f"{ROW}.pmtiles"
RES = 0.005
WEST, EAST, SOUTH, NORTH = -180.0, 180.0, -45.0, 40.0
COLOUR = "#3FC0C9"


def main():
    if OUT.exists() and (pathlib.Path("tiles") / f"{ROW}.choices.json").exists() and not os.environ.get("OWN_REBUILD"):
        print(f"{ROW}: already built")
        return
    pyramid.need("rasterio")
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    z = pyramid.download(URL, pathlib.Path(tempfile.gettempdir()) / "gmw2020.zip", ROW)
    tifs = [n for n in zipfile.ZipFile(z).namelist() if n.lower().endswith((".tif", ".tiff"))]
    print(f"{ROW}: {len(tifs)} squares in the zip", flush=True)
    H, W = int(round((NORTH - SOUTH) / RES)), int(round((EAST - WEST) / RES))
    grid = np.zeros((H, W), np.uint8)
    t0, marked = time.time(), 0
    for k, name in enumerate(tifs):
        with rasterio.open(f"/vsizip/{z}/{name}") as src:
            b = src.bounds
            r0, r1 = int(round((NORTH - b.top) / RES)), int(round((NORTH - b.bottom) / RES))
            c0, c1 = int(round((b.left - WEST) / RES)), int(round((b.right - WEST) / RES))
            r0, c0 = max(0, r0), max(0, c0)
            r1, c1 = min(H, r1), min(W, c1)
            if r1 <= r0 or c1 <= c0:
                continue
            a = src.read(1, out_shape=(r1 - r0, c1 - c0), resampling=Resampling.max)
            nod = src.nodata
            hit = (a > 0) if nod is None else ((a > 0) & (a != nod))
            grid[r0:r1, c0:c1] |= hit.astype(np.uint8)
            marked += int(hit.sum())
        if k % 100 == 99:
            print(f"{ROW}: {k + 1} of {len(tifs)} squares read, {marked:,} cells with mangrove, {time.time() - t0:.0f} s", flush=True)
    if not grid.any():
        raise SystemExit(f"{ROW}: no mangrove read from the squares")
    pyramid.build(grid, WEST, NORTH, RES, {1: pyramid.rgba(COLOUR)}, OUT, 8, how="max",
                  attribution="Global Mangrove Watch v4.0.19 (CC BY 4.0)", name=ROW,
                  meta={"from": URL, "year": 2020, "resolution_deg": RES, "squares": len(tifs), "cells": int(grid.sum())})
    pyramid.write_choices(ROW, [{"label": "2020", "archive": f"tiles/{ROW}.pmtiles",
                                 "key": [[COLOUR, "mangrove anywhere under the pixel"]]}])


if __name__ == "__main__":
    main()
