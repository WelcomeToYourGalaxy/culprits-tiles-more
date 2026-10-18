#!/usr/bin/env python3
"""
Asks each live source the map reads what it answers today, as the map's page
would ask it (round 61, 26 September): the owner found these rows not drawing.
For each: the status, how long it took, the type and size of what came back,
and whether the answer lets another site read it (its Access-Control-Allow-
Origin header, asked with the map's own origin). Saved to
probe/live_sources.json. Changes nothing else. By hand only: run it from
Actions > refresh with live_sources_probe in the box.
"""
import json, os, pathlib, sys, time, urllib.request

if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
    print("live_sources_probe: by hand only")
    sys.exit(0)

ORIGIN = "https://welcometoyourgalaxy.github.io"
SOURCES = {
    "owid_aid (Our World in Data chart data)": "https://ourworldindata.org/grapher/foreign-aid-received-as-a-share-of-national-income-net.csv?v=1&csvType=full&useColumnShortNames=true",
    "owid_aid (chart metadata)": "https://ourworldindata.org/grapher/foreign-aid-received-as-a-share-of-national-income-net.metadata.json?v=1&csvType=full&useColumnShortNames=true",
    "ejatlas (GeoJSON list)": "https://ejatlas.org/api/v1/conflicts/?format=geojson",
    "ejatlas (plain list)": "https://ejatlas.org/api/v1/conflicts/?limit=500&offset=0",
    "ejatlas (data policy page)": "https://ejatlas.org/datapolicy",
    "gsn (layer list)": "https://api.gsn.naturedatalab.org/geo-analysis/layers",
    "usda_corn (map server)": "https://gis.ipad.fas.usda.gov/arcgis/rest/services/CommodityExplorerCorn/MapServer?f=json",
    "usda_soybean (map server)": "https://gis.ipad.fas.usda.gov/arcgis/rest/services/CommodityExplorerSoybean/MapServer?f=json",
    "gfw (dataset list)": "https://data-api.globalforestwatch.org/datasets?page[size]=100&page[number]=1",
    "trase (regions)": "https://resources.trase.earth/data/trase-regions",
    "umap wreckers (map settings)": "https://umap.openstreetmap.fr/en/map/409815/geojson/",
    "launch library (upcoming)": "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=1",
    "carbon mapper": "https://api.carbonmapper.org/api/v1/catalog/plumes/annotated?limit=1",
    "nusantara (WMS capabilities)": "https://map.nusantara-atlas.org/geoserver/atlas-workspace-v3/wms?service=WMS&request=GetCapabilities",
    "wastewater model tiles": "https://mazu.nceas.ucsb.edu/wastewater/N_effluent/0/0/0.png",
}


def ask(url):
    t0 = time.time()
    req = urllib.request.Request(url, headers={"Origin": ORIGIN, "User-Agent": "Mozilla/5.0 (Culprits atlas live-source check)"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read(200000)
            return {"status": r.status, "seconds": round(time.time() - t0, 1), "type": r.headers.get("Content-Type"),
                    "allow_origin": r.headers.get("Access-Control-Allow-Origin"), "bytes_read": len(body),
                    "starts": body[:160].decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "seconds": round(time.time() - t0, 1), "allow_origin": e.headers.get("Access-Control-Allow-Origin"),
                "starts": e.read(300).decode("utf-8", "replace")}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "seconds": round(time.time() - t0, 1)}


def main():
    out = {"asked": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "origin": ORIGIN, "sources": {}}
    for name, url in SOURCES.items():
        out["sources"][name] = {"url": url, **ask(url)}
        s = out["sources"][name]
        print(f"  {name}: {s.get('status', s.get('error'))} in {s['seconds']} s; may be read by the map: {s.get('allow_origin') in ('*', ORIGIN)}", flush=True)
    p = pathlib.Path("probe/live_sources.json")
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
