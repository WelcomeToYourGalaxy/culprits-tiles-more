#!/usr/bin/env python3
"""
The layers of the uMap maps Culprits draws, copied daily into
umap/<map id>/<layer id>.geojson.

uMap serves a map's own settings to any site, but each layer's places come back
without a CORS header (and marked as a web page), at both the address the map
gives (/en/datalayer/<map>/<layer>/) and the one without the language part -
checked 22 September. So the browser cannot read them, and Culprits reads this
copy. Every field of every place is kept as uMap gives it.

A layer that cannot be read today keeps yesterday's copy.
"""
import json, pathlib, sys, urllib.request

SITE = "https://umap.openstreetmap.fr"
MAPS = [409815]                        # Wreckers of the Earth (Corporate Watch)
OUT = pathlib.Path("umap")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas refresh)"}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode("utf-8"))


def main():
    copied = kept = 0
    for mid in MAPS:
        try:
            m = get(f"{SITE}/en/map/{mid}/geojson/")
        except Exception as e:  # noqa: BLE001
            print(f"umap {mid}: the map could not be read ({e}); yesterday's copy stays", file=sys.stderr)
            continue
        props = m.get("properties") or {}
        tpl = (props.get("urls") or {}).get("datalayer_view") or "/en/datalayer/{map_id}/{pk}/"
        here = OUT / str(mid)
        here.mkdir(parents=True, exist_ok=True)
        # The map's own settings too (round 61): read live, they failed on the
        # owner's screen and the whole row with them.
        (here / "map.json").write_text(json.dumps(m, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        for dl in props.get("datalayers") or m.get("datalayers") or []:
            lid = dl.get("id") or dl.get("uuid") or dl.get("pk") if isinstance(dl, dict) else dl
            if not lid:
                continue
            url = SITE + tpl.replace("{map_id}", str(mid)).replace("{pk}", str(lid)).replace("{datalayer_id}", str(lid))
            try:
                gj = get(url)
                if gj.get("type") != "FeatureCollection":
                    raise ValueError("not a list of places")
                (here / f"{lid}.geojson").write_text(json.dumps(gj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                copied += 1
            except Exception as e:  # noqa: BLE001
                kept += (here / f"{lid}.geojson").exists()
                print(f"umap {mid}/{lid}: not read ({e})", file=sys.stderr)
    print(f"umap: {copied} layers copied, {kept} kept from before")
    if not copied and not kept:
        sys.exit("umap: nothing could be copied")


if __name__ == "__main__":
    main()
