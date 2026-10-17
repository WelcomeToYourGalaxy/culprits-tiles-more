#!/usr/bin/env python3
"""
Roads cutting into the land, worldwide, for the Invasion of non-humans map
(round nh2, asked 16 October).

Source: the Global Roads Inventory Project, GRIP4 (Meijer, J.R. et al. 2018,
"Global patterns of current and future road infrastructure", Environmental
Research Letters 13: 064006; PBL Netherlands Environmental Assessment Agency),
the road density maps in its Zenodo record 6420961: metres of road per square
kilometre at 5 arc-minutes, for all roads and for each of its five road types
(highways, primary, secondary, tertiary, local). Every density map in the
record is drawn, each in tenths of its own values; the licence the record
states is written to the build file.

  nonhuman/roads.json, nonhuman/roads/*.pmtiles, nonhuman/roads.build.json

Each density zip also holds the map of land area per cell
(grip4_area_land_km2), the same in every zip: it is not a road map and is left
out (round nh4; round nh2 drew it six times).

A fixed release: built once (and once more after round nh4's mend);
ROADS_REBUILD=1 builds again.
"""
import os, pathlib, re, sys, tempfile, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "roads"
RECORD = "https://zenodo.org/api/records/6420961"
TYPES = {"tp1": "highways", "tp2": "primary roads", "tp3": "secondary roads", "tp4": "tertiary roads", "tp5": "local roads",
         "total": "all roads", "all": "all roads"}


def label(name):
    n = name.lower()
    for k, v in TYPES.items():
        if re.search(rf"(^|[_\-.]){k}([_\-.]|$)", n):
            return v
    return re.sub(r"[_\-]+", " ", pathlib.Path(name).stem)


def main():
    if nh.read_stamp(NAME).get("version") == 2 and not nh.due(NAME, None, "ROADS_REBUILD", hand=False):
        return
    pyr = nh.lib_pyramid()
    pyr.need("rasterio")
    import numpy as np
    import rasterio
    rec = nh.get_json(RECORD)
    lic = ((rec.get("metadata") or {}).get("license") or {})
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp()) / "roads"
    work.mkdir(parents=True, exist_ok=True)
    files = rec.get("files") or []
    rasters = []
    for f in files:
        k = f["key"]
        if not re.search(r"dens", k, re.I):
            continue
        p = nh.download(f["links"]["self"], work / k, k)
        if k.lower().endswith(".zip"):
            z = zipfile.ZipFile(p)
            for n in z.namelist():
                if re.search(r"area_land", n, re.I):
                    continue
                if re.search(r"\.(tif|tiff|asc|img)$", n, re.I) and n not in {m for _, m in rasters}:
                    rasters.append((f"zip://{p}!/{n}", n))
        elif re.search(r"\.(tif|tiff|asc|img)$", k, re.I):
            rasters.append((str(p), k))
    choices, report = [], {"files in the record": [f["key"] for f in files], "licence": lic}
    for path, n in rasters:
        try:
            with rasterio.open(path) as src:
                plain = src.crs is None or src.crs.to_epsg() == 4326
                if plain:
                    a = src.read(1).astype("float64")
                    t = src.transform
                    west, north, res = t.c, t.f, t.a
                    if src.nodata is not None:
                        a[a == src.nodata] = np.nan
            if not plain:
                a, west, north = pyr.read_grid(path, 1 / 12)
                res = 1 / 12
            cuts = nh.tenths(a[np.isfinite(a)])
            key, pal = nh.ramp_key(cuts, float(np.nanmin(a[a > 0])), float(np.nanmax(a)), "m per km²")
            stem = nh.slug(pathlib.Path(n).stem)
            out = nh.OUT / "roads" / f"{stem}.pmtiles"
            pyr.build(nh.coded(a, cuts), west, north, res, pal, out, 4, how="max", attribution="GRIP4 (Meijer et al. 2018, PBL)", name=stem, meta={"file": n})
            choices.append({"label": f"Density of {label(n)}", "archive": f"{pyr.PAGES}nonhuman/roads/{out.name}", "key": key})
            report[n] = "built"
        except Exception as e:
            report[n] = f"not built: {e}"[:300]
    stale = nh.OUT / "roads" / "grip4_area_land_km2.pmtiles"
    if stale.exists():
        stale.unlink()
    choices.sort(key=lambda c: (c["label"] != "Density of all roads", c["label"]))
    if choices:
        nh.write_json("roads.json", {"source": "GRIP4, Meijer et al. 2018 (PBL), Zenodo 6420961", "licence": lic.get("id") or lic.get("title"), "choices": choices}, compact=False)
    nh.write_stamp(NAME, dict(report, failed=not choices, version=2))


if __name__ == "__main__":
    main()
