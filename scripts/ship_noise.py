#!/usr/bin/env python3
"""
Underwater noise from ships, worldwide, each year 2014 to 2020 (round 183o).

Jalkanen, Johansson, Andersson, Majamaki and Sigray, "Underwater noise from
ships during 2014-2020" (Zenodo record 4730482 and its later versions,
CC BY 4.0; paper: Environmental Pollution 311, 119766, 2022,
doi:10.1016/j.envpol.2022.119766). The Finnish Meteorological Institute's
STEAM model gives the noise energy ships put into the sea each day, in
joules, in three frequency bands, on a world grid, as netCDF3 files zipped
one band and one year at a time.

Each zip is read on its own, its days added up into one year, and drawn in
eight steps on a log scale. The steps of a band are set once, from the first
year built (the 10th to 99th percentiles of the cells with any noise), and
written to tiles/ocean_noise.build.json, so every year of that band is
coloured alike and can be compared. Any cell with noise gets a colour; none
is left out.

Nothing is assumed about the files: the data variable, its units, the grid
and its spacing, and any frequency named in the file are read from it and
written to the build file. If the grid is not an even latitude-longitude
grid the build stops and says why.

A year once built is kept. The record's newest version is used (Zenodo API,
versions/latest); its licence is checked to be CC BY before anything is read.
"""
import json, math, os, pathlib, re, shutil, sys, tempfile, time, urllib.request, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

ROW = "ocean_noise"
T = pathlib.Path("tiles")
STAMP = T / f"{ROW}.build.json"
LATEST = "https://zenodo.org/api/records/4730482/versions/latest"
UA = {"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy)"}
CITE = ("Jalkanen et al. 2022, Underwater noise from ships during 2014-2020, "
        "Finnish Meteorological Institute, Zenodo doi:10.5281/zenodo.4730482 (CC BY 4.0)")
# The record's description lists the bands as 63, 125 and 2000 Hz, in that
# order, and its files are named 1stBand, 2ndBand, 3rdBand. A frequency
# written in the file itself is used instead when there is one.
LISTED = {"1st": "63 Hz", "2nd": "125 Hz", "3rd": "2000 Hz"}
HEARD = {"63 Hz": "the low hum of large ships' propellers",
         "125 Hz": "low ship noise",
         "2000 Hz": "higher-pitched noise, mostly from smaller and faster vessels"}
RAMP8 = ["#D6EEF6", "#A9DEEC", "#74C3DA", "#3FA9C2", "#2A86B4", "#1E6FA8", "#13447A", "#0C2E5E"]
PCTS = [10, 25, 40, 55, 70, 85, 95]
START, BUDGET = time.time(), 140 * 60


