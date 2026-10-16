#!/usr/bin/env python3
"""
Wetlands drained since 1700, decade by decade, for the Invasion of
non-humans map (round nh2, asked 16 October).

Source: Fluet-Chouinard, E. et al. 2023, "Extensive global wetland loss over
the past three centuries", Nature 614: 281-286; data on Zenodo (record
7616651, newest version). The gridded maps of wetland drained or converted
from 1700 to 2020 are read from whatever files the record holds (GeoTIFF or
NetCDF); every map with a year in its name, description or time step is
drawn, all in the same tenths so the decades can be compared. Which files,
variables, units and years were read is written to the build file.

  nonhuman/wetlands.json, nonhuman/wetlands/*.pmtiles, nonhuman/wetlands.build.json

A fixed release: built once (each run picks up where the last stopped);
WETLANDS_REBUILD=1 builds again.
"""
import json, os, pathlib, re, sys, tempfile, time, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "wetlands"
RECORD = "https://zenodo.org/api/records/7616651/versions/latest"
START, BUDGET = time.time(), 140 * 60
EXT = r"\.(tif|tiff|nc|nc4|asc)$"


def year_in(text, lo=1700, hi=2030):
    for m in re.finditer(r"(?<!\d)(1[7-9]\d\d|20[0-3]\d)(?!\d)", str(text)):
        y = int(m.group(1))
        if lo <= y <= hi:
            return y
    return None


def bands_of(path):
    import rasterio
    out = []
    with rasterio.open(path) as src:
        subs = list(src.subdatasets or [])
    for sd in (subs or [path]):
        with rasterio.open(sd) as s:
            for b in range(1, s.count + 1):
                tags = s.tags(b)
                text = " ".join([s.descriptions[b - 1] or "", json.dumps(tags), sd.split("/")[-1]])
                y = year_in(tags.get("NETCDF_DIM_time", "")) or year_in(text)
                out.append({"path": sd, "band": b, "year": y, "label": text[:200], "units": tags.get("units") or s.tags().get("units")})
    return out


def main():
    st = nh.read_stamp(NAME)
    if (nh.OUT / "wetlands.json").exists() and st.get("complete") and not os.environ.get("WETLANDS_REBUILD"):
        print("wetlands: built; a fixed release (set WETLANDS_REBUILD=1 to build again)")
        return
    pyr = nh.lib_pyramid()
    pyr.need("rasterio", "netCDF4")
    import numpy as np
    import rasterio
    rec = nh.get_json(RECORD)
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp()) / "wetlands"
    work.mkdir(parents=True, exist_ok=True)
    files = rec.get("files") or []
    paths = []
    for f in files:
        k = f["key"]
        if not re.search(EXT + r"|\.zip$", k, re.I) or int(f.get("size") or 0) > 6e9:
            continue
        p = nh.download(f["links"]["self"], work / k, k)
        if k.lower().endswith(".zip"):
            z = zipfile.ZipFile(p)
            for n in z.namelist():
                if re.search(EXT, n, re.I):
                    z.extract(n, work / "unzipped")
                    paths.append(str(work / "unzipped" / n))
        else:
            paths.append(str(p))
    bands = []
    for p in paths:
        try:
            bands += bands_of(p)
        except Exception as e:
            print(f"  {p}: not readable ({e})", flush=True)
    dated = [b for b in bands if b["year"]]
    report = {"files in the record": [f["key"] for f in files], "version": (rec.get("metadata") or {}).get("version"),
              "bands found": len(bands), "with a year": len(dated), "examples": bands[:20]}
    if not dated:
        nh.write_stamp(NAME, dict(report, failed=True))
        raise SystemExit("wetlands: no dated maps found")
    # Several variables may carry years (drained by cropland, by pasture, ...):
    # each variable is its own choice, with its own timeline.
    groups = {}
    for b in dated:
        var = re.sub(r"\d{4}", "", b["path"].split(":")[-1]) if ":" in b["path"] else pathlib.Path(b["path"]).stem
        var = re.sub(r"(?<!\d)(1[7-9]\d\d|20[0-3]\d)(?!\d)", "", var).strip("_- ")
        groups.setdefault(var, {})
        groups[var].setdefault(b["year"], b)
    choices, complete = [], True
    for var, by in sorted(groups.items()):
        grids = {}
        for y, b in sorted(by.items()):
            with rasterio.open(b["path"]) as s:
                if s.crs is None or s.crs.to_epsg() == 4326:
                    a = s.read(b["band"]).astype("float64")
                    t = s.transform
                    geo = (t.c, t.f, t.a)
                    if t.e > 0:      # stored south-up
                        a = a[::-1]
                        geo = (t.c, t.f + t.e * a.shape[0], t.a)
                    if s.nodata is not None:
                        a[a == s.nodata] = np.nan
                else:
                    a, w, n = pyr.read_grid(b["path"], 1 / 12, band=b["band"])
                    geo = (w, n, 1 / 12)
            grids[y] = (a, geo)
        pooled = np.concatenate([g[np.isfinite(g) & (g > 0)] for g, _ in grids.values()])
        if not pooled.size:
            continue
        cuts = nh.tenths(pooled)
        unit = next((b["units"] for b in by.values() if b.get("units")), "")
        key, pal = nh.ramp_key(cuts, float(pooled.min()), float(pooled.max()), unit or "")
        steps = []
        for y, (a, geo) in sorted(grids.items()):
            if time.time() - START > BUDGET:
                complete = False
                break
            out = nh.OUT / "wetlands" / f"{nh.slug(var)}_{y}.pmtiles"
            if not out.exists() or os.environ.get("WETLANDS_REBUILD"):
                pyr.build(nh.coded(a, cuts), geo[0], geo[1], geo[2], pal, out, 4, how="max", attribution="Fluet-Chouinard et al. 2023", name=out.stem, meta={"variable": var, "year": y})
            steps.append({"year": y, "label": str(y), "archive": f"{pyr.PAGES}nonhuman/wetlands/{out.name}"})
        choices.append({"label": var.replace("_", " "), "unit": unit, "key": key, "steps": steps})
    nh.write_json("wetlands.json", {"source": "Fluet-Chouinard et al. 2023, Nature 614: 281-286; Zenodo 7616651", "choices": choices}, compact=False)
    nh.write_stamp(NAME, dict(report, complete=complete, variables=list(groups), failed=not choices))


if __name__ == "__main__":
    main()
