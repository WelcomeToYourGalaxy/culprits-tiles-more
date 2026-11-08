#!/usr/bin/env python3
"""
Agriculture-linked deforestation, district by district, for the Culprits map
(round 85b, asked 27 September: Global Forest Watch's row loaded slowly and
drew blank white shapes).

The source is WRI's "Agriculture-Linked Deforestation" (Goldman, Weisse, Harris
and Schneider 2020, "Estimating the Role of Seven Commodities in
Agriculture-Linked Deforestation", World Resources Institute; CC BY 4.0):
tree cover loss from 2001 to 2015 linked to cattle, oil palm, soy, cocoa,
coffee, rubber and wood fibre, for every second-level administrative area
(GADM), year by year. Global Forest Watch serves it only as tiles made from its
database on request, one per square, which is why the row was slow; this reads
the shapefile through the download link Global Forest Watch's open data portal
publishes for it (data.globalforestwatch.org, "Agriculture-linked
Deforestation") and builds

  tiles/agri_linked.pmtiles    one shape per district, layer agri_linked:
                               id, name, main (the crop or animal linked to
                               the most loss there), share (that loss as a
                               share of the district's area)
  agri_linked/pieces/<xx>.json.gz  every field for every crop or animal and
                               year, by district id (the map's boxes)
  agri_linked/key.json         how many districts each crop or animal leads

Built once (the release, v202010, is fixed); AGRI_REBUILD=1 builds it again.
"""
import gzip, io, json, os, pathlib, re, subprocess, sys, tempfile, time, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

VERSION = "v202010"
# The link Global Forest Watch's open data portal gives for the download
# (item d47bc4ded98545458d08ed454366c9c8), its own public key included.
URLS = [
    f"https://data-api.globalforestwatch.org/dataset/wri_agriculture_linked_deforestation/{VERSION}/download/shp?x-api-key=2d60cd88-8348-4c0f-a6d5-bd9adb585a8c",
    f"https://gfw-data-lake.s3.amazonaws.com/wri_agriculture_linked_deforestation/{VERSION}/vector/epsg-4326/wri_agriculture_linked_deforestation_{VERSION}.shp.zip",
]
NAME = "agri_linked"
OUT = pathlib.Path(NAME)
TILES = pathlib.Path("tiles")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
KINDS = [(r"cattle|beef|pasture", "Cattle"), (r"oil.?palm|palm", "Oil palm"), (r"soy", "Soy"), (r"cocoa|cacao", "Cocoa"),
         (r"coffee", "Coffee"), (r"rubber", "Rubber"), (r"wood.?fib|pulp|fiber|fibre|plantation", "Wood fiber")]


def piece_of(key):
    h = 0x811C9DC5
    for b in str(key).encode():
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h % 256:02x}"


def kind(v):
    t = str(v or "")
    for rule, name in KINDS:
        if re.search(rule, t, re.I):
            return name
    return t.strip() or "not named"


def download(work):
    last = None
    for u in URLS:
        try:
            req = urllib.request.Request(u, headers=UA)
            with urllib.request.urlopen(req, timeout=3600) as r, open(work / "src.zip", "wb") as f:
                while True:
                    b = r.read(1 << 22)
                    if not b:
                        break
                    f.write(b)
            if zipfile.is_zipfile(work / "src.zip"):
                print(f"agri_linked: read {(work / 'src.zip').stat().st_size / 1e6:.0f} MB from {u.split('?')[0]}", flush=True)
                return
            last = f"{u.split('?')[0]} did not give a zip"
        except Exception as e:  # noqa: BLE001
            last = f"{u.split('?')[0]}: {e}"
        print(f"  {last}", flush=True)
    raise RuntimeError(last)


