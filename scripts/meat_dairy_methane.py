#!/usr/bin/env python3
"""
Methane from 15 of the largest meat and dairy companies (round 189o, asked
8 October; the authors said the map may use it).

Emissions Impossible: Methane Edition (Institute for Agriculture and Trade
Policy and Changing Markets Foundation, 15 November 2022): the report's own
dataset workbook, every sheet of it, kept as methane/emissions_impossible/
dataset.json (the cells as the workbook holds them). The estimates are the
authors': each company's animals processed or milk taken in (Tab 4, with the
company report or IFCN source for each), times FAO GLEAM 2.0 average emissions
for that product in that region.

Each company is one point at its headquarters as Wikidata gives it (through
its Wikipedia article), else its country; the box says which. Its box holds
every row of every table in the workbook that names it, with the table's own
headings and units. Every sheet, whole, is in the row's "read them" window.

  methane/meat_dairy.places.geojson, methane/meat_dairy.boxes.json,
  methane/meat_dairy.build.json

Daily with the refresh, or by hand. Nothing changes unless Wikidata does.
"""
import hashlib, html, json, math, pathlib, sys, time, urllib.parse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import wdtools as W  # noqa: E402

ROW = "methane_meat_dairy"
DIR = pathlib.Path("methane")
DATA = DIR / "emissions_impossible" / "dataset.json"
API = "https://en.wikipedia.org/w/api.php"
REPORT = "https://www.iatp.org/emissions-impossible-methane-edition"
PDF = "https://www.iatp.org/sites/default/files/2022-11/Emissions%20Impossible_Methane%20Edition_%20FINAL.pdf"
CITE = ("Emissions Impossible: Methane Edition, Institute for Agriculture and Trade Policy (IATP) and "
        "Changing Markets Foundation, 15 November 2022, dataset workbook; used with the authors' agreement")
# The workbook's company names -> each company's Wikipedia article (for its Wikidata headquarters).
ARTICLES = {
    "Tyson": "Tyson Foods", "Danish Crown": "Danish Crown", "WH Group": "WH Group", "JBS": "JBS S.A.",
    "Marfrig": "Marfrig", "Fonterra": "Fonterra", "Dairy Farmers of America": "Dairy Farmers of America",
    "Lactalis": "Lactalis", "Nestlé": "Nestlé", "Arla": "Arla Foods", "FrieslandCampina": "FrieslandCampina",
    "Danone": "Danone", "DMK": "Deutsches Milchkontor", "Saputo": "Saputo Inc.", "Yili": "Yili Group",
}
KINDS = {"meat": ("Meat company", "#1A5C92"), "milk": ("Dairy company", "#6FC2DA")}


def api(**params):
    params = dict(params, format="json", formatversion="2")
    last = None
    for i in range(4):
        try:
            return json.loads(W.get(API + "?" + urllib.parse.urlencode(params), timeout=120))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise last


def qids(titles):
    j = api(action="query", prop="pageprops", ppprop="wikibase_item", titles="|".join(titles), redirects=1)
    q = j.get("query") or {}
    back = {r["to"]: r["from"] for r in q.get("redirects", [])}
    back.update({n["to"]: n["from"] for n in q.get("normalized", [])})
    out = {}
    for p in q.get("pages", []):
        item = (p.get("pageprops") or {}).get("wikibase_item")
        t = p.get("title")
        while item and t:
            out[t] = item
            t = back.get(t)
    return out


def places(items, countries):
    vals = " ".join(f"wd:{q}" for q in items)
    rows = W.sparql(f"""SELECT ?item ?own ?hqc ?hqLabel ?iso2 ?countryLabel WHERE {{
      VALUES ?item {{ {vals} }}
      OPTIONAL {{ ?item wdt:P625 ?own. }}
      OPTIONAL {{ ?item wdt:P159 ?hq. OPTIONAL {{ ?hq wdt:P625 ?hqc. }} }}
      OPTIONAL {{ ?item wdt:P17 ?country. OPTIONAL {{ ?country wdt:P297 ?iso2. }} }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }} }}""")
    out = {}
    for r in rows:
        q = W.qid(W.v(r, "item"))
        if q in out and out[q][0]:
            continue
        at, how = W.place_row(r, countries)
        out[q] = (at, how, W.v(r, "hqLabel"), W.v(r, "countryLabel"))
    return out


