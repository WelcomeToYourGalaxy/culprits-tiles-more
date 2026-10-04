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
  3. writes methane/gem_coal_mines.geojson, one point per mine. The column
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
    name, head, body = max(located, key=lambda t: len(t[2]))
    la, lo = col(head, r"^lat(itude)?$", r"latitude"), col(head, r"^lon(gitude)?$|^lng$", r"longitude")
    idc = col(head, r"^gem mine id$", r"mine id", r"^gem.*id$", r"^id$")
    meth = col(head, r"methane.*(emission|estimate)", r"\bcmm\b.*(emission|estimate)", r"methane", r"\bcmm\b")
    build.update(mines_sheet=name, latitude=la, longitude=lo, id_column=idc, methane_column=meth)
    ix = {h: i for i, h in enumerate(head)}
    mines, by_id, unplaced = [], {}, 0
    for r in body:
        props = {h: clean(r[i]) for h, i in ix.items() if i < len(r) and r[i] not in (None, "")}
        lat, lon = num(props.get(la)), num(props.get(lo))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            unplaced += 1
            continue
        if meth and num(props.get(meth)) is not None:
            props["methane_for_colour"] = num(props.get(meth))
        f = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]}, "properties": props}
        mines.append(f)
        if idc and props.get(idc) is not None:
            by_id.setdefault(str(props[idc]).strip(), []).append(f)
    joined, not_joined = {}, []
    for n, h, b in tables:
        if n == name:
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
    build["built"] = True
    STAMP.write_text(json.dumps(build, indent=1, ensure_ascii=False, default=str))
    shutil.rmtree(work, ignore_errors=True)
    print(f"gem_coal: {len(mines):,} mines ({unplaced} without a position), joined {joined}, not joined {not_joined}", flush=True)


if __name__ == "__main__":
    main()
