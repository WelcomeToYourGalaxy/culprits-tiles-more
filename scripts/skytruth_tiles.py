#!/usr/bin/env python3
"""
SkyTruth Monitor's feeds as tiles: tiles/skytruth_<name>.pmtiles, one per feed.

The feeds' copies (skytruth/<name>/<hh>.json, kept by scripts/skytruth.py) run
to tens of megabytes; a browser reading a whole feed to draw its points was
slow, and the biggest would soon pass what GitHub takes. Tiles are read square
by square. Every alert with a position is in them, at every zoom, merged into
none merged (23 September; before, crowded points were merged into counts);
nothing is dropped. A point carries only its id and date; its title, the
alert's own text, and every other field, stays in the copy, and the map reads
that alert's piece on a click.

Run by skytruth.py at the end of its own run (the workflow runs scripts side by
side, so a separate job found no pieces yet). On its own, it rebuilds the tiles
from the pieces already there.
Each feed's tiles are rebuilt only when its pieces have changed since
(tiles/skytruth_<name>.build.json records what they were built from).
"""
import hashlib, json, pathlib, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mines  # noqa: E402  sh() and tools()

COPY = pathlib.Path("skytruth")
TILES = pathlib.Path("tiles")
MAXZOOM = 12
# The map's row id for each feed: the tile layer is named for it, which is how
# map/app.js's pmtiles route finds a layer's tiles (source-layer = the row id).
ROWS = {
    "feed_1": "skytruth_nrc", "feed_2": "skytruth_posts", "feed_3": "skytruth_marine_incidents",
    "feed_4": "skytruth_pa_permits", "feed_5": "skytruth_pa_spud", "feed_6": "skytruth_quakes",
    "feed_8": "skytruth_well_permits", "feed_9": "skytruth_pa_violations", "feed_10": "skytruth_fracfocus",
    "feed_10101": "skytruth_tests", "vessels_of_concern": "skytruth_voc",
}


def fingerprint(store):
    h = hashlib.sha1()
    for piece in sorted(store.glob("*.json")):
        st = piece.stat()
        h.update(f"{piece.name}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()


def build(name, row):
    store = COPY / name
    if not store.is_dir():
        return None
    out, stamp = TILES / f"{row}.pmtiles", TILES / f"{row}.build.json"
    print_ = f"skytruth tiles {name} ({row})"
    fp = fingerprint(store)
    if out.exists() and stamp.exists():
        try:
            # A build from before 23 September merged its points; it is made again.
            if json.loads(stamp.read_text())["from"] == fp and json.loads(stamp.read_text()).get("slim") is True:
                print(f"{print_}: unchanged, kept")
                return json.loads(stamp.read_text())
        except Exception:  # noqa: BLE001
            pass
    work = pathlib.Path(tempfile.mkdtemp())
    lines = work / "points.geojsonl"
    placed = nowhere = 0
    with open(lines, "w", encoding="utf-8") as fo:
        for piece in sorted(store.glob("*.json")):
            for key, f in json.loads(piece.read_text(encoding="utf-8")).items():
                g = f.get("geometry")
                if not g or not g.get("coordinates"):
                    nowhere += 1
                    continue
                p = f.get("properties") or {}
                placed += 1
                # Only the id, the date and the count are in the squares (23
                # September): with every alert kept and its title in every
                # square, the widest square of the spill reports was 3.8 MB.
                # The title and every other field are read from the alert's
                # piece on a click, as before.
                fo.write(json.dumps({"type": "Feature", "geometry": g, "properties": {
                    "id": key, "x_date": p.get("incident_datetime"), "_count": 1}}, ensure_ascii=False) + "\n")
    if not placed:
        print(f"{print_}: no alert has a position; no tiles", file=sys.stderr)
        return None
    TILES.mkdir(exist_ok=True)
    part = work / "out.pmtiles"
    mines.sh("tippecanoe", "-o", str(part), "--force", "-q", "-Z0", f"-z{MAXZOOM}", "-r1", "-l", row, "--name", row,
             # Every alert at every zoom, none merged (23 September).
             "--no-feature-limit", "--no-tile-size-limit", "--preserve-input-order", str(lines))
    part.replace(out)
    info = {"points_merged": False, "slim": True, "from": fp, "row": row, "feed": name, "alerts_with_position": placed, "no_position": nowhere,
            "bytes": out.stat().st_size, "boxes": f"skytruth/{name}"}
    stamp.write_text(json.dumps(info, indent=1))
    print(f"{print_}: {placed:,} alerts placed, {nowhere:,} with no position; {out.stat().st_size / 1e6:.1f} MB")
    return info


def main():
    mines.tools()
    built = [b for b in (build(n, r) for n, r in ROWS.items()) if b]
    if not built:
        sys.exit("skytruth tiles: nothing to build; run scripts/skytruth.py first")


if __name__ == "__main__":
    main()
