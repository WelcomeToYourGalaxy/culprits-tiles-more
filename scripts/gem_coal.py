#!/usr/bin/env python3
"""
Global Coal Mine Tracker, with its ownership chains and mine boundaries
(round 145b, 3 October: Global Energy Monitor's Dorothy Mei said the two
supplemental files come with the tracker download, by ticking their boxes on
the download form; the tracker is under GEM's Creative Commons licence, CC BY
4.0, credit "Global Energy Monitor, Global Coal Mine Tracker, <release>").

The owner downloads the tracker from globalenergymonitor.org (both
supplemental boxes ticked) and uploads what comes (zips or spreadsheets, as
they are) into culprits-tiles-more gem/coal/download/. This script then:

  1. reads every spreadsheet (inside zips too); the mines sheet is the one
     with latitude and longitude columns and the most rows. Every column of
     every mine goes in its box, unchanged.
  2. joins every row of the other sheets and files that carry the mines' own
     ID column (the ownership chains, and any others) to its mine, every
     column kept, as "<sheet> 1: <column>" fields in that mine's box.
  3. writes methane/gem_coal_mines.geojson, one point per mine (open and
     closed mines alike, round 176b). The column
     holding the mine's methane estimate is found by its name (it says
     methane, or CMM) and copied as methane_for_colour for the map's colours;
     which column it was is in methane/gem_coal_build.json.
  4. turns any boundary file (GeoPackage, shapefile, GeoJSON, KML, file
     geodatabase) into tiles/gem_coal_boundaries.pmtiles, layer "boundaries",
     every field kept.

Runs when the download folder changes (by hand otherwise). Nothing is guessed:
a sheet whose ID column is not found is listed as not joined.
"""
import datetime, glob, hashlib, io, json, os, pathlib, re, shutil, subprocess, sys, tempfile, zipfile

SRC = pathlib.Path("gem/coal/download")
OUT_DIR = pathlib.Path("methane")
MINES = OUT_DIR / "gem_coal_mines.geojson"
STAMP = OUT_DIR / "gem_coal_build.json"
BOUNDS = pathlib.Path("tiles") / "gem_coal_boundaries.pmtiles"
GEO_EXT = (".gpkg", ".shp", ".geojson", ".json", ".kml", ".kmz", ".gdb")


def sh(*a, **k):
    print("+", " ".join(map(str, a)), flush=True)
    subprocess.run(a, check=True, **k)


def need():
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        sh(sys.executable, "-m", "pip", "install", "-q", "openpyxl")


def tools():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import mines
    mines.tools()


def unpack(work):
    """Every file in the download folder, zips opened (and zips in zips)."""
    files = []
    for p in sorted(SRC.rglob("*")):
        if p.is_file() and p.name.lower() != "readme.md":
            files.append(p)
    out, i = [], 0
    while files:
        p = files.pop(0)
        if p.suffix.lower() == ".zip":
            d = work / f"z{i}"
            i += 1
            zipfile.ZipFile(p).extractall(d)
            files += [q for q in sorted(d.rglob("*")) if q.is_file()]
        else:
            out.append(p)
    return out


def sheets(path):
    import openpyxl
    if path.suffix.lower() == ".csv":
        import csv
        rows = list(csv.reader(open(path, encoding="utf-8-sig", errors="replace")))
        yield path.stem, rows
        return
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    for ws in wb.worksheets:
        yield f"{path.stem} / {ws.title}", [list(r) for r in ws.iter_rows(values_only=True)]


def header(rows):
    """The first row that looks like a header (several text cells), and the rows after it."""
    for i, r in enumerate(rows[:15]):
        cells = [c for c in r if isinstance(c, str) and c.strip()]
        if len(cells) >= 3 and len(cells) >= 0.6 * len([c for c in r if c not in (None, "")]):
            return [str(c).strip() if c is not None else f"column {j + 1}" for j, c in enumerate(r)], rows[i + 1:]
    return None, rows


def col(names, *pats):
    for pat in pats:
        for n in names:
            if re.search(pat, n, re.I):
                return n
    return None


def num(v):
    try:
        f = float(str(v).replace(",", ""))
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def clean(v):
    if v is None:
        return None
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()[:10]
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v

PARENTS = OUT_DIR / "gem_coal_parents.geojson"
# GEM's names for countries that pycountry spells otherwise (exact names only).
GEM_COUNTRY = {"Russia": "RUS", "Virgin Islands (British)": "VGB"}
PARENTS_ALL = OUT_DIR / "gem_coal_parents.json"


