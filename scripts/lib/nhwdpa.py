"""
The World Database on Protected Areas (public release, UNEP-WCMC and IUCN,
Protected Planet) for the nonhuman_*.py scripts: finding this month's
download, reading its shapes and points, and measuring how far things are
from the nearest protected or conserved area.

The database's terms do not allow passing on its shapes: the scripts keep only
an area's id, name, designation, IUCN category and figures worked out from it.

Kept in scripts/lib/ so the refresh workflow does not run it as a job.
"""
import datetime, pathlib, re, zipfile

import nhcommon as nh

CF = "https://d1gam3xoknrgr2.cloudfront.net/current/"
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
BANDS = ["inside a protected area", "within 1 km", "within 10 km", "within 20 km", "further than 20 km"]
EDGES = [0.0, 1.0, 10.0, 20.0]
SEARCH = 0.6   # degrees: wider than 20 km anywhere up to about 75 degrees north or south

# Column names, old schema and the August 2025 one, matched whole and in any case.
COLS = {
    "pa_id": (r"site_id", r"wdpaid", r"wdpa_id"),
    "pa_name": (r"name_eng", r"name", r"site_name"),
    "pa_desig": (r"desig_eng", r"desig"),
    "pa_iucn": (r"iucn_cat", r"iucn_category"),
    "pa_marine": (r"marine", r"realm"),
    "pa_no_take": (r"no_take",),
    "pa_status_yr": (r"status_yr",),
    "pa_rep_area": (r"rep_area",),
    "pa_rep_m_area": (r"rep_m_area",),
    "pa_iso3": (r"iso3",),
    "pa_def": (r"pa_def", r"site_type"),
}


def band_of(km):
    if km is None:
        return BANDS[-1]
    if km <= 0:
        return BANDS[0]
    for b, e in zip(BANDS[1:4], EDGES[1:]):
        if km <= e:
            return b
    return BANDS[-1]


def url():
    """This month's download (or one of the three before), and every name tried."""
    import urllib.request
    today = datetime.date.today()
    tried = []
    for back in range(0, 4):
        y, m = today.year, today.month - back
        while m < 1:
            m += 12
            y -= 1
        tag = f"{MON[m - 1]}{y}"
        for name in (f"WDPA_WDOECM_{tag}_Public_all_gdb.zip", f"WDPA_WDOECM_{tag}_Public_gdb.zip", f"WDPA_{tag}_Public_gdb.zip",
                     f"WDPA_WDOECM_{tag}_Public_all_shp.zip", f"WDPA_{tag}_Public_shp.zip"):
            u = CF + name
            try:
                req = urllib.request.Request(u, method="HEAD", headers=nh.UA)
                with urllib.request.urlopen(req, timeout=60) as r:
                    if r.status == 200:
                        return u, tried
            except Exception as e:
                tried.append(f"{name}: {e}")
    return None, tried


def _pick(cols, pats):
    for p in pats:
        for c in cols:
            if re.fullmatch(p, c, re.I):
                return c
    return None


def read(zpath, work, want=("pa_id", "pa_name", "pa_desig", "pa_iucn")):
    """(shapes, points, what was read): every polygon and point layer in the
    download, with the columns asked for, renamed as in COLS."""
    import geopandas as gpd
    import pandas as pd
    import pyogrio
    work = pathlib.Path(work)
    srcs = []
    z = zipfile.ZipFile(zpath)
    z.extractall(work / "wdpa")
    if any(".gdb/" in n for n in z.namelist()):
        gdb = next((work / "wdpa").rglob("*.gdb"))
        for lname, gtype in pyogrio.list_layers(str(gdb)):
            srcs.append((str(gdb), lname, str(gtype)))
    else:
        for inner in (work / "wdpa").rglob("*.zip"):
            zipfile.ZipFile(inner).extractall(work / "wdpa" / inner.stem)
        for shp in (work / "wdpa").rglob("*.shp"):
            info = pyogrio.read_info(str(shp))
            srcs.append((str(shp), None, str(info.get("geometry_type"))))
    polys, points, used = [], [], []
    for path, layer, gtype in srcs:
        cols = list(pyogrio.read_info(path, layer=layer)["fields"])
        found = {k: _pick(cols, COLS[k]) for k in want}
        if not found.get("pa_id"):
            continue
        df = gpd.read_file(path, layer=layer, columns=[c for c in found.values() if c], engine="pyogrio")
        df = df.rename(columns={c: k for k, c in found.items() if c})
        df = df.to_crs(4326) if df.crs and df.crs.to_epsg() != 4326 else df
        kind = "point" if "point" in gtype.lower() else "poly"
        used.append({"file": pathlib.Path(path).name, "layer": layer, "geometry": gtype, "rows": len(df), "as": kind,
                     "columns": {k: c for k, c in found.items() if c}})
        (points if kind == "point" else polys).append(df)
    P = pd.concat(polys, ignore_index=True) if polys else None
    Q = pd.concat(points, ignore_index=True) if points else None
    return P, Q, used


