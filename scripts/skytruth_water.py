#!/usr/bin/env python3
"""
SkyTruth's own write-ups (Taylor Energy, derailments, refuge spills: the
feed the map calls skytruth_posts), split into those at sea and those on land
(round 81, asked 27 September), for the two parts of the map's oil slicks
layer.

Reads every write-up from the daily copy (skytruth/feed_2/<hh>.json, kept by
skytruth.py) and tests its point against Natural Earth's 1:10 million land
(public domain; ne_10m_land plus ne_10m_minor_islands):

  skytruth/posts_sea.geojson    write-ups whose point is off the land
  skytruth/posts_land.geojson   write-ups whose point is on land (lakes and
                                rivers count as land at this scale)

Every field of every write-up is kept, its own box (_html) included; each
also says which side of the coastline it fell on and how that was decided.
Rebuilt whenever the copy has changed.
"""
import hashlib, json, pathlib, subprocess, sys, urllib.request

COPY = pathlib.Path("skytruth/feed_2")
OUT = pathlib.Path("skytruth")
STAMP = OUT / "posts_water.json"
LAND = ["https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson",
        "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_minor_islands.geojson"]
HOW = "Placed by testing the write-up's point against Natural Earth's 1:10 million coastline"


def fingerprint():
    h = hashlib.sha1()
    for p in sorted(COPY.glob("*.json")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def main():
    if not COPY.is_dir():
        print("skytruth_water: no copy of the write-ups yet (skytruth.py makes it)")
        return
    fp = fingerprint()
    try:
        if json.loads(STAMP.read_text()).get("from") == fp:
            print("skytruth_water: the write-ups have not changed; kept")
            return
    except Exception:  # noqa: BLE001
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "shapely"], check=True)
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree
    polys = []
    for u in LAND:
        raw = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Culprits atlas build"}), timeout=300).read()
        for f in json.loads(raw)["features"]:
            g = shape(f["geometry"])
            polys.extend(list(g.geoms) if g.geom_type == "MultiPolygon" else [g])
    tree = STRtree(polys)
    sea, land, seen = [], [], set()
    for piece in sorted(COPY.glob("*.json")):
        for key, f in json.loads(piece.read_text()).items():
            if key in seen or not f.get("geometry") or f["geometry"].get("type") != "Point":
                continue
            seen.add(key)
            lon, lat = f["geometry"]["coordinates"][:2]
            pt = Point(lon, lat)
            on_land = any(polys[i].covers(pt) for i in tree.query(pt))
            p = dict(f.get("properties") or {})
            p["where"] = "on land" if on_land else "at sea"
            p["placed_by"] = HOW
            p["group"] = "On land" if on_land else "At sea"
            (land if on_land else sea).append({"type": "Feature", "geometry": f["geometry"], "properties": p})
    OUT.mkdir(exist_ok=True)
    for name, feats in (("posts_sea", sea), ("posts_land", land)):
        (OUT / f"{name}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats,
                                                         "source": "SkyTruth Monitor, placed with Natural Earth"},
                                                        ensure_ascii=False, separators=(",", ":")))
    STAMP.write_text(json.dumps({"from": fp, "at_sea": len(sea), "on_land": len(land)}, indent=1))
    print(f"skytruth_water: {len(sea)} write-ups at sea, {len(land)} on land")


if __name__ == "__main__":
    main()