def rank_parents(tables, by_id):
    """Round 176b: the parent companies at the top of each mine's ownership
    chain (GEM's Global Energy Ownership Tracker, Coal Mine Ownership sheet),
    ranked by the methane of the mines they own, each mine's methane taken in
    proportion to the parent's share. Nothing is filled in:
      - a parent reached by several chains to one mine (GEM lists one row per
        chain and per unit) is counted once for that mine, at the largest
        share any of its chains gives; shares are not added up across chains,
        which would count the same holding twice;
      - where GEM gives the share as "unknown", that mine's methane is not
        divided: it is shown apart, as methane at mines of unknown share;
      - two measures are kept apart: GEM's own estimate (million tonnes of
        methane a year, open mines) and the methane mines reported
        (thousand tonnes)."""
    own = next(((n, h, b) for n, h, b in tables if col(h, r"^parent$") and col(h, r"^share$") and col(h, r"^ownership path$")
                and col(h, r"^gem mine id$")), None)
    if not own:
        return {"built": False, "why": "no ownership sheet with Parent, Share, Ownership Path and GEM Mine ID columns"}
    n, h, b = own
    ix = {x: i for i, x in enumerate(h)}
    g = lambda r, c: r[ix[c]] if c in ix and ix[c] < len(r) else None  # noqa: E731
    pid, pname = col(h, r"^parent gem entity id$"), col(h, r"^parent$")
    hqc, regc = col(h, r"^parent headquarters country$"), col(h, r"^parent registration country$")
    share_c, path_c, mine_c = col(h, r"^share$"), col(h, r"^ownership path$"), col(h, r"^gem mine id$")
    est_c = rep_c = None
    for fs in by_id.values():
        for f in fs:
            est_c = est_c or col(list(f["properties"]), r"gem coal mine methane emissions estimate \(m tonnes")
            rep_c = rep_c or col(list(f["properties"]), r"reported coal mine methane emissions \(thousand tonnes ch4\)")
    holds = {}
    for r in b:
        p, mine = g(r, pid) or g(r, pname), g(r, mine_c)
        if not p or not mine:
            continue
        k = (str(p).strip(), str(mine).strip())
        e = holds.setdefault(k, {"name": g(r, pname), "hq": g(r, hqc) or g(r, regc), "shares": [], "paths": set()})
        s = num(g(r, share_c))
        if s is not None:
            e["shares"].append(s)
        if g(r, path_c):
            e["paths"].add(str(g(r, path_c)))
    parents = {}
    for (p, mine), e in holds.items():
        fs = by_id.get(mine, [])
        props = fs[0]["properties"] if fs else {}
        est = num(props.get(est_c)) if est_c else None
        rep = num(props.get(rep_c)) if rep_c else None
        share = max(e["shares"]) if e["shares"] else None
        q = parents.setdefault(p, {"name": e["name"], "hq": e["hq"], "mines": 0, "est": 0.0, "est_unknown": 0.0, "rep": 0.0, "rep_unknown": 0.0,
                                   "lines": [], "not_in_tracker": 0})
        q["mines"] += 1
        if not fs:
            q["not_in_tracker"] += 1
        mname = props.get("Mine Name") or mine
        ctry = props.get("Country / Area") or ""
        if share is None:
            q["est_unknown"] += est or 0
            q["rep_unknown"] += rep or 0
            q["lines"].append((est or 0, f"{mname} ({ctry}): share unknown; GEM estimate {est if est is not None else 'none'} Mt a year"))
        else:
            q["est"] += (est or 0) * share / 100
            q["rep"] += (rep or 0) * share / 100
            q["lines"].append(((est or 0) * share / 100, f"{mname} ({ctry}): {share:g}% of GEM estimate {est if est is not None else 'none'} Mt a year"))
    order = sorted(parents, key=lambda p: (-parents[p]["est"], -parents[p]["est_unknown"]))
    try:
        import pycountry
    except ImportError:
        sh(sys.executable, "-m", "pip", "install", "-q", "pycountry")
        import pycountry
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from forest500_map import capitals
    caps = capitals()
    feats, unplaced, spin, table = [], [], {}, []
    for rank, p in enumerate(order, 1):
        q = parents[p]
        q["lines"].sort(key=lambda t: -t[0])
        row = {"rank by GEM estimate, own share": rank, "parent company": q["name"], "GEM entity ID": p, "headquarters country": q["hq"],
               "mines held": q["mines"],
               "methane, GEM estimate, by its shares (million tonnes a year)": round(q["est"], 5),
               "methane, GEM estimate, at mines of unknown share, not divided (million tonnes a year)": round(q["est_unknown"], 5),
               "methane reported by the mines, by its shares (thousand tonnes)": round(q["rep"], 3),
               "methane reported at mines of unknown share, not divided (thousand tonnes)": round(q["rep_unknown"], 3),
               "mines and shares": "; ".join(t for _, t in q["lines"])}
        if q["not_in_tracker"]:
            row["mines not found in the tracker's sheets"] = q["not_in_tracker"]
        table.append(row)
        hq = str(q["hq"] or "").strip()
        code = GEM_COUNTRY.get(hq)
        if not code and hq:
            try:
                code = pycountry.countries.lookup(hq).alpha_3
            except LookupError:
                code = None
        cap = caps.get(code) if code else None
        if not cap:
            unplaced.append({"parent": q["name"], "headquarters": q["hq"]})
            continue
        i = spin[code] = spin.get(code, -1) + 1
        import math
        ang, rad = math.radians(137.508 * i), 0.12 * math.sqrt(i)
        lon = cap[0] + rad * math.cos(ang) / max(0.3, math.cos(math.radians(cap[1])))
        lat = max(-85, min(85, cap[1] + rad * math.sin(ang)))
        props = dict(row, **{"placed at": (f"the capital of its headquarters country ({cap[2]})" if cap[3] == "capital" else
                                          f"{cap[2]}, the most populous place Natural Earth lists in its headquarters country") +
                                         "; GEM gives the country, not the address. Spread so each can be clicked.",
                             "source": "Global Energy Monitor, Global Coal Mine Tracker (August 2026) and Global Energy Ownership Tracker (September 2026), CC BY 4.0"})
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}, "properties": props})
    PARENTS.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, default=str))
    PARENTS_ALL.write_text(json.dumps(table, ensure_ascii=False, indent=0, default=str))
    return {"built": True, "sheet": n, "methane_estimate_column": est_c, "methane_reported_column": rep_c, "parents": len(parents),
            "placed": len(feats), "not_placed": unplaced, "holdings": len(holds),
            "holdings_with_unknown_share": sum(1 for e in holds.values() if not e["shares"])}


