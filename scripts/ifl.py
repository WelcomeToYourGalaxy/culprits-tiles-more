#!/usr/bin/env python3
"""
The Intact Forest Landscapes of 2000, 2013, 2016, 2020 and 2025 as the map's
own copies (round 99b, asked 28 September: the five rows did not load, or not
fast enough; Global Forest Watch serves them only as tiles made on request).

Source: Global Forest Watch's tables of them (datasets
ifl_intact_forest_landscapes_<year>, the latest version of each), read through
its Data API's csv download, every field kept, each shape from its
gfw_geojson column. The data are Potapov et al.'s Intact Forest Landscapes
(intactforests.org), CC BY 4.0.

  tiles/ifl_<year>.pmtiles   layer "ifl", zooms 0 to 10 (fewer if over 95 MB)
  ifl/build.json             for each year: version read, shapes, fields, size

Built once; IFL_REBUILD=1 builds them again.
"""
import csv, json, os, pathlib, sys, tempfile, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

API = "https://data-api.globalforestwatch.org"
KEY = "2d60cd88-8348-4c0f-a6d5-bd9adb585a8c"
YEARS = ["2000", "2013", "2016", "2020", "2025"]
TILES = pathlib.Path("tiles")
OUT = pathlib.Path("ifl")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)", "x-api-key": KEY}
LIMIT = 95 * 1024 * 1024
SKIP = {"geom", "geom_wm", "gfw_geojson", "gfw_bbox", "gfw_geostore_id", "created_on", "updated_on"}


def get(url, to=None, timeout=1800):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if to is None:
            return r.read()
        with open(to, "wb") as f:
            while True:
                b = r.read(1 << 22)
                if not b:
                    break
                f.write(b)
    return to


def latest(ds):
    j = json.loads(get(f"{API}/dataset/{ds}/latest", timeout=120))
    return j["data"]["version"]


def tile(src, out, top):
    import mines
    for z in (top, top - 1, top - 2):
        mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", "ifl", "-Z0", f"-z{z}", "--detect-shared-borders",
                 "--coalesce-densest-as-needed", "--simplification=4", "--maximum-tile-bytes=800000", str(src))
        if out.stat().st_size <= LIMIT:
            return z
        print(f"ifl: {out.name} is {out.stat().st_size / 1e6:.0f} MB at zoom {z}; one zoom lower", flush=True)
    raise RuntimeError(f"{out.name} still over 95 MB")


def one(year, work, stamp):
    ds = f"ifl_intact_forest_landscapes_{year}"
    ver = latest(ds)
    url = f"{API}/dataset/{ds}/{ver}/download/csv?" + urllib.parse.urlencode({"sql": "SELECT * FROM data", "x-api-key": KEY})
    raw = get(url, work / f"{year}.csv")
    print(f"ifl {year}: {ds} {ver}, {raw.stat().st_size / 1e6:.0f} MB", flush=True)
    csv.field_size_limit(1 << 30)
    lines = work / f"{year}.geojsons"
    n, fields = 0, []
    with open(raw, newline="", encoding="utf-8") as f, lines.open("w") as w:
        rd = csv.DictReader(f)
        fields = [k for k in (rd.fieldnames or []) if k not in SKIP]
        for r in rd:
            g = r.get("gfw_geojson")
            if not g:
                continue
            props = {}
            for k in fields:
                v = r.get(k)
                if v in (None, ""):
                    continue
                try:
                    props[k] = int(v) if v.lstrip("-").isdigit() else float(v)
                except ValueError:
                    props[k] = v
            props["year"] = int(year)
            w.write(json.dumps({"type": "Feature", "properties": props, "geometry": json.loads(g)}) + "\n")
            n += 1
    if not n:
        raise RuntimeError("no shapes read")
    top = tile(lines, TILES / f"ifl_{year}.pmtiles", 10)
    stamp[year] = {"dataset": ds, "version": ver, "shapes": n, "fields": fields, "to_zoom": top,
                   "bytes": (TILES / f"ifl_{year}.pmtiles").stat().st_size}
    print(f"ifl {year}: {n} landscapes, zooms 0 to {top}", flush=True)


def main():
    OUT.mkdir(exist_ok=True)
    TILES.mkdir(exist_ok=True)
    stamp_path = OUT / "build.json"
    stamp = json.loads(stamp_path.read_text()) if stamp_path.exists() else {}
    want = [y for y in YEARS if os.environ.get("IFL_REBUILD") or not (TILES / f"ifl_{y}.pmtiles").exists()]
    if not want:
        print("ifl: already built")
        return
    import mines
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    failed = []
    for y in want:
        try:
            one(y, work, stamp)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{y}: {type(e).__name__}: {e}")
            print(f"ifl {y}: not built ({e})", flush=True)
        stamp_path.write_text(json.dumps(stamp, indent=1))
        for p in work.glob(f"{y}.*"):
            p.unlink()
    if failed:
        sys.exit("ifl: " + "; ".join(failed))


if __name__ == "__main__":
    main()
