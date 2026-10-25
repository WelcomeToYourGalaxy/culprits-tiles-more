#!/usr/bin/env python3
"""
Every UFO and UAP sighting in UFOSINT's public database, copied so the Culprits
map can draw them at every zoom.

UFOSINT (ufosint.com, github.com/UFOSINT) merges UFOCAT (CUFOS), UPDB
(PhenomAInon), Capella and UFO-search, which between them carry NUFORC, MUFON,
Blue Book, NICAP and other reports, into one SQLite file published with each
release:

  https://github.com/UFOSINT/ufosint-explorer/releases/latest/download/ufo_public.db

UFOSINT holds no licence from those sources; the owner chose to use it for now
(24 September), until NUFORC or CUFOS answer.

Made here:
  tiles/ufo_sightings.pmtiles (and, if one file would be over GitHub's limit,
  one file per zoom listed in tiles/ufo_sightings.build.json)
      layer "ufo_sightings"; since format 2 each point is the sightings at one
      spot in one year: y (the year, -9999 when undated), n (how many) and ids. x_precision = "locality" where UFOSINT placed it by matching
      the place name to a town (location.geocode_src set), so the map draws it
      hollow; a point with no x_precision is where the source itself put it.
  ufosint/pieces/<00-ff>.json.gz
      every field of every sighting, positioned or not, keyed by id, in 256
      pieces (FNV-1a over the id, as map/app.js pieceOf). A click reads one.

Nothing is filtered: every row is kept, duplicates included (UFOSINT flags them
but does not merge them). Rows with no position are in the pieces and counted
in the build list; they cannot be drawn. One column is left out:
witness_names, the names of private people.

Rebuilt only when UFOSINT publishes a new release (or with UFOSINT_REBUILD=1).
"""
import gzip, json, math, os, pathlib, re, shutil, sqlite3, subprocess, sys, tempfile, time, urllib.request

REPO = "https://github.com/UFOSINT/ufosint-explorer"
DB_URL = f"{REPO}/releases/latest/download/ufo_public.db"
ROW = "ufo_sightings"
OUT = pathlib.Path(f"tiles/{ROW}.pmtiles")
STAMP = OUT.with_suffix(".build.json")
PIECES = pathlib.Path("ufosint/pieces")
SHARDS = 256
MAXZOOM = 10
LIMIT = 95 * 1024 * 1024
LEFT_OUT = {"witness_names"}
# Format 2 (24 September): the sightings reported at the same spot in the same
# year are one point of the tiles, carrying how many (n), their year (y) and
# their ids, so the world view is a fifth of the size it was and the map's year
# bar can filter by year. Nothing is dropped: every sighting is in its point.
FORMAT = 3
# Format 3 (26 September, round 59): the owner found the points slow to load.
# With every spot in every tile down to the world view, the world tile held all
# 227,000 spots and their ids. Now the wide views draw sightings summed into
# squares (BANDS), still by year so the year bar works, each square at the
# middle of its own sightings rather than at the square's centre; from zoom
# DETAIL_FROM every spot is drawn as before, with its ids. Nothing is dropped:
# the squares' counts add up to every sighting, and zooming in shows each one.
BANDS = [(0, 1, 2.0), (2, 3, 0.5), (4, 5, 0.1)]      # zooms from, to; square size in degrees
DETAIL_FROM = 6
UNDATED = -9999
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}


def sh(*cmd, **kw):
    print("  $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def tools():
    if shutil.which("tippecanoe"):
        return
    sh("sudo", "apt-get", "update", "-qq")
    sh("sudo", "apt-get", "install", "-y", "-qq", "libsqlite3-dev", "zlib1g-dev", "build-essential")
    d = tempfile.mkdtemp()
    sh("git", "clone", "--depth", "1", "https://github.com/felt/tippecanoe.git", d)
    sh("make", "-j4", cwd=d)
    sh("sudo", "make", "install", cwd=d)


def shard(key):
    """Which of the 256 pieces a sighting is in: FNV-1a over its id, as two hex
    digits. map/app.js pieceOf has the same function; the two must agree."""
    h = 0x811C9DC5
    for b in str(key).encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h % SHARDS:02x}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def latest_tag():
    """The release 'latest' points at, read from GitHub's redirect."""
    op = urllib.request.build_opener(NoRedirect)
    try:
        op.open(urllib.request.Request(f"{REPO}/releases/latest", headers=UA, method="HEAD"), timeout=60)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") or ""
        m = re.search(r"/tag/([^/?#]+)", loc)
        if m:
            return m.group(1)
    return None


def download(to):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(DB_URL, headers=UA), timeout=600) as r, open(to, "wb") as fo:
                got = 0
                while True:
                    b = r.read(1 << 22)
                    if not b:
                        break
                    fo.write(b)
                    got += len(b)
                    if got % (100 << 20) < (1 << 22):
                        print(f"    {got / 1e6:,.0f} MB", flush=True)
            return
        except Exception as e:  # noqa: BLE001
            if i == 3:
                raise
            print(f"    download stopped ({e}); again in {20 * (i + 1)}s", flush=True)
            time.sleep(20 * (i + 1))


