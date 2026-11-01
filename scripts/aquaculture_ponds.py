#!/usr/bin/env python3
"""
Aquaculture ponds worldwide, 2020, built once into tiles/aquaculture_ponds*.pmtiles.

Source: Zenodo record 5643036, "Global Landside Clustering of Aquaculture
Ponds Distribution Acquired from Dense Time-Series Sentinel-2 Images by Google
Earth Engine" (the paper: International Journal of Applied Earth Observation
and Geoinformation, 2022): the areas on land where aquaculture ponds cluster,
worldwide, for 2020, from 10 m Sentinel-2 images. Ponds on land only: sea
cages, rafts and lines are not in it. The record's own page
gives its authors, paper and licence; this build writes the record's metadata
beside the archive (tiles/aquaculture_ponds.build.json) so the map's row can
be checked against it.

Built exactly as the mine features are (scripts/mine_features.py, whose
tiling, census and split are the mines build's own): one point per pond, every
one in the world-view square, to zoom 6; outlines from zoom 7 to 13 with none
folded away; the result cut into files GitHub will take. A fixed research
release, so it is built once; set PONDS_REBUILD=1 to build it again.

Asked for 23 September (round 23, item 5): a worldwide aquaculture map for the
Oceans heading, beside the Clark Labs tropical pond maps.
"""
import json, os, pathlib, subprocess, sys, tempfile, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mines  # noqa: E402
import mine_features  # noqa: E402  label points and the world-view count

RECORD = "https://zenodo.org/api/records/5643036"
OUT = pathlib.Path("tiles/aquaculture_ponds.pmtiles")
STAMP = OUT.with_suffix(".build.json")
VECTOR = (".gpkg", ".shp", ".geojson", ".json", ".kml", ".gdb")


def main():
    if OUT.exists() and STAMP.exists() and not os.environ.get("PONDS_REBUILD") and json.loads(STAMP.read_text()).get("points_at_world_view") is True:
        print("aquaculture ponds: already built (set PONDS_REBUILD=1 to build again)")
        return
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    record = json.load(urllib.request.urlopen(urllib.request.Request(RECORD, headers={"User-Agent": "Culprits"})))
    meta = record.get("metadata") or {}
    print("  record:", meta.get("title"), "| licence:", (meta.get("license") or {}).get("id"),
          "| doi:", record.get("doi") or meta.get("doi"))
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
        sys.exit("aquaculture ponds: no map file among " + ", ".join(str(p.relative_to(work)) for p in work.rglob("*") if p.is_file()))
    seen = {}
    for p in found:
        seen[str(p.relative_to(work))] = subprocess.run(["ogrinfo", "-so", "-al", str(p)], capture_output=True, text=True).stdout
        print(f"  ---- {p.relative_to(work)}\n{seen[str(p.relative_to(work))]}")
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
                    if "id" in props:
                        props["source_id"] = props["id"]
                    props["id"] = n
                    if len(found) > 1:
                        props["source_file"] = p.name
                    f["properties"] = props
                    fo.write(json.dumps(f, separators=(",", ":")) + "\n")
    if not n:
        sys.exit("aquaculture ponds: the release holds no outlines that could be read")
    print(f"  {n:,} ponds read")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    ptiles, otiles = work / "points.mbtiles", work / "outlines.mbtiles"
    pts = work / "pts.geojsonl"
    made = mine_features.points_file(polys, pts)
    mines.sh("tippecanoe", "-o", str(ptiles), "--force", "-q", "-Z0", f"-z{mines.POINTS_TO}", "-r1", "-l", "pond_points",
             "--no-feature-limit", "--no-tile-size-limit", str(pts))
    world = mine_features.world_count(ptiles)
    print(f"  {world:,} of {made:,} points in the world-view square")
    if world != made:
        sys.exit(f"aquaculture ponds: the world view holds {world:,} points of {made:,}; nothing kept")
    mines.sh("tippecanoe", "-o", str(otiles), "--force", "-q", f"-Z{mines.POINTS_TO + 1}", f"-z{mines.OUTLINES_TO}", "-P", "-l", "ponds",
             "--drop-densest-as-needed", "--extend-zooms-if-still-dropping", "--simplification=4", "--no-tiny-polygon-reduction",
             f"--maximum-tile-bytes={mines.TILE_BYTES}", str(polys))
    counted = mines.census(otiles, polys)
    mines.OUT = OUT                      # the split names its files after this
    parts = mines.split(ptiles, otiles, work)
    STAMP.write_text(json.dumps({"points_merged": False, "points_whole": True, "points_at_world_view": True,
                                 "tile_bytes": mines.TILE_BYTES, "points_to": mines.POINTS_TO, "zoom": mines.OUTLINES_TO,
                                 "outlines": n, "record": {"title": meta.get("title"), "licence": meta.get("license"),
                                 "doi": record.get("doi") or meta.get("doi"), "creators": meta.get("creators")},
                                 "files_in_release": seen, "parts": parts, **counted}, indent=1))
    print("aquaculture ponds: built", OUT, "and", STAMP)


if __name__ == "__main__":
    main()
