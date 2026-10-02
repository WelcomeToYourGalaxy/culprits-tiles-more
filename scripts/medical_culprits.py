#!/usr/bin/env python3
"""
Who is most to blame for what the Suppression page's medical section names
(round 114b, asked 29 September: "map the entities most guilty of the
subjects discussed in the first half of the medical industry section"):
doctors paid to prescribe, drugs pushed for profit (addictive ones above
all), illegal marketing and kickbacks, and the blood products sold with HIV
in them.

Three parts, each marked in the box:
  1. settlements  every row of Wikipedia's "List of largest pharmaceutical
                  settlements" (illegal marketing, off-label promotion,
                  kickbacks to doctors, false claims ...), every column
                  kept, the company placed at its headquarters;
  2. opioids      the makers, distributors, pharmacies and consultants of the
                  US opioid epidemic found liable, convicted or settling, as
                  Wikipedia's articles name them;
  3. blood        the companies that sold clotting products contaminated with
                  HIV in the 1980s, as Wikipedia's article names them.
Parts 2 and 3 are a list compiled for this map, and every entry is kept only
if its name is found in the Wikipedia article cited for it when this runs;
anything not found is left out and named in medical/build.json. Places:
each company's headquarters from Wikidata (through its Wikipedia article),
else its country; the box says which.

  medical/culprits.geojson
  medical/build.json

Weekly (Mondays) or by hand.
"""
import datetime, html, json, os, pathlib, re, sys, time, urllib.parse, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import wdtools as W  # noqa: E402

OUT = pathlib.Path("medical")
API = "https://en.wikipedia.org/w/api.php"
SETTLEMENTS = "List of largest pharmaceutical settlements"
OPIOIDS = "Opioid epidemic in the United States"
BLOOD = "Contaminated haemophilia blood products"
# (name as the article writes it, the entity's own article, what the cited article is, the part)
COMPILED = [
    ("Purdue Pharma", "Purdue Pharma", OPIOIDS, "opioids"),
    ("Sackler", "Sackler family", OPIOIDS, "opioids"),
    ("Insys", "Insys Therapeutics", OPIOIDS, "opioids"),
    ("Johnson & Johnson", "Johnson & Johnson", OPIOIDS, "opioids"),
    ("McKesson", "McKesson Corporation", OPIOIDS, "opioids"),
    ("Cardinal Health", "Cardinal Health", OPIOIDS, "opioids"),
    ("AmerisourceBergen", "Cencora", OPIOIDS, "opioids"),
    ("Teva", "Teva Pharmaceuticals", OPIOIDS, "opioids"),
    ("Allergan", "Allergan", OPIOIDS, "opioids"),
    ("Mallinckrodt", "Mallinckrodt", OPIOIDS, "opioids"),
    ("Endo", "Endo International", OPIOIDS, "opioids"),
    ("CVS", "CVS Health", OPIOIDS, "opioids"),
    ("Walgreens", "Walgreens", OPIOIDS, "opioids"),
    ("Walmart", "Walmart", OPIOIDS, "opioids"),
    ("McKinsey", "McKinsey & Company", OPIOIDS, "opioids"),
    ("Cutter", "Cutter Laboratories", BLOOD, "blood"),
    ("Bayer", "Bayer", BLOOD, "blood"),
    ("Baxter", "Baxter International", BLOOD, "blood"),
    ("Alpha Therapeutic", "Alpha Therapeutic Corporation", BLOOD, "blood"),
    ("Armour", "Armour Pharmaceutical Company", BLOOD, "blood"),
]
GROUPS = {"settlements": "Paid to settle illegal marketing, kickbacks or false claims", "opioids": "Named in the opioid epidemic's convictions and settlements",
          "blood": "Sold blood products contaminated with HIV"}


def api(**params):
    params = dict(params, format="json", formatversion="2")
    for i in range(4):
        try:
            return json.loads(W.get(API + "?" + urllib.parse.urlencode(params), timeout=120))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise last


def plain(title):
    j = api(action="query", prop="extracts", explaintext=1, titles=title, redirects=1)
    return ((j.get("query") or {}).get("pages") or [{}])[0].get("extract", "")


def qids(titles):
    out = {}
    titles = list(dict.fromkeys(t for t in titles if t))
    for i in range(0, len(titles), 40):
        j = api(action="query", prop="pageprops", ppprop="wikibase_item", titles="|".join(titles[i:i + 40]), redirects=1)
        q = j.get("query") or {}
        back = {r["to"]: r["from"] for r in q.get("redirects", [])}
        back.update({n["to"]: n["from"] for n in q.get("normalized", [])})
        for p in q.get("pages", []):
            item = (p.get("pageprops") or {}).get("wikibase_item")
            if item:
                t = p["title"]
                out[t] = item
                while t in back:
                    t = back[t]
                    out[t] = item
    return out


def places(items, countries):
    """Wikidata items -> ((lon, lat), how, hq, country)."""
    out = {}
    items = list(dict.fromkeys(items))
    for i in range(0, len(items), 80):
        vals = " ".join(f"wd:{q}" for q in items[i:i + 80])
        rows = W.sparql(f"""SELECT ?item ?own ?hqc ?hqLabel ?iso2 ?countryLabel WHERE {{
          VALUES ?item {{ {vals} }}
          OPTIONAL {{ ?item wdt:P625 ?own. }}
          OPTIONAL {{ ?item wdt:P159 ?hq. OPTIONAL {{ ?hq wdt:P625 ?hqc. }} }}
          OPTIONAL {{ ?item wdt:P17 ?country. OPTIONAL {{ ?country wdt:P297 ?iso2. }} }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}""")
        for r in rows:
            q = W.qid(W.v(r, "item"))
            if q in out and out[q][0]:
                continue
            at, how = W.place_row(r, countries)
            out[q] = (at, how, W.v(r, "hqLabel"), W.v(r, "countryLabel"))
    return out


