#!/usr/bin/env python3
"""
Sea Around Us reconstructed catch (round 140b, asked 2 October: "add Sea Around
Us"). The University of British Columbia's Sea Around Us rebuilds each
country's catch from 1950, adding what official statistics leave out:
unreported, illegal and small-scale catch and fish thrown back dead
(discards). CC BY-NC 4.0; cite Pauly, Zeller and Palomares (2020), Sea Around
Us Concepts, Design and Data (seaaroundus.org).

Its data sit in a public bucket (s3://fisheries-catch-data, Registry of Open
Data on AWS) whose files are not described anywhere public. This script:

  1. lists every file in the bucket and writes the list, with sizes and the
     header of each CSV, to sau/listing.json (so the build can be pointed at
     the right file if step 2 picks wrongly);
  2. takes the CSV whose header carries the year, the fishing country
     (fishing entity), the tonnes (catch_sum) and the reporting and catch
     status, and adds up, for each fishing country and its latest year: all
     tonnes, reported and unreported, landed and discarded, by sector and by
     gear where given, and the landed value;

  sau/countries.json  ISO3 -> {value: tonnes in the latest year, the parts}
  sau/build.json      file used, columns found, names not matched to a country

Weekly (Sundays), or by hand.
"""
import csv, datetime, io, json, os, pathlib, re, urllib.parse, urllib.request, xml.etree.ElementTree as ET

BUCKET = "https://fisheries-catch-data.s3.us-west-2.amazonaws.com/"
OUT = pathlib.Path("sau")
UA = {"User-Agent": "Culprits atlas build (welcometoyourgalaxy@gmail.com)"}
NAMES = {"USA": "USA", "Russian Fed": "RUS", "Korea (South)": "KOR", "Korea (North)": "PRK", "Iran": "IRN", "Viet Nam": "VNM",
         "Taiwan": "TWN", "UK": "GBR", "Tanzania": "TZA", "Venezuela": "VEN", "Syria": "SYR", "Congo (ex-Zaire)": "COD", "Congo, R. of": "COG",
         "Côte d'Ivoire": "CIV", "Micronesia": "FSM", "Bolivia": "BOL", "Brunei Darussalam": "BRN", "Cabo Verde": "CPV", "Turkey": "TUR"}


def get(url, headers=None, timeout=300):
    h = dict(UA, **(headers or {}))
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout).read()


def listing():
    keys, token = [], None
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    while True:
        url = BUCKET + "?list-type=2&max-keys=1000" + (f"&continuation-token={urllib.parse.quote(token)}" if token else "")
        x = ET.fromstring(get(url))
        for c in x.findall(f"{ns}Contents"):
            keys.append({"key": c.find(f"{ns}Key").text, "size": int(c.find(f"{ns}Size").text)})
        nxt = x.find(f"{ns}NextContinuationToken")
        if nxt is None:
            return keys
        token = nxt.text


def header(key):
    raw = get(BUCKET + urllib.parse.quote(key), headers={"Range": "bytes=0-65535"}, timeout=120)
    line = raw.decode("utf-8-sig", "ignore").splitlines()[0]
    return next(csv.reader([line]))


def iso_of(name):
    if name in NAMES:
        return NAMES[name]
    import pycountry
    for k in ("name", "official_name", "common_name"):
        for c in pycountry.countries:
            if getattr(c, k, None) == name:
                return c.alpha_3
    m = re.match(r"^(.*?)\s*\(", name or "")
    return iso_of(m.group(1)) if m and m.group(1) != name else None


def pick(cols, *alts):
    low = {c.lower(): c for c in cols}
    for a in alts:
        if a in low:
            return low[a]
    return None


