#!/usr/bin/env python3
"""
Wars, militaries and weapons, past and current: the Culprits map's own layers
in place of Guerillamap (round 74, asked 27 September). Each part is copied
daily from an open source; the map reads the copies (and reads the aircraft,
the news and the country figures live). A part whose source does not answer
keeps its last copy, and says so in the log.

  military/ucdp/            UCDP Georeferenced Event Dataset (every armed
  tiles/mil_conflicts.pmtiles  conflict event since 1989 with at least one
                            death, global release plus the monthly candidate
                            events of the current year), CC BY 4.0. Cite: Sundberg
                            and Melander (2013), Journal of Peace Research 50(4);
                            Davies, Pettersson and Öberg (2024) for the candidates.
                            Every field kept, in 256 gzipped pieces; the tiles
                            carry id, date, kind and deaths.
  military/sites.geojson    military bases, air bases, naval bases and other
                            military installations in Wikidata (CC0), in use
                            and closed, with the state that runs each and the
                            country it is in.
  military/units.geojson    military units at their headquarters (Wikidata),
                            active and disbanded.
  military/test_sites.geojson  nuclear test sites (Wikidata).
  military/attacks.geojson  terrorist attacks with a position in Wikidata, by
                            decade. Wikidata is edited by anyone and is far
                            from complete; the Global Terrorism Database forbids
                            republishing, so it is not used.
  military/minefields.geojson  minefields mapped in OpenStreetMap (ODbL),
                            marked and past (was:/disused:).
  shapes/mil_alliances.geojson  every state's memberships of military
                            alliances in Wikidata, current and past, with a
                            menu to shade by each alliance.
  military/news.geojson     the last seven days of news about fighting,
                            placed where the reports name, from GDELT's GEO
                            API (a copy for when GDELT does not answer the map).
  military/news/<YYYY-MM>.geojson  round 78: the same news kept, a month to a
                            file, so the map is not limited to seven days: each
                            place with the days it was named, the first and last,
                            and every article link seen for it that month.
                            military/news/index.json lists the months.
  military/osm_military.geojson  round 78: OpenStreetMap's military places
                            (military=airfield, base, naval_base, barracks, range,
                            training_area, nuclear_explosion_site), each at its
                            middle, every tag kept (ODbL).
  military/mirta.geojson    round 78: the US Department of Defense's Military
                            Installations, Ranges and Training Areas (MIRTA),
                            found on catalog.data.gov and read from the file it
                            lists; the version and date are those the catalogue
                            gives.
"""
import csv, gzip, io, json, pathlib, re, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas daily copy; welcometoyourgalaxy@gmail.com)", "Accept-Encoding": "identity"}
OUT = pathlib.Path("military")
TILES = pathlib.Path("tiles")
SHAPES = pathlib.Path("shapes")
WDQS = "https://query.wikidata.org/sparql"
CULPRITS_RAW = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/culprits/main/"
csv.field_size_limit(1 << 30)


def get(url, tries=3, timeout=180, data=None, headers=None):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=dict(UA, **(headers or {})), data=data)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  {url[:120]}: {e}; again in {20 * (i + 1)}s", flush=True)
            time.sleep(20 * (i + 1))


def sparql(q, timeout=300):
    body = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    raw = get(WDQS, data=body, timeout=timeout, headers={"Accept": "application/sparql-results+json",
                                                          "Content-Type": "application/x-www-form-urlencoded"})
    return json.loads(raw)["results"]["bindings"]


def v(row, k):
    x = row.get(k)
    return x["value"] if x else None


def point(wkt):
    m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", wkt or "")
    return [round(float(m.group(1)), 5), round(float(m.group(2)), 5)] if m else None


def write_geojson(path, feats, meta=None):
    OUT.mkdir(exist_ok=True)
    path.write_text(json.dumps(dict({"type": "FeatureCollection", "features": feats}, **(meta or {})),
                               ensure_ascii=False, separators=(",", ":")))
    print(f"  wrote {path}: {len(feats):,} features, {path.stat().st_size / 1e6:.1f} MB", flush=True)


def part(name, fn):
    try:
        fn()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL  {name}: {e}; its last copy is kept", flush=True)
        return False


