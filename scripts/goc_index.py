#!/usr/bin/env python3
"""
Environmental crime by country, from the Global Organized Crime Index (round
85b, asked 27 September: the nearest thing there is to a worldwide record of
environmental crime; no register covers the world).

The Global Initiative Against Transnational Organized Crime scores all 193 UN
member states, among other markets, on three environmental crimes, each from
1 (little or no presence) to 10 (the most pervasive and harmful):

  flora crimes                  illegal logging, the timber trade and protected plants
  fauna crimes                  poaching, wildlife trafficking and illegal fishing
  non-renewable resource crimes illegal mining, oil and fuel theft, gold and minerals

This reads the workbook it publishes for download (ocindex.net/downloads) and
writes

  goc/countries.json   ISO3 -> {flora, fauna, resources: the newest year's
                       scores; x_<year> <column>: every column of every year
                       the workbook gives, so nothing it publishes is left out}
  goc/source.xlsx      the workbook as downloaded
  goc/status.json      the sheets and columns read

Weekly.
"""
import io, json, os, pathlib, re, subprocess, sys, time, urllib.request

URL = "https://ocindex.net/assets/downloads/global_oc_index.xlsx"
OUT = pathlib.Path("goc")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas; welcometoyourgalaxy@gmail.com)"}
WANT = {"flora": r"flora", "fauna": r"fauna", "resources": r"non.?renewable"}
# Names the country lookup does not know.
ALIASES = {"Congo, Dem. Rep.": "COD", "DR Congo": "COD", "Democratic Republic of the Congo": "COD", "Congo, Rep.": "COG",
           "Republic of the Congo": "COG", "Congo": "COG", "Côte d'Ivoire": "CIV", "Cote d'Ivoire": "CIV", "Ivory Coast": "CIV",
           "Türkiye": "TUR", "Turkey": "TUR", "Russia": "RUS", "Iran": "IRN", "Syria": "SYR", "Laos": "LAO", "Vietnam": "VNM",
           "Bolivia": "BOL", "Venezuela": "VEN", "Tanzania": "TZA", "Moldova": "MDA", "North Korea": "PRK", "South Korea": "KOR",
           "Korea, DPR": "PRK", "Korea, Rep.": "KOR", "Micronesia": "FSM", "Micronesia (Federated States of)": "FSM",
           "Brunei": "BRN", "Cabo Verde": "CPV", "Cape Verde": "CPV", "Eswatini": "SWZ", "Swaziland": "SWZ",
           "Timor-Leste": "TLS", "East Timor": "TLS", "Palestine": "PSE", "Kosovo": "XKX", "The Gambia": "GMB", "Gambia": "GMB",
           "The Bahamas": "BHS", "Bahamas": "BHS", "Saint Kitts and Nevis": "KNA", "Saint Lucia": "LCA",
           "Saint Vincent and the Grenadines": "VCT", "Sao Tome and Principe": "STP", "São Tomé and Príncipe": "STP",
           "United States": "USA", "United States of America": "USA", "United Kingdom": "GBR", "Czechia": "CZE",
           "Czech Republic": "CZE", "North Macedonia": "MKD", "Myanmar": "MMR"}


def get(url, timeout=180):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == 2:
                raise
            print(f"  {url}: {e}; again", flush=True)
            time.sleep(20 * (i + 1))


def iso3(name, pycountry):
    n = str(name or "").strip()
    if not n:
        return None
    if n in ALIASES:
        return ALIASES[n]
    try:
        return pycountry.countries.lookup(n).alpha_3
    except LookupError:
        try:
            return pycountry.countries.search_fuzzy(n)[0].alpha_3
        except LookupError:
            return None


def main():
    stamp = OUT / "status.json"
    if stamp.exists() and time.time() - stamp.stat().st_mtime < 6 * 24 * 3600 and not os.environ.get("GOC_REBUILD"):
        print("goc_index: copied less than a week ago")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl", "pycountry"], check=True)
    import openpyxl
    import pycountry
    raw = get(URL)
    OUT.mkdir(exist_ok=True)
    (OUT / "source.xlsx").write_bytes(raw)
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    out, status, unplaced = {}, {"from": URL, "sheets": {}}, set()
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        # The header is the first row naming a country column and at least one of the three crimes.
        hi = next((i for i, r in enumerate(rows[:30]) if any(re.search(r"^country$|country name", str(c or ""), re.I) for c in r)
                   and any(re.search(p, str(c or ""), re.I) for c in r for p in WANT.values())), None)
        if hi is None:
            status["sheets"][ws.title] = "no country and crime columns"
            continue
        head = [str(c or "").strip() for c in rows[hi]]
        cc = next(i for i, h in enumerate(head) if re.search(r"^country$|country name", h, re.I))
        yc = next((i for i, h in enumerate(head) if re.fullmatch(r"year|edition", h, re.I)), None)
        cols = {k: next((i for i, h in enumerate(head) if re.search(p, h, re.I)), None) for k, p in WANT.items()}
        year_of_sheet = (re.search(r"(20\d\d)", ws.title) or [None, None])[1]
        status["sheets"][ws.title] = {"columns": head, "rows": len(rows) - hi - 1}
        for r in rows[hi + 1:]:
            if cc >= len(r) or not r[cc]:
                continue
            iso = iso3(r[cc], pycountry)
            if not iso:
                unplaced.add(str(r[cc]))
                continue
            year = str(r[yc]) if yc is not None and yc < len(r) and r[yc] else year_of_sheet or ws.title
            rec = out.setdefault(iso, {"x_country": str(r[cc]).strip()})
            for i, h in enumerate(head):
                if i != cc and h and i < len(r) and r[i] not in (None, ""):
                    rec[f"x_{year} {h}"] = r[i]
            newest = rec.get("_year")
            if newest is None or str(year) >= str(newest):
                for k, i in cols.items():
                    if i is not None and i < len(r):
                        try:
                            rec[k] = float(r[i])
                        except (TypeError, ValueError):
                            pass
                rec["_year"] = year
    for rec in out.values():
        rec["x_year of the scores shown"] = rec.pop("_year", None)
    (OUT / "countries.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    status["countries"] = len(out)
    status["not placed"] = sorted(unplaced)
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False, default=str))
    print(f"goc_index: {len(out)} countries" + (f"; not placed: {sorted(unplaced)}" if unplaced else ""))


if __name__ == "__main__":
    main()
