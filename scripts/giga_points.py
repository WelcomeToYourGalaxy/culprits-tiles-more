#!/usr/bin/env python3
"""
Every school Giga has mapped, as the Culprits map's own copy (round 112b,
asked 29 September: "The every school Giga has mapped layer loads too slow").

The row drew Giga's live tiles (giga/schools_tiles.json, written daily by
giga_schools.py). Giga makes each square on request and a square of the
world view weighs about 1.5 MB, so the row took long to appear. This reads
those same tiles once, square by square, and writes them as archives the map
reads from GitHub Pages:

  1. zoom 4 squares (256) to find where there are schools, then every zoom 7
     square inside those (each school's position to about 75 m, the zoom 7
     square's own grid);
  2. every school kept once, with every field Giga's tiles give it;
  3. wider out (zooms 0 to 7) one mark per square of 2, 0.5, 0.1 or 0.02
     degrees with how many schools it holds and how many of each connectivity
     status, coloured by the status most of them have; from zoom 8 each
     school, in west-to-east strips where one file would pass GitHub's limit.

  tiles/giga_points.pmtiles (and giga_points_z*.pmtiles where one file would
  pass GitHub's limit)   layer "schools"
  tiles/giga_points.build.json   the parts, counts, fields seen, date

Weekly (Mondays) or by hand; GIGA_AGAIN=1 reads every square again.
"""
import datetime, json, math, os, pathlib, subprocess, sys, tempfile, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
OUT = pathlib.Path("tiles/giga_points.pmtiles")
STAMP = OUT.with_suffix(".build.json")
SRC = pathlib.Path("giga/schools_tiles.json")
LIMIT = 90 * 1024 * 1024
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
FIELD = "connectivity_status"
SQUARES = [((0, 1), 2.0), ((2, 3), 0.5), ((4, 5), 0.1), ((6, 7), 0.02)]
DETAIL = 8   # each school from this zoom; the map enlarges it beyond


