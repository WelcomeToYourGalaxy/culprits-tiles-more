#!/usr/bin/env python3
"""
Pesticides sprayed on crops, by active ingredient, 2015, 2020 and 2025, for
the Invasion of non-humans map.

Source: Maggi, F., Tang, F.H.M., la Cecilia, D. and McBratney, A. 2020, Global
Pesticide Grids (PEST-CHEMGRIDS), Version 1.01, NASA SEDAC,
doi:10.7927/weq9-pv30, CC BY 4.0 (the paper: Maggi et al. 2019, Scientific
Data 6: 170). The application-rate GeoTIFFs (kg per hectare per year, 5 arc-
minutes), one per crop class, active ingredient, year and high or low
estimate, are read from the GeoTIFF zip on NASA Earthdata (the repository's
EARTHDATA_USER and EARTHDATA_PASS). Every file in it is read.

For each active ingredient, year and estimate, the rates on all crop classes
are added (the kilograms applied to a hectare of all its crops together), and
"All ingredients together" adds every ingredient. Each is drawn in tenths of
that ingredient's own values over its six maps (so 2015 and 2025 can be
compared), lightest the least; where none is applied nothing is drawn.

Negative values in the files mark no data and are not added.

  nonhuman/pest_grids.json, nonhuman/pestgrids/*.pmtiles, nonhuman/pest_grids.build.json

A fixed release: built once (each run picks up where the last stopped);
PESTGRIDS_REBUILD=1 builds again.
"""
import collections, json, os, pathlib, re, sys, tempfile, time, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "pest_grids"
ZIP_URL = ("https://data.earthdata.nasa.gov/nasa-earth/human-dimensions/sedac-root/downloads/data/ferman-v1/"
           "ferman-v1-pest-chemgrids-v1-01/ferman-v1-pest-chemgrids-v1-01-geotiff.zip")
TOP = 4   # a zoom-4 pixel is about 10 km, close to the grids' own 5 arc-minutes (about 9 km)
START, BUDGET = time.time(), 140 * 60
PAT = re.compile(r"APR_(?P<crop>[A-Za-z]+)_(?P<ai>.+?)_(?P<year>20\d\d)_(?P<est>[HL])\.tif$", re.I)


def main():
    done_file = nh.OUT / "pest_grids.json"
    st = nh.read_stamp(NAME)
    if done_file.exists() and st.get("complete") and not os.environ.get("PESTGRIDS_REBUILD"):
        print("pest grids: built; a fixed release (set PESTGRIDS_REBUILD=1 to build again)")
        return
    pyr = nh.lib_pyramid()
    pyr.need("rasterio", "requests")
    import numpy as np
    import rasterio
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
    import earthdata
    if not earthdata.have_login():
        nh.write_stamp(NAME, {"failed": True, "error": "EARTHDATA_USER and EARTHDATA_PASS are not set"})
        raise SystemExit("pest grids: no Earthdata login")
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp())
    zpath = nh.download(ZIP_URL, work / "pest-chemgrids-geotiff.zip", "PEST-CHEMGRIDS", session=earthdata.session())
    z = zipfile.ZipFile(zpath)
    names = [n for n in z.namelist() if n.lower().endswith(".tif")]
    groups = collections.defaultdict(list)
    skipped = []
    for n in names:
        m = PAT.search(n.split("/")[-1])
        if m:
            groups[m["ai"]].append((m["crop"], int(m["year"]), m["est"].upper(), n))
        else:
            skipped.append(n.split("/")[-1])
    if not groups:
        nh.write_stamp(NAME, {"failed": True, "error": "no application-rate files matched", "some names": names[:40]})
        raise SystemExit("pest grids: no files matched APR_<crop>_<ingredient>_<year>_<H|L>.tif")
    print(f"pest grids: {len(names)} GeoTIFFs, {len(groups)} active ingredients, {len(skipped)} other files", flush=True)
    prev = {}
    if done_file.exists() and not os.environ.get("PESTGRIDS_REBUILD"):
        try:
            prev = {g["name"]: g for g in json.loads(done_file.read_text()).get("ingredients", [])}
        except Exception:
            prev = {}
    geo = None
    totals = {}

    def read(n):
        nonlocal geo
        with rasterio.open(f"zip://{zpath}!/{n}") as src:
            a = src.read(1).astype("float32")
            nod = src.nodata
            if geo is None:
                t = src.transform
                geo = (t.c, t.f, t.a, abs(t.e))
        if nod is not None:
            a[a == nod] = np.nan
        a[a < 0] = np.nan
        return a

    def draw(label, slug, grids):
        pooled = np.concatenate([g[np.isfinite(g) & (g > 0)] for g in grids.values()]) if grids else np.array([])
        cuts = nh.tenths(pooled) if pooled.size else []
        lo, hi = (float(pooled.min()), float(pooled.max())) if pooled.size else (0.0, 0.0)
        key, pal = nh.ramp_key(cuts, lo, hi, "")
        choices = []
        for (year, est), g in sorted(grids.items()):
            out = nh.OUT / "pestgrids" / f"{slug}_{year}_{est}.pmtiles"
            pyr.build(nh.coded(g, cuts), geo[0], geo[1], geo[2], pal, out, TOP, how="max",
                      attribution="PEST-CHEMGRIDS v1.01 (Maggi et al.), NASA SEDAC, CC BY 4.0", name=out.stem,
                      meta={"ingredient": label, "year": year, "estimate": est})
            choices.append({"year": year, "est": est, "archive": f"{pyr.PAGES}nonhuman/pestgrids/{out.name}", "key": key})
        return {"name": label, "choices": choices}

    ingredients, report = [], {}
    for ai in sorted(groups, key=str.lower):
        if time.time() - START > BUDGET:
            report["stopped"] = f"time budget reached before {ai}; the next run carries on"
            break
        files = groups[ai]
        grids = {}
        for crop, year, est, n in files:
            a = read(n)
            k = (year, est)
            grids[k] = a if k not in grids else np.where(np.isnan(grids[k]), a, np.where(np.isnan(a), grids[k], grids[k] + a))
            totals[k] = a.copy() if k not in totals else np.where(np.isnan(totals[k]), a, np.where(np.isnan(a), totals[k], totals[k] + a))
        # An ingredient drawn by an earlier run is kept; its numbers are still
        # read above, for the total of all ingredients.
        reuse = ai in prev and not os.environ.get("PESTGRIDS_REBUILD") and \
            all((nh.OUT / "pestgrids" / c["archive"].split("/")[-1]).exists() for c in prev[ai]["choices"])
        ingredients.append(prev[ai] if reuse else draw(ai, "ai_" + nh.slug(ai), grids))
        report[ai] = {"files": len(files), "crops": sorted({f[0] for f in files}), "kept from the last run": reuse}
        print(f"  {ai}: {len(files)} files{' (kept)' if reuse else ''}", flush=True)
    complete = "stopped" not in report
    if complete and totals:
        ingredients.insert(0, draw("All ingredients together", "all_ingredients", totals))
    if complete and totals:
        ingredients = [ingredients[0]] + sorted(ingredients[1:], key=lambda g: g["name"].lower())
    nh.write_json("pest_grids.json", {"source": "PEST-CHEMGRIDS v1.01, NASA SEDAC doi:10.7927/weq9-pv30 (CC BY 4.0)", "ingredients": ingredients,
                                      "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")})
    nh.write_stamp(NAME, {"complete": complete, "ingredients": len(groups), "geotiffs": len(names), "other files": skipped[:200], "by ingredient": report})


if __name__ == "__main__":
    main()
