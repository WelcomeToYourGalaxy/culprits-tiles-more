"""Points from many rows in a few shared files (round 58, 26 September).

The layers box's "Turn on every: Points" switch turns on dozens of rows at
once. Each row reads its own archive, so each asked for the same squares of the
map separately: dozens of archives meant dozens of requests for every square in
view. The owner asked for the points to be put together so they load at once.

This copies each row listed in bundles/members.json (its own archive, from
wherever the map reads it) and joins them with tippecanoe's tile-join into
tiles/points_bundle_N.pmtiles. Each row stays its own layer inside the file,
under the same name, with every field it had: nothing is dropped or thinned
(tile-join runs with no tile size limit). Rows are grouped by their deepest
zoom, so no row stops short of where its own archive went, and a file is kept
under 90 MB. Left to load on their own, and named in the log and in
bundles/points.json: rows whose archive is split into parts (a .build.json
listing them), over 40 MB, not vector tiles, or not found.

bundles/points.json tells the map which file holds which row. The map uses the
shared file only for rows the switch turns on; a row ticked by hand reads its
own archive as before.
"""
import hashlib, json, os, pathlib, shutil, struct, subprocess, sys, tempfile, time, urllib.request

MEMBERS = pathlib.Path("bundles/members.json")
MANIFEST = pathlib.Path("bundles/points.json")
OUTDIR = pathlib.Path("tiles")
MAX_MEMBER = 40 * 1024 * 1024
MAX_BUNDLE = 88 * 1024 * 1024
LIMIT = 95 * 1024 * 1024
BASE = "https://welcometoyourgalaxy.github.io/culprits-tiles-more/"
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}


def sh(*cmd, **kw):
    print("  $", " ".join(str(c) for c in cmd[:6]), "…" if len(cmd) > 6 else "", flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def tools():
    if shutil.which("tile-join"):
        return
    sh("sudo", "apt-get", "update", "-qq")
    sh("sudo", "apt-get", "install", "-y", "-qq", "libsqlite3-dev", "zlib1g-dev", "build-essential")
    d = tempfile.mkdtemp()
    sh("git", "clone", "--depth", "1", "https://github.com/felt/tippecanoe.git", d)
    sh("make", "-j4", cwd=d)
    sh("sudo", "make", "install", cwd=d)


def fetch(url, to=None, tries=4):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                if to is None:
                    return r.read()
                with open(to, "wb") as f:
                    shutil.copyfileobj(r, f, 1 << 20)
                return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except Exception as e:
            last = e
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def header(path):
    """min zoom, max zoom and tile type from a PMTiles v3 header."""
    with open(path, "rb") as f:
        h = f.read(127)
    if h[:7] != b"PMTiles" or h[7] != 3:
        return None
    return {"tile_type": h[99], "minzoom": h[100], "maxzoom": h[101]}


def sha(path):
    d = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            d.update(b)
    return d.hexdigest()


def main():
    members = json.loads(MEMBERS.read_text())["rows"]
    work = pathlib.Path(tempfile.mkdtemp())
    got, left = [], []
    for m in members:
        row, url = m["row"], m["url"]
        try:
            build = fetch(url.replace(".pmtiles", ".build.json"), tries=2)
        except Exception:
            build = None
        if build:
            try:
                b = json.loads(build)
                if b.get("parts") or (isinstance(b.get("files"), (int, list)) and (b.get("files") if isinstance(b.get("files"), int) else len(b["files"])) > 1):
                    left.append({"row": row, "why": "its archive is split into parts"})
                    continue
            except Exception:
                pass
        p = work / f"{row}.pmtiles"
        try:
            ok = fetch(url, p)
        except Exception as e:
            print(f"  {row}: not copied ({e})")
            ok = False
        if not ok:
            left.append({"row": row, "why": "not found"})
            continue
        size = p.stat().st_size
        h = header(p)
        if not h or h["tile_type"] != 1:
            left.append({"row": row, "why": "not vector tiles"})
            p.unlink()
            continue
        if size > MAX_MEMBER:
            left.append({"row": row, "why": f"{size / 1e6:.0f} MB, loads faster on its own"})
            p.unlink()
            continue
        got.append({"row": row, "path": p, "size": size, "sha": sha(p), **h})
        print(f"  {row}: {size / 1e6:.1f} MB, zooms {h['minzoom']}-{h['maxzoom']}", flush=True)

    # Nothing changed since the last build: nothing is written.
    old = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    if old.get("members") == {g["row"]: g["sha"] for g in got} and all(pathlib.Path(b["file"]).exists() for b in old.get("bundles", [])):
        print("  every member is as it was; the bundles stand")
        return

    tools()
    groups = {}
    for g in sorted(got, key=lambda g: (g["maxzoom"], -g["size"])):
        groups.setdefault(g["maxzoom"], []).append(g)
    packs = []
    for mz, gs in sorted(groups.items()):
        cur, tot = [], 0
        for g in gs:
            if cur and tot + g["size"] > MAX_BUNDLE:
                packs.append(cur); cur, tot = [], 0
            cur.append(g); tot += g["size"]
        if cur:
            packs.append(cur)

    bundles = []

    def join(pack):
        n = len(bundles) + 1
        out = work / f"points_bundle_{n}.pmtiles"
        sh("tile-join", "-o", out, "--force", "-q", "--no-tile-size-limit", *[g["path"] for g in pack])
        if out.stat().st_size > LIMIT and len(pack) > 1:
            out.unlink()
            half = len(pack) // 2
            join(pack[:half]); join(pack[half:])
            return
        if out.stat().st_size > LIMIT:
            for g in pack:
                left.append({"row": g["row"], "why": "too large to share a file"})
            return
        bundles.append({"n": n, "path": out, "rows": [g["row"] for g in pack],
                        "minzoom": min(g["minzoom"] for g in pack), "maxzoom": max(g["maxzoom"] for g in pack)})

    for pack in packs:
        join(pack)

    OUTDIR.mkdir(exist_ok=True)
    for old_file in OUTDIR.glob("points_bundle_*.pmtiles"):
        old_file.unlink()
    manifest = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "bundles": [], "left_out": left,
                "members": {g["row"]: g["sha"] for g in got}}
    for b in bundles:
        dest = OUTDIR / b["path"].name
        shutil.move(str(b["path"]), dest)
        manifest["bundles"].append({"file": str(dest), "url": BASE + str(dest), "rows": b["rows"],
                                    "minzoom": b["minzoom"], "maxzoom": b["maxzoom"], "bytes": dest.stat().st_size})
        print(f"  {dest}: {len(b['rows'])} rows, {dest.stat().st_size / 1e6:.1f} MB")
    MANIFEST.parent.mkdir(exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    for l in left:
        print(f"  left to load on its own: {l['row']} ({l['why']})")


if __name__ == "__main__":
    main()
