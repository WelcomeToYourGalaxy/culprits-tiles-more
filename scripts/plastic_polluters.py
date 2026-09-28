#!/usr/bin/env python3
"""
The World's Worst Plastic Polluters, where they are (round 95b, asked 27
September, in place of the Break Free From Plastic brand audit page).

Break Free From Plastic's Brand Audit 2023 (250 audits by 8,804 volunteers in
41 countries; 537,719 pieces of plastic waste traced to 6,858 brands of 3,810
parent companies) names the ten parent companies whose branded plastic was
found most: The Coca-Cola Company, Nestlé, Unilever, PepsiCo, Mondelēz
International, Mars, Procter & Gamble, Danone, Altria and British American
Tobacco (https://brandaudit.breakfreefromplastic.org/brand-audit-2023/). The
audit publishes no locations; this maps where each company is:

  1. Its headquarters, and its subsidiaries' headquarters, from Wikidata
     (P159 headquarters location, P625 coordinates; subsidiaries by P355 and
     P749 parent organisation, one level).
  2. Its plants, bottling works, warehouses and offices mapped in
     OpenStreetMap: works, factories, industrial land and offices whose name,
     operator or brand names the company or its best-known brand names.

  plastic/polluters.geojson   group = the company; rank = its place in the list;
                              kind = headquarters, subsidiary headquarters or
                              the OpenStreetMap feature's own kind
  plastic/build.json          counts by company and source

Weekly (Mondays), or by hand.
"""
import datetime, json, os, pathlib, re, sys, time, urllib.parse, urllib.request

OUT = pathlib.Path("plastic")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
# rank, name, the name Wikidata is searched for, words that name it in OpenStreetMap
COMPANIES = [
    (1, "The Coca-Cola Company", "The Coca-Cola Company", r"coca[- ]?cola"),
    (2, "Nestlé", "Nestlé", r"nestl[eé]"),
    (3, "Unilever", "Unilever", r"unilever"),
    (4, "PepsiCo", "PepsiCo", r"pepsico|pepsi[- ]cola|frito[- ]lay"),
    (5, "Mondelēz International", "Mondelez International", r"mondel[eē]z|cadbury"),
    (6, "Mars, Inc.", "Mars Incorporated", r"mars (inc|incorporated|wrigley|petcare|food)|wrigley|royal canin"),
    (7, "Procter & Gamble", "Procter & Gamble", r"procter ?(&|and) ?gamble|\bp ?& ?g\b"),
    (8, "Danone", "Danone", r"danone"),
    (9, "Altria", "Altria", r"altria|philip morris usa"),
    (10, "British American Tobacco", "British American Tobacco", r"british american tobacco|\bbat\b (plc|factory)"),
]
SPARQL = "https://query.wikidata.org/sparql"


