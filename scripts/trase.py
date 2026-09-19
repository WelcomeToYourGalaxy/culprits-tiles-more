#!/usr/bin/env python3
"""
Reread Trase's regional measures (trase.earth, CC BY 4.0) and publish them for
Culprits' Trase row.

Trase publishes the full list of what its deforestation map can show at
  https://trase.earth/api/data/spatial-data/indicators
(every measure, for every country, region level and year, with its units,
description and citation). Its region shapes are published separately, and the
map reads those live from resources.trase.earth. Its values cannot be read by
another website, so this script copies them, every measure, level and year:

  trase/catalogue.json                       the menu: countries, levels, measures, years, units, text
  trase/values/<country>/<level>/<METRIC>.json   {year: {region id: value}}
  trase/facilities.json                      which file on resources.trase.earth holds each
                                             facilities map (Trase dates its file names, so
                                             they are found again each week in its page code)

Run weekly by .github/workflows/refresh.yml (Mondays, or by hand).
"""
import json, os, pathlib, sys, time, urllib.parse, urllib.request

BASE = os.environ.get("TRASE", "https://trase.earth").rstrip("/")
OUT = pathlib.Path(os.environ.get("TRASE_OUT", "trase"))


def get(path, tries=4):
    url = BASE + path
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas refresh)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise RuntimeError(f"{url}: {e}") from e
            time.sleep(4 * (i + 1))


FACILITY_TYPES = [  # Trase's facilities menu: its id, what it holds, and a part of its file name
    ("brazil-facilities", "Brazil: slaughterhouses and animal-product facilities", "beef_logistics"),
    ("brazil-silos", "Brazil: soy silos and storage", "silos_"),
    ("cote-d-ivoire-cocoa-cooperatives", "C\u00f4te d'Ivoire: cocoa cooperatives", "coop"),
    ("indonesia-palm-oil-mills", "Indonesia: palm oil mills", "PO_mills"),
    ("indonesia-wood-pulp-mills", "Indonesia: wood pulp mills", "wood_mills"),
    ("indonesia-wood-pulp-concessions-2015-2019", "Indonesia: wood pulp concessions, 2015\u20132019", "concessions_2015_2019"),
    ("indonesia-wood-pulp-concessions-2020-2022", "Indonesia: wood pulp concessions, 2020\u20132022", "concessions_2020_2022"),
    ("indonesia-wood-pulp-concessions-2023-2024", "Indonesia: wood pulp concessions, 2023\u20132024", "concessions_2023_2024"),
]


def facilities():
    """Find the current file behind each facilities map in the page's own code."""
    import re
    page = BASE + "/explore/facilities-data/map?facilityTypeId=brazil-facilities"
    req = urllib.request.Request(page, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas refresh)"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    code = html
    for src in sorted(set(re.findall(r'src="(/_next/static/[^"]+\.js)"', html))):
        try:
            code += urllib.request.urlopen(urllib.request.Request(BASE + src, headers={"User-Agent": "Mozilla/5.0"}),
                                           timeout=60).read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
    files = sorted(set(re.findall(r"[A-Za-z0-9_.\-]+\.geo\.json", code)))
    files = [f for f in files if f not in ("metadata.geo.json",)]
    out, used = [], set()
    for tid, label, part in FACILITY_TYPES:
        hit = [f for f in files if part in f]
        if hit:
            out.append({"id": tid, "label": label, "file": sorted(hit)[-1]})
            used.update(hit)
    # A facilities map Trase adds later still appears, named by its file.
    for f in files:
        if f not in used and not re.search(r"^(country|province|department|municipality|state|region|district|kabupaten|parish|canton|biome|port|mesoregion|microregion)-", f):
            out.append({"id": f.replace(".geo.json", ""), "label": "Trase: " + f.replace(".geo.json", "").replace("_", " "), "file": f})
    return out


def main():
    # Weekly: Mondays, or whenever the workflow is run by hand.
    if time.gmtime().tm_wday != 0 and os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("trase: not Monday; Trase is reread weekly.")
        return
    try:
        fac = facilities()
        if fac:
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / "facilities.json").write_text(json.dumps({"base": "https://resources.trase.earth/data/facilities-data/",
                                                             "types": fac}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"trase: {len(fac)} facilities maps found")
    except Exception as e:  # noqa: BLE001
        print(f"  facilities list could not be read: {e}", file=sys.stderr)
    rows = (get("/api/data/spatial-data/indicators") or {}).get("rows") or []
    if not rows:
        sys.exit("Trase returned no measures; nothing written (the last good copy stays).")
    catalogue = {}
    jobs = []
    for r in rows:
        c, lvl, m = r.get("country_slug"), r.get("node_type_slug"), r.get("metric_name")
        if not (c and lvl and m):
            continue
        entry = catalogue.setdefault(c, {"name": (r.get("country") or c).title(), "levels": {}})
        lv = entry["levels"].setdefault(lvl, {"name": (r.get("level_name") or lvl.replace("-", " ")).title(), "metrics": {}})
        if m in lv["metrics"]:
            continue
        years = sorted(int(y) for y in (r.get("years_available") or []))
        lv["metrics"][m] = {k: r.get(k) for k in (
            "display_name", "unit", "unit_abbreviation", "color_scheme", "metric_group", "commodity",
            "tooltip", "long_description", "data_source", "citation", "is_numerical", "display_order")}
        lv["metrics"][m]["years"] = years
        jobs.append((c, lvl, m, years))
    done = failed = 0
    for c, lvl, m, years in jobs:
        values = {}
        for y in years:
            q = urllib.parse.urlencode({"country_slug": c, "metricName": m, "node_type_slug": lvl,
                                        "year": y, "withTimeseries": "false"})
            try:
                data = get(f"/api/data/spatial-data/indicator?{q}")
            except Exception as e:  # noqa: BLE001
                print(f"  could not read {c} {lvl} {m} {y}: {e}", file=sys.stderr)
                failed += 1
                continue
            yr = {}
            for row in data.get("rows") or []:
                rid = row.get("region_trase_id")
                if not rid:
                    continue
                v = row.get("numerical_value")
                yr[rid] = v if v is not None else row.get("string_value")
            values[str(y)] = yr
            time.sleep(0.15)
        path = OUT / "values" / c / lvl / f"{m}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(values, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        done += 1
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "catalogue.json").write_text(json.dumps({"countries": catalogue}, ensure_ascii=False, separators=(",", ":")),
                                        encoding="utf-8")
    print(f"trase: {done} measures written across {len(catalogue)} countries; {failed} year requests failed")


if __name__ == "__main__":
    main()
