#!/usr/bin/env python3
"""
Mines worldwide, built once into tiles/mining_polygons.pmtiles.

Source: "Global mining deforestation footprint data from 2000 to 2019"
(WU Vienna, Zenodo record 7307210, ODbL): Maus et al. 2022's satellite-traced
mining polygons merged with OpenStreetMap's mines and quarries, 192,584 outlines,
with the tree cover loss inside each from 2000 to 2019. A fixed research
release, so it is built once; set MINES_REBUILD=1 to build again.

Two layers in the archive: "mines" (the outlines, from zoom 7) and
"mine_points" (a point inside each outline, to zoom 8), so the whole set can be
seen from the world view without drawing 192,584 outlines at once.
"""
import csv, gzip, io, json, os, pathlib, shutil, subprocess, sys, tempfile, urllib.request

OUT = pathlib.Path("tiles/mining_polygons.pmtiles")
RECORD = "https://zenodo.org/api/records/7307210"
LIMIT = 95 * 1024 * 1024          # GitHub refuses files over 100 MB


def sh(*cmd, **kw):
    print("  $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def tools():
    if not shutil.which("ogr2ogr"):
        sh("sudo", "apt-get", "update", "-qq")
        sh("sudo", "apt-get", "install", "-y", "-qq", "gdal-bin", "libsqlite3-dev", "zlib1g-dev", "build-essential")
    if not shutil.which("tippecanoe"):
        d = tempfile.mkdtemp()
        sh("git", "clone", "--depth", "1", "https://github.com/felt/tippecanoe.git", d)
        sh("make", "-j4", cwd=d)
        sh("sudo", "make", "install", cwd=d)


def download(url, to):
    req = urllib.request.Request(url, headers={"User-Agent": "Culprits atlas build"})
    with urllib.request.urlopen(req, timeout=600) as r, open(to, "wb") as f:
        shutil.copyfileobj(r, f)


def loss_table(files, work):
    """The tree cover loss per mine, if the record has it as CSV (wide or long)."""
    for f in files:
        key = f["key"]
        if not key.lower().endswith((".csv", ".csv.gz")):
            continue
        path = work / key
        download(f["links"]["self"], path)
        opener = gzip.open if key.endswith(".gz") else open
        table = {}
        with opener(path, "rt", encoding="utf-8", errors="replace") as fh:
            rows = csv.DictReader(fh)
            cols = rows.fieldnames or []
            if "id" not in cols:
                continue
            long_form = "year" in cols
            value_col = next((c for c in cols if c not in ("id", "year", "isoa3", "country")), None)
            for r in rows:
                rec = table.setdefault(r["id"], {})
                if long_form and value_col:
                    rec[f"loss_{r['year']}"] = float(r[value_col] or 0)
                else:
                    for c in cols:
                        if c != "id" and any(ch.isdigit() for ch in c):
                            try:
                                rec[c] = float(r[c])
                            except (TypeError, ValueError):
                                pass
        print(f"  tree cover loss read from {key} for {len(table):,} mines")
        return table
    print("  no CSV loss table in the record; outlines are built without it")
    return {}


def main():
    if OUT.exists() and not os.environ.get("MINES_REBUILD"):
        print("mines: already built (set MINES_REBUILD=1 to build again)")
        return
    tools()
    work = pathlib.Path(tempfile.mkdtemp())
    record = json.load(urllib.request.urlopen(urllib.request.Request(RECORD, headers={"User-Agent": "Culprits"})))
    files = record.get("files") or []
    print("  record files:", ", ".join(f["key"] for f in files))
    gpkg = next(f for f in files if f["key"].endswith(".gpkg"))
    gpath = work / gpkg["key"]
    download(gpkg["links"]["self"], gpath)
    loss = loss_table(files, work)

    polys, pts = work / "polys.geojsonl", work / "pts.geojsonl"
    sh("ogr2ogr", "-f", "GeoJSONSeq", str(work / "raw.geojsonl"), str(gpath), "-t_srs", "EPSG:4326")
    sh("ogr2ogr", "-f", "GeoJSONSeq", str(work / "rawpts.geojsonl"), str(gpath), "-dialect", "SQLITE",
       "-sql", "SELECT id, isoa3, country, area, ST_PointOnSurface(geom) AS geom FROM mining_polygons", "-t_srs", "EPSG:4326")
    for src, dst, zoom in ((work / "raw.geojsonl", polys, {"minzoom": 7}), (work / "rawpts.geojsonl", pts, {"maxzoom": 8})):
        with open(src, encoding="utf-8") as fi, open(dst, "w", encoding="utf-8") as fo:
            for line in fi:
                line = line.strip().lstrip("\x1e")
                if not line:
                    continue
                f = json.loads(line)
                p = f.get("properties") or {}
                p.update(loss.get(str(p.get("id")), {}))
                f["properties"] = p
                f["tippecanoe"] = zoom
                fo.write(json.dumps(f, separators=(",", ":")) + "\n")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for maxz in (13, 12, 11, 10):
        sh("tippecanoe", "-o", str(OUT), "--force", "-Z0", f"-z{maxz}", "-P",
           "-L", json.dumps({"file": str(polys), "layer": "mines"}),
           "-L", json.dumps({"file": str(pts), "layer": "mine_points"}),
           "--drop-densest-as-needed", "--extend-zooms-if-still-dropping", "--simplification=4")
        size = OUT.stat().st_size
        print(f"  built to zoom {maxz}: {size / 1e6:.1f} MB")
        if size <= LIMIT:
            break
    else:
        OUT.unlink()
        sys.exit("mines: could not get the archive under GitHub's 100 MB limit")
    print("mines: built", OUT)


if __name__ == "__main__":
    main()
