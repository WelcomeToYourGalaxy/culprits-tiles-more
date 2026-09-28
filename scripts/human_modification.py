#!/usr/bin/env python3
"""
How much people have changed the land, 2022: the map's own copy of the Human
Modification index v3 (round 90b, asked 27 September, in place of Global Safety
Net's "Modified Land (HM90)" layer, which is the same index at 90 m drawn from
Google Earth Engine).

Source: Theobald, D.M. et al. 2025, "A global dataset of human modification of
terrestrial lands, v3", Scientific Data 12:489; the 300 m release for 2022,
Zenodo 10.5281/zenodo.14502573 (CC BY 4.0), a Cloud Optimised GeoTIFF of values
0 (unchanged) to 1 (wholly changed). The 90 m version is published only inside
Earth Engine.

The file is 9.3 GB; it is read over the network at about 1 km from its own
overviews, never downloaded whole.

  tiles/own_modification.pmtiles       zooms 0 to 6 (lower if too large), ten
                                       steps of 0.1, each map pixel the mean
                                       of the cells under it
  tiles/own_modification.choices.json  the row's one choice and its key
  tiles/own_modification.build.json    what it was built from

Built once; OWN_REBUILD=1 builds it again.
"""
import os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

URL = "https://zenodo.org/records/14502573/files/HMv20240801_2022s_AA_300.tif"
ROW = "own_modification"
OUT = pathlib.Path("tiles") / f"{ROW}.pmtiles"
RES = 0.01


def main():
    if OUT.exists() and (pathlib.Path("tiles") / f"{ROW}.choices.json").exists() and not os.environ.get("OWN_REBUILD"):
        print(f"{ROW}: already built")
        return
    pyramid.need("rasterio")
    import numpy as np
    print(f"{ROW}: reading {URL} at {RES} degrees", flush=True)
    a, west, north = pyramid.read_grid("/vsicurl/" + URL, RES, resampling="average")
    a[a < 0] = np.nan
    # Some releases store 0-1 as integers scaled by 10,000 or 100.
    top = np.nanmax(a)
    if top > 1.5:
        a = a / (10000.0 if top > 100 else 100.0)
        print(f"{ROW}: values reach {top:.0f}; read as scaled integers", flush=True)
    codes = np.where(np.isnan(a), 0, np.clip(np.floor(a * 10), 0, 9) + 1).astype(np.uint8)
    del a
    pal = {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(pyramid.RAMP10)}
    pyramid.build(codes, west, north, RES, pal, OUT, 6, how="mean",
                  attribution="Human Modification v3, Theobald et al. 2025 (CC BY 4.0)", name=ROW,
                  meta={"from": URL, "year": 2022, "resolution_deg": RES, "steps": "0.1"})
    key = [[c, f"{i / 10:.1f} to {(i + 1) / 10:.1f}" + (" (little changed)" if i == 0 else " (wholly changed)" if i == 9 else "")]
           for i, c in enumerate(pyramid.RAMP10)]
    pyramid.write_choices(ROW, [{"label": "2022", "archive": f"tiles/{ROW}.pmtiles", "key": key}])


if __name__ == "__main__":
    main()
