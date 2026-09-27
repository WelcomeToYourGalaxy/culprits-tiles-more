#!/usr/bin/env python3
"""
Countries for the Invasion of the after-life rows (round 77, 27 September).

The Unearthings map (WelcomeToYourGalaxy/remains) opens a country when it is
clicked: what its harvest holds inside that country, counted by direction, the
first fourteen records by name, then its guides and its resources for that
jurisdiction. It draws the countries from world-atlas (countries-50m, Natural
Earth) and names them with its own table of numeric codes (NUM2A3). This builds
the same countries once a day, each carrying what the map would count inside it,
so the Culprits map can open them the same way.

Writes shapes/remains_units.geojson: one feature per country, with iso3, name,
n (records inside), harm / watch / redress / unlawful, and list (the first 14
records inside: name, kind, date, posture, as JSON) and more (how many past 14).
Records are placed by the map's own published coordinates; blurred records stay
blurred, and a blurred record near a border can fall on the neighbour's side,
as it does on the map.
"""
import gzip, json, pathlib, re, subprocess, sys, urllib.request

OUT = pathlib.Path("shapes/remains_units.geojson")
WORLD = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json"
RAW = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/remains/main/"
UA = {"User-Agent": "Culprits atlas refresh"}


def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read()


def topo_features(topo, name):
    """TopoJSON to GeoJSON features (arcs delta-decoded, quantised)."""
    tf = topo.get("transform")
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for p in arc:
            if tf:
                x += p[0]
                y += p[1]
                pts.append([x * tf["scale"][0] + tf["translate"][0], y * tf["scale"][1] + tf["translate"][1]])
            else:
                pts.append(list(p))
        arcs.append(pts)

    def ring(ids):
        out = []
        for i in ids:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            out.extend(a if not out else a[1:])
        return out

    feats = []
    for g in topo["objects"][name]["geometries"]:
        t = g.get("type")
        if t == "Polygon":
            coords = [ring(r) for r in g["arcs"]]
        elif t == "MultiPolygon":
            coords = [[ring(r) for r in poly] for poly in g["arcs"]]
        else:
            continue
        feats.append({"type": "Feature", "id": g.get("id"), "properties": dict(g.get("properties") or {}),
                      "geometry": {"type": t, "coordinates": coords}})
    return feats


def rounded(c):
    if isinstance(c[0], (int, float)):
        return [round(c[0], 3), round(c[1], 3)]
    return [rounded(x) for x in c]


def main():
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "shapely"], check=True)
    from shapely.geometry import Point, shape
    from shapely.strtree import STRtree

    page = get(RAW + "index.html").decode("utf-8", "replace")
    m = re.search(r"var NUM2A3=(\{[^;]*\});", page)
    num2a3 = json.loads(m.group(1)) if m else {}
    recs = json.loads(gzip.decompress(get(RAW + "remains.json.gz")))
    recs = recs.get("records", recs) if isinstance(recs, dict) else recs
    feats = topo_features(json.loads(get(WORLD)), "countries")
    geoms = [shape(f["geometry"]).buffer(0) for f in feats]
    tree = STRtree(geoms)
    inside = [[] for _ in feats]
    placed = 0
    for r in recs:
        if r.get("lat") is None or r.get("lng") is None:
            continue
        pt = Point(float(r["lng"]), float(r["lat"]))
        for i in tree.query(pt):
            if geoms[int(i)].contains(pt):
                inside[int(i)].append(r)
                placed += 1
                break
    out = []
    for f, rs in zip(feats, inside):
        code = str(f.get("id") or "").zfill(3) if str(f.get("id") or "").lstrip("-").isdigit() else str(f.get("id") or "")
        by = {}
        for r in rs:
            by[r.get("posture")] = by.get(r.get("posture"), 0) + 1
        props = {"iso3": num2a3.get(code, ""), "name": f["properties"].get("name", ""), "n": len(rs),
                 "harm": by.get("harm", 0), "watch": by.get("watch", 0), "redress": by.get("redress", 0),
                 "unlawful": by.get("unlawful", 0),
                 "list": json.dumps([{"n": r.get("name", ""), "k": r.get("kind", ""), "d": r.get("date", ""), "p": r.get("posture", "")}
                                     for r in rs[:14]], ensure_ascii=False),
                 "more": max(0, len(rs) - 14)}
        out.append({"type": "Feature", "properties": props,
                    "geometry": {"type": f["geometry"]["type"], "coordinates": rounded(f["geometry"]["coordinates"])}})
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": out}, ensure_ascii=False, separators=(",", ":")))
    print(f"remains_units: {len(out)} countries; {placed:,} of {len(recs):,} records placed inside one "
          f"({sum(1 for p in out if p['properties']['n'])} countries hold any); {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
