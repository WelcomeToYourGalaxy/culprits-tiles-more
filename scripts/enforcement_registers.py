#!/usr/bin/env python3
"""
Round 127b (2 October): national environmental-crime registers, mapped from
what each register really holds (probe/enforcement/, read by round 84b's
env_enforcement.py). Three publish whole tables that can be placed:

  England, Environment Agency enforcement actions (Open Government Licence
  v3.0): every action in the public register, placed at the postcode at the
  end of its address (postcodes.io, Open Government Licence). Actions with no
  postcode, or one no longer in use and not found, are counted, not guessed.
    tiles/ea_enforcement.pmtiles + enforcement/ea_enforcement/<hh>.json.gz

  Canada, Environmental Offenders Registry (Environment and Climate Change
  Canada): every conviction in the registry's own export, placed at the town
  of the offence (or, if none is given, the offender's town) by
  OpenStreetMap's Nominatim; the box says which.
    tiles/canada_offenders.pmtiles + enforcement/canada_offenders/<hh>.json.gz

  United States, EPA enforcement cases (ECHO case downloads, US government
  work, public domain): every civil and criminal case, one point for each
  facility the case names, at the centre of the facility's ZIP code (Census
  Bureau gazetteer: ECHO's case files give addresses, not coordinates); the
  box says so. Every field of the case, plus its violations, laws, pollutants
  and defendants, in its box.
    tiles/epa_cases.pmtiles + enforcement/epa_cases/<hh>.json.gz

Counts, what was not placed and why: enforcement/registers.json.
Weekly (or ENFORCEMENT_REBUILD=1); a register never built is tried daily.
"""
import csv, datetime, io, json, os, pathlib, re, sys, time, urllib.parse, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import env_enforcement as ee  # noqa: E402  get(), write_layer(), table()

csv.field_size_limit(1 << 30)
OUT = pathlib.Path("enforcement")
TILES = pathlib.Path("tiles")
STAMP = OUT / "registers.json"
NOMI = {"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy; welcometoyourgalaxy@gmail.com)"}
WEEK = 7 * 24 * 3600
POSTCODE = re.compile(r"\b([A-Z]{1,2}[0-9][A-Z0-9]?) ?([0-9][A-Z]{2})\b")


def post_json(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=dict(NOMI, **{"Content-Type": "application/json"}))
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


# ---------- England ----------
def ea_enforcement(st):
    raw = ee.get("https://environment.data.gov.uk/public-register/downloads/enforcement-action")
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
    rows = list(csv.DictReader(io.StringIO(z.read(name).decode("utf-8-sig", "replace"))))
    print(f"  EA enforcement: {len(rows):,} rows, columns {list(rows[0]) if rows else []}", flush=True)
    codes = {}
    for r in rows:
        m = POSTCODE.findall(str(r.get("Address") or "").upper())
        if m:
            codes[f"{m[-1][0]} {m[-1][1]}"] = None
    todo = list(codes)
    for i in range(0, len(todo), 100):
        try:
            got = post_json("https://api.postcodes.io/postcodes", {"postcodes": todo[i:i + 100]})
        except Exception as e:  # noqa: BLE001
            print(f"    postcodes.io: {e}", flush=True)
            time.sleep(5)
            continue
        for g in got.get("result") or []:
            res = g.get("result")
            if res and res.get("longitude") is not None:
                codes[g["query"]] = (res["longitude"], res["latitude"])
        time.sleep(0.2)
    old = [c for c, v in codes.items() if v is None]
    for c in old:      # postcodes no longer in use keep their last position
        try:
            with urllib.request.urlopen(urllib.request.Request("https://api.postcodes.io/terminated_postcodes/" + urllib.parse.quote(c), headers=NOMI), timeout=60) as r:
                res = json.loads(r.read()).get("result") or {}
            if res.get("longitude") is not None:
                codes[c] = (res["longitude"], res["latitude"])
        except Exception:  # noqa: BLE001
            pass
    feats, pieces, no_code, not_found = [], {}, 0, 0
    for i, r in enumerate(rows):
        key = str(r.get("Action Number") or f"row{i}")
        m = POSTCODE.findall(str(r.get("Address") or "").upper())
        if not m:
            no_code += 1
            continue
        pc = f"{m[-1][0]} {m[-1][1]}"
        at = codes.get(pc)
        if not at:
            not_found += 1
            continue
        kind = (r.get("Action Type") or "").strip() or "not given"
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 6), round(at[1], 6)]},
                      "properties": {"id": key, "x_date": str(r.get("Action Date") or "")[:10], "x_kind": kind[:60]}})
        pieces[key] = dict({k: v for k, v in r.items() if v not in (None, "")}, title=str(r.get("Offender") or "Environment Agency action " + key),
                           **{"placed at": f"the centre of postcode {pc} (postcodes.io), from the address the Environment Agency gives"})
    ee.write_layer("ea_enforcement", feats, pieces)
    st["ea_enforcement"] = {"rows": len(rows), "placed": len(feats), "no_postcode_in_address": no_code, "postcode_not_found": not_found,
                            "licence": "Open Government Licence v3.0 (the download's own licence file)"}


