#!/usr/bin/env python3
"""
A daily archive of Cerulean's oil slicks (SkyTruth), so every slick stays on the
map by month even when Cerulean's own service is slow, down or changes.

Each run reads the slicks from the last 3 days and adds any new ones to that
month's store, keeping everything already archived:

  cerulean_archive/<year-month>/<date>.geojson.gz   each day's slicks, every field (the store)
  cerulean_archive/<year-month>*.pmtiles     the month drawn as tiles: layer "slicks"
                                             (shapes, zoom 7 in) and "slick_points"
                                             (one point per slick, the world view to 6),
                                             each slick carrying its id and time only
  cerulean_archive/tiles.json                which archive(s) hold each month
  cerulean_archive/index.json                the months and how many slicks each holds

Before 23 September the store was plain GeoJSON. A busy month passed GitHub's
95 MB cut and was left out of every save, so August and July were lost and
September was close. The store is now gzipped (a tenth of the size), and the
map reads each month's tiles, square by square. A month the index lists with
no store (lost that way) is read again from Cerulean a day at a time, saved
as it goes, and carried on by the next run where it stopped (refill.json).
Nothing is filtered: every slick is kept, with every field, in the store.

23 September, second run: a whole month gzipped was still over 95 MB (July
and August, about 49,000 slicks each), and a month's tiles with every field
came to 750 MB. So the store is kept a day to a file, and the tiles carry
only each slick's id and time; the map reads the rest from Cerulean by id on
a click. A month whose tiles still pass the limit is drawn to zoom 9 rather than 10,
then split by date into several files; nothing is left out.
"""
import datetime as dt, gzip, json, pathlib, subprocess, sys, tempfile, time, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

API = "https://api.cerulean.skytruth.org/collections/public.slick_plus/items"
OUT = pathlib.Path("cerulean_archive")


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


def read_window(since, until, max_pages=400):
    url = API + "?" + urllib.parse.urlencode({"datetime": f"{since}/{until}", "limit": 1000})
    got, pages = [], 0
    while url and pages < max_pages:
        try:
            page = get(url)
        except Exception as e:  # noqa: BLE001
            print(f"cerulean archive: stopped after {len(got)} slicks for {since[:10]}..{until[:10]} ({e})", file=sys.stderr)
            break
        got.extend(page.get("features") or [])
        url = next((l.get("href") for l in page.get("links") or [] if l.get("rel") == "next"), None)
        pages += 1
    return got


def month_of(f):
    p = f.get("properties") or {}
    return str(p.get("slick_timestamp") or p.get("datetime") or "")[:7]


def key_of(f):
    return str((f.get("properties") or {}).get("id", f.get("id")))


def day_of(f):
    p = f.get("properties") or {}
    return str(p.get("slick_timestamp") or p.get("datetime") or "")[:10]


def read_gz(path):
    return json.loads(gzip.decompress(path.read_bytes()))["features"]


def write_gz(path, feats):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps({"type": "FeatureCollection", "features": feats},
                                              separators=(",", ":")).encode("utf-8"), 9, mtime=0))


def load(month):
    """The month's slicks from its day files; None if the month has no store."""
    days = sorted((OUT / month).glob("*.geojson.gz")) if (OUT / month).is_dir() else []
    if not days:
        return None
    out = []
    for d in days:
        out += read_gz(d)
    return out


def save_days(feats):
    """Merge feats into their day files; returns (new, months touched)."""
    by_day, new, months = {}, 0, set()
    for f in feats:
        d = day_of(f)
        if len(d) == 10:
            by_day.setdefault(d, []).append(f)
    for d, fs in by_day.items():
        path = OUT / d[:7] / f"{d}.geojson.gz"
        have = read_gz(path) if path.exists() else []
        ids = {key_of(x) for x in have}
        added = [f for f in fs if key_of(f) not in ids and not ids.add(key_of(f))]
        if added or not path.exists():
            write_gz(path, have + added)
        new += len(added)
        months.add(d[:7])
    return new, months