def get(url, data=None, timeout=300, headers=None):
    req = urllib.request.Request(url, headers=dict(UA, **(headers or {})), data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def find_qid(label):
    """The company's Wikidata item: the first search result described as a
    company, corporation or conglomerate (the item chosen is written to the log)."""
    j = json.loads(get("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "wbsearchentities", "search": label, "language": "en", "type": "item", "limit": 10, "format": "json"})))
    for r in j.get("search", []):
        if re.search(r"company|corporation|conglomerate|multinational|manufacturer|holding", r.get("description", ""), re.I):
            print(f"  {label}: {r['id']} ({r.get('description')})", flush=True)
            return r["id"]
    raise LookupError(f"no company item found for {label}")


def wikidata(label):
    qid = find_qid(label)
    q = f"""SELECT DISTINCT ?org ?orgLabel ?place ?placeLabel ?coord ?rel WHERE {{
      {{ BIND(wd:{qid} AS ?org) BIND("headquarters" AS ?rel) }}
      UNION {{ wd:{qid} wdt:P355 ?org. BIND("subsidiary headquarters" AS ?rel) }}
      UNION {{ ?org wdt:P749 wd:{qid}. BIND("subsidiary headquarters" AS ?rel) }}
      ?org wdt:P159 ?place.
      OPTIONAL {{ ?org p:P159/pq:P625 ?q1 }}
      OPTIONAL {{ ?place wdt:P625 ?q2 }}
      BIND(COALESCE(?q1, ?q2) AS ?coord)
      FILTER(BOUND(?coord))
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}"""
    j = json.loads(get(SPARQL + "?" + urllib.parse.urlencode({"query": q, "format": "json"}), headers={"Accept": "application/sparql-results+json"}))
    out = []
    for b in j["results"]["bindings"]:
        m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", b["coord"]["value"])
        if not m:
            continue
        out.append({"lon": float(m.group(1)), "lat": float(m.group(2)), "name": b["orgLabel"]["value"], "kind": b["rel"]["value"],
                    "place": b.get("placeLabel", {}).get("value", ""), "source": "Wikidata", "link": b["org"]["value"]})
    return out


def osm(words):
    rx = words.replace('"', "")
    q = f"""[out:json][timeout:900];
(
  nwr["man_made"="works"]["name"~"{rx}",i];
  nwr["man_made"="works"]["operator"~"{rx}",i];
  nwr["industrial"]["name"~"{rx}",i];
  nwr["industrial"]["operator"~"{rx}",i];
  nwr["building"~"industrial|factory|warehouse|office"]["name"~"{rx}",i];
  nwr["landuse"="industrial"]["name"~"{rx}",i];
  nwr["office"]["name"~"{rx}",i];
  nwr["office"]["brand"~"{rx}",i];
);
out center tags;"""
    j = json.loads(get("https://overpass-api.de/api/interpreter", data=urllib.parse.urlencode({"data": q}).encode(), timeout=1000))
    out = []
    for e in j.get("elements", []):
        c = e.get("center") or e
        if "lat" not in c:
            continue
        t = e.get("tags", {})
        kind = t.get("man_made") and "works" or t.get("industrial") and f"industrial: {t['industrial']}" or t.get("office") and "office" or t.get("building") or t.get("landuse") or "place"
        out.append({"lon": c["lon"], "lat": c["lat"], "name": t.get("name") or t.get("operator") or "", "kind": kind,
                    "place": ", ".join(t[k] for k in ("addr:city", "addr:country") if t.get(k)), "source": "OpenStreetMap",
                    "link": f"https://www.openstreetmap.org/{e['type']}/{e['id']}"})
    return out


def main():
    stamp_p = OUT / "build.json"
    if stamp_p.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("plastic_polluters: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    feats, counts = [], {}
    for rank, name, qid, words in COMPANIES:
        got = {}
        for label, job in (("Wikidata", lambda: wikidata(qid)), ("OpenStreetMap", lambda: osm(words))):
            try:
                rows = job()
            except Exception as e:  # noqa: BLE001
                got[label] = f"did not answer ({type(e).__name__}: {e})"
                continue
            got[label] = len(rows)
            for r in rows:
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(r["lon"], 6), round(r["lat"], 6)]},
                              "properties": {"name": r["name"] or name, "group": name, "rank": rank, "kind": r["kind"], "place": r["place"],
                                             "source": r["source"], "link": r["link"],
                                             "audit": "Break Free From Plastic Brand Audit 2023: number " + str(rank) + " of the World's Worst Plastic Polluters"}})
            time.sleep(2)
        counts[name] = got
        print(f"plastic_polluters: {name}: {got}", flush=True)
    if not feats:
        sys.exit("plastic_polluters: nothing found")
    (OUT / "polluters.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    stamp_p.write_text(json.dumps({"read": datetime.date.today().isoformat(), "features": len(feats), "by_company": counts,
                                   "audit": "https://brandaudit.breakfreefromplastic.org/brand-audit-2023/"}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
