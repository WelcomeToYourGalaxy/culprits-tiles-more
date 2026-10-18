#!/usr/bin/env python3
"""
Offshore oil and gas platforms (round 136b, asked 2 October; also under Oil
and gas spills). Every platform OpenStreetMap maps at sea: man_made =
offshore_platform, and seamark:type = platform, every tag of each kept.
OpenStreetMap is made by volunteers: it is not a register, and some seas are
mapped far more fully than others. ODbL.

  offshore/platforms.geojson   one point per platform (the middle of a drawn
                               outline), every tag, "x_kind" from its tags
  offshore/build.json          counts, and the slices Overpass did not answer

Asked from Overpass in slices of 30 by 30 degrees. Weekly (Sundays), or by hand.
"""
import datetime, json, os, pathlib, time, urllib.parse, urllib.request

OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
OUT = pathlib.Path("offshore")
UA = {"User-Agent": "Culprits atlas build (welcometoyourgalaxy@gmail.com)"}


def ask(q):
    last = None
    for url in OVERPASS:
        for wait in (0, 30):
            time.sleep(wait)
            try:
                data = urllib.parse.urlencode({"data": q}).encode()
                return json.loads(urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=300).read())
            except Exception as e:  # noqa: BLE001
                last = e
    raise last


def kind(t):
    words = " ".join(str(v) for v in t.values()).lower()
    if "gas" in words and "oil" not in words:
        return "gas"
    if "oil" in words and "gas" not in words:
        return "oil"
    if "oil" in words and "gas" in words:
        return "oil and gas"
    if "wind" in words:
        return "wind"
    return "not stated"


def main():
    if (OUT / "platforms.geojson").exists() and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("offshore_platforms: weekly; not Sunday")
        return
    OUT.mkdir(exist_ok=True)
    feats, seen, missed = [], set(), []
    for s in range(-90, 90, 30):
        for w in range(-180, 180, 30):
            bbox = f"{s},{w},{s + 30},{w + 30}"
            q = (f'[out:json][timeout:240];(nwr["man_made"="offshore_platform"]({bbox});nwr["seamark:type"="platform"]({bbox}););out center tags;')
            try:
                els = ask(q).get("elements", [])
            except Exception as e:  # noqa: BLE001
                missed.append({"slice": bbox, "error": f"{type(e).__name__}: {e}"})
                continue
            for el in els:
                k = f'{el["type"]}/{el["id"]}'
                if k in seen:
                    continue
                seen.add(k)
                lat = el.get("lat", (el.get("center") or {}).get("lat"))
                lon = el.get("lon", (el.get("center") or {}).get("lon"))
                if lat is None or lon is None:
                    continue
                t = el.get("tags", {})
                p = {"name": t.get("name") or t.get("seamark:name") or "", "group": kind(t), "x_kind": kind(t), "osm": f"https://www.openstreetmap.org/{k}"}
                p.update(t)
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": p})
    (OUT / "platforms.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    kinds = {}
    for f in feats:
        kinds[f["properties"]["x_kind"]] = kinds.get(f["properties"]["x_kind"], 0) + 1
    (OUT / "build.json").write_text(json.dumps({"read": datetime.date.today().isoformat(), "platforms": len(feats), "kinds": kinds,
                                                "slices_not_answered": missed}, indent=1))
    print(f"offshore_platforms: {len(feats)} platforms {kinds}; {len(missed)} slices not answered", flush=True)


if __name__ == "__main__":
    main()
