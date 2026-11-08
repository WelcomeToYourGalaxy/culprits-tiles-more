#!/usr/bin/env python3
"""
Fish stocks worldwide and how far they have been fished down (round 137b,
asked 2 October: a layer on the decline of salt and fresh water fish). The RAM
Legacy Stock Assessment Database (Zenodo, CC BY 4.0; Ricard et al. 2012, Fish
and Fisheries 13:380-398): the scientific assessments of commercially fished
stocks, mostly at sea.

For every stock, its latest year with a figure of B/Bmsy (the stock's size
over the size that would give the most catch year after year; under 1 means
fished below it) and of U/Umsy (how hard it is fished over the rate that
would). Then, for each country the database names for a stock's area:

  fish/ram_countries.json   ISO3 -> {value: share of its assessed stocks below
                            B/Bmsy 1 (%), every count, and every stock with
                            its figures and years}
  fish/ram_build.json       version, sheets read, countries the database names
                            that are not one country (e.g. multinational),
                            with their stocks

Nothing is dropped: stocks with no B/Bmsy are counted as such. The newest
version is found from the Zenodo concept record. Weekly (Sundays), or by hand.
"""
import datetime, io, json, os, pathlib, re, sys, tempfile, urllib.request, zipfile

CONCEPT = "https://zenodo.org/api/records/14043031/versions/latest"
OUT = pathlib.Path("fish")
UA = {"User-Agent": "Culprits atlas build (welcometoyourgalaxy@gmail.com)"}
# The names RAM writes for countries, where they are not the country's
# standard English name. Anything else is matched by pycountry by exact name.
NAMES = {"USA": "USA", "United States": "USA", "Russia": "RUS", "Russian Federation": "RUS", "South Korea": "KOR", "Korea": "KOR",
         "Iran": "IRN", "Vietnam": "VNM", "Taiwan": "TWN", "UK": "GBR", "United Kingdom": "GBR", "Venezuela": "VEN",
         "Tanzania": "TZA", "Bolivia": "BOL", "Falkland Islands": "FLK", "Turkey": "TUR", "Syria": "SYR", "Laos": "LAO"}


def iso_of(name):
    if name in NAMES:
        return NAMES[name]
    import pycountry
    for k in ("name", "official_name", "common_name"):
        for c in pycountry.countries:
            if getattr(c, k, None) == name:
                return c.alpha_3
    return None


def main():
    if (OUT / "ram_countries.json").exists() and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("fish_stocks: weekly; not Sunday")
        return
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl", "pandas", "pycountry"], check=True)
    import pandas as pd
    rec = json.loads(urllib.request.urlopen(urllib.request.Request(CONCEPT, headers=UA), timeout=120).read())
    files = rec.get("files") or []
    f = next(x for x in files if x["key"].lower().endswith(".zip"))
    url = f["links"]["self"]
    print(f"fish_stocks: {rec.get('metadata', {}).get('version')} {f['key']}", flush=True)
    z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=1800).read()))
    xl = [n for n in z.namelist() if n.lower().endswith(".xlsx") and "assessment" in n.lower()] or [n for n in z.namelist() if n.lower().endswith(".xlsx")]
    if not xl:
        raise SystemExit(f"fish_stocks: no Excel file in the zip: {z.namelist()[:30]}")
    path = pathlib.Path(tempfile.gettempdir()) / "ram.xlsx"
    path.write_bytes(z.read(xl[0]))
    sheets = pd.ExcelFile(path).sheet_names
    want = lambda name: next((s for s in sheets if s.lower() == name), None)
    stock = pd.read_excel(path, sheet_name=want("stock"))
    area = pd.read_excel(path, sheet_name=want("area"))
    tsname = want("timeseries_values_views")
    ts = pd.read_excel(path, sheet_name=tsname, usecols=lambda c: c in ("stockid", "year", "BdivBmsypref", "UdivUmsypref"))
    latest = {}
    for col in ("BdivBmsypref", "UdivUmsypref"):
        if col not in ts.columns:
            continue
        t = ts.dropna(subset=[col]).sort_values("year").groupby("stockid").tail(1)
        for r in t.itertuples():
            latest.setdefault(r.stockid, {})[col] = (float(getattr(r, col)), int(r.year))
    st = stock.merge(area[["areaid", "country", "areaname"]], on="areaid", how="left")
    out, not_country = {}, {}
    for r in st.itertuples():
        name = str(r.country) if r.country == r.country else "not given"
        iso = iso_of(name)
        L = latest.get(r.stockid, {})
        b, u = L.get("BdivBmsypref"), L.get("UdivUmsypref")
        entry = {"stock": r.stocklong, "species": r.scientificname, "common name": getattr(r, "commonname", ""), "area": r.areaname,
                 "B/Bmsy": round(b[0], 3) if b else None, "B/Bmsy year": b[1] if b else None,
                 "U/Umsy": round(u[0], 3) if u else None, "U/Umsy year": u[1] if u else None}
        if not iso:
            not_country.setdefault(name, []).append(entry)
            continue
        c = out.setdefault(iso, {"x_country as RAM writes it": name, "stocks": []})
        c["stocks"].append(entry)
    for iso, c in out.items():
        bs = [s["B/Bmsy"] for s in c["stocks"] if s["B/Bmsy"] is not None]
        below = sum(1 for v in bs if v < 1)
        c["value"] = round(100 * below / len(bs), 1) if bs else None
        c["x_stocks assessed"] = len(c["stocks"])
        c["x_stocks with a B/Bmsy figure"] = len(bs)
        c["x_below the size that gives the most catch (B/Bmsy under 1)"] = below
        c["x_below half of it (B/Bmsy under 0.5)"] = sum(1 for v in bs if v < 0.5)
        c["x_fished harder than the rate that gives the most catch (U/Umsy over 1)"] = sum(1 for s in c["stocks"] if s["U/Umsy"] is not None and s["U/Umsy"] > 1)
        c["x_every stock (latest B/Bmsy, year)"] = "; ".join(f'{s["stock"]}: {s["B/Bmsy"] if s["B/Bmsy"] is not None else "no figure"}'
                                                            f'{" (" + str(s["B/Bmsy year"]) + ")" if s["B/Bmsy year"] else ""}' for s in c["stocks"])
        del c["stocks"]
    OUT.mkdir(exist_ok=True)
    (OUT / "ram_countries.json").write_text(json.dumps({k: v for k, v in out.items() if v["value"] is not None}, ensure_ascii=False, indent=1))
    (OUT / "ram_build.json").write_text(json.dumps({"read": datetime.date.today().isoformat(), "version": rec.get("metadata", {}).get("version"),
                                                    "file": xl[0], "sheets": sheets, "countries": len(out),
                                                    "countries_with_no_B_figure": sorted(k for k, v in out.items() if v["value"] is None),
                                                    "not_one_country": not_country}, ensure_ascii=False, indent=1, default=str))
    print(f"fish_stocks: {len(out)} countries; not one country: {sorted(not_country)}", flush=True)


if __name__ == "__main__":
    main()