def get(url, tries=5):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(4 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def lonlat(z, x, y, gx, gy, extent):
    n = 2 ** z
    lon = (x + gx / extent) / n * 360 - 180
    t = math.pi * (1 - 2 * (y + gy / extent) / n)
    return round(lon, 6), round(math.degrees(math.atan(math.sinh(t))), 6)


def points_of(tile, z, x, y):
    import mapbox_vector_tile
    d = mapbox_vector_tile.decode(tile, default_options={"y_coord_down": True})
    out = []
    for lname, layer in d.items():
        ext = layer.get("extent", 4096)
        for f in layer.get("features", []):
            g = f.get("geometry") or {}
            pts = [g["coordinates"]] if g.get("type") == "Point" else g.get("coordinates", []) if g.get("type") == "MultiPoint" else []
            for gx, gy in pts:
                lon, lat = lonlat(z, x, y, gx, gy, ext)
                out.append((lon, lat, dict(f.get("properties") or {}, **({"_layer": lname} if len(d) > 1 else {}))))
    return out


def main():
    if STAMP.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" \
            and not os.environ.get("GIGA_AGAIN"):
        print("giga_points: weekly; not Monday")
        return
    if not SRC.exists():
        sys.exit("giga_points: giga/schools_tiles.json is missing; run giga_schools first")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "mapbox-vector-tile"], check=True)
    import mines
    mines.tools()
    tpl = json.loads(SRC.read_text())["tiles"]
    url = lambda z, x, y: tpl.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
    t0 = time.time()

    def fetch(zxy):
        z, x, y = zxy
        try:
            b = get(url(z, x, y))
            return zxy, b, None
        except Exception as e:  # noqa: BLE001
            return zxy, None, str(e)

    failed = []
    have4 = []
    with ThreadPoolExecutor(12) as ex:
        for (z, x, y), b, err in ex.map(fetch, [(4, x, y) for x in range(16) for y in range(16)]):
            if err:
                failed.append(f"{z}/{x}/{y}: {err}")
            elif b and len(b) > 30:
                have4.append((x, y))
    print(f"giga_points: {len(have4)} zoom 4 squares hold schools ({time.time() - t0:.0f} s)", flush=True)
    todo = [(7, x * 8 + dx, y * 8 + dy) for x, y in have4 for dx in range(8) for dy in range(8)]
    seen, schools, fields = set(), [], {}
    idkey = None
    done = 0
    with ThreadPoolExecutor(12) as ex:
        for (z, x, y), b, err in ex.map(fetch, todo):
            done += 1
            if err:
                failed.append(f"{z}/{x}/{y}: {err}")
                continue
            if b and len(b) > 30:
                for lon, lat, p in points_of(b, z, x, y):
                    if idkey is None:
                        idkey = next((k for k in ("giga_id_school", "school_id", "id", "school_id_giga") if k in p), "")
                    k = str(p.get(idkey)) if idkey and p.get(idkey) is not None else f"{lon},{lat},{p.get('name', '')}"
                    if k in seen:
                        continue
                    seen.add(k)
                    for f in p:
                        fields[f] = fields.get(f, 0) + 1
                    schools.append((lon, lat, p))
            if done % 1000 == 0:
                print(f"  {done:,} of {len(todo):,} squares, {len(schools):,} schools, {time.time() - t0:.0f} s", flush=True)
    if not schools:
        sys.exit(f"giga_points: no schools read; {len(failed)} squares failed: {failed[:5]}")
    print(f"giga_points: {len(schools):,} schools; fields {fields}; {len(failed)} squares failed", flush=True)

    work = pathlib.Path(tempfile.mkdtemp())
    detail = work / "schools.ndjson"
    with detail.open("w") as w:
        for lon, lat, p in schools:
            w.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": p}, ensure_ascii=False) + "\n")
    runs = []
    # Wider out: one mark per square with its counts.
    for (z0, z1), deg in SQUARES:
        sq = {}
        for lon, lat, p in schools:
            k = (math.floor(lon / deg), math.floor(lat / deg))
            e = sq.setdefault(k, {"n": 0, "by": {}, "x": 0.0, "y": 0.0})
            e["n"] += 1
            e["x"] += lon
            e["y"] += lat
            s = str(p.get(FIELD, "unknown"))
            e["by"][s] = e["by"].get(s, 0) + 1
        f = work / f"sq{z0}.ndjson"
        with f.open("w") as w:
            for e in sq.values():
                top = max(e["by"].items(), key=lambda kv: kv[1])[0]
                props = {"schools": e["n"], FIELD: top, **{f"{k.replace('_', ' ')}": v for k, v in sorted(e["by"].items())}}
                w.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(e["x"] / e["n"], 5), round(e["y"] / e["n"], 5)]},
                                    "properties": props}) + "\n")
        runs.append(((z0, z1), f, False))
    runs.append(((DETAIL, DETAIL), detail, True))
    OUT.parent.mkdir(exist_ok=True)
    for old in OUT.parent.glob("giga_points_z*.pmtiles"):
        old.unlink()
    built = []

    def tip(src, lo, hi, out):
        mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", "schools", f"-Z{lo}", f"-z{hi}", "-r1",
                 "--no-feature-limit", "--no-tile-size-limit", str(src))
        return out.stat().st_size

    def place(src, lo, hi):
        out = work / f"part{lo}.pmtiles"
        size = tip(src, lo, hi, out)
        if size <= LIMIT:
            built.append((lo, hi, out, None))
            return
        if lo < hi:
            mid = (lo + hi) // 2
            place(src, lo, mid)
            place(src, mid + 1, hi)
            return
        strips(src, lo, -180.0, 180.0)

    def strips(src, zz, west, east):
        """One zoom too big for one file: cut west to east at the median school."""
        lons = sorted(json.loads(l)["geometry"]["coordinates"][0] for l in src.open())
        cut = round(lons[len(lons) // 2], 4)
        for a, b in ((west, cut), (cut, east)):
            part = work / f"strip{zz}_{a}_{b}.ndjson"
            with part.open("w") as w:
                for line in src.open():
                    x = json.loads(line)["geometry"]["coordinates"][0]
                    if a <= x < b or (b == east and x == east):
                        w.write(line)
            out = work / f"part{zz}_{a}.pmtiles"
            size = tip(part, zz, zz, out)
            if size <= LIMIT:
                built.append((zz, zz, out, [a, b]))
            elif b - a > 0.5:
                strips(part, zz, a, b)
            else:
                raise SystemExit(f"giga_points: {a} to {b} degrees at zoom {zz} is {size / 1e6:.0f} MB, over GitHub's limit")

    for (lo, hi), src, _ in runs:
        place(src, lo, hi)
    built.sort(key=lambda b: (b[0], (b[3] or [0])[0]))
    parts = []
    for i, (lo, hi, f, lon) in enumerate(built):
        name = OUT.name if i == 0 else (f"giga_points_z{lo}.pmtiles" if lon is None else f"giga_points_z{lo}_{i}.pmtiles")
        os.replace(f, OUT.parent / name)
        parts.append(dict({"file": name, "from": lo, "to": hi, "bytes": (OUT.parent / name).stat().st_size},
                          **({"bounds": [lon[0], -85.05, lon[1], 85.05]} if lon else {})))
    STAMP.write_text(json.dumps({"layer": "schools", "schools": len(schools), "detail_from": DETAIL, "fields": fields, "id_field": idkey,
                                 "squares": [{"zooms": list(z), "degrees": d} for z, d in SQUARES], "from": tpl,
                                 "read_at_zoom": 7, "squares_failed": failed[:200], "squares_failed_count": len(failed),
                                 "parts": parts, "date": datetime.date.today().isoformat(), "seconds": round(time.time() - t0)}, indent=1))
    print(f"giga_points: {len(schools):,} schools in {len(parts)} file(s), {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