def main():
    if not SRC.exists() or not any(p.is_file() and p.name.lower() != "readme.md" for p in SRC.rglob("*")):
        print("gem_coal: nothing in gem/coal/download/ yet; the owner uploads the tracker download there")
        return
    digest = hashlib.sha256()
    for p in sorted(SRC.rglob("*")):
        if p.is_file():
            digest.update(p.name.encode())
            digest.update(str(p.stat().st_size).encode())
    if STAMP.exists() and json.loads(STAMP.read_text()).get("download") == digest.hexdigest() and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("gem_coal: the download has not changed")
        return
    need()
    work = pathlib.Path(tempfile.mkdtemp())
    files = unpack(work)
    tables, geos = [], []
    for f in files:
        ext = f.suffix.lower()
        if ext in (".xlsx", ".xlsm", ".csv"):
            for name, rows in sheets(f):
                head, body = header(rows)
                if head:
                    tables.append((name, head, [r for r in body if any(c not in (None, "") for c in r)]))
        elif ext in GEO_EXT or f.parent.suffix.lower() == ".gdb":
            geos.append(f.parent if f.parent.suffix.lower() == ".gdb" else f)
    geos = sorted(set(geos))
    build = {"read": datetime.date.today().isoformat(), "download": digest.hexdigest(), "files": [str(f.relative_to(work)) if work in f.parents else str(f) for f in files],
             "sheets": {n: {"columns": h, "rows": len(b)} for n, h, b in tables}}
    located = [(n, h, b) for n, h, b in tables if col(h, r"^lat(itude)?$", r"latitude") and col(h, r"^lon(gitude)?$|^lng$", r"longitude")]
    if not located:
        build["built"] = False
        build["why"] = "no sheet with latitude and longitude columns; see sheets"
        OUT_DIR.mkdir(exist_ok=True)
        STAMP.write_text(json.dumps(build, indent=1, ensure_ascii=False, default=str))
        raise SystemExit("gem_coal: no sheet with latitude and longitude")
    # Round 176b (carries the lost 146b): every sheet of mines with a position
    # and a mine ID (open and closed mines alike), each mine saying which
    # sheet it came from. GEM's own methane estimate colours the dots; where a
    # sheet has none (closed mines), the reported figure does.
    mine_sheets = [(n, h, b) for n, h, b in located if col(h, r"^gem mine id$", r"mine id")]
    if not mine_sheets:
        mine_sheets = [max(located, key=lambda t: len(t[2]))]
    build["mines_sheets"] = {}
    mines, by_id, unplaced = [], {}, 0
    idc = meth = None
    for name, head, body in mine_sheets:
        la, lo = col(head, r"^lat(itude)?$", r"latitude"), col(head, r"^lon(gitude)?$|^lng$", r"longitude")
        sid = col(head, r"^gem mine id$", r"mine id", r"^gem.*id$", r"^id$")
        idc = idc or sid
        m = col(head, r"gem coal mine methane emissions estimate \(m tonnes", r"methane.*estimate", r"reported coal mine methane emissions \(thousand tonnes ch4\)",
                r"methane.*(emission|estimate)", r"\bcmm\b.*(emission|estimate)")
        build["mines_sheets"][name] = {"latitude": la, "longitude": lo, "id_column": sid, "methane_column": m, "rows": len(body)}
        ix = {h: i for i, h in enumerate(head)}
        sheet_short = re.sub(r"^.*/\s*", "", name)
        for r in body:
            props = {h: clean(r[i]) for h, i in ix.items() if i < len(r) and r[i] not in (None, "")}
            lat, lon = num(props.get(la)), num(props.get(lo))
            if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                unplaced += 1
                continue
            props["Tracker sheet"] = sheet_short
            if m and num(props.get(m)) is not None:
                props["methane_for_colour"] = num(props.get(m))
                props["methane_for_colour_is"] = m
            f = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}, "properties": props}
            mines.append(f)
            if sid and props.get(sid) is not None:
                by_id.setdefault(str(props[sid]).strip(), []).append(f)
    joined, not_joined = {}, []
    names_used = {n for n, _, _ in mine_sheets}
    # The ownership sheet (one row per chain and per unit) is written into
    # each mine as its distinct chains, one line each, with the parent's
    # headquarters; its other columns repeat the mine's own.
    for n, h, b in tables:
        if not (col(h, r"^ownership path$") and col(h, r"^gem mine id$") and col(h, r"^parent$")):
            continue
        names_used.add(n)
        hi = {x: i for i, x in enumerate(h)}
        pc, mc = col(h, r"^ownership path$"), col(h, r"^gem mine id$")
        hq = col(h, r"^parent headquarters country$")
        seen, count = {}, 0
        for r in b:
            path = r[hi[pc]] if hi[pc] < len(r) else None
            mine = r[hi[mc]] if hi[mc] < len(r) else None
            if not path or mine is None:
                continue
            line = str(path) + (f" (parent's headquarters: {r[hi[hq]]})" if hq and hi[hq] < len(r) and r[hi[hq]] else "")
            for f in by_id.get(str(mine).strip(), []):
                got = seen.setdefault(id(f), set())
                if line in got:
                    continue
                got.add(line)
                f["properties"][f"Ownership chain {len(got)}"] = line
                count += 1
        joined[n + " (as distinct chains)"] = count
    for n, h, b in tables:
        if n in names_used:
            continue
        k = idc if idc in h else col(h, r"^gem mine id$", r"mine id")
        if not k or not by_id:
            not_joined.append(n)
            continue
        short = re.sub(r"^.*/\s*", "", n)
        hi = {x: i for i, x in enumerate(h)}
        count = 0
        for r in b:
            key = r[hi[k]] if hi[k] < len(r) else None
            for f in by_id.get(str(key).strip(), []) if key is not None else []:
                f["properties"]["_n_" + short] = f["properties"].get("_n_" + short, 0) + 1
                j = f["properties"]["_n_" + short]
                for x, i in hi.items():
                    if x != k and i < len(r) and r[i] not in (None, ""):
                        f["properties"][f"{short} {j}: {x}"] = clean(r[i])
                count += 1
        joined[n] = count
    for f in mines:
        for key in [k for k in f["properties"] if k.startswith("_n_")]:
            del f["properties"][key]
    OUT_DIR.mkdir(exist_ok=True)
    MINES.write_text(json.dumps({"type": "FeatureCollection", "features": mines}, ensure_ascii=False, default=str))
    build.update(mines=len(mines), not_placed=unplaced, joined_rows=joined, not_joined=not_joined, boundary_files=[str(g) for g in geos])
    if geos:
        tools()
        parts = []
        for i, g in enumerate(geos):
            out = work / f"b{i}.geojsonseq"
            try:
                sh("ogr2ogr", "-f", "GeoJSONSeq", "-t_srs", "EPSG:4326", str(out), str(g))
                parts.append(str(out))
            except subprocess.CalledProcessError as e:
                build.setdefault("boundary_errors", []).append(f"{g}: {e}")
        if parts:
            BOUNDS.parent.mkdir(exist_ok=True)
            sh("tippecanoe", "-o", str(BOUNDS), "--force", "-l", "boundaries", "-Z0", "-z12", "--drop-densest-as-needed",
               "--extend-zooms-if-still-dropping", "--no-tile-size-limit", "--attribution", "Global Energy Monitor, Global Coal Mine Tracker (CC BY 4.0)", *parts)
            build["boundaries_built"] = True
    try:
        build["parents"] = rank_parents(tables, by_id)
    except Exception as e:  # noqa: BLE001
        build["parents"] = {"error": f"{type(e).__name__}: {e}"}
        print(f"::warning::gem_coal: parent ranking failed ({e})", flush=True)
    build["built"] = True
    STAMP.write_text(json.dumps(build, indent=1, ensure_ascii=False, default=str))
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem_coal: {len(mines):,} mines ({unplaced} without a position), joined {joined}, not joined {not_joined}", flush=True)


if __name__ == "__main__":
    main()
