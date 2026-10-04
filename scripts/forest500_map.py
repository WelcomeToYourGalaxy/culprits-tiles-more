#!/usr/bin/env python3
"""
Every company and financial institution Forest 500 has assessed, and its 2022
country selection, for the map (round 122b, asked 2 October 2026: "i
downloaded all of forest 500's data; add all").

Forest 500 (Global Canopy) assesses the companies and financial institutions
with the most influence over tropical deforestation: 2014 to 2025, the
companies by their policies on palm oil, soy, cattle, timber, pulp and paper
(and cocoa, coffee and rubber from 2024), the institutions by the policies
they apply to the money they put into them. Licence: Creative Commons
Attribution-NonCommercial 4.0; cite "Forest 500 assessment data [Year],
Global Canopy, Forest500.org".

Read from:
  forest500/rankings.json   every company and institution by year, with its
                            scores, sectors, commodities and profile, from
                            Forest 500's own API (scripts/defor_funds.py)
  forest500/details.json    the describing columns of each row of Forest
                            500's downloaded masterfiles (website, ownership,
                            operating countries, powerbroker roles, scores
                            by group; scripts/forest500_details.py)
  forest500/download/country_selection_data_2022.xlsx   Forest 500's 2022
                            selection of producer and trading countries

Writes:
  forest500/companies.geojson     one point per company (as Forest 500 names
  forest500/institutions.geojson  it), every year's score in its box, the
                                  latest year's details in full
  forest500/producer_countries.json, forest500/trading_countries.json
                                  ISO3 -> every figure of the sheet's row
  forest500/map.build.json        counts, and anything not placed

Forest 500 gives each one's headquarters country, not its address. Each is
placed at its headquarters country's capital (Natural Earth's populated
places, public domain), spread in a small spiral around it so each can be
clicked; where in the spiral means nothing. The box says so.

Weekly (Mondays, after defor_funds.py has read the API), or by hand.
"""
import datetime, json, math, os, pathlib, subprocess, sys, time, urllib.request

F = pathlib.Path("forest500")
NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_populated_places_simple.geojson"
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
CITE = "Forest 500 assessment data {y}, Global Canopy, Forest500.org (CC BY-NC 4.0)"
# Forest 500's names for places Natural Earth or pycountry write otherwise.
ALIAS = {"democratic republic of congo": "COD", "republic of congo": "COG", "cote d'ivoire": "CIV", "côte d'ivoire": "CIV",
         "south korea": "KOR", "taiwan": "TWN", "turkey": "TUR", "russia": "RUS", "iran": "IRN", "vietnam": "VNM",
         "bolivia": "BOL", "venezuela": "VEN", "laos": "LAO", "tanzania": "TZA", "hong kong": "HKG", "macau": "MAC",
         "british virgin islands": "VGB", "jersey": "JEY", "guernsey": "GGY", "bermuda": "BMU", "cayman islands": "CYM",
         "uk": "GBR", "democratic republic of the congo": "COD", "rep. of korea": "KOR", "usa": "USA", "the netherlands": "NLD", "czech republic": "CZE", "swaziland": "SWZ"}
GROUPS = [("overall_app", "Overall approach"), ("com_total_app", "Commodities together"), ("commit_strength_app", "Commitment strength"),
          ("policy_strength_app", "Policy strength"), ("impl_rpt_app", "Implementation and reporting"), ("impl_app", "Implementation"),
          ("rpt_verif_app", "Reporting and verification"), ("human_rights_app", "Human rights")]


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
        return r.read()


def iso3(name, pycountry):
    n = (name or "").strip()
    if not n:
        return None
    if n.lower() in ALIAS:
        return ALIAS[n.lower()]
    try:
        return pycountry.countries.lookup(n).alpha_3
    except LookupError:
        try:
            return pycountry.countries.search_fuzzy(n)[0].alpha_3
        except LookupError:
            return None


