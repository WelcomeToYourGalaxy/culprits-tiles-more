#!/usr/bin/env python3
"""
The world's rivers, free-flowing or broken by dams and reservoirs (round 100b,
asked 28 September, for Biodiversity loss > Fish).

Source: Grill et al. 2019, "Mapping the world's free-flowing rivers", Nature
569, 215-221; data set and technical documentation on figshare
(doi 10.6084/m9.figshare.7688801), CC BY 4.0. Every river reach of HydroRIVERS
(about 8.5 million) with its connectivity status index (CSI, 0 to 100): how far
dams, reservoirs, roads, urban areas and water use have cut the river up or
changed its flow. The paper's classes, as its documentation gives them:
a river is free-flowing where the CSI is 95% or more over its whole length;
a reach with CSI 95% or more on a river that is not free-flowing as a whole
has "good connectivity status"; below 95% the reach is impacted.

Every reach is drawn: each is burned into a grid of 1/60 degree (about 2 km),
the most impacted reach in a cell showing, so a broken river is never hidden
under a free one; wider out each map pixel shows the most impacted cell under
it. Coloured in the paper's three classes.

  tiles/fish_rivers.pmtiles          zooms 0 to 8
  tiles/fish_rivers.choices.json     the row's choice and its key
  fish/rivers_build.json             layer read, fields, counts by class

Built once; FISH_REBUILD=1 builds it again.
"""
import json, os, pathlib, re, subprocess, sys, tempfile, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pyramid  # noqa: E402

ARTICLE = "https://api.figshare.com/v2/articles/7688801"
ROW = "fish_rivers"
OUT = pathlib.Path("tiles") / f"{ROW}.pmtiles"
RES = 1 / 60
# code: (colour, words), the paper's own three classes. 3 wins a cell.
CLASSES = {1: ("#8FD6E8", "free-flowing river (CSI 95% or more along its whole length)"),
           2: ("#3FA9C2", "good connectivity: this reach 95% or more, the river as a whole not free-flowing"),
           3: ("#0E2F66", "impacted: CSI under 95%")}


def main():
    if OUT.exists() and (pathlib.Path("tiles") / f"{ROW}.choices.json").exists() and not os.environ.get("FISH_REBUILD"):
        print(f"{ROW}: already built")
        return
    pyramid.need("rasterio")
    import numpy as np
    import mines
    mines.tools()
    import urllib.request
    with urllib.request.urlopen(urllib.request.Request(ARTICLE, headers={"User-Agent": "Culprits atlas build"}), timeout=120) as r:
        art = json.loads(r.read())
    gdb = max((f for f in art["files"] if f["name"].lower().endswith(".zip")), key=lambda f: f["size"])
    work = pathlib.Path(tempfile.mkdtemp())
    z = pyramid.download(gdb["download_url"], work / "ffr.zip", ROW)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(work)
    src = next(p for p in work.rglob("*.gdb") if p.is_dir())
    info = subprocess.run(["ogrinfo", "-ro", "-so", str(src)], capture_output=True, text=True).stdout
    print(info, flush=True)
    # ogrinfo lists layers as "1: name (type)", or, in a geodatabase with
    # groups, as "Layer: name (type)" (round 111b: GDAL 3.8 printed
    # "Layer: FFR_river_network_v1 (Multi Line String)" and none were found).
    layers = [l.split(":", 1)[1].split("(")[0].strip() for l in info.splitlines()
              if ":" in l and (l.strip()[:1].isdigit() or l.strip().lower().startswith("layer:"))]
    if not layers:
        layers = [l.strip() for l in subprocess.run(["ogrinfo", "-ro", "-q", "-so", str(src)], capture_output=True, text=True).stdout.splitlines() if l.strip()]
        layers = [re.sub(r"^\d+:\s*|^Layer:\s*", "", l).split(" (")[0].strip() for l in layers]
    print(f"{ROW}: layers {layers}", flush=True)
    layer = (next((l for l in layers if "river" in l.lower() and "network" in l.lower()), None)
             or next((l for l in layers if "river" in l.lower()), None) or (layers[0] if len(layers) == 1 else None))
    if not layer:
        raise SystemExit(f"{ROW}: no river layer among {layers}")
    fields = subprocess.run(["ogrinfo", "-ro", "-so", str(src), layer], capture_output=True, text=True).stdout
    print(fields, flush=True)
    names = {l.split(":")[0].strip().upper(): l.split(":")[0].strip() for l in fields.splitlines() if ":" in l and "(" in l.split(":", 1)[1]}
    csi = names.get("CSI")
    ff = names.get("CSI_FF1") or names.get("CSI_FF")
    if not csi:
        raise SystemExit(f"{ROW}: no CSI field in {layer}; see the fields above")
    case = (f"CASE WHEN {ff} = 1 THEN 1 WHEN {csi} >= 95 THEN 2 ELSE 3 END" if ff
            else f"CASE WHEN {csi} >= 95 THEN 1 ELSE 3 END")
    tif = work / "rivers.tif"
    # Burned in order of the class, so the most impacted reach in a cell is last and stays.
    sql = f"SELECT {case} AS cls, * FROM \"{layer}\" ORDER BY cls"
    mines.sh("gdal_rasterize", "-dialect", "SQLite", "-sql", sql, "-a", "cls", "-at", "-ot", "Byte", "-a_nodata", "0",
             "-te", "-180", "-90", "180", "90", "-tr", str(RES), str(RES), "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES", str(src), str(tif))
    import rasterio
    with rasterio.open(tif) as ds:
        grid = ds.read(1)
    counts = {int(k): int(v) for k, v in zip(*np.unique(grid, return_counts=True)) if k}
    print(f"{ROW}: cells by class {counts}", flush=True)
    if not counts:
        raise SystemExit(f"{ROW}: nothing burned")
    pal = {k: pyramid.rgba(c) for k, (c, _) in CLASSES.items()}
    pyramid.build(grid, -180.0, 90.0, RES, pal, OUT, 8, how="max", attribution="Grill et al. 2019, Nature (CC BY 4.0)", name=ROW,
                  meta={"from": gdb["download_url"], "layer": layer, "fields": {"csi": csi, "free_flowing": ff}, "cells": counts})
    key = [[c, w] for k, (c, w) in CLASSES.items() if k in counts or (k == 2 and ff)]
    pyramid.write_choices(ROW, [{"label": "every river reach", "archive": f"tiles/{ROW}.pmtiles", "key": key}])
    pathlib.Path("fish").mkdir(exist_ok=True)
    (pathlib.Path("fish") / "rivers_build.json").write_text(json.dumps({"file": gdb, "layer": layer, "csi": csi, "free_flowing_field": ff,
                                                                         "cells_by_class": counts}, indent=1))


if __name__ == "__main__":
    main()
