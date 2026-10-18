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
import json, os, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402
import nhwdpa  # noqa: E402

NAME = "extraction"
MINES = "https://zenodo.org/api/records/7307210"
BANDS = nhwdpa.BANDS


def main():
    if not nh.due(NAME, 30, "EXTRACTION_REBUILD", hand=False):
        return
    nh.pip("geopandas", "pyogrio", "shapely>=2", "pyproj", "pandas")
    import geopandas as gpd
    import numpy as np
    nh.tools()
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
    try:
        P, Q, wdpa, used = nhwdpa.get(work, near=M.geometry.values)
    except Exception as e:
        nh.write_stamp(NAME, {"failed": True, "error": str(e)[:1000]})
        raise SystemExit(f"extraction: {e}")
    print(f"extraction: {0 if P is None else len(P):,} protected-area shapes, {0 if Q is None else len(Q):,} given as points", flush=True)
    km, ix, src = nhwdpa.nearest(M.geometry.values, P, Q, log=lambda t: print(t, flush=True))
    rows = []
    counts = {b: 0 for b in BANDS}
    for i in range(len(M)):
        k = float(km[i]) if np.isfinite(km[i]) else None
        band = nhwdpa.band_of(k)
        counts[band] += 1
        r = M.iloc[i]
        g = M.geometry.values[i].representative_point()
        props = {"band": band, "id": r.get("id"), "country": r.get("country") or r.get("isoa3"),
                 "area_km2": round(float(r["area"]), 4) if "area" in M.columns and r.get("area") == r.get("area") else None}
        props.update(nhwdpa.describe(km[i], ix[i], src[i], P, Q))
        rows.append((round(g.x, 5), round(g.y, 5), {k2: v for k2, v in props.items() if v is not None and v == v}))
    sets = {}
    for b in BANDS:
        pts = [r for r in rows if r[2]["band"] == b]
        if not pts:
            continue
        out = nh.OUT / "extraction" / f"mines_{nh.slug(b)}.pmtiles"
        parts = pointtiles.build(pts, out, "mines", "band", attribution="Maus et al. 2022; OpenStreetMap contributors (ODbL); WDPA (UNEP-WCMC and IUCN)")
        sets[b] = [dict(p, file="extraction/" + p["file"]) for p in parts]
    nh.write_json("extraction.json", {"source": "Mines: Maus et al. 2022 and OpenStreetMap (Zenodo 7307210, ODbL); protected areas: " + wdpa,
                                      "wdpa": wdpa, "layer": "mines", "detail": 8, "bands": BANDS, "counts": counts, "total": len(rows), "sets": sets,
                                      "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")}, compact=False)
    nh.write_stamp(NAME, {"mines": len(rows), "counts": counts, "wdpa": wdpa, "wdpa layers read": used, "mine columns": list(M.columns)})


if __name__ == "__main__":
    main()