# ---------- Canada ----------
def nominatim(q, cache):
    if q in cache:
        return cache[q]
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1, "countrycodes": "ca"})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=NOMI), timeout=60) as r:
            j = json.loads(r.read())
        cache[q] = (float(j[0]["lon"]), float(j[0]["lat"])) if j else None
    except Exception as e:  # noqa: BLE001
        print(f"    Nominatim {q}: {e}", flush=True)
        return None            # not cached: tried again next run
    time.sleep(1.2)
    return cache[q]


def canada_offenders(st):
    import openpyxl  # noqa: E402
    raw = ee.get("https://environmental-protection.canada.ca/offenders-registry/Home/Export")
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    head = [str(h or "").strip() for h in next(it)]
    rows = [dict(zip(head, ["" if v is None else str(v).strip() for v in row])) for row in it if any(v not in (None, "") for v in row)]
    print(f"  Canada offenders: {len(rows):,} rows, columns {head}", flush=True)
    cache_f = OUT / "canada_places.json"
    try:
        cache = {k: tuple(v) if v else None for k, v in json.loads(cache_f.read_text()).items()}
    except Exception:  # noqa: BLE001
        cache = {}
    bad = re.compile(r"^(not available|non disponible|n/?a|)$", re.I)
    feats, pieces, unplaced = [], {}, []
    for i, r in enumerate(rows):
        key = f"ca{i + 1}"
        at, how = None, ""
        for city_k, prov_k, what in (("Offense city", "Offense province/territory", "the town of the offence"),
                                     ("City", "Province/territory", "the offender's town (the registry gives no town for the offence)")):
            city, prov = r.get(city_k, ""), r.get(prov_k, "") or r.get("Province/territory", "")
            if bad.match(city or ""):
                continue
            at = nominatim(f"{city}, {prov}, Canada" if prov and not bad.match(prov) else f"{city}, Canada", cache)
            if at:
                how = f"{what}: {city}{', ' + prov if prov and not bad.match(prov) else ''} (OpenStreetMap's Nominatim)"
                break
        if not at:
            unplaced.append(r.get("Corporation name") or key)
            continue
        laws = r.get("Legislative details", "")
        act = laws.split("/")[0].strip() if laws else "not given"
        date = r.get("Date of conviction", "") or r.get("Date of sentencing", "")
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 5), round(at[1], 5)]},
                      "properties": {"id": key, "x_date": date[:10], "x_kind": act[:60]}})
        pieces[key] = dict({k: v for k, v in r.items() if v}, title=r.get("Corporation name") or "Conviction " + key, **{"placed at": how})
    OUT.mkdir(exist_ok=True)
    cache_f.write_text(json.dumps(cache, ensure_ascii=False))
    ee.write_layer("canada_offenders", feats, pieces)
    st["canada_offenders"] = {"rows": len(rows), "placed": len(feats), "not_placed": unplaced,
                              "licence": "canada.ca terms of use (non-commercial reproduction allowed with credit); check if in doubt"}


# ---------- United States ----------
def zip_centres():
    for y in (2024, 2023, 2022):
        u = f"https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{y}_Gazetteer/{y}_Gaz_zcta_national.zip"
        try:
            z = zipfile.ZipFile(io.BytesIO(ee.get(u, 300)))
        except Exception as e:  # noqa: BLE001
            print(f"    {u}: {e}", flush=True)
            continue
        text = z.read(z.namelist()[0]).decode("utf-8", "replace")
        out = {}
        rd = csv.reader(io.StringIO(text), delimiter="\t")
        head = [h.strip() for h in next(rd)]
        gi, la, lo = head.index("GEOID"), head.index("INTPTLAT"), head.index("INTPTLONG")
        for row in rd:
            try:
                out[row[gi].strip()] = (float(row[lo].strip()), float(row[la].strip()))
            except (ValueError, IndexError):
                pass
        print(f"    ZIP centres: {len(out):,} from {u}", flush=True)
        return out, u
    raise RuntimeError("no Census ZIP gazetteer answered")