# ------------------------------------------------------------- Wikidata classes
def cls(label):
    """A class by its English label: of the items with that label, the one
    with the most instances (so a disambiguation page never wins)."""
    q = f'''SELECT ?c (COUNT(?x) AS ?n) WHERE {{ ?c rdfs:label "{label}"@en . ?x wdt:P31 ?c . }} GROUP BY ?c ORDER BY DESC(?n) LIMIT 1'''
    rows = sparql(q)
    if not rows:
        raise RuntimeError(f"no Wikidata class labelled {label!r}")
    return v(rows[0], "c").rsplit("/", 1)[-1]


def subclasses(qid):
    rows = sparql(f"SELECT DISTINCT ?t WHERE {{ ?t wdt:P279* wd:{qid} . }}")
    return sorted({v(r, "t").rsplit("/", 1)[-1] for r in rows})


def instances(classes, extra, fields, batch=40):
    """Every item that is an instance of one of the classes and has a position."""
    out = {}
    for i in range(0, len(classes), batch):
        vals = " ".join(f"wd:{c}" for c in classes[i:i + batch])
        q = f"""SELECT ?x ?xLabel ?coord ?tLabel {' '.join('?' + f for f in fields)} WHERE {{
  VALUES ?t {{ {vals} }}
  ?x wdt:P31 ?t .
  {extra}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr,es,de,ru,zh,ar". }}
}}"""
        for r in sparql(q):
            x = v(r, "x")
            d = out.setdefault(x, {"wikidata": x, "name": v(r, "xLabel"), "kinds": set(), "coord": v(r, "coord")})
            if v(r, "tLabel"):
                d["kinds"].add(v(r, "tLabel"))
            for f in fields:
                val = v(r, f)
                if val and not d.get(f):
                    d[f] = val
        time.sleep(1)
    return out


def year(s):
    m = re.match(r"(-?\d{4})", s or "")
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------- sites
NOT_MILITARY = {"observation tower", "lookout tower", "belfry"}


def sites():
    base = []
    for label in ("military base", "air base", "naval base", "military installation", "military airfield", "barracks",
                  "military facility", "fortification"):
        try:
            base.append(cls(label))
        except Exception as e:  # noqa: BLE001
            print(f"    {label}: {e}")
    classes = sorted({c for b in base for c in subclasses(b)})
    print(f"    {len(classes)} classes of military installation")
    extra = """?x wdt:P625 ?coord .
  OPTIONAL { ?x wdt:P17 ?country . ?country rdfs:label ?countryName FILTER(lang(?countryName) = "en") . OPTIONAL { ?country wdt:P298 ?countryIso } }
  OPTIONAL { ?x wdt:P137 ?op . ?op rdfs:label ?operator FILTER(lang(?operator) = "en") . OPTIONAL { ?op wdt:P17 ?opc . ?opc wdt:P298 ?operatorIso } OPTIONAL { ?op wdt:P298 ?operatorIso } }
  OPTIONAL { ?x wdt:P571 ?opened } OPTIONAL { ?x wdt:P576 ?closed } OPTIONAL { ?x wdt:P3999 ?closedOfficially }"""
    got = instances(classes, extra, ["countryName", "countryIso", "operator", "operatorIso", "opened", "closed", "closedOfficially"])
    feats = []
    left_out = 0
    for d in got.values():
        c = point(d["coord"])
        if not c:
            continue
        # Round 85b (asked 27 September): Wikidata files fire lookout towers,
        # observation towers and belfries under fortifications; they are not
        # military installations. A tower also filed as a military kind stays.
        kinds = {k.lower() for k in d["kinds"]}
        if any("fire lookout" in k for k in kinds) or (kinds and kinds <= NOT_MILITARY):
            left_out += 1
            continue
        shut = d.get("closed") or d.get("closedOfficially")
        foreign = bool(d.get("operatorIso") and d.get("countryIso") and d["operatorIso"] != d["countryIso"])
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": c}, "properties": {
            "name": d["name"], "kind": ", ".join(sorted(d["kinds"])), "country": d.get("countryName"), "run_by": d.get("operator"),
            "foreign": "run by another state" if foreign else None, "opened": year(d.get("opened")), "closed": year(shut),
            "group": ("closed" if shut else "in use or no closing recorded") + (", run by another state" if foreign else ""),
            "wikidata": d["wikidata"]}})
    print(f"    {left_out:,} fire lookout towers, observation towers and belfries left out", flush=True)
    write_geojson(OUT / "sites.geojson", feats, {"source": "Wikidata (CC0)", "classes": classes})