def get(work, want=("pa_id", "pa_name", "pa_desig", "pa_iucn")):
    """Downloads and reads this month's release. Returns (shapes, points, file name, report)."""
    u, tried = url()
    if not u:
        raise RuntimeError("no WDPA download found at Protected Planet; tried " + "; ".join(tried[:10]))
    z = nh.download(u, pathlib.Path(work) / u.rsplit("/", 1)[-1], "WDPA")
    P, Q, used = read(z, work, want)
    return P, Q, u.rsplit("/", 1)[-1], used


def nearest(geoms, P, Q, log=print):
    """For each of geoms (shapely, WGS84): the distance in km on the globe to
    the nearest protected area within 20 km or so (0 if they touch or
    overlap), which table it is in ("shape" or "point") and its row there.
    Distances are measured between the nearest points of the two shapes."""
    import numpy as np
    import shapely
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    g = shapely.make_valid(np.asarray(geoms))
    best_km = np.full(len(g), np.inf)
    best_ix = np.full(len(g), -1)
    best_src = np.array([""] * len(g), dtype=object)
    for label, D in (("shape", P), ("point", Q)):
        if D is None or not len(D):
            continue
        dg = shapely.make_valid(np.asarray(D.geometry.values))
        tree = shapely.STRtree(dg)
        if label == "shape":
            mi, pi = tree.query(g, predicate="intersects")
            best_km[mi] = 0.0
            best_ix[mi] = pi
            best_src[mi] = label
        mi, pi = tree.query(g, predicate="dwithin", distance=SEARCH)
        keep = best_km[mi] > 0
        mi, pi = mi[keep], pi[keep]
        log(f"  {label}: {len(mi):,} pairs within {SEARCH} degrees")
        CH = 1_000_000
        for s0 in range(0, len(mi), CH):
            a, b = mi[s0:s0 + CH], pi[s0:s0 + CH]
            xy = shapely.get_coordinates(shapely.shortest_line(g[a], dg[b])).reshape(-1, 2, 2)
            km = np.asarray(geod.inv(xy[:, 0, 0], xy[:, 0, 1], xy[:, 1, 0], xy[:, 1, 1])[2]) / 1000
            order = np.lexsort((km, a))
            a, b, km = a[order], b[order], km[order]
            first = np.r_[True, a[1:] != a[:-1]]
            a, b, km = a[first], b[first], km[first]
            better = km < best_km[a]
            best_km[a[better]] = km[better]
            best_ix[a[better]] = b[better]
            best_src[a[better]] = label
    return best_km, best_ix, best_src


def describe(km, ix, src, P, Q):
    """The fields kept with a thing for its nearest area (empty beyond 20 km)."""
    import math
    if ix < 0 or not math.isfinite(km) or km > 20:
        return {}
    D = P if src == "shape" else Q
    pa = D.iloc[int(ix)]
    out = {"dist_km": round(float(km), 3), "pa_id": str(pa.get("pa_id")).removesuffix(".0"), "pa_name": pa.get("pa_name"),
           "pa_desig": pa.get("pa_desig"), "pa_iucn": pa.get("pa_iucn"),
           "pa_shape": "boundary" if src == "shape" else "a point only (no boundary in the database)"}
    return {k: v for k, v in out.items() if v is not None and v == v}
