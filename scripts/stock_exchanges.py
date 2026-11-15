#!/usr/bin/env python3
"""
The world's major stock exchanges, by the value of the companies listed on
them (round 104b, asked 28 September: a Stock market heading beside Wealth
concentration).

Source: Wikipedia's "List of major stock exchanges" (CC BY-SA 4.0), its main
table as it stands each week: every exchange with its market capitalisation
(US$ trillion), MIC code, region, city, time zone and hours, every column kept.
Each is placed at the coordinates of its own Wikipedia article, or, where that
has none, of its city's article; the box says which.

  markets/exchanges.geojson   markets/build.json

Weekly (Mondays) or by hand.
"""
import datetime, io, json, os, pathlib, re, subprocess, sys, urllib.parse, urllib.request

API = "https://en.wikipedia.org/w/api.php"
PAGE = "List of major stock exchanges"
OUT = pathlib.Path("markets")
UA = {"User-Agent": "Culprits atlas build (welcometoyourgalaxy@gmail.com)"}


def api(**q):
    q.update({"format": "json", "formatversion": "2"})
    url = API + "?" + urllib.parse.urlencode(q)
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read())


def coords(titles):
    out = {}
    for i in range(0, len(titles), 40):
        j = api(action="query", prop="coordinates", titles="|".join(titles[i:i + 40]), redirects=1, colimit="max")
        norm = {n["from"]: n["to"] for n in j["query"].get("normalized", []) + j["query"].get("redirects", [])}
        got = {p["title"]: (p["coordinates"][0]["lon"], p["coordinates"][0]["lat"]) for p in j["query"]["pages"] if p.get("coordinates")}
        for t in titles[i:i + 40]:
            u = t
            while u in norm:
                u = norm[u]
            if u in got:
                out[t] = got[u]
    return out


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("stock_exchanges: weekly; not Monday")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pandas", "lxml", "beautifulsoup4"], check=False)
    import pandas as pd
    from bs4 import BeautifulSoup
    html = api(action="parse", page=PAGE, prop="text")["parse"]["text"]
    soup = BeautifulSoup(html, "lxml")
    table = next(t for t in soup.find_all("table", class_="wikitable") if "Market cap" in t.get_text())
    df = pd.read_html(io.StringIO(str(table)))[0]
    df.columns = [" ".join(dict.fromkeys(str(x) for x in (c if isinstance(c, tuple) else (c,)) if not str(x).startswith("Unnamed"))).strip() for c in df.columns]
    # Each row's exchange and city articles, in the table's own order.
    links = []
    for tr in table.find_all("tr"):
        tds = tr.find_all(["td", "th"])
        if not tr.find_all("td"):
            continue
        a = tds[0].find("a", href=re.compile(r"^/wiki/"))
        cells = tr.find_all("td")
        city = None
        for td in cells:
            for x in td.find_all("a", href=re.compile(r"^/wiki/")):
                if x is not a and x.get("title") and not re.search(r"time|Daylight|UTC|Market", x["title"], re.I):
                    city = x["title"]
        if a and a.get("title"):
            links.append((a["title"], city))
    names = [c for c in df.columns if re.search(r"stock exchange", c, re.I)]
    cap = next((c for c in df.columns if re.search(r"market cap", c, re.I)), None)
    rows = df.to_dict("records")
    titles = sorted({t for t, _ in links} | {c for _, c in links if c})
    at = coords(titles)
    feats, unplaced, last_city = [], [], None
    for k, r in enumerate(rows):
        title, city = links[k] if k < len(links) else (None, None)
        city = city or last_city
        last_city = city
        pos, how = (at.get(title), "the exchange's own Wikipedia article") if title in at else (at.get(city), "its city's Wikipedia article") if city in at else (None, None)
        props = {str(c): (None if pd.isna(v) else v) for c, v in r.items()}
        props["name"] = str(r.get(names[0]) if names else title)
        try:
            props["market_cap_usd_tn"] = float(str(r.get(cap)).replace(",", "")) if cap else None
        except ValueError:
            props["market_cap_usd_tn"] = None
        props["article"] = f"https://en.wikipedia.org/wiki/{urllib.parse.quote((title or '').replace(' ', '_'))}"
        if not pos:
            unplaced.append(props["name"])
            continue
        props["position"] = f"from {how}"
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(pos[0], 4), round(pos[1], 4)]}, "properties": props})
    OUT.mkdir(exist_ok=True)
    (OUT / "exchanges.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, default=str))
    stamp.write_text(json.dumps({"page": PAGE, "rows": len(rows), "placed": len(feats), "not_placed": unplaced, "columns": list(df.columns),
                                 "date": datetime.date.today().isoformat()}, indent=1, ensure_ascii=False))
    print(f"stock_exchanges: {len(feats)} of {len(rows)} placed; not placed {unplaced}")


if __name__ == "__main__":
    main()
