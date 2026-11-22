#!/usr/bin/env python3
"""
Reads only (round 94b, asked 27 September: what share of the "Concessions of
other kinds" are mining and what share clearing for plantations or timber).
Asks Nusantara Atlas's GeoServer for the layer's fields and every record's
attributes (no shapes), and counts the records and their stated area by each
field that names a kind, sector, commodity or permit type.

  probe/concessions.json   fields, and counts and areas by each kind-like field

By hand only.
"""
import collections, json, os, pathlib, re, urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas probe; welcometoyourgalaxy@gmail.com)"}
TRIES = [("https://map.nusantara-atlas.org/geoserver/atlas-workspace-v3/wfs", "concessionother_spv"),
         ("https://map.nusantara-atlas.org/geoserver/atlas-workspace-v3/wfs", "v3p3_concessionother_spv"),
         ("https://map.nusantara-atlas.org/geoserver/atlas-workspace-v2/wfs", "concessionother_spv")]
KINDISH = re.compile(r"type|jenis|kind|sector|sektor|komod|commod|activ|kegiatan|izin|permit|category|kategori|class|usaha|bidang", re.I)
AREAISH = re.compile(r"^(luas|area|ha|area_ha|luas_ha|shape_area|hectares?)$", re.I)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        return r.read()


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("concession_probe: by hand only")
        return
    out = {}
    for base, layer in TRIES:
        rec = {}
        try:
            q = urllib.parse.urlencode({"service": "WFS", "version": "1.0.0", "request": "GetFeature", "typeName": layer,
                                        "outputFormat": "application/json", "maxFeatures": 200000})
            j = json.loads(get(f"{base}?{q}"))
            feats = j.get("features", [])
            props = [f.get("properties") or {} for f in feats]
            fields = sorted({k for p in props for k in p})
            rec["records"] = len(props)
            rec["fields"] = fields
            area_f = next((k for k in fields if AREAISH.match(k)), None)
            rec["area_field"] = area_f
            by = {}
            for k in fields:
                if not KINDISH.search(k):
                    continue
                c, a = collections.Counter(), collections.Counter()
                for p in props:
                    v = str(p.get(k))
                    c[v] += 1
                    try:
                        a[v] += float(p.get(area_f) or 0) if area_f else 0
                    except (TypeError, ValueError):
                        pass
                if len(c) <= 200:
                    by[k] = {"count": dict(c.most_common()), "area": {x: round(y, 1) for x, y in a.most_common()} if area_f else None}
            rec["by"] = by
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {e}"
        out[f"{base.split('/')[-2]}:{layer}"] = rec
        print(layer, {k: v for k, v in rec.items() if k != "by"}, flush=True)
    pathlib.Path("probe").mkdir(exist_ok=True)
    pathlib.Path("probe/concessions.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
