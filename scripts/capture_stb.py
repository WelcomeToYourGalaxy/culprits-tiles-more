#!/usr/bin/env python3
"""
Czechoslovak StB registers matched to people who held office (round 112c, for
the Planted, bought or captured layer).

Slovakia's Nation's Memory Institute (ÚPN) publishes the StB and military
counter-intelligence registration books: 172,131 records, searchable by
surname, first name, cover name, birth date and category
(https://www.upn.gov.sk/projekty/regpro/). Most records are not collaborators:
the books also register people the StB watched (hostile person, checked
person) and files on places and groups. So this does not draw the whole
register. It takes everyone Wikidata records as holding an office who was a
citizen of Slovakia, the Czech Republic or Czechoslovakia and born before 1975,
searches the register for their surname and first name, and keeps a record
only when its birth date is the same as Wikidata's. Kept by category:

  archive tier   agent (A), informer (I), resident (R), secret collaborator
                 (TS), confidant (D)
  alleged tier   candidate agent (KA), candidate informer (KI), candidate for
                 secret collaboration (KTS): people the StB meant to recruit
  not drawn      hostile person (NO), checked person (PO) and the file kinds:
                 these are people the StB watched, not people who worked for it
                 (counted in capture/stb_build.json)

A search whose results give no birth date is not matched (listed in the build
file for a look). Resumable: a slice each day until every person is searched,
then again after 90 days.

  capture/stb.geojson   capture/stb_state.json   capture/stb_build.json

By hand: capture_stb.
"""
import datetime, html, json, os, pathlib, re, time, urllib.parse, urllib.request

OUT = pathlib.Path("capture")
UA = {"User-Agent": "Culprits atlas build (https://github.com/WelcomeToYourGalaxy/culprits-tiles-more; welcometoyourgalaxy@gmail.com)"}
SEARCH = "https://www.upn.gov.sk/projekty/regpro/vysledky-vyhladavania/?"
SPARQL = "https://query.wikidata.org/sparql"
BUDGET_S = 110 * 60
AGENT = {"A": "agent", "I": "informer", "R": "resident", "TS": "secret collaborator", "D": "confidant"}
CANDIDATE = {"KA": "candidate agent", "KI": "candidate informer", "KTS": "candidate for secret collaboration"}
TIERS = {"archive": "Named in opened secret-police or spy-service files", "alleged": "Charged or alleged, not proven"}
CAPITALS = {"Slovakia": (17.1077, 48.1486), "Czech Republic": (14.4205, 50.0875), "Czechoslovakia": (14.4205, 50.0875)}
BRANCH = [("courts", r"judge|justice|court|prosecutor|procurator"),
          ("lawmaking", r"member of|deputy|senator|parliament|assembly|council|legislat"),
          ("ruling and running", r"president|prime minister|minister|mayor|governor|ambassador|director|chair|head of|secretary")]


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise last


def office_holders():
    q = """SELECT ?p ?pLabel ?given ?family ?birth ?citLabel (GROUP_CONCAT(DISTINCT ?posL; separator="|") AS ?offices) ?art WHERE {
      VALUES ?cit { wd:Q214 wd:Q213 wd:Q33946 }
      ?p wdt:P31 wd:Q5; wdt:P27 ?cit; wdt:P39 ?pos; wdt:P569 ?birth. FILTER(YEAR(?birth) < 1975)
      OPTIONAL { ?p wdt:P735/rdfs:label ?given FILTER(LANG(?given) IN ("sk", "cs", "mul", "en")) }
      OPTIONAL { ?p wdt:P734/rdfs:label ?family FILTER(LANG(?family) IN ("sk", "cs", "mul", "en")) }
      OPTIONAL { ?pos rdfs:label ?posL FILTER(LANG(?posL) = "en") }
      OPTIONAL { ?art schema:about ?p; schema:isPartOf <https://sk.wikipedia.org/> }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "sk,cs,mul,en". ?p rdfs:label ?pLabel. ?cit rdfs:label ?citLabel. }
    } GROUP BY ?p ?pLabel ?given ?family ?birth ?citLabel ?art"""
    req = urllib.request.Request(SPARQL, data=urllib.parse.urlencode({"query": q, "format": "json"}).encode(),
                                 headers=dict(UA, Accept="application/sparql-results+json"))
    rows = json.loads(urllib.request.urlopen(req, timeout=320).read())["results"]["bindings"]
    people = {}
    for b in rows:
        g = lambda k: b.get(k, {}).get("value", "")
        qid = g("p").rsplit("/", 1)[-1]
        d = people.setdefault(qid, {"qid": qid, "name": g("pLabel"), "given": g("given"), "family": g("family"), "birth": g("birth")[:10],
                                    "country": g("citLabel"), "offices": g("offices"), "article": g("art")})
        if not d["given"] and g("given"):
            d["given"] = g("given")
        if not d["family"] and g("family"):
            d["family"] = g("family")
    for d in people.values():
        if not d["family"]:
            parts = d["name"].split()
            if len(parts) >= 2:
                d["given"], d["family"] = d["given"] or parts[0], parts[-1]
    return [d for d in people.values() if d["family"]]


def rows_of(page):
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    tables = re.findall(r"(?is)<table[^>]*>(.*?)</table>", body)
    out = []
    for t in tables:
        header = []
        for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", t):
            cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in re.findall(r"(?is)<t[hd][^>]*>(.*?)</t[hd]>", tr)]
            if re.search(r"(?is)<th", tr) and not header:
                header = cells
                continue
            if cells:
                out.append(dict(zip(header, cells)) if header and len(header) == len(cells) else {f"column {i + 1}": c for i, c in enumerate(cells)})
    return out