def migrate():
    """A month kept whole (plain or gzipped, before 23 September) is split into day files."""
    for old in list(OUT.glob("????-??.geojson.gz")) + list(OUT.glob("????-??.geojson")):
        feats = read_gz(old) if old.suffix == ".gz" else json.loads(old.read_text(encoding="utf-8"))["features"]
        save_days(feats)
        old.unlink()
        print(f"cerulean archive: {old.name} split into day files", flush=True)


def middle(geom):
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
    return [round(sum(p[0] for p in pts) / len(pts), 5), round(sum(p[1] for p in pts) / len(pts), 5)]


def tile(month, feats, part=""):
    """The month (or part of it) as tiles; returns the file names made, or [] if none fit."""
    import mines
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    polys, pts = work / "slicks.geojsonl", work / "points.geojsonl"
    with open(polys, "w", encoding="utf-8") as fp, open(pts, "w", encoding="utf-8") as fq:
        for f in feats:
            g = f.get("geometry")
            if not g:
                continue
            props = {"id": key_of(f), "t": str((f.get("properties") or {}).get("slick_timestamp") or "")}
            fp.write(json.dumps({"type": "Feature", "geometry": g, "properties": props, "tippecanoe": {"minzoom": 7}}) + "\n")
            c = middle(g)
            if c:
                fq.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": c},
                                     "properties": props, "tippecanoe": {"maxzoom": 6}}) + "\n")
    dest = OUT / f"{month}{part}.pmtiles"
    # Every slick at every zoom, none merged or dropped; shapes to zoom 10 where
    # that fits, the map enlarging the deepest squares closer in.
    # Shapes are wanted closer in than zoom 9, so a month is split by date
    # before it is drawn any shallower.
    for top in (10, 9):
        mines.sh("tippecanoe", "-o", str(dest), "--force", "-q", "-Z0", f"-z{top}", "-r1",
                 "--no-feature-limit", "--no-tile-size-limit", "--no-tiny-polygon-reduction",
                 "-L", f"slicks:{polys}", "-L", f"slick_points:{pts}")
        size = dest.stat().st_size
        print(f"cerulean archive: {month}{part} to zoom {top}: {len(feats):,} slicks, {size / 1e6:.1f} MB", flush=True)
        if size <= 95e6:
            return [dest.name]
    dest.unlink()
    # Still too big: the dates are split in two and each half is tiled on its own.
    days = sorted({day_of(f) for f in feats})
    if len(days) < 2:
        print(f"cerulean archive: {month}{part} is one day and still over GitHub's limit; left as its store only", file=sys.stderr)
        return []
    half = days[len(days) // 2]
    early = [f for f in feats if day_of(f) < half]
    late = [f for f in feats if day_of(f) >= half]
    return tile(month, early, f"{part}_{days[0][8:]}") + tile(month, late, f"{part}_{half[8:]}")


BUDGET_S = 100 * 60   # the refresh job is stopped at 160 minutes; leave room to tile and save


def by_month(feats):
    out = {}
    for f in feats:
        mo = month_of(f)
        if len(mo) == 7 and f.get("geometry"):
            f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
            out.setdefault(mo, []).append(f)
    return out


def main():
    started = time.time()
    OUT.mkdir(exist_ok=True)
    index = json.loads((OUT / "index.json").read_text()) if (OUT / "index.json").exists() else {}
    tiled = json.loads((OUT / "tiles.json").read_text()) if (OUT / "tiles.json").exists() else {}
    refill_path = OUT / "refill.json"
    refill = json.loads(refill_path.read_text()) if refill_path.exists() else {}
    now = dt.datetime.utcnow()
    first = not index
    changed, added = set(), 0
    migrate()
    since = (now - dt.timedelta(days=60 if first else 3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for mo, feats in by_month(read_window(since, now.strftime("%Y-%m-%dT%H:%M:%SZ"))).items():
        n, months = save_days(feats)
        added += n
        changed |= months
        index.setdefault(mo, 0)
    # A month the index lists with no store was lost to the size cut (August and
    # July 2026). It is read again a day at a time, saved after each day, and
    # picked up where it stopped on the next run: the first try read a whole
    # month in one go and the job was stopped before it could save anything.
    for mo in sorted(index):
        if load(mo) is None and mo not in refill:
            refill[mo] = f"{mo}-01"
    # A month with days missing from its store is read again from the first
    # missing day (23 September: September's store began on the 17th, the day
    # the archive's first copy was made, so the 1st to the 16th were never kept).
    # A month found whole is noted in whole.json and not looked at again.
    whole_path = OUT / "whole.json"
    whole = set(json.loads(whole_path.read_text())) if whole_path.exists() else set()
    for mo in sorted(index):
        if mo in whole or mo in refill or load(mo) is None:
            continue
        y, m = map(int, mo.split("-"))
        last = min(dt.datetime(y + (m == 12), (m % 12) + 1, 1), now.replace(hour=0, minute=0, second=0, microsecond=0))
        d, missing = dt.datetime(y, m, 1), None
        while d < last:
            if not (OUT / mo / f"{d:%Y-%m-%d}.geojson.gz").exists():
                missing = d
                break
            d += dt.timedelta(days=1)
        if missing:
            refill[mo] = f"{missing:%Y-%m-%d}"
            print(f"cerulean archive: {mo} has no store from {refill[mo]}; reading it again from there", flush=True)
        elif mo < f"{now:%Y-%m}":          # a past month with every day kept
            whole.add(mo)
    for mo in sorted(refill):
        day = dt.datetime.strptime(refill[mo], "%Y-%m-%d")
        y, m = map(int, mo.split("-"))
        end = min(dt.datetime(y + (m == 12), (m % 12) + 1, 1), now)
        while day < end and time.time() - started < BUDGET_S:
            nxt = day + dt.timedelta(days=1)
            got = by_month(read_window(day.strftime("%Y-%m-%dT%H:%M:%SZ"), nxt.strftime("%Y-%m-%dT%H:%M:%SZ")))
            for m2, feats in got.items():
                n, months = save_days(feats)
                added += n
                changed |= months
                index.setdefault(m2, 0)
            day = nxt
            refill[mo] = day.strftime("%Y-%m-%d")
            refill_path.write_text(json.dumps(refill), encoding="utf-8")
            print(f"cerulean archive: {mo} read again up to {refill[mo]}", flush=True)
        if day >= end:
            del refill[mo]
            if mo < f"{now:%Y-%m}":
                whole.add(mo)
            print(f"cerulean archive: {mo} read again in full", flush=True)
        else:
            print(f"cerulean archive: {mo} read again up to {refill[mo]}; the next run carries on from there", flush=True)
            break
    refill_path.write_text(json.dumps(refill), encoding="utf-8")
    whole_path.write_text(json.dumps(sorted(whole)), encoding="utf-8")
    for month in sorted(set(index)):
        feats = load(month) if (month in changed or month not in tiled) else None
        if feats is not None:
            index[month] = len(feats)
        if month in refill:
            continue          # tiled once the whole month is back
        have = [tiled[month]] if isinstance(tiled.get(month), str) else (tiled.get(month) or [])
        if month in changed or not have or not all((OUT / n).exists() for n in have):
            feats = feats if feats is not None else load(month)
            if feats:
                for old in OUT.glob(f"{month}*.pmtiles"):
                    old.unlink()
                names = tile(month, feats)
                if names:
                    tiled[month] = names if len(names) > 1 else names[0]
    (OUT / "index.json").write_text(json.dumps(dict(sorted(index.items(), reverse=True))), encoding="utf-8")
    (OUT / "tiles.json").write_text(json.dumps(dict(sorted(tiled.items(), reverse=True))), encoding="utf-8")
    print(f"cerulean archive: {added} new, {len(index)} months kept, {len(tiled)} tiled, {len(refill)} still being read again")


if __name__ == "__main__":
    main()
