#!/usr/bin/env python3
"""
Fires detected by satellite across South America in 2023 (INPE), as map tiles
(round 107b). From the owner's Attacks On Activists collection: the shapefile
"All Cases in South America in GIS Format" is INPE's fire foci for 1 January to
11 December 2023 (focos_qmd_inpe_20230101_20231211), 332,432 detections, read
into attacks/inpe_fire_foci_2023.geojson.gz (every field kept). Too many for
the map to read as one file, so it is cut into tiles here.

  tiles/inpe_fire_2023.pmtiles   layer "inpe_fire_2023"

Built once; again only if the source file changes or INPE_REBUILD=1.
"""
import gzip, json, os, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
SRC = pathlib.Path("attacks/inpe_fire_foci_2023.geojson.gz")
OUT = pathlib.Path("tiles/inpe_fire_2023.pmtiles")


def main():
    if not SRC.exists():
        sys.exit("inpe_fire: attacks/inpe_fire_foci_2023.geojson.gz not found")
    if OUT.exists() and OUT.stat().st_mtime >= SRC.stat().st_mtime and not os.environ.get("INPE_REBUILD"):
        print("inpe_fire: built already")
        return
    import mines  # noqa: E402  sh() and tools()
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    lines = work / "fire.ndjson"
    n = 0
    with gzip.open(SRC, "rt", encoding="utf-8") as f, open(lines, "w", encoding="utf-8") as fo:
        for ft in json.load(f)["features"]:
            fo.write(json.dumps(ft, ensure_ascii=False, separators=(",", ":")) + "\n")
            n += 1
    out = work / "inpe_fire_2023.pmtiles"
    mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", "inpe_fire_2023", "-Z0", "-z11", "-r1",
             "--no-feature-limit", "--no-tile-size-limit", str(lines))
    if out.stat().st_size > 95 * 1024 * 1024:
        sys.exit(f"inpe_fire: {out.stat().st_size / 1e6:.0f} MB is over GitHub's limit")
    OUT.parent.mkdir(exist_ok=True)
    os.replace(out, OUT)
    print(f"inpe_fire: {n:,} fires, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