# --------------------------------------------------------------------- units
def units():
    base = cls("military unit")
    classes = subclasses(base)
    print(f"    {len(classes)} classes of military unit")
    extra = """?x wdt:P159 ?hq . ?hq wdt:P625 ?coord .
  OPTIONAL { ?hq rdfs:label ?hqName FILTER(lang(?hqName) = "en") }
  OPTIONAL { ?x wdt:P17 ?country . ?country rdfs:label ?countryName FILTER(lang(?countryName) = "en") }
  OPTIONAL { ?x wdt:P571 ?formed } OPTIONAL { ?x wdt:P576 ?disbanded }
  OPTIONAL { ?x wdt:P241 ?branch . ?branch rdfs:label ?branchName FILTER(lang(?branchName) = "en") }"""
    got = instances(classes, extra, ["hqName", "countryName", "formed", "disbanded", "branchName"], batch=25)
    feats = []
    for d in got.values():
        c = point(d["coord"])
        if not c:
            continue
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": c}, "properties": {
            "name": d["name"], "kind": ", ".join(sorted(d["kinds"])), "headquarters": d.get("hqName"), "country": d.get("countryName"),
            "branch": d.get("branchName"), "formed": year(d.get("formed")), "disbanded": year(d.get("disbanded")),
            "group": "disbanded" if d.get("disbanded") else "active or no end recorded", "wikidata": d["wikidata"],
            "position": "the unit's headquarters, not where it is deployed"}})
    write_geojson(OUT / "units.geojson", feats, {"source": "Wikidata (CC0)"})


# ---------------------------------------------------------------- test sites
def test_sites():
    base = cls("nuclear test site")
    extra = """?x wdt:P625 ?coord .
  OPTIONAL { ?x wdt:P17 ?country . ?country rdfs:label ?countryName FILTER(lang(?countryName) = "en") }
  OPTIONAL { ?x wdt:P137 ?op . ?op rdfs:label ?operator FILTER(lang(?operator) = "en") }
  OPTIONAL { ?x wdt:P571 ?opened } OPTIONAL { ?x wdt:P576 ?closed }"""
    got = instances(subclasses(base), extra, ["countryName", "operator", "opened", "closed"])
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": point(d["coord"])}, "properties": {
        "name": d["name"], "country": d.get("countryName"), "run_by": d.get("operator"), "opened": year(d.get("opened")),
        "closed": year(d.get("closed")), "group": "closed" if d.get("closed") else "no closing recorded", "wikidata": d["wikidata"]}}
        for d in got.values() if point(d["coord"])]
    write_geojson(OUT / "test_sites.geojson", feats, {"source": "Wikidata (CC0)"})


# ------------------------------------------------------------------- attacks
def attacks():
    base = cls("terrorist attack")
    extra = """?x wdt:P625 ?coord .
  OPTIONAL { ?x wdt:P585 ?date } OPTIONAL { ?x wdt:P580 ?start }
  OPTIONAL { ?x wdt:P1120 ?deaths } OPTIONAL { ?x wdt:P1339 ?injured }
  OPTIONAL { ?x wdt:P8031 ?perp . ?perp rdfs:label ?perpetrator FILTER(lang(?perpetrator) = "en") }
  OPTIONAL { ?x wdt:P17 ?country . ?country rdfs:label ?countryName FILTER(lang(?countryName) = "en") }"""
    got = instances(subclasses(base), extra, ["date", "start", "deaths", "injured", "perpetrator", "countryName"])
    feats = []
    for d in got.values():
        c = point(d["coord"])
        if not c:
            continue
        y = year(d.get("date") or d.get("start"))
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": c}, "properties": {
            "name": d["name"], "date": (d.get("date") or d.get("start") or "")[:10] or None, "deaths": d.get("deaths"),
            "injured": d.get("injured"), "perpetrator": d.get("perpetrator"), "country": d.get("countryName"),
            "group": f"{y // 10 * 10}s" if y else "date not recorded", "wikidata": d["wikidata"]}})
    write_geojson(OUT / "attacks.geojson", feats, {"source": "Wikidata (CC0)"})


