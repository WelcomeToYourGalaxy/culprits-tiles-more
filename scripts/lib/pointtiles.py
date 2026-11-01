"""
Many points as map archives (round 114b; the same way as giga_points.py):
wider out one mark per square with how many places it holds (and how many of
each kind), coloured by the kind most of them are; closer in every place, in
west-to-east strips where one file would pass GitHub's 95 MB limit.

  build(points, out, layer, kind_field, squares, detail, attribution)
    points: iterable of (lon, lat, properties)
    out:    pathlib.Path of the first archive (tiles/<row>.pmtiles)
  returns the parts list for <row>.build.json (file, from, to, bytes, bounds)

Kept in scripts/lib/ so the refresh workflow does not run it on its own.
"""
import json, math, os, pathlib, sys, tempfile

LIMIT = 90 * 1024 * 1024
SQUARES = [((0, 1), 2.0), ((2, 3), 0.5), ((4, 5), 0.1), ((6, 7), 0.02)]


def _tip(mines, src, lo, hi, out, layer, attribution):
    mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", layer, f"-Z{lo}", f"-z{hi}", "-r1",
             "--no-feature-limit", "--no-tile-size-limit", "--attribution", attribution, str(src))
    return out.stat().st_size


def build(points, out, layer, kind_field, squares=SQUARES, detail=8, attribution=""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    import mines
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    pts = list(points)
    detail_f = work / "detail.ndjson"
    with detail_f.open("w") as w:
        for lon, lat, p in pts:
            w.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": p}, ensure_ascii=False) + "\n")
    runs = []
    for (z0, z1), deg in squares:
        sq = {}
        for lon, lat, p in pts:
            k = (math.floor(lon / deg), math.floor(lat / deg))
            e = sq.setdefault(k, {"n": 0, "by": {}, "x": 0.0, "y": 0.0})
            e["n"] += 1
            e["x"] += lon
            e["y"] += lat
            kind = str(p.get(kind_field, "other"))
            e["by"][kind] = e["by"].get(kind, 0) + 1
        f = work / f"sq{z0}.ndjson"
        with f.open("w") as w:
            for e in sq.values():
                top = max(e["by"].items(), key=lambda kv: kv[1])[0]
                props = {"_count": e["n"], kind_field: top, **{f"of which {k}": v for k, v in sorted(e["by"].items())}}
                w.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(e["x"] / e["n"], 5), round(e["y"] / e["n"], 5)]},
                                    "properties": props}, ensure_ascii=False) + "\n")
        runs.append(((z0, z1), f))
    runs.append(((detail, detail), detail_f))
    built = []

    def place(src, lo, hi):
        o = work / f"part{lo}_{hi}.pmtiles"
        size = _tip(mines, src, lo, hi, o, layer, attribution)
        if size <= LIMIT:
            built.append((lo, hi, o, None))
        elif lo < hi:
            mid = (lo + hi) // 2
            place(src, lo, mid)
            place(src, mid + 1, hi)
        else:
            strips(src, lo, -180.0, 180.0)

    def strips(src, zz, west, east):
        lons = sorted(json.loads(l)["geometry"]["coordinates"][0] for l in src.open())
        cut = round(lons[len(lons) // 2], 4)
        if not (west < cut < east):
            raise SystemExit(f"pointtiles: cannot cut {west} to {east} further at zoom {zz}")
        for a, b in ((west, cut), (cut, east)):
            part = work / f"strip{zz}_{a}_{b}.ndjson"
            with part.open("w") as w:
                for line in src.open():
                    x = json.loads(line)["geometry"]["coordinates"][0]
                    if a <= x < b or (b == east and x == east):
                        w.write(line)
            o = work / f"part{zz}_{a}.pmtiles"
            size = _tip(mines, part, zz, zz, o, layer, attribution)
            if size <= LIMIT:
                built.append((zz, zz, o, [a, b]))
            elif b - a > 0.5:
                strips(part, zz, a, b)
            else:
                raise SystemExit(f"pointtiles: {a} to {b} degrees at zoom {zz} is {size / 1e6:.0f} MB, over GitHub's limit")

    for (lo, hi), src in runs:
        place(src, lo, hi)
    out.parent.mkdir(parents=True, exist_ok=True)
    stem = out.stem
    for old in out.parent.glob(f"{stem}_z*.pmtiles"):
        old.unlink()
    built.sort(key=lambda b: (b[0], (b[3] or [0])[0]))
    parts = []
    for i, (lo, hi, f, lon) in enumerate(built):
        name = out.name if i == 0 else (f"{stem}_z{lo}.pmtiles" if lon is None else f"{stem}_z{lo}_{i}.pmtiles")
        os.replace(f, out.parent / name)
        parts.append(dict({"file": name, "from": lo, "to": hi, "bytes": (out.parent / name).stat().st_size},
                          **({"bounds": [lon[0], -85.05, lon[1], 85.05]} if lon else {})))
    return parts
