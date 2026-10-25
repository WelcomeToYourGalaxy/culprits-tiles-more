#!/usr/bin/env python3
"""
Bottom trawling and dredging inside marine protected areas, for the Culprits
map's row under Biodiversity loss (round nh2, asked 16 October).

Sources: Global Fishing Watch, apparent fishing effort by gear type (the same
service and token as scripts/gfw_trawling.py), the latest full year, at 0.1
degree; and the public release of the World Database on Protected Areas
(UNEP-WCMC and IUCN), every area it marks as marine or partly marine.

For each of those areas: the hours of fishing by trawlers and by dredges
inside its boundary, each 0.1 degree square counted by the share of it the
boundary covers (exactextract), which assumes the hours in a square are spread
evenly across it; and the hours per square kilometre. Global Fishing Watch's
"trawlers" includes mid-water trawlers; dredges all work the seabed. Every
marine area is kept, those with no trawling too. Each is drawn as a dot at a
point inside it (its shape is not passed on, as the database's terms ask),
with its id, name, designation, IUCN category, no-take status and year.

  nonhuman/trawl_mpas.geojson, nonhuman/trawl_mpas.build.json

Monthly; TRAWLMPAS_REBUILD=1 builds at once.
"""
import json, math, os, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import nhcommon as nh  # noqa: E402
import nhwdpa  # noqa: E402

NAME = "trawl_mpas"
RES = 0.1
GEARS = ["trawlers", "dredge_fishing"]


def main():
    if not nh.due(NAME, 30, "TRAWLMPAS_REBUILD", hand=False):
        return
    token = os.environ.get("GFW_TOKEN")
    if not token:
        nh.write_stamp(NAME, {"failed": True, "error": "no GFW_TOKEN"})
        raise SystemExit("trawl mpas: no GFW_TOKEN in the environment")
    nh.pip("geopandas", "pyogrio", "shapely>=2", "pyproj", "pandas", "rasterio", "exactextract", "numpy")
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    from exactextract import exact_extract
    import gfw_trawling
    import datetime
    year = datetime.date.today().year - 1
    W, H = int(360 / RES), int(180 / RES)
    grids = {g: np.zeros((H, W), np.float32) for g in GEARS}
    missed = []
    for s in range(-90, 90, 20):
        for w in range(-180, 180, 20):
            try:
                d = gfw_trawling.ask(year, (w, s, w + 20, s + 20), token)
            except Exception as e:
                missed.append({"box": [w, s], "error": str(e)[:200]})
                continue
            for entry in d.get("entries", []):
                for rows in entry.values():
                    for r in rows or []:
                        g = str(r.get("geartype") or "").lower()
                        lat, lon, h = r.get("lat"), r.get("lon"), r.get("hours") or 0
                        if g not in grids or lat is None or lon is None or not h:
                            continue
                        x, y = int((lon + 180) / RES), int((90 - lat) / RES)
                        if 0 <= x < W and 0 <= y < H:
                            grids[g][y, x] += h
    if not any(a.sum() for a in grids.values()):
        nh.write_stamp(NAME, {"failed": True, "year": year, "boxes not answered": missed})
        raise SystemExit("trawl mpas: nothing came back from Global Fishing Watch")
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp()) / "trawl"
    work.mkdir(parents=True, exist_ok=True)
    tifs = {}
    for g, a in grids.items():
        p = work / f"{g}.tif"
        with rasterio.open(p, "w", driver="GTiff", height=H, width=W, count=1, dtype="float32", crs="EPSG:4326", transform=from_origin(-180, 90, RES, RES)) as d:
            d.write(a, 1)
        tifs[g] = str(p)
    MARINE = ["1", "2", "1.0", "2.0", "marine", "coastal"]
    # Only marine and partly marine areas are kept as they are read (round nh4).
    keep = lambda df: df["pa_marine"].astype(str).str.strip().str.lower().isin(MARINE) if "pa_marine" in df.columns else [True] * len(df)
    P, Q, wdpa, used = nhwdpa.get(work, want=("pa_id", "pa_name", "pa_desig", "pa_iucn", "pa_marine", "pa_no_take", "pa_status_yr", "pa_iso3", "pa_rep_m_area"), keep=keep)
    m = P["pa_marine"].astype(str).str.strip().str.lower() if P is not None and "pa_marine" in P.columns else None
    if m is None:
        nh.write_stamp(NAME, {"failed": True, "error": "no MARINE or REALM column in the WDPA download", "wdpa layers read": used})
        raise SystemExit("trawl mpas: no marine column")
    M = P[m.isin(MARINE)].copy()
    print(f"trawl mpas: {len(M):,} marine and partly marine areas", flush=True)
    sums = {g: exact_extract(tifs[g], M, ["sum"], output="pandas")["sum"].to_numpy() for g in GEARS}
    eq = M.to_crs("+proj=cea")   # equal-area, for each area's size
    km2 = eq.geometry.area.to_numpy() / 1e6
    feats = []
    for i, (_, r) in enumerate(M.iterrows()):
        pt = r.geometry.representative_point()
        props = {k: r.get(k) for k in ("pa_id", "pa_name", "pa_desig", "pa_iucn", "pa_marine", "pa_no_take", "pa_status_yr", "pa_iso3", "pa_rep_m_area") if k in M.columns}
        props = {k: (str(v).removesuffix(".0") if k == "pa_id" else v) for k, v in props.items() if v is not None and v == v}
        tr, dr = float(sums["trawlers"][i] or 0), float(sums["dredge_fishing"][i] or 0)
        props.update({"year": year, "trawler_hours": round(tr, 1), "dredge_hours": round(dr, 1), "area_km2": round(float(km2[i]), 2),
                      "trawler_hours_per_km2": round(tr / km2[i], 4) if km2[i] > 0 else None, "dredge_hours_per_km2": round(dr / km2[i], 4) if km2[i] > 0 else None})
        props = {k: (v.item() if hasattr(v, "item") else v) for k, v in props.items() if v is not None}
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(pt.x, 4), round(pt.y, 4)]}, "properties": props})
    nh.OUT.mkdir(parents=True, exist_ok=True)
    (nh.OUT / "trawl_mpas.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, default=str))
    nh.write_stamp(NAME, {"year": year, "marine areas": len(feats), "with trawling": sum(1 for f in feats if f["properties"]["trawler_hours"] > 0),
                          "with dredging": sum(1 for f in feats if f["properties"]["dredge_hours"] > 0), "boxes not answered": missed, "wdpa": wdpa})


if __name__ == "__main__":
    main()
