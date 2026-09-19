#!/usr/bin/env python3
"""
A daily archive of Cerulean's oil slicks (SkyTruth), so every slick stays on the
map by month even when Cerulean's own service is slow, down or changes. Each run
reads the slicks from the last 3 days (the first run reads the last 60) and adds
any new ones to cerulean_archive/<year-month>.geojson, keeping everything
already archived. cerulean_archive/index.json lists the months and counts.
"""
import datetime as dt, json, pathlib, sys, time, urllib.parse, urllib.request

API = "https://api.cerulean.skytruth.org/collections/public.slick_plus/items"
OUT = pathlib.Path("cerulean_archive")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Culprits atlas daily archive", "Accept": "application/geo+json"})
    for i in range(3):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=180).read())
        except Exception:  # noqa: BLE001
            if i == 2:
                raise
            time.sleep(10)


def rnd(c):
    return [rnd(x) for x in c] if isinstance(c, list) and c and isinstance(c[0], list) else [round(x, 5) for x in c] if isinstance(c, list) else c


def main():
    OUT.mkdir(exist_ok=True)
    first = not (OUT / "index.json").exists()
    since = (dt.datetime.utcnow() - dt.timedelta(days=60 if first else 3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    url = API + "?" + urllib.parse.urlencode({"datetime": f"{since}/{now}", "limit": 1000})
    new, pages = [], 0
    while url and pages < 200:
        try:
            page = get(url)
        except Exception as e:  # noqa: BLE001
            print(f"cerulean archive: stopped after {len(new)} slicks ({e})", file=sys.stderr)
            break
        new.extend(page.get("features") or [])
        url = next((l.get("href") for l in page.get("links") or [] if l.get("rel") == "next"), None)
        pages += 1
    by_month = {}
    for f in new:
        p = f.get("properties") or {}
        stamp = str(p.get("slick_timestamp") or p.get("datetime") or "")[:7]
        if len(stamp) == 7 and f.get("geometry"):
            f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
            by_month.setdefault(stamp, []).append(f)
    index = json.loads((OUT / "index.json").read_text()) if not first else {}
    added = 0
    for month, feats in by_month.items():
        path = OUT / f"{month}.geojson"
        have = json.loads(path.read_text())["features"] if path.exists() else []
        ids = {str((x.get("properties") or {}).get("id", x.get("id"))) for x in have}
        for f in feats:
            key = str((f.get("properties") or {}).get("id", f.get("id")))
            if key not in ids:
                have.append(f)
                ids.add(key)
                added += 1
        path.write_text(json.dumps({"type": "FeatureCollection", "features": have}, separators=(",", ":")), encoding="utf-8")
        index[month] = len(have)
    (OUT / "index.json").write_text(json.dumps(dict(sorted(index.items(), reverse=True))), encoding="utf-8")
    print(f"cerulean archive: {len(new)} slicks read, {added} new, {len(index)} months kept")


if __name__ == "__main__":
    main()
