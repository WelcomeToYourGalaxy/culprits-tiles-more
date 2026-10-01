#!/usr/bin/env python3
"""
Homicides, worldwide (round 119b, asked 30 September 2026: "a global layer of
homicides, preferably cases as points over national highlights. If none
exists, do best to compile multiple").

No source publishes every homicide in the world as a place. This compiles
what is open, each in its own file, every field each source gives kept:

  homicides/countries.json   every country's intentional homicide rate per
                             100,000 people, every year the World Bank gives
                             (indicator VC.IHR.PSRC.P5, from UNODC's figures;
                             CC BY 4.0), with the latest year as "rate"
  homicides/wikidata.geojson murders recorded in Wikidata with a place (CC0):
                             notable cases only, not a count
  homicides/colombia.geojson every homicide Colombia's police record, day by
                             day since 2010 (Ministry of Defence open data,
                             CC BY-SA 4.0), counted at each town's centre
                             (DANE's own town list), by year, weapon, motive
                             and sex
  tiles/homicide_cases.pmtiles (and parts)  each case as a point:
                             every homicide in Chicago's crime records since
                             2001, at its block (City of Chicago open data);
                             criminal homicides, Los Angeles, 2020 to 2024
                             (LAPD, CC0); murders and non-negligent
                             manslaughters, New York City, 2006 on (NYPD
                             complaint records); 52,000 criminal homicides in
                             50 large US cities, about 2007 to 2017, with
                             whether anyone was arrested (The Washington Post,
                             CC BY-NC-SA 4.0). The Post's cities overlap the
                             three cities' own records for those years; each
                             source is its own colour, nothing is merged.
  homicides/build.json       what was read, counts, and what could not be

Weekly (Mondays) or by hand.
"""
import csv, datetime, io, json, os, pathlib, sys, time, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import wdtools  # noqa: E402

OUT = pathlib.Path("homicides")
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
WB = "https://api.worldbank.org/v2/country/all/indicator/VC.IHR.PSRC.P5?format=json&per_page=20000"
WB_COUNTRIES = "https://api.worldbank.org/v2/country?format=json&per_page=400"
WAPO = "https://raw.githubusercontent.com/washingtonpost/data-homicides/master/homicide-data.csv"
CHICAGO = "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
LA = "https://data.lacity.org/resource/2nrs-mtv8.json"
NYC_HIST = "https://data.cityofnewyork.us/resource/qgea-i56i.json"
NYC_NOW = "https://data.cityofnewyork.us/resource/5uac-w243.json"
COL = "https://www.datos.gov.co/resource/m8fd-ahd9.json"
COL_TOWNS = "https://www.datos.gov.co/resource/gdxc-w37w.json"
TILE = pathlib.Path("tiles/homicide_cases.pmtiles")
CASES = []                      # the case-by-case points, built into TILE at the end


def get(url, timeout=300):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def socrata(base, where=None, select=None, page=50000, most=2000000):
    rows, off = [], 0
    while off < most:
        q = {"$limit": page, "$offset": off, "$order": ":id"}
        if where:
            q["$where"] = where
        if select:
            q["$select"] = select
        got = json.loads(get(base + "?" + urllib.parse.urlencode(q)))
        rows += got
        if len(got) < page:
            break
        off += page
        time.sleep(1)
    return rows


def fc(feats, source, licence):
    return {"type": "FeatureCollection", "source": source, "licence": licence, "features": feats}


def pt(lon, lat, props):
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90) or (lon == 0 and lat == 0):
        return None
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}, "properties": props}


def clean(d):
    return {k: v for k, v in d.items() if v not in (None, "") and not k.startswith(":@")}


def countries(status):
    meta = json.loads(get(WB_COUNTRIES))[1]
    real = {c["id"] for c in meta if (c.get("region") or {}).get("value") != "Aggregates"}
    rows = json.loads(get(WB))[1]
    out = {}
    for r in rows:
        iso = r.get("countryiso3code")
        if not iso or iso not in real or r.get("value") is None:
            continue
        rec = out.setdefault(iso, {"country": r["country"]["value"]})
        rec[f"x_rate per 100,000, {r['date']}"] = round(r["value"], 2)
        if "year" not in rec or int(r["date"]) > int(rec["year"]):
            rec["rate"], rec["year"] = round(r["value"], 2), int(r["date"])
    (OUT / "countries.json").write_text(json.dumps(out, ensure_ascii=False, indent=0))
    status["countries"] = len(out)