# ----------------------------------------------------------------- alliances
def alliances():
    base = cls("military alliance")
    classes = subclasses(base)
    vals = " ".join(f"wd:{c}" for c in classes)
    q = f"""SELECT ?country ?iso ?a ?aLabel ?start ?end WHERE {{
  VALUES ?t {{ {vals} }}
  ?a wdt:P31 ?t .
  ?country p:P463 ?st . ?st ps:P463 ?a .
  ?country wdt:P298 ?iso .
  OPTIONAL {{ ?st pq:P580 ?start }} OPTIONAL {{ ?st pq:P582 ?end }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}"""
    rows = sparql(q)
    by = {}
    for r in rows:
        iso = v(r, "iso").upper()
        by.setdefault(iso, []).append({"alliance": v(r, "aLabel"), "wikidata": v(r, "a"), "from": year(v(r, "start")), "until": year(v(r, "end"))})
    now_count = {}
    for iso, ms in by.items():
        for m in ms:
            if not m["until"]:
                now_count[m["alliance"]] = now_count.get(m["alliance"], 0) + 1
    big = [a for a, n in sorted(now_count.items(), key=lambda x: -x[1]) if n >= 3]
    bounds = json.loads(get(CULPRITS_RAW + "map/data/boundaries.geojson").decode())["features"]
    slug = lambda a: "al_" + re.sub(r"[^a-z0-9]+", "_", a.lower()).strip("_")[:40]  # noqa: E731
    feats = []
    for f in bounds:
        iso = f["properties"].get("iso3")
        if not iso or iso not in by:
            continue
        ms = sorted(by[iso], key=lambda m: (m["from"] or 0))
        now = [m["alliance"] for m in ms if not m["until"]]
        p = {"name": f["properties"]["name"], "iso3": iso, "alliances_now": len(set(now)) or None,
             "list": "\n".join(f"{m['alliance']}: {m['from'] or 'start not recorded'} to {m['until'] or 'now, or no end recorded'}" for m in ms)}
        for a in big:
            p[slug(a)] = "member now" if a in now else ("former member" if any(m["alliance"] == a for m in ms) else "never a member")
        feats.append({"type": "Feature", "geometry": f["geometry"], "properties": p})
    counts = sorted({f["properties"]["alliances_now"] for f in feats if f["properties"].get("alliances_now")})
    menu = [{"label": "military alliances it belongs to now (Wikidata)", "field": "alliances_now", "national": True,
             "classes": [[str(n), f"{n} alliance{'' if n == 1 else 's'}"] for n in counts]}]
    for a in big:
        menu.append({"label": a, "field": slug(a), "national": True,
                     "classes": [["member now", "member now"], ["former member", "former member"], ["never a member", "never a member"]]})
    SHAPES.mkdir(exist_ok=True)
    (SHAPES / "mil_alliances.geojson").write_text(json.dumps({"type": "FeatureCollection", "menu": menu, "features": feats}, ensure_ascii=False, separators=(",", ":")))
    print(f"  wrote shapes/mil_alliances.geojson: {len(feats)} countries, {len(big)} alliances in the menu")


# ---------------------------------------------------------------- minefields
def minefields():
    q = """[out:json][timeout:900];
(nwr["hazard"="minefield"]; nwr["hazard"="landmine"]; nwr["hazard:type"="minefield"];
 nwr["was:hazard"="minefield"]; nwr["disused:hazard"="minefield"]; nwr["historic"="minefield"];);
out center tags;"""
    raw = overpass(q)
    if raw is None:
        raise RuntimeError("no Overpass server answered")
    feats = []
    for el in json.loads(raw).get("elements", []):
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None:
            continue
        t = el.get("tags") or {}
        past = any(k.startswith(("was:", "disused:")) for k in t) or t.get("historic") == "minefield"
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": dict({k: v_ for k, v_ in t.items()}, group="cleared or no longer marked" if past else "marked as a minefield",
                                         osm=f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                                         position="the middle of the area OpenStreetMap maps" if el["type"] != "node" else None)})
    write_geojson(OUT / "minefields.geojson", feats, {"source": "© OpenStreetMap contributors (ODbL)"})


# ---------------------------------------------------------------------- news
NEWS_QUERY = '(airstrike OR shelling OR "armed clashes" OR militants OR "killed in fighting" OR "drone strike" OR bombing OR insurgents OR "military offensive")'