def epa_cases(st):
    zips, zsrc = zip_centres()
    z = zipfile.ZipFile(io.BytesIO(ee.get("https://echo.epa.gov/files/echodownloads/case_downloads.zip", 1800)))
    names = {pathlib.Path(n).name.upper(): n for n in z.namelist()}

    def rows(fname):
        n = names.get(fname)
        if not n:
            print(f"    {fname}: not in the zip", flush=True)
            return
        with z.open(n) as fh:
            yield from csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace"))

    clean = lambda d: {k: (v or "").strip() for k, v in d.items() if (v or "").strip()}  # noqa: E731
    cases = {r["ACTIVITY_ID"]: clean(r) for r in rows("CASE_ENFORCEMENTS.CSV")}
    print(f"  EPA cases: {len(cases):,}", flush=True)
    joins = (("CASE_VIOLATIONS.CSV", "VIOLATION_TYPE_DESC", "Violations"), ("CASE_LAW_SECTIONS.CSV", "LAW_SECTION_DESC", "Laws"),
             ("CASE_POLLUTANTS.CSV", "POLLUTANT_DESC", "Pollutants"), ("CASE_DEFENDANTS.CSV", "DEFENDANT_NAME", "Defendants"),
             ("CASE_PROGRAMS.CSV", "PROGRAM_DESC", "Programs"), ("CASE_ENFORCEMENT_TYPE.CSV", "ENF_TYPE_DESC", "Enforcement types"),
             ("CASE_RELIEF_SOUGHT.CSV", "RELIEF_DESC", "Relief sought"))
    for fname, col, label in joins:
        for r in rows(fname):
            c = cases.get(r.get("ACTIVITY_ID"))
            v = (r.get(col) or "").strip()
            if c is not None and v:
                have = c.setdefault(label, [])
                if v not in have:
                    have.append(v)
    facs = {}
    for r in rows("CASE_FACILITIES.CSV"):
        facs.setdefault(r.get("ACTIVITY_ID"), []).append(clean(r))
    feats, pieces, no_fac, no_zip = [], {}, 0, 0
    for aid, c in cases.items():
        for label, *_ in [(j[2],) for j in joins]:
            if isinstance(c.get(label), list):
                c[label] = "; ".join(c[label])
        fl = facs.get(aid) or []
        if not fl:
            no_fac += 1
            continue
        c["Facilities"] = "; ".join(" ".join(x for x in (f.get("FACILITY_NAME", ""), f.get("LOCATION_ADDRESS", ""), f.get("CITY", ""), f.get("STATE_CODE", ""), f.get("ZIP", "")) if x) for f in fl)
        placed = 0
        for f in fl:
            at = zips.get((f.get("ZIP") or "")[:5])
            if not at:
                continue
            placed += 1
            pen = c.get("TOTAL_PENALTY_ASSESSED_AMT", "")
            try:
                pen = float(pen)
            except ValueError:
                pen = None
            d = c.get("ACTIVITY_STATUS_DATE", "")
            m = re.match(r"(\d\d)/(\d\d)/(\d{4})", d)
            p = {"id": aid, "x_date": f"{m[3]}-{m[1]}-{m[2]}" if m else (d or c.get("FISCAL_YEAR", "")), "x_kind": c.get("ACTIVITY_TYPE_DESC", "not given")[:60]}
            if pen is not None:
                p["x_penalty"] = pen
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 5), round(at[1], 5)]}, "properties": p})
        if not placed:
            no_zip += 1
            continue
        pieces[aid] = dict(c, title=c.get("CASE_NAME") or c.get("ACTIVITY_NAME") or "EPA case " + aid,
                           **{"placed at": "the centre of each named facility's ZIP code (US Census Bureau gazetteer); ECHO's case files give addresses, not coordinates"})
    ee.write_layer("epa_cases", feats, pieces)
    st["epa_cases"] = {"cases": len(cases), "points": len(feats), "cases_placed": len(pieces), "no_facility_named": no_fac,
                       "no_zip_found": no_zip, "zip_centres": zsrc, "licence": "US government work (public domain)"}


def main():
    OUT.mkdir(exist_ok=True)
    try:
        st = json.loads(STAMP.read_text())
    except Exception:  # noqa: BLE001
        st = {}
    names = (("ea_enforcement", ea_enforcement), ("canada_offenders", canada_offenders), ("epa_cases", epa_cases))
    unbuilt = [n for n, _ in names if not (TILES / f"{n}.pmtiles").exists()]
    due = time.time() - st.get("at", 0) >= WEEK or os.environ.get("ENFORCEMENT_REBUILD") or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if not due and not unbuilt:
        print("enforcement_registers: copied less than a week ago")
        return
    st.pop("errors", None)
    failed = False
    for name, fn in names:
        if not due and name not in unbuilt:
            continue
        print(f"enforcement_registers: {name}", flush=True)
        try:
            fn(st)
        except Exception as e:  # noqa: BLE001
            failed = True
            print(f"::warning::{name}: {e}; the last copy stays", flush=True)
            st.setdefault("errors", {})[name] = str(e)[:300]
    st["at"] = time.time() if not failed or not unbuilt else st.get("at", 0)
    st["when"] = datetime.date.today().isoformat()
    STAMP.write_text(json.dumps(st, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