def wikidata(status):
    q = """
SELECT ?item ?itemLabel ?itemDescription ?date ?start ?coord ?placeLabel ?countryLabel ?deaths ?article
       (GROUP_CONCAT(DISTINCT ?victimLabel; separator="; ") AS ?victims)
       (GROUP_CONCAT(DISTINCT ?perpLabel; separator="; ") AS ?perpetrators)
       (GROUP_CONCAT(DISTINCT ?kindLabel; separator="; ") AS ?kinds) WHERE {
  ?item wdt:P31 ?kind . ?kind wdt:P279* wd:Q132821 .
  { ?item wdt:P625 ?coord } UNION { ?item wdt:P276 ?place . ?place wdt:P625 ?coord }
  OPTIONAL { ?item wdt:P585 ?date } OPTIONAL { ?item wdt:P580 ?start }
  OPTIONAL { ?item wdt:P17 ?country } OPTIONAL { ?item wdt:P276 ?place }
  OPTIONAL { ?item wdt:P1120 ?deaths }
  OPTIONAL { ?item wdt:P8032 ?victim . ?victim rdfs:label ?victimLabel . FILTER(LANG(?victimLabel) = "en") }
  OPTIONAL { ?item wdt:P8031 ?perp . ?perp rdfs:label ?perpLabel . FILTER(LANG(?perpLabel) = "en") }
  OPTIONAL { ?kind rdfs:label ?kindLabel . FILTER(LANG(?kindLabel) = "en") }
  OPTIONAL { ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,es,fr,de,pt,ru,ar,zh". }
} GROUP BY ?item ?itemLabel ?itemDescription ?date ?start ?coord ?placeLabel ?countryLabel ?deaths ?article"""
    rows = wdtools.sparql(q)
    seen, feats = set(), []
    for b in rows:
        item = wdtools.v(b, "item")
        if item in seen:
            continue
        at = wdtools.point(wdtools.v(b, "coord"))
        if not at:
            continue
        seen.add(item)
        date = (wdtools.v(b, "date") or wdtools.v(b, "start"))[:10]
        f = pt(at[0], at[1], clean({
            "name": wdtools.v(b, "itemLabel"), "what it is": wdtools.v(b, "itemDescription"), "kind": wdtools.v(b, "kinds"),
            "date": date, "year": int(date[:4]) if date[:4].isdigit() else None, "place": wdtools.v(b, "placeLabel"),
            "country": wdtools.v(b, "countryLabel"), "deaths": wdtools.v(b, "deaths"), "victims": wdtools.v(b, "victims"),
            "perpetrators": wdtools.v(b, "perpetrators"), "Wikipedia": wdtools.v(b, "article"), "Wikidata": item,
            "group": "Recorded in Wikidata", "source": "Wikidata (CC0): items that are murders or a kind of murder, with a place"}))
        if f:
            feats.append(f)
    (OUT / "wikidata.geojson").write_text(json.dumps(fc(feats, "Wikidata", "CC0"), ensure_ascii=False, separators=(",", ":")))
    status["wikidata"] = len(feats)


def colombia(status):
    towns = {}
    for t in socrata(COL_TOWNS, page=5000):
        try:
            towns[t["cod_mpio"]] = (float(t["longitud"].replace(",", ".")), float(t["latitud"].replace(",", ".")), t.get("nom_mpio"), t.get("dpto"))
        except (KeyError, ValueError, AttributeError):
            continue
    rows = socrata(COL, page=50000)
    by = {}
    for r in rows:
        code = r.get("cod_muni")
        n = int(float(r.get("cantidad") or 1))
        e = by.setdefault(code, {"n": 0, "years": {}, "weapon": {}, "motive": {}, "sex": {}, "zone": {}, "first": None, "last": None,
                                 "town": r.get("municipio"), "dept": r.get("departamento")})
        e["n"] += n
        d = (r.get("fecha_hecho") or "")[:10]
        if d:
            e["years"][d[:4]] = e["years"].get(d[:4], 0) + n
            e["first"] = min(e["first"] or d, d)
            e["last"] = max(e["last"] or d, d)
        for k, f in (("weapon", "arma_medio"), ("motive", "_modalidad_presunta"), ("sex", "sexo"), ("zone", "zona")):
            v = (r.get(f) or "NO REPORTADO").strip()
            e[k][v] = e[k].get(v, 0) + n
    feats, unplaced = [], 0
    for code, e in by.items():
        t = towns.get(code)
        if not t:
            unplaced += e["n"]
            continue
        top = lambda dct: "; ".join(f"{k.capitalize()}: {v:,}" for k, v in sorted(dct.items(), key=lambda kv: -kv[1]))
        props = {"name": f"{(t[2] or e['town'] or '').title()}, {(t[3] or e['dept'] or '').title()}", "homicides": e["n"],
                 "first recorded": e["first"], "latest recorded": e["last"], "by weapon (as the police word it)": top(e["weapon"]),
                 "by presumed motive (as the police word it)": top(e["motive"]), "by sex": top(e["sex"]), "urban or rural": top(e["zone"]),
                 "group": "Colombia: counted at each town", "DANE town code": code,
                 "source": "Ministry of Defence of Colombia, HOMICIDIO (datos.gov.co m8fd-ahd9, CC BY-SA 4.0); town centres from DANE's list (gdxc-w37w)"}
        for y, v in sorted(e["years"].items()):
            props[f"x_homicides {y}"] = v
        f = pt(t[0], t[1], props)
        if f:
            feats.append(f)
    (OUT / "colombia.geojson").write_text(json.dumps(fc(feats, COL, "CC BY-SA 4.0"), ensure_ascii=False, separators=(",", ":")))
    status["colombia"] = {"towns": len(feats), "records read": len(rows), "homicides not placed (town code not in DANE's list)": unplaced}