def cols(con, table):
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def plain(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v


def main():
    tag = latest_tag()
    try:
        old = json.loads(STAMP.read_text()) if STAMP.exists() else {}
    except Exception:  # noqa: BLE001
        old = {}
    if tag and old.get("release") == tag and old.get("format") == FORMAT and not os.environ.get("UFOSINT_REBUILD"):
        print(f"ufosint: release {tag} already copied; nothing to do")
        return
    work = pathlib.Path(tempfile.mkdtemp())
    db = work / "ufo_public.db"
    if os.environ.get("UFOSINT_DB"):
        shutil.copy(os.environ["UFOSINT_DB"], db)
    else:
        print(f"ufosint: downloading release {tag or '(latest)'}", flush=True)
        download(db)
    con = sqlite3.connect(str(db))
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "sighting" not in tables:
        sys.exit("ufosint: the file has no sighting table; the last copy stays")

    s_cols = [c for c in cols(con, "sighting") if c not in LEFT_OUT]
    sel = [f's."{c}" AS "{c}"' for c in s_cols]
    joins = []
    if "source_database" in tables and "source_db_id" in s_cols:
        sel.append('sd.name AS "source_database"')
        joins.append("LEFT JOIN source_database sd ON sd.id = s.source_db_id")
    if "source_origin" in tables and "origin_id" in s_cols:
        sel.append('so.name AS "upstream_source"')
        joins.append("LEFT JOIN source_origin so ON so.id = s.origin_id")
    if "location" in tables and "location_id" in s_cols:
        for c in cols(con, "location"):
            if c != "id":
                sel.append(f'l."{c}" AS "location_{c}"')
        joins.append("LEFT JOIN location l ON l.id = s.location_id")
    if "sighting_analysis" in tables:
        for c in cols(con, "sighting_analysis"):
            if c not in ("id", "sighting_id"):
                sel.append(f'sa."{c}" AS "analysis_{c}"')
        joins.append("LEFT JOIN sighting_analysis sa ON sa.sighting_id = s.id")

    # Possible duplicates, where the file carries UFOSINT's pairs (the public
    # file of v0.17 does not). Kept as a field; nothing is merged or dropped.
    dups = {}
    if "duplicate_candidate" in tables:
        for a, b in con.execute("SELECT sighting_id_a, sighting_id_b FROM duplicate_candidate"):
            dups.setdefault(a, []).append(b)
            dups.setdefault(b, []).append(a)

    lat_c = "lat" if "lat" in s_cols else ("location_latitude" if "location" in tables else None)
    lng_c = "lng" if "lng" in s_cols else ("location_longitude" if "location" in tables else None)
    q = f"SELECT {', '.join(sel)} FROM sighting s {' '.join(joins)} ORDER BY s.id"
    cur = con.execute(q)
    names = [d[0] for d in cur.description]
    # The pieces are written as the rows are read, one gzip stream each, so the
    # 700,000 records are never all held in memory at once.
    staged = work / "pieces"
    staged.mkdir()
    streams, first = {}, {}

    def put(key, rec):
        hh = shard(key)
        if hh not in streams:
            fo = open(staged / f"{hh}.json.gz", "wb")
            streams[hh] = (fo, gzip.GzipFile(fileobj=fo, mode="wb", mtime=0, compresslevel=9))
            streams[hh][1].write(b"{")
            first[hh] = True
        gz = streams[hh][1]
        if not first[hh]:
            gz.write(b",")
        first[hh] = False
        gz.write(json.dumps(str(key)).encode() + b":" + json.dumps({"properties": rec}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    lines = work / "points.geojsonl"
    total = placed = named = 0
    by_source = {}
    spots = {}
    with open(lines, "w", encoding="utf-8") as fo:
        for row in cur:
            r = {k: plain(v) for k, v in zip(names, row) if v is not None and v != ""}
            sid = r.get("id")
            total += 1
            if sid in dups:
                r["possible_duplicates (UFOSINT ids)"] = ", ".join(str(x) for x in sorted(dups[sid]))
            src = r.get("source_database") or ""
            by_source[src] = by_source.get(src, 0) + 1
            when = r.get("date_event") or r.get("date_event_raw") or "undated"
            where = r.get("location_raw_text") or ", ".join(str(r[k]) for k in ("location_city", "location_state", "location_country") if r.get(k)) or "place not given"
            title = f"{when} · {where}"
            r["title"] = title
            put(sid, r)
            y, x = r.get(lat_c), r.get(lng_c)
            try:
                x, y = float(x), float(y)
            except (TypeError, ValueError):
                continue
            if not (-180 <= x <= 180 and -90 <= y <= 90):
                continue
            m = re.match(r"(-?\d{1,4})\b", str(r.get("date_event") or ""))
            yr = int(m.group(1)) if m else UNDATED
            geo = bool(r.get("location_geocode_src"))
            if geo:
                named += 1
            spots.setdefault((round(x, 5), round(y, 5), yr, geo), []).append(sid)
            placed += 1
            if total % 100000 == 0:
                print(f"    {total:,} read, {placed:,} placed", flush=True)
        years = [k[2] for k in spots if k[2] != UNDATED]
        for (x, y, yr, geo), ids in spots.items():
            props = {"y": yr, "n": len(ids), "ids": ",".join(str(i) for i in ids)}
            if geo:
                props["x_precision"] = "locality"
            fo.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]},
                                 "properties": props}, separators=(",", ":")) + "\n")
    con.close()
    db.unlink()
    for fo, gz in streams.values():
        gz.write(b"}")
        gz.close()
        fo.close()
    if not placed:
        sys.exit("ufosint: no sighting had a position; the last copy stays")
    print(f"ufosint: {total:,} sightings, {placed:,} with a position ({named:,} of them placed by UFOSINT from the place name)", flush=True)

    tools()
    parts = []
    # The wide views: sightings summed by square and year.
    for lo, hi, cell in BANDS:
        sq = {}
        for (x, y, yr, geo), ids in spots.items():
            k = (math.floor(x / cell), math.floor(y / cell), yr)
            a = sq.setdefault(k, [0, 0.0, 0.0, 0])
            n = len(ids)
            a[0] += n; a[1] += x * n; a[2] += y * n; a[3] += n if geo else 0
        band = work / f"band{lo}.geojsonl"
        with open(band, "w", encoding="utf-8") as fo:
            for (gx, gy, yr), (n, sx, sy, named_n) in sq.items():
                props = {"y": yr, "n": n, "sq": 1}
                if named_n:
                    props["placed_from_place_name"] = named_n
                fo.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(sx / n, 5), round(sy / n, 5)]},
                                     "properties": props}, separators=(",", ":")) + "\n")
        name = OUT.name if lo == 0 else f"{ROW}_z{lo}.pmtiles"
        p = work / name
        sh("tippecanoe", "-o", str(p), "--force", "-q", f"-Z{lo}", f"-z{hi}", "-r1", "-l", ROW, "--name", ROW,
           "--no-feature-limit", "--no-tile-size-limit", str(band))
        print(f"  zooms {lo}-{hi}: {len(sq):,} squares, {p.stat().st_size / 1e6:.1f} MB", flush=True)
        parts.append({"file": name, "from": lo, "to": hi, "bytes": p.stat().st_size, "_path": p})
    # Close in: every spot, with its ids, as before.
    one = work / f"{ROW}_z{DETAIL_FROM}.pmtiles"
    sh("tippecanoe", "-o", str(one), "--force", "-q", f"-Z{DETAIL_FROM}", f"-z{MAXZOOM}", "-r1", "-l", ROW, "--name", ROW,
       "--no-feature-limit", "--no-tile-size-limit", "--preserve-input-order", str(lines))
    if one.stat().st_size <= LIMIT:
        parts.append({"file": one.name, "from": DETAIL_FROM, "to": MAXZOOM, "bytes": one.stat().st_size, "_path": one})
    else:
        print(f"  one file is {one.stat().st_size / 1e6:.0f} MB; one file per zoom instead", flush=True)
        one.unlink()
        for z in range(DETAIL_FROM, MAXZOOM + 1):
            name = f"{ROW}_z{z}.pmtiles"
            p = work / name
            sh("tippecanoe", "-o", str(p), "--force", "-q", f"-Z{z}", f"-z{z}", "-r1", "-l", ROW, "--name", ROW,
               "--no-feature-limit", "--no-tile-size-limit", "--preserve-input-order", str(lines))
            size = p.stat().st_size
            print(f"  zoom {z}: {size / 1e6:.1f} MB", flush=True)
            if size > LIMIT:
                sys.exit(f"ufosint: zoom {z} alone is over GitHub's limit; the last copy stays")
            parts.append({"file": name, "from": z, "to": z, "bytes": size, "_path": p})

    # The pieces: replaced whole, since UFOSINT renumbers its ids each release,
    # and only now that the tiles have been made.
    if PIECES.exists():
        shutil.rmtree(PIECES)
    PIECES.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(staged), str(PIECES))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for old_part in OUT.parent.glob(f"{ROW}_z*.pmtiles"):
        old_part.unlink()
    for p in parts:
        shutil.move(str(p.pop("_path")), str(OUT.parent / p["file"]))
    info = {"release": tag, "rows": total, "alerts_with_position": placed, "no_position": total - placed,
            "placed_from_place_name": named, "by_source_database": by_source,
            "points_merged": "only sightings at the same spot in the same year", "spots": len(spots), "format": FORMAT,
            "years": [min(years), max(years)] if years else None,
            "undated_with_position": sum(len(v) for k, v in spots.items() if k[2] == UNDATED),
            "left_out_columns": sorted(LEFT_OUT), "source": DB_URL}
    info["parts"] = parts
    info["squares"] = [{"zooms": [lo, hi], "degrees": cell} for lo, hi, cell in BANDS]
    info["detail_from"] = DETAIL_FROM
    STAMP.write_text(json.dumps(info, indent=1))
    print(f"ufosint: {placed:,} drawn and {total - placed:,} without a position, from release {tag}; "
          f"{len(parts)} tile file(s), {len(streams)} pieces")


if __name__ == "__main__":
    main()
