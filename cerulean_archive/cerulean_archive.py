#!/usr/bin/env python3
"""
A daily archive of Cerulean's oil slicks (SkyTruth), so every slick stays on the
map by month even when Cerulean's own service is slow, down or changes. Each run
reads the slicks from the last 3 days (the first run reads the last 60) and adds
any new ones to cerulean_archive/<year-month>.geojson, keeping everything
already archived. cerulean_archive/index.json lists the months and counts.
Each month it touches is also tiled into cerulean_archive/tiles/<month>.pmtiles
(layers "slicks" and "slick_points"), listed in cerulean_archive/tiles.json,
because a busy month is about 58 MB of GeoJSON and the map could not read it
whole. Months already tiled and unchanged are left alone. The plain .geojson
files stay: they are the archive, and the map still reads them for any month
that has no tiles yet.
"""
import datetime as dt, json, pathlib, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request

API = "https://api.cerulean.skytruth.org/collections/public.slick_plus/items"
OUT = pathlib.Path("cerulean_archive")
TILES = OUT / "tiles"
LIMIT = 95 * 1024 * 1024          # GitHub refuses files over 100 MB


def sh(*cmd, **kw):
    print("  $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def tools():
    if not shutil.which("tippecanoe"):
        sh("sudo", "apt-get", "update", "-qq")
        sh("sudo", "apt-get", "install", "-y", "-qq", "libsqlite3-dev", "zlib1g-dev", "build-essential")
        d = tempfile.mkdtemp()
        sh("git", "clone", "--depth", "1", "https://github.com/felt/tippecanoe.git", d)
        sh("make", "-j4", cwd=d)
        sh("sudo", "make", "install", cwd=d)


def middle(geom):
    """A point inside the slick: the average of its corners."""
    pts = []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            pts.append(c)
        else:
            for x in c:
                walk(x)

    walk(geom.get("coordinates") or [])
    if not pts:
        return None
    return [sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)]


def tile_month(month, feats, work):
    """One archive per month: the shapes from zoom 7, a point per slick below it."""
    shapes = work / f"{month}.shapes.geojsonl"
    points = work / f"{month}.points.geojsonl"
    with open(shapes, "w", encoding="utf-8") as fs, open(points, "w", encoding="utf-8") as fp:
        for f in feats:
            if not f.get("geometry"):
                continue
            fs.write(json.dumps(f, separators=(",", ":")) + "\n")
            at = middle(f["geometry"])
            if at:
                fp.write(json.dumps({"type": "Feature", "properties": f.get("properties") or {},
                                     "geometry": {"type": "Point", "coordinates": at}}, separators=(",", ":")) + "\n")
    st, pt = work / f"{month}.s.mbtiles", work / f"{month}.p.mbtiles"
    sh("tippecanoe", "-o", str(pt), "--force", "-q", "-Z0", "-z6", "-r1", "-l", "slick_points",
       "--cluster-densest-as-needed", "--no-feature-limit", str(points))
    out = TILES / f"{month}.pmtiles"
    TILES.mkdir(parents=True, exist_ok=True)
    for maxz in (12, 11, 10, 9):
        sh("tippecanoe", "-o", str(st), "--force", "-q", "-Z7", f"-z{maxz}", "-P", "-l", "slicks",
           "--drop-densest-as-needed", "--extend-zooms-if-still-dropping", str(shapes))
        sh("tile-join", "-o", str(out), "--force", "-q", str(pt), str(st))
        if out.stat().st_size <= LIMIT:
            return out
        print(f"  {month}: {out.stat().st_size / 1e6:.1f} MB at zoom {maxz}; trying one lower")
    # Still over the cap: the month keeps its plain file and is not listed as
    # tiled, so the map reads it the old way rather than a broken archive.
    out.unlink(missing_ok=True)
    return None


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Culprits atlas daily archive", "Accept": "application/geo+json"})
    for i in range(3):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=180).read())
        except Exception:  # noqa: BLE001
            if i == 2:
                raise
            time.sleep(10)


def rnd(c):
    return [rnd(x) for x in c] if isinstance(c, list) and c and isinstance(c[0], list) else [round(x, 5) for x in c] if isinstance(c, list) else c


def main():
    OUT.mkdir(exist_ok=True)
    first = not (OUT / "index.json").exists()
    since = (dt.datetime.utcnow() - dt.timedelta(days=60 if first else 3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now = dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    url = API + "?" + urllib.parse.urlencode({"datetime": f"{since}/{now}", "limit": 1000})
    new, pages = [], 0
    while url and pages < 200:
        try:
            page = get(url)
        except Exception as e:  # noqa: BLE001
            print(f"cerulean archive: stopped after {len(new)} slicks ({e})", file=sys.stderr)
            break
        new.extend(page.get("features") or [])
        url = next((l.get("href") for l in page.get("links") or [] if l.get("rel") == "next"), None)
        pages += 1
    by_month = {}
    for f in new:
        p = f.get("properties") or {}
        stamp = str(p.get("slick_timestamp") or p.get("datetime") or "")[:7]
        if len(stamp) == 7 and f.get("geometry"):
            f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
            by_month.setdefault(stamp, []).append(f)
    index = json.loads((OUT / "index.json").read_text()) if not first else {}
    added, touched = 0, {}
    for month, feats in by_month.items():
        path = OUT / f"{month}.geojson"
        have = json.loads(path.read_text())["features"] if path.exists() else []
        ids = {str((x.get("properties") or {}).get("id", x.get("id"))) for x in have}
        for f in feats:
            key = str((f.get("properties") or {}).get("id", f.get("id")))
            if key not in ids:
                have.append(f)
                ids.add(key)
                added += 1
        path.write_text(json.dumps({"type": "FeatureCollection", "features": have}, separators=(",", ":")), encoding="utf-8")
        index[month] = len(have)
        touched[month] = have
    (OUT / "index.json").write_text(json.dumps(dict(sorted(index.items(), reverse=True))), encoding="utf-8")

    # Tiling. Months this run changed, plus any month that has never been
    # tiled, so the first run after this lands catches up the whole archive.
    tiles = json.loads((OUT / "tiles.json").read_text()) if (OUT / "tiles.json").exists() else {}
    todo = dict(touched)
    for month in index:
        if month in tiles or month in todo:
            continue
        path = OUT / f"{month}.geojson"
        if path.exists():
            todo[month] = json.loads(path.read_text())["features"]
    if todo:
        try:
            tools()
            work = pathlib.Path(tempfile.mkdtemp())
            for month, feats in sorted(todo.items(), reverse=True):
                built = tile_month(month, feats, work)
                if built:
                    tiles[month] = f"tiles/{month}.pmtiles"
                    print(f"  {month}: {len(feats):,} slicks, {built.stat().st_size / 1e6:.1f} MB")
                else:
                    tiles.pop(month, None)
                    print(f"  {month}: too big to tile under the file cap; its plain file stays")
        except Exception as e:  # noqa: BLE001
            # A tiling failure must not cost the archive itself, which is
            # already written above; the map falls back to the plain files.
            print(f"cerulean archive: could not tile ({e})", file=sys.stderr)
    (OUT / "tiles.json").write_text(json.dumps(dict(sorted(tiles.items(), reverse=True))), encoding="utf-8")
    print(f"cerulean archive: {len(new)} slicks read, {added} new, {len(index)} months kept, {len(tiles)} tiled")


if __name__ == "__main__":
    main()
