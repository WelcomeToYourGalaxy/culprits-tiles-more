#!/usr/bin/env python3
"""
Plastic production worldwide, and vinyl chloride, from public registers and open
maps (round 81, asked 27 September). No open worldwide list of plastics plants
exists (the industry's own, such as Polyglobe, are sold by subscription), so the
Culprits map's two rows are built here from the sources that do publish plant
locations, each record kept whole and labelled with where it came from:

  plastics/plants.geojson          plants that make plastic or its building blocks
  plastics/vinyl_chloride.geojson  plants that make or release vinyl chloride (the
                                   gas PVC is made from)
  plastics/status.json             what each source gave on the last run

Sources, each tried on its own; one that does not answer keeps its records
from the last copy:

  us_tri     US EPA Toxics Release Inventory, the latest year published (public
             domain): facilities whose main activity is NAICS 325211, "Plastics
             Material and Resin Manufacturing", with every chemical they report
             and their releases; and every facility reporting vinyl chloride
             (CAS 75-01-4), with its releases of it.
  eu_prtr    The EU's industrial emissions register (E-PRTR, European
             Environment Agency; reuse allowed with the source named):
             installations whose main activity is Annex I 4(a)(viii), "basic
             plastic materials (polymers, synthetic fibres and cellulose-based
             fibres)", and every facility reporting vinyl chloride releases.
             Read through the EEA's DISCODATA service; its tables are found by
             their columns on each run, since their names change by release.
  ct_crack   Climate TRACE (CC BY 4.0), petrochemical steam cracking: the
             ethylene and propylene crackers that make the building blocks of
             polyethylene, polypropylene and PVC, worldwide, with their
             capacity and emissions for the latest full year.
  osm        OpenStreetMap (ODbL): places tagged as making plastic, polymers,
             resin, PVC or vinyl chloride (product=...), worldwide.
  wikidata   Wikidata (CC0): places whose product is a plastic, a polymer or
             vinyl chloride, with a position.

Nothing is merged across sources (the same plant can appear once from each),
and nothing is left out. Run daily; the registers change once a year, so a
source is read again only when its last read is a week old.
"""
import csv, gzip, io, json, os, pathlib, re, sys, tempfile, time, urllib.parse, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
csv.field_size_limit(1 << 30)

OUT = pathlib.Path("plastics")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas; welcometoyourgalaxy@gmail.com)", "Accept-Encoding": "identity"}
WEEK = 7 * 24 * 3600
PLAST, VC = "plants", "vinyl_chloride"
POLYMER_WORDS = re.compile(r"polymer|resin|poly(ethylene|propylene|styrene|vinyl|amide|carbonate|ester|urethane)|\bpvc\b|\bpet\b|"
                           r"vinyl.?chloride|\bvcm\b|\bhdpe\b|\bldpe\b|\babs\b|pellet|\bnylon", re.I)


def get(url, data=None, timeout=600, tries=3, headers=None):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=dict(UA, **(headers or {})))
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"    {url[:110]}: {e}; again in {15 * (i + 1)}s", flush=True)
            time.sleep(15 * (i + 1))