# GDELT's GEO 2.0 API answers 404 since late September 2026 (round 80). The
# news now comes from GDELT 2.0's own event files, published every 15 minutes
# (data.gdeltproject.org/gdeltv2/<stamp>.export.CSV.zip): the events coded as
# fighting - CAMEO root codes 18 (assault), 19 (fight) and 20 (unconventional
# mass violence) - each at the place GDELT gives for the action, with the
# article it was coded from. Files not read yet are read, up to the last two
# days, so a missed day is caught up.
CAMEO_ROOT = {"18": "assault", "19": "fight", "20": "unconventional mass violence"}
GDELT_FILES = "http://data.gdeltproject.org/gdeltv2/"


def news():
    d = OUT / "news"
    d.mkdir(parents=True, exist_ok=True)
    cur_path = d / "cursor.json"
    now = time.time()
    last = json.loads(cur_path.read_text()).get("last", 0) if cur_path.exists() else 0
    t = max(last + 900, now - 2 * 86400)
    t = t - (t % 900)
    stamps = []
    while t <= now - 900:
        stamps.append((t, time.strftime("%Y%m%d%H%M%S", time.gmtime(t))))
        t += 900
    events, read, last_ok, missed = [], 0, last, []
    for at, st in stamps:
        try:
            raw = get(f"{GDELT_FILES}{st}.export.CSV.zip", tries=2, timeout=60)
        except Exception as e:  # noqa: BLE001
            missed.append(f"{st} ({e})")
            continue
        read += 1
        last_ok = max(last_ok, at)
        z = zipfile.ZipFile(io.BytesIO(raw))
        for line in z.read(z.namelist()[0]).decode("utf-8", "replace").splitlines():
            c = line.split("\t")
            if len(c) < 61 or c[28] not in CAMEO_ROOT or not c[56] or not c[57]:
                continue
            try:
                lat, lon = float(c[56]), float(c[57])
            except ValueError:
                continue
            events.append({"day": f"{c[1][:4]}-{c[1][4:6]}-{c[1][6:8]}", "place": c[52] or "A place named in the news",
                           "at": (round(lon, 3), round(lat, 3)), "url": c[60], "kind": CAMEO_ROOT[c[28]],
                           "a1": c[6], "a2": c[16], "code": c[26]})
    if not read:
        raise RuntimeError("no GDELT event file could be read")
    cur_path.write_text(json.dumps({"last": last_ok}))
    news_archive(events)
    # The last seven days, for the map's first row.
    cut = time.strftime("%Y-%m-%d", time.gmtime(now - 7 * 86400))
    recent = []
    for f in sorted(d.glob("20*.geojson"))[-2:]:
        for ft in json.loads(f.read_text()).get("features", []):
            p = ft["properties"]
            links = [x for x in p.get("links", []) if x.get("day", "") >= cut]
            if links:
                recent.append({"type": "Feature", "geometry": ft["geometry"],
                               "properties": dict(p, links=links, days=[x for x in p.get("days", []) if x >= cut])})
    write_geojson(OUT / "news.geojson", recent, {"source": "GDELT 2.0 event files (CAMEO 18, 19, 20)", "made": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())})
    print(f"  news: {read} of {len(stamps)} event files read, {len(events):,} fighting events" +
          (f"; not read: {len(missed)} (first {missed[0]})" if missed else ""), flush=True)


LINK = re.compile(r'<a[^>]*href="(https?:[^"]+)"[^>]*>([\s\S]*?)</a>', re.I)


