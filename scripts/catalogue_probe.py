#!/usr/bin/env python3
"""
What the Culprits map's two big catalogues hold right now (round 82b), so rows
the owner names can be found by their real ids and titles:

  probe/catalogues/gfw.json        every Global Forest Watch dataset: id, title,
                                   coverage, and its drawable assets (type,
                                   address, status, latest or not)
  probe/catalogues/nusantara.json  every Nusantara Atlas map layer (v2 and v3
                                   workspaces): name, title, styles
  probe/catalogues/tries.json      one tile asked for from each dataset whose
                                   id or title names fire, burn, concession,
                                   Peru or nitrogen dioxide, and the answer

Runs once on its own (when the files are missing) and whenever it is named by
hand in the refresh box. Reads only; changes nothing else.
"""
import json, os, pathlib, re, sys, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET

OUT = pathlib.Path("probe/catalogues")
API = "https://data-api.globalforestwatch.org"
NUS = ["https://map.nusantara-atlas.org/geoserver/atlas-workspace-v3/wms", "https://map.nusantara-atlas.org/geoserver/atlas-workspace-v2/wms"]
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas probe; welcometoyourgalaxy@gmail.com)"}
KINDS = ["Static vector tile cache", "Dynamic vector tile cache", "Raster tile cache", "COG"]
WANT = re.compile(r"fire|burn|concession|peru|\bper_|nitrogen|no2|tropomi|mangrove|mosaic|complex|logging", re.I)


def get(url, timeout=120):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.status, r.read()


def gfw():
    ds = []
    for page in range(1, 40):
        _, raw = get(f"{API}/datasets?page[size]=100&page[number]={page}")
        rows = json.loads(raw).get("data", [])
        ds += rows
        if len(rows) < 100:
            break
    assets = {}
    for kind in KINDS:
        for page in range(1, 30):
            try:
                _, raw = get(f"{API}/assets?asset_type={urllib.parse.quote(kind)}&page[size]=1000&page[number]={page}", 180)
            except Exception as e:  # noqa: BLE001
                print(f"  assets {kind} page {page}: {e}")
                break
            part = json.loads(raw).get("data", [])
            for a in part:
                assets.setdefault(a.get("dataset"), []).append({k: a.get(k) for k in ("asset_type", "asset_uri", "status", "is_latest", "version")})
            if len(part) < 1000:
                break
    out = []
    for d in ds:
        m = d.get("metadata") or {}
        out.append({"id": d.get("dataset"), "title": m.get("title"), "coverage": m.get("geographic_coverage"),
                    "assets": assets.get(d.get("dataset"), [])})
    return out


def nusantara():
    out = {}
    for url in NUS:
        try:
            _, raw = get(f"{url}?service=WMS&request=GetCapabilities&version=1.3.0", 180)
        except Exception as e:  # noqa: BLE001
            out[url] = {"error": str(e)}
            continue
        root = ET.fromstring(raw)
        ns = {"w": "http://www.opengis.net/wms"}
        layers = []
        for l in root.iter("{http://www.opengis.net/wms}Layer"):
            name = l.find("w:Name", ns)
            if name is None:
                continue
            title = l.find("w:Title", ns)
            layers.append({"name": name.text, "title": title.text if title is not None else None,
                           "styles": [s.findtext("w:Name", namespaces=ns) for s in l.findall("w:Style", ns)]})
        out[url] = layers
    return out


def tries(gfw_rows):
    res = []
    for d in gfw_rows:
        if not WANT.search(f"{d['id']} {d.get('title') or ''}"):
            continue
        for a in d["assets"]:
            uri = a.get("asset_uri") or ""
            if not uri.startswith("http"):
                continue
            u = uri.replace("{z}", "3").replace("{x}", "5").replace("{y}", "3")
            try:
                st, body = get(u, 60)
                res.append({"id": d["id"], "title": d.get("title"), "type": a.get("asset_type"), "url": u, "status": st, "bytes": len(body)})
            except Exception as e:  # noqa: BLE001
                res.append({"id": d["id"], "title": d.get("title"), "type": a.get("asset_type"), "url": u, "error": str(e)[:200]})
            time.sleep(0.2)
    return res


def main():
    named = "catalogue_probe" in " ".join(sys.argv[1:]) or os.environ.get("CATALOGUE_PROBE")
    if (OUT / "gfw.json").exists() and not named and os.environ.get("GITHUB_EVENT_NAME", "schedule") == "schedule":
        print("catalogue_probe: already probed; name it in the refresh box to probe again")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    try:
        rows = gfw()
        (OUT / "gfw.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        print(f"catalogue_probe: {len(rows)} Global Forest Watch datasets")
    except Exception as e:  # noqa: BLE001
        print(f"catalogue_probe: Global Forest Watch did not answer ({e})")
    try:
        n = nusantara()
        (OUT / "nusantara.json").write_text(json.dumps(n, indent=1, ensure_ascii=False))
        print("catalogue_probe: Nusantara " + ", ".join(f"{k.split('/')[-2]}: {len(v) if isinstance(v, list) else v}" for k, v in n.items()))
    except Exception as e:  # noqa: BLE001
        print(f"catalogue_probe: Nusantara did not answer ({e})")
    if rows:
        t = tries(rows)
        (OUT / "tries.json").write_text(json.dumps(t, indent=1, ensure_ascii=False))
        print(f"catalogue_probe: {len(t)} tiles tried")


if __name__ == "__main__":
    main()
