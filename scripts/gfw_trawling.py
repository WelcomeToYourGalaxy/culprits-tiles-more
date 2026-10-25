#!/usr/bin/env python3
"""
Bottom trawling and every other kind of fishing, as Global Fishing Watch sees
it from ships' own position signals (round 140b; the owner added the free API
token as the repository secret GFW_TOKEN, which the refresh workflow passes to
this script). Global Fishing Watch, apparent fishing effort
(public-global-fishing-effort), the latest full year, 0.1 degree squares,
fishing hours by gear type. Non-commercial use with credit (Global Fishing
Watch terms of use).

The world is asked for in 20 by 20 degree boxes (the report service takes a
polygon at a time). Writes, for the map's row gfw_gear:

  tiles/gfw_gear_<gear>_<year>.pmtiles   hours of fishing per square, log steps
  tiles/gfw_gear.choices.json            trawlers first, dredges, then every
                                         other gear type the service returns,
                                         and all gear together
  fish/gfw_build.json                    year, gear types, boxes not answered

Monthly (first Sunday), or by hand.
"""
import datetime, json, math, os, pathlib, sys, time, urllib.parse, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

API = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
T = pathlib.Path("tiles")
STAMP = pathlib.Path("fish/gfw_build.json")
RES = 0.1
FIRST = ["trawlers", "dredge_fishing"]
WORDS = {"trawlers": "Trawlers (bottom and mid-water trawling)", "dredge_fishing": "Dredges", "all": "All fishing gear together"}


def ask(year, box, token):
    w, s, e, n = box
    q = {"spatial-resolution": "LOW", "temporal-resolution": "ENTIRE", "group-by": "GEARTYPE", "spatial-aggregation": "false",
         "datasets[0]": "public-global-fishing-effort:latest", "date-range": f"{year}-01-01,{year + 1}-01-01", "format": "JSON"}
    body = json.dumps({"geojson": {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}}).encode()
    for wait in (0, 20, 60, 180):
        time.sleep(wait)
        try:
            req = urllib.request.Request(API + "?" + urllib.parse.urlencode(q), data=body, method="POST",
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json",
                                                  "User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"})
            return json.loads(urllib.request.urlopen(req, timeout=600).read())
        except urllib.error.HTTPError as ex:
            if ex.code not in (429, 500, 502, 503, 504):
                # Round 145b: every box came back 403 on 3 October; say what GFW said.
                try:
                    said = ex.read()[:400].decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    said = ""
                raise RuntimeError(f"HTTP {ex.code}: {said}") from None
            last = ex
    raise last


def main():
    token = os.environ.get("GFW_TOKEN")
    if not token:
        raise SystemExit("gfw_trawling: no GFW_TOKEN in the environment; the refresh workflow must pass the repository secret")
    today = datetime.date.today()
    if STAMP.exists() and not (today.weekday() == 6 and today.day <= 7) and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("gfw_trawling: monthly; not the first Sunday")
        return
    pyramid.need()
    import numpy as np
    year = today.year - 1
    W, H = int(360 / RES), int(180 / RES)
    grids, missed = {}, []
    for s in range(-90, 90, 20):
        if len(missed) >= 3 and not grids and all("HTTP 40" in m["error"] for m in missed[-3:]):
            break
        for w in range(-180, 180, 20):
            try:
                d = ask(year, (w, s, w + 20, s + 20), token)
            except Exception as e:  # noqa: BLE001
                missed.append({"box": [w, s], "error": f"{type(e).__name__}: {e}"})
                # The same refusal three times running: the token or the request, not the box.
                if len(missed) >= 3 and all("HTTP 40" in m["error"] for m in missed[-3:]) and len(missed) == len(grids) + len(missed) and not grids:
                    break
                continue
            for entry in d.get("entries", []):
                for rows in entry.values():
                    for r in rows or []:
                        g = str(r.get("geartype") or "not given").lower()
                        lat, lon, h = r.get("lat"), r.get("lon"), r.get("hours") or 0
                        if lat is None or lon is None or not h:
                            continue
                        x, y = int((lon + 180) / RES), int((90 - lat) / RES)
                        if 0 <= x < W and 0 <= y < H:
                            for k in (g, "all"):
                                grids.setdefault(k, np.zeros((H, W), np.float32))[y, x] += h
    if not grids:
        STAMP.parent.mkdir(exist_ok=True)
        STAMP.write_text(json.dumps({"year": year, "boxes_not_answered": missed}, indent=1))
        raise SystemExit("gfw_trawling: nothing came back; see fish/gfw_build.json")
    order = [g for g in FIRST if g in grids] + sorted(g for g in grids if g not in FIRST and g != "all") + ["all"]
    choices = []
    for g in order:
        a = grids[g]
        pos = a[a > 0]
        lo, hi = max(float(np.percentile(pos, 50)), 1e-3), max(float(np.percentile(pos, 99.9)), 1e-2)
        hi = max(hi, lo * 10)
        t = (np.log10(np.clip(a, lo, hi)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
        codes = np.where(a > 0, 1 + np.clip(np.floor(t * 10), 0, 9), 0).astype(np.uint8)
        edges = [lo * (hi / lo) ** (i / 10) for i in range(11)]
        out = T / f"gfw_gear_{g}_{year}.pmtiles"
        pyramid.build(codes, -180.0, 90.0, RES, {i + 1: pyramid.rgba(c, 240) for i, c in enumerate(pyramid.RAMP10)}, out, 7, how="max",
                      attribution="Global Fishing Watch", name=out.stem, meta={"year": year, "gear": g})
        key = [[c, f"{edges[i]:,.1f} to {edges[i + 1]:,.1f} hours"] for i, c in enumerate(pyramid.RAMP10)]
        choices.append({"label": f"{WORDS.get(g, g.replace('_', ' ').capitalize())}, {year}", "archive": f"tiles/{out.name}", "key": key})
    pyramid.write_choices("gfw_gear", choices)
    STAMP.parent.mkdir(exist_ok=True)
    STAMP.write_text(json.dumps({"year": year, "gear_types": order, "hours": {g: float(grids[g].sum()) for g in order},
                                 "boxes_not_answered": missed}, indent=1))
    print(f"gfw_trawling: {year}: {', '.join(order)}; {len(missed)} boxes not answered", flush=True)


if __name__ == "__main__":
    main()
