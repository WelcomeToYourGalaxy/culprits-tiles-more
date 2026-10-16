#!/usr/bin/env python3
"""
How much people have changed the land inside each protected area, for the
Invasion of non-humans map (round nh2, asked 16 October). The owner's page
cites the finding behind it (footnote 19.5: Jones, K.R. et al. 2018, "One-
third of global protected land is under intense human pressure", Science
360: 788-791, which used the human footprint); here the same question is
asked of the Global Human Modification map.

Sources: Kennedy, C.M. et al. 2019, "Managing the middle: A shift in
conservation priorities based on the global human modification gradient",
Global Change Biology 25: 811-826, the 1 km Global Human Modification map
(gHM, about 2016) on figshare (article 7283087), CC BY 4.0; and the public
release of the World Database on Protected Areas (UNEP-WCMC and IUCN).

For every protected or conserved area with a boundary: the average human
modification inside it (0 none to 1 complete) and the share of its area in
each of Kennedy et al.'s four classes: low (under 0.1), moderate (0.1 to
0.4), high (0.4 to 0.7) and very high (0.7 and over). Cells are weighted by
how much of each the boundary covers (exactextract). Areas the database gives
only as a point have no area to measure and are counted in the build file.
Only the area's id and these figures are kept, never its shape; the map
colours the areas Global Forest Watch draws by their id.

  nonhuman/pa_pressure.json, nonhuman/pa_pressure.build.json

Monthly (the database is updated monthly); PAPRESSURE_REBUILD=1 builds at once.
"""
import json, os, pathlib, re, sys, tempfile, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402
import nhwdpa  # noqa: E402

NAME = "pa_pressure"
ARTICLE = "https://api.figshare.com/v2/articles/7283087"
CLASSES = [(0.0, 0.1, "low"), (0.1, 0.4, "moderate"), (0.4, 0.7, "high"), (0.7, 1.01, "very high")]


def main():
    if not nh.due(NAME, 30, "PAPRESSURE_REBUILD", hand=False):
        return
    nh.pip("geopandas", "pyogrio", "shapely>=2", "pyproj", "pandas", "rasterio", "exactextract")
    import numpy as np
    import rasterio
    from exactextract import exact_extract
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp()) / "papressure"
    work.mkdir(parents=True, exist_ok=True)
    art = nh.get_json(ARTICLE)
    files = sorted(art.get("files") or [], key=lambda f: -int(f.get("size") or 0))
    f = next((x for x in files if re.search(r"\.(tif|tiff|zip)$", x["name"], re.I)), None)
    if not f:
        nh.write_stamp(NAME, {"failed": True, "files": [x.get("name") for x in files]})
        raise SystemExit("pa pressure: no GeoTIFF or zip in the figshare article")
    p = nh.download(f["download_url"], work / f["name"], "gHM")
    if p.suffix.lower() == ".zip":
        z = zipfile.ZipFile(p)
        tifs = sorted([n for n in z.namelist() if n.lower().endswith((".tif", ".tiff"))], key=lambda n: -z.getinfo(n).file_size)
        z.extract(tifs[0], work)
        p = work / tifs[0]
    # The classes as a second raster, written block by block.
    cls = work / "ghm_classes.tif"
    with rasterio.open(p) as src:
        prof = src.profile.copy()
        nod = src.nodata
        crs = src.crs
        prof.update(dtype="uint8", nodata=0, compress="deflate", count=1)
        with rasterio.open(cls, "w", **prof) as dst:
            for _, win in src.block_windows(1):
                a = src.read(1, window=win).astype("float32")
                out = np.zeros(a.shape, np.uint8)
                ok = np.isfinite(a) & ((a != nod) if nod is not None else True) & (a >= 0)
                for i, (lo, hi, _) in enumerate(CLASSES):
                    out[ok & (a >= lo) & (a < hi)] = i + 1
                dst.write(out, 1, window=win)
    P, Q, wdpa, used = nhwdpa.get(work, want=("pa_id",))
    P = P.to_crs(crs)
    print(f"pa pressure: {len(P):,} areas with a boundary", flush=True)
    means = exact_extract(str(p), P, ["mean"], include_cols=["pa_id"], output="pandas")
    fracs = exact_extract(str(cls), P, ["unique", "frac"], include_cols=["pa_id"], output="pandas")
    ids = {}
    for (_, m), (_, fr) in zip(means.iterrows(), fracs.iterrows()):
        pid = str(m["pa_id"]).removesuffix(".0")
        mean = m["mean"]
        shares = [0, 0, 0, 0]
        for u, fv in zip(list(fr["unique"]) if fr["unique"] is not None else [], list(fr["frac"]) if fr["frac"] is not None else []):
            if 1 <= int(u) <= 4:
                shares[int(u) - 1] = round(float(fv) * 100, 1)
        if mean is None or mean != mean:
            continue
        # The same id can be several shapes (parts of one area): the first is kept,
        # the others counted.
        ids.setdefault(pid, [round(float(mean), 3)] + shares)
    nh.write_json("pa_pressure.json", {"source": "Global Human Modification (Kennedy et al. 2019, figshare 7283087, CC BY 4.0) inside each area of " + wdpa,
                                       "fields": ["mean human modification (0 to 1)", "% low", "% moderate", "% high", "% very high"],
                                       "classes": [[lo, hi, w] for lo, hi, w in CLASSES], "ids": ids,
                                       "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")})
    nh.write_stamp(NAME, {"file": f["name"], "raster crs": str(crs), "areas with a boundary": len(P), "areas measured": len(ids),
                          "areas given only as a point (not measured)": 0 if Q is None else len(Q), "wdpa": wdpa, "wdpa layers read": used})


if __name__ == "__main__":
    main()
