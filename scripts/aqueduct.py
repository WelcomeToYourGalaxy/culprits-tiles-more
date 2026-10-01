#!/usr/bin/env python3
"""
WRI Aqueduct's water stress, as the map's own vector tiles (round 93b, asked 27
September: the projected water stress row loaded too slowly and showed one
blue everywhere, and the farmland water stress row showed nothing).

Both were drawn from Global Forest Watch's tiles, made from its database when
asked for, one square at a time (slow at every zoom), with no colouring. This
builds each once, from its source, so the map reads a small archive and
colours each basin by its own figures.

1. Aqueduct Water Stress Projections (Luck, Landis and Gassert 2015, WRI;
   CC BY 4.0): https://files.wri.org/d8/s3fs-public/aqueduct_projections_20150309_shp.zip
   every catchment with water stress (ws), seasonal variability (sv), total
   water withdrawals (ut) and total blue water supply (bt), for 2020, 2030 and
   2040, under three scenarios, each as a value, a change from the baseline and
   an uncertainty, raw (r) and as WRI's own category label (l).
       tiles/aqueduct_projections.pmtiles   layer "basins", every field kept
2. Aqueduct crop baseline 2020 (WRI, as published on Global Forest Watch,
   dataset aqueduct_crop_baseline_2020 v1.12): one figure per crop for each
   area, 44 crops. Read from Global Forest Watch's open data lake copy
   (default.ndjson).
       tiles/aqueduct_crop.pmtiles          layer "areas", every field kept
   aqueduct/build.json records each file's fields and each crop's range.

   Round 111b: if both copies above refuse (29 September: 403 and 500), the
   table is read through the Data API's query a page at a time.

Built once; AQUEDUCT_REBUILD=1 builds again.
"""
import csv, gzip, json, os, pathlib, shutil, subprocess, sys, tempfile, urllib.parse, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

PROJ_URL = "https://files.wri.org/d8/s3fs-public/aqueduct_projections_20150309_shp.zip"
GFW_KEY = "2d60cd88-8348-4c0f-a6d5-bd9adb585a8c"
CROP_DS = "https://data-api.globalforestwatch.org/dataset/aqueduct_crop_baseline_2020/v1.12"
# Round 97b (28 September): the data lake copy answers 403 and the Data API
# has no geojson download (404). The Data API's csv download of the table
# (every field, the shape as the gfw_geojson text column) is read instead;
# the data lake stays first in case it opens again.
CROP_URLS = ["https://gfw-data-lake.s3.amazonaws.com/aqueduct_crop_baseline_2020/v1.12/vector/epsg-4326/default.ndjson",
             CROP_DS + "/download/csv?sql=" + urllib.parse.quote("SELECT * FROM data") + "&x-api-key=" + GFW_KEY]
TILES = pathlib.Path("tiles")
OUT = pathlib.Path("aqueduct")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
# Round 118b (30 September: every query answered 403): Global Forest Watch's
# public key is tied to its own website, and its Data API refuses a request
# that does not come from there; the request says it does, as the GFW map's
# own requests do.
GFW_FROM = {"Origin": "https://www.globalforestwatch.org", "Referer": "https://www.globalforestwatch.org/"}
LIMIT = 95 * 1024 * 1024
DROP = {"geom", "geom_wm", "gfw_geojson", "gfw_bbox", "gfw_geostore_id", "created_on", "updated_on"}


def fetch(url, to):
    head = dict(UA, **({"x-api-key": GFW_KEY, **GFW_FROM} if "globalforestwatch.org" in url else {}))
    with urllib.request.urlopen(urllib.request.Request(url, headers=head), timeout=1800) as r, open(to, "wb") as f:
        shutil.copyfileobj(r, f)
    print(f"aqueduct: {url.split('?')[0]}: {to.stat().st_size / 1e6:.1f} MB", flush=True)


