#!/usr/bin/env python3
"""
Solar farms worldwide (round 209o, asked 15 October 2026: "all solar tech
locations worldwide"): Global Energy Monitor's Global Solar Power Tracker,
every phase it lists (operating, under construction, announced, shelved,
cancelled and retired alike), every column as GEM gives it.

Licence: GEM's Creative Commons CC BY 4.0, credit "Global Energy Monitor,
Global Solar Power Tracker, <release>". GEM notes that rows with a "TZ ID"
come from TransitionZero's Solar Asset Mapper under CC BY-NC 4.0; this map
is non-commercial, and those rows keep their TZ ID in their box.

GEM gives the tracker only through its download form, so the owner downloads
it from globalenergymonitor.org/projects/global-solar-power-tracker/download-data/
and uploads what comes (a zip or spreadsheet, as it is) into
culprits-tiles-more gem/solar/download/. This script then:

  1. reads every spreadsheet (inside zips too); the phases sheet is the one
     with latitude and longitude columns and the most rows;
  2. writes tiles/solar_gem.pmtiles, layer "solar_gem", one point per phase,
     every column kept; "value" is the phase's capacity in MW (the column
     whose name says capacity and MW), for the map's glow;
  3. writes solar/gem_solar_build.json: the file and sheet read, the columns,
     how many rows, and how many had no position (listed, not placed).

Runs when the download folder changes; otherwise it leaves the last copy.
"""
import hashlib, json, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gem_coal  # noqa: E402  (its sheet readers)
import mines     # noqa: E402  (tippecanoe)

SRC = pathlib.Path("gem/solar/download")
OUT = pathlib.Path("tiles") / "solar_gem.pmtiles"
STAMP = pathlib.Path("solar") / "gem_solar_build.json"


def files_in(work):
    import zipfile
    files = [p for p in sorted(SRC.rglob("*")) if p.is_file() and p.name.lower() != "readme.md"]
    out, i = [], 0
    while files:
        p = files.pop(0)
        if p.suffix.lower() == ".zip":
            d = work / f"z{i}"
            i += 1
            zipfile.ZipFile(p).extractall(d)
            files += [q for q in sorted(d.rglob("*")) if q.is_file()]
        elif p.suffix.lower() in (".xlsx", ".xlsm", ".csv"):
            out.append(p)
    return out


def main():
    SRC.mkdir(parents=True, exist_ok=True)
    readme = SRC / "README.md"
    if not readme.exists():
        readme.write_text("Upload Global Energy Monitor's Global Solar Power Tracker download here (zip or spreadsheet, as it comes).\n")
    src_files = [p for p in sorted(SRC.rglob("*")) if p.is_file() and p.name.lower() != "readme.md"]
    if not src_files:
        print("gem_solar: nothing in gem/solar/download yet; the row says it is not built")
        return
    h = hashlib.sha256()
    for p in src_files:
        h.update(p.name.encode()); h.update(p.read_bytes())
    digest = h.hexdigest()
    if STAMP.exists() and OUT.exists():
        try:
            if json.loads(STAMP.read_text()).get("sha256") == digest:
                print("gem_solar: download unchanged; the copy stands")
                return
        except ValueError:
            pass
    gem_coal.need()
    work = pathlib.Path(tempfile.mkdtemp())
    best = None
    for f in files_in(work):
        for name, rows in gem_coal.sheets(f):
            head, body = gem_coal.header(rows)
            if not head:
                continue
            lat, lon = gem_coal.col(head, r"^latitude$", r"\blat"), gem_coal.col(head, r"^longitude$", r"\blon")
            if lat and lon and (best is None or len(body) > len(best[2])):
                best = (name, head, body, lat, lon)
    if not best:
        sys.exit("gem_solar: no sheet with latitude and longitude columns was found in the download")
    name, head, body, lat, lon = best
    cap = gem_coal.col(head, r"capacity.*\(mw", r"capacity.*mw", r"capacity")
    ix = {c: i for i, c in enumerate(head)}
    feats, unplaced = [], 0
    for r in body:
        if not any(v not in (None, "") for v in r):
            continue
        p = {c: gem_coal.clean(r[i]) for c, i in ix.items() if i < len(r) and r[i] not in (None, "")}
        y, x = gem_coal.num(p.get(lat)), gem_coal.num(p.get(lon))
        if y is None or x is None or not (-90 <= y <= 90 and -180 <= x <= 180):
            unplaced += 1
            continue
        if cap and gem_coal.num(p.get(cap)) is not None:
            p["value"] = gem_coal.num(p.get(cap))
        feats.append({"type": "Feature", "properties": p, "geometry": {"type": "Point", "coordinates": [x, y]}})
    pts = work / "solar.geojsonl"
    with open(pts, "w", encoding="utf-8") as fh:
        for f in feats:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    mines.tools()
    OUT.parent.mkdir(exist_ok=True)
    for maxz in (12, 11, 10):
        gem_coal.sh("tippecanoe", "-o", str(OUT), "--force", "-l", "solar_gem", "-Z0", f"-z{maxz}", "-r1",
                    "--no-feature-limit", "--no-tile-size-limit", "-q", "-P", str(pts))
        if OUT.stat().st_size <= 95 * 1024 * 1024:
            break
    else:
        OUT.unlink()
        sys.exit("gem_solar: could not get the archive under GitHub's 100 MB limit")
    STAMP.parent.mkdir(exist_ok=True)
    STAMP.write_text(json.dumps({"sha256": digest, "sheet": name, "columns": head, "capacity_column": cap,
                                 "phases": len(feats), "no_position": unplaced, "maxzoom": maxz}, indent=1, ensure_ascii=False))
    print(f"gem_solar: {len(feats)} phases placed, {unplaced} without a position, from {name}")


if __name__ == "__main__":
    main()
