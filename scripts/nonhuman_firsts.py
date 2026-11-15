#!/usr/bin/env python3
"""
When alien species were first recorded in each place, for the Invasion of
non-humans map.

Source: the Alien Species First Records Database (Seebens, H. et al. 2017,
"No saturation in the accumulation of alien species worldwide", Nature
Communications 8: 14435, and its later versions), from Zenodo. The newest
version of the first record found below that holds a readable table is used;
which one, and the table's columns, are written to the build file.

Every record is kept. Each place the database names is matched to a country
shape by its exact name only; places with no shape (islands, states and
other parts of countries) are kept and listed as unplaced, never folded in.

  nonhuman/first_records.json                counts per place per year
  nonhuman/first_records/<place>.json        every taxon with its year
  nonhuman/first_records.build.json

Checked weekly for a new version; FIRSTS_REBUILD=1 or a run by hand builds.
"""
import collections, math, pathlib, re, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "first_records"
# Newest record first: the 2026 "FirstRecords" dataset, then the database's
# own concept record (its latest version).
RECORDS = ["18759840", "4632335"]


def pick_columns(cols):
    # Digits kept, so FirstRecord and FirstRecord1 stay apart.
    low = {c: re.sub(r"[^a-z0-9]", "", str(c).lower()) for c in cols}
    def find(*pats, avoid=()):
        for p in pats:
            for c, l in low.items():
                if re.fullmatch(p, l) and not any(re.fullmatch(a, l) for a in avoid):
                    return c
        for p in pats:
            for c, l in low.items():
                if re.search(p, l) and not any(re.search(a, l) for a in avoid):
                    return c
        return None
    return {
        # The country first: in the 2026 table Region is free text (seas,
        # states, towns), Country the country (round nh4).
        "place": find(r"country", r"region", r"location", r"locality", avoid=(r"code", r"iso")),
        "where": find(r"region", r"location", r"locality", avoid=(r"code", r"iso")),
        "island": find(r"island"),
        "taxon": find(r"genusspecies", r"scientificname", r"taxonname", r"taxon", r"species", avoid=(r"group", r"rank", r"id$", r"type")),
        "year": find(r"firstrecord", r"firstrecordyear", r"firstrecord1", r"year", avoid=(r"source", r"ref")),
        # Used where the year column is blank (the 2026 table gives a range,
        # FirstRecord1 to FirstRecord2, beside its FirstRecord).
        "year_else": find(r"firstrecord1"),
        "life": find(r"lifeform", r"taxonomicgroup", r"group"),
    }


def read_table(path):
    import pandas as pd
    s = str(path).lower()
    if s.endswith((".xlsx", ".xls")):
        book = pd.read_excel(path, sheet_name=None, dtype=str)
        best = max(book.items(), key=lambda kv: len(kv[1]))
        return best[1], f"sheet {best[0]}"
    for enc in ("utf-8", "latin-1"):
        for sep in (",", ";", "\t"):
            try:
                df = pd.read_csv(path, dtype=str, sep=sep, encoding=enc)
                if df.shape[1] > 3:
                    return df, f"csv sep {sep!r} {enc}"
            except Exception:
                pass
    raise RuntimeError("could not read the table")


