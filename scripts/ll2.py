#!/usr/bin/env python3
"""
A daily copy of Launch Library 2's launch pads and upcoming launches, for when
a visitor's 15 live requests an hour are used up. Culprits reads Launch Library
live first; this is only its fallback.  ll2/pads.json, ll2/upcoming.json
"""
import json, pathlib, sys, time, urllib.request

BASE = "https://ll.thespacedevs.com/2.3.0"
OUT = pathlib.Path("ll2")


def get_all(path):
    out, url = [], f"{BASE}{path}?limit=100&mode=detailed"
    while url and len(out) < 600:
        req = urllib.request.Request(url, headers={"User-Agent": "Culprits atlas daily copy"})
        j = json.loads(urllib.request.urlopen(req, timeout=120).read())
        out.extend(j.get("results") or [])
        url = j.get("next")
        time.sleep(2)
    return out


def main():
    OUT.mkdir(exist_ok=True)
    for name, path in (("pads", "/pads/"), ("upcoming", "/launches/upcoming/")):
        try:
            rows = get_all(path)
        except Exception as e:  # noqa: BLE001
            print(f"ll2 {name}: could not read ({e}); the last good copy stays", file=sys.stderr)
            continue
        if rows:
            (OUT / f"{name}.json").write_text(json.dumps({"results": rows}, separators=(",", ":")), encoding="utf-8")
            print(f"ll2 {name}: {len(rows)}")


if __name__ == "__main__":
    main()
