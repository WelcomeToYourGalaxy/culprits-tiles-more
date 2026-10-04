"""
World Benchmarking Alliance, Nature Benchmark: every company it assessed, with
every column of its benchmark rows, placed at the capital of its headquarters
country (round 172b of the culprits map; redoes the lost round 148b).

Licence: CC BY 4.0 (WBA's disclaimer page). Read through WBA's Data API
(https://data.worldbenchmarkingalliance.org/api/data/v1, documented at
https://www.worldbenchmarkingalliance.org/documentation/api-specification):
one request a second, Bearer key in the secret WBA_API_KEY.

Without the key it writes wba/build.json saying so and stops without failing.
Nothing is guessed: the benchmark, country and year columns are found by
their names and written to wba/build.json; WBA's own column list goes to
wba/columns.json. Countries are matched exactly (ISO code or the country's
own name); the unmatched are listed, not placed.

Writes wba/nature_companies.geojson, wba/build.json, wba/columns.json.
"""
import json, math, os, pathlib, subprocess, sys, time, urllib.parse, urllib.request

BASE = "https://data.worldbenchmarkingalliance.org/api/data/v1"
OUT = pathlib.Path("wba")
CITE = "World Benchmarking Alliance, Nature Benchmark (CC BY 4.0), data.worldbenchmarkingalliance.org"
_last = [0.0]


def api(path, **params):
    wait = 1.1 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"accept": "application/json", "Authorization": f"Bearer {os.environ['WBA_API_KEY']}",
                                               "User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"})
    for attempt in range(4):
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise


def rows(name):
    out, page = [], 1
    while True:
        j = api(f"/datasets/{name}", per_page=1000, page=page)
        data = j.get("data") or []
        out += data
        total = (j.get("meta") or {}).get("rows")
        if not data or (total is not None and len(out) >= total) or len(data) < 1000:
            return out
        page += 1


def col(cols, *words, avoid=()):
    """The first column whose name holds every word (and none of avoid)."""
    for c in cols:
        n = c.lower()
        if all(w in n for w in words) and not any(a in n for a in avoid):
            return c
    return None


def main():
    OUT.mkdir(exist_ok=True)
    status = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "source": CITE}
    if not os.environ.get("WBA_API_KEY"):
        status.update(built=False, reason="No WBA_API_KEY secret yet. Request access at data.worldbenchmarkingalliance.org, "
                      "then add the secret and the line WBA_API_KEY: ${{ secrets.WBA_API_KEY }} in refresh.yml.")
        (OUT / "build.json").write_text(json.dumps(status, indent=1))
        print("::warning::wba_nature: no WBA_API_KEY; nothing read")
        return
    try:
        import pycountry
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pycountry"], check=True)
        import pycountry
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    from forest500_map import capitals

    cols = {n: api(f"/datasets/{n}/cols") for n in ("benchmarks", "companies")}
    (OUT / "columns.json").write_text(json.dumps(cols, indent=1, ensure_ascii=False))
    bench, comps = rows("benchmarks"), rows("companies")
    bcols = [c["name"] for c in cols["benchmarks"]] or sorted({k for r in bench for k in r})
    ccols = [c["name"] for c in cols["companies"]] or sorted({k for r in comps for k in r})
    which = col(bcols, "benchmark", "name") or col(bcols, "benchmark", avoid=("score", "id", "rank", "year"))
    cid_b, cid_c = col(bcols, "company", "id"), col(ccols, "company", "id")
    year = col(bcols, "year")
    country = col(ccols, "headquarter") or col(ccols, "country", avoid=("operat", "number"))
    status["columns used"] = {"benchmark": which, "company id (benchmarks)": cid_b, "company id (companies)": cid_c,
                              "year": year, "headquarters country": country}
    status["benchmarks seen"] = sorted({str(r.get(which)) for r in bench}) if which else []
    if not (which and cid_b and cid_c and country):
        status.update(built=False, reason="A needed column was not found by name; see columns.json")
        (OUT / "build.json").write_text(json.dumps(status, indent=1, ensure_ascii=False))
        print("::warning::wba_nature: column not found; see wba/columns.json")
        return
    nature = [r for r in bench if "nature" in str(r.get(which) or "").lower()]
    by_co = {}
    for r in nature:
        by_co.setdefault(r.get(cid_b), []).append(r)
    info = {c.get(cid_c): c for c in comps}
    caps = capitals()
    feats, unplaced, spin = [], [], {}
    for co, rs in sorted(by_co.items(), key=lambda kv: str(kv[0])):
        c = info.get(co) or {}
        hq = str(c.get(country) or "").strip()
        code = None
        if hq:
            try:
                code = pycountry.countries.lookup(hq).alpha_3
            except LookupError:
                code = None
        cap = caps.get(code) if code else None
        name = c.get(col(ccols, "company", "name") or "") or co
        if not cap:
            unplaced.append({"company": name, "headquarters": hq})
            continue
        i = spin[code] = spin.get(code, -1) + 1
        ang, rad = math.radians(137.508 * i), 0.12 * math.sqrt(i)
        lon = cap[0] + rad * math.cos(ang) / max(0.3, math.cos(math.radians(cap[1])))
        lat = max(-85, min(85, cap[1] + rad * math.sin(ang)))
        p = {"name": name}
        p.update({k: v for k, v in c.items() if v not in (None, "")})
        for r in sorted(rs, key=lambda r: str(r.get(year) or ""), reverse=True):
            y = r.get(year) if year else None
            for k, v in r.items():
                if v not in (None, ""):
                    p[f"{y}: {k}" if y else k] = v
        p["placed at"] = (f"the capital of its headquarters country ({cap[2]})" if cap[3] == "capital" else
                          f"{cap[2]}, the most populous place Natural Earth lists in its headquarters country") + \
                         "; WBA gives the country, not the address. Spread around it so each can be clicked."
        p["source"] = CITE
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": {k: (v if isinstance(v, (int, float, str, bool)) else json.dumps(v, ensure_ascii=False)) for k, v in p.items()}})
    (OUT / "nature_companies.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    status.update(built=True, benchmark_rows=len(bench), nature_rows=len(nature), companies=len(by_co),
                  placed=len(feats), not_placed=unplaced)
    (OUT / "build.json").write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"wba_nature: {len(feats)} placed, {len(unplaced)} not placed")


if __name__ == "__main__":
    main()
