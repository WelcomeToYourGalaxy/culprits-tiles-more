#!/usr/bin/env python3
"""
Mines worldwide, built once into tiles/mining_polygons.pmtiles.

Source: "Global mining deforestation footprint data from 2000 to 2019"
(WU Vienna, Zenodo record 7307210, ODbL): Maus et al. 2022's satellite-traced
mining polygons merged with OpenStreetMap's mines and quarries, 192,584 outlines,
with the tree cover loss inside each from 2000 to 2019. A fixed research
release, so it is built once; set MINES_REBUILD=1 to build again.

Two layers: "mines" (the outlines, zoom 7 to 13) and "mine_points" (a point
inside each outline, to zoom 6, every mine kept at every zoom and merged into
counted points where they crowd), so the whole set can be seen from the world
view without drawing 192,584 outlines at once.

GitHub refuses any file over 100 MB, and the outlines to zoom 13 weigh more
than that. So the build is cut into as many files as it takes, by zoom:
tiles/mining_polygons.pmtiles holds the points and the first zooms of outlines,
tiles/mining_polygons_2.pmtiles the next zooms, and so on. Where one zoom alone
is too big for a file it is cut in two down a line of longitude. Every tile
tippecanoe made is in exactly one file; the count is checked before anything is
kept. tiles/mining_polygons.build.json lists the files and the zooms each
holds, and the map reads that list.
"""
import re, csv, gzip, json, os, pathlib, shutil, sqlite3, subprocess, sys, tempfile, urllib.request

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
            rows = list(rows)

            def numeric(c):
                seen = 0
                for r in rows[:500]:
                    v = (r.get(c) or "").strip()
                    if not v:
                        continue
                    try:
                        float(v)
                    except ValueError:
                        return False
                    seen += 1
                return seen > 0
            # The loss column is the one whose values are numbers (a name like
            # loss or area first); the first run picked an id column by position.
            others = [c for c in cols if c not in ("id", "year", "isoa3", "country")]
            named = [c for c in others if re.search(r"loss|area|km|ha\b|hectare", c, re.I)]
            value_col = next((c for c in named + others if numeric(c)), None)
            print(f"  loss table {key}: columns {cols}; loss read from {value_col!r}")
            for r in rows:
                rec = table.setdefault(r["id"], {})
                if long_form and value_col:
                    try:
                        rec[f"loss_{r['year']}"] = float(r[value_col] or 0)
                    except ValueError:
                        pass
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


# What one tile may weigh. tippecanoe's own default is 500 kB; the map fetches
# one of these per square on screen, so this is the wait at the world view.
TILE_BYTES = 500000
POINTS_TO = 6            # counted points to here; outlines from the zoom above
OUTLINES_TO = 13         # how far in the outlines are tiled


def biggest(path):
    """The largest tile in an .mbtiles, so the build says what a square weighs.

    Measured on the mbtiles tippecanoe writes, not on the .pmtiles that
    tile-join produces: PMTiles is its own format, not a SQLite database.
    """
    try:
        con = sqlite3.connect(str(path))
        n = con.execute("SELECT MAX(LENGTH(tile_data)) FROM tiles").fetchone()[0] or 0
        con.close()
        return n
    except Exception as e:
        print("  could not measure the tiles:", e)
        return 0


ID = re.compile(r'"id": ?("[^"]*"|-?[0-9.]+)')     # a mine's own id, number or text