def feat(lon, lat, props):
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90) or (lon == 0 and lat == 0):
        return None
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            "properties": {k: v for k, v in props.items() if v not in (None, "")}}


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ US TRI
def us_tri():
    year = int(time.strftime("%Y"))
    text, used = None, None
    for y in range(year, year - 5, -1):
        url = f"https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/{y}_US/csv"
        try:
            raw = get(url, timeout=900, tries=2)
        except Exception as e:  # noqa: BLE001
            print(f"    TRI {y}: {e}")
            continue
        if raw[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(raw))
            raw = z.read([n for n in z.namelist() if n.lower().endswith(".csv")][0])
        t = raw.decode("utf-8-sig", errors="replace")
        if t.count("\n") > 1000:
            text, used = t, y
            break
    if not text:
        raise RuntimeError("no TRI year could be read")
    rd = csv.reader(io.StringIO(text))
    head = [re.sub(r"^\s*\d+\.\s*", "", h).strip().upper() for h in next(rd)]
    col = lambda *names: next((head.index(n) for n in names if n in head), None)  # noqa: E731
    c = {k: col(*v) for k, v in {
        "trifd": ("TRIFD", "TRI FACILITY ID"), "name": ("FACILITY NAME",), "street": ("STREET ADDRESS",), "city": ("CITY",),
        "state": ("ST", "STATE"), "lat": ("LATITUDE",), "lon": ("LONGITUDE",), "parent": ("PARENT CO NAME", "PARENT COMPANY NAME"),
        "naics": ("PRIMARY NAICS",), "chem": ("CHEMICAL",), "cas": ("CAS#", "CAS #", "CAS NUMBER"), "unit": ("UNIT OF MEASURE",),
        "onsite": ("ON-SITE RELEASE TOTAL",), "total": ("TOTAL RELEASES",), "carc": ("CARCINOGEN",)}.items()}
    missing = [k for k in ("trifd", "lat", "lon", "naics", "chem") if c[k] is None]
    if missing:
        raise RuntimeError(f"TRI columns not found: {missing} (have {head[:40]})")
    g = lambda row, k: row[c[k]].strip() if c[k] is not None and c[k] < len(row) else ""  # noqa: E731
    plants, vcs = {}, {}
    for row in rd:
        if not row:
            continue
        tid = g(row, "trifd")
        cas = re.sub(r"\D", "", g(row, "cas")).lstrip("0")
        is_vc = cas == "75014" or g(row, "chem").upper() == "VINYL CHLORIDE"
        is_plast = g(row, "naics").startswith("325211")
        if not (is_vc or is_plast):
            continue
        base = {"name": g(row, "name").title(), "address": ", ".join(x for x in (g(row, "street").title(), g(row, "city").title(), g(row, "state")) if x),
                "parent_company": g(row, "parent"), "tri_facility_id": tid, "primary_naics": g(row, "naics"), "year": used,
                "source": f"US EPA Toxics Release Inventory, {used}", "link": f"https://enviro.epa.gov/facts/tri/ef-facilities/#/Facility/{tid}"}
        tot = num(g(row, "total"))
        unit = g(row, "unit") or "Pounds"
        if is_plast:
            p = plants.setdefault(tid, dict(base, group="Plastic resin and polymer plants", chemicals_reported=[], total_releases_pounds=0.0,
                                            _lat=g(row, "lat"), _lon=g(row, "lon")))
            p["chemicals_reported"].append(g(row, "chem"))
            if tot is not None and unit.lower().startswith("pound"):
                p["total_releases_pounds"] += tot
        if is_vc:
            v = vcs.setdefault(tid, dict(base, group="Reporting vinyl chloride releases, United States", _lat=g(row, "lat"), _lon=g(row, "lon")))
            v["vinyl_chloride_released_pounds"] = (v.get("vinyl_chloride_released_pounds") or 0) + (tot or 0)
            v["vinyl_chloride_released_on_site_pounds"] = (v.get("vinyl_chloride_released_on_site_pounds") or 0) + (num(g(row, "onsite")) or 0)
            v["value"] = v["vinyl_chloride_released_pounds"]
            v["unit"] = "pounds of vinyl chloride released a year"
    out = {PLAST: [], VC: []}
    for kind, got in ((PLAST, plants), (VC, vcs)):
        for p in got.values():
            lat, lon = p.pop("_lat"), p.pop("_lon")
            if "chemicals_reported" in p:
                p["chemicals_reported"] = "; ".join(sorted(set(p["chemicals_reported"])))
                p["total_releases_pounds"] = round(p["total_releases_pounds"], 3)
                p["value"] = p["total_releases_pounds"]
                p["unit"] = "pounds of reported chemicals released a year"
            f = feat(lon, lat, p)
            if f:
                out[kind].append(f)
    print(f"    TRI {used}: {len(out[PLAST]):,} plastic resin plants, {len(out[VC]):,} vinyl chloride facilities")
    return out


# ------------------------------------------------------------------ EU E-PRTR
DISCO = "https://discodata.eea.europa.eu/sql"


def disco(sql, hits=50000):
    raw = get(f"{DISCO}?{urllib.parse.urlencode({'query': sql, 'p': 1, 'nrOfHits': hits})}", timeout=600)
    j = json.loads(raw)
    return j.get("results", j if isinstance(j, list) else [])