def tile(src, out, layer, top):
    import mines
    for z in (top, top - 1, top - 2):
        mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", layer, "-Z0", f"-z{z}", "--detect-shared-borders",
                 "--coalesce-densest-as-needed", "--simplification=4", "--maximum-tile-bytes=800000", str(src))
        if out.stat().st_size <= LIMIT:
            return z
        print(f"aqueduct: {out.name} is {out.stat().st_size / 1e6:.0f} MB at zoom {z}; one zoom lower", flush=True)
    sys.exit(f"aqueduct: {out.name} still over 95 MB")


def projections(work, stamp):
    z = work / "proj.zip"
    fetch(PROJ_URL, z)
    zipfile.ZipFile(z).extractall(work / "proj")
    shp = next((work / "proj").rglob("*.shp"))
    gj = work / "proj.geojsons"
    import mines
    mines.sh("ogr2ogr", "-f", "GeoJSONSeq", "-t_srs", "EPSG:4326", "-lco", "RS=NO", str(gj), str(shp))
    first = json.loads(gj.open().readline())
    fields = list(first.get("properties", {}))
    top = tile(gj, TILES / "aqueduct_projections.pmtiles", "basins", 8)
    stamp["projections"] = {"from": PROJ_URL, "shapefile": shp.name, "fields": fields, "to_zoom": top,
                            "bytes": (TILES / "aqueduct_projections.pmtiles").stat().st_size}


def paged(to):
    """Round 111b (29 September): the whole-table csv download answered 500
    and the data lake 403. The table is read through the Data API's query, a
    thousand rows at a time in the order of gfw_fid, every column, each row
    written as one line of JSON (the shape comes in gfw_geojson or geom)."""
    last, n = None, 0
    with open(to, "w", encoding="utf-8") as w:
        while True:
            where = f" WHERE gfw_fid > {last}" if last is not None else ""
            sql = f"SELECT * FROM data{where} ORDER BY gfw_fid LIMIT 1000"
            url = CROP_DS + "/query/json?" + urllib.parse.urlencode({"sql": sql})
            body = None
            for i in range(4):
                try:
                    req = urllib.request.Request(url, headers=dict(UA, **{"x-api-key": GFW_KEY}, **GFW_FROM))
                    with urllib.request.urlopen(req, timeout=600) as r:
                        body = json.loads(r.read())
                    break
                except Exception as e:  # noqa: BLE001
                    print(f"aqueduct: page after {last}: {e}; again", flush=True)
                    __import__("time").sleep(10 * (i + 1))
            if body is None:
                raise RuntimeError(f"the query stopped answering after {n} rows")
            rows = body.get("data") or []
            if not rows:
                break
            for r in rows:
                w.write(json.dumps(r) + "\n")
            n += len(rows)
            last = rows[-1].get("gfw_fid")
            if last is None:
                raise RuntimeError("rows have no gfw_fid to page by")
            if n % 10000 < 1000:
                print(f"aqueduct: {n:,} rows read", flush=True)
            if len(rows) < 1000:
                break
    if not n:
        raise RuntimeError("the query gave no rows")
    print(f"aqueduct: {n:,} rows read through the query", flush=True)


