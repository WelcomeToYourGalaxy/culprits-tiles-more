#!/usr/bin/env python3
"""
Land and environmental defenders killed, from Global Witness (round 84b, asked
27 September), for the Culprits map's rows under Invasion of humans and under
Destruction > Of individuals > Of humans.

Global Witness allows its data to be downloaded and shared for non-commercial
use, in line with its terms. Its "In numbers" page draws its charts with
Datawrapper; this reads the page, finds every chart on it, and copies each
chart's own data table:

  global_witness/charts/<chart id>.csv   each chart's table, as published
  global_witness/charts.json             each chart's title and columns
  global_witness/countries.json          where one chart gives a figure per
                                         country: ISO3 -> every column of that
                                         country's row, "value" its total

Weekly.
"""
import csv, io, json, os, pathlib, re, subprocess, sys, time, urllib.request

PAGE = "https://globalwitness.org/en/campaigns/land-and-environmental-defenders/in-numbers-lethal-attacks-against-defenders-since-2012/"
OUT = pathlib.Path("global_witness")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas; welcometoyourgalaxy@gmail.com)"}
KNOWN = ["rhBcA", "8Hdke", "Os5Qu", "lHwRF"]


def get(url, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read().decode("utf-8", "replace")


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


def main():
    stamp = OUT / "charts.json"
    if stamp.exists() and time.time() - stamp.stat().st_mtime < 6 * 24 * 3600 and not os.environ.get("GW_REBUILD"):
        print("global_witness: copied less than a week ago")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pycountry"], check=True)
    import pycountry
    ids = list(KNOWN)
    try:
        _, page = get(PAGE)
        ids = sorted(set(ids) | set(re.findall(r"datawrapper\.dwcdn\.net/([A-Za-z0-9]{5})", page)))
    except Exception as e:  # noqa: BLE001
        print(f"global_witness: the page did not answer ({e}); the known charts are read", flush=True)
    (OUT / "charts").mkdir(parents=True, exist_ok=True)
    charts, countries = {}, {}
    for cid in ids:
        try:
            final, html = get(f"https://datawrapper.dwcdn.net/{cid}/")
            m = re.search(r'url=([^"]+)"', html)                      # the chart page points to its latest version
            if m and "dwcdn" in m.group(1):
                final, html = get(m.group(1) if m.group(1).startswith("http") else f"https:{m.group(1)}")
            base = final if final.endswith("/") else final.rsplit("/", 1)[0] + "/"
            _, data = get(base + "dataset.csv")
        except Exception as e:  # noqa: BLE001
            print(f"  {cid}: {e}", flush=True)
            continue
        title = re.sub(r"\s+", " ", (re.search(r"<title>([\s\S]*?)</title>", html) or [None, cid])[1]).strip()
        (OUT / "charts" / f"{cid}.csv").write_text(data)
        rows = list(csv.reader(io.StringIO(data), delimiter="\t" if data.count("\t") > data.count(",") else ","))
        if not rows:
            continue
        head = rows[0]
        charts[cid] = {"title": title, "columns": head, "rows": len(rows) - 1, "from": base}
        # A chart with a country column and figures: one record per country.
        cc = next((i for i, h in enumerate(head) if re.search(r"countr|pa[ií]s|nation", h, re.I)), None)
        if cc is None:
            continue
        for r in rows[1:]:
            if cc >= len(r) or not r[cc].strip():
                continue
            try:
                iso = pycountry.countries.lookup(r[cc].strip()).alpha_3
            except LookupError:
                try:
                    iso = pycountry.countries.search_fuzzy(r[cc].strip())[0].alpha_3
                except LookupError:
                    continue
            rec = countries.setdefault(iso, {"value": 0, "unit": "defenders killed or disappeared"})
            vals = [num(x) for i, x in enumerate(r) if i != cc]
            for i, x in enumerate(r):
                if i != cc and x.strip():
                    rec[f"x_{title[:40]} — {head[i]}"] = x
            total = next((num(r[i]) for i, h in enumerate(head) if re.search(r"total", h, re.I) and i < len(r)), None)
            rec["value"] = max(rec["value"], total if total is not None else sum(v for v in vals if v) or 0)
            rec["x_country"] = r[cc]
    stamp.write_text(json.dumps(charts, indent=1, ensure_ascii=False))
    (OUT / "countries.json").write_text(json.dumps(countries, indent=1, ensure_ascii=False))
    print(f"global_witness: {len(charts)} charts, {len(countries)} countries")


if __name__ == "__main__":
    main()