def main():
    if (OUT / "listing.json").exists() and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("sea_around_us: weekly; not Sunday")
        return
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pycountry"], check=True)
    OUT.mkdir(exist_ok=True)
    keys = listing()
    for k in keys:
        if k["key"].lower().endswith(".csv"):
            try:
                k["columns"] = header(k["key"])
            except Exception as e:  # noqa: BLE001
                k["columns_error"] = f"{type(e).__name__}: {e}"
    (OUT / "listing.json").write_text(json.dumps(keys, indent=1))
    print(f"sea_around_us: {len(keys)} files in the bucket; {sum(1 for k in keys if 'columns' in k)} CSVs read", flush=True)
    want = []
    for k in keys:
        cols = k.get("columns") or []
        ent = pick(cols, "name_fishing_entity", "fishing_entity", "fishing_entity_name")
        if pick(cols, "year") and ent and pick(cols, "catch_sum", "tonnes") and not re.search(r"rfmo", k["key"], re.I):
            score = sum(1 for c in ("reporting_status", "catch_status", "name_reporting_status", "name_catch_type", "catch_type", "sector_type", "name_sector_type", "gear", "name_gear") if pick(cols, c))
            want.append((score, -k["size"], k))
    stamp = {"read": datetime.date.today().isoformat(), "files": len(keys)}
    if not want:
        stamp["built"] = False
        stamp["why"] = "no CSV in the bucket has a year, a fishing country and tonnes outside the RFMO tables; see sau/listing.json"
        (OUT / "build.json").write_text(json.dumps(stamp, indent=1))
        print("sea_around_us: " + stamp["why"], flush=True)
        return
    k = sorted(want, key=lambda w: (-w[0], w[1]))[0][2]
    cols = k["columns"]
    c_year, c_ent = pick(cols, "year"), pick(cols, "name_fishing_entity", "fishing_entity", "fishing_entity_name")
    c_t, c_v = pick(cols, "catch_sum", "tonnes"), pick(cols, "real_value", "landed_value")
    parts = {"reported or not": pick(cols, "reporting_status", "name_reporting_status"), "landed or discarded": pick(cols, "catch_status", "name_catch_type", "catch_type"),
             "sector": pick(cols, "sector_type", "name_sector_type"), "gear": pick(cols, "gear", "name_gear", "gear_type")}
    agg, last = {}, 0
    with urllib.request.urlopen(urllib.request.Request(BUCKET + urllib.parse.quote(k["key"]), headers=UA), timeout=3600) as r:
        for row in csv.DictReader(io.TextIOWrapper(r, encoding="utf-8-sig", errors="replace")):
            try:
                y, t = int(row[c_year]), float(row[c_t] or 0)
            except (TypeError, ValueError):
                continue
            last = max(last, y)
            a = agg.setdefault(row[c_ent], {}).setdefault(y, {"t": 0.0, "v": 0.0, "parts": {}})
            a["t"] += t
            if c_v:
                try:
                    a["v"] += float(row[c_v] or 0)
                except ValueError:
                    pass
            for label, col in parts.items():
                if col:
                    d = a["parts"].setdefault(label, {})
                    d[row[col] or "not given"] = d.get(row[col] or "not given", 0) + t
    out, unmatched = {}, {}
    fmt = lambda d: "; ".join(f"{k}: {v:,.0f} t" for k, v in sorted(d.items(), key=lambda kv: -kv[1]))
    for name, years in agg.items():
        y = max(years)
        a = years[y]
        iso = iso_of(name)
        if not iso:
            unmatched[name] = round(a["t"])
            continue
        e = out.setdefault(iso, {"value": 0, "x_fishing countries as Sea Around Us names them": [], "x_year": y})
        e["value"] += round(a["t"])
        e["x_fishing countries as Sea Around Us names them"].append(name)
        if c_v:
            e["x_landed value (US$)"] = e.get("x_landed value (US$)", 0) + round(a["v"])
        for label, d in a["parts"].items():
            e[f"x_{label}"] = (e.get(f"x_{label}", "") + ("; " if e.get(f"x_{label}") else "") + fmt(d))
    for e in out.values():
        e["x_fishing countries as Sea Around Us names them"] = "; ".join(e["x_fishing countries as Sea Around Us names them"])
    (OUT / "countries.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    stamp.update({"built": True, "file": k["key"], "columns": cols, "latest_year": last, "countries": len(out), "not_matched_to_a_country": unmatched})
    (OUT / "build.json").write_text(json.dumps(stamp, ensure_ascii=False, indent=1))
    print(f"sea_around_us: {k['key']}: {len(out)} countries, latest year {last}", flush=True)


if __name__ == "__main__":
    import urllib.parse  # noqa: F401
    main()
