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
  trase/facilities/<file>                    a copy of each of those files: Trase's file
                                             server sends no CORS header, so the map cannot
                                             read them from there (checked 22 September)
  trase/regions/metadata.json and <file>     the region shapes the measures are drawn on,
                                             every file Trase's metadata lists: its server
                                             stopped letting the map read them too (the
                                             browser blocked them, 24 September)

Run weekly by .github/workflows/refresh.yml (Mondays, or by hand).
"""
import json, os, pathlib, sys, time, urllib.error, urllib.parse, urllib.request

START = time.monotonic()
BUDGET = float(os.environ.get("TRASE_BUDGET_MIN", "130")) * 60   # the job is stopped at 160 minutes

BASE = os.environ.get("TRASE", "https://trase.earth").rstrip("/")
OUT = pathlib.Path(os.environ.get("TRASE_OUT", "trase"))
TRASE_FILES = "https://resources.trase.earth/data/facilities-data/"
COPY_BASE = "https://welcometoyourgalaxy.github.io/culprits-tiles-more/trase/facilities/"
TRASE_REGIONS = "https://resources.trase.earth/data/trase-regions/"
GITHUB_CAP = 95_000_000          # GitHub refuses files of 100 MB; kept under it with room


def get(path, tries=4):
    url = BASE + path
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas refresh)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Trase answers some measures with a steady 500 (Indonesia's
            # remaining forest, burned area and peat, 23 September): asked once
            # more, then left. A 4xx is not asked again. Four tries with waits
            # on every one of those ran the job past its time limit.
            if e.code < 500 or i >= 1:
                raise RuntimeError(f"{url}: {e}") from e
            time.sleep(3)
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


def fetch_bytes(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Culprits atlas refresh)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def regions():
    """Copy Trase's region shapes: its metadata.json and every file it lists.
    A file that cannot be reread keeps last week's copy; one over GitHub's size
    limit is not copied and is named, and the map reads it from Trase instead."""
    here = OUT / "regions"
    here.mkdir(parents=True, exist_ok=True)
    try:
        body = fetch_bytes(TRASE_REGIONS + "metadata.json", 120)
        meta = json.loads(body.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  region list could not be read ({e}); last week's shapes kept", file=sys.stderr)
        return
    (here / "metadata.json").write_bytes(body)
    files = sorted({m.get("endpoint_geojson") for m in (meta if isinstance(meta, list) else meta.get("rows") or []) if m.get("endpoint_geojson")})
    got = kept = big = failed = 0
    for f in files:
        if time.monotonic() - START > BUDGET / 2:
            print(f"  regions: out of time after {got} files; the rest keep last week's copy", file=sys.stderr)
            break
        dest = here / f
        try:
            data = fetch_bytes(TRASE_REGIONS + f)
            json.loads(data.decode("utf-8"))              # a whole file, not an error page
            if len(data) > GITHUB_CAP:
                big += 1
                print(f"  regions: {f} is {len(data) / 1e6:.0f} MB, over GitHub's limit; the map reads it from Trase", file=sys.stderr)
                if dest.exists():
                    dest.unlink()
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            got += 1
        except Exception as e:  # noqa: BLE001
            if dest.exists():
                kept += 1
            else:
                failed += 1
            print(f"  regions: {f} not read ({e})", file=sys.stderr)
    print(f"trase: {got} of {len(files)} region shape files copied; {kept} kept from last week; "
          f"{big} too large for GitHub; {failed} missing", flush=True)


def main():
    # Weekly: Mondays, or whenever the workflow is run by hand.
    if time.gmtime().tm_wday != 0 and os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("trase: not Monday; Trase is reread weekly.")
        return
    try:
        fac = facilities()
        if fac:
            OUT.mkdir(parents=True, exist_ok=True)
            # Each file copied here; a type whose copy could not be made keeps
            # Trase's own address, and says so, rather than losing its row.
            here = OUT / "facilities"
            here.mkdir(parents=True, exist_ok=True)
            for t in fac:
                try:
                    req = urllib.request.Request(TRASE_FILES + t["file"], headers={"User-Agent": "Mozilla/5.0 (Culprits atlas refresh)"})
                    with urllib.request.urlopen(req, timeout=300) as r:
                        body = r.read()
                    json.loads(body.decode("utf-8"))          # a whole file, not an error page
                    (here / t["file"]).write_bytes(body)
                    t["base"] = COPY_BASE
                except Exception as e:  # noqa: BLE001
                    if (here / t["file"]).exists():
                        t["base"] = COPY_BASE
                        print(f"  {t['file']}: not reread ({e}); last week's copy kept", file=sys.stderr)
                    else:
                        print(f"  {t['file']}: could not be copied ({e})", file=sys.stderr)
            (OUT / "facilities.json").write_text(json.dumps({"base": TRASE_FILES, "types": fac}, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"trase: {len(fac)} facilities maps found, {sum(1 for t in fac if t.get('base') == COPY_BASE)} copied", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"  facilities list could not be read: {e}", file=sys.stderr)
    regions()
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
    done = failed = left = 0
    for c, lvl, m, years in jobs:
        # Out of time: the measures not reached keep last week's copy, and the
        # menu is still written, rather than the job being stopped mid-file.
        if time.monotonic() - START > BUDGET:
            left += 1
            continue
        path = OUT / "values" / c / lvl / f"{m}.json"
        # A year Trase will not give today keeps the value last copied for it.
        try:
            values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except Exception:  # noqa: BLE001
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(values, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        done += 1
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "catalogue.json").write_text(json.dumps({"countries": catalogue}, ensure_ascii=False, separators=(",", ":")),
                                        encoding="utf-8")
    print(f"trase: {done} measures written across {len(catalogue)} countries; {failed} year requests failed"
          + (f"; {left} not reached in the time allowed, last week's copies kept" if left else ""), flush=True)


if __name__ == "__main__":
    main()