def same_birth(row, iso):
    y, m, d = (int(x) for x in iso.split("-"))
    for dd, mm, yy in re.findall(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", " ".join(row.values())):
        if (int(dd), int(mm), int(yy)) == (d, m, y):
            return True
    return False


def has_date(row):
    return bool(re.search(r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}", " ".join(row.values())))


CODES = r"KTS|KA|KI|TS|A|I|R|D|PO|NO|KB|PB|S|OZ|OB|SKZ|APZ|EZ|K|VOZ|P|PZ|ZPS"


def category(row):
    """The record's category, from the column headed as such, else from a cell
    that is nothing but a category code."""
    for k, val in row.items():
        if re.search(r"kateg|druh|typ", k, re.I):
            m = re.search(r"\b(" + CODES + r")\b", val)
            if m:
                return m.group(1)
    for val in row.values():
        m = re.fullmatch(r"\s*\(?(" + CODES + r")\)?\s*", val)
        if m:
            return m.group(1)
    return ""


def branch(offices):
    for k, rx in BRANCH:
        if re.search(rx, offices or "", re.I):
            return k
    return "other office"


def main():
    OUT.mkdir(exist_ok=True)
    sp = OUT / "stb_state.json"
    st = json.loads(sp.read_text()) if sp.exists() else {"people": None, "done": 0, "matches": {}, "counts": {}, "no_dates": []}
    if st.get("finished"):
        if (datetime.date.today() - datetime.date.fromisoformat(st["finished"])).days < 90 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
            print("capture_stb: every person searched; next pass after 90 days")
            return
        st.update({"people": None, "done": 0, "finished": None})
    if not st["people"]:
        st["people"] = office_holders()
        st["done"] = 0
        print(f"capture_stb: {len(st['people'])} office holders to search", flush=True)
    started = time.time()
    while st["done"] < len(st["people"]) and time.time() - started < BUDGET_S:
        p = st["people"][st["done"]]
        url = SEARCH + urllib.parse.urlencode({"kraj": "", "priezvisko": p["family"], "meno": p["given"], "krycie_meno": "", "datum_narodenia": "", "kategoria": ""})
        try:
            rows = rows_of(get(url))
        except Exception as e:  # noqa: BLE001
            st["counts"]["search failed"] = st["counts"].get("search failed", 0) + 1
            print(f"  {p['name']}: {type(e).__name__}: {e}", flush=True)
            rows = []
        if rows and not any(has_date(r) for r in rows) and len(st["no_dates"]) < 200:
            st["no_dates"].append({"person": p["name"], "url": url, "first row": rows[0]})
        for r in rows:
            if not same_birth(r, p["birth"]):
                continue
            c = category(r)
            kind = "archive" if c in AGENT else "alleged" if c in CANDIDATE else None
            st["counts"][c or "no category read"] = st["counts"].get(c or "no category read", 0) + 1
            if kind:
                st["matches"].setdefault(p["qid"], {"person": p, "records": []})["records"].append({"category": c, "kind": kind, "row": r, "url": url})
        st["done"] += 1
        if st["done"] % 25 == 0:
            sp.write_text(json.dumps(st, ensure_ascii=False))
        time.sleep(1.2)
    if st["done"] >= len(st["people"]):
        st["finished"] = datetime.date.today().isoformat()
    sp.write_text(json.dumps(st, ensure_ascii=False))
    feats = []
    for qid, m in st["matches"].items():
        p, recs = m["person"], m["records"]
        kind = "archive" if any(r["kind"] == "archive" for r in recs) else "alleged"
        names = [AGENT.get(r["category"]) or CANDIDATE.get(r["category"]) for r in recs]
        props = {"name": p["name"], "group": TIERS[kind], "branch": branch(p["offices"]), "working for or tied to": "StB (Czechoslovak secret police) or military counter-intelligence",
                 "offices held (Wikidata)": p["offices"].replace("|", "; "), "date of birth (Wikidata and the register agree)": p["birth"], "citizenship": p["country"],
                 "registered as": "; ".join(sorted(set(n for n in names if n))),
                 "note": ("The StB's registration book lists this person, with the same name and birth date as Wikidata's record, as " + ", ".join(sorted(set(n for n in names if n))) + ". A registration is the StB's own record, not a court finding; Slovak courts have heard challenges to some."
                          if kind == "archive" else "Registered only as a candidate: someone the StB meant to recruit, not a collaborator."),
                 "Wikidata": f"https://www.wikidata.org/wiki/{qid}", "Wikipedia": p["article"], "ÚPN search": recs[0]["url"],
                 "source": "Nation's Memory Institute (ÚPN), StB registration books, matched to Wikidata by name and birth date, read " + datetime.date.today().isoformat(),
                 "placed at": "the capital of their country of citizenship", "part": "stb"}
        for i, r in enumerate(recs, 1):
            for k, v in r["row"].items():
                props[f"register record {i}: {k}"] = v
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(CAPITALS.get(p["country"], CAPITALS["Slovakia"]))}, "properties": props})
    (OUT / "stb.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "stb_build.json").write_text(json.dumps({"read": datetime.date.today().isoformat(), "people": len(st["people"] or []), "searched": st["done"],
                                                     "finished": st.get("finished"), "matched by name and birth date": st["counts"], "drawn": len(feats),
                                                     "searches whose results gave no birth date": st["no_dates"][:50]}, indent=1, ensure_ascii=False))
    print(f"capture_stb: searched {st['done']} of {len(st['people'])}; {len(feats)} drawn", flush=True)


if __name__ == "__main__":
    main()