def clean(v):
    return " ".join(str(v).split()) if isinstance(v, str) else v


HEADS = ("company", "companies/countries", "country", "species", "region for average emissions factor")


def tables(sheet):
    """A sheet -> its tables: {title, head, units, rows:[(row index, cells)]}."""
    rows, out, cur = sheet["rows"], [], None
    for i, r in enumerate(rows):
        cells = [clean(c) for c in r]
        filled = [c for c in cells if c not in (None, "")]
        first = filled[0] if filled else None
        if isinstance(first, str) and first.startswith("Table "):
            cur = {"title": first, "head": None, "units": None, "group": None, "rows": [], "named": False}
            out.append(cur)
            continue
        if cur is None or not filled:
            continue
        texts = [c for c in filled if isinstance(c, str)]
        named = any(isinstance(c, str) and c.strip().lower() in HEADS for c in cells)
        if cur["head"] is None or (named and not cur["rows"] and not cur["named"]):
            if cur["head"] is not None:          # the row above was a group label row
                cur["group"], cur["units"] = cur["head"], None
            if named or len(texts) >= 3:
                cur["head"], cur["named"] = cells, named
            elif len(texts) == len(filled):
                cur["group"] = cells
            continue
        if cur["units"] is None and not cur["rows"] and len(texts) == len(filled) and any(isinstance(c, str) and ("kg" in c or c == "%" or "CO2e" in c) for c in texts):
            cur["units"] = cells
            continue
        cur["rows"].append((i, cells))
    return out


def number(v, pct):
    if pct:
        return f"{v * 100:.1f}%"
    if isinstance(v, float):
        return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.3g}"
    if isinstance(v, int):
        return str(v) if 1000 <= v <= 2100 else f"{v:,}"   # years stay as years
    return v


def esc(v):
    return html.escape(str(v))


def cell(v, pct, link=True):
    if v in (None, ""):
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return esc(number(v, pct))
    s = str(v)
    if link and s.startswith(("http://", "https://")):
        return f'<a href="{esc(s)}" target="_blank" rel="noopener">source</a>'
    return esc(s)


def table_html(t, rows, pcts):
    head, units, group = t["head"] or [], t["units"] or [], t["group"] or []
    width = max([len(head)] + [len(c) for _, c in rows])
    # Some tables repeat their own rows beside them, rearranged for a chart
    # ("Data arranged for chart:"); the box shows the table once (the whole
    # sheet, with the repeat, is in the "read them" window).
    cut = next((j for j, h in enumerate(head) if isinstance(h, str) and h.lower().startswith("data arranged for chart")), None)
    if cut is not None:
        width = cut
        rows = [(i, c[:cut]) for i, c in rows if any(v not in (None, "") for v in c[:cut])]
    keep = [j for j in range(width) if (j < len(head) and head[j] not in (None, "")) or any(j < len(c) and c[j] not in (None, "") for _, c in rows)]

    def at(lst, j):
        return lst[j] if j < len(lst) and lst[j] not in (None, "") else ""
    th = "".join(f"<th>{esc(at(head, j))}" + (f" <span>({esc(at(group, j))})</span>" if at(group, j) else "") +
                 (f"<br><span>{esc(at(units, j))}</span>" if at(units, j) else "") + "</th>" for j in keep)
    body = "".join("<tr>" + "".join(f"<td>{cell(at(c, j), (i, j) in pcts)}</td>" for j in keep) + "</tr>" for i, c in rows)
    return f'<div class="md-t"><div class="md-cap">{esc(t["title"])}</div><div class="md-scroll"><table><tr>{th}</tr>{body}</table></div></div>'


