"""
The World Database on Protected Areas (public release, UNEP-WCMC and IUCN,
Protected Planet) for the nonhuman_*.py scripts: finding this month's
download, reading its shapes and points, and measuring how far things are
from the nearest protected or conserved area.

The database's terms do not allow passing on its shapes: the scripts keep only
an area's id, name, designation, IUCN category and figures worked out from it.

Kept in scripts/lib/ so the refresh workflow does not run it as a job.
"""
import datetime, gc, pathlib, re, zipfile

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


def near_mask(D, near, reach=SEARCH):
    """Which rows of D have a bounding box within reach (degrees) of a
    bounding box of one of near: a cheap test that keeps everything that could
    be the nearest area to one of them."""
    import numpy as np
    import shapely
    if near is None:
        return np.ones(len(D), bool)
    tree = shapely.STRtree(shapely.envelope(near))
    hit = tree.query(shapely.envelope(np.asarray(D.geometry.values)), predicate="dwithin", distance=reach)[0]
    m = np.zeros(len(D), bool)
    m[hit] = True
    return m


def _sources(zpath, work):
    """Each layer in the download, as (GDAL path, layer, geometry type, done),
    read straight from the zip; inner zips are copied out one at a time and
    done() deletes each once read, so the disk never holds the release twice
    over (round nh4: unpacking it whole filled the runner)."""
    import pyogrio
    z = zipfile.ZipFile(zpath)
    names = z.namelist()
    gdbs = sorted({n.split(".gdb/")[0] + ".gdb" for n in names if ".gdb/" in n})
    for g in gdbs:
        path = f"/vsizip/{zpath}/{g}"
        for lname, gtype in pyogrio.list_layers(path):
            yield path, str(lname), str(gtype), (lambda: None)
    for n in names:
        if n.lower().endswith(".shp"):
            path = f"/vsizip/{zpath}/{n}"
            yield path, None, str(pyogrio.read_info(path).get("geometry_type")), (lambda: None)
    for n in names:
        if not n.lower().endswith(".zip"):
            continue
        inner = pathlib.Path(work) / "wdpa_inner" / pathlib.Path(n).name
        inner.parent.mkdir(parents=True, exist_ok=True)
        with z.open(n) as src, open(inner, "wb") as dst:
            while True:
                b = src.read(1 << 24)
                if not b:
                    break
                dst.write(b)
        for m in zipfile.ZipFile(inner).namelist():
            if m.lower().endswith(".shp"):
                path = f"/vsizip/{inner}/{m}"
                yield path, None, str(pyogrio.read_info(path).get("geometry_type")), (lambda: None)
        inner.unlink(missing_ok=True)


def read(zpath, work, want=("pa_id", "pa_name", "pa_desig", "pa_iucn"), near=None, keep=None, each=None, batch=20_000):
    """(shapes, points, what was read): every polygon and point layer in the
    download, with the columns asked for, renamed as in COLS, read 20,000 at
    a time straight from the zip. Given near (shapely geometries, WGS84), only
    areas that could be within 20 km or so of one of them are kept; given
    keep(df) -> mask, only the rows it marks; given each(kind, df), every
    batch is handed to it and nothing is kept (shapes and points come back
    None). So the whole world's outlines are never held at once."""
    nh.pip("pyarrow")
    import geopandas as gpd
    import pandas as pd
    import pyogrio
    import shapely
    polys, points, used = [], [], []
    for path, layer, gtype, done in _sources(zpath, work):
        info = pyogrio.read_info(path, layer=layer)
        cols = list(info["fields"])
        found = {k: _pick(cols, COLS[k]) for k in want}
        if not found.get("pa_id"):
            continue
        kind = "point" if "point" in gtype.lower() else "poly"
        rows = kept = 0
        with pyogrio.raw.open_arrow(path, layer=layer, columns=[c for c in found.values() if c], batch_size=batch, use_pyarrow=True) as (meta, reader):
            gname = meta.get("geometry_name") or "wkb_geometry"
            crs = meta.get("crs")
            for rb in reader:
                t = rb.to_pandas()
                geom = shapely.from_wkb(t.pop(gname if gname in t.columns else t.columns[-1]).values)
                df = gpd.GeoDataFrame(t.rename(columns={c: k for k, c in found.items() if c}), geometry=geom, crs=crs)
                df = df.to_crs(4326) if df.crs and df.crs.to_epsg() != 4326 else df
                rows += len(df)
                if near is not None:
                    df = df[near_mask(df, near)]
                if keep is not None and len(df):
                    df = df[keep(df)]
                kept += len(df)
                if each is not None:
                    if len(df):
                        each(kind, df.reset_index(drop=True))
                elif len(df):
                    (points if kind == "point" else polys).append(df.reset_index(drop=True))
                del t, df, geom
                gc.collect()
        done()
        used.append({"file": path.rsplit("/", 1)[-1], "layer": layer, "geometry": gtype, "rows": rows, "kept": kept, "as": kind,
                     "columns": {k: c for k, c in found.items() if c}})
    P = pd.concat(polys, ignore_index=True) if polys else None
    Q = pd.concat(points, ignore_index=True) if points else None
    del polys, points
    gc.collect()
    return P, Q, used


