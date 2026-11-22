#!/usr/bin/env python3
"""
How much people have changed the land, 1990 to 2022, for the Invasion of
non-humans map (round nh11, asked 18 October: a layer on how much people
have changed the land today, comprehensive enough to stand for every kind of
pressure at once).

Source: Theobald, D.M., Oakleaf, J.R., Moncrieff, G., Voigt, M., Kiesecker, J.
and Kennedy, C.M. 2025, "Global extent and change in human modification of
terrestrial ecosystems from 1990 to 2022", Scientific Data 12: 489,
doi:10.1038/s41597-025-04892-2; the Global Human Modification v3 maps on
Zenodo, CC BY 4.0:
  record 14449495  1990, 1995, 2000, 2005, 2010, 2015, 2020 ("change-consistent")
  record 14502573  2022
Each year has the overall score (all threats combined, AA) and each of the
eight kinds of threat it is built from: agriculture (AG), built-up land (BU),
energy production and mining (EX), biological resource use (FR), human
accessibility (HI), natural system modification (NS), pollution (PO), and
transportation and service corridors (TI). Every map is 0 (untouched) to 1
(completely changed) at 300 m.

The files are cloud-optimised GeoTIFFs (9.5 GB each for the overall score), so
nothing is downloaded whole: each is read over the network at one of the
overviews the file carries, the overall score at 1/8 of its detail (about
2.4 km, drawn to zoom 6) and each kind of threat at 1/16 (about 4.8 km, zoom
5), each pixel the average of the 300 m cells under it. Every map is coloured
in the same tenths of 0 to 1, so years and kinds can be compared; 0 is left
clear.

  nonhuman/ghm3.json, nonhuman/ghm3/*.pmtiles, nonhuman/ghm3.build.json

Fixed releases: built once (each run carries on where the last stopped);
GHM3_REBUILD=1 builds again.
"""
import json, os, pathlib, re, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "ghm3"
RECORDS = ["14449495", "14502573"]
KINDS = [("AA", "All threats combined"), ("AG", "Agriculture"), ("BU", "Built-up land"), ("EX", "Energy production and mining"),
         ("FR", "Biological resource use (logging, hunting, fishing)"), ("HI", "Human accessibility"),
         ("NS", "Natural system modification (dams, reservoirs, water taken)"), ("PO", "Pollution"),
         ("TI", "Transportation and service corridors (roads, railways, power lines)")]
CUTS = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
START, BUDGET = time.time(), 140 * 60
ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,/content", GDAL_HTTP_MULTIRANGE="YES",
           GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES", GDAL_HTTP_MAX_RETRY="8", GDAL_HTTP_RETRY_DELAY="10", VSI_CACHE="TRUE")


def main():
    st = nh.read_stamp(NAME)
    meta_p = nh.OUT / "ghm3.json"
    if meta_p.exists() and st.get("complete") and not os.environ.get("GHM3_REBUILD"):
        print("ghm3: built; fixed releases (set GHM3_REBUILD=1 to build again)")
        return
    pyr = nh.lib_pyramid()
    pyr.need("rasterio")
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    files = {}
    report = {"records": {}, "built": [], "skipped": []}
    for rec in RECORDS:
        j = nh.get_json(f"https://zenodo.org/api/records/{rec}")
        report["records"][rec] = {"title": (j.get("metadata") or {}).get("title"), "licence": ((j.get("metadata") or {}).get("license") or {}).get("id"),
                                  "files": len(j.get("files") or [])}
        for f in j.get("files") or []:
            m = re.match(r"HMv\d+_(\d{4})[cs]_([A-Z]{2})(?:_300)?\.tif$", f["key"])
            if m:
                files[(int(m.group(1)), m.group(2))] = f"https://zenodo.org/api/records/{rec}/files/{f['key']}/content"
    years = sorted({y for y, _ in files})
    if not years:
        nh.write_stamp(NAME, dict(report, failed=True, error="no HMv..._YEAR_KIND.tif files in the records"))
        raise SystemExit("ghm3: no files found")
    key, pal = nh.ramp_key(CUTS, 0, 1, "")
    meta = json.loads(meta_p.read_text()) if meta_p.exists() and not os.environ.get("GHM3_REBUILD") else {}
    meta.update({"source": "Theobald et al. 2025, Scientific Data 12: 489; Global Human Modification v3, Zenodo 14449495 and 14502573",
                 "licence": "CC BY 4.0", "years": years, "key": key})
    kinds = {k["code"]: k for k in meta.get("kinds", [])}
    complete = True
    for code, words in KINDS:
        k = kinds.setdefault(code, {"code": code, "label": words, "steps": []})
        k["label"] = words
        have = {s["year"] for s in k["steps"]} | set(k.get("empty", []))
        for y in years:
            if (y, code) not in files or y in have:
                continue
            if time.time() - START > BUDGET:
                complete = False
                break
            top, step = (6, 8) if code == "AA" else (5, 16)
            url = files[(y, code)]
            out = nh.OUT / "ghm3" / f"{code.lower()}_{y}.pmtiles"
            t0 = time.time()
            try:
                with rasterio.Env(**ENV):
                    with rasterio.open("/vsicurl/" + url) as src:
                        t = src.transform
                        a = src.read(1, out_shape=(src.height // step, src.width // step), resampling=Resampling.average)
                        res = t.a * src.width / a.shape[1]
                        west, north = t.c, t.f
                a = np.nan_to_num(a, nan=0)
                a[(a < 0) | (a > 1)] = 0
                code_grid = nh.coded(a, CUTS)
                if not code_grid.any():
                    report["skipped"].append(f"{code} {y}: nothing above 0")
                    k.setdefault("empty", []).append(y)
                    continue
                pyr.build(code_grid, west, north, res, pal, out, top, how="mean", attribution="Global Human Modification v3 (Theobald et al. 2025), CC BY 4.0",
                          name=out.stem, meta={"year": y, "kind": code})
                del a, code_grid
            except Exception as e:
                report["skipped"].append(f"{code} {y}: {e}"[:300])
                complete = False
                continue
            k["steps"].append({"year": y, "label": str(y), "archive": f"{pyr.PAGES}nonhuman/ghm3/{out.name}"})
            k["steps"].sort(key=lambda s: s["year"])
            report["built"].append(f"{code} {y} ({time.time() - t0:.0f} s)")
            meta["kinds"] = [kinds[c] for c, _ in KINDS if c in kinds]
            nh.write_json("ghm3.json", meta, compact=False)
        if not complete:
            break
    meta["kinds"] = [kinds[c] for c, _ in KINDS if c in kinds]
    nh.write_json("ghm3.json", meta, compact=False)
    want = sum(1 for (y, c) in files if c in dict(KINDS))
    got = sum(len(k["steps"]) + len(k.get("empty", [])) for k in meta["kinds"])
    nh.write_stamp(NAME, dict(report, complete=complete and got >= want, maps=got, of=want, failed=not got))


if __name__ == "__main__":
    main()