def main():
    if not nh.due(NAME, 7, "FIRSTS_REBUILD"):
        return
    nh.pip("pandas", "openpyxl", "xlrd")
    work = pathlib.Path(tempfile.mkdtemp())
    tried, chosen, df, cols, how, version = [], None, None, None, None, None
    for rec in RECORDS:
        try:
            j = nh.get_json(f"https://zenodo.org/api/records/{rec}/versions/latest")
        except Exception as e:
            tried.append({"record": rec, "error": str(e)[:200]})
            continue
        files = j.get("files") or []
        names = [f.get("key") for f in files]
        tried.append({"record": rec, "resolved": j.get("id"), "version": (j.get("metadata") or {}).get("version"), "files": names})
        tables = [f for f in files if re.search(r"\.(xlsx|xls|csv|txt|zip)$", f.get("key", ""), re.I)]
        tables.sort(key=lambda f: (not re.search(r"first.?record", f["key"], re.I), -int(f.get("size") or 0)))
        for f in tables:
            try:
                p = nh.download(f["links"]["self"], work / f["key"], f["key"])
                if p.suffix.lower() == ".zip":
                    import zipfile
                    z = zipfile.ZipFile(p)
                    inner = [n for n in z.namelist() if re.search(r"\.(xlsx|xls|csv|txt)$", n, re.I)]
                    inner.sort(key=lambda n: (not re.search(r"first.?record", n, re.I), -z.getinfo(n).file_size))
                    if not inner:
                        raise RuntimeError("no table inside the zip")
                    z.extract(inner[0], work / "unzipped")
                    p = work / "unzipped" / inner[0]
                d, h = read_table(p)
                c = pick_columns(d.columns)
                if c["place"] and c["taxon"] and c["year"]:
                    chosen, df, cols, how, version = f"{rec}:{f['key']}", d, c, h, (j.get("metadata") or {}).get("version")
                    break
                tried.append({"file": f["key"], "columns": list(map(str, d.columns))[:40], "error": "no place, taxon and year columns found"})
            except Exception as e:
                tried.append({"file": f.get("key"), "error": str(e)[:200]})
        if chosen:
            break
    if not chosen:
        nh.write_stamp(NAME, {"failed": True, "tried": tried})
        raise SystemExit("first records: no readable table")
    print(f"first records: {chosen} ({how}); columns {cols}", flush=True)
    C = nh.Countries()
    places = collections.defaultdict(lambda: {"byYear": collections.Counter(), "records": [], "noYear": 0})
    for _, r in df.iterrows():
        place = str(r[cols["place"]]).strip() if r[cols["place"]] == r[cols["place"]] else ""
        if not place or place.lower() == "nan":
            continue
        taxon = str(r[cols["taxon"]]).strip()
        life = str(r[cols["life"]]).strip() if cols["life"] and r[cols["life"]] == r[cols["life"]] else ""
        yv = str(r[cols["year"]]).strip() if r[cols["year"]] == r[cols["year"]] else ""
        if (not yv or yv.lower() == "nan") and cols.get("year_else") and cols["year_else"] != cols["year"] and r[cols["year_else"]] == r[cols["year_else"]]:
            yv = str(r[cols["year_else"]]).strip()
        m = re.match(r"^-?\d{1,4}(\.0+)?$", yv)
        y = int(float(yv)) if m else None
        e = places[place]
        if y is None:
            e["noYear"] += 1
        else:
            e["byYear"][y] += 1
        # Where in the country, as the table words it (region, island).
        bits = []
        for k in ("where", "island"):
            c = cols.get(k)
            if c and c != cols["place"] and r[c] == r[c] and str(r[c]).strip() and str(r[c]).strip().lower() not in ("nan", "no", "0"):
                bits.append(str(r[c]).strip())
        rec = [taxon, y, life if life and life.lower() != "nan" else ""]
        if bits:
            rec.append(", ".join(dict.fromkeys(bits)))
        while len(rec) > 2 and not rec[-1]:
            rec.pop()
        e["records"].append(rec)
    regions, years, used_iso = [], [], set()
    for name in sorted(places):
        e = places[name]
        iso = C.by_name(name)
        if iso in used_iso:
            iso = None
        if iso:
            used_iso.add(iso)
        rel = f"first_records/{nh.slug(name)}.json"
        recs = sorted(e["records"], key=lambda x: (x[1] is None, x[1] if x[1] is not None else 0, x[0]))
        nh.write_json(rel, {"name": name, "records": recs})
        ys = sorted(e["byYear"])
        years += ys
        regions.append({"name": name, "iso3": iso, "total": sum(e["byYear"].values()), "noYear": e["noYear"],
                        "first": ys[0] if ys else None, "last": ys[-1] if ys else None,
                        "byYear": {str(k): v for k, v in sorted(e["byYear"].items())}, "file": rel})
    nh.write_json("first_records.json", {"source": f"Alien Species First Records Database (Seebens et al.), Zenodo {chosen}", "version": version,
                                         "from": min(years) if years else 1500, "to": max(years) if years else 2020, "regions": regions,
                                         "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")})
    nh.write_stamp(NAME, {"chosen": chosen, "read as": how, "columns used": cols, "all columns": list(map(str, df.columns)), "rows": int(len(df)),
                          "places": len(regions), "matched to a country": sum(1 for r in regions if r["iso3"]),
                          "unplaced": [r["name"] for r in regions if not r["iso3"]], "tried": tried})


if __name__ == "__main__":
    main()