def main():
    if (TILES / f"{NAME}.pmtiles").exists() and (OUT / "key.json").exists() and not os.environ.get("AGRI_REBUILD"):
        print("agri_linked: already built")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyshp", "pyproj", "shapely"], check=True)
    import shapefile
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    work = pathlib.Path(tempfile.mkdtemp())
    download(work)
    zipfile.ZipFile(work / "src.zip").extractall(work / "src")
    for inner in (work / "src").rglob("*.zip"):
        zipfile.ZipFile(inner).extractall(inner.parent)
    shp = sorted((work / "src").rglob("*.shp"), key=lambda p: -p.stat().st_size)[0]
    rd = shapefile.Reader(str(shp), encoding="utf-8", encodingErrors="replace")
    names = [f[0] for f in rd.fields[1:]]
    print(f"agri_linked: {len(rd):,} records in {shp.name}; fields {names}", flush=True)
    low = {n.lower(): n for n in names}
    fid = low.get("gid_2") or low.get("gfw_fid")
    layer = low.get("layer")
    years = sorted((n for n in names if re.fullmatch(r"loss_(19|20)\d\d", n, re.I)), key=str.lower)
    total = low.get("total_loss") or low.get("total_los")
    area_f = next((n for n in names if n.lower().startswith("gfw_area")), None)
    districts, unknown = {}, set()
    t0 = time.time()
    for n, sr in enumerate(rd.iterShapeRecords()):
        rec = dict(zip(names, sr.record))
        key = str(rec.get(fid) or f"row{n}")
        g = sr.shape.__geo_interface__
        k = kind(rec.get(layer))
        if k not in {name for _, name in KINDS}:
            unknown.add(k)
        d = districts.get(key)
        if d is None:
            area = None
            if area_f and rec.get(area_f) not in (None, ""):
                try:
                    area = float(rec[area_f])
                except (TypeError, ValueError):
                    area = None
            if area is None and g and g.get("coordinates"):
                try:
                    area = abs(geod.geometry_area_perimeter(__import__("shapely.geometry", fromlist=["shape"]).shape(g))[0]) / 1e4
                except Exception:  # noqa: BLE001
                    area = None
            d = districts[key] = {"geometry": g, "area_ha": area, "names": {kk: rec.get(low.get(kk)) for kk in ("name_0", "name_1", "name_2", "gid_0", "gid_1", "gid_2") if low.get(kk)},
                                  "by": {}}
        tot = rec.get(total)
        try:
            tot = float(tot)
        except (TypeError, ValueError):
            tot = sum(float(rec.get(y) or 0) for y in years)
        d["by"][k] = {"total": tot, **{y: rec.get(y) for y in years}}
        if n % 20000 == 0 and n:
            print(f"  {n:,} records, {time.time() - t0:.0f} s", flush=True)
    if unknown:
        print(f"agri_linked: kinds not matched to the map's seven: {sorted(unknown)}", flush=True)
    feats, pieces, counts = [], {}, {}
    for key, d in districts.items():
        if not d["geometry"] or not d["by"]:
            continue
        main, v = max(d["by"].items(), key=lambda kv: kv[1]["total"] or 0)
        if not (v["total"] or 0) > 0:
            continue
        area = d["area_ha"]
        share = round(min(1.0, v["total"] / area), 5) if area else None
        nm = ", ".join(str(x) for x in (d["names"].get("name_2"), d["names"].get("name_1"), d["names"].get("name_0")) if x)
        counts[main] = counts.get(main, 0) + 1
        feats.append({"type": "Feature", "geometry": d["geometry"],
                      "properties": {"id": key, "name": nm, "main": main, **({"share": share} if share is not None else {})}})
        props = {"title": nm, "linked to the most tree cover loss": main,
                 "that loss, hectares, 2001 to 2015": round(v["total"], 1),
                 **({"as a share of the district": f"{share * 100:.2f}%"} if share is not None else {}),
                 **({"district area, hectares": round(area)} if area else {}), **d["names"]}
        for k, b in sorted(d["by"].items(), key=lambda kv: -(kv[1]["total"] or 0)):
            props[f"{k}: hectares, 2001 to 2015"] = round(b["total"] or 0, 1)
            for y in years:
                if b.get(y) not in (None, "", 0, 0.0):
                    props[f"{k}: {y.split('_')[1]}"] = round(float(b[y]), 1)
        props["source"] = "Goldman, Weisse, Harris and Schneider 2020, World Resources Institute (CC BY 4.0), via Global Forest Watch"
        pieces[key] = props
    print(f"agri_linked: {len(feats):,} districts with linked loss; led by {counts}", flush=True)
    base = OUT / "pieces"
    base.mkdir(parents=True, exist_ok=True)
    buckets = {}
    for key, props in pieces.items():
        buckets.setdefault(piece_of(key), {})[key] = {"properties": props}
    for hh, d in buckets.items():
        (base / f"{hh}.json.gz").write_bytes(gzip.compress(json.dumps(d, ensure_ascii=False, separators=(",", ":")).encode()))
    import mines  # noqa: E402  sh() and tools()
    mines.tools()
    lines = work / f"{NAME}.geojsonl"
    with open(lines, "w", encoding="utf-8") as fo:
        for f in feats:
            fo.write(json.dumps(f, ensure_ascii=False, separators=(",", ":")) + "\n")
    out = work / f"{NAME}.pmtiles"
    mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", NAME, "-Z0", "-z9", "--detect-shared-borders",
             "--coalesce-densest-as-needed", "--simplification=4", "--no-tile-size-limit", str(lines))
    size = out.stat().st_size
    if size > 95 * 1024 * 1024:
        raise RuntimeError(f"{size / 1e6:.0f} MB is over GitHub's limit")
    TILES.mkdir(exist_ok=True)
    os.replace(out, TILES / f"{NAME}.pmtiles")
    (OUT / "key.json").write_text(json.dumps({"count": len(feats), "kinds": counts, "version": VERSION, "bytes": size,
                                              "years": [y.split("_")[1] for y in years]}, indent=1))
    print(f"agri_linked: {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
