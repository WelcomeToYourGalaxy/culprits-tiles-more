#!/usr/bin/env python3
"""
Giga (UNICEF/ITU) school mapping, by country: every country on its map with its
own figures (schools mapped, share with connectivity data, whether connectivity
and coverage data exist, the data source), plus its world totals. Copied daily
into giga/countries.json, since its data service does not let other sites read it.
"""
import gzip, json, pathlib, sys, urllib.request

G = "https://uni-ooi-giga-backend-hjekcuagasashucv.a03.azurefd.net"
OUT = pathlib.Path("giga/countries.json")


def get(path):
    req = urllib.request.Request(G + path, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy)", "Accept-Encoding": "identity"})
    raw = urllib.request.urlopen(req, timeout=120).read()
    return json.loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)


def main():
    try:
        countries = get("/api/v2/entities/countries/")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"giga: could not read ({e}); the last good copy stays")
    try:
        world = get("/api/v2/entities/global-stat/?entity_type__code=all")
    except Exception:  # noqa: BLE001
        world = None
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"world": world, "countries": countries}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"giga: {len(countries)} countries")


if __name__ == "__main__":
    main()
