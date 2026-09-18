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


def main():
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
