#!/usr/bin/env python3
"""
Risk of pesticide pollution on farmland, worldwide, for the Invasion of
non-humans map.

Source: Tang, F.H.M., Lenzen, M., McBratney, A. and Maggi, F. 2021, "Risk of
pesticide pollution at the global scale", Nature Geoscience 14: 206-210;
data: "Global pesticide pollution risk data sets", figshare
doi:10.6084/m9.figshare.10302218, CC BY 4.0. Three of its GeoTIFFs are drawn:
the risk scores, the regions of concern and the number of active
ingredients. The authors' values are kept as they are: a map whose values
are a few whole numbers is drawn one colour per value; any other is drawn in
tenths of its own values, with the range of each tenth in the key.

  nonhuman/pest_risk.json, nonhuman/pestrisk/*.pmtiles, nonhuman/pest_risk.build.json

A fixed release: built once; PESTRISK_REBUILD=1 builds again.
"""
import pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "pest_risk"
FILES = [
    ("Pesticide pollution risk score", "26221673", "Global_pesticide_risk_scores.tif", "risk_scores", "risk score"),
    ("Regions of concern", "26221682", "Global_regions_of_concern.tif", "regions_of_concern", ""),
    ("How many active ingredients are used", "26221670", "Global_active_ingredient_counts.tif", "ingredient_counts", "ingredients"),
]
CATS = ["#E9E1D3", "#D08A9C", "#9A5878", "#7E92B8", "#2E8FBA", "#0C2E5E", "#B9A6C9", "#C7B49A", "#A9C4D2", "#6E737B", "#E2B8C4", "#13447A"]


def main():
    if not nh.due(NAME, None, "PESTRISK_REBUILD", hand=False):
        return
    pyr = nh.lib_pyramid()
    pyr.need("rasterio")
    import numpy as np
    import rasterio
    work = pathlib.Path(tempfile.mkdtemp())
    choices, report = [], {}
    for label, fid, fname, stem, unit in FILES:
        try:
            p = nh.download(f"https://ndownloader.figshare.com/files/{fid}", work / fname, fname)
            with rasterio.open(p) as src:
                tr, crs, nod = src.transform, src.crs, src.nodata
                plain = crs is not None and crs.to_epsg() == 4326 and abs(tr.e + tr.a) < 1e-9
                if plain:
                    a = src.read(1).astype("float64")
                    west, north, res = tr.c, tr.f, tr.a
            if not plain:
                # Another projection, or cells that are not square: read onto a
                # longitude/latitude grid of 5 arc-minutes, nearest cell.
                a, west, north = pyr.read_grid(str(p), 1 / 12, resampling="nearest")
                a = a.astype("float64")
                res = 1 / 12
                nod = None
            crs = str(crs)
            if nod is not None:
                a[a == nod] = np.nan
            a[~np.isfinite(a)] = np.nan
            vals = a[np.isfinite(a)]
            uniq = np.unique(vals[np.isfinite(vals)])
            info = {"crs": crs, "size": list(a.shape), "cell": res, "nodata": nod, "min": float(np.nanmin(a)), "max": float(np.nanmax(a)),
                    "distinct values": int(uniq.size)}
            if uniq.size <= 12 and np.all(np.equal(np.mod(uniq, 1), 0)):
                codes = np.zeros(a.shape, dtype=np.uint8)
                key, pal = [], {}
                for i, v in enumerate(uniq):
                    codes[a == v] = i + 1
                    c = CATS[i % len(CATS)]
                    key.append([c, f"value {int(v)}"])
                    pal[i + 1] = pyr.rgba(c, 235)
                info["values"] = [int(v) for v in uniq]
            else:
                # Zero is a value here (no risk, no ingredient), not "nothing":
                # tenths are cut over every value at or above zero, shifted so
                # the codes start at 1.
                shift = 0.0
                if np.nanmin(a) <= 0:
                    shift = -float(np.nanmin(a)) + 1e-12
                b = a + shift
                cuts = nh.tenths(b[np.isfinite(b)])
                codes = nh.coded(b, cuts)
                key, pal = nh.ramp_key([c - shift for c in cuts], float(np.nanmin(a)), float(np.nanmax(a)), unit)
                info["tenths cut at"] = [c - shift for c in cuts]
            out = nh.OUT / "pestrisk" / f"{stem}.pmtiles"
            pyr.build(codes, west, north, res, pal, out, 4, how="max", attribution="Tang et al. 2021 (CC BY 4.0)", name=stem, meta=info)
            choices.append({"label": label, "archive": f"{pyr.PAGES}nonhuman/pestrisk/{stem}.pmtiles", "key": key})
            report[stem] = info
        except Exception as e:
            report[stem] = {"error": str(e)[:300]}
            print(f"pest risk {stem}: {e}", flush=True)
    if choices:
        nh.write_json("pest_risk.json", {"source": "Tang et al. 2021, figshare doi:10.6084/m9.figshare.10302218 (CC BY 4.0)", "choices": choices}, compact=False)
    nh.write_stamp(NAME, dict(report, failed=not choices))
    if not choices:
        raise SystemExit("pest risk: nothing built")


if __name__ == "__main__":
    main()