def eu_prtr():
    # The tables are found by their columns: a facility table with a position
    # and a main activity, and a release table with a pollutant and a quantity.
    cols = disco("SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME FROM IED.INFORMATION_SCHEMA.COLUMNS")
    tables = {}
    for r in cols:
        tables.setdefault((r["TABLE_SCHEMA"], r["TABLE_NAME"]), set()).add(r["COLUMN_NAME"])
    print("    E-PRTR tables: " + ", ".join(f"{s}.{t}" for s, t in sorted(tables))[:1500])
    pick = lambda need: sorted([k for k, v in tables.items() if need <= v], key=lambda k: ("latest" not in k[0].lower(), k))  # noqa: E731
    fac = pick({"pointGeometryLat", "pointGeometryLon", "mainActivityCode"})
    rel = pick({"pollutantName", "totalPollutantQuantityKg"})
    if not fac:
        raise RuntimeError("no facility table with a position and a main activity")
    fs, ft = fac[0]
    fcols = tables[fac[0]]
    idc = next((x for x in ("Facility_INSPIRE_ID", "FacilityInspireId", "facilityInspireId") if x in fcols), None)
    namec = next((x for x in ("nameOfFeature", "facilityName", "FacilityName") if x in fcols), None)
    rows = disco(f"SELECT * FROM IED.[{fs}].[{ft}] WHERE mainActivityCode LIKE '4(a)(viii)%' OR mainActivityCode LIKE '4.a.viii%' OR mainActivityCode LIKE '4(a)(8)%'")
    out = {PLAST: [], VC: []}
    seen = set()
    for r in rows:
        k = r.get(idc) if idc else None
        if k in seen:
            continue
        seen.add(k)
        p = {kk: vv for kk, vv in r.items() if not kk.lower().startswith("pointgeometry")}
        p.update(name=r.get(namec) or "", group="Plastic resin and polymer plants", source="EU industrial emissions register (E-PRTR), European Environment Agency")
        f = feat(r.get("pointGeometryLon"), r.get("pointGeometryLat"), p)
        if f:
            out[PLAST].append(f)
    if rel and idc:
        rs, rt = rel[0]
        rcols = tables[rel[0]]
        ridc = idc if idc in rcols else next((x for x in rcols if x.lower() == idc.lower()), None)
        yc = "reportingYear" if "reportingYear" in rcols else None
        if ridc:
            rel_rows = disco(f"SELECT * FROM IED.[{rs}].[{rt}] WHERE pollutantName LIKE '%inyl chloride%'")
            best = {}
            for r in rel_rows:
                k = r.get(ridc)
                y = (r.get(yc) or 0) if yc else 0
                had = (best[k].get(yc) or 0) if (k in best and yc) else -1
                if k not in best or y > had:
                    best[k] = r
            ids = list(best)
            placed = {}
            for i in range(0, len(ids), 300):
                part = "','".join(str(x).replace("'", "''") for x in ids[i:i + 300])
                for r in disco(f"SELECT * FROM IED.[{fs}].[{ft}] WHERE [{idc}] IN ('{part}')"):
                    placed[r.get(idc)] = r
            for k, r in best.items():
                fr = placed.get(k)
                if not fr:
                    continue
                p = {kk: vv for kk, vv in fr.items() if not kk.lower().startswith("pointgeometry")}
                p.update({f"release_{kk}": vv for kk, vv in r.items()})
                p.update(name=fr.get(namec) or "", group="Reporting vinyl chloride releases, Europe",
                         source="EU industrial emissions register (E-PRTR), European Environment Agency",
                         value=num(r.get("totalPollutantQuantityKg")), unit="kg of vinyl chloride released a year")
                f = feat(fr.get("pointGeometryLon"), fr.get("pointGeometryLat"), p)
                if f:
                    out[VC].append(f)
    print(f"    E-PRTR: {len(out[PLAST]):,} basic plastics installations, {len(out[VC]):,} vinyl chloride facilities")
    return out


# ------------------------------------------------------------------ Climate TRACE
CT_URL = "https://downloads.climatetrace.org/latest/sector_packages/co2e_100yr/manufacturing.zip"