def capitals():
    """ISO3 -> (lon, lat, city): each country's capital, the most populous where there are several."""
    # A country's own capital first; a territory's (Bermuda, the British
    # Virgin Islands: Natural Earth calls these region capitals) where the
    # place has none of its own.
    best = {}
    feats = json.loads(get(NE))["features"]
    # Round 172b: a place Natural Earth gives no capital at all (the British
    # Virgin Islands: Road Town is listed only as a town) takes its most
    # populous listed place, and the box says so rather than "capital".
    for kinds in (("Admin-0 capital",), ("Admin-0 region capital", "Admin-0 capital alt"), None):
        found = {}
        for f in feats:
            p = f["properties"]
            if kinds is not None and p.get("featurecla") not in kinds:
                continue
            for code in [p.get("adm0_a3")] + ([p.get("sov_a3")] if kinds and kinds[0] == "Admin-0 capital" else []):
                if code and code not in best and (code not in found or (p.get("pop_max") or 0) > found[code][3]):
                    found[code] = (p["longitude"], p["latitude"], p["name"], p.get("pop_max") or 0,
                                   "capital" if kinds is not None else "town")
        best.update(found)
    return {k: (v[0], v[1], v[2], v[4]) for k, v in best.items()}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def entities(kind, ranks, details, caps, pycountry):
    rows = {}
    for r in ranks:
        if r["cotype"] != kind:
            continue
        key = (r["coname"].strip(), r["ayear"])
        if key not in rows or (r.get("optional_cols") and not rows[key].get("optional_cols")):
            rows[key] = r
    by = {}
    for (name, year), r in rows.items():
        by.setdefault(name, {})[year] = r
    feats, unplaced, spin = [], [], {}
    for name in sorted(by):
        years = by[name]
        last = max(years)
        r = years[last]
        # The describing columns from the latest year whose download has it.
        dy = max((y for y in years if name in (details.get(kind, {}).get(str(y)) or {})), default=None)
        det = details[kind][str(dy)][name] if dy else {}
        hq = r.get("cohq") or det.get("HQ") or det.get("FI Headquarters")
        code = iso3(hq, pycountry)
        cap = caps.get(code) if code else None
        if not cap:
            unplaced.append({"name": name, "headquarters": hq})
            continue
        i = spin[code] = spin.get(code, -1) + 1
        ang, rad = math.radians(137.508 * i), 0.12 * math.sqrt(i)
        lon = cap[0] + rad * math.cos(ang) / max(0.3, math.cos(math.radians(cap[1])))
        lat = max(-85, min(85, cap[1] + rad * math.sin(ang)))
        comm = r.get("commodities") or []
        p = {"name": name,
             "total score, last assessed (out of 100)": round(num(r.get("totalscore")), 1) if num(r.get("totalscore")) is not None else None,
             "last assessed": last,
             "rank within that year": r.get("ranking_within_year"),
             "every year's total score": "; ".join(f"{y}: {round(num(years[y].get('totalscore')), 1) if num(years[y].get('totalscore')) is not None else 'not given'}" for y in sorted(years, reverse=True)),
             "years assessed": len(years),
             "headquarters": hq,
             "region": det.get("HQ Region") or det.get("FI HQ Region") or "",
             "commodities": "; ".join(sorted({c.get("commodity_name") for c in comm if c.get("commodity_name")})),
             "roles": "; ".join(sorted({c.get("segment") for c in comm if c.get("segment") and c.get("segment") != "NA"})),
             "commodities and roles": "; ".join(sorted({f"{c.get('commodity_name')} ({c.get('segment')})" for c in comm if c.get("commodity_name")})),
             "sectors": (r.get("cosectors") or "").replace("|", "; "),
             "ticker or Forest 500 code": r.get("coticker"),
             "brands": "; ".join(str(b) for b in r["brands"] if b) if isinstance(r.get("brands"), list) else r.get("brands"),
             "about (Forest 500)": r.get("coprofile")}
        for k, label in GROUPS:
            if r.get(f"{k}_max_pts"):
                p[f"{label}, {last} (points)"] = f"{r.get(f'{k}_pts')} of {r.get(f'{k}_max_pts')}"
        for k, v in det.items():
            if k == "_answers":
                p[f"indicator answers in Forest 500's {dy} file"] = v
            else:
                p[f"x_{k} ({dy})"] = v
        p["placed at"] = ((f"the capital of its headquarters country ({cap[2]})" if cap[3] == "capital" else
                           f"{cap[2]}, the most populous place Natural Earth lists in its headquarters country (Natural Earth names no capital there)") +
                          "; Forest 500 gives the country, not the address. "
                          "Spread around the capital so each can be clicked; where in the spread means nothing.")
        p["source"] = CITE.format(y=last)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 4), round(lat, 4)]},
                      "properties": {k: v for k, v in p.items() if v not in (None, "")}})
    return feats, unplaced


def countries(pycountry):
    xl = F / "download" / "country_selection_data_2022.xlsx"
    if not xl.exists():
        return {"not read": "no country_selection_data_2022.xlsx in forest500/download/"}
    try:
        import openpyxl
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "openpyxl"], check=True)
        import openpyxl
    wb = openpyxl.load_workbook(xl, data_only=True)
    status = {}
    for ws, out, head_at in ((wb["Producer Countries"], "producer_countries.json", 1), (wb["Trading Countries"], "trading_countries.json", 2)):
        rows = list(ws.iter_rows(values_only=True))
        head = [str(c).strip() if c is not None else "" for c in rows[head_at]]
        recs, unplaced = {}, []
        for r in rows[head_at + 1:]:
            if not r or not r[0]:
                continue
            code = iso3(str(r[0]), pycountry)
            if not code:
                unplaced.append(r[0])
                continue
            rec = {"name": str(r[0]).strip()}
            for h, v in zip(head[1:], r[1:]):
                if h and v is not None:
                    rec[f"x_{h}"] = ("yes" if v == 1 else "no") if h in ("Beef", "Leather", "Palm Oil", "Pulp and Paper", "Soy", "Timber") else v
            recs[code] = rec
        (F / out).write_text(json.dumps(recs, ensure_ascii=False, indent=0))
        status[out] = {"countries": len(recs), "not placed": unplaced, "columns": head}
    return status


def main():
    stamp = F / "map.build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("forest500_map: weekly; not Monday")
        return
    try:
        import pycountry
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pycountry"], check=True)
        import pycountry
    ranks = json.loads((F / "rankings.json").read_text(encoding="utf-8"))["rows"]
    details = json.loads((F / "details.json").read_text(encoding="utf-8")) if (F / "details.json").exists() else {}
    caps = capitals()
    status = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "capitals": len(caps)}
    for kind, out in (("CO", "companies.geojson"), ("FI", "institutions.geojson")):
        feats, unplaced = entities(kind, ranks, details, caps, pycountry)
        (F / out).write_text(json.dumps({"type": "FeatureCollection", "licence": "CC BY-NC 4.0; Forest 500 assessment data, Global Canopy, Forest500.org",
                                         "features": feats}, ensure_ascii=False, separators=(",", ":")))
        status[out] = {"placed": len(feats), "not placed": unplaced}
    status.update(countries(pycountry))
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print("forest500_map:", json.dumps({k: (v if not isinstance(v, dict) else {a: b for a, b in v.items() if a != "columns"}) for k, v in status.items()}, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
