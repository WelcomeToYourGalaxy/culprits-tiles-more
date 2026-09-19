#!/usr/bin/env python3
"""
SkyTruth Monitor, "Vessels of concern": its alerts for the whole world over the
last 30 days, copied daily into skytruth/vessels_of_concern.geojson, with the
issue's own description and feeds (skytruth/issue.json), since its service is
built for its own page.
"""
import json, pathlib, sys, urllib.request

API = "https://skytruth-alerts2.appspot.com/api"
OUT = pathlib.Path("skytruth")


def get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy)"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def point(a):
    for la, lo in (("lat", "lng"), ("lat", "lon"), ("latitude", "longitude")):
        if num(a.get(la)) is not None and num(a.get(lo)) is not None:
            return [num(a[lo]), num(a[la])]
    g = a.get("geometry") or a.get("location")
    if isinstance(g, dict) and g.get("coordinates"):
        return g["coordinates"][:2]
    if isinstance(g, str):
        m = [num(x) for x in g.replace("POINT", "").strip("() ").split()]
        if len(m) == 2 and None not in m:
            return m
    return None


def main():
    OUT.mkdir(exist_ok=True)
    try:
        issue = get("/getissue/?id=vessels-of-concern")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"skytruth: could not read ({e}); the last good copy stays")
    (OUT / "issue.json").write_text(json.dumps(issue, ensure_ascii=False), encoding="utf-8")
    feeds = set()
    for k in ("feeds", "feed_ids", "selected", "feedsources"):
        v = issue.get(k) if isinstance(issue, dict) else None
        if isinstance(v, list):
            feeds.update(str(x.get("id") if isinstance(x, dict) else x) for x in v)
    feeds = feeds or {"10102"}
    rows = []
    for f in sorted(feeds):
        try:
            got = get(f"/getalerts/?l=-85,-180,85,180&d=30&selected={f}&n=5000&keyword=")
        except Exception as e:  # noqa: BLE001
            print(f"skytruth feed {f}: {e}", file=sys.stderr)
            continue
        rows.extend(got if isinstance(got, list) else got.get("alerts") or got.get("results") or got.get("features") or [])
    feats, seen = [], set()
    for a in rows:
        props = a.get("properties", a) if isinstance(a, dict) else {}
        at = point(a) or point(props)
        key = props.get("id") or props.get("url") or json.dumps(props, sort_keys=True)[:200]
        if not at or key in seen:
            continue
        seen.add(key)
        clean = {k: v for k, v in props.items() if isinstance(v, (str, int, float, bool)) and k not in ("lat", "lng", "lon")}
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": at}, "properties": clean})
    if not feats:
        sample = rows[0] if rows else issue
        sys.exit(f"skytruth: no positions found; an alert's fields are {sorted((sample or {}).keys()) if isinstance(sample, dict) else type(sample)}")
    (OUT / "vessels_of_concern.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")
    print(f"skytruth: {len(feats)} vessels-of-concern alerts from {len(feeds)} feeds")


if __name__ == "__main__":
    main()
