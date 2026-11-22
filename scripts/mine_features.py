#!/usr/bin/env python3
"""
Mine features worldwide (Tang & Werner 2023), built once into tiles/mine_features*.pmtiles.

Source: "Global mining footprint mapped from high-resolution satellite imagery",
Liang Tang and Tim T. Werner, Communications Earth & Environment 4, 134 (2023),
data at Zenodo record 7894216, CC BY 4.0: 74,548 outlines drawn tight around
each mine feature - pits, waste rock dumps, tailings dams, ponds, heap leach
pads, processing plant - not around a whole mine site. That is how it differs
from the Mines layer already on the map (Maus et al. 2022), whose outlines take
in the ground between a mine's features.

WHAT IT CARRIES is not known until the file is opened: the first thing this does
is write every layer and column it finds to the log and to
tiles/mine_features.build.json. Every column is kept on every outline. Whether
the map's row can say anything about commodities depends on what that list
shows.

Built exactly as the mines are (scripts/mines.py does the work): counted points
to zoom 6 with every feature kept, outlines from zoom 7 to 13 with none folded
away, the build stopped if tippecanoe left anything out, the outlines counted
zoom by zoom, and the result cut into files GitHub will take. A fixed research
release, so it is built once; set MINES_REBUILD=1 to build it again.
"""
import json, os, pathlib, subprocess, sys, tempfile, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mines  # noqa: E402  the tiling, the census and the split are the mines build's own

RECORD = "https://zenodo.org/api/records/7894216"
OUT = pathlib.Path("tiles/mine_features.pmtiles")
STAMP = OUT.with_suffix(".build.json")
VECTOR = (".gpkg", ".shp", ".geojson", ".json", ".kml", ".gdb")


def label_point(geom):
    """A point for an outline, from its own corners: the middle of the largest
    ring's corners, which for the small, compact shapes these are lies inside
    them. Computed here rather than by tippecanoe, whose polygon-to-point
    conversion ran after it had folded outlines smaller than a pixel into
    stand-ins, so at the world view only 14,169 of 74,548 features had a point
    (round 23, item 13)."""
    t, c = geom.get("type"), geom.get("coordinates") or []
    rings = [c[0]] if t == "Polygon" and c else [p[0] for p in c if p] if t == "MultiPolygon" else []
    ring = max(rings, key=len) if rings else []
    pts = [(x[0], x[1]) for x in ring[:-1] or ring]
    if not pts:
        return None
    return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def points_file(polys, pts):
    """One point per outline, carrying the outline's own fields. Returns how
    many can be drawn: a web map stops at 85.05 degrees north and south, so a
    point beyond that is in no square at any zoom, and is counted apart."""
    n = beyond = 0
    with open(polys, encoding="utf-8") as fi, open(pts, "w", encoding="utf-8") as fo:
        for line in fi:
            f = json.loads(line)
            at = label_point(f["geometry"])
            if at is None:
                continue
            fo.write(json.dumps({"type": "Feature", "properties": f["properties"],
                                 "geometry": {"type": "Point", "coordinates": at}}, separators=(",", ":")) + "\n")
            if abs(at[1]) > 85.0511:
                beyond += 1
            else:
                n += 1
    if beyond:
        print(f"  {beyond:,} lie beyond 85 degrees north or south, where no web map reaches")
    return n


def world_count(ptiles):
    """How many features the world-view square holds, counted from the decoded
    square itself. Counting the text "Point" missed the ones tippecanoe writes
    as MultiPoint (round 23: 74,444 of 74,548 and 78 of 79 were short by exactly
    those), so the features are read as JSON and counted."""
    out = subprocess.run(["tippecanoe-decode", "-Z0", "-z0", str(ptiles)], capture_output=True, text=True).stdout
    n = 0
    def walk(o):
        nonlocal n
        if isinstance(o, dict):
            if o.get("type") == "Feature":
                n += 1
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(json.loads(out))
    return n


