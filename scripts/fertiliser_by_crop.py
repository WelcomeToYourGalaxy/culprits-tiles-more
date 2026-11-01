#!/usr/bin/env python3
"""
Which crops get the most nitrogen fertiliser, country by country (round 120b,
asked 1 October 2026: "a layer of the crops most responsible worldwide" for
nitrous oxide). Synthetic nitrogen spread on fields is the largest human
source of nitrous oxide (Tian et al. 2020, Nature).

Source: Ludemann, Gruere, Heffer and Dobermann (2022), Global data on fertilizer
use by crop and by country, Scientific Data, with the International Fertilizer
Association's surveys (Dryad, doi:10.5061/dryad.2rbnzs7qh). The latest survey
each country is in, every crop's nitrogen, phosphate and potash as given.

  fertiliser/by_crop.json    ISO3 -> {"top crop": the crop given the most
                             nitrogen, "value": nitrogen on all crops, every
                             crop's figures as x_ fields, the survey year}
  fertiliser/world.json      every crop's nitrogen summed over the countries
  fertiliser/build.json      the file read, its columns, what was not placed

Nitrogen is not nitrous oxide: about one per cent of it escapes as nitrous
oxide (the IPCC's default), more or less with soil and climate. The map
shows the nitrogen, as the source gives it.

Monthly or by hand.

Round 188o: Dryad answered 401 (Unauthorized) to the file's download on
7 October, though it listed the files. A copy downloaded by hand from
https://datadryad.org/dataset/doi:10.5061/dryad.2rbnzs7qh into
fertiliser/download/ (the data CSV, or the whole "Download dataset" zip) is
read first; without one, a refusal is written to fertiliser/build.json, not
a failed run.
"""
import csv, io, json, os, pathlib, re, subprocess, sys, time, urllib.error, urllib.parse, urllib.request, zipfile

OUT = pathlib.Path("fertiliser")
DOI = "doi:10.5061/dryad.2rbnzs7qh"
API = "https://datadryad.org/api/v2"
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)", "Accept": "application/json"}


WHAT_TO_DO = ("download the data CSV (or the whole dataset as a zip) from https://datadryad.org/dataset/doi:10.5061/dryad.2rbnzs7qh "
              "and upload it to fertiliser/download/ in culprits-tiles-more")


