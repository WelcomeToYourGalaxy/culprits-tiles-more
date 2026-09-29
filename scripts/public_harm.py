#!/usr/bin/env python3
"""
Public money behind the destruction of nature (round 100b, asked 28
September: in place of the Subsidising Extinction page, which only linked out
and whose data cannot be reused, the map's own rows from open records).

1. World Bank projects the Bank itself rated most harmful to the environment:
   environmental Category A (the Bank's OP 4.01: "likely to have significant
   adverse environmental impacts that are sensitive, diverse, or
   unprecedented"), and, for projects under its Environmental and Social
   Framework (2018 on), those rated High risk. Read from the World Bank's
   projects API (search.worldbank.org/api/v2/projects, CC BY 4.0), every
   project read and the rated ones kept, every field of each kept. Each is
   placed at every location the Bank's record gives; one with none is placed
   at its country's label point (Natural Earth, public domain) and says so.

     subsidies/wb_category_a.geojson   one point per project location
     subsidies/wb_build.json           counts, fields, what was read

2. The IMF's fossil fuel subsidies data, as the World Bank's Data360 serves it
   (dataset IMF_FFS): every indicator for every country and year. For the
   map's shading, each country's total subsidies as a share of GDP in its
   latest year; every other figure in its record.

     subsidies/imf_fossil_subsidies.json   ISO3 -> {value, unit, year, x_...}
     subsidies/imf_build.json              the indicators and their names

Weekly (Mondays) or by hand.
"""
import datetime, json, os, pathlib, re, sys, time, urllib.parse, urllib.request

OUT = pathlib.Path("subsidies")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)", "Accept": "application/json"}
WB = "https://search.worldbank.org/api/v2/projects"
WB_FIELDS = ["id", "project_name", "countryshortname", "countrycode", "countryname", "regionname", "totalcommamt", "totalamt",
             "boardapprovaldate", "closingdate", "status", "envassesmentcategorycode", "esrc_ovrl_risk_rate", "sector1", "sector",
             "mjsector_namecode", "theme_list", "impagency", "borrower", "lendinginstr", "url", "locations", "project_abstract"]
NE_COUNTRIES = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
D360 = "https://data360api.worldbank.org/data360"


def get(url, data=None, headers=None, timeout=180):
    last = None
    for i in range(4):
        try:
            req = urllib.request.Request(url, data=data, headers=dict(UA, **(headers or {})))
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"    {url[:120]}: {e}", flush=True)
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"no answer from {url[:120]} ({last})")


def flat(v):
    if isinstance(v, dict):
        if "cdata!" in v:
            return v["cdata!"]
        return "; ".join(f"{k}: {flat(x)}" for k, x in v.items() if x not in (None, "", [], {}))
    if isinstance(v, list):
        return "; ".join(flat(x) for x in v if x not in (None, "", [], {}))
    return v


def amount(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def rated(p):
    cat = str(p.get("envassesmentcategorycode") or "").strip().upper()
    risk = str(flat(p.get("esrc_ovrl_risk_rate")) or "").strip().lower()
    if cat == "A":
        return "Category A"
    if risk == "high":
        return "High risk (Environmental and Social Framework)"
    return None


def world_bank():
    labels = {}
    try:
        for f in json.loads(get(NE_COUNTRIES, timeout=300))["features"]:
            pr = f["properties"]
            for k in ("ISO_A2", "ISO_A2_EH", "WB_A2"):
                code = pr.get(k)
                if code and code != "-99" and pr.get("LABEL_X") is not None:
                    labels.setdefault(code, (pr["LABEL_X"], pr["LABEL_Y"]))
    except Exception as e:  # noqa: BLE001
        print(f"  Natural Earth's countries could not be read ({e}); projects with no location are left unplaced and counted", flush=True)
    feats, read, kept, placed_country, unplaced, fields = [], 0, 0, 0, 0, set()
    os_ = 0
    total = None
    while True:
        q = urllib.parse.urlencode({"format": "json", "rows": 500, "os": os_, "fl": ",".join(WB_FIELDS)})
        j = json.loads(get(f"{WB}?{q}", timeout=300))
        total = int(j.get("total") or 0)
        projects = j.get("projects") or {}
        if not projects:
            break
        for pid, p in projects.items():
            read += 1
            why = rated(p)
            if not why:
                continue
            kept += 1
            props = {k: flat(v) for k, v in p.items() if k != "locations" and v not in (None, "", [], {})}
            props["rated"] = why
            props["totalcommamt"] = amount(p.get("totalcommamt")) or amount(p.get("totalamt"))
            fields.update(props)
            locs = p.get("locations") or []
            pts = []
            for L in locs if isinstance(locs, list) else []:
                lat = amount(L.get("latitude")) if isinstance(L, dict) else None
                lon = amount(L.get("longitude")) if isinstance(L, dict) else None
                if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
                    pts.append((lon, lat, flat({k: v for k, v in L.items() if k not in ("latitude", "longitude")})))
            if pts:
                for lon, lat, where in pts:
                    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                                  "properties": dict(props, location=where, position="as the World Bank's record gives it")})
                continue
            codes = p.get("countrycode") or []
            codes = codes if isinstance(codes, list) else [codes]
            at = next((labels[c] for c in codes if c in labels), None)
            if at:
                placed_country += 1
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 4), round(at[1], 4)]},
                              "properties": dict(props, position="the middle of its country: the World Bank's record gives no location")})
            else:
                unplaced += 1
        os_ += 500
        print(f"  World Bank: {min(os_, total):,} of {total:,} projects read, {kept:,} rated", flush=True)
        if os_ >= total:
            break
        time.sleep(0.5)
    if not kept:
        raise RuntimeError(f"no rated project among {read:,} read; the fields may have changed ({sorted(fields)[:20]})")
    (OUT / "wb_category_a.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "wb_build.json").write_text(json.dumps({"read": read, "total_said": total, "rated": kept, "points": len(feats),
                                                   "placed_at_country": placed_country, "not_placed": unplaced,
                                                   "fields": sorted(fields), "date": datetime.date.today().isoformat()}, indent=1))
    print(f"  World Bank: {kept:,} rated projects, {len(feats):,} points ({placed_country} at their country, {unplaced} not placed)", flush=True)