def ct_crack():
    tmp = pathlib.Path(tempfile.mkdtemp()) / "m.zip"
    with urllib.request.urlopen(urllib.request.Request(CT_URL, headers=UA), timeout=1800) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 22)
            if not b:
                break
            f.write(b)
    z = zipfile.ZipFile(tmp)
    names = [n for n in z.namelist() if re.search(r"petrochemical.steam.cracking", n, re.I) and n.lower().endswith(".csv")
             and "emissions_sources" in n.lower() and not re.search(r"confidence|ownership", n, re.I)]
    if not names:
        raise RuntimeError("no steam cracking file in the package: " + ", ".join(z.namelist()[:30]))
    by = {}
    for n in names:
        with z.open(n) as fh:
            for row in csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig")):
                sid = row.get("source_id")
                y = (row.get("start_time") or "")[:4]
                if not sid or not y.isdigit():
                    continue
                cur = by.setdefault(sid, {})
                yr = cur.setdefault(y, {"row": row, "t": 0.0})
                yr["t"] += num(row.get("emissions_quantity")) or 0
                yr["row"] = row
    out = []
    this_year = time.strftime("%Y")
    for sid, years in by.items():
        full = [y for y in years if y < this_year] or list(years)
        y = max(full)
        row = years[y]["row"]
        p = {k: v for k, v in row.items() if k not in ("lat", "lon", "start_time", "end_time", "emissions_quantity", "gas")}
        p.update(name=row.get("source_name") or "", year=int(y), group="Ethylene and propylene crackers (the building blocks of plastic)",
                 emissions_t_co2e_100yr=round(years[y]["t"], 1), source="Climate TRACE (CC BY 4.0), petrochemical steam cracking",
                 value=round(years[y]["t"], 1), unit="t CO2e a year")
        f = feat(row.get("lon"), row.get("lat"), p)
        if f:
            out.append(f)
    tmp.unlink(missing_ok=True)
    print(f"    Climate TRACE: {len(out):,} steam crackers")
    return {PLAST: out, VC: []}


# ------------------------------------------------------------------ OpenStreetMap
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
OSM_RE = "plastic|polymer|resin|polyethylene|polypropylene|polystyrene|polyvinyl|pvc|vinyl.chloride|polyamide|polycarbonate|polyester"


def osm():
    q = f'[out:json][timeout:900];(nwr["product"~"{OSM_RE}",i];nwr["produce"~"{OSM_RE}",i];);out center tags;'
    raw = None
    for ep in OVERPASS:
        try:
            raw = get(ep, data=urllib.parse.urlencode({"data": q}).encode(), timeout=960, tries=2,
                      headers={"Accept": "application/json, */*", "Content-Type": "application/x-www-form-urlencoded"})
            break
        except Exception as e:  # noqa: BLE001
            print(f"    {ep}: {e}")
    if raw is None:
        raise RuntimeError("no Overpass server answered")
    out = {PLAST: [], VC: []}
    for el in json.loads(raw).get("elements", []):
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        t = el.get("tags") or {}
        made = " ".join(str(t.get(k, "")) for k in ("product", "produce"))
        polymer = bool(POLYMER_WORDS.search(made))
        p = dict(t, name=t.get("name") or t.get("operator") or "", osm=f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                 source="OpenStreetMap contributors (ODbL)",
                 group="Plastic resin and polymer plants" if polymer else "Plastic goods factories",
                 position=None if el["type"] == "node" else "the middle of the area OpenStreetMap maps")
        f = feat(lon, lat, p)
        if not f:
            continue
        out[PLAST].append(f)
        if re.search(r"vinyl.?chloride|\bpvc\b|polyvinyl", made, re.I):
            out[VC].append(feat(lon, lat, dict(p, group="Vinyl chloride and PVC plants in open maps")))
    print(f"    OpenStreetMap: {len(out[PLAST]):,} places, {len(out[VC]):,} naming vinyl chloride or PVC")
    return out


# ------------------------------------------------------------------ Wikidata
WDQS = "https://query.wikidata.org/sparql"


