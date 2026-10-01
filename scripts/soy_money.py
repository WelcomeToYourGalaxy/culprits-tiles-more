#!/usr/bin/env python3
"""
The soy culprits coloured by money (round 121b, asked 1 October 2026: "colour
soy by $ and influence", then "yes to both").

1. The soy traders' offices (the 24 places on the Destruction page's soybean
   companies map, sitemaps/site_soybean_companies.*), each with its trader's
   revenue from Wikidata (CC0): revenue (P2139), the latest year given,
   in US dollars where Wikidata gives dollars for that year, otherwise turned
   into dollars at the European Central Bank's average rate for that year.
   Each trader's Wikidata item is found by Wikidata's own search for its name
   (the first result that has a revenue figure); the item used is written in
   each box and in soy/build.json so it can be checked.
       soy/traders.geojson    the offices, the page's own box, the revenue

2. The banks and investors on the Destruction page's Forest 500 soy map (the
   70 places of sitemaps/site_forest500_soy.*), with the money they put into
   the companies Forest 500 assesses, from Forest 500's own data download
   (Global Canopy; CC BY-NC 4.0; "Forest 500 assessment data [Year], Global
   Canopy, Forest500.org"). Forest 500 gives that file only through a form on
   https://forest500.org/forest-500-data-methods/ , so the owner downloads it
   and uploads it, as it comes (.xlsx or .csv), into forest500/download/ in
   this repository. Every sheet is read; every column whose name speaks of
   financing or money is kept, as given; an institution is matched by its
   name only (the same letters, ignoring case, spaces and punctuation; no
   guessing). Until the file is there the places are written with their
   Forest 500 soy score only, and the build says it is waiting.
       forest500/soy_money.geojson
   Whether Forest 500's file holds US dollar figures has not been checked
   (its download needs the form); soy/build.json lists the columns found.

Weekly (Mondays), by hand, or when a new file is in forest500/download/.
"""
import csv, datetime, hashlib, io, json, os, pathlib, re, subprocess, sys, time, urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from largest_companies import get, WDQS, val, qid, ecb_rates  # noqa: E402

OUT = pathlib.Path("soy")
F500 = pathlib.Path("forest500")
DOWNLOAD = F500 / "download"
TRADERS = pathlib.Path("sitemaps/site_soybean_companies")
FIS = pathlib.Path("sitemaps/site_forest500_soy")
# The names the page gives, and the name Wikidata is searched for.
SEARCH = {"ADM": "Archer Daniels Midland", "Bunge": "Bunge", "Cargill": "Cargill", "Louis Dreyfus": "Louis Dreyfus Company",
          "COFCO Intl": "COFCO International", "COFCO Corp": "COFCO", "Amaggi": "Amaggi"}
MONEY = re.compile(r"financ|usd|us\$|\$|dollar|million|billion|exposure|investment|lending|loan|bond|share ?holding|value", re.I)


def sparql(q):
    body = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    return json.loads(get(WDQS, data=body, tries=3, timeout=120))["results"]["bindings"]


def places(stem):
    pl = json.loads(pathlib.Path(f"{stem}.places.geojson").read_text(encoding="utf-8"))["features"]
    boxes = json.loads(pathlib.Path(f"{stem}.boxes.json").read_text(encoding="utf-8")).get("boxes", {})
    return pl, boxes


