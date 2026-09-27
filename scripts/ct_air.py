#!/usr/bin/env python3
"""
Climate TRACE's air-pollution sources in urban areas (the ones its city
air-pollution pages show, each with modelled pollution plumes), gathered daily
from its per-country plume indexes into ct_air/sources.geojson: each source's
position, name, urban area, PM2.5 rate and the address of its latest plume.
Culprits reads each source's plume and pollutant figures live when clicked.
"""
import json, pathlib, sys, time, urllib.error, urllib.request

BASE = "https://plumes.climatetrace.org"
ISO = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/culprits/main/map/data/boundaries.geojson"
OUT = pathlib.Path("ct_air/sources.geojson")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Culprits atlas daily copy"})
    return urllib.request.urlopen(req, timeout=60).read()


def walk(node, path, out):
    if isinstance(node, dict):
        if "asset_path" in node and "latitude" in node and "longitude" in node:
            out.append((path, node))
            return
        for k, v in node.items():
            walk(v, path + [k], out)
    elif isinstance(node, list):
        for v in node:
            walk(v, path, out)


def main():
    isos = sorted({f["properties"].get("iso3") for f in json.loads(get(ISO))["features"] if f["properties"].get("iso3")})
    feats, found = {}, 0
    for iso in isos:
        try:
            idx = json.loads(get(f"{BASE}/{iso.lower()}-aggregations-index.json"))
        except urllib.error.HTTPError:
            continue
        except Exception as e:  # noqa: BLE001
            print(f"ct_air {iso}: {e}", file=sys.stderr)
            continue
        found += 1
        rows = []
        walk(idx, [], rows)
        for path, a in rows:
            keys = [str(p) for p in path if p != "asset_paths"]
            area = next((p for p in keys if p.startswith("ghs-")), keys[-2] if len(keys) > 1 else "")
            key = str(a.get("asset_id"))
            f = feats.get(key)
            if f is None:
                feats[key] = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(a["longitude"]), float(a["latitude"])]},
                              "properties": {"id": key, "name": a.get("asset_name") or "", "country": iso, "area": str(area),
                                             "group": keys[-1] if keys else "", "pm25_kg_hr": a.get("monthly_pm2_5_emission_kg_hr"),
                                             "plume": a.get("asset_path") or ""}}
            elif (a.get("asset_path") or "") > f["properties"]["plume"]:
                f["properties"]["plume"] = a["asset_path"]
        time.sleep(0.2)
    if not feats:
        sys.exit("ct_air: no plume indexes answered; the last good copy stays")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": list(feats.values())}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"ct_air: {len(feats)} sources from {found} countries' plume indexes")


if __name__ == "__main__":
    main()
