#!/usr/bin/env python3
"""
Where pesticides are made in Europe, for the Invasion of non-humans map
(round nh2, asked 16 October).

Source: the European Environment Agency's E-PRTR facilities map service
(air.discomap.eea.europa.eu, EPRTR/EPRTR_FACILITIES, layer 0), which lists
each reporting facility with its main activity. Every activity name the
service gives is listed in the build file; every facility whose main activity
names plant protection products, biocides or pesticides is kept, with every
field the service gives. (The United States' registered pesticide-producing
establishments are read live by the map itself, from EPA's own service.)

  nonhuman/pest_plants_eu.geojson, nonhuman/pest_plants_eu.build.json

Weekly; PESTPLANTS_REBUILD=1 or a run by hand builds at once.
"""
import json, pathlib, re, sys, urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "pest_plants_eu"
LAYER = "https://air.discomap.eea.europa.eu/arcgis/rest/services/EPRTR/EPRTR_FACILITIES/MapServer/0/query"
WANT = re.compile(r"plant protection|biocid|pesticid", re.I)


def q(**kw):
    kw.setdefault("f", "json")
    return nh.get_json(LAYER + "?" + urllib.parse.urlencode(kw), timeout=180)


def main():
    if not nh.due(NAME, 7, "PESTPLANTS_REBUILD"):
        return
    d = q(where="1=1", outFields="mainActivityName", returnDistinctValues="true", returnGeometry="false")
    acts = sorted({(f.get("attributes") or {}).get("mainActivityName") for f in d.get("features", [])} - {None})
    chosen = [a for a in acts if WANT.search(a)]
    feats = []
    for a in chosen:
        off = 0
        while True:
            j = q(where=f"mainActivityName = '{a.replace(chr(39), chr(39) * 2)}'", outFields="*", outSR="4326", resultOffset=off, resultRecordCount=1000, f="geojson")
            fs = j.get("features", [])
            feats += fs
            off += len(fs)
            if not fs or not j.get("exceededTransferLimit") and len(fs) < 1000:
                break
    nh.OUT.mkdir(parents=True, exist_ok=True)
    (nh.OUT / "pest_plants_eu.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    nh.write_stamp(NAME, {"activity names the service gives": acts, "kept": chosen, "facilities": len(feats), "failed": not chosen})
    print(f"pest plants: {len(feats)} facilities under {chosen}")


if __name__ == "__main__":
    main()
