"""Round 123b (asked 2 October: a layer of those most responsible for water
scarcity; "ag does most"). For each country, from FAO AQUASTAT as the World
Bank publishes it (CC BY 4.0), the latest year each figure is given:

  ER.H2O.FWST.ZS  level of water stress: freshwater withdrawn as a share of
                  the renewable freshwater left after nature's needs (SDG 6.4.2)
  ER.H2O.FWAG.ZS  share of withdrawals taken by farming (irrigation, livestock
                  and fish farming)
  ER.H2O.FWIN.ZS  share taken by industry (power plant cooling included)
  ER.H2O.FWDM.ZS  share taken by homes and towns
  ER.H2O.FWTL.K3  all freshwater withdrawn, billion cubic metres a year

Worked out here, and said so on the map: how much of the renewable water
farming alone takes (water stress x farming's share), and industry alone; and
billions of cubic metres withdrawn by farming. Written to water/culprits.json
by ISO3. Weekly (Mondays) or by hand.
"""
import datetime, json, os, pathlib, urllib.request

OUT = pathlib.Path("water")
UA = {"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy)"}
IND = {"ER.H2O.FWST.ZS": "water_stress_pct", "ER.H2O.FWAG.ZS": "farming_share_pct",
       "ER.H2O.FWIN.ZS": "industry_share_pct", "ER.H2O.FWDM.ZS": "homes_share_pct", "ER.H2O.FWTL.K3": "withdrawn_bn_m3"}


def latest(code):
    url = f"https://api.worldbank.org/v2/country/all/indicator/{code}?format=json&per_page=20000&date=1990:{datetime.date.today().year}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        j = json.loads(r.read())
    out = {}
    for row in (j[1] if len(j) > 1 and j[1] else []):
        iso, v = row.get("countryiso3code"), row.get("value")
        if not iso or v is None:
            continue
        y = int(row["date"])
        if iso not in out or y > out[iso][1]:
            out[iso] = (float(v), y, row["country"]["value"])
    return out


def main():
    if (OUT / "culprits.json").exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("water_culprits: weekly; not Monday")
        return
    data = {code: latest(code) for code in IND}
    countries = {}
    for code, key in IND.items():
        for iso, (v, y, name) in data[code].items():
            d = countries.setdefault(iso, {"x_Country": name})
            d[f"x_{key}"] = round(v, 2)
            d[f"x_{key}_year"] = y
    for d in countries.values():
        ws, fa, ind, tot = (d.get("x_water_stress_pct"), d.get("x_farming_share_pct"), d.get("x_industry_share_pct"), d.get("x_withdrawn_bn_m3"))
        if ws is not None and fa is not None:
            d["x_farming_takes_pct_of_renewable"] = round(ws * fa / 100, 1)
        if ws is not None and ind is not None:
            d["x_industry_takes_pct_of_renewable"] = round(ws * ind / 100, 1)
        if tot is not None and fa is not None:
            d["x_farming_withdrawn_bn_m3"] = round(tot * fa / 100, 2)
    # Aggregates (regions, income groups) have codes that are not countries; the
    # map only shades codes it has an outline for, so they stay in the file.
    OUT.mkdir(exist_ok=True)
    (OUT / "culprits.json").write_text(json.dumps(countries, ensure_ascii=False))
    (OUT / "culprits.build.json").write_text(json.dumps({"from": "World Bank API (FAO AQUASTAT)", "indicators": IND, "countries": len(countries),
                                                        "read": datetime.date.today().isoformat()}, indent=1))
    print(f"water_culprits: {len(countries)} countries and groups")


if __name__ == "__main__":
    main()
