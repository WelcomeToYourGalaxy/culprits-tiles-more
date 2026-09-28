#!/usr/bin/env python3
"""
The human footprint and the wilderness left, 2024: the map's own layer in place
of Global Safety Net's "Wild & Intact Areas" (round 90b, asked 27 September).
Global Safety Net draws that layer from Venter et al. 2016's wilderness and
Plumptre et al.'s intact places (the second not published); this uses the
newest release of the same measure.

Source: Mu, H. et al. 2022, "A global record of annual terrestrial Human
Footprint dataset from 2000 to 2018", Scientific Data 9:176, extended to 2024
in figshare doi:10.6084/m9.figshare.16571064 version 8 (CC BY 4.0): eight
pressures (built land, cropland, pasture, population, night lights, roads,
railways, navigable waterways) summed on Venter et al.'s 0 to 50 scale, 1 km,
World Mollweide.

Wilderness is a footprint under 1 (Allan, Venter and Watson 2017, Scientific
Data 4:170187); Venter et al. 2016 found a footprint of 4 to be about the
pressure of pasture. The other steps are this map's, for reading the rest.

  tiles/own_wilderness.pmtiles           every level, five steps
  tiles/own_wilderness_only.pmtiles      the wilderness alone
  tiles/own_wilderness.choices.json      the two, and their keys

Built once; OWN_REBUILD=1 builds it again.
"""
import os, pathlib, sys, tempfile, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

URL = "https://ndownloader.figshare.com/files/59321030"        # hfp2024, per the figshare record's file list
ROW = "own_wilderness"
OUT = pathlib.Path("tiles") / f"{ROW}.pmtiles"
ONLY = pathlib.Path("tiles") / f"{ROW}_only.pmtiles"
RES = 0.01
STEPS = [0, 1, 4, 10, 20]


def newest():
    """The newest year's file on the figshare record, read from its API; the
    2024 file's own address if the API cannot be read."""
    import json, re, urllib.request
    try:
        with urllib.request.urlopen(urllib.request.Request("https://api.figshare.com/v2/articles/16571064",
                                                           headers={"User-Agent": "Culprits atlas build"}), timeout=60) as r:
            files = json.loads(r.read()).get("files", [])
        years = [(int(m[1]), f) for f in files for m in [re.search(r"(20\d\d)", f.get("name", ""))] if m and f.get("download_url")]
        if years:
            y, f = max(years, key=lambda t: t[0])
            print(f"{ROW}: newest on the record: {f['name']} ({y})", flush=True)
            return f["download_url"], y
    except Exception as e:  # noqa: BLE001
        print(f"{ROW}: figshare's API did not answer ({e}); using the 2024 file", flush=True)
    return URL, 2024


def main():
    if OUT.exists() and ONLY.exists() and (pathlib.Path("tiles") / f"{ROW}.choices.json").exists() and not os.environ.get("OWN_REBUILD"):
        print(f"{ROW}: already built")
        return
    pyramid.need("rasterio")
    import numpy as np
    url, year = newest()
    z = pyramid.download(url, pathlib.Path(tempfile.gettempdir()) / f"hfp{year}.zip", ROW)
    names = [n for n in zipfile.ZipFile(z).namelist() if n.lower().endswith((".tif", ".tiff"))]
    if not names:
        raise SystemExit(f"{ROW}: no GeoTIFF in {URL}: {zipfile.ZipFile(z).namelist()[:10]}")
    print(f"{ROW}: reading {names[0]}", flush=True)
    a, west, north = pyramid.read_grid(f"/vsizip/{z}/{names[0]}", RES, resampling="average")
    a[(a < 0) | (a > 50.5)] = np.nan
    codes = np.zeros(a.shape, np.uint8)
    ok = ~np.isnan(a)
    for i, lo in enumerate(STEPS):
        codes[ok & (a >= lo)] = i + 1
    wild = (codes == 1).astype(np.uint8)
    print(f"{ROW}: {int(ok.sum()):,} land cells, {int(wild.sum()):,} of them wilderness", flush=True)
    del a
    ramp = pyramid.RAMP5
    att = "Mu et al. annual human footprint, figshare v8 (CC BY 4.0)"
    pyramid.build(codes, west, north, RES, {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(ramp)}, OUT, 6, how="mean",
                  attribution=att, name=ROW, meta={"from": url, "file": names[0], "year": year, "steps": STEPS})
    pyramid.build(wild, west, north, RES, {1: pyramid.rgba("#1E8C8A", 235)}, ONLY, 7, how="max",
                  attribution=att, name=ROW + "_only", meta={"from": url, "file": names[0], "year": year, "wilderness": "footprint under 1"})
    labels = ["under 1: wilderness", "1 to 4", "4 to 10 (4 is about the pressure of pasture)", "10 to 20", "20 to 50"]
    pyramid.write_choices(ROW, [
        {"label": f"the wilderness left, {year}", "archive": f"tiles/{ROW}_only.pmtiles", "key": [["#1E8C8A", "human footprint under 1 of 50"]]},
        {"label": f"every level of footprint, {year}", "archive": f"tiles/{ROW}.pmtiles", "key": [[c, l] for c, l in zip(ramp, labels)]},
    ])


if __name__ == "__main__":
    main()