def api(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def words(j):
    """Joules in everyday words."""
    for v, w in ((1e15, "thousand trillion"), (1e12, "trillion"), (1e9, "billion"), (1e6, "million"), (1e3, "thousand")):
        if j >= v:
            n = j / v
            return f"{n:.3g} {w} joules"
    return f"{j:.3g} joules"


def find_var(nc):
    """The noise variable: the largest variable with a latitude and a longitude dimension."""
    best = None
    for name, v in nc.variables.items():
        dims = [d.lower() for d in v.dimensions]
        if len(dims) >= 2 and any(d.startswith("lat") or d == "y" for d in dims) and any(d.startswith("lon") or d == "x" for d in dims):
            size = 1
            for s in v.shape:
                size *= s
            if best is None or size > best[1]:
                best = (name, size)
    if not best:
        raise RuntimeError(f"no variable on a latitude-longitude grid among {list(nc.variables)}")
    return best[0]


def coord(nc, var, kind):
    v = nc.variables[var]
    for d in v.dimensions:
        dl = d.lower()
        if (kind == "lat" and (dl.startswith("lat") or dl == "y")) or (kind == "lon" and (dl.startswith("lon") or dl == "x")):
            if d in nc.variables:
                return d, nc.variables[d][:].astype("float64").copy()
            raise RuntimeError(f"dimension {d} has no coordinate variable")
    raise RuntimeError(f"no {kind} dimension on {var}")


def attrs_of(obj):
    out = {}
    for k in getattr(obj, "_attributes", {}) or {}:
        v = obj._attributes[k]
        out[k] = v.decode("utf-8", "replace") if isinstance(v, bytes) else (v.tolist() if hasattr(v, "tolist") else v)
    return out


def sum_member(path, total, meta):
    """Adds every day in one netCDF3 file to total (a dict holding the grid)."""
    import numpy as np
    from scipy.io import netcdf_file
    nc = netcdf_file(str(path), "r", mmap=True)
    try:
        name = find_var(nc)
        v = nc.variables[name]
        latd, lat = coord(nc, name, "lat")
        lond, lon = coord(nc, name, "lon")
        va = attrs_of(v)
        fill = va.get("_FillValue", va.get("missing_value"))
        scale = va.get("scale_factor")
        offset = va.get("add_offset")
        dims = list(v.dimensions)
        ilat, ilon = dims.index(latd), dims.index(lond)
        if meta.get("variable") is None:
            meta.update(variable=name, units=str(va.get("units", "")), dims=dims, shape=list(v.shape),
                        variable_attributes=va, file_attributes=attrs_of(nc))
        # Sum over every other axis (time, and height if any), one slice of the
        # first other axis at a time so the whole file is never in memory.
        other = [i for i in range(len(dims)) if i not in (ilat, ilon)]
        def clean(a):
            a = np.array(a, dtype="float64")
            if fill is not None:
                a[a == float(np.asarray(fill).ravel()[0])] = 0
            a[~np.isfinite(a)] = 0
            if scale not in (None, 1):
                a = a * float(np.asarray(scale).ravel()[0])
            if offset not in (None, 0):
                a = a + float(np.asarray(offset).ravel()[0])
            a[a < 0] = 0
            return a
        if not other:
            grid = clean(v[:])
            days = 1
        else:
            first = other[0]
            grid, days = None, v.shape[first]
            for i in range(v.shape[first]):
                idx = [slice(None)] * len(dims)
                idx[first] = i
                a = clean(v[tuple(idx)])
                rest = [d for d in dims if d not in (dims[first],)]
                # collapse any further axes that are not lat / lon
                while a.ndim > 2:
                    k = next(j for j, d in enumerate(rest) if d not in (latd, lond))
                    a = a.sum(axis=k)
                    rest.pop(k)
                if rest.index(latd) > rest.index(lond):
                    a = a.T
                grid = a if grid is None else grid + a
        if ilat > ilon and not other:
            grid = grid.T
        if total.get("grid") is None:
            total.update(grid=grid, lat=lat, lon=lon)
        else:
            if grid.shape != total["grid"].shape:
                raise RuntimeError(f"{path.name}: grid {grid.shape} differs from {total['grid'].shape}")
            total["grid"] = total["grid"] + grid
        total["days"] = total.get("days", 0) + days
    finally:
        nc.close()


def to_world(total):
    """The year's grid as row 0 = north, west edge, and cell size; checks the grid is even."""
    import numpy as np
    g, lat, lon = total["grid"], total["lat"], total["lon"]
    if lat[0] < lat[-1]:
        g, lat = g[::-1], lat[::-1]
    if lon.max() > 180.0001:
        order = np.argsort(((lon + 180) % 360) - 180)
        lon, g = (((lon + 180) % 360) - 180)[order], g[:, order]
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    rlat, rlon = float(abs(np.median(dlat))), float(np.median(dlon))
    if np.max(np.abs(np.abs(dlat) - rlat)) > rlat * 1e-3 or np.max(np.abs(dlon - rlon)) > rlon * 1e-3:
        raise RuntimeError("the grid's spacing is not even; see the build file")
    if abs(rlat - rlon) > rlon * 1e-3:
        raise RuntimeError(f"cells are {rlat} by {rlon} degrees, not square; drawing them would need resampling, not done without checking")
    return g, float(lon[0] - rlon / 2), float(lat[0] + rlat / 2), rlon


def main():
    pyramid.need("scipy")
    import numpy as np
    T.mkdir(exist_ok=True)
    stamp = json.loads(STAMP.read_text()) if STAMP.exists() else {}
    rec = api(LATEST)
    lic = ((rec.get("metadata") or {}).get("license") or {}).get("id", "")
    stamp.update(record=rec.get("id"), doi=rec.get("doi"), version=(rec.get("metadata") or {}).get("version"), licence=lic)
    if not re.match(r"cc-by(-4\.0)?$", str(lic), re.I):
        stamp.update(built=False, why=f"the record's licence is {lic!r}, not CC BY; nothing read")
        STAMP.write_text(json.dumps(stamp, indent=1, default=str))
        print(f"::warning::ship_noise: licence {lic!r}; stopped")
        return
    files = []
    for f in rec.get("files") or []:
        key = f.get("key") or f.get("filename") or ""
        m = re.search(r"(1st|2nd|3rd)Band.*?(\d{4})-01-01", key)
        if m and key.lower().endswith(".zip"):
            files.append((m.group(1), int(m.group(2)), key, (f.get("links") or {}).get("self") or (f.get("links") or {}).get("download"), f.get("size")))
    stamp["files_listed"] = [k for _, _, k, _, _ in files]
    if not files:
        stamp.update(built=False, why="no NOISE_ENE_<band>Band_..._<year>.zip files in the record")
        STAMP.write_text(json.dumps(stamp, indent=1, default=str))
        sys.exit("ship_noise: no band files found in the record")
    done = stamp.setdefault("years", {})
    breaks = stamp.setdefault("breaks", {})
    tmp = pathlib.Path(tempfile.mkdtemp())
    for band, year, key, url, size in sorted(files, key=lambda t: (t[0], -t[1])):
        tag = f"{band}_{year}"
        out = T / f"{ROW}_{tag}.pmtiles"
        if out.exists() and tag in done and done[tag].get("file") == key:
            continue
        if time.time() - START > BUDGET:
            stamp["waiting"] = f"time budget spent before {key}; the next run goes on"
            break
        z = pyramid.download(url, tmp / key, ROW)
        total, meta = {}, {}
        with zipfile.ZipFile(z) as zf:
            members = [i for i in zf.infolist() if re.search(r"\.nc\d?$|\.cdf$", i.filename, re.I)]
            if not members:
                raise RuntimeError(f"{key}: no netCDF file inside ({[i.filename for i in zf.infolist()][:10]})")
            for i in sorted(members, key=lambda i: i.filename):
                free = shutil.disk_usage(tmp).free
                if i.file_size > free - (2 << 30):
                    stamp["waiting"] = f"{key}: {i.filename} unpacks to {i.file_size / 1e9:.1f} GB, more than the disk has free"
                    STAMP.write_text(json.dumps(stamp, indent=1, default=str))
                    sys.exit(f"ship_noise: {stamp['waiting']}")
                p = pathlib.Path(zf.extract(i, tmp / "x"))
                sum_member(p, total, meta)
                p.unlink(missing_ok=True)
        z.unlink(missing_ok=True)
        grid, west, north, res = to_world(total)
        found = None
        for k, v in list((meta.get("variable_attributes") or {}).items()) + list((meta.get("file_attributes") or {}).items()):
            mm = re.search(r"(\d+(?:\.\d+)?)\s*Hz", str(v), re.I)
            if mm and re.search(r"freq|band|octave|title|long_name|description", k, re.I):
                found = f"{float(mm.group(1)):g} Hz"
                break
        hz = found or LISTED[band]
        nz = grid[grid > 0]
        if band not in breaks:
            if not nz.size:
                raise RuntimeError(f"{key}: no cell has any noise")
            breaks[band] = {"from_year": year, "joules": [float(x) for x in np.percentile(nz, PCTS)]}
        b = breaks[band]["joules"]
        codes = np.zeros(grid.shape, np.uint8)
        codes[grid > 0] = (np.searchsorted(b, grid[grid > 0], side="right") + 1).astype(np.uint8)
        pal = {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(RAMP8)}
        top = max(3, min(7, math.ceil(math.log2(360.0 / (256 * res))) + 2))
        pyramid.build(codes, west, north, res, pal, out, top, how="max", attribution=CITE, name=out.stem,
                      meta={"year": year, "band": hz, "days": total.get("days")})
        done[tag] = {"file": key, "band": hz, "band_from": "the file" if found else "the record's description (bands listed in order)",
                     "days": total.get("days"), "cells_with_noise": int(nz.size), "joules_total": float(grid.sum()),
                     "cell_degrees": res, "top_zoom": top, "read": meta}
        STAMP.write_text(json.dumps(stamp, indent=1, default=str))
        print(f"ship_noise: {key}: {total.get('days')} days, {nz.size:,} cells with noise, {hz}", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    choices = []
    for tag in sorted(done, key=lambda t: (t.split("_")[0], -int(t.split("_")[1]))):
        band, year = tag.split("_")
        if not (T / f"{ROW}_{tag}.pmtiles").exists() or band not in breaks:
            continue
        b = breaks[band]["joules"]
        names = [f"under {words(b[0])}"] + [f"{words(b[i])} to {words(b[i + 1])}" for i in range(len(b) - 1)] + [f"{words(b[-1])} or more"]
        hz = done[tag]["band"]
        key_ = [[c, f"{w} a year in the cell" + (" (steps set from " + str(breaks[band]["from_year"]) + ")" if i == 0 else "")]
                for i, (c, w) in enumerate(zip(RAMP8, names))]
        days = done[tag].get("days")
        choices.append({"label": f"{year}, {hz}" + (f" ({HEARD[hz]})" if hz in HEARD else "") + (f", {days} days" if days and days < 365 else ""),
                        "archive": f"tiles/{ROW}_{tag}.pmtiles", "key": key_})
    if choices:
        pyramid.write_choices(ROW, choices)
    stamp["built"] = bool(choices)
    STAMP.write_text(json.dumps(stamp, indent=1, default=str))


if __name__ == "__main__":
    main()