def revenue(name):
    """The first item Wikidata's search gives for name that has a revenue."""
    rows = sparql(f"""
SELECT ?item ?itemLabel ?num ?amount ?code ?date ?rank WHERE {{
  SERVICE wikibase:mwapi {{ bd:serviceParam wikibase:api "EntitySearch" ; wikibase:endpoint "www.wikidata.org" ;
      mwapi:search {json.dumps(name)} ; mwapi:language "en" . ?item wikibase:apiOutputItem mwapi:item . ?num wikibase:apiOrdinal true . }}
  ?item p:P2139 ?st . ?st psv:P2139 ?v ; wikibase:rank ?rank . FILTER(?rank != wikibase:DeprecatedRank)
  ?v wikibase:quantityAmount ?amount ; wikibase:quantityUnit ?cur . OPTIONAL {{ ?cur wdt:P498 ?code }}
  OPTIONAL {{ ?st pq:P585 ?date }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}""")
    if not rows:
        return None
    first = min(int(val(b, "num")) for b in rows)
    rows = [b for b in rows if int(val(b, "num")) == first]
    dated = [b for b in rows if val(b, "date")] or rows
    year = max((val(b, "date") or "")[:4] for b in dated)
    pick = [b for b in dated if (val(b, "date") or "")[:4] == year]
    b = next((x for x in pick if val(x, "code") == "USD"), None) or next((x for x in pick if (val(x, "rank") or "").endswith("PreferredRank")), None) or pick[0]
    return {"wikidata": qid(val(b, "item")), "label": val(b, "itemLabel"), "amount": float(val(b, "amount")),
            "currency": val(b, "code"), "year": year or None}


def traders(status):
    pl, boxes = places(TRADERS)
    ecb = None
    money, feats = {}, []
    for n in sorted({f["properties"].get("n") for f in pl}):
        r = None
        try:
            r = revenue(SEARCH.get(n, n))
        except Exception as e:  # noqa: BLE001
            status.setdefault("wikidata not answering", []).append(f"{n}: {e!r:.200}")
        if r:
            if r["currency"] == "USD":
                r["usd"], r["rate"] = r["amount"], "given in US dollars"
            else:
                ecb = ecb if ecb is not None else ecb_rates()
                rate = (ecb.get(r["currency"] or "") or {}).get(r["year"] or "")
                r["usd"], r["rate"] = (r["amount"] / rate, f"European Central Bank, {r['year']} average") if rate else (None, "no rate for this currency and year")
        money[n] = r
        time.sleep(1)
    for f in pl:
        p = f["properties"]
        n, r = p.get("n"), money.get(p.get("n"))
        bn = round(r["usd"] / 1e9, 1) if r and r.get("usd") else None
        if bn is not None:
            given = "" if r["currency"] == "USD" else f" ({r['amount']:,.0f} {r['currency']}; {r['rate']})"
            link = f"<a href=\"https://www.wikidata.org/wiki/{r['wikidata']}\" target=\"_blank\" rel=\"noopener\">Wikidata</a>"
            line = f"<br><small>Revenue of {r['label']}, {r['year'] or 'year not given'}: <b>US${bn:,} billion</b>{given} ({link})</small>"
        else:
            line = "<br><small>Revenue: none found in Wikidata</small>"
        html = (boxes.get(p.get("k")) or {}).get("h") or f"<b>{n}</b>"
        feats.append({"type": "Feature", "geometry": f["geometry"],
                      "properties": {"name": n, "trader": n, "revenue, US$ billion": bn, "revenue year": r and r["year"],
                                     "wikidata": r and f"https://www.wikidata.org/wiki/{r['wikidata']}", "_html": html + line}})
    OUT.mkdir(exist_ok=True)
    (OUT / "traders.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    status["traders"] = {n: r for n, r in money.items()}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def table_rows(path):
    """Every row of every sheet (or the csv) as {column: value}, with the sheet's name."""
    if path.suffix.lower() == ".csv":
        text = path.read_bytes().decode("utf-8-sig", "replace")
        return [dict(r, _sheet=path.name) for r in csv.DictReader(io.StringIO(text))]
    try:
        import openpyxl
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=True)
        import openpyxl
    out = []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        # The header is the first row with at least three filled cells.
        h = next((i for i, r in enumerate(rows[:30]) if sum(1 for c in r if c not in (None, "")) >= 3), None)
        if h is None:
            continue
        head = [str(c).strip() if c is not None else f"column {j + 1}" for j, c in enumerate(rows[h])]
        for r in rows[h + 1:]:
            if any(c not in (None, "") for c in r):
                out.append(dict(zip(head, r), _sheet=ws.title))
    return out