def get(work, want=("pa_id", "pa_name", "pa_desig", "pa_iucn"), near=None, keep=None, each=None):
    """Downloads and reads this month's release. Returns (shapes, points, file name, report)."""
    u, tried = url()
    if not u:
        raise RuntimeError("no WDPA download found at Protected Planet; tried " + "; ".join(tried[:10]))
    z = nh.download(u, pathlib.Path(work) / u.rsplit("/", 1)[-1], "WDPA")
    P, Q, used = read(z, work, want, near=near, keep=keep, each=each)
    pathlib.Path(z).unlink(missing_ok=True)
    return P, Q, u.rsplit("/", 1)[-1], used


_TREES = {}
PIECE = 64          # vertices per piece of boundary
SIMPLIFY = 0.0003   # degrees (about 30 m): boundaries are simplified this much for measuring only


def _pieces(dg):
    """Every boundary of every area cut into short pieces of at most PIECE
    vertices, after simplifying by SIMPLIFY degrees (about 30 m; whether a
    thing is inside an area is still tested on the full boundary). Returns
    (pieces, the row in dg each came from)."""
    import numpy as np
    import shapely
    parts, pidx = shapely.get_parts(dg, return_index=True)
    t = shapely.get_type_id(parts)
    poly = np.isin(t, [3])
    rings, ridx = shapely.get_rings(parts[poly], return_index=True)
    lines = np.concatenate([rings, parts[np.isin(t, [1, 2])]])
    owner = np.concatenate([pidx[poly][ridx], pidx[np.isin(t, [1, 2])]])
    lines = shapely.simplify(lines, SIMPLIFY, preserve_topology=False)
    coords, cidx = shapely.get_coordinates(lines, return_index=True)
    n = np.bincount(cidx, minlength=len(lines))
    off = np.r_[0, np.cumsum(n)[:-1]]
    ok = n >= 2
    m = np.where(ok, np.maximum(1, -(-(n - 1) // (PIECE - 1))), 0)
    line_of_piece = np.repeat(np.arange(len(lines)), m)
    k = np.arange(m.sum()) - np.repeat(np.r_[0, np.cumsum(m)[:-1]], m)
    start = off[line_of_piece] + k * (PIECE - 1)
    length = np.minimum(PIECE, off[line_of_piece] + n[line_of_piece] - start)
    piece_id = np.repeat(np.arange(len(start)), length)
    at = np.repeat(start, length) + (np.arange(length.sum()) - np.repeat(np.r_[0, np.cumsum(length)[:-1]], length))
    pieces = shapely.linestrings(coords[at], indices=piece_id)
    pts = parts[np.isin(t, [0, 4])]
    if len(pts):
        pieces = np.concatenate([pieces, pts])
        line_of_piece = np.concatenate([line_of_piece, np.arange(len(lines), len(lines) + len(pts))])
        owner = np.concatenate([owner, pidx[np.isin(t, [0, 4])]])
    return pieces, owner[line_of_piece]


def nearest(geoms, P, Q, log=print):
    """For each of geoms (shapely, WGS84): the distance in km on the globe to
    the nearest protected area within 20 km or so (0 if it touches or
    overlaps one), which table it is in ("shape" or "point") and its row
    there.

    Round nh5: whether a thing touches an area is tested on the area's full
    boundary. Distances are measured to the area's boundary cut into short
    pieces (simplified by about 30 m): the piece nearest on the lon/lat grid
    is found, every piece within that distance widened for how much a degree
    of longitude shrinks at that latitude is measured on the globe (WGS84),
    and the shortest is kept. (Measuring whole outlines took about 400 pairs
    a second and the oil and gas run never finished.)"""
    import numpy as np
    import shapely
    from pyproj import Geod
    geod = Geod(ellps="WGS84")

    def valid(a):
        a = np.asarray(a)
        bad = ~shapely.is_valid(a)
        if bad.any():
            a = a.copy()
            a[bad] = shapely.make_valid(a[bad])
        return a

    g = valid(geoms)
    best_km = np.full(len(g), np.inf)
    best_ix = np.full(len(g), -1)
    best_src = np.array([""] * len(g), dtype=object)
    STEP = 20_000
    for label, D in (("shape", P), ("point", Q)):
        if D is None or not len(D):
            continue
        # Mended, cut into pieces and indexed once per table, however many
        # times this is called with it (the oil and gas script calls it
        # chunk by chunk).
        if _TREES.get(label, (None,))[0] is not D:
            _TREES[label] = (D,)
            dg = valid(D.geometry.values)
            if label == "shape":
                pieces, owner = _pieces(dg)
                log(f"  {label}: {len(dg):,} areas cut into {len(pieces):,} pieces of boundary")
            else:
                pieces, owner = dg, np.arange(len(dg))
            _TREES[label] = (D, dg, shapely.STRtree(dg) if label == "shape" else None, pieces, owner, shapely.STRtree(pieces))
        _, dg, whole, pieces, owner, tree = _TREES[label]
        pairs = 0
        for t0 in range(0, len(g), STEP):
            gs = g[t0:t0 + STEP]
            if label == "shape":
                mi, pi = whole.query(gs, predicate="intersects")
                best_km[mi + t0] = 0.0
                best_ix[mi + t0] = pi
                best_src[mi + t0] = label
            out = np.where(~(best_km[t0:t0 + len(gs)] == 0))[0]
            if not len(out):
                continue
            (qi, ti), dd = tree.query_nearest(gs[out], max_distance=SEARCH, return_distance=True)
            if not len(qi):
                continue
            first = np.r_[True, qi[1:] != qi[:-1]]
            qi, dd = qi[first], dd[first]
            # Widen for latitude: a degree of longitude is cos(latitude) as
            # long as one of latitude, so the nearest on the grid may not be
            # the nearest on the globe.
            lat = np.abs(shapely.get_y(shapely.centroid(gs[out][qi])))
            widen = np.minimum(1 / np.maximum(np.cos(np.radians(lat)), 0.15), 7.0)
            reach = np.minimum(dd * widen * 1.01 + 1e-9, SEARCH)
            ai, b = tree.query(gs[out][qi], predicate="dwithin", distance=reach)
            a = out[qi][ai] + t0
            pairs += len(a)
            CH = 500_000
            for s0 in range(0, len(a), CH):
                aa, bb = a[s0:s0 + CH], b[s0:s0 + CH]
                xy = shapely.get_coordinates(shapely.shortest_line(g[aa], pieces[bb])).reshape(-1, 2, 2)
                km = np.asarray(geod.inv(xy[:, 0, 0], xy[:, 0, 1], xy[:, 1, 0], xy[:, 1, 1])[2]) / 1000
                rows = owner[bb]
                order = np.lexsort((km, aa))
                aa, rows, km = aa[order], rows[order], km[order]
                keep = np.r_[True, aa[1:] != aa[:-1]]
                aa, rows, km = aa[keep], rows[keep], km[keep]
                better = km < best_km[aa]
                best_km[aa[better]] = km[better]
                best_ix[aa[better]] = rows[better]
                best_src[aa[better]] = label
            log(f"  {label}: {min(t0 + STEP, len(g)):,} of {len(g):,} measured, {pairs:,} pieces measured so far")
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
