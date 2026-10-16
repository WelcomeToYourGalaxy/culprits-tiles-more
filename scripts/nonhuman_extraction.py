#!/usr/bin/env python3
"""
Mines inside and near protected areas, by distance, for the Invasion of
non-humans map.

Mines: the worldwide mines file the Culprits map's mines row uses (Maus et
al. 2022's satellite-traced mining areas merged with OpenStreetMap's mines and
quarries, WU Vienna, Zenodo record 7307210, ODbL), every outline.
Protected areas: the public release of the World Database on Protected Areas
and OECMs (UNEP-WCMC and IUCN, Protected Planet), downloaded from Protected
Planet; the file used is written to the build file.

For each mine, the nearest protected or conserved area and the distance from
the mine's outline to it, measured on the globe (WGS84) between the nearest
points of the two shapes: 0 if they touch or overlap. Areas the database
gives only as a point (no boundary) are measured to that point and say so.
Every mine is kept and put in one band: inside a protected area, within 1 km,
within 10 km, within 20 km (12.4 miles), or further than 20 km. Each band is
its own set of map files (counted squares wider out, every mine closer in).

The database's terms do not allow passing on its shapes; only the nearest
area's id, name, designation and IUCN category are kept with each mine.

  nonhuman/extraction.json, nonhuman/extraction/*.pmtiles, nonhuman/extraction.build.json

Rebuilt monthly (the database is updated monthly), and whenever a build
failed; EXTRACTION_REBUILD=1 builds at once.
"""
import datetime, json, os, pathlib, re, subprocess, sys, tempfile, time, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "extraction"
MINES = "https://zenodo.org/api/records/7307210"
CF = "https://d1gam3xoknrgr2.cloudfront.net/current/"
BANDS = ["inside a protected area", "within 1 km", "within 10 km", "within 20 km", "further than 20 km"]
EDGES = [0.0, 1.0, 10.0, 20.0]
MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def band_of(km):
    if km is None:
        return BANDS[-1]
    if km <= 0:
        return BANDS[0]
    for b, e in zip(BANDS[1:4], EDGES[1:]):
        if km <= e:
            return b
    return BANDS[-1]


def wdpa_url():
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
            url = CF + name
            try:
                req = urllib.request.Request(url, method="HEAD", headers=nh.UA)
                with urllib.request.urlopen(req, timeout=60) as r:
                    if r.status == 200:
                        return url, tried
            except Exception as e:
                tried.append(f"{name}: {e}")
    return None, tried


def pick(cols, *pats):
    for p in pats:
        for c in cols:
            if re.fullmatch(p, c, re.I):
                return c
    return None


def read_wdpa(zpath, work):
    """Every polygon and every point layer in the download, with id, name,
    designation and IUCN category."""
    import geopandas as gpd
    import pyogrio
    srcs = []
    z = zipfile.ZipFile(zpath)
    names = z.namelist()
    if any(".gdb/" in n for n in names):
        z.extractall(work / "wdpa")
        gdb = next((work / "wdpa").rglob("*.gdb"))
        for lname, gtype in pyogrio.list_layers(str(gdb)):
            srcs.append((str(gdb), lname, str(gtype)))
    else:
        z.extractall(work / "wdpa")
        for inner in (work / "wdpa").rglob("*.zip"):
            d = work / "wdpa" / inner.stem
            zipfile.ZipFile(inner).extractall(d)
        for shp in (work / "wdpa").rglob("*.shp"):
            info = pyogrio.read_info(str(shp))
            srcs.append((str(shp), None, str(info.get("geometry_type"))))
    polys, points, used = [], [], []
    for path, layer, gtype in srcs:
        info = pyogrio.read_info(path, layer=layer)
        cols = list(info["fields"])
        c_id = pick(cols, r"site_id", r"wdpaid", r"wdpa_id")
        c_name = pick(cols, r"name_eng", r"name", r"site_name")
        c_des = pick(cols, r"desig_eng", r"desig")
        c_cat = pick(cols, r"iucn_cat", r"iucn_category")
        if not c_id:
            continue
        want = [c for c in (c_id, c_name, c_des, c_cat) if c]
        df = gpd.read_file(path, layer=layer, columns=want, engine="pyogrio")
        df = df.rename(columns={c_id: "pa_id", **({c_name: "pa_name"} if c_name else {}), **({c_des: "pa_desig"} if c_des else {}), **({c_cat: "pa_iucn"} if c_cat else {})})
        df = df.to_crs(4326) if df.crs and df.crs.to_epsg() != 4326 else df
        kind = "point" if "point" in gtype.lower() else "poly"
        used.append({"file": pathlib.Path(path).name, "layer": layer, "geometry": gtype, "rows": len(df), "as": kind, "columns": want})
        (points if kind == "point" else polys).append(df)
    import pandas as pd
    P = pd.concat(polys, ignore_index=True) if polys else None
    Q = pd.concat(points, ignore_index=True) if points else None
    return P, Q, used