def wikidata():
    q = """SELECT ?item ?itemLabel ?coord ?productLabel ?countryLabel ?operatorLabel ?ownerLabel ?inception ?article WHERE {
  { ?product wdt:P279* wd:Q11474 } UNION { ?product wdt:P279* wd:Q81163 } UNION { ?product rdfs:label "vinyl chloride"@en }
  ?item wdt:P1056 ?product ; wdt:P625 ?coord .
  OPTIONAL { ?item wdt:P17 ?country } OPTIONAL { ?item wdt:P137 ?operator } OPTIONAL { ?item wdt:P127 ?owner }
  OPTIONAL { ?item wdt:P571 ?inception }
  OPTIONAL { ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en,mul". }
}"""
    raw = get(WDQS, data=urllib.parse.urlencode({"query": q, "format": "json"}).encode(), timeout=300,
              headers={"Accept": "application/sparql-results+json", "Content-Type": "application/x-www-form-urlencoded"})
    rows = json.loads(raw)["results"]["bindings"]
    v = lambda r, k: r[k]["value"] if k in r else None  # noqa: E731
    by = {}
    for r in rows:
        m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", v(r, "coord") or "")
        if not m:
            continue
        it = by.setdefault(v(r, "item"), {"lon": m.group(1), "lat": m.group(2), "name": v(r, "itemLabel"), "products": set(),
                                          "country": v(r, "countryLabel"), "operator": v(r, "operatorLabel"), "owner": v(r, "ownerLabel"),
                                          "inception": (v(r, "inception") or "")[:10], "wikipedia": v(r, "article")})
        if v(r, "productLabel"):
            it["products"].add(v(r, "productLabel"))
    out = {PLAST: [], VC: []}
    for qid, it in by.items():
        prods = "; ".join(sorted(it.pop("products")))
        lon, lat = it.pop("lon"), it.pop("lat")
        p = dict(it, products=prods, wikidata=qid, source="Wikidata (CC0)",
                 group="Plastic resin and polymer plants" if POLYMER_WORDS.search(prods) else "Plastic goods factories")
        f = feat(lon, lat, p)
        if f:
            out[PLAST].append(f)
            if re.search(r"vinyl chloride|polyvinyl|\bpvc\b", prods, re.I):
                out[VC].append(feat(lon, lat, dict(p, group="Vinyl chloride and PVC plants in open maps")))
    print(f"    Wikidata: {len(out[PLAST]):,} places, {len(out[VC]):,} naming vinyl chloride or PVC")
    return out


SOURCES = [("us_tri", us_tri), ("eu_prtr", eu_prtr), ("ct_crack", ct_crack), ("osm", osm), ("wikidata", wikidata)]


def main():
    OUT.mkdir(exist_ok=True)
    try:
        status = json.loads((OUT / "status.json").read_text())
    except Exception:  # noqa: BLE001
        status = {}
    kept = {}
    for kind in (PLAST, VC):
        try:
            kept[kind] = json.loads((OUT / f"{kind}.geojson").read_text()).get("features", [])
        except Exception:  # noqa: BLE001
            kept[kind] = []
    got = {PLAST: [], VC: []}
    only = set(sys.argv[1:])
    for name, fn in SOURCES:
        last = status.get(name, {})
        stale = time.time() - last.get("at", 0) > WEEK or not last.get("ok")
        if (only and name not in only) or (not only and not stale and not os.environ.get("PLASTICS_REBUILD")):
            for kind in (PLAST, VC):
                got[kind] += [f for f in kept[kind] if f["properties"].get("_from") == name]
            continue
        print(f"plastics: {name}", flush=True)
        try:
            res = fn()
            for kind in (PLAST, VC):
                for f in res[kind]:
                    if f:
                        f["properties"]["_from"] = name
                        got[kind].append(f)
            status[name] = {"ok": True, "at": time.time(), "when": time.strftime("%Y-%m-%d"),
                            "plants": len(res[PLAST]), "vinyl_chloride": len([f for f in res[VC] if f])}
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL {name}: {e}; its records from the last copy are kept", flush=True)
            for kind in (PLAST, VC):
                got[kind] += [f for f in kept[kind] if f["properties"].get("_from") == name]
            status[name] = dict(last, ok=False, error=str(e)[:300], tried=time.strftime("%Y-%m-%d"))
    for kind in (PLAST, VC):
        if not got[kind] and kept[kind]:
            got[kind] = kept[kind]
        (OUT / f"{kind}.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": got[kind]},
                                                        ensure_ascii=False, separators=(",", ":")))
        print(f"plastics: {kind}: {len(got[kind]):,} places")
    (OUT / "status.json").write_text(json.dumps(status, indent=1))


if __name__ == "__main__":
    main()
