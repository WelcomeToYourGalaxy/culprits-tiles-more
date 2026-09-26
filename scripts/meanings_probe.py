#!/usr/bin/env python3
"""
What the publishers themselves say a number or a code name means, fetched
from their own servers (which the chat's sandbox cannot reach), written to

  probe/gfw/            Global Forest Watch: the layer settings (legend names
                        and colours) its website draws the Wageningen alert
                        drivers and the older loss-driver layers with, and the
                        Data API's records for those datasets
  probe/nusantara/      Nusantara Atlas: what its two map servers say about
                        concessioncma_spv, millopbufferol_spv,
                        millopbufferpolyloreal_spv and millopbufferollor_spv
                        (titles, abstracts, legend rules, column names, and
                        every value each column holds, with counts)
  probe/summary.txt     what came back and what did not, in plain words

Nothing here is drawn on the map. It is read by a person, who decides whether
it names the numbers well enough to use (HANDOFF_COULDNT_GET.md, items 1, 4
and 5). A request that fails is written down, never retried in a loop.

Runs only when asked by name from the Actions tab (meanings_probe), not on the
daily schedule.
"""
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

OUT = pathlib.Path("probe")
UA = {"User-Agent": "Mozilla/5.0 (welcometoyourgalaxy culprits atlas; one-off look-up)"}
LOG = []

# The map draws the Wageningen drivers from the datasets named with _class and
# _date (the first run asked for the bare name, which does not exist: 404).
GFW_DATASETS = ["wur_integration_alert_drivers_class", "wur_integration_alert_drivers_date",
                "tsc_tree_cover_loss_drivers", "tsc_drivers", "umd_drivers"]
# Text that marks a Resource Watch layer as one of these (the website's own
# colouring code for the alert drivers is named alertDriversEncoded).
GFW_MARKS = re.compile(r"alertDriversEncoded|wur_integration_alert_drivers|alert.?drivers|tsc_tree_cover_loss_drivers|tsc_drivers|umd_drivers", re.I)

NUSANTARA_LAYERS = ["concessioncma_spv", "millopbufferol_spv", "millopbufferpolyloreal_spv", "millopbufferollor_spv"]
NUSANTARA_SERVERS = {
    "v2": {"ows": "https://map.nusantara-atlas.org/geoserver/atlas-workspace-v2/ows", "ws": "atlas-workspace-v2"},
    "v3": {"ows": "https://server1.nusantara-atlas.org/geoserver/ows", "ws": "atlas-workspace-v3"},
}
DISTINCT_CAP = 500     # values listed per column; the count of all values is always given


def say(line):
    print(line)
    LOG.append(line)


def get(url, params=None, timeout=120):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body = e.read()[:400].decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code}: {' '.join(body.split())[:300]}") from None


def get_json(url, params=None, timeout=120):
    raw, _ = get(url, params, timeout)
    return json.loads(raw)


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (bytes, str)):
        path.write_bytes(obj if isinstance(obj, bytes) else obj.encode())
    else:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=1))


