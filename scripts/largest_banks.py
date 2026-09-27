#!/usr/bin/env python3
"""
The world's largest banks by total assets, compiled from Wikidata (CC0), for
the Culprits map (asked for 26 September: "make your own largest banks in the
world layer"). Built the same way as largest_companies.py, which it borrows
from.

  1. Wikidata: every item with a total assets (P2403) statement over 1e9 in its
     own currency, with the currency (ISO 4217 code, P498) and the year (point
     in time, P585). Each item's latest year is used; where it has a US dollar
     figure for that year, that one.
  2. Converted to US dollars at the year's average rate: the European Central
     Bank's euro reference rates, or for currencies the ECB does not publish,
     the World Bank's official exchange rate. A figure with no stated rate for
     its currency and year is not ranked; how many is written down.
  3. Sorted into three by what Wikidata says each item is (instance of, through
     subclass of), asked 26 September:
       - central banks: left out (the map has its own central banks layer);
         listed in the build file;
       - development banks (a kind of "development bank" or "multilateral
         development bank"): every one with a figure, in
         banks/development.geojson;
       - the other banks (a kind of bank, Q22687): the largest TOP, in
         banks/largest.geojson.
     Items that are none of these are listed in the build file. The classes
     are found by their English names when the build runs, so a renamed or
     merged class is noticed (the build stops rather than guessing).
     For each, from Wikidata: name, kinds (P31), headquarters (P159) and its
     coordinates (P625, on the headquarters item or on the statement), country
     (P17), employees (P1128), founded (P571), website (P856), stock exchange
     (P414), parent (P749), owner (P127), chief executive (P169). A bank whose
     headquarters Wikidata gives no coordinates for is listed, not placed.

Writes banks/largest.geojson, banks/development.geojson and banks/largest.build.json. Weekly;
BANKS_REBUILD=1 builds again.
"""
import json, os, pathlib, re, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from largest_companies import sparql, val, qid, ecb_rates, wb_rates  # noqa: E402

OUT = pathlib.Path("banks")
TOP = 250
WEEK = 7 * 24 * 3600
BANK = "Q22687"


