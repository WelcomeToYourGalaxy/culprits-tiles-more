#!/usr/bin/env python3
"""
Ocean Conservancy's Coastal Cleanup sites, copied daily into
coastal/cleanups.geojson. Its server lets only its own site read its data, so
Culprits reads this copy instead. Every field it gives for a site is kept.
"""
import json, pathlib, sys, urllib.request

URL = "https://www.coastalcleanupdata.org/ajax/cleanups"
OUT = pathlib.Path("coastal/cleanups.geojson")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas refresh)",
                                               "X-Requested-With": "XMLHttpRequest"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode("utf-8"))


def all_sites():
    """Every site, page by page, over every date. Asked with no page, the server
    gives 5,000 sites (a cap: the copy of 24 September held exactly 5,000). Its
    own map asks ?page=1, 2, 3... with a start and end date, so that is done
    here from 1900 to today, until a page brings nothing new."""
    import datetime, time
    end = datetime.date.today().isoformat()
    seen, sites, t0 = set(), [], time.monotonic()
    for page in range(1, 5000):
        if time.monotonic() - t0 > 100 * 60:
            print(f"coastal cleanup: stopped at page {page} for time", file=sys.stderr)
            break
        try:
            data = fetch(f"{URL}?page={page}&start=1900-01-01&end={end}&year=true")
        except Exception as e:  # noqa: BLE001
            print(f"coastal cleanup: page {page} not read ({e})", file=sys.stderr)
            break
        new = 0
        for s in data.get("sites") or []:
            key = s.get("id") or json.dumps(s, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            sites.append(s)
            new += 1
        if not new:
            break
        time.sleep(0.3)
    print(f"coastal cleanup: {page - 1 if not new else page} pages read", flush=True)
    return sites


def main():
    try:
        sites = all_sites()
    except Exception as e:  # noqa: BLE001
        sites = []
        print(f"coastal cleanup: paged reading failed ({e})", file=sys.stderr)
    if not sites:
        # The old single request, which gives the first 5,000.
        try:
            sites = fetch(URL).get("sites") or []
        except Exception as e:  # noqa: BLE001
            sys.exit(f"coastal cleanup: could not read ({e}); the last good copy stays")
    feats = []
    for s in sites:
        try:
            lat, lng = float(s["lat"]), float(s["lng"])
        except (KeyError, TypeError, ValueError):
            continue
        props = {k: v for k, v in s.items() if k not in ("lat", "lng")}
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]}, "properties": props})
    if not feats:
        sys.exit("coastal cleanup: no sites returned; the last good copy stays")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":"))
    if len(body.encode("utf-8")) > 95_000_000:
        sys.exit(f"coastal cleanup: {len(feats):,} sites make a file over GitHub's limit; not written, the last copy stays. "
                 "The copy needs cutting into parts.")
    OUT.write_text(body, encoding="utf-8")
    print(f"coastal cleanup: {len(feats):,} sites")


if __name__ == "__main__":
    main()