def settlement_rows():
    j = api(action="parse", page=SETTLEMENTS, prop="text", redirects=1)
    page = j["parse"]["text"]
    rows = []
    for t in re.findall(r"(?is)<table[^>]*wikitable[^>]*>(.*?)</table>", page):
        head = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                for c in re.findall(r"(?is)<th[^>]*>(.*?)</th>", t.split("</tr>")[0])]
        last, prev = None, []
        for tr in t.split("</tr>")[1:]:
            cells = re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)
            if not cells:
                continue
            text = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<sup.*?</sup>", "", c)))).strip() for c in cells]
            links = [urllib.parse.unquote(h.split("#")[0]).replace("_", " ") for c in cells for h in re.findall(r'href="/wiki/([^"]+)"', c)]
            # Round 123b: the company is read from the table's own Company
            # column (the first linked cell was often a drug: "Neurontin",
            # "Zoladex"). A row with fewer cells than headings sits under a
            # company cell that spans several rows: it is that company's.
            comp_col = next((i for i, h in enumerate(head) if re.search(r"compan|defendant|firm|manufacturer|corporation", h, re.I)), None)
            company = comp_link = None
            if comp_col is not None and len(text) == len(head):
                company = text[comp_col]
                m = re.search(r'href="/wiki/([^"#]+)"', cells[comp_col])
                comp_link = urllib.parse.unquote(m.group(1)).replace("_", " ") if m else None
                last = (company, comp_link)
            elif comp_col is not None and len(text) < len(head):
                # Cells spanning rows are the leftmost ones: this row's cells
                # are the right-hand headings; the missing ones are carried down.
                shift = len(head) - len(text)
                if comp_col >= shift:
                    company = text[comp_col - shift]
                    m = re.search(r'href="/wiki/([^"#]+)"', cells[comp_col - shift])
                    comp_link = urllib.parse.unquote(m.group(1)).replace("_", " ") if m else None
                    last = (company, comp_link)
                elif last:
                    company, comp_link = last
                text = (prev[:shift] if len(prev) >= shift else [""] * shift) + text
            elif comp_col is None:
                comp_i = next((i for i, c in enumerate(cells) if re.search(r'href="/wiki/', c)), None)
                if comp_i is not None:
                    company = text[comp_i]
                    m = re.search(r'href="/wiki/([^"#]+)"', cells[comp_i])
                    comp_link = urllib.parse.unquote(m.group(1)).replace("_", " ") if m else None
            prev = text
            rec = dict(zip(head, text)) if len(head) == len(text) else {f"column {i + 1}": c for i, c in enumerate(text)}
            rows.append({"rec": rec, "company": company or "", "article": comp_link, "links": links})
    return rows


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("medical_culprits: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    status = {"date": datetime.date.today().isoformat()}
    countries = W.country_points()
    entries = []
    try:
        rows = settlement_rows()
        status["settlements"] = {"rows": len(rows), "columns": sorted({k for r in rows for k in r["rec"]})}
        for r in rows:
            if r["company"]:
                entries.append({"part": "settlements", "name": r["company"], "article": r["article"], "rec": r["rec"],
                                "source": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(SETTLEMENTS.replace(' ', '_'))}"})
        print(f"medical_culprits: settlements {len(rows)} rows", flush=True)
    except Exception as e:  # noqa: BLE001
        status["settlements"] = f"not read ({e})"
    texts, dropped = {}, []
    for name, article, cited, part in COMPILED:
        if cited not in texts:
            try:
                texts[cited] = plain(cited)
            except Exception as e:  # noqa: BLE001
                texts[cited] = ""
                status[f"article {cited}"] = f"not read ({e})"
        word = re.compile(r"\b" + re.escape(name) + r"\b", re.I)
        if not word.search(texts[cited]):
            dropped.append(f"{name} (not found in {cited})")
            continue
        # The sentences of the cited article that name it, as the box's own words.
        said = [s.strip() for s in re.split(r"(?<=[.!?])\s+", texts[cited]) if word.search(s)][:4]
        entries.append({"part": part, "name": article, "article": article, "rec": {"what the article says": " ".join(said)},
                        "source": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(cited.replace(' ', '_'))}"})
    status["compiled_left_out"] = dropped
    q = qids([e["article"] for e in entries])
    at = places([q[e["article"]] for e in entries if e["article"] in q], countries)
    feats, unplaced = [], []
    for e in entries:
        item = q.get(e["article"])
        where = at.get(item) if item else None
        if not where or not where[0]:
            unplaced.append(e["name"])
            continue
        (lon, lat), how, hq, country = where
        props = dict({"name": e["name"], "group": GROUPS[e["part"]], "headquarters": hq, "country": country, "placed at": how,
                      "Wikipedia": f"https://en.wikipedia.org/wiki/{urllib.parse.quote((e['article'] or '').replace(' ', '_'))}" if e["article"] else "",
                      "Wikidata": f"https://www.wikidata.org/wiki/{item}", "source": e["source"]}, **e["rec"])
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {k: v for k, v in props.items() if v}})
    (OUT / "culprits.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    status.update({"placed": len(feats), "not_placed": unplaced})
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"medical_culprits: {len(feats)} placed; {len(dropped)} compiled entries not found in their articles; {len(unplaced)} not placed")
    if not feats:
        sys.exit("medical_culprits: nothing placed")


if __name__ == "__main__":
    main()