def main():
    stamp = OUT / "largest.build.json"
    if stamp.exists() and time.time() - stamp.stat().st_mtime < WEEK and not os.environ.get("BANKS_REBUILD"):
        print("largest banks: built less than a week ago")
        return
    print("largest banks: reading total assets statements from Wikidata", flush=True)
    one = """
SELECT ?item ?amount ?cur ?code ?date ?rank WHERE {{
  {values}
  ?item p:P2403 ?st . ?st psv:P2403 ?v ; wikibase:rank ?rank .
  ?v wikibase:quantityAmount ?amount ; wikibase:quantityUnit ?cur .
  FILTER(?amount > 1000000000)
  FILTER(?rank != wikibase:DeprecatedRank)
  OPTIONAL {{ ?cur wdt:P498 ?code }}
  OPTIONAL {{ ?st pq:P585 ?date }}
}}"""
    try:
        rows = sparql(one.format(values=""))
    except Exception as e:  # noqa: BLE001
        print(f"  all at once failed ({e}); one currency at a time", flush=True)
        curs = [qid(val(b, "cur")) for b in sparql("""
SELECT DISTINCT ?cur WHERE { ?item p:P2403/psv:P2403/wikibase:quantityUnit ?cur . }""")]
        rows = []
        for cur in curs:
            if cur and re.match(r"^Q\d+$", cur):
                rows += sparql(one.format(values=f"VALUES ?cur {{ wd:{cur} }}"))
                time.sleep(1)
    print(f"  {len(rows):,} statements", flush=True)
    cur_items = sorted({qid(val(b, "cur")) for b in rows if val(b, "code") and re.match(r"^Q\d+$", qid(val(b, "cur")) or "")})
    code_of = {qid(val(b, "cur")): val(b, "code") for b in rows if val(b, "code")}
    cur_country = {}
    for i in range(0, len(cur_items), 100):
        values = " ".join(f"wd:{q}" for q in cur_items[i:i + 100])
        for b in sparql(f"""
SELECT ?cur ?iso3 WHERE {{ VALUES ?cur {{ {values} }} ?cur wdt:P17 ?c . ?c wdt:P298 ?iso3 . }}"""):
            cur_country.setdefault(code_of.get(qid(val(b, "cur"))), set()).add(val(b, "iso3"))
        time.sleep(1)
    ecb, wb = ecb_rates(), wb_rates()

    def rate(code, year):
        if not code or not year:
            return None, None
        if code in ecb and year in ecb[code]:
            return ecb[code][year], "European Central Bank euro reference rates, year average"
        for iso3 in sorted(cur_country.get(code, ())):
            if iso3 in wb and year in wb[iso3]:
                return wb[iso3][year], f"World Bank official exchange rate (PA.NUS.FCRF), {iso3}"
        return None, None

    by = {}
    for b in rows:
        y = (val(b, "date") or "")[:4] or None
        by.setdefault(qid(val(b, "item")), []).append({"amount": float(val(b, "amount")), "code": val(b, "code"), "year": y,
                                                       "preferred": (val(b, "rank") or "").endswith("PreferredRank")})
    ranked, unconverted, undated = [], 0, 0
    for q, sts in by.items():
        dated = [s for s in sts if s["year"]]
        if not dated:
            undated += 1
            continue
        latest = max(s["year"] for s in dated)
        pick = [s for s in dated if s["year"] == latest]
        s = next((x for x in pick if x["code"] == "USD"), None) or next((x for x in pick if x["preferred"]), None) or max(pick, key=lambda x: x["amount"])
        r, src = rate(s["code"], s["year"])
        if r is None:
            unconverted += 1
            continue
        ranked.append(dict(s, qid=q, usd=s["amount"] / r, rate=r, rate_source=src))
    ranked.sort(key=lambda x: -x["usd"])
    # The classes, by their English names.
    classes = {}
    for b in sparql("""
SELECT ?c ?l WHERE { VALUES ?l { "central bank"@en "development bank"@en "multilateral development bank"@en }
  ?c rdfs:label ?l . ?c wdt:P279 ?any . }"""):
        classes.setdefault(val(b, "l"), set()).add(qid(val(b, "c")))
    print(f"  classes: {json.dumps({k: sorted(v) for k, v in classes.items()})}", flush=True)
    central = classes.get("central bank", set())
    devel = classes.get("development bank", set()) | classes.get("multilateral development bank", set())
    if not central or not devel:
        raise SystemExit(f"largest banks: Wikidata's central or development bank class was not found by name ({classes}); nothing written")
    kinds = " ".join(f"wd:{q}" for q in sorted(central | devel | {BANK}))
    print(f"  {len(ranked):,} items ranked; sorting banks, central banks and development banks", flush=True)
    top, dev, central_out, not_bank = [], [], [], []
    for i in range(0, len(ranked), 200):
        chunk = ranked[i:i + 200]
        values = " ".join(f"wd:{c['qid']}" for c in chunk)
        is_ = {}
        for b in sparql(f"""
SELECT DISTINCT ?item ?k WHERE {{ VALUES ?item {{ {values} }} VALUES ?k {{ {kinds} }} ?item wdt:P31/wdt:P279* ?k . }}"""):
            is_.setdefault(qid(val(b, "item")), set()).add(qid(val(b, "k")))
        for c in chunk:
            k = is_.get(c["qid"], set())
            if k & central:
                central_out.append(c)
            elif k & devel:
                dev.append(c)
            elif BANK in k:
                if len(top) < TOP:
                    top.append(c)
            else:
                not_bank.append(c)
        time.sleep(2)
    if not top:
        raise SystemExit("largest banks: no bank found; nothing written")

    fields = (("kind", "kindLabel"), ("hq", "hqLabel"), ("country", "countryLabel"), ("employees", "employees"),
              ("founded", "founded"), ("website", "site"), ("exchange", "exchangeLabel"), ("parent", "parentLabel"),
              ("owner", "ownerLabel"), ("ceo", "ceoLabel"))

    def place(items):
      feats, unplaced = [], []
      for i in range(0, len(items), 50):
        chunk = items[i:i + 50]
        values = " ".join(f"wd:{c['qid']}" for c in chunk)
        res = sparql(f"""
SELECT ?item ?itemLabel ?kindLabel ?hqLabel ?coord ?stcoord ?countryLabel ?employees ?founded ?site ?exchangeLabel ?parentLabel ?ownerLabel ?ceoLabel WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item wdt:P31 ?kind }}
  OPTIONAL {{ ?item p:P159 ?hqs . ?hqs ps:P159 ?hq . OPTIONAL {{ ?hq wdt:P625 ?coord }} OPTIONAL {{ ?hqs pq:P625 ?stcoord }} }}
  OPTIONAL {{ ?item wdt:P17 ?country }}
  OPTIONAL {{ ?item wdt:P1128 ?employees }}
  OPTIONAL {{ ?item wdt:P571 ?founded }}
  OPTIONAL {{ ?item wdt:P856 ?site }}
  OPTIONAL {{ ?item wdt:P414 ?exchange }}
  OPTIONAL {{ ?item wdt:P749 ?parent }}
  OPTIONAL {{ ?item wdt:P127 ?owner }}
  OPTIONAL {{ ?item wdt:P169 ?ceo }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
}}""")
        info = {}
        for b in res:
            d = info.setdefault(qid(val(b, "item")), {"name": val(b, "itemLabel"), "coord": None, **{k: set() for k, _ in fields}})
            for k, f in fields:
                if val(b, f):
                    d[k].add(val(b, f)[:10] if k == "founded" else val(b, f))
            c = val(b, "stcoord") or val(b, "coord")
            if c and not d["coord"]:
                d["coord"] = c
        for n, c in enumerate(chunk, i + 1):
            d = info.get(c["qid"], {"name": c["qid"]})
            props = {"rank": n, "name": d.get("name") or c["qid"],
                     "total_assets_in_dollars": f"${c['usd'] / 1e9:,.1f} billion", "total_assets_usd": round(c["usd"]),
                     "total_assets": c["amount"], "total_assets_currency": c["code"], "total_assets_year": c["year"],
                     "usd_rate": c["rate"], "usd_rate_source": c["rate_source"],
                     "wikidata": f"https://www.wikidata.org/wiki/{c['qid']}"}
            for k, _ in fields:
                if d.get(k):
                    props[k] = "; ".join(sorted(d[k]))
            m = d.get("coord") and re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", d["coord"])
            if not m:
                unplaced.append({"rank": n, "name": props["name"], "wikidata": props["wikidata"]})
                continue
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(m.group(1)), float(m.group(2))]},
                          "properties": props})
        time.sleep(2)
      return feats, unplaced

    feats, unplaced = place(top)
    dfeats, dunplaced = place(dev)
    brief = lambda xs: [{"wikidata": c["qid"], "total_assets_usd": round(c["usd"]), "year": c["year"]} for c in xs]
    OUT.mkdir(exist_ok=True)
    (OUT / "largest.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "development.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": dfeats}, ensure_ascii=False))
    stamp.write_text(json.dumps({"ranked": len(ranked), "classes": {k: sorted(v) for k, v in classes.items()},
                                 "top": len(top), "placed": len(feats), "not_placed": unplaced,
                                 "development_banks": len(dev), "development_placed": len(dfeats), "development_not_placed": dunplaced,
                                 "central_banks_left_out": brief(central_out),
                                 "no_rate": unconverted, "no_year": undated,
                                 "not_a_bank": brief(not_bank),
                                 "sources": ["Wikidata (CC0)", "European Central Bank", "World Bank"]}, ensure_ascii=False, indent=1))
    (OUT / "largest.failed.json").unlink(missing_ok=True)
    print(f"largest banks: {len(feats)} of the top {len(top)} placed; development banks: {len(dfeats)} of {len(dev)} placed; "
          f"{len(central_out)} central banks left out")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        OUT.mkdir(exist_ok=True)
        (OUT / "largest.failed.json").write_text(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                                                             "error": repr(e)[:2000]}, indent=1))
        raise
