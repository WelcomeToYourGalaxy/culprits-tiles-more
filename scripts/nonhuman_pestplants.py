#!/usr/bin/env python3
"""
Where pesticides are made in Europe, for the Invasion of non-humans map
(round nh2, asked 16 October; source changed in round nh4).

Source: the European Pollutant Release and Transfer Register (E-PRTR) as the
European Environment Agency serves it (air.discomap.eea.europa.eu,
Air/EprtrFacilities_Dyna_WGS84, layer 0): every facility report from 2001 to
2017, with each facility's activity under the E-PRTR Regulation's Annex I and
its NACE economic activity. Kept: every report whose Annex I activity is 4(d),
"chemical installations for the production on an industrial scale of basic
plant health products and of biocides", or whose NACE activity is 20.2,
"manufacture of pesticides and other agrochemical products". Each facility is
one dot, with every field of its newest report, the years it reported, and
which of the two it was listed under. (Round nh2 read a different EEA service
that, it turned out, holds only the 129 facilities whose air pollution costs
the most; none makes pesticides.)

The United States' registered pesticide-producing establishments are read
live by the map itself, from EPA's own service.

  nonhuman/pest_plants_eu.geojson, nonhuman/pest_plants_eu.build.json

Weekly; PESTPLANTS_REBUILD=1 or a run by hand builds at once.
"""
import json, pathlib, sys, urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "pest_plants_eu"
LAYER = "https://air.discomap.eea.europa.eu/arcgis/rest/services/Air/EprtrFacilities_Dyna_WGS84/MapServer/0/query"
WHERE = "IAActivityCode = '4.(d)' OR NACEActivityCode = '20.2'"
WHY = {"annex": "E-PRTR Annex I 4(d): plant health products and biocides", "nace": "NACE 20.2: pesticides and other agrochemical products"}


def q(**kw):
    kw.setdefault("f", "json")
    return nh.get_json(LAYER + "?" + urllib.parse.urlencode(kw), timeout=180)


def main():
    if not nh.due(NAME, 7, "PESTPLANTS_REBUILD"):
        return
    n = q(where=WHERE, returnCountOnly="true").get("count")
    reports, off = [], 0
    while True:
        j = q(where=WHERE, outFields="*", outSR="4326", orderByFields="FacilityReportID", resultOffset=off, resultRecordCount=1000, f="geojson")
        fs = j.get("features", [])
        reports += fs
        off += len(fs)
        if not fs or len(fs) < 1000 and not (j.get("exceededTransferLimit") or (j.get("properties") or {}).get("exceededTransferLimit")):
            break
    by = {}
    for f in reports:
        p = f.get("properties") or {}
        k = p.get("FacilityID") or p.get("FacilityReportID")
        by.setdefault(k, []).append(f)
    feats = []
    for k, fs in by.items():
        fs.sort(key=lambda f: (f["properties"].get("ReportingYear") or 0))
        new = fs[-1]
        if not new.get("geometry"):
            new = next((f for f in reversed(fs) if f.get("geometry")), None)
            if not new:
                continue
        p = {c: v for c, v in new["properties"].items() if v is not None and not str(c).startswith("LOV_")}
        p["years_reported"] = ", ".join(str(y) for y in sorted({f["properties"].get("ReportingYear") for f in fs} - {None}))
        why = []
        if any(f["properties"].get("IAActivityCode") == "4.(d)" for f in fs):
            why.append(WHY["annex"])
        if any(f["properties"].get("NACEActivityCode") == "20.2" for f in fs):
            why.append(WHY["nace"])
        p["listed_as"] = "; ".join(why)
        feats.append({"type": "Feature", "geometry": new["geometry"], "properties": p})
    nh.OUT.mkdir(parents=True, exist_ok=True)
    (nh.OUT / "pest_plants_eu.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    nh.write_stamp(NAME, {"service": LAYER, "where": WHERE, "reports counted": n, "reports read": len(reports), "facilities": len(feats),
                          "years": sorted({f["properties"].get("ReportingYear") for f in reports} - {None}), "failed": not feats})
    print(f"pest plants: {len(feats)} facilities from {len(reports)} reports")


if __name__ == "__main__":
    main()
