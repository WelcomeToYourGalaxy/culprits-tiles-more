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
# Companies Wikidata gives no place for: the address in a published document,
# placed where OpenStreetMap (Nominatim) finds that address.
ADDRESSES = {
    "Alpha Therapeutic Corporation": ("5555 Valley Boulevard, Los Angeles, CA 90032, USA",
        "the address on its letterhead, 23 February 1987 (Infected Blood Inquiry document KDUD0000001)",
        "https://www.infectedbloodinquiry.org.uk/sites/default/files/documents/KDUD0000001%20-%20Letter%20from%20Alpha%20Therapeutic%20Corporation%20to%20Pine%20Bluff%20Biological%20Products%20-%2023%20Feb%201987.pdf"),
}
UA = {"User-Agent": "WelcomeToYourGalaxy Culprits map (welcometoyourgalaxy@gmail.com)"}


def geocode(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            got = json.loads(r.read())
    except Exception:
        return None
    time.sleep(1.2)
    return (float(got[0]["lon"]), float(got[0]["lat"])) if got else None


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


def grid(table_html):
    """The table's rows as full grids: a cell spanning rows or columns
    (rowspan / colspan) is repeated in every row and column it covers, as a
    reader sees it. Round 129b: rows are no longer guessed by shifting cells
    to the left (a drug name was taken for the company when a middle column,
    not the company, spanned rows)."""
    out, pending = [], {}            # column -> [rows left, cell html]
    for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", table_html):
        row, col = [], 0
        cells = re.findall(r"(?is)<(t[dh])([^>]*)>(.*?)</\1>", tr)
        k = 0
        while k < len(cells) or col in pending:
            if col in pending:
                left, c = pending[col]
                row.append(c)
                if left <= 1:
                    del pending[col]
                else:
                    pending[col] = [left - 1, c]
                col += 1
                continue
            tag, attrs, body = cells[k]
            k += 1
            rs = re.search(r'rowspan\s*=\s*"?(\d+)', attrs)
            cs = re.search(r'colspan\s*=\s*"?(\d+)', attrs)
            for _ in range(int(cs.group(1)) if cs else 1):
                if rs and int(rs.group(1)) > 1:
                    pending[col] = [int(rs.group(1)) - 1, (tag, body)]
                row.append((tag, body))
                col += 1
        if row:
            out.append(row)
    return out


def cell_text(body):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<sup.*?</sup>", "", body)))).strip()


def cell_link(body):
    m = re.search(r'href="/wiki/([^"#]+)"', body)
    return urllib.parse.unquote(m.group(1)).replace("_", " ") if m else None


def settlement_rows():
    j = api(action="parse", page=SETTLEMENTS, prop="text", redirects=1)
    return table_rows(j["parse"]["text"])


def table_rows(page):
    rows = []
    for t in re.findall(r"(?is)<table[^>]*wikitable[^>]*>(.*?)</table>", page):
        g = grid(t)
        if not g:
            continue
        head = [cell_text(b) for _, b in g[0]]
        comp_col = next((i for i, h in enumerate(head) if re.search(r"compan|defendant|firm|manufacturer|corporation", h, re.I)), None)
        for r in g[1:]:
            if all(tag == "th" for tag, _ in r) and len(r) == len(head):
                continue                                  # a repeated heading row
            text = [cell_text(b) for _, b in r]
            links = [urllib.parse.unquote(h.split("#")[0]).replace("_", " ") for _, b in r for h in re.findall(r'href="/wiki/([^"]+)"', b)]
            company = comp_link = None
            if comp_col is not None and comp_col < len(r):
                company, comp_link = text[comp_col], cell_link(r[comp_col][1])
            elif comp_col is None:
                comp_i = next((i for i, (_, b) in enumerate(r) if 'href="/wiki/' in b), None)
                if comp_i is not None:
                    company, comp_link = text[comp_i], cell_link(r[comp_i][1])
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
    # Round 172b: Wikipedia links a company only the first time a table names
    # it, so its later rows (Pfizer, GlaxoSmithKline, AstraZeneca,
    # Schering-Plough...) came with no article and were left unplaced. They
    # take the article linked from the same name's other row; a name never
    # linked is looked up as a Wikipedia title of its own (redirects followed),
    # and stays unplaced if there is none.
    linked = {}
    for e in entries:
        if e.get("article"):
            linked.setdefault(e["name"], e["article"])
    for e in entries:
        if not e.get("article"):
            e["article"] = linked.get(e["name"]) or e["name"]
            e["article from"] = "the same company's linked row" if e["name"] in linked else "its name, as a Wikipedia title"
    q = qids([e["article"] for e in entries])
    at = places([q[e["article"]] for e in entries if e["article"] in q], countries)
    feats, unplaced = [], []
    for e in entries:
        item = q.get(e["article"])
        where = at.get(item) if item else None
        if (not where or not where[0]) and e["name"] in ADDRESSES:
            addr, said, doc = ADDRESSES[e["name"]]
            ll = geocode(addr)
            if ll:
                where = (ll, f"{addr}: {said}", addr, (where[3] if where else "") or "United States")
                e["rec"] = dict(e["rec"], **{"address source": doc})
        if not where or not where[0]:
            unplaced.append(e["name"])
            continue
        (lon, lat), how, hq, country = where
        props = dict({"name": e["name"], "group": GROUPS[e["part"]], "headquarters": hq, "country": country, "placed at": how,
                      "Wikipedia": f"https://en.wikipedia.org/wiki/{urllib.parse.quote((e['article'] or '').replace(' ', '_'))}" if e["article"] else "",
                      "Wikidata": f"https://www.wikidata.org/wiki/{item}", "source": e["source"],
                      "Wikipedia article found from": e.get("article from", "")}, **e["rec"])
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": {k: v for k, v in props.items() if v}})
    (OUT / "culprits.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    status.update({"placed": len(feats), "not_placed": unplaced})
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"medical_culprits: {len(feats)} placed; {len(dropped)} compiled entries not found in their articles; {len(unplaced)} not placed")
    if not feats:
        sys.exit("medical_culprits: nothing placed")


if __name__ == "__main__":
    main()