def attempt(label, fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        say(f"  {label}: did not come ({e.__class__.__name__}: {str(e)[:160]})")
        return None


# ---------- Global Forest Watch ----------

def gfw():
    d = OUT / "gfw"
    say("Global Forest Watch")
    for ds in GFW_DATASETS:
        rec = attempt(f"Data API record {ds}", lambda: get_json(f"https://data-api.globalforestwatch.org/dataset/{ds}"))
        if rec is None:
            continue
        write(d / f"data_api_{ds}.json", rec)
        versions = (rec.get("data") or {}).get("versions") or []
        say(f"  Data API {ds}: record saved; versions {versions[-5:]}")
        if versions:
            v = versions[-1]
            for part in ("", "/assets", "/fields"):
                got = attempt(f"{ds} {v}{part}", lambda p=part: get_json(f"https://data-api.globalforestwatch.org/dataset/{ds}/{v}{p}"))
                if got is not None:
                    write(d / f"data_api_{ds}_{v}{part.replace('/', '_')}.json", got)
                    text = json.dumps(got)
                    if part == "/assets":
                        for a in got.get("data") or []:
                            for b in ((a.get("metadata") or {}).get("bands") or []):
                                if b.get("values_table"):
                                    say(f"  {ds} {v}: {a.get('asset_type')} band '{b.get('pixel_meaning')}' carries a values table: "
                                        + "; ".join(f"{r.get('value')} = {r.get('meaning')}" for r in b["values_table"].get("rows", [])))
                    if "values_table" in text:
                        tables = re.findall(r'"values_table": (\{.*?\}|null)', text)
                        say(f"  {ds} {v}{part}: values_table present {len([t for t in tables if t != 'null'])} time(s) with content")
    # Resource Watch holds the layer settings GFW's website draws with,
    # including each layer's legend (colour and name per item).
    hits, page = [], 1
    while page <= 30:
        got = attempt(f"Resource Watch layers page {page}", lambda: get_json(
            "https://api.resourcewatch.org/v1/layer", {"application": "gfw", "env": "production", "page[size]": 500, "page[number]": page}, 180))
        if not got or not got.get("data"):
            break
        for layer in got["data"]:
            if GFW_MARKS.search(json.dumps(layer)):
                hits.append(layer)
        if len(got["data"]) < 500:
            break
        page += 1
    write(d / "resourcewatch_layers.json", hits)
    say(f"  Resource Watch: {len(hits)} GFW layer(s) mention the drivers datasets")
    for layer in hits:
        a = layer.get("attributes", {})
        items = ((a.get("legendConfig") or {}).get("items")) or []
        say(f"    {a.get('name')} (layer {layer.get('id')}, dataset {a.get('dataset')}): legend of {len(items)} item(s)")
        for it in items:
            say(f"      {it.get('color')}  {it.get('name')}" + (f"  value {it.get('value')}" if 'value' in it else ""))
        ds_id = a.get("dataset")
        if ds_id:
            got = attempt(f"dataset {ds_id}", lambda: get_json(f"https://api.resourcewatch.org/v1/dataset/{ds_id}", {"includes": "metadata,layer"}))
            if got is not None:
                write(d / f"resourcewatch_dataset_{ds_id}.json", got)


# ---------- Nusantara Atlas ----------

def local(tag):
    return tag.rsplit("}", 1)[-1]


def wms_layers(xml_bytes, wanted):
    """Name, title, abstract, keywords and styles of each wanted layer in a WMS capabilities document."""
    out = {}
    root = ET.fromstring(xml_bytes)
    for el in root.iter():
        if local(el.tag) != "Layer":
            continue
        kids = {local(c.tag): c for c in el}
        name = (kids["Name"].text or "") if "Name" in kids else ""
        short = name.split(":")[-1]
        if short not in wanted:
            continue
        styles = []
        for c in el:
            if local(c.tag) == "Style":
                s = {local(x.tag): (x.text or "").strip() for x in c if local(x.tag) in ("Name", "Title", "Abstract")}
                styles.append(s)
        out.setdefault(short, []).append({
            "name": name,
            "title": (kids["Title"].text or "").strip() if "Title" in kids else "",
            "abstract": (kids["Abstract"].text or "").strip() if "Abstract" in kids else "",
            "keywords": [(k.text or "").strip() for k in el.iter() if local(k.tag) == "Keyword"],
            "styles": styles,
        })
    return out


def summarise_features(features):
    cols = {}
    for f in features:
        for k, v in (f.get("properties") or {}).items():
            c = cols.setdefault(k, {})
            key = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            c[key] = c.get(key, 0) + 1
    return {k: {"distinct": len(v), "values": dict(sorted(v.items(), key=lambda kv: -kv[1])[:DISTINCT_CAP])} for k, v in cols.items()}


def nusantara():
    d = OUT / "nusantara"
    say("Nusantara Atlas")
    for tag, srv in NUSANTARA_SERVERS.items():
        caps = attempt(f"{tag} WMS capabilities", lambda: get(srv["ows"], {"service": "WMS", "request": "GetCapabilities"}, 180)[0])
        if caps:
            found = attempt(f"{tag} reading capabilities", lambda: wms_layers(caps, set(NUSANTARA_LAYERS))) or {}
            write(d / f"{tag}_wms_layers.json", found)
            for lname in NUSANTARA_LAYERS:
                for rec in found.get(lname, []):
                    say(f"  {tag} {lname}: title '{rec['title']}', abstract '{rec['abstract'][:200]}', styles {[s.get('Title') or s.get('Name') for s in rec['styles']]}")
                if lname not in found:
                    say(f"  {tag} {lname}: not listed by this server's map service")
        for lname in NUSANTARA_LAYERS:
            full = f"{srv['ws']}:{lname}"
            leg = attempt(f"{tag} {lname} legend", lambda: get_json(srv["ows"], {
                "service": "WMS", "version": "1.1.1", "request": "GetLegendGraphic", "format": "application/json", "layer": full}))
            if leg is not None:
                write(d / f"{tag}_{lname}_legend.json", leg)
                rules = [r.get("title") or r.get("name") for lg in leg.get("Legend", []) for r in lg.get("rules", [])]
                say(f"  {tag} {lname}: legend rules {rules}")
            schema = attempt(f"{tag} {lname} columns", lambda: get_json(srv["ows"], {
                "service": "WFS", "version": "2.0.0", "request": "DescribeFeatureType", "typeNames": full, "outputFormat": "application/json"}))
            if schema is not None:
                write(d / f"{tag}_{lname}_columns.json", schema)
            # Paging in WFS 2.0 needs a sort order; the first column that is an
            # id is used (objectid, ogc_fid).
            props = [q.get("name") for ft in (schema or {}).get("featureTypes", []) for q in ft.get("properties", [])]
            sort = next((c for c in ("objectid", "ogc_fid", "fid", "id", "cid") if c in props), None)
            feats, start = [], 0
            while start < 2_000_000:
                q = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": full,
                     "outputFormat": "application/json", "count": 5000, "startIndex": start}
                if sort:
                    q["sortBy"] = sort
                page = attempt(f"{tag} {lname} features from {start}", lambda q=q: get_json(srv["ows"], q, 300))
                if page is None and start == 0:
                    # WFS 1.0: no paging, every feature at once.
                    page = attempt(f"{tag} {lname} features (WFS 1.0)", lambda: get_json(srv["ows"], {
                        "service": "WFS", "version": "1.0.0", "request": "GetFeature", "typeName": full,
                        "outputFormat": "application/json"}, 600))
                    if page:
                        feats.extend(page.get("features") or [])
                        break
                if not page:
                    break
                got = page.get("features") or []
                feats.extend(got)
                if len(got) < 5000:
                    break
                start += 5000
            if feats:
                summary = {"features": len(feats), "geometry": sorted({(f.get("geometry") or {}).get("type", "none") for f in feats}),
                           "columns": summarise_features(feats)}
                write(d / f"{tag}_{lname}_values.json", summary)
                say(f"  {tag} {lname}: {len(feats)} features; columns {list(summary['columns'])}")


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("meanings_probe: runs only when asked by name")
        return
    OUT.mkdir(exist_ok=True)
    attempt("Global Forest Watch", gfw)
    attempt("Nusantara Atlas", nusantara)
    write(OUT / "summary.txt", "\n".join(LOG) + "\n")
    print(f"wrote {OUT}/")


if __name__ == "__main__":
    sys.exit(main())
