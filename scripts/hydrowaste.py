#!/usr/bin/env python3
"""
HydroWASTE v1.0 (Ehalt Macedo et al., Earth System Science Data 2022; CC BY 4.0):
every one of its 58,502 wastewater treatment plants, for the Culprits row
"Wastewater treatment plants (HydroWASTE)" (round 81, 27 September).

The copy the map drew before was built with points merged: at its deepest zoom
1,090 dots still stood for about 2,800 plants, whose names and figures could
never be opened. This builds the archive again from HydroWASTE's own file:

  tiles/hydrowaste.pmtiles     layer "hydrowaste": every plant at its own
                               place at every zoom, none merged, every column
                               of the file kept, plus "value" (the population
                               it serves) so the glow can weigh it
  hydrowaste/build.json        what it was built from, and the counts

Built once (the database is a fixed release); HYDROWASTE_REBUILD=1 builds it
again.
"""
import csv, io, json, os, pathlib, shutil, sys, tempfile, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mines  # noqa: E402  sh() and tools()

URLS = ["https://figshare.com/ndownloader/files/31910714",
        "https://data.hydrosheds.org/file/HydroWASTE/HydroWASTE_v10.zip"]
OUT = pathlib.Path("tiles/hydrowaste.pmtiles")
STAMP = pathlib.Path("hydrowaste/build.json")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
NUMERIC = {"POP_SERVED", "WASTE_DIS", "DF", "RIVER_DIS", "DESIGN_CAP"}


def fetch():
    last = None
    for u in URLS:
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=600) as r:
                data = r.read()
            print(f"hydrowaste: {len(data) / 1e6:.1f} MB from {u}", flush=True)
            return data, u
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"hydrowaste: {u} did not answer ({e})", flush=True)
    raise SystemExit(f"hydrowaste: no copy of the file could be read ({last}); the archive that is there stays")


def main():
    if OUT.exists() and STAMP.exists() and not os.environ.get("HYDROWASTE_REBUILD"):
        print("hydrowaste: already built from HydroWASTE's own file")
        return
    data, url = fetch()
    rows = None
    if data[:2] == b"PK":
        z = zipfile.ZipFile(io.BytesIO(data))
        names = [n for n in z.namelist() if n.lower().endswith(".csv") and not n.startswith("__MACOSX")]
        print("hydrowaste: files in the package: " + ", ".join(z.namelist()), flush=True)
        if not names:
            raise SystemExit("hydrowaste: no table (.csv) in the package; nothing built")
        text = z.read(sorted(names, key=len)[0]).decode("utf-8-sig", errors="replace")
    else:
        text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows or "LAT_WWTP" not in rows[0]:
        raise SystemExit(f"hydrowaste: the table has no LAT_WWTP column (columns: {list(rows[0]) if rows else []}); nothing built")
    work = pathlib.Path(tempfile.mkdtemp())
    lines = work / "hw.geojsonl"
    kept, nowhere, named = 0, 0, 0
    with open(lines, "w", encoding="utf-8") as fo:
        for r in rows:
            try:
                lat, lon = float(r["LAT_WWTP"]), float(r["LON_WWTP"])
            except (TypeError, ValueError):
                nowhere += 1
                continue
            p = {}
            for k, v in r.items():
                if k is None:
                    continue
                v = (v or "").strip()
                if v == "" or v.upper() in ("NA", "NAN"):
                    continue
                if k in NUMERIC:
                    try:
                        p[k] = float(v) if "." in v else int(v)
                        continue
                    except ValueError:
                        pass
                p[k] = v
            if p.get("WWTP_NAME"):
                named += 1
            if isinstance(p.get("POP_SERVED"), (int, float)):
                p["value"] = p["POP_SERVED"]
            fo.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": p},
                                ensure_ascii=False, separators=(",", ":")) + "\n")
            kept += 1
    mines.tools()
    tmp = work / "hydrowaste.pmtiles"
    # -r1 and no --cluster-*: every plant is drawn at every zoom (asked for 23 September, for every point layer).
    mines.sh("tippecanoe", "-o", str(tmp), "--force", "-q", "-l", "hydrowaste", "-Z0", "-z10", "-r1",
             "--no-feature-limit", "--no-tile-size-limit", str(lines))
    size = tmp.stat().st_size
    if size > 95 * 1024 * 1024:
        raise SystemExit(f"hydrowaste: {size / 1e6:.0f} MB is over GitHub's limit; the archive that is there stays")
    OUT.parent.mkdir(exist_ok=True)
    shutil.move(str(tmp), OUT)
    STAMP.parent.mkdir(exist_ok=True)
    STAMP.write_text(json.dumps({"from": url, "rows": len(rows), "plants_drawn": kept, "no_position": nowhere,
                                 "with_a_name": named, "merged": False, "bytes": size}, indent=1))
    shutil.rmtree(work, ignore_errors=True)
    print(f"hydrowaste: {kept:,} plants tiled ({named:,} with a name in the file, {nowhere:,} with no position), {size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
