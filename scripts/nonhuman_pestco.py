#!/usr/bin/env python3
"""
The largest pesticide companies, their headquarters and the companies they
own, for the Invasion of non-humans map.

The companies are the ten the owner's page names (footnote 22, from
reportsanddata.com): BASF, Bayer, Sumitomo Chemical, Syngenta, UPL, Adama,
Kumiai Chemical Industry, Nissan Chemical, Nufarm and Jiangsu Yangnong
Chemical. Each is found on Wikidata (CC0) by the item below, checked by its
English label; a company with no item given is searched for by name, and the
build file says what was found. For each: its headquarters (P159) placed by
the coordinates on that statement, else the headquarters place's own
coordinates; else the company's own coordinate location (P625). Then every
company Wikidata records as owned by it (P355 subsidiary, or P749 parent
organisation pointing at it), two steps down, placed the same way. A company
with no place at all is listed in the build file, not drawn.

  nonhuman/pesticide_companies.geojson, nonhuman/pestco.build.json

Weekly; PESTCO_REBUILD=1 or a run by hand builds at once.
"""
import json, pathlib, re, sys, time, urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "pestco"
SPARQL = "https://query.wikidata.org/sparql"
WD = "https://www.wikidata.org/w/api.php"
COMPANIES = [
    ("BASF", ["Q9401"], r"basf"),
    ("Bayer", ["Q152051"], r"bayer"),
    ("Sumitomo Chemical", ["Q137803"], r"sumitomo chemical"),
    ("Syngenta", ["Q688613"], r"syngenta"),
    ("UPL", ["Q98033901", "Q65083411"], r"\bupl\b|united phosphorus"),
    ("Adama", ["Q903943"], r"adama"),
    ("Kumiai Chemical Industry", ["Q11298808"], r"kumiai"),
    ("Nissan Chemical", ["Q7040930"], r"nissan chemical"),
    ("Nufarm", ["Q900401"], r"nufarm"),
    ("Jiangsu Yangnong Chemical", [], r"yangnong"),
]


def sparql(q):
    for i in range(5):
        try:
            return nh.get_json(SPARQL + "?" + urllib.parse.urlencode({"query": q, "format": "json"}), timeout=120, tries=1)["results"]["bindings"]
        except Exception as e:
            print(f"  query failed ({e}); waiting", flush=True)
            time.sleep(15 * (i + 1))
    raise RuntimeError("Wikidata's query service did not answer")


def qid(uri):
    return uri.rsplit("/", 1)[-1] if uri else None


def point(wkt):
    m = re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", wkt or "")
    return (float(m.group(1)), float(m.group(2))) if m else None


def labels(ids):
    if not ids:
        return {}
    j = nh.get_json(WD + "?" + urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|claims", "languages": "en", "format": "json"}))
    return j.get("entities", {})


def search(name):
    j = nh.get_json(WD + "?" + urllib.parse.urlencode({"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 10, "format": "json"}))
    return [(r["id"], r.get("label", ""), r.get("description", "")) for r in j.get("search", [])]


def places(items):
    """For each item: label, its HQ (label, coords from the statement or the
    place) and its own coordinates; its country."""
    vals = " ".join(f"wd:{i}" for i in items)
    q = f"""SELECT ?co ?coLabel ?hq ?hqLabel ?stc ?hqc ?own ?country ?countryLabel WHERE {{
  VALUES ?co {{ {vals} }}
  OPTIONAL {{ ?co p:P159 ?st . ?st ps:P159 ?hq . OPTIONAL {{ ?st pq:P625 ?stc }} OPTIONAL {{ ?hq wdt:P625 ?hqc }} }}
  OPTIONAL {{ ?co wdt:P625 ?own }}
  OPTIONAL {{ ?co wdt:P17 ?country }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}"""
    out = {}
    for b in sparql(q):
        g = lambda k: (b.get(k) or {}).get("value")
        i = qid(g("co"))
        e = out.setdefault(i, {"label": g("coLabel"), "hq": None, "country": g("countryLabel"), "where": None, "placed": None})
        for k, how in (("stc", "coordinates given on its headquarters statement"), ("hqc", "its headquarters place's coordinates"), ("own", "the company's own coordinate location")):
            pt = point(g(k))
            if pt and (e["where"] is None or ["coordinates given on its headquarters statement", "its headquarters place's coordinates", "the company's own coordinate location"].index(how) <
                       ["coordinates given on its headquarters statement", "its headquarters place's coordinates", "the company's own coordinate location"].index(e["placed"])):
                e["where"], e["placed"] = pt, how
                if k != "own":
                    e["hq"] = g("hqLabel")
        if not e["hq"] and g("hqLabel"):
            e["hq"] = g("hqLabel")
    return out


def owned(items):
    vals = " ".join(f"wd:{i}" for i in items)
    q = f"""SELECT DISTINCT ?parent ?sub WHERE {{
  VALUES ?parent {{ {vals} }}
  {{ ?parent wdt:P355 ?sub }} UNION {{ ?sub wdt:P749 ?parent }} }}"""
    pairs = []
    for b in sparql(q):
        pairs.append((qid(b["parent"]["value"]), qid(b["sub"]["value"])))
    return pairs


def main():
    if not nh.due(NAME, 7, "PESTCO_REBUILD"):
        return
    found, notes = {}, {}
    for name, ids, pat in COMPANIES:
        ents = labels(ids)
        ok = [i for i in ids if re.search(pat, ((ents.get(i, {}).get("labels") or {}).get("en") or {}).get("value", ""), re.I)]
        # Of two candidate items, the one Wikidata gives a headquarters.
        ok.sort(key=lambda i: "P159" not in (ents.get(i, {}).get("claims") or {}))
        if not ok:
            hits = [h for h in search(name) if re.search(pat, h[1], re.I)]
            notes[name] = {"searched": hits[:5]}
            ok = [hits[0][0]] if hits else []
        if ok:
            found[name] = ok[0]
            notes.setdefault(name, {})["item"] = ok[0]
        else:
            notes.setdefault(name, {})["item"] = None
    top = list(found.values())
    level1 = owned(top)
    subs1 = sorted({s for _, s in level1} - set(top))
    level2 = owned(subs1) if subs1 else []
    subs2 = sorted({s for _, s in level2} - set(top) - set(subs1))
    allids = top + subs1 + subs2
    info = {}
    for i in range(0, len(allids), 150):
        info.update(places(allids[i:i + 150]))
    parent = {}
    for p, s in level1 + level2:
        parent.setdefault(s, p)
    group_of = {v: k for k, v in found.items()}

    def group(i, seen=()):
        if i in group_of:
            return group_of[i]
        p = parent.get(i)
        return group(p, seen + (i,)) if p and p not in seen else None

    feats, unplaced = [], []
    for i in allids:
        e = info.get(i) or {}
        props = {"name": e.get("label") or i, "qid": i, "role": "company" if i in group_of else "subsidiary",
                 "group": group(i), "parent": (info.get(parent.get(i)) or {}).get("label") if parent.get(i) else None,
                 "hq": e.get("hq"), "country": e.get("country"), "placed": e.get("placed")}
        if e.get("where"):
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(e["where"])}, "properties": {k: v for k, v in props.items() if v is not None}})
        else:
            unplaced.append(props)
    (nh.OUT).mkdir(parents=True, exist_ok=True)
    (nh.OUT / "pesticide_companies.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    nh.write_stamp(NAME, {"companies": notes, "owned, first step": len(subs1), "owned, second step": len(subs2), "placed": len(feats),
                          "no place on Wikidata (not drawn)": unplaced, "failed": not feats})


if __name__ == "__main__":
    main()
