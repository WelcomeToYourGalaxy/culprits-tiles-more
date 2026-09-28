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

Built once; AQUEDUCT_REBUILD=1 builds again.
"""
import gzip, json, os, pathlib, shutil, subprocess, sys, tempfile, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

PROJ_URL = "https://files.wri.org/d8/s3fs-public/aqueduct_projections_20150309_shp.zip"
CROP_URLS = ["https://gfw-data-lake.s3.amazonaws.com/aqueduct_crop_baseline_2020/v1.12/vector/epsg-4326/default.ndjson",
             "https://data-api.globalforestwatch.org/dataset/aqueduct_crop_baseline_2020/v1.12/download/geojson?x-api-key=2d60cd88-8348-4c0f-a6d5-bd9adb585a8c"]
TILES = pathlib.Path("tiles")
OUT = pathlib.Path("aqueduct")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
LIMIT = 95 * 1024 * 1024
DROP = {"geom", "geom_wm", "gfw_geojson", "gfw_bbox", "gfw_geostore_id", "created_on", "updated_on"}


def fetch(url, to):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=1800) as r, open(to, "wb") as f:
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


def crops(work, stamp):
    raw = work / "crop.ndjson"
    for u in CROP_URLS:
        try:
            fetch(u, raw)
            break
        except Exception as e:  # noqa: BLE001
            print(f"aqueduct: {u.split('?')[0]} did not answer ({e})", flush=True)
    else:
        sys.exit("aqueduct: no copy of the crop data could be fetched")
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
    stamp["crops"] = {"from": CROP_URLS[0], "areas": n, "ranges": ranges, "to_zoom": top,
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
