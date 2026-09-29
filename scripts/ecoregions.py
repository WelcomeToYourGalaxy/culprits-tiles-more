#!/usr/bin/env python3
"""
RESOLVE's Ecoregions 2017 as the map's own copy (round 99b, asked 28
September: Global Safety Net's "Terrestrial Ecoregions" row did not load, or
not fast enough).

Source: Dinerstein et al. 2017, "An Ecoregion-Based Approach to Protecting
Half the Terrestrial Realm", BioScience 67(6); the file RESOLVE publishes,
https://storage.googleapis.com/teow2016/Ecoregions2017.zip (CC BY 4.0). 846
ecoregions in 14 biomes, every field kept (ECO_NAME, BIOME_NUM, BIOME_NAME,
REALM, NNH, NNH_NAME, COLOR ... as the file gives them).

  tiles/ecoregions_2017.pmtiles   layer "ecoregions", zooms 0 to 9 (fewer if over 95 MB)
  ecoregions/build.json           what was read

Built once; ECOREGIONS_REBUILD=1 builds it again.
"""
import json, os, pathlib, sys, tempfile, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

URL = "https://storage.googleapis.com/teow2016/Ecoregions2017.zip"
OUT = pathlib.Path("ecoregions")
TILE = pathlib.Path("tiles") / "ecoregions_2017.pmtiles"
LIMIT = 95 * 1024 * 1024
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}


def main():
    if TILE.exists() and not os.environ.get("ECOREGIONS_REBUILD"):
        print("ecoregions: already built")
        return
    import mines
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    z = work / "Ecoregions2017.zip"
    with urllib.request.urlopen(urllib.request.Request(URL, headers=UA), timeout=1800) as r, open(z, "wb") as f:
        while True:
            b = r.read(1 << 22)
            if not b:
                break
            f.write(b)
    print(f"ecoregions: {z.stat().st_size / 1e6:.0f} MB", flush=True)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(work)
        names = zf.namelist()
    shp = next(work / n for n in names if n.lower().endswith(".shp"))
    lines = work / "ecoregions.geojsons"
    mines.sh("ogr2ogr", "-f", "GeoJSONSeq", "-t_srs", "EPSG:4326", "-makevalid", str(lines), str(shp))
    n = sum(1 for _ in open(lines, encoding="utf-8"))
    TILE.parent.mkdir(exist_ok=True)
    for top in (9, 8, 7):
        mines.sh("tippecanoe", "-o", str(TILE), "--force", "-q", "-l", "ecoregions", "-Z0", f"-z{top}", "--detect-shared-borders",
                 "--coalesce-densest-as-needed", "--simplification=4", "--maximum-tile-bytes=800000", str(lines))
        if TILE.stat().st_size <= LIMIT:
            break
        print(f"ecoregions: {TILE.stat().st_size / 1e6:.0f} MB at zoom {top}; one zoom lower", flush=True)
    else:
        sys.exit("ecoregions: still over 95 MB")
    OUT.mkdir(exist_ok=True)
    (OUT / "build.json").write_text(json.dumps({"from": URL, "file": shp.name, "ecoregions": n, "to_zoom": top,
                                                "bytes": TILE.stat().st_size}, indent=1))
    print(f"ecoregions: {n} ecoregions, zooms 0 to {top}", flush=True)


if __name__ == "__main__":
    main()
