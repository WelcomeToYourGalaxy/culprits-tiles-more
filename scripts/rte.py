#!/usr/bin/env python3
"""
A daily copy of resourcetrade.earth's country list and its largest trade flows
for every year, for when a visitor's browser cannot read Chatham House's own
data address. Culprits reads it live first; this is its fallback.
  rte/models.json, rte/trades_<year>.json
"""
import json, pathlib, sys, time, urllib.request

API = "https://api.resourcetrade.earth/api/rt/2.7"
OUT = pathlib.Path("rte")


def get(path):
    req = urllib.request.Request(API + path, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy)"})
    return urllib.request.urlopen(req, timeout=120).read()


def main():
    OUT.mkdir(exist_ok=True)
    try:
        models = json.loads(get("/models"))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"rte: could not read ({e}); the last good copy stays")
    (OUT / "models.json").write_text(json.dumps({"countries": models.get("countries"), "years": models.get("years")}), encoding="utf-8")
    n = 0
    for y in [int(x["id"]) for x in models.get("years") or []]:
        try:
            (OUT / f"trades_{y}.json").write_bytes(get(f"/trades?year={y}&autozoom=1"))
            n += 1
        except Exception as e:  # noqa: BLE001
            print(f"rte {y}: {e}", file=sys.stderr)
        time.sleep(1)
    print(f"rte: {n} years copied")


if __name__ == "__main__":
    main()