def get(url, timeout=600):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def files():
    """The latest version's files, through Dryad's own API: [(name, download address)]."""
    v = json.loads(get(f"{API}/datasets/{urllib.parse.quote(DOI, safe='')}/versions"))
    versions = (v.get("_embedded") or {}).get("stash:versions") or []
    last = versions[-1]
    href = last["_links"]["stash:files"]["href"]
    out, url = [], "https://datadryad.org" + href
    while url:
        page = json.loads(get(url))
        for f in (page.get("_embedded") or {}).get("stash:files") or []:
            dl = (f.get("_links") or {}).get("stash:download", {}).get("href")
            if dl:
                out.append((f.get("path") or f.get("name") or "", "https://datadryad.org" + dl))
        nxt = (page.get("_links") or {}).get("next", {}).get("href")
        url = "https://datadryad.org" + nxt if nxt else None
    return out, last.get("license") or last.get("_links", {}).get("license")


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and time.time() - stamp.stat().st_mtime < 25 * 24 * 3600 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("fertiliser_by_crop: monthly")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pycountry"], check=True)
    import pycountry
    OUT.mkdir(exist_ok=True)
    # A copy downloaded by hand first: the CSVs in fertiliser/download/, or in a zip there.
    local, licence = [], "as on the Dryad page (the copy uploaded by hand)"
    for f in sorted((OUT / "download").glob("*")):
        if f.suffix.lower() == ".csv":
            local.append((f.name, f.read_bytes()))
        elif f.suffix.lower() == ".zip":
            with zipfile.ZipFile(f) as z:
                local += [(n.rsplit("/", 1)[-1], z.read(n)) for n in z.namelist() if n.lower().endswith(".csv")]
    if local:
        listing = local
    else:
        try:
            listing, licence = files()
        except urllib.error.HTTPError as e:
            stamp.write_text(json.dumps({"built": False, "why": f"Dryad refused the file list ({e.code})", "what to do": WHAT_TO_DO}, indent=1))
            print(f"::warning::fertiliser_by_crop: Dryad refused the file list ({e.code}); see fertiliser/build.json")
            return
    data = [f for f in listing if re.search(r"\.csv$", f[0], re.I) and re.search(r"data", f[0], re.I)] or [f for f in listing if f[0].lower().endswith(".csv")]
    if not data:
        stamp.write_text(json.dumps({"files": listing, "found": False}, indent=1))
        sys.exit("fertiliser_by_crop: no CSV data file in the dataset; its files are in fertiliser/build.json")
    name, url = sorted(data, key=lambda f: (0 if "1_to" in f[0] else 1, f[0]))[0]
    if isinstance(url, bytes):
        raw, url = url, f"fertiliser/download (uploaded by hand): {name}"
    else:
        try:
            raw = get(url)
        except urllib.error.HTTPError as e:
            stamp.write_text(json.dumps({"built": False, "file": name, "address": url, "why": f"Dryad refused the download ({e.code})",
                                         "what to do": WHAT_TO_DO}, indent=1))
            print(f"::warning::fertiliser_by_crop: Dryad refused the download of {name} ({e.code}); see fertiliser/build.json")
            return
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig", "replace"))))
    head = list(rows[0].keys()) if rows else []
    col = lambda *pats: next((h for h in head for p in pats if re.search(p, h, re.I)), None)
    c_iso, c_country, c_crop = col(r"iso"), col(r"^country"), col(r"^crop")
    c_n = col(r"^n\b|^n_|nitrogen|\bN_k_t\b")
    c_year = col(r"year"), col(r"fubc|report|survey|round")
    c_p, c_k = col(r"p2o5|phosph"), col(r"k2o|potash|potassium")
    if not (c_crop and c_n and (c_iso or c_country)):
        stamp.write_text(json.dumps({"file": url, "columns": head, "found": False}, indent=1))
        sys.exit("fertiliser_by_crop: the columns were not recognised; they are in fertiliser/build.json")

    def iso_of(r):
        v = (r.get(c_iso) or "").strip().upper() if c_iso else ""
        if re.fullmatch(r"[A-Z]{3}", v):
            return v
        try:
            return pycountry.countries.lookup((r.get(c_country) or "").strip()).alpha_3
        except LookupError:
            try:
                return pycountry.countries.search_fuzzy((r.get(c_country) or "").strip())[0].alpha_3
            except LookupError:
                return None

    def when(r):
        for c in c_year:
            m = re.findall(r"(?:19|20)\d\d", str(r.get(c) or "")) if c else []
            if m:
                return max(int(x) for x in m)
        return 0

    num = lambda v: (lambda s: float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None)(str(v or "").replace(",", "").strip())
    latest, unplaced = {}, set()
    for r in rows:
        iso = iso_of(r)
        if not iso:
            unplaced.add(r.get(c_country) or r.get(c_iso))
            continue
        latest[iso] = max(latest.get(iso, 0), when(r))
    out, world = {}, {}
    for r in rows:
        iso = iso_of(r)
        if not iso or when(r) != latest.get(iso):
            continue
        crop = (r.get(c_crop) or "").strip()
        n = num(r.get(c_n))
        if not crop or n is None:
            continue
        rec = out.setdefault(iso, {"country": r.get(c_country) or iso, "survey year": latest[iso], "value": 0.0, "_crops": {}})
        if re.search(r"^(total|all crops|sum)", crop, re.I):
            continue
        rec["_crops"][crop] = rec["_crops"].get(crop, 0) + n
        rec[f"x_{crop}: nitrogen ({c_n})"] = n
        if c_p and num(r.get(c_p)) is not None:
            rec[f"x_{crop}: phosphate ({c_p})"] = num(r.get(c_p))
        if c_k and num(r.get(c_k)) is not None:
            rec[f"x_{crop}: potash ({c_k})"] = num(r.get(c_k))
        world[crop] = world.get(crop, 0) + n
    for iso, rec in out.items():
        crops = rec.pop("_crops")
        rec["value"] = round(sum(crops.values()), 3)
        top = max(crops.items(), key=lambda kv: kv[1]) if crops else None
        rec["top crop"] = top[0] if top else "not given"
        rec["share of the nitrogen on the top crop"] = f"{100 * top[1] / rec['value']:.0f}%" if top and rec["value"] else ""
    (OUT / "by_crop.json").write_text(json.dumps(out, ensure_ascii=False, indent=0))
    (OUT / "world.json").write_text(json.dumps(dict(sorted(world.items(), key=lambda kv: -kv[1])), ensure_ascii=False, indent=1))
    stamp.write_text(json.dumps({"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "file": name, "address": url, "licence": licence,
                                 "columns": head, "used": {"crop": c_crop, "nitrogen": c_n, "iso": c_iso, "country": c_country},
                                 "countries": len(out), "not placed": sorted(x for x in unplaced if x)}, indent=1, ensure_ascii=False))
    print(f"fertiliser_by_crop: {len(out)} countries from {name}")


if __name__ == "__main__":
    main()
