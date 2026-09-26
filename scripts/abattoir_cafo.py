#!/usr/bin/env python3
"""
Climate TRACE's confined animal facilities, as the abattoir atlas carries them.

The abattoir atlas (WelcomeToYourGalaxy/abattoir-atlas) draws these on its own
map beside its registered facilities, from its file

  raw/climate_trace_cafo.geojsonl.gz

This copies that file each day and tiles it into

  tiles/abattoir_cafo.pmtiles     layer "cafo", one point per facility

so the Slaughterhouses row in Culprits can draw them the way the atlas does:
solid where Climate TRACE gives the facility's own position, hollow where it
gives an area. Every field the file carries is kept. Where the file repeats a
facility once per month, the latest month is kept, as the atlas does.

Rebuilt only when the atlas's file changes (its hash is kept beside the tiles).
"""
import gzip, hashlib, json, os, pathlib, shutil, subprocess, sys, tempfile, urllib.request

SRC = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/abattoir-atlas/main/raw/climate_trace_cafo.geojsonl.gz"
OUT = pathlib.Path("tiles/abattoir_cafo.pmtiles")
STAMP = pathlib.Path("tiles/abattoir_cafo.source.sha256")
PRECISE = ("asset", "facility", "high", "exact", "point")


def piece_of(key):
    """Which of 256 pieces a record is in: FNV-1a over its id, as the map's pieceOf."""
    h = 0x811C9DC5
    for b in str(key).encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return format(h % 256, "02x")


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


def main():
    req = urllib.request.Request(SRC, headers={"User-Agent": "Culprits atlas build"})
    raw = urllib.request.urlopen(req, timeout=300).read()
    digest = hashlib.sha256(raw).hexdigest()
    # The stamp now names the unmerged build too, so a merged one is made again.
    digest = digest + " unmerged slim"
    if OUT.exists() and STAMP.exists() and STAMP.read_text().strip() == digest and not os.environ.get("CAFO_REBUILD"):
        print("abattoir_cafo: the atlas's file has not changed")
        return

    best = {}
    for line in gzip.decompress(raw).decode("utf-8").splitlines():
        line = line.strip().lstrip("\x1e")
        if not line:
            continue
        try:
            f = json.loads(line)
        except json.JSONDecodeError:
            continue
        g = f.get("geometry") or {}
        if g.get("type") != "Point":
            continue
        p = f.get("properties") or {}
        if p.get("x_asset_definition") not in (None, "confined-animal-facility"):
            continue
        x, y = g["coordinates"][:2]
        key = (round(float(x), 5), round(float(y), 5), p.get("name"))
        period = str(p.get("x_period") or "")
        if key in best and period <= best[key][0]:
            continue
        p["precise"] = 1 if str(p.get("x_precision", "")).lower() in PRECISE else 0
        best[key] = (period, {"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(x), float(y)]},
                              "properties": {k: v for k, v in p.items() if v is not None}})
    if not best:
        sys.exit("abattoir_cafo: no facilities read from the atlas's file; the last copy stays")

    tools()
    work = pathlib.Path(tempfile.mkdtemp())
    pts = work / "cafo.geojsonl"
    # The squares carry only each facility's id and whether its position is its
    # own; every field it has is in 256 pieces beside the tiles (cafo/pieces,
    # FNV-1a of the id, the map's pieceOf), read on a click. With every field
    # in every square and none merged, the world-view square was 3.6 MB.
    pieces = {}
    with open(pts, "w", encoding="utf-8") as fo:
        for n, key in enumerate(sorted(best, key=lambda k: (k[0], k[1], str(k[2])))):
            feat = best[key][1]
            fid = str(n)
            pieces.setdefault(piece_of(fid), {})[fid] = {"properties": feat["properties"]}
            fo.write(json.dumps({"type": "Feature", "geometry": feat["geometry"],
                                 "properties": {"id": fid, "precise": feat["properties"].get("precise", 1)}},
                                separators=(",", ":")) + "\n")
    pdir = pathlib.Path("cafo/pieces")
    if pdir.exists():
        shutil.rmtree(pdir)
    pdir.mkdir(parents=True)
    for k, recs in pieces.items():
        (pdir / f"{k}.json").write_text(json.dumps(recs, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Every facility at every zoom, none merged (asked for 23 September): no
    # clustering and no size cap. The deepest zoom is lowered only if the file
    # would be over GitHub's limit; closer in, the map enlarges those squares.
    for maxz in (10, 9, 8, 7):
        sh("tippecanoe", "-o", str(OUT), "--force", "-l", "cafo", "-Z0", f"-z{maxz}", "-r1",
           "--no-feature-limit", "--no-tile-size-limit", "-q", str(pts))
        if OUT.stat().st_size <= 95 * 1024 * 1024:
            break
    else:
        OUT.unlink()
        sys.exit("abattoir_cafo: could not get the archive under GitHub's 100 MB limit; the last copy stays")
    STAMP.write_text(digest + "\n")
    print(f"abattoir_cafo: {len(best):,} facilities tiled into {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
