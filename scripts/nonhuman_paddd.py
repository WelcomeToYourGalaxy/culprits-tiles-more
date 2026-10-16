#!/usr/bin/env python3
"""
Protected areas downgraded, downsized or degazetted, for the Invasion of
non-humans map.

Source: Conservation International and World Wildlife Fund 2021,
PADDDtracker.org Data Release Version 2.1, doi:10.5281/zenodo.4974336. The
Zenodo record says CC BY 4.0; the release's own ReadMe says CC BY-NC-ND 4.0.
Shown as published, unaltered: every field of every event is kept.

The release's points shapefile (events) and polygons shapefile (the land
affected) are read whole. The fields that hold each event's type, year, name
and status are found by what they contain and written to the build file.
Every point is a dot and every polygon is drawn as its outline, each as the
release gives it (no dot is made for an event given only as an outline).

  nonhuman/paddd.json             which fields mean what, types, years
  nonhuman/paddd_events.geojson   a dot per event
  nonhuman/paddd_areas.pmtiles    the land affected
  nonhuman/paddd.build.json

A fixed release: built once; PADDD_REBUILD=1 builds again.
"""
import json, math, pathlib, re, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "paddd"
REC = "https://zenodo.org/records/4974336/files/"
STEM = "PADDDtracker_DataReleaseV2_1_2021"
EXTS = (".shp", ".shx", ".dbf", ".prj", ".cpg")
TYPES = re.compile(r"downgrad|downsiz|degazet", re.I)


def fetch_set(work, suffix):
    for e in EXTS:
        try:
            nh.download(f"{REC}{STEM}_{suffix}{e}?download=1", work / f"{STEM}_{suffix}{e}", f"{suffix}{e}")
        except Exception as err:
            if e in (".shp", ".shx", ".dbf"):
                raise
            print(f"  {suffix}{e}: {err} (not needed)")
    return work / f"{STEM}_{suffix}.shp"


def clean(v):
    if v is None:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return int(v) if v.is_integer() else v
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    s = str(v).strip()
    return s or None


def detect(df):
    cols = [c for c in df.columns if c != "geometry"]
    typ = None
    for c in cols:
        vals = df[c].dropna().astype(str)
        if len(vals) and vals.str.contains(TYPES).mean() > 0.6:
            if typ is None or re.search(r"type|event", c, re.I):
                typ = c
    year = None
    for c in cols:
        if not re.search(r"year|yr", c, re.I):
            continue
        v = df[c].dropna()
        try:
            n = v.astype(float)
        except (TypeError, ValueError):
            continue
        if len(n) and ((n >= 1800) & (n <= 2030)).mean() > 0.6:
            if year is None or re.search(r"padd|enact|event", c, re.I):
                year = c
    name = next((c for c in cols if re.search(r"pa_?name|^name$|site_?name", c, re.I)), None) or next((c for c in cols if re.search(r"name", c, re.I)), None)
    status = next((c for c in cols if re.search(r"enact|status", c, re.I)), None)
    ident = next((c for c in cols if re.search(r"^paddd_?id$|^padddid$|^paddd_id", c, re.I)), None) or next((c for c in cols if re.search(r"paddd.*id", c, re.I) and not re.search(r"old", c, re.I)), None)
    return {"type": typ, "year": year, "name": name, "status": status, "id": ident}


def main():
    if not nh.due(NAME, None, "PADDD_REBUILD", hand=False):
        return
    nh.pip("geopandas", "pyogrio", "shapely")
    import geopandas as gpd
    mines = nh.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    pts = gpd.read_file(fetch_set(work, "Pts")).to_crs(4326)
    polys = gpd.read_file(fetch_set(work, "Poly")).to_crs(4326)
    fp, fa = detect(pts), detect(polys)
    print(f"paddd: {len(pts)} points, {len(polys)} polygons; fields {fp} / {fa}", flush=True)
    feats = []
    for _, r in pts.iterrows():
        g = r.geometry
        if g is None or g.is_empty:
            continue
        g = g.representative_point() if g.geom_type != "Point" else g
        props = {k: clean(r[k]) for k in pts.columns if k != "geometry"}
        props["_from"] = "point"
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(g.x, 5), round(g.y, 5)]}, "properties": {k: v for k, v in props.items() if v is not None}})
    nh.OUT.mkdir(parents=True, exist_ok=True)
    (nh.OUT / "paddd_events.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    # The land affected, every polygon with every field.
    nd = work / "areas.geojsonl"
    with nd.open("w") as w:
        for _, r in polys.iterrows():
            if r.geometry is None or r.geometry.is_empty:
                continue
            props = {k: clean(r[k]) for k in polys.columns if k != "geometry"}
            w.write(json.dumps({"type": "Feature", "geometry": r.geometry.__geo_interface__, "properties": {k: v for k, v in props.items() if v is not None}}, ensure_ascii=False) + "\n")
    out = nh.OUT / "paddd_areas.pmtiles"
    top = 11
    while True:
        mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", "paddd_areas", "-Z0", f"-z{top}", "--no-feature-limit", "--no-tile-size-limit",
                 "--attribution", "PADDDtracker v2.1 (CI and WWF 2021)", str(nd))
        if out.stat().st_size <= 95 * 1024 * 1024 or top <= 6:
            break
        top -= 1
    tf = fp["type"] or fa["type"]
    yf = fp["year"] or fa["year"]
    # Types and years from the outlines too, so the filters reach every one.
    every = [f["properties"] for f in feats] + [{k: clean(r[k]) for k in (tf, yf) if k and k in polys.columns} for _, r in polys.iterrows()]
    types = sorted({str(p[tf]) for p in every if tf and p.get(tf) is not None})
    years = [int(float(f["properties"][yf])) for f in feats if yf and f["properties"].get(yf) is not None and re.match(r"^\d{4}(\.0+)?$", str(f["properties"][yf]))]
    years_all = years + [int(float(p[yf])) for p in every[len(feats):] if yf and p.get(yf) is not None and re.match(r"^\d{4}(\.0+)?$", str(p[yf]))]
    meta = {"typeField": tf, "yearField": yf, "nameField": fp["name"] or fa["name"], "statusField": fp["status"] or fa["status"],
            "types": types, "yearMin": min(years_all) if years_all else None, "yearMax": max(years_all) if years_all else None,
            "noYear": len(feats) - len(years), "events": len(feats), "outlines": len(polys), "areas": "paddd_areas.pmtiles", "areasLayer": "paddd_areas",
            "fields": [c for c in pts.columns if c != "geometry"],
            "licence": "Zenodo record: CC BY 4.0; the release's ReadMe: CC BY-NC-ND 4.0"}
    nh.write_json("paddd.json", meta, compact=False)
    nh.write_stamp(NAME, {"points": len(pts), "polygons": len(polys), "fields (points)": fp, "fields (polygons)": fa,
                          "polygon columns": [c for c in polys.columns if c != "geometry"], "areas to zoom": top, "areas bytes": out.stat().st_size})


if __name__ == "__main__":
    main()
