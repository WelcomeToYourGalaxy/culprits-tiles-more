#!/usr/bin/env python3
"""
The soy traders coloured by money (round 121b, asked 1 October 2026: "colour
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

Round 122b (2 October): the Forest 500 part is taken out. The owner
downloaded every Forest 500 file; they hold scores and policy answers, no
amounts of money, so nothing here could colour the banks by money. Every
company and institution Forest 500 assessed is now on the map from
scripts/forest500_map.py.

Weekly (Mondays) or by hand.
"""
import datetime, json, os, pathlib, sys, time, urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from largest_companies import get, WDQS, val, qid, ecb_rates  # noqa: E402

OUT = pathlib.Path("soy")
TRADERS = pathlib.Path("sitemaps/site_soybean_companies")
# The names the page gives, and the name Wikidata is searched for.
SEARCH = {"ADM": "Archer Daniels Midland", "Bunge": "Bunge", "Cargill": "Cargill", "Louis Dreyfus": "Louis Dreyfus Company",
          "COFCO Intl": "COFCO International", "COFCO Corp": "COFCO", "Amaggi": "Amaggi"}


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


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("soy_money: weekly; not Monday")
        return
    status = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    traders(status)
    OUT.mkdir(exist_ok=True)
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False, default=str))
    print("soy_money:", json.dumps(status, ensure_ascii=False, default=str)[:3000])


if __name__ == "__main__":
    main()