def forest500(status):
    pl, boxes = places(FIS)
    files = sorted(p for p in DOWNLOAD.glob("*") if p.suffix.lower() in (".xlsx", ".xlsm", ".csv")) if DOWNLOAD.exists() else []
    found, columns, matched, unmatched = {}, {}, set(), []
    for path in files:
        for r in table_rows(path):
            namecol = next((k for k in r if re.search(r"^(fi|financial institution|institution|company|organi[sz]ation)?\s*name$|^financial institution$|^institution$", str(k), re.I)), None)
            if not namecol or not r.get(namecol):
                continue
            keep = {k: v for k, v in r.items() if k != "_sheet" and MONEY.search(str(k)) and v not in (None, "")}
            if not keep:
                continue
            columns.setdefault(f"{path.name} / {r['_sheet']}", sorted(keep))
            year = next((str(v)[:4] for k, v in r.items() if re.search(r"year", str(k), re.I) and re.match(r"(19|20)\d\d", str(v or ""))), "")
            e = found.setdefault(norm(r[namecol]), {})
            for k, v in keep.items():
                e[f"{k} ({r['_sheet']}{', ' + year if year else ''})"] = v
    feats = []
    for f in pl:
        p = f["properties"]
        html = (boxes.get(p.get("k")) or {}).get("h") or f"<b>{p.get('n')}</b>"
        m = re.search(r"Soy Score:</strong>\s*([\d.]+)\s*/\s*94", html)
        props = {"name": p.get("n"), "soy score (out of 94)": float(m.group(1)) if m else None}
        got = found.get(norm(p.get("n")))
        if got:
            matched.add(p.get("n"))
            props.update({f"x_{k}": v for k, v in got.items()})
            # The first column speaking of financing, as a number, colours the row.
            fin = next((v for k, v in got.items() if re.search(r"financ", k, re.I) and isinstance(v, (int, float))), None)
            if fin is None:
                fin = next((v for v in got.values() if isinstance(v, (int, float))), None)
            props["financing (Forest 500's figure, its unit)"] = fin
            html += "<div><small>" + "<br>".join(f"<strong>{k}:</strong> {v:,}" if isinstance(v, (int, float)) else f"<strong>{k}:</strong> {v}" for k, v in got.items()) + \
                    "<br>Forest 500 assessment data, Global Canopy, Forest500.org (CC BY-NC 4.0)</small></div>"
        elif files:
            unmatched.append(p.get("n"))
        props["_html"] = html
        feats.append({"type": "Feature", "geometry": f["geometry"], "properties": props})
    F500.mkdir(exist_ok=True)
    (F500 / "soy_money.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats,
                                                        "licence": "CC BY-NC 4.0; Forest 500 assessment data, Global Canopy, Forest500.org"}, ensure_ascii=False))
    status["forest500"] = {"files": [p.name for p in files] or "waiting: no file in forest500/download/ yet",
                           "money columns": columns, "institutions matched": len(matched), "not found in the file": unmatched}


def main():
    stamp = OUT / "build.json"
    files = sorted(DOWNLOAD.glob("*")) if DOWNLOAD.exists() else []
    seen = hashlib.sha1("".join(f"{p.name}:{p.stat().st_size}" for p in files).encode()).hexdigest()
    old = json.loads(stamp.read_text()) if stamp.exists() else {}
    if (stamp.exists() and datetime.date.today().weekday() != 0 and old.get("download") == seen
            and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"):
        print("soy_money: weekly; not Monday, and no new Forest 500 file")
        return
    status = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "download": seen}
    traders(status)
    forest500(status)
    OUT.mkdir(exist_ok=True)
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False, default=str))
    print("soy_money:", json.dumps(status, ensure_ascii=False, default=str)[:3000])


if __name__ == "__main__":
    main()
