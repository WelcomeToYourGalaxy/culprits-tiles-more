#!/usr/bin/env python3
"""
Who and what is behind the most methane (round 120b, asked 1 October 2026:
"a resource covering the biggest culprits behind methane emissions worldwide").

  methane/imeo_plumes.geojson   every methane plume seen by satellite and
                                reported to governments by the UN Environment
                                Programme's International Methane Emissions
                                Observatory (its Methane Alert and Response
                                System), with sector, country and the rate of
                                each (CC BY-NC-SA 4.0); the source names no
                                operator
  methane/imeo_top50.geojson    UNEP IMEO's monthly list of the 50 largest
                                emitting sites it sees
  methane/ct_owned_sites.geojson  every methane-emitting site Climate TRACE
                                names an owner for, with its methane (tonnes a
                                year) and owners
  methane/ct_owners.json        those owners ranked by the methane of the
                                sites they own (shares weighted where given)
  methane/build.json            what was read and what could not be

Weekly (Mondays) or by hand.
"""
import csv, datetime, io, json, os, pathlib, sys, time, urllib.parse, urllib.request, zipfile

OUT = pathlib.Path("methane")
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
IMEO_PLUMES = "https://unepazeconomyadlsstorage.blob.core.windows.net/public/unep_methanedata_detected_plumes_geojson.zip"
IMEO_TOP50 = "https://methanedata.unep.org/downloads/top50_emitters/latest/unep_methanedata_topemitter_sources.zip"
CT_ASSETS = "https://api.climatetrace.org/v6/assets"
TOP_OWNERS = 20


def get(url, timeout=600):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def feats_from_zip(body, group_keys):
    """A zip's GeoJSON features, or its CSV rows with a latitude and longitude."""
    z = zipfile.ZipFile(io.BytesIO(body))
    feats = []
    for n in z.namelist():
        low = n.lower()
        if low.endswith((".geojson", ".json")):
            d = json.loads(z.read(n))
            feats += d.get("features") or []
        elif low.endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(z.read(n).decode("utf-8-sig", "replace"))))
            for r in rows:
                lat = next((num(r[k]) for k in r if k and k.lower() in ("lat", "latitude", "source_lat", "plume_lat")), None)
                lon = next((num(r[k]) for k in r if k and k.lower() in ("lon", "lng", "longitude", "source_lon", "plume_lon")), None)
                if lat is None or lon is None:
                    continue
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": dict(r)})
    for f in feats:
        p = f.setdefault("properties", {})
        g = next((p[k] for k in group_keys if p.get(k)), None)
        p["group"] = str(g).replace("_", " ").capitalize() if g else "Sector not given"
    return feats


def imeo(status):
    for key, url, name in (("plumes", IMEO_PLUMES, "imeo_plumes"), ("top50", IMEO_TOP50, "imeo_top50")):
        try:
            feats = feats_from_zip(get(url), ["sector", "Sector", "source_sector"])
            (OUT / f"{name}.geojson").write_text(json.dumps({"type": "FeatureCollection", "source": url, "licence": "CC BY-NC-SA 4.0 (UNEP IMEO)",
                                                             "features": feats}, ensure_ascii=False, separators=(",", ":")))
            status[key] = len(feats)
        except Exception as e:  # noqa: BLE001
            status[key] = f"not read: {type(e).__name__}: {e}"


def owner_list(o):
    """Climate TRACE's owners of a site, as [(name, share or None)], whatever shape it gives them in."""
    out = []
    for x in (o if isinstance(o, list) else [o] if o else []):
        if isinstance(x, str):
            out.append((x, None))
        elif isinstance(x, dict):
            name = next((x[k] for k in ("CompanyName", "Name", "name", "OwnerName", "EntityName", "company_name") if x.get(k)), None)
            share = next((num(x[k]) for k in ("PercentInterest", "Percentage", "percent", "Share", "OwnershipPercentage") if x.get(k) is not None), None)
            if name:
                out.append((str(name), share))
    return out


def climate_trace(status):
    feats, owners, pages, seen = [], {}, 0, set()
    off = 0
    while pages < 400:
        q = urllib.parse.urlencode({"gas": "ch4", "limit": 1000, "offset": off})
        got = json.loads(get(f"{CT_ASSETS}?{q}", 300))
        assets = got if isinstance(got, list) else (got.get("assets") or got.get("data") or [])
        if not assets:
            break
        pages += 1
        off += len(assets)
        for a in assets:
            if a.get("Id") in seen:
                continue
            seen.add(a.get("Id"))
            ch4 = sum((num(e.get("EmissionsQuantity")) or 0) for e in (a.get("EmissionsSummary") or []) if str(e.get("Gas", "")).lower() == "ch4")
            own = owner_list(a.get("Owners"))
            if not own or not ch4:
                continue
            c = a.get("Centroid") or {}
            g = c.get("Geometry") or c.get("coordinates") or c.get("geometry")
            if isinstance(g, dict):
                g = g.get("coordinates")
            if not (isinstance(g, list) and len(g) >= 2):
                continue
            for name, share in own:
                o = owners.setdefault(name, {"methane, tonnes a year (shares weighted where given)": 0.0, "sites": 0})
                o["methane, tonnes a year (shares weighted where given)"] += ch4 * (share / 100 if share and share > 1 else share if share else 1)
                o["sites"] += 1
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(g[0]), float(g[1])]},
                          "properties": {"name": a.get("Name"), "sector": a.get("Sector"), "country": a.get("Country"),
                                         "methane, tonnes a year": round(ch4, 1),
                                         "owners": "; ".join(f"{n}{f' ({s:g}%)' if s else ''}" for n, s in own),
                                         "_owners": [n for n, _ in own], "Climate TRACE id": a.get("Id")}})
        time.sleep(1)
    ranked = sorted(owners.items(), key=lambda kv: -kv[1]["methane, tonnes a year (shares weighted where given)"])
    top = [n for n, _ in ranked[:TOP_OWNERS]]
    for f in feats:
        p = f["properties"]
        mine = [n for n in p.pop("_owners") if n in top]
        p["group"] = min(mine, key=top.index) if mine else "Other owners"
    (OUT / "ct_owned_sites.geojson").write_text(json.dumps({"type": "FeatureCollection", "source": CT_ASSETS, "licence": "Climate TRACE (CC BY 4.0)",
                                                            "features": feats}, ensure_ascii=False, separators=(",", ":")))
    (OUT / "ct_owners.json").write_text(json.dumps([dict(v, owner=n, rank=i + 1) for i, (n, v) in enumerate(ranked)], ensure_ascii=False, indent=0))
    status["climate_trace"] = {"pages": pages, "sites with an owner": len(feats), "owners": len(owners), "top owners": top}


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("methane_culprits: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    status = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    imeo(status)
    try:
        climate_trace(status)
    except Exception as e:  # noqa: BLE001
        status["climate_trace"] = f"not read: {type(e).__name__}: {e}"
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print("methane_culprits:", json.dumps(status, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