def sheet_html(sheet):
    pcts = {tuple(p) for p in sheet["pct"]}
    width = max([len(r) for r in sheet["rows"]] + [0])
    keep = [j for j in range(width) if any(j < len(r) and r[j] not in (None, "") for r in sheet["rows"])]
    body = "".join("<tr>" + "".join(f"<td>{cell(r[j] if j < len(r) else None, (i, j) in pcts)}</td>" for j in keep) + "</tr>"
                   for i, r in enumerate(sheet["rows"]) if any(c not in (None, "") for c in r))
    return f'<div class="md-scroll"><table class="md-sheet">{body}</table></div>'


CSS = """
:where(.wtyg-map-methane_meat_dairy) .md{font:12.5px/1.45 system-ui,sans-serif;color:#DCE6EA}
:where(.wtyg-map-methane_meat_dairy) .md h2{font-size:16px;margin:0 0 2px;color:#E8F1F4}
:where(.wtyg-map-methane_meat_dairy) .md .md-sub{color:#93A9B0;margin-bottom:6px}
:where(.wtyg-map-methane_meat_dairy) .md .md-big{font-size:14px;margin:4px 0 8px}
:where(.wtyg-map-methane_meat_dairy) .md-cap{font-weight:600;margin:8px 0 3px;color:#BFD8E0}
:where(.wtyg-map-methane_meat_dairy) .md-scroll{overflow-x:auto;max-width:100%}
:where(.wtyg-map-methane_meat_dairy) table{border-collapse:collapse;font-size:11.5px}
:where(.wtyg-map-methane_meat_dairy) th,:where(.wtyg-map-methane_meat_dairy) td{border:1px solid #24404F;padding:2px 5px;vertical-align:top;text-align:left}
:where(.wtyg-map-methane_meat_dairy) th span{font-weight:400;color:#93A9B0}
:where(.wtyg-map-methane_meat_dairy) td{white-space:nowrap}
:where(.wtyg-map-methane_meat_dairy) a{color:#8FC3D6}
:where(.wtyg-map-methane_meat_dairy) .md-foot{color:#93A9B0;margin-top:8px;font-size:11.5px}
.md-pop .maplibregl-popup-content{background:#0F1C26;color:#DCE6EA;max-height:520px;overflow:auto}
"""


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    sheets = {s["name"]: s for s in data["sheets"]}
    summary = next(s for n, s in sheets.items() if n.startswith("Tab 1.1"))
    t11 = tables(summary)[0]
    head = t11["head"]
    col = {h: j for j, h in enumerate(head) if h}
    ch4_mass = next(j for h, j in col.items() if h.startswith("Methane/CH4"))
    ch4_100 = next(j for h, j in col.items() if h.startswith("CH4 emissions") and "GWP100" in h)
    ghg_100 = next(j for h, j in col.items() if h.startswith("GHG emissions") and "GWP100" in h)
    name_j = col["Company"]
    pcts11 = {tuple(p) for p in summary["pct"]}
    companies = [(i, c) for i, c in t11["rows"] if isinstance(c[name_j], str) and c[name_j].strip() != "Total"]
    kind = {}
    for n, s in sheets.items():
        k = "meat" if "meat" in n.lower() and n.startswith("Tab 2") else "milk" if n.startswith("Tab 3") else None
        if k:
            for t in tables(s):
                for _, c in t["rows"]:
                    for v in c:
                        if isinstance(v, str) and v.strip() in ARTICLES:
                            kind.setdefault(v.strip(), k)
    all_tables = [(n, s, t) for n, s in sheets.items() for t in tables(s)]
    countries = W.country_points()
    q = qids(sorted(set(ARTICLES.values())))
    at = places(sorted(set(q.values())), countries)
    top = max(float(c[ch4_mass]) for _, c in companies)
    feats, boxes, status = [], {}, {"source": CITE, "companies": len(companies), "placed": [], "not placed": []}
    for _, c in companies:
        name = c[name_j].strip()
        article = ARTICLES.get(name)
        item = q.get(article) if article else None
        where = at.get(item) if item else None
        if not where or not where[0]:
            status["not placed"].append(name)
            continue
        (lon, lat), how, hq, country = where
        kd = kind.get(name, "milk")
        label, colour = KINDS[kd]
        k = hashlib.sha1(name.encode()).hexdigest()[:16]
        parts = []
        for n, s, t in all_tables:
            cut = next((j for j, h in enumerate(t["head"] or []) if isinstance(h, str) and h.lower().startswith("data arranged for chart")), None)
            mine = [(i, r) for i, r in t["rows"] if any(isinstance(v, str) and v.strip() == name for v in r[:cut])]
            if mine:
                parts.append(table_html(t, mine, {tuple(p) for p in s["pct"]}))
        mass, co2e = float(c[ch4_mass]), float(c[ch4_100])
        big = (f'<div class="md-big">Methane: <b>{mass / 1e9:,.2f} million tonnes</b> a year ({co2e / 1e9:,.1f} million tonnes CO2e over 100 years); '
               f'all greenhouse gases: {float(c[ghg_100]) / 1e9:,.1f} million tonnes CO2e (GWP100), 2021 estimates</div>')
        where_said = f"Placed at {esc(hq or country)}: {esc(how)} (Wikidata, from the Wikipedia article {esc(article)})."
        h = (f'<div class="md"><h2>{esc(name)}</h2><div class="md-sub">{esc(label)}' + (f" · {esc(hq)}" if hq else "") + (f", {esc(country)}" if country else "") + "</div>"
             + big + "".join(parts)
             + f'<div class="md-foot">{where_said} Source: <a href="{REPORT}" target="_blank" rel="noopener">Emissions Impossible: Methane Edition</a> '
             f'(IATP and Changing Markets Foundation, 2022; <a href="{PDF}" target="_blank" rel="noopener">report</a>), its dataset workbook. '
             "The figures are the authors' estimates: each company's animals processed or milk taken in, times FAO GLEAM 2.0 average emissions for that product and region.</div></div>")
        boxes[k] = {"h": h, "o": {"maxWidth": 560, "minWidth": 320, "maxHeight": 520, "className": "md-pop"}, "t": f"{name}: {mass / 1e9:,.2f} million tonnes of methane a year"}
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": {"k": k, "n": name, "c": colour, "r": round(5 + 9 * math.sqrt(mass / top), 2), "s": "#08203F", "w": 1.2,
                                     "o": 0.95, "t": 1, "p": 1, "f": f"|kind:{kd}|"}})
        status["placed"].append({"company": name, "at": hq or country, "how": how, "wikidata": item})
    n = {kd: sum(1 for f in feats if f"|kind:{kd}|" in f["properties"]["f"]) for kd in KINDS}
    places_gj = {"type": "FeatureCollection", "name": "Methane from 15 large meat and dairy companies (Emissions Impossible: Methane Edition, IATP and Changing Markets)",
                 "overlays": [], "filters": [{"label": "Show", "values": [{"k": f"kind:{kd}", "label": KINDS[kd][0].replace("company", "companies"), "n": n[kd]} for kd in KINDS]}],
                 "features": feats}
    entries = [{"title": s["name"], "kind": "the whole sheet", "html": sheet_html(s)} for s in data["sheets"]]
    out = {"name": places_gj["name"], "page": REPORT, "stylesheets": [], "chain": [], "css": CSS, "boxes": boxes,
           "entries": {"title": "The dataset workbook, every sheet", "note": CITE + ". Every sheet as the workbook has it; percentages shown as percent.", "entries": entries}}
    DIR.mkdir(exist_ok=True)
    (DIR / "meat_dairy.places.geojson").write_text(json.dumps(places_gj, ensure_ascii=False))
    (DIR / "meat_dairy.boxes.json").write_text(json.dumps(out, ensure_ascii=False))
    (DIR / "meat_dairy.build.json").write_text(json.dumps(status, ensure_ascii=False, indent=1))
    print(f"meat_dairy_methane: {len(feats)} of {len(companies)} companies placed; not placed: {status['not placed']}")


if __name__ == "__main__":
    main()