def chicago(status):
    rows = socrata(CHICAGO, where="primary_type='HOMICIDE'", select="id,case_number,date,block,description,location_description,arrest,domestic,year,latitude,longitude")
    feats = [f for f in (pt(r.get("longitude"), r.get("latitude"), clean(dict(
        {k: v for k, v in r.items() if k not in ("latitude", "longitude")}, name=f"Homicide, {r.get('block', '')}".strip(", "),
        group="Chicago", source="City of Chicago, Crimes - 2001 to Present (ijzp-q8t2), primary type HOMICIDE, at the block"))) for r in rows) if f]
    CASES.extend(feats)
    status["chicago"] = len(feats)


def los_angeles(status):
    rows = socrata(LA, where="crm_cd='110'")
    feats = [f for f in (pt(r.get("lon"), r.get("lat"), clean(dict(
        {k: v for k, v in r.items() if k not in ("lat", "lon")}, name=f"Criminal homicide, {r.get('location', '').strip()}".strip(", "),
        group="Los Angeles", source="Los Angeles Police Department, Crime Data from 2020 to Present (2nrs-mtv8), crime code 110, CC0"))) for r in rows) if f]
    CASES.extend(feats)
    status["los_angeles"] = len(feats)


def new_york(status):
    feats, got = [], {}
    for base in (NYC_HIST, NYC_NOW):
        try:
            rows = socrata(base, where="ofns_desc='MURDER & NON-NEGL. MANSLAUGHTER'")
        except Exception as e:  # noqa: BLE001
            got[base] = f"not read: {e}"
            continue
        got[base] = len(rows)
        for r in rows:
            f = pt(r.get("longitude"), r.get("latitude"), clean(dict(
                {k: v for k, v in r.items() if k not in ("latitude", "longitude", "lat_lon", "geocoded_column")},
                name=f"Murder or non-negligent manslaughter, {r.get('boro_nm', '').title()}".strip(", "),
                group="New York City", source=f"New York Police Department complaint records ({base.rsplit('/', 1)[-1].replace('.json', '')})")))
            if f:
                feats.append(f)
    CASES.extend(feats)
    status["new_york"] = {"placed": len(feats), "read": got}


def wapo(status):
    text = get(WAPO).decode("latin-1")
    feats = []
    for r in csv.DictReader(io.StringIO(text)):
        d = r.get("reported_date") or ""
        date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
        props = clean({"name": f"{r.get('victim_first', '').title()} {r.get('victim_last', '').title()}".strip() or "Unnamed victim",
                       "reported": date, "year": int(d[:4]) if d[:4].isdigit() else None, "city": r.get("city"), "state": r.get("state"),
                       "victim age": r.get("victim_age"), "victim sex": r.get("victim_sex"), "victim race (as the Post records it)": r.get("victim_race"),
                       "case status": r.get("disposition"), "Post's id": r.get("uid"), "group": "50 US cities (The Washington Post)",
                       "source": "The Washington Post, data-homicides (CC BY-NC-SA 4.0)"})
        f = pt(r.get("lon"), r.get("lat"), props)
        if f:
            feats.append(f)
    CASES.extend(feats)
    status["washington_post"] = len(feats)


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("homicides: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    status, failed = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}, []
    for name, job in (("countries", countries), ("wikidata", wikidata), ("colombia", colombia), ("chicago", chicago),
                      ("los_angeles", los_angeles), ("new_york", new_york), ("washington_post", wapo)):
        try:
            job(status)
            print(f"homicides: {name}: {status.get(name)}", flush=True)
        except Exception as e:  # noqa: BLE001
            status[name] = f"not read: {type(e).__name__}: {e}"
            failed.append(name)
            print(f"homicides: {name}: {e}", flush=True)
    if CASES:
        # Too many for one file the browser reads whole (the Post's alone is
        # 23 MB): map archives, one mark per square wide out, each case close in.
        import pointtiles
        pts = [(f["geometry"]["coordinates"][0], f["geometry"]["coordinates"][1], f["properties"]) for f in CASES]
        parts = pointtiles.build(pts, TILE, "homicides", "group",
                                 attribution="The Washington Post (CC BY-NC-SA 4.0); City of Chicago; LAPD (CC0); NYPD")
        by = {}
        for _, _, p in pts:
            by[p.get("group")] = by.get(p.get("group"), 0) + 1
        TILE.with_suffix(".build.json").write_text(json.dumps({"layer": "homicides", "places": len(pts), "detail_from": 8, "groups": by,
                                                               "parts": parts, "date": datetime.date.today().isoformat()}, indent=1))
        status["case archive"] = {"points": len(pts), "files": len(parts)}
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    if len(failed) == 7:
        sys.exit("homicides: nothing could be read")


if __name__ == "__main__":
    main()