def main():
    # A build from before 23 September merged its points, and one from before
    # round 23 lost most of them at the world view; either is made again.
    if OUT.exists() and STAMP.exists() and not os.environ.get("MINES_REBUILD") and json.loads(STAMP.read_text()).get("points_at_world_view") is True:
        print("mine features: already built (set MINES_REBUILD=1 to build again)")
        return
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    record = json.load(urllib.request.urlopen(urllib.request.Request(RECORD, headers={"User-Agent": "Culprits"})))
    files = record.get("files") or []
    print("  record files:", ", ".join(f"{f['key']} ({f.get('size', 0) / 1e6:.1f} MB)" for f in files))
    for f in files:
        path = work / f["key"]
        mines.download(f["links"]["self"], path)
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                z.extractall(work / (path.stem + "_unzipped"))
    found = sorted(p for p in work.rglob("*") if p.suffix.lower() in VECTOR and not p.name.startswith("."))
    if not found:
        sys.exit("mine features: no map file among " + ", ".join(str(p.relative_to(work)) for p in work.rglob("*") if p.is_file()))
    # What the release holds, in full, before anything is decided about it.
    seen = {}
    for p in found:
        info = subprocess.run(["ogrinfo", "-so", "-al", str(p)], capture_output=True, text=True).stdout
        seen[str(p.relative_to(work))] = info
        print(f"  ---- {p.relative_to(work)}\n{info}")
    polys = work / "polys.geojsonl"
    n = 0
    with open(polys, "w", encoding="utf-8") as fo:
        for p in found:
            raw = work / (p.stem + ".raw.geojsonl")
            r = subprocess.run(["ogr2ogr", "-f", "GeoJSONSeq", str(raw), str(p), "-t_srs", "EPSG:4326"], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"  {p.name}: could not be read ({r.stderr.strip()[:200]})")
                continue
            with open(raw, encoding="utf-8") as fi:
                for line in fi:
                    line = line.strip().lstrip("\x1e")
                    if not line:
                        continue
                    f = json.loads(line)
                    if not f.get("geometry") or "Polygon" not in f["geometry"].get("type", ""):
                        continue
                    props = f.get("properties") or {}
                    n += 1
                    # The release's own id, if it has one, is kept beside this one, which only the count uses.
                    if "id" in props:
                        props["source_id"] = props["id"]
                    props["id"] = n
                    if len(found) > 1:
                        props["source_file"] = p.name
                    f["properties"] = props
                    fo.write(json.dumps(f, separators=(",", ":")) + "\n")
    if not n:
        sys.exit("mine features: the release holds no outlines that could be read")
    print(f"  {n:,} outlines read (the paper gives 74,548)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ptiles, otiles = work / "points.mbtiles", work / "outlines.mbtiles"
    # Every point at every zoom, none merged (asked for 23 September): no
    # clustering, and no size cap that would merge or drop points to fit.
    pts = work / "pts.geojsonl"
    made = points_file(polys, pts)
    mines.sh("tippecanoe", "-o", str(ptiles), "--force", "-q", "-Z0", f"-z{mines.POINTS_TO}", "-r1", "-l", "mine_feature_points",
             "--no-feature-limit", "--no-tile-size-limit", str(pts))
    world = world_count(ptiles)
    print(f"  {world:,} of {made:,} points in the world-view square")
    if world != made:
        sys.exit(f"mine features: the world view holds {world:,} points of {made:,}; nothing kept")
    mines.sh("tippecanoe", "-o", str(otiles), "--force", "-q", f"-Z{mines.POINTS_TO + 1}", f"-z{mines.OUTLINES_TO}", "-P", "-l", "mine_features",
             "--drop-densest-as-needed", "--extend-zooms-if-still-dropping", "--simplification=4", "--no-tiny-polygon-reduction",
             f"--maximum-tile-bytes={mines.TILE_BYTES}", str(polys))
    counted = mines.census(otiles, polys)
    mines.OUT = OUT                      # the split names its files after this
    parts = mines.split(ptiles, otiles, work)
    STAMP.write_text(json.dumps({"points_merged": False, "points_whole": True, "points_at_world_view": True, "tile_bytes": mines.TILE_BYTES, "points_to": mines.POINTS_TO, "zoom": mines.OUTLINES_TO,
                                 "outlines": n, "files_in_release": seen, "parts": parts, **counted}, indent=1))
    print("mine features: built", OUT, "and", STAMP)


if __name__ == "__main__":
    main()
