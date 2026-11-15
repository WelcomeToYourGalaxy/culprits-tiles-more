#!/usr/bin/env python3
"""
The world's 500 largest companies by revenue, compiled from Wikidata (CC0), for
the Culprits map (asked for 24 September in place of Fortune's Global 500,
whose terms forbid copying it).

  1. Wikidata: every item with a total revenue (P2139) statement over 1e9 in
     its own currency, with the currency (and its ISO 4217 code, P498) and the
     year (point in time, P585). Each company's latest year is used; where it
     has a US dollar figure for that year, that one.
  2. Converted to US dollars at the year's average rate: the European Central
     Bank's euro reference rates (eurofxref-hist), and for currencies the ECB
     does not publish, the World Bank's official exchange rate (PA.NUS.FCRF,
     local currency per dollar, by the country whose currency it is). A figure
     with no stated rate for its currency and year is not ranked; how many is
     written down.
  3. The top 500 by dollar revenue among items Wikidata says are a kind of
     business (Q4830453), so governments and cities with a revenue figure are
     not ranked (they are listed in the build file).
     For each, from Wikidata: name, headquarters
     (P159) and its coordinates (P625, on the headquarters item or on the
     statement), country (P17), industry (P452), employees (P1128), founded
     (P571), official website (P856), stock exchange (P414), parent (P749),
     CEO (P169). A company whose headquarters Wikidata gives no coordinates for
     is listed, not placed.

Writes companies/largest.geojson (every company placed, every field above,
the revenue as Wikidata gives it and in dollars, the rate and its source) and
companies/largest.build.json (counts, what was not ranked or not placed).
Weekly; COMPANIES_REBUILD=1 builds again.
"""
import csv, io, json, os, pathlib, re, time, urllib.parse, urllib.request, zipfile

WDQS = "https://query.wikidata.org/sparql"
ECB = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
WB = "https://api.worldbank.org/v2/country/all/indicator/PA.NUS.FCRF?format=json&per_page=20000&date=1990:2026"
OUT = pathlib.Path("companies")
UA = {"User-Agent": "Culprits atlas (github.com/WelcomeToYourGalaxy) largest companies build", "Accept": "application/sparql-results+json"}
TOP = 500
WEEK = 7 * 24 * 3600


def get(url, data=None, tries=5, timeout=300):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"    no answer ({e}); again in {20 * (i + 1)}s", flush=True)
            time.sleep(20 * (i + 1))


def sparql(q):
    body = urllib.parse.urlencode({"query": q, "format": "json"}).encode()
    return json.loads(get(WDQS, data=body))["results"]["bindings"]


def val(b, k):
    return b[k]["value"] if k in b else None


def qid(u):
    return u.rsplit("/", 1)[-1] if u else None


def ecb_rates():
    """{currency: {year: units per US dollar}} from the ECB's daily euro rates."""
    z = zipfile.ZipFile(io.BytesIO(get(ECB)))
    rows = list(csv.DictReader(io.StringIO(z.read(z.namelist()[0]).decode("utf-8"))))
    sums, eur = {}, {}
    for r in rows:
        y = r["Date"][:4]
        usd = r.get("USD", "").strip()
        if not usd or usd == "N/A":
            continue
        usd = float(usd)
        e = eur.setdefault(y, [0.0, 0])
        e[0] += 1 / usd
        e[1] += 1
        for cur, v in r.items():
            v = (v or "").strip()
            if cur in ("Date", "") or not v or v == "N/A":
                continue
            per_usd = float(v) / usd
            s = sums.setdefault(cur, {}).setdefault(y, [0.0, 0])
            s[0] += per_usd
            s[1] += 1
    out = {c: {y: s / n for y, (s, n) in ys.items()} for c, ys in sums.items()}
    out["EUR"] = {y: s / n for y, (s, n) in eur.items()}   # euros per dollar
    out["USD"] = {y: 1.0 for y in sums["USD"]}
    return out