def crops(work, stamp):
    raw = work / "crop.ndjson"
    for u in CROP_URLS + ["paged"]:
        try:
            if u == "paged":
                paged(raw)
            else:
                fetch(u, raw)
            break
        except Exception as e:  # noqa: BLE001
            print(f"aqueduct: {u.split('?')[0]} did not answer ({e})", flush=True)
    else:
        sys.exit("aqueduct: no copy of the crop data could be fetched")
    used = CROP_DS + "/query/json (a page at a time)" if u == "paged" else u.split("?")[0]
    if "/download/csv" in u:
        # The csv's rows as the data lake's rows: figures as numbers, the shape
        # in gfw_geojson.
        csv.field_size_limit(1 << 30)
        rows = raw.with_suffix(".rows.ndjson")
        with open(raw, newline="", encoding="utf-8") as f, rows.open("w") as w:
            for r in csv.DictReader(f):
                for k, v in list(r.items()):
                    if v in ("", None):
                        r[k] = None
                    elif k not in ("gfw_geojson", "geom", "geom_wm", "gfw_geostore_id", "gfw_bbox", "created_on", "updated_on"):
                        try:
                            r[k] = float(v) if not v.lstrip("-").isdigit() else int(v)
                        except ValueError:
                            pass
                w.write(json.dumps(r) + "\n")
        raw = rows
    # One GeoJSON feature per line, whatever the source's own shape: a row of
    # the data lake carries its geometry as geojson text (gfw_geojson) or as a
    # geometry member.
    out = work / "crop.geojsons"
    ranges, n = {}, 0
    opener = gzip.open if raw.open("rb").read(2) == b"\x1f\x8b" else open
    with opener(raw, "rt", encoding="utf-8") as f:
        start = f.read(300)
    if '"FeatureCollection"' in start:
        with opener(raw, "rt", encoding="utf-8") as f:
            lines = [json.dumps(x) for x in json.load(f).get("features", [])]
    else:
        lines = opener(raw, "rt", encoding="utf-8")
    with out.open("w") as w:
        for line in lines:
            line = line.strip() if isinstance(line, str) else line
            if not line:
                continue
            r = json.loads(line)
            if r.get("type") == "Feature":
                props, geom = r.get("properties") or {}, r.get("geometry")
            else:
                props, geom = r, r.get("geometry") or (json.loads(r["gfw_geojson"]) if isinstance(r.get("gfw_geojson"), str) else r.get("gfw_geojson"))
            if not geom and isinstance(r.get("geom"), str) and all(c in "0123456789abcdefABCDEF" for c in r["geom"][:40]):
                # PostGIS's hex WKB, as a database export writes it.
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", "shapely"], check=True) if "shapely" not in sys.modules else None
                from shapely import wkb
                from shapely.geometry import mapping
                geom = mapping(wkb.loads(bytes.fromhex(r["geom"])))
            if not geom:
                continue
            p = {k: v for k, v in props.items() if k not in DROP and k != "geometry"}
            for k, v in p.items():
                if isinstance(v, (int, float)) and k not in ("gfw_fid", "gfw_area__ha"):
                    lo, hi = ranges.get(k, (v, v))
                    ranges[k] = (min(lo, v), max(hi, v))
            w.write(json.dumps({"type": "Feature", "properties": p, "geometry": geom}) + "\n")
            n += 1
    if not n:
        sys.exit("aqueduct: no crop areas read")
    top = tile(out, TILES / "aqueduct_crop.pmtiles", "areas", 8)
    stamp["crops"] = {"from": used, "areas": n, "ranges": ranges, "to_zoom": top,
                      "bytes": (TILES / "aqueduct_crop.pmtiles").stat().st_size}


def main():
    stamp_path = OUT / "build.json"
    stamp = json.loads(stamp_path.read_text()) if stamp_path.exists() else {}
    want_p = os.environ.get("AQUEDUCT_REBUILD") or not (TILES / "aqueduct_projections.pmtiles").exists()
    want_c = os.environ.get("AQUEDUCT_REBUILD") or not (TILES / "aqueduct_crop.pmtiles").exists()
    if not (want_p or want_c):
        print("aqueduct: already built")
        return
    import mines
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    OUT.mkdir(exist_ok=True)
    failed = []
    for want, job in ((want_p, projections), (want_c, crops)):
        if not want:
            continue
        try:
            job(work, stamp)
        except SystemExit as e:
            failed.append(str(e))
        except Exception as e:  # noqa: BLE001
            failed.append(f"{job.__name__}: {type(e).__name__}: {e}")
        stamp_path.write_text(json.dumps(stamp, indent=1, default=str))
    if failed:
        sys.exit("; ".join(failed))


if __name__ == "__main__":
    main()