def main():
    if not nh.due(NAME, 30, "EXTRACTION_REBUILD", hand=False):
        return
    nh.pip("geopandas", "pyogrio", "shapely>=2", "pyproj", "pandas")
    import geopandas as gpd
    import numpy as np
    import shapely
    from pyproj import Geod
    mines_mod = nh.tools()
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
    import pointtiles
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp()) / "extraction"
    work.mkdir(parents=True, exist_ok=True)
    # The mines file.
    rec = nh.get_json(MINES)
    gpkg = next(f for f in rec.get("files", []) if f["key"].endswith(".gpkg"))
    gpath = nh.download(gpkg["links"]["self"], work / gpkg["key"], "mines")
    M = gpd.read_file(gpath, layer="mining_polygons", engine="pyogrio")
    M = M.to_crs(4326) if M.crs and M.crs.to_epsg() != 4326 else M
    print(f"extraction: {len(M):,} mines; columns {list(M.columns)}", flush=True)
    # The protected areas.
    url, tried = wdpa_url()
    if not url:
        nh.write_stamp(NAME, {"failed": True, "error": "no WDPA download found at Protected Planet", "tried": tried})
        raise SystemExit("extraction: no WDPA download found")
    zpath = nh.download(url, work / url.rsplit("/", 1)[-1], "WDPA")
    P, Q, used = read_wdpa(zpath, work)
    print(f"extraction: {0 if P is None else len(P):,} protected-area shapes, {0 if Q is None else len(Q):,} given as points", flush=True)
    geod = Geod(ellps="WGS84")
    mg = shapely.make_valid(np.asarray(M.geometry.values))
    best_km = np.full(len(M), np.inf)
    best_ix = np.full(len(M), -1)
    best_src = np.array([""] * len(M), dtype=object)
    SEARCH = 0.6   # degrees: wider than 20 km anywhere a mine is (up to about 75 degrees north or south)
    for label, D in (("shape", P), ("point", Q)):
        if D is None or not len(D):
            continue
        dg = shapely.make_valid(np.asarray(D.geometry.values))
        tree = shapely.STRtree(dg)
        # Overlap first: those are inside, distance 0.
        if label == "shape":
            mi, pi = tree.query(mg, predicate="intersects")
            for a, b in zip(mi, pi):
                if best_km[a] > 0:
                    best_km[a], best_ix[a], best_src[a] = 0.0, b, label
        mi, pi = tree.query(mg, predicate="dwithin", distance=SEARCH)
        print(f"  {label}: {len(mi):,} mine and area pairs within {SEARCH} degrees", flush=True)
        keep = best_km[mi] > 0
        mi, pi = mi[keep], pi[keep]
        CH = 1_000_000
        for s0 in range(0, len(mi), CH):
            a, b = mi[s0:s0 + CH], pi[s0:s0 + CH]
            lines = shapely.shortest_line(mg[a], dg[b])
            xy = shapely.get_coordinates(lines).reshape(-1, 2, 2)
            km = np.asarray(geod.inv(xy[:, 0, 0], xy[:, 0, 1], xy[:, 1, 0], xy[:, 1, 1])[2]) / 1000
            # The nearest per mine within this chunk, then against what was found before.
            order = np.lexsort((km, a))
            a, b, km = a[order], b[order], km[order]
            first = np.r_[True, a[1:] != a[:-1]]
            for ai, bi, ki in zip(a[first], b[first], km[first]):
                if ki < best_km[ai]:
                    best_km[ai], best_ix[ai], best_src[ai] = ki, bi, label
            print(f"    {min(s0 + CH, len(mi)):,} pairs measured", flush=True)
    rows = []
    counts = {b: 0 for b in BANDS}
    for i in range(len(M)):
        km = None if not np.isfinite(best_km[i]) else float(best_km[i])
        band = band_of(km)
        counts[band] += 1
        r = M.iloc[i]
        g = mg[i].representative_point()
        props = {"band": band, "id": r.get("id"), "country": r.get("country") or r.get("isoa3"),
                 "area_km2": round(float(r["area"]), 4) if "area" in M.columns and r.get("area") == r.get("area") else None}
        if best_ix[i] >= 0 and km is not None and km <= 20:
            D = P if best_src[i] == "shape" else Q
            pa = D.iloc[int(best_ix[i])]
            props.update({"dist_km": round(km, 3), "pa_id": str(pa.get("pa_id")).removesuffix(".0"), "pa_name": pa.get("pa_name"),
                          "pa_desig": pa.get("pa_desig"), "pa_iucn": pa.get("pa_iucn"),
                          "pa_shape": "boundary" if best_src[i] == "shape" else "a point only (no boundary in the database)"})
        rows.append((round(g.x, 5), round(g.y, 5), {k: v for k, v in props.items() if v is not None and v == v}))
    sets = {}
    for b in BANDS:
        pts = [r for r in rows if r[2]["band"] == b]
        if not pts:
            continue
        out = nh.OUT / "extraction" / f"mines_{nh.slug(b)}.pmtiles"
        parts = pointtiles.build(pts, out, "mines", "band", attribution="Maus et al. 2022; OpenStreetMap contributors (ODbL); WDPA (UNEP-WCMC and IUCN)")
        sets[b] = [dict(p, file="extraction/" + p["file"]) for p in parts]
    nh.write_json("extraction.json", {"source": "Mines: Maus et al. 2022 and OpenStreetMap (Zenodo 7307210, ODbL); protected areas: " + url.rsplit("/", 1)[-1],
                                      "wdpa": url.rsplit("/", 1)[-1], "layer": "mines", "detail": 8, "bands": BANDS, "counts": counts, "total": len(rows), "sets": sets,
                                      "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")}, compact=False)
    nh.write_stamp(NAME, {"mines": len(rows), "counts": counts, "wdpa": url, "wdpa layers read": used, "mine columns": list(M.columns)})


if __name__ == "__main__":
    main()
