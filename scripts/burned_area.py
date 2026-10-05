#!/usr/bin/env python3
"""
Burned area worldwide, year by year since 2001 (round 179b): NASA's MODIS
burned area on the 0.25-degree climate modelling grid (MCD64CMQ, collection
6.1; Giglio et al., MODIS Collection 6.1 Burned Area Product User's Guide).
Each month's file gives the area burned in each 0.25-degree cell; a year's
months are added up and drawn as the share of the cell's area that burned,
in six steps. Needs the Earthdata login (secrets EARTHDATA_USER and
EARTHDATA_PASS). NASA shares the data without restriction (EOSDIS data use
policy), with the citation in the attribution.

A year once built is kept; the current year is rebuilt each run until it is
complete. The science data set's name, units and scale factor are read from
the file and written to tiles/own_burned.build.json, nothing assumed.
"""
import datetime, json, math, os, pathlib, re, subprocess, sys, tempfile, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402
import earthdata  # noqa: E402

ROW = "own_burned"
T = pathlib.Path("tiles")
STAMP = T / f"{ROW}.build.json"
CITE = "MODIS MCD64CMQ v061 burned area, Giglio et al., NASA LP DAAC (EOSDIS, no restriction)"
STEPS = [(0.0, 0.01, "under 1% of the land burned"), (0.01, 0.05, "1 to 5%"), (0.05, 0.1, "5 to 10%"),
         (0.1, 0.25, "10 to 25%"), (0.25, 0.5, "25 to 50%"), (0.5, 9.9, "half or more")]
RAMP6 = ["#D6EEF6", "#8FD6E8", "#3FA9C2", "#2275A8", "#13447A", "#0C2E5E"]
START, BUDGET = time.time(), 140 * 60


def read_month(path):
    """The burned area grid of one month's HDF file, in hectares, and what was read."""
    try:
        from pyhdf.SD import SD, SDC
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyhdf"], check=True)
        from pyhdf.SD import SD, SDC
    import numpy as np
    f = SD(str(path), SDC.READ)
    names = list(f.datasets())
    name = next((n for n in names if re.fullmatch(r"burned[ _]?area", n, re.I)), None) or \
        next((n for n in names if re.search(r"burn", n, re.I) and not re.search(r"uncert|unmapped|qa", n, re.I)), None)
    if not name:
        raise RuntimeError(f"no burned area data set among {names}")
    sds = f.select(name)
    a = sds.get().astype("float64")
    at = sds.attributes()
    fill = at.get("_FillValue")
    if fill is not None:
        a[a == fill] = np.nan
    vr = at.get("valid_range")
    if vr is not None and len(vr) == 2:
        a[(a < vr[0]) | (a > vr[1])] = np.nan
    sf = at.get("scale_factor")
    if sf not in (None, 0, 1):
        a = a * float(sf)
    units = str(at.get("units", ""))
    f.end()
    return a, {"data_set": name, "units": units, "scale_factor": sf, "shape": list(a.shape), "all_data_sets": names}


def main():
    pyramid.need("rasterio", "requests")
    import numpy as np
    T.mkdir(exist_ok=True)
    stamp = json.loads(STAMP.read_text()) if STAMP.exists() else {}
    if not earthdata.have_login():
        stamp.update(built=False, why="no EARTHDATA_USER / EARTHDATA_PASS in the run; see refresh.yml")
        STAMP.write_text(json.dumps(stamp, indent=1))
        print("::warning::burned_area: no Earthdata login in this run")
        return
    coll = earthdata.collection(short_name="MCD64CMQ", version="061")
    links = earthdata.granule_links(coll["id"], suffix=".hdf")
    stamp.update(collection=coll.get("id"), files_listed=len(links))
    by_year = {}
    for l in links:
        y = (l.get("start") or "")[:4]
        if y.isdigit():
            by_year.setdefault(int(y), []).append(l)
    s = earthdata.session()
    done = stamp.setdefault("years", {})
    this_year = datetime.date.today().year
    tmp = pathlib.Path(tempfile.gettempdir())
    for y in sorted(by_year):
        out = T / f"{ROW}_{y}.pmtiles"
        months = sorted(by_year[y], key=lambda l: l["start"])
        complete = len(months) >= 12
        if out.exists() and str(y) in done and done[str(y)].get("months") == len(months) and (complete or y < this_year):
            continue
        if time.time() - START > BUDGET:
            stamp["waiting"] = f"time budget spent at {y}; next run"
            break
        total, meta = None, None
        for l in months:
            p = earthdata.download(s, l["href"], tmp / l["href"].rsplit("/", 1)[-1], ROW)
            a, meta = read_month(p)
            p.unlink(missing_ok=True)
            total = np.nan_to_num(a) if total is None else total + np.nan_to_num(a)
        H, W = total.shape
        res = 360.0 / W
        if abs(180.0 / H - res) > 1e-9:
            raise RuntimeError(f"grid {H} x {W} is not a whole-world latitude-longitude grid")
        lat = 90 - (np.arange(H) + 0.5) * res
        km = 111.32 * res
        cell_ha = (km * km * np.cos(np.radians(lat)) * 100)[:, None]
        if "hectare" in meta["units"].lower() or meta["units"].strip().lower() in ("ha",):
            share = total / cell_ha
        elif re.search(r"km", meta["units"], re.I):
            share = total * 100 / cell_ha
        else:
            raise RuntimeError(f"units {meta['units']!r} not understood; see the build file")
        codes = np.zeros((H, W), np.uint8)
        for i, (lo, hi, _) in enumerate(STEPS):
            codes[(total > 0) & (share >= lo) & (share < hi)] = i + 1
        pal = {i + 1: pyramid.rgba(c, 230) for i, c in enumerate(RAMP6)}
        pyramid.build(codes, -180.0, 90.0, res, pal, out, 6, how="max", attribution=CITE, name=out.stem,
                      meta={"year": y, "months": len(months)})
        done[str(y)] = {"months": len(months), "hectares_burned": round(float(total.sum())), "read": meta}
        STAMP.write_text(json.dumps(stamp, indent=1, default=str))
        print(f"burned_area: {y}: {len(months)} months, {total.sum():,.0f} ha", flush=True)
    key = [[c, t] for c, (_, _, t) in zip(RAMP6, STEPS)]
    choices = []
    for y in sorted((int(k) for k in done), reverse=True):
        if (T / f"{ROW}_{y}.pmtiles").exists():
            m = done[str(y)]["months"]
            choices.append({"label": str(y) if m >= 12 else f"{y}, first {m} months", "archive": f"tiles/{ROW}_{y}.pmtiles", "key": key})
    if choices:
        pyramid.write_choices(ROW, choices)
    stamp["built"] = bool(choices)
    STAMP.write_text(json.dumps(stamp, indent=1, default=str))


if __name__ == "__main__":
    main()
