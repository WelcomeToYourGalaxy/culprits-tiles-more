#!/usr/bin/env python3
"""
Ocean Conservancy's Coastal Cleanup sites, copied daily into
coastal/cleanups.geojson. Its server lets only its own site read its data, so
Culprits reads this copy instead. Every field it gives for a site is kept.
"""
import json, pathlib, sys, urllib.request

URL = "https://www.coastalcleanupdata.org/ajax/cleanups"
OUT = pathlib.Path("coastal/cleanups.geojson")


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas refresh)",
                                               "X-Requested-With": "XMLHttpRequest"})
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=120).read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"coastal cleanup: could not read ({e}); the last good copy stays")
    feats = []
    for s in data.get("sites") or []:
        try:
            lat, lng = float(s["lat"]), float(s["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        props = {k: v for k, v in s.items() if k not in ("lat", "lng")}
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]}, "properties": props})
    if not feats:
        sys.exit("coastal cleanup: no sites returned; the last good copy stays")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), encoding="utf-8")
    print(f"coastal cleanup: {len(feats):,} sites")


if __name__ == "__main__":
    main()