def d360_names(codes):
    names = {}
    for c in codes:
        try:
            body = json.dumps({"search": c, "top": 5, "select": "series_description/idno, series_description/name, series_description/definition_long"}).encode()
            j = json.loads(get(f"{D360}/searchv2", data=body, headers={"Content-Type": "application/json"}, timeout=60))
            for v in j.get("value", []):
                sd = v.get("series_description") or {}
                if sd.get("idno") == c:
                    names[c] = sd.get("name") or c
        except Exception as e:  # noqa: BLE001
            print(f"    Data360 name of {c}: {e}", flush=True)
    return names


def imf():
    codes = json.loads(get(f"{D360}/indicators?datasetId=IMF_FFS"))
    codes = [c if isinstance(c, str) else c.get("idno") or c.get("id") for c in (codes if isinstance(codes, list) else codes.get("value", []))]
    codes = [c for c in codes if c]
    names = d360_names(codes)
    print(f"  IMF: {len(codes)} indicators; names {names}", flush=True)
    rows = []
    for c in codes:
        skip = 0
        while True:
            q = urllib.parse.urlencode({"DATABASE_ID": "IMF_FFS", "INDICATOR": c, "skip": skip, "top": 1000})
            j = json.loads(get(f"{D360}/data?{q}"))
            vals = j.get("value", [])
            rows += vals
            skip += len(vals)
            if not vals or skip >= int(j.get("count") or 0):
                break
    out = {}
    for r in rows:
        iso, c, y, u = r.get("REF_AREA"), r.get("INDICATOR"), r.get("TIME_PERIOD"), r.get("UNIT_MEASURE")
        v = amount(r.get("OBS_VALUE"))
        if not iso or v is None or not re.fullmatch(r"[A-Z]{3}", iso):
            continue
        rec = out.setdefault(iso, {})
        label = f"{names.get(c, c)} ({u})"
        best = rec.get(label)
        if not best or str(y) > best[0]:
            rec[label] = (str(y), v)
        if c == "IMF_FFS_ECGFT" and u == "PT_GDP" and ("_y" not in rec or str(y) > rec["_y"]):
            rec["_y"], rec["_v"] = str(y), v
    final = {}
    for iso, rec in out.items():
        if "_v" not in rec:
            continue
        f = {"value": rec["_v"], "unit": "% of GDP", "year": rec["_y"]}
        for k, (y, v) in sorted(rec.items()):
            if k.startswith("_"):
                continue
            f[f"x_{k}, {y}"] = v
        final[iso] = f
    if not final:
        raise RuntimeError("no country has the total as a share of GDP (IMF_FFS_ECGFT, PT_GDP)")
    (OUT / "imf_fossil_subsidies.json").write_text(json.dumps(final, indent=1, ensure_ascii=False))
    (OUT / "imf_build.json").write_text(json.dumps({"indicators": codes, "names": names, "rows": len(rows), "countries": len(final),
                                                    "date": datetime.date.today().isoformat()}, indent=1))
    print(f"  IMF: {len(final)} countries", flush=True)


def main():
    stamp = OUT / "wb_build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("public_harm: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    failed = []
    for name, job in (("World Bank", world_bank), ("IMF", imf)):
        try:
            job()
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name}: {type(e).__name__}: {e}")
            print(f"public_harm: {name} not built ({e})", flush=True)
    if failed:
        sys.exit("public_harm: " + "; ".join(failed))


if __name__ == "__main__":
    main()
