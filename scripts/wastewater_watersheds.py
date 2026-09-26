#!/usr/bin/env python3
"""
The Global Wastewater Model's watersheds (Tuholske et al. 2021, KNB
doi:10.5063/F76B09): the land each coastal outlet drains, as shapes, for the
Culprits row "Nitrogen from human wastewater, by the watershed it drains from"
(asked for 23 September).

Downloads N_PourPoint_And_Watershed.zip (403 MB) from KNB, finds the watershed
shapefile in it, turns its Mollweide coordinates into longitude and latitude
(tested, as the pour points were: every vertex must lie inside the Mollweide
world, else nothing is built), and tiles every watershed:

  tiles/wastewater_watersheds.pmtiles   layer "watersheds": each shape with its
                                        basin id and its total nitrogen (value)
  wastewater/watersheds.key.json        the steps the map shades by, and the count

Every other field is already in wastewater/pieces (written with the pour
points, found by the same basin id), so the map reads it from there on a click.
If the archive is too big for GitHub at zoom 10, it is made again one zoom
shallower, down to 7; nothing is dropped from it.

By hand only (Actions tab, "wastewater_watersheds").
"""
import io, json, math, os, pathlib, shutil, subprocess, sys, tempfile, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

URL = "https://knb.ecoinformatics.org/knb/d1/mn/v2/object/urn:uuid:af8d0bd6-dc0c-4149-a3cd-93b5aed71f7c"
OUT = pathlib.Path("tiles/wastewater_watersheds.pmtiles")
KEY = pathlib.Path("wastewater/watersheds.key.json")
LIMIT = 95e6
A = 6378137.0
SQ2 = math.sqrt(2)


def moll_inv(x, y):
    theta = math.asin(max(-1.0, min(1.0, y / (SQ2 * A))))
    lat = math.asin(max(-1.0, min(1.0, (2 * theta + math.sin(2 * theta)) / math.pi)))
    c = math.cos(theta)
    lon = math.pi * x / (2 * SQ2 * A * c) if c > 1e-12 else 0.0
    return round(math.degrees(lon), 5), round(math.degrees(lat), 5)


def inside(x, y):
    return (x / (2 * SQ2 * A)) ** 2 + (y / (SQ2 * A)) ** 2 <= 1 + 1e-9


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("wastewater_watersheds: by hand only")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyshp"], check=True)
    import shapefile, mines
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    zpath = work / "n.zip"
    print("wastewater_watersheds: downloading the model's N package (403 MB)", flush=True)
    with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "Culprits atlas"}), timeout=3600) as r, open(zpath, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 22)
    z = zipfile.ZipFile(zpath)
    # macOS's hidden copies (__MACOSX/, ._name) are not the data: the first run
    # (23 September) found one beside the real watershed file and stopped.
    stems = sorted({n[:-4] for n in z.namelist() if n.lower().endswith(".shp")
                    and not n.startswith("__MACOSX") and not n.rsplit("/", 1)[-1].startswith("._")})
    print("wastewater_watersheds: shapefiles in the package: " + ", ".join(stems), flush=True)
    pick = [s for s in stems if ("watershed" in s.lower() or "basin" in s.lower()) and "countr" not in s.lower() and "point" not in s.lower()]
    if len(pick) != 1:
        sys.exit(f"wastewater_watersheds: expected one watershed shapefile, found {pick}; nothing built")
    stem = pick[0]
    for ext in ("shp", "shx", "dbf"):
        z.extract(f"{stem}.{ext}", work)
    rd = shapefile.Reader(str(work / stem), encoding="utf-8")
    x0, y0, x1, y1 = rd.bbox
    lonlat = -181 <= x0 <= x1 <= 181 and -91 <= y0 <= y1 <= 91
    names = [f[0] for f in rd.fields[1:]]
    if "basin_id" not in names or "tot_N" not in names:
        sys.exit(f"wastewater_watersheds: the table has no basin_id or tot_N (fields: {names}); nothing built")
    lines = work / "ws.geojsonl"
    values, count, outside = [], 0, 0
    with open(lines, "w", encoding="utf-8") as fo:
        for sr in rd.iterShapeRecords():
            g = sr.shape.__geo_interface__
            if not g or not g.get("coordinates"):
                continue
            rec = dict(zip(names, sr.record))
            if not lonlat:
                def conv(c):
                    nonlocal outside
                    if isinstance(c[0], (int, float)):
                        if not inside(c[0], c[1]):
                            outside += 1
                        return list(moll_inv(c[0], c[1]))
                    return [conv(x) for x in c]
                g = {"type": g["type"], "coordinates": conv(g["coordinates"])}
            v = rec.get("tot_N")
            v = float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None
            if v is not None and v > 0:
                values.append(v)
            fo.write(json.dumps({"type": "Feature", "geometry": g, "properties": {"id": str(rec.get("basin_id")), "value": v}},
                                separators=(",", ":")) + "\n")
            count += 1
    if outside:
        sys.exit(f"wastewater_watersheds: {outside:,} vertices fall outside the Mollweide world, so the projection is not known; nothing built")
    print(f"wastewater_watersheds: {count:,} watersheds read from {stem}", flush=True)
    for top in (10, 9, 8, 7):
        mines.sh("tippecanoe", "-o", str(work / "ws.pmtiles"), "--force", "-q", "-Z0", f"-z{top}", "-l", "watersheds",
                 "--no-feature-limit", "--no-tile-size-limit", "--detect-shared-borders", str(lines))
        size = (work / "ws.pmtiles").stat().st_size
        print(f"wastewater_watersheds: to zoom {top}: {size / 1e6:.1f} MB", flush=True)
        if size <= LIMIT:
            break
    else:
        sys.exit("wastewater_watersheds: even to zoom 7 the archive is over GitHub's limit; nothing saved")
    OUT.parent.mkdir(exist_ok=True)
    shutil.move(str(work / "ws.pmtiles"), OUT)
    values.sort()
    # Six steps at equal shares of the watersheds that carry any nitrogen, so each
    # shade holds about as many as the next; the breaks are the values themselves.
    breaks = sorted({round(values[int(len(values) * q / 7)], 3) for q in range(1, 7)}) if values else []
    KEY.parent.mkdir(exist_ok=True)
    KEY.write_text(json.dumps({"count": count, "breaks": breaks, "field": "tot_N", "zoom": top, "from": stem,
                               "source": "Tuholske et al. 2021, KNB doi:10.5063/F76B09"}, indent=1), encoding="utf-8")
    shutil.rmtree(work, ignore_errors=True)
    print(f"wastewater_watersheds: saved {OUT} and {KEY}")


if __name__ == "__main__":
    main()