def news_archive(events):
    """Keeps the fighting events a month to a file (round 78; events since round
    80). A place is the name and position GDELT gives; each event adds its day
    and its article, each article once."""
    d = OUT / "news"
    by_month = {}
    for e in events:
        by_month.setdefault(e["day"][:7], []).append(e)
    for month, evs in by_month.items():
        path = d / f"{month}.geojson"
        old = json.loads(path.read_text()) if path.exists() else {"type": "FeatureCollection", "features": []}
        by = {(f["properties"]["name"], tuple(f["geometry"]["coordinates"])): f for f in old.get("features", [])}
        for e in evs:
            key = (e["place"], e["at"])
            if key not in by:
                by[key] = {"type": "Feature", "geometry": {"type": "Point", "coordinates": list(e["at"])},
                           "properties": {"name": e["place"], "first": e["day"], "last": e["day"], "days": [], "links": [], "events": 0}}
            q = by[key]["properties"]
            q.setdefault("events", 0)
            q["events"] += 1
            q["first"], q["last"] = min(q["first"], e["day"]), max(q["last"], e["day"])
            if e["day"] not in q["days"]:
                q["days"].append(e["day"])
            if e["url"] and e["url"] not in {x["u"] for x in q["links"]}:
                who = " and ".join(x for x in (e["a1"], e["a2"]) if x)
                q["links"].append({"u": e["url"], "t": f"{e['kind']}" + (f": {who}" if who else ""), "day": e["day"], "seen": e["day"]})
        out = list(by.values())
        path.write_text(json.dumps({"type": "FeatureCollection", "month": month, "features": out}, ensure_ascii=False, separators=(",", ":")))
        print(f"  news archive {month}: {len(out):,} places", flush=True)
    months = sorted(x.stem for x in d.glob("20*.geojson"))
    (d / "index.json").write_text(json.dumps({"months": [{"month": m, "places": len(json.loads((d / f"{m}.geojson").read_text()).get("features", []))}
                                                         for m in months]}, indent=1))


# ---------------------------------------------------------- OpenStreetMap bases
OSM_MIL = ["airfield", "base", "naval_base", "barracks", "range", "training_area", "nuclear_explosion_site"]


OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
# overpass-api.de answers 406 to a request that does not say what it accepts
# and how its body is written (round 80).
OVERPASS_HEADERS = {"Accept": "application/json, */*", "Content-Type": "application/x-www-form-urlencoded"}


def overpass(q):
    for ep in OVERPASS:
        try:
            return get(ep, data=urllib.parse.urlencode({"data": q}).encode(), timeout=960, tries=2, headers=OVERPASS_HEADERS)
        except Exception as e:  # noqa: BLE001
            print(f"    {ep}: {e}")
    return None


def osm_military():
    path = OUT / "osm_military.geojson"
    old = json.loads(path.read_text()).get("features", []) if path.exists() else []
    feats = []
    for kind in OSM_MIL:
        q = f"""[out:json][timeout:900];(nwr["military"="{kind}"];nwr["was:military"="{kind}"];nwr["disused:military"="{kind}"];);out center tags;"""
        raw = None
        raw = overpass(q)
        if raw is None:
            kept = [f for f in old if str(f["properties"].get("group", "")).startswith(kind.replace("_", " "))]
            feats.extend(kept)
            print(f"    {kind}: no Overpass server answered; its {len(kept):,} places from the last copy kept", flush=True)
            continue
        n = 0
        for el in json.loads(raw).get("elements", []):
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None:
                continue
            t = el.get("tags") or {}
            past = any(k.startswith(("was:", "disused:")) for k in t)
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                          "properties": dict(t, group=kind.replace("_", " ") + (" (no longer in use)" if past else ""),
                                             osm=f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
                                             position=None if el["type"] == "node" else "the middle of the area OpenStreetMap maps")})
            n += 1
        print(f"    {kind}: {n:,}", flush=True)
    if not feats:
        raise RuntimeError("nothing came back")
    write_geojson(OUT / "osm_military.geojson", feats, {"source": "© OpenStreetMap contributors (ODbL)"})


# ------------------------------------------------------------------ US MIRTA
# catalog.data.gov's API answers 404 (round 80). MIRTA is read instead from
# the federal ArcGIS items that publish it: the points layer first, the USACE
# copy second. Every field is kept.
MIRTA_ITEMS = ["8acd7277c2d04bc294c927fc7149c626", "fc0f38c5a19a46dbacd92f2fb823ef8c"]


