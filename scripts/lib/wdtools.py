"""
Wikidata and OpenStreetMap helpers for the round 114b rows (sports betting,
match fixing, pet food, animal breeding, zoos and aquariums).

No item number is written into a script: every kind is found by its exact
English name (classes()), with every narrower kind under it, and the numbers
found are written to the row's build file so they can be checked.

Places: an item's own coordinates, else its headquarters', else its
location's, else its country's label point (Natural Earth); the box says which.

Kept in scripts/lib/ so the refresh workflow does not run it on its own.
"""
import json, time, urllib.parse, urllib.request

SPARQL = "https://query.wikidata.org/sparql"
UA = {"User-Agent": "CulpritsAtlasBuild/1.0 (https://github.com/WelcomeToYourGalaxy; welcometoyourgalaxy@gmail.com)"}
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
                 "https://overpass.private.coffee/api/interpreter"]


def get(url, timeout=120, data=None, headers=None):
    req = urllib.request.Request(url, headers=dict(UA, **(headers or {})), data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sparql(q, tries=3):
    last = None
    for i in range(tries):
        try:
            body = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
            return json.loads(get(SPARQL, timeout=320, data=body))["results"]["bindings"]
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  query failed ({type(e).__name__}: {e}); try {i + 1} of {tries}", flush=True)
            time.sleep(20 * (i + 1))
    raise last


def v(b, k):
    return b.get(k, {}).get("value", "")


def qid(url):
    return url.rsplit("/", 1)[-1]


def classes(names, subclasses=True):
    """Items named exactly so in English (not disambiguation pages), with
    every narrower kind below them when subclasses is set: {qid: label}."""
    vals = " ".join(json.dumps(n) + "@en" for n in names)
    path = "wdt:P279*" if subclasses else "wdt:P279?"
    rows = sparql(f"""SELECT DISTINCT ?c ?cLabel WHERE {{
      VALUES ?l {{ {vals} }} ?base rdfs:label ?l.
      FILTER NOT EXISTS {{ ?base wdt:P31 wd:Q4167410 }}
      ?c {path} ?base.
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}""")
    return {qid(v(r, "c")): v(r, "cLabel") for r in rows}


def point(wkt):
    try:
        lon, lat = wkt.replace("Point(", "").replace(")", "").split()
        return round(float(lon), 5), round(float(lat), 5)
    except Exception:  # noqa: BLE001
        return None


def country_points():
    """ISO alpha-2 and alpha-3 -> (lon, lat, name): each country's label point."""
    out = {}
    for f in json.loads(get(NE))["features"]:
        p = f["properties"]
        if p.get("LABEL_X") is None:
            continue
        at = (round(p["LABEL_X"], 4), round(p["LABEL_Y"], 4), p.get("NAME") or p.get("ADMIN"))
        for k in (p.get("ISO_A2"), p.get("ISO_A2_EH"), p.get("ISO_A3"), p.get("ADM0_A3")):
            if k and k != "-99":
                out[k] = at
    return out


def overpass(query):
    last = None
    for u in OVERPASS_URLS:
        try:
            return json.loads(get(u, timeout=1100, data=urllib.parse.urlencode({"data": query}).encode(),
                                  headers={"Accept": "application/json, */*", "Content-Type": "application/x-www-form-urlencoded"}))
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  {u}: {e}", flush=True)
    raise RuntimeError(f"no Overpass instance answered ({last})")


def osm_features(elements, keep=None):
    """Overpass elements (with out center) as GeoJSON points with every tag."""
    feats = []
    for e in elements:
        lat = e.get("lat", (e.get("center") or {}).get("lat"))
        lon = e.get("lon", (e.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        t = dict(e.get("tags") or {})
        if keep and not keep(t):
            continue
        t["OpenStreetMap"] = f"https://www.openstreetmap.org/{e['type']}/{e['id']}"
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}, "properties": t})
    return feats


def wikidata_places(where, extra_select="", extra_where="", limit=None):
    """Items matched by `where` (SPARQL using ?item), each placed: own
    coordinates, headquarters, location, or country label point."""
    rows = sparql(f"""SELECT ?item ?itemLabel ?itemDescription ?own ?hqc ?hqLabel ?locc ?iso2 ?countryLabel ?website ?article {extra_select} WHERE {{
      {where}
      OPTIONAL {{ ?item wdt:P625 ?own. }}
      OPTIONAL {{ ?item wdt:P159 ?hq. OPTIONAL {{ ?hq wdt:P625 ?hqc. }} }}
      OPTIONAL {{ ?item wdt:P276 ?loc. ?loc wdt:P625 ?locc. }}
      OPTIONAL {{ ?item wdt:P17|wdt:P27 ?country. OPTIONAL {{ ?country wdt:P297 ?iso2. }} }}
      OPTIONAL {{ ?item wdt:P856 ?website. }}
      OPTIONAL {{ ?article schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>. }}
      {extra_where}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
    }}{f" LIMIT {limit}" if limit else ""}""")
    return rows


def place_row(r, countries):
    for k, how in (("own", "its own coordinates in Wikidata"), ("hqc", "its headquarters"), ("locc", "its location")):
        at = point(v(r, k))
        if at:
            return at, how
    c = countries.get(v(r, "iso2"))
    if c:
        return (c[0], c[1]), f"the middle of {c[2]}: Wikidata gives no nearer place"
    return None, ""