def census(otiles, polys):
    """Say how many of the mines have an outline at each zoom, and name any that never get one.

    An outline narrower than one step of a tile's grid (about 76 m at zoom 7,
    halving with each zoom) has no shape left to draw at that zoom, so the wide
    zooms can hold fewer outlines than there are mines; the log says how many.
    Any mine with no outline even at the closest zoom is named in the log and
    in the build's record, so it is known rather than quietly absent.
    """
    # tippecanoe writes down what it did at each zoom. If it ever left outlines
    # out to keep a tile under TILE_BYTES, that is in its record, and the build
    # stops here - before any file on the site has been touched.
    con = sqlite3.connect(str(otiles))
    row = con.execute("SELECT value FROM metadata WHERE name = 'strategies'").fetchone()
    con.close()
    for zoom, did in enumerate(json.loads(row[0]) if row and row[0] else []):
        lost = {k: v for k, v in did.items() if "dropped" in k or "coalesced" in k or "tiny" in k}
        if lost:
            sys.exit(f"mines: tippecanoe left outlines out at zoom {zoom} to keep a tile small ({lost}); nothing kept")
    went_in = set()
    with open(polys, encoding="utf-8") as fh:
        for line in fh:
            went_in.update(ID.findall(line))
    made = len(went_in)
    if not made:
        print("  the outlines carry no id, so they cannot be counted zoom by zoom")
        return {"outlines_by_zoom": {}, "no_outline_at_closest_zoom": []}
    con = sqlite3.connect(str(otiles))
    zooms = [z for (z,) in con.execute("SELECT DISTINCT zoom_level FROM tiles ORDER BY 1")]
    con.close()
    seen, last = {}, set()
    for z in zooms:
        ids = set()
        out = subprocess.Popen(["tippecanoe-decode", f"-Z{z}", f"-z{z}", str(otiles)],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        for line in out.stdout:
            ids.update(ID.findall(line))
        out.wait()
        seen[z], last = len(ids), ids
        print(f"  zoom {z}: {len(ids):,} of {made:,} mines have an outline", flush=True)
    missing = sorted(i.strip('"') for i in went_in - last)
    if missing:
        print(f"  NOT DRAWN even at zoom {zooms[-1]}: {len(missing):,} mines whose outline has no area to draw. "
              f"They are still in the points. Their ids: {', '.join(missing[:200])}")
    return {"outlines_by_zoom": seen, "no_outline_at_closest_zoom": missing}


def part_name(n):
    return OUT.name if n == 1 else f"{OUT.stem}_{n}.pmtiles"


def cut(src, dst, where, args):
    """Copy the tiles of `src` that match `where` into a new .mbtiles."""
    if dst.exists():
        dst.unlink()
    con = sqlite3.connect(str(dst))
    con.execute("ATTACH DATABASE ? AS src", (str(src),))
    con.execute("CREATE TABLE metadata (name text, value text)")
    con.execute("INSERT INTO metadata SELECT name, value FROM src.metadata")
    con.execute("CREATE TABLE tiles (zoom_level integer, tile_column integer, tile_row integer, tile_data blob)")
    con.execute(f"INSERT INTO tiles SELECT zoom_level, tile_column, tile_row, tile_data FROM src.tiles WHERE {where}", args)
    con.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)")
    n = con.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    lo, hi = con.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles").fetchone()
    for k, v in (("minzoom", lo), ("maxzoom", hi)):
        con.execute("DELETE FROM metadata WHERE name = ?", (k,))
        con.execute("INSERT INTO metadata VALUES (?, ?)", (k, str(v)))
    con.commit()
    con.close()
    return n


def split(ptiles, otiles, work):
    """Cut the outlines into files GitHub will take, by zoom; the points ride in the first.

    Nothing is left out to make a file fit: a file that comes out too big gives
    up its top zoom to the next file, and a single zoom that is too big on its
    own is cut in two by longitude. The tiles in the files are counted against
    the tiles tippecanoe made, and the build stops if they differ.
    """
    con = sqlite3.connect(str(otiles))
    total = con.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
    zooms = [z for (z,) in con.execute("SELECT DISTINCT zoom_level FROM tiles ORDER BY 1")]
    con.close()

    for old in OUT.parent.glob(f"{OUT.stem}_*.pmtiles"):
        old.unlink()

    # Each piece: (first zoom, last zoom, first column or None, last column or None)
    todo = [(zooms[0], zooms[-1], None, None)]
    parts, placed = [], 0
    while todo:
        z0, z1, x0, x1 = todo.pop(0)
        n = len(parts) + 1
        where, args = "zoom_level BETWEEN ? AND ?", [z0, z1]
        if x0 is not None:
            where, args = where + " AND tile_column BETWEEN ? AND ?", args + [x0, x1]
        piece = work / f"piece_{n}.mbtiles"
        count = cut(otiles, piece, where, args)
        dest = OUT.parent / part_name(n)
        inputs = ([str(ptiles)] if n == 1 else []) + [str(piece)]
        # tile-join leaves out any square over 500 kB unless told not to. With the
        # points no longer merged (23 September), the world-view squares are over
        # that, and the first unmerged build lost them: zoom 0 had no square at
        # all. Nothing is left out now.
        sh("tile-join", "-o", str(dest), "--force", "-q", "--no-tile-size-limit", *inputs)
        size = dest.stat().st_size
        if size > LIMIT:
            dest.unlink()
            if z1 > z0:
                # Too big: this file keeps the lower zooms, the top one waits its turn.
                # If the next piece starts right above it, the two wait together, so
                # zooms that fit in one file are not given a file each.
                nxt = (z1, z1, x0, x1)
                if todo and x0 is None and todo[0][2] is None and todo[0][0] == z1 + 1:
                    nxt = (z1, todo.pop(0)[1], None, None)
                todo = [(z0, z1 - 1, x0, x1), nxt] + todo
            else:
                con = sqlite3.connect(str(piece))
                rows = con.execute("SELECT tile_column, SUM(LENGTH(tile_data)) FROM tiles GROUP BY 1 ORDER BY 1").fetchall()
                con.close()
                if len(rows) < 2:
                    sys.exit(f"mines: zoom {z0} will not fit under GitHub's 100 MB limit however it is cut")
                half, run, mid = sum(b for _, b in rows) / 2, 0, rows[0][0]
                for col, b in rows[:-1]:
                    run, mid = run + b, col
                    if run >= half:
                        break
                todo = [(z0, z0, rows[0][0], mid), (z0, z0, mid + 1, rows[-1][0])] + todo
            continue
        placed += count
        part = {"file": dest.name, "from": z0, "to": z1, "points": n == 1, "bytes": size}
        if x0 is not None:
            part["columns"] = [x0, x1]
        parts.append(part)
        print(f"  {dest.name}: outlines zoom {z0} to {z1}" + (f", columns {x0} to {x1}" if x0 is not None else "")
              + (", with the points" if n == 1 else "") + f" \u2014 {size / 1e6:.1f} MB, {count:,} tiles")
    if placed != total:
        for p in parts:
            (OUT.parent / p["file"]).unlink()
        sys.exit(f"mines: {total:,} outline tiles were made but {placed:,} reached the files; nothing kept")
    print(f"  all {total:,} outline tiles are in {len(parts)} file(s)")
    return parts