def mirta():
    last = None
    for item in MIRTA_ITEMS:
        try:
            meta = json.loads(get(f"https://www.arcgis.com/sharing/rest/content/items/{item}?f=json"))
            url = (meta.get("url") or "").rstrip("/")
            if not url:
                raise RuntimeError("the item names no service")
            if not re.search(r"/\d+$", url):
                url += "/0"
            feats, off = [], 0
            while True:
                j = json.loads(get(f"{url}/query?where=1%3D1&outFields=*&outSR=4326&f=geojson&resultOffset={off}&resultRecordCount=1000", timeout=300))
                page = j.get("features") or []
                for f in page:
                    g = f.get("geometry") or {}
                    pt = None
                    if g.get("type") == "Point":
                        pt = g["coordinates"][:2]
                    elif g.get("coordinates"):
                        xs, ys = [], []

                        def walk(c):
                            if isinstance(c[0], (int, float)):
                                xs.append(c[0]); ys.append(c[1])
                            else:
                                for x in c:
                                    walk(x)
                        walk(g["coordinates"])
                        pt = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2] if xs else None
                    if not pt:
                        continue
                    props = {k: v_ for k, v_ in (f.get("properties") or {}).items() if v_ not in (None, "")}
                    if g.get("type") != "Point":
                        props["position"] = "the middle of the installation's outline"
                    feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(pt[0], 5), round(pt[1], 5)]}, "properties": props})
                if len(page) < 1000 and not j.get("exceededTransferLimit") and not (j.get("properties") or {}).get("exceededTransferLimit"):
                    break
                off += len(page) or 1000
            if not feats:
                raise RuntimeError("no features")
            write_geojson(OUT / "mirta.geojson", feats, {"source": f"US Department of Defense, {meta.get('title')} (ArcGIS item {item})",
                                                         "modified": meta.get("modified"), "service": url})
            return
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"    MIRTA item {item}: {e}", flush=True)
    raise RuntimeError(f"no MIRTA copy could be read ({last})")


# ---------------------------------------------------------------------- UCDP
# Round 97b (28 September): main() named ucdp but the function had gone
# missing from this file, so the whole script stopped with a NameError before
# any part ran. Written again here from the docstring's description.
UCDP_PAGE = "https://ucdp.uu.se/downloads/"
UCDP_KINDS = {"1": "state-based conflict", "2": "non-state conflict", "3": "one-sided violence against civilians"}


def piece_of(key):
    """The map's pieceOf(): FNV-1a of the id, 256 pieces."""
    h = 0x811C9DC5
    for b in str(key).encode():
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h % 256:02x}"


def ucdp_links():
    """The GED global release (newest) and this release's monthly candidate files, as the downloads page lists them."""
    try:
        page = get(UCDP_PAGE, timeout=120).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"    UCDP downloads page: {e}", flush=True)
        page = ""
    hrefs = {urllib.parse.urljoin(UCDP_PAGE, h) for h in re.findall(r'href="([^"]+)"', page, re.I)}
    ged = sorted((h for h in hrefs if re.search(r"/ged/ged(\d+)-csv\.zip$", h, re.I)),
                 key=lambda h: int(re.search(r"ged(\d+)-csv", h, re.I).group(1)))
    cands = [h for h in hrefs if re.search(r"candidate.*\.csv$", h, re.I)]
    if not ged:
        # The page could not be read: the release names UCDP uses (ged251,
        # ged261 ...), newest first.
        yy = time.gmtime().tm_year % 100
        ged = [f"{UCDP_PAGE}ged/ged{y}1-csv.zip" for y in (yy - 2, yy - 1, yy)]
    return ged, sorted(cands)


def ucdp_rows(raw):
    if raw[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(raw))
        name = max((n for n in z.namelist() if n.lower().endswith(".csv")), key=lambda n: z.getinfo(n).file_size)
        raw = z.read(name)
    return csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace")))


