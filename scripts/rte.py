#!/usr/bin/env python3
"""
A daily copy of resourcetrade.earth's country list and its largest trade flows
for every year, for when a visitor's browser cannot read Chatham House's own
data address. Culprits reads it live first; this is its fallback.
  rte/models.json, rte/trades_<year>.json
Round 119b: also every flow of each year, not only the largest, which the map
now reads first (rte/trades_all_<year>.json; older years once, the last three
each day).
"""
import json, os, pathlib, sys, time, urllib.request

API = "https://api.resourcetrade.earth/api/rt/2.7"
OUT = pathlib.Path("rte")


def get(path, timeout=120):
    req = urllib.request.Request(API + path, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy)"})
    return urllib.request.urlopen(req, timeout=timeout).read()


def main():
    OUT.mkdir(exist_ok=True)
    try:
        models = json.loads(get("/models"))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"rte: could not read ({e}); the last good copy stays")
    (OUT / "models.json").write_text(json.dumps({"countries": models.get("countries"), "years": models.get("years")}), encoding="utf-8")
    n = full = 0
    for y in [int(x["id"]) for x in models.get("years") or []]:
        try:
            (OUT / f"trades_{y}.json").write_bytes(get(f"/trades?year={y}&autozoom=1"))
            n += 1
        except Exception as e:  # noqa: BLE001
            print(f"rte {y}: {e}", file=sys.stderr)
        time.sleep(1)
        # Round 119b: every flow of the year (autozoom=0), not only the largest
        # the live address sends; kept only when it holds more.
        all_path = OUT / f"trades_all_{y}.json"
        if all_path.exists() and y < time.gmtime().tm_year - 2 and not os.environ.get("RTE_REBUILD"):
            continue
        try:
            body = get(f"/trades?year={y}&autozoom=0", timeout=900)
            got = json.loads(body)
            small = json.loads((OUT / f"trades_{y}.json").read_text()) if (OUT / f"trades_{y}.json").exists() else {}
            if len(got.get("main") or []) > len(small.get("main") or []):
                all_path.write_bytes(body)
                full += 1
                print(f"rte {y}: {len(got['main']):,} flows (every one)", flush=True)
            else:
                print(f"rte {y}: the whole-year request gave no more flows than the largest ({len(got.get('main') or [])})", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"rte {y}, every flow: {e}", file=sys.stderr)
        time.sleep(2)
    print(f"rte: {n} years copied, {full} with every flow")


if __name__ == "__main__":
    main()