# Beside the archive, what it was built with. The old archive was joined with
# no tile size limit at all, and nothing in a .pmtiles says so - so without this
# the run just reported "already built" and left the slow archive in place.
STAMP = OUT.with_suffix(".build.json")


def built_already():
    if not OUT.exists():
        return False
    if os.environ.get("MINES_REBUILD"):
        return False
    try:
        was = json.loads(STAMP.read_text())
        # A build from before 23 September merged its points; it is made again.
        return (was.get("points_whole") is True and was.get("points_merged") is False and was.get("tile_bytes") == TILE_BYTES and was.get("points_to") == POINTS_TO
                and was.get("zoom") == OUTLINES_TO and bool(was.get("parts"))
                and all((OUT.parent / p["file"]).exists() for p in was["parts"]))
    except Exception:
        return False


def main():
    if built_already():
        print(f"mines: already built to {TILE_BYTES / 1000:.0f} kB tiles "
              "(set MINES_REBUILD=1 to build again)")
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
    for src, dst, zoom in ((work / "raw.geojsonl", polys, {"minzoom": POINTS_TO + 1}), (work / "rawpts.geojsonl", pts, {"maxzoom": POINTS_TO})):
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
    # Points: every mine at every zoom from the world view to 8. Where they
    # crowd, they are merged into one point that says how many it stands for
    # (point_count), so none drop out of the wide view.
    ptiles = work / "points.mbtiles"
    # The archive was joined with --no-tile-size-limit, so a single tile could be
    # any size at all, and at the world view the browser was fetching one huge
    # square before anything drew. Each tile is now held to TILE_BYTES.
    #
    # Nothing is dropped to get there. --cluster-densest-as-needed merges points
    # that sit on top of each other into one that carries point_count, which is
    # how the wide view already worked; a tighter budget only makes it merge
    # sooner. --no-feature-limit is gone with it: it allowed 200,000 features
    # into one tile, which is what made the tiles that size.
    # Points stop at POINTS_TO and outlines start above it, so no square in the
    # joined archive ever carries both layers. That matters because tile-join
    # has no size option of its own: it takes whatever its inputs give it, and
    # dropping rows to fit is exactly what must not happen here. Each builder
    # is held to TILE_BYTES on its own, and no square adds two of them together.
    # MapLibre reuses the last point square above POINTS_TO, so the counted
    # points still show where the outlines are drawing.
    # Every point at every zoom, none merged (asked for 23 September): no
    # clustering, and no size cap that would merge or drop points to fit.
    sh("tippecanoe", "-o", str(ptiles), "--force", "-q", "-Z0", f"-z{POINTS_TO}", "-r1", "-l", "mine_points",
       "--no-feature-limit", "--no-tile-size-limit", str(pts))
    otiles = work / "outlines.mbtiles"
    sh("tippecanoe", "-o", str(otiles), "--force", "-q", f"-Z{POINTS_TO + 1}", f"-z{OUTLINES_TO}", "-P", "-l", "mines",
       "--drop-densest-as-needed", "--extend-zooms-if-still-dropping", "--simplification=4",
       # tippecanoe's habit of folding outlines smaller than a pixel into one
       # stand-in square is off: a small mine keeps its own outline and its own box.
       "--no-tiny-polygon-reduction",
       f"--maximum-tile-bytes={TILE_BYTES}", str(polys))
    counted = census(otiles, polys)
    print(f"  biggest square \u2014 points {biggest(ptiles) / 1e3:.0f} kB, outlines {biggest(otiles) / 1e3:.0f} kB")
    parts = split(ptiles, otiles, work)
    STAMP.write_text(json.dumps({"tile_bytes": TILE_BYTES, "points_to": POINTS_TO, "zoom": OUTLINES_TO, "points_merged": False, "points_whole": True,
                                 "parts": parts, **counted}, indent=1))
    print("mines: built", OUT, "and", STAMP)


if __name__ == "__main__":
    main()