def wb_rates():
    """{iso3 country: {year: local currency per US dollar}} from the World Bank."""
    j = json.loads(get(WB))
    out = {}
    for r in j[1] if len(j) > 1 else []:
        if r.get("value") is not None and r.get("countryiso3code"):
            out.setdefault(r["countryiso3code"], {})[r["date"]] = float(r["value"])
    return out


def main():
    stamp = OUT / "largest.build.json"
    if stamp.exists() and time.time() - stamp.stat().st_mtime < WEEK and not os.environ.get("COMPANIES_REBUILD"):
        print("largest companies: built less than a week ago")
        return
    print("largest companies: reading revenue statements from Wikidata", flush=True)
    # The run of 25 September read all 21,154 statements in one request; it was
    # the next request (which countries use each currency, asked of every
    # currency in Wikidata) that timed out. That one now names only the
    # currencies the statements use. If the one big request ever times out,
    # it is asked again one currency at a time.
    one = """
SELECT ?item ?amount ?cur ?code ?date ?rank WHERE {{
  {values}
  ?item p:P2139 ?st . ?st psv:P2139 ?v ; wikibase:rank ?rank .
  ?v wikibase:quantityAmount ?amount ; wikibase:quantityUnit ?cur .
  FILTER(?amount > 1000000000)
  FILTER(?rank != wikibase:DeprecatedRank)
  OPTIONAL {{ ?cur wdt:P498 ?code }}
  OPTIONAL {{ ?st pq:P585 ?date }}
}}"""
    try:
        rev = sparql(one.format(values=""))
    except Exception as e:  # noqa: BLE001
        print(f"  all at once failed ({e}); one currency at a time", flush=True)
        curs = [qid(val(b, "cur")) for b in sparql("""
SELECT DISTINCT ?cur WHERE { ?item p:P2139/psv:P2139/wikibase:quantityUnit ?cur . }""")]
        rev = []
        for cur in curs:
            if cur and re.match(r"^Q\d+$", cur):
                rev += sparql(one.format(values=f"VALUES ?cur {{ wd:{cur} }}"))
                time.sleep(1)
    print(f"  {len(rev):,} statements", flush=True)
    cur_items = sorted({qid(val(b, "cur")) for b in rev if val(b, "code") and re.match(r"^Q\d+$", qid(val(b, "cur")) or "")})
    code_of = {qid(val(b, "cur")): val(b, "code") for b in rev if val(b, "code")}
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
    for b in rev:
        q = qid(val(b, "item"))
        y = (val(b, "date") or "")[:4] or None
        by.setdefault(q, []).append({"amount": float(val(b, "amount")), "code": val(b, "code"), "currency_item": qid(val(b, "cur")),
                                     "year": y, "preferred": (val(b, "rank") or "").endswith("PreferredRank")})
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
    print("  keeping the businesses (Wikidata: instance of a kind of business, Q4830453)", flush=True)
    top, not_business = [], []
    for i in range(0, len(ranked), 200):
        if len(top) >= TOP:
            break
        chunk = ranked[i:i + 200]
        values = " ".join(f"wd:{c['qid']}" for c in chunk)
        biz = {qid(val(b, "item")) for b in sparql(f"""
SELECT DISTINCT ?item WHERE {{ VALUES ?item {{ {values} }} ?item wdt:P31/wdt:P279* wd:Q4830453 . }}""")}
        for c in chunk:
            (top if c["qid"] in biz else not_business).append(c)
        time.sleep(2)
    top = top[:TOP]
    print(f"  {len(ranked):,} companies ranked; {unconverted:,} with no stated rate; {undated:,} with no year", flush=True)

    feats, unplaced = [], []
    for i in range(0, len(top), 100):
        chunk = top[i:i + 100]
        values = " ".join(f"wd:{c['qid']}" for c in chunk)
        rows = sparql(f"""
SELECT ?item ?itemLabel ?hq ?hqLabel ?coord ?stcoord ?countryLabel ?industryLabel ?employees ?founded ?site ?exchangeLabel ?parentLabel ?ceoLabel WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item p:P159 ?hqs . ?hqs ps:P159 ?hq . OPTIONAL {{ ?hq wdt:P625 ?coord }} OPTIONAL {{ ?hqs pq:P625 ?stcoord }} }}
  OPTIONAL {{ ?item wdt:P17 ?country }}
  OPTIONAL {{ ?item wdt:P452 ?industry }}
  OPTIONAL {{ ?item wdt:P1128 ?employees }}
  OPTIONAL {{ ?item wdt:P571 ?founded }}
  OPTIONAL {{ ?item wdt:P856 ?site }}
  OPTIONAL {{ ?item wdt:P414 ?exchange }}
  OPTIONAL {{ ?item wdt:P749 ?parent }}
  OPTIONAL {{ ?item wdt:P169 ?ceo }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,mul". }}
}}""")
        info = {}
        for b in rows:
            q = qid(val(b, "item"))
            d = info.setdefault(q, {"name": val(b, "itemLabel"), "hq": set(), "coord": None, "country": set(), "industry": set(),
                                    "employees": set(), "founded": set(), "website": set(), "exchange": set(), "parent": set(), "ceo": set()})
            for k, f in (("hq", "hqLabel"), ("country", "countryLabel"), ("industry", "industryLabel"), ("employees", "employees"),
                         ("founded", "founded"), ("website", "site"), ("exchange", "exchangeLabel"), ("parent", "parentLabel"), ("ceo", "ceoLabel")):
                if val(b, f):
                    d[k].add(val(b, f)[:10] if k == "founded" else val(b, f))
            c = val(b, "stcoord") or val(b, "coord")
            if c and not d["coord"]:
                d["coord"] = c
        for n, c in enumerate(chunk, i + 1):
            d = info.get(c["qid"], {"name": c["qid"]})
            props = {"rank": n, "name": d.get("name") or c["qid"], "revenue_in_dollars": f"${c['usd'] / 1e9:,.1f} billion", "revenue_usd": round(c["usd"]), "revenue": c["amount"],
                     "revenue_currency": c["code"], "revenue_year": c["year"], "usd_rate": c["rate"], "usd_rate_source": c["rate_source"],
                     "wikidata": f"https://www.wikidata.org/wiki/{c['qid']}"}
            for k in ("hq", "country", "industry", "employees", "founded", "website", "exchange", "parent", "ceo"):
                if d.get(k):
                    props[k] = "; ".join(sorted(d[k]))
            m = d.get("coord") and re.match(r"Point\(([-\d.eE]+) ([-\d.eE]+)\)", d["coord"])
            if not m:
                unplaced.append({"rank": n, "name": props["name"], "wikidata": props["wikidata"]})
                continue
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(m.group(1)), float(m.group(2))]}, "properties": props})
        time.sleep(2)
    OUT.mkdir(exist_ok=True)
    (OUT / "largest.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    stamp.write_text(json.dumps({"ranked": len(ranked), "top": len(top), "placed": len(feats), "not_placed": unplaced,
                                 "no_rate": unconverted, "not_a_business_above_the_500th": [{"wikidata": c["qid"], "revenue_usd": round(c["usd"])} for c in not_business], "no_year": undated, "sources": ["Wikidata (CC0)", "European Central Bank", "World Bank"]},
                                ensure_ascii=False, indent=1))
    (OUT / "largest.failed.json").unlink(missing_ok=True)
    print(f"largest companies: {len(feats)} of the top {len(top)} placed at their headquarters; {len(unplaced)} with no headquarters position")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        # Written down so the failure can be read from the repository.
        OUT.mkdir(exist_ok=True)
        (OUT / "largest.failed.json").write_text(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                                                             "error": repr(e)[:2000]}, indent=1))
        raise