def ucdp():
    import mines  # noqa: E402  sh() and tools()
    ged, cands = ucdp_links()
    raw, release_url = None, None
    for u in reversed(ged):
        try:
            raw = get(u, timeout=900)
            release_url = u
            break
        except Exception as e:  # noqa: BLE001
            print(f"    {u}: {e}", flush=True)
    if raw is None:
        raise RuntimeError("no UCDP GED global release could be fetched")
    ver = re.search(r"ged(\d)(\d+)-csv", release_url, re.I)
    release = f"GED {ver.group(1)}{ver.group(2)[:-1]}.{ver.group(2)[-1]}" if ver else "GED"
    print(f"    {release} from {release_url}: {len(raw) / 1e6:.0f} MB", flush=True)
    work = pathlib.Path(tempfile.mkdtemp())
    parts = {}          # piece -> open file of JSON lines
    lines = open(work / "mil_conflicts.geojsonl", "w", encoding="utf-8")
    seen, counts = set(), {"global": 0, "candidate": 0, "no position": 0}

    def add(r, source):
        eid = str(r.get("id") or "").strip()
        if not eid or eid in seen:
            return
        try:
            lon, lat = float(r["longitude"]), float(r["latitude"])
        except (KeyError, TypeError, ValueError):
            counts["no position"] += 1
            return
        seen.add(eid)
        props = {k: v_ for k, v_ in r.items() if k and v_ not in (None, "")}
        props["release"] = source
        props["kind"] = UCDP_KINDS.get(str(r.get("type_of_violence")), str(r.get("type_of_violence") or ""))
        props["title"] = r.get("conflict_name") or r.get("dyad_name") or ""
        hh = piece_of(eid)
        if hh not in parts:
            parts[hh] = open(work / f"{hh}.jsonl", "w", encoding="utf-8")
        parts[hh].write(json.dumps([eid, {"properties": props}], ensure_ascii=False, separators=(",", ":")) + "\n")
        try:
            deaths = int(float(r.get("best") or 0))
        except ValueError:
            deaths = 0
        lines.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                                "properties": {"id": eid, "x_date": (r.get("date_start") or "")[:10], "x_kind": props["kind"],
                                               "x_deaths": deaths}}, separators=(",", ":")) + "\n")
        counts["global" if source == release else "candidate"] += 1

    for r in ucdp_rows(raw):
        add(r, release)
    del raw
    # The candidate events: monthly files of the year after the release, the
    # newest first, so a later month's correction of an event is the one kept.
    for u in sorted(cands, key=lambda h: [int(x) for x in re.findall(r"\d+", h.rsplit("/", 1)[-1])], reverse=True):
        try:
            for r in ucdp_rows(get(u, timeout=600)):
                add(r, "candidate " + u.rsplit("/", 1)[-1].rsplit(".", 1)[0])
        except Exception as e:  # noqa: BLE001
            print(f"    candidate file {u}: {e}; left out this time", flush=True)
    lines.close()
    for f in parts.values():
        f.close()
    print(f"    UCDP: {counts['global']:,} events from {release}, {counts['candidate']:,} candidate events, "
          f"{counts['no position']:,} without a position", flush=True)
    if counts["global"] == 0:
        raise RuntimeError("no events read from the release")
    mines.tools()
    tile = work / "mil_conflicts.pmtiles"
    mines.sh("tippecanoe", "-o", str(tile), "--force", "-q", "-l", "mil_conflicts", "-Z0", "-z10", "-r1",
             "--no-feature-limit", "--no-tile-size-limit", str(work / "mil_conflicts.geojsonl"))
    if tile.stat().st_size > 95 * 1024 * 1024:
        raise RuntimeError(f"mil_conflicts: {tile.stat().st_size / 1e6:.0f} MB is over GitHub's limit")
    base = OUT / "ucdp"
    base.mkdir(parents=True, exist_ok=True)
    for hh in parts:
        d = {}
        with open(work / f"{hh}.jsonl", encoding="utf-8") as f:
            for line in f:
                k, val = json.loads(line)
                d[k] = val
        (base / f"{hh}.json.gz").write_bytes(gzip.compress(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode()))
    TILES.mkdir(exist_ok=True)
    shutil.move(str(tile), TILES / "mil_conflicts.pmtiles")
    (base / "build.json").write_text(json.dumps({"release": release, "from": release_url, "candidates": cands, **counts,
                                                 "run": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}, indent=1))


def main():
    OUT.mkdir(exist_ok=True)
    only = set(sys.argv[1:])
    done = {}
    for name, fn in (("news", news), ("alliances", alliances), ("test_sites", test_sites), ("attacks", attacks),
                     ("sites", sites), ("units", units), ("minefields", minefields), ("osm_military", osm_military),
                     ("mirta", mirta), ("ucdp", ucdp)):
        if only and name not in only:
            continue
        print(f"military: {name}", flush=True)
        done[name] = part(name, fn)
    (OUT / "status.json").write_text(json.dumps({"run": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "parts": done}, indent=1))
    if not any(done.values()):
        sys.exit("military: nothing was copied")


if __name__ == "__main__":
    main()
