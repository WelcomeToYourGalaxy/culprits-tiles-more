#!/usr/bin/env python3
"""
Critical habitat, on land and at sea: the map's own copy of UNEP-WCMC's Global
Critical Habitat screening layer (round 90b, asked 27 September, in place of
Global Safety Net's two "Critical habitats" layers).

Source: UNEP-WCMC, Global Critical Habitat screening layer, basic version 2.1
(Dunnett, S. et al. 2025, Scientific Data 12:1812; doi:10.34892/snwv-a025;
CC BY 4.0), a GeoTIFF at 30 arc-seconds (about 1 km): places that meet the
International Finance Corporation's Performance Standard 6 criteria for
critical habitat, as likely or potential.

The classes' names are read from the file's own attribute table; if it has
none, from UNEP-WCMC's public image service of the same layer; if neither
answers, each class is shown by its number, and the build log says so.

  tiles/own_critical_habitat.pmtiles       zooms 0 to 7; each map pixel the
                                           highest class under it
  tiles/own_critical_habitat.choices.json  the row's choice and its key

Built once; OWN_REBUILD=1 builds it again.
"""
import json, os, pathlib, sys, tempfile, urllib.request, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

URL = "https://datadownload-production.s3.us-east-1.amazonaws.com/WCMC_043_GlobalCH_Basic_IFCPS6_2025.zip"
SERVICE = "https://data-gis.unep-wcmc.org/server/rest/services/GlobalCH_2023_Basic/ImageServer"
ROW = "own_critical_habitat"
OUT = pathlib.Path("tiles") / f"{ROW}.pmtiles"
RES = 1 / 120
PAPER_NAMES = {1: "Potential critical habitat", 10: "Likely critical habitat"}


def names_from_service():
    try:
        with urllib.request.urlopen(urllib.request.Request(SERVICE + "/rasterAttributeTable?f=json",
                                                           headers={"User-Agent": "Culprits atlas build"}), timeout=60) as r:
            j = json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        print(f"{ROW}: the image service's attribute table did not answer ({e})", flush=True)
        return {}
    out = {}
    for f in j.get("features", []):
        a = f.get("attributes", {})
        v = a.get("Value", a.get("VALUE", a.get("value")))
        text = [x for k, x in a.items() if isinstance(x, str) and k.lower() not in ("objectid",)]
        if v is not None and text:
            out[int(v)] = text[0]
    return out


def main():
    if OUT.exists() and (pathlib.Path("tiles") / f"{ROW}.choices.json").exists() and not os.environ.get("OWN_REBUILD"):
        print(f"{ROW}: already built")
        return
    pyramid.need("rasterio")
    import numpy as np
    import rasterio
    z = pyramid.download(URL, pathlib.Path(tempfile.gettempdir()) / "globalch.zip", ROW)
    zf = zipfile.ZipFile(z)
    tifs = [n for n in zf.namelist() if n.lower().endswith((".tif", ".tiff"))]
    print(f"{ROW}: in the zip: {zf.namelist()}", flush=True)
    if not tifs:
        raise SystemExit(f"{ROW}: no GeoTIFF in the zip")
    path = f"/vsizip/{z}/{tifs[0]}"
    names = {}
    # A .tif.aux.xml or .vat.dbf beside it may carry the names; rasterio reads
    # GDAL's category names through the band's tags where the driver gives them.
    with rasterio.open(path) as src:
        tags = src.tags(1)
        print(f"{ROW}: {src.width}x{src.height}, {src.dtypes[0]}, nodata {src.nodata}; band tags {tags}", flush=True)
    dbf = [n for n in zf.namelist() if n.lower().endswith(".vat.dbf")]
    if dbf:
        try:
            pyramid.need("dbfread")
            from dbfread import DBF
            p = pathlib.Path(tempfile.gettempdir()) / "ch.vat.dbf"
            p.write_bytes(zf.read(dbf[0]))
            for rec in DBF(str(p)):
                v = rec.get("Value", rec.get("VALUE"))
                text = [x for k, x in rec.items() if isinstance(x, str) and x.strip()]
                if v is not None and text:
                    names[int(v)] = text[0]
        except Exception as e:  # noqa: BLE001
            print(f"{ROW}: the attribute table could not be read ({e})", flush=True)
    if not names:
        names = names_from_service()
    # Round 99b (asked 28 September: "class 1" and "class 10" with no names):
    # the paper's own Data Records give the values: 0 unclassified, 1 potential
    # critical habitat, 10 likely critical habitat (Dunnett et al. 2025,
    # Scientific Data, doi 10.1038/s41597-025-06117-y). Used where the file
    # carries no names of its own.
    for v, t in PAPER_NAMES.items():
        names.setdefault(v, t)
    a, west, north = pyramid.read_grid(path, RES, bounds=(-180, -85, 180, 85), resampling="max")
    vals = sorted(int(v) for v in np.unique(a[~np.isnan(a)]) if v > 0)
    print(f"{ROW}: classes in the file {vals}; names {names}", flush=True)
    if not vals:
        raise SystemExit(f"{ROW}: no classes read")
    if len(vals) > 5:
        raise SystemExit(f"{ROW}: {len(vals)} classes, more than a screening layer should have; look at the file before drawing it")
    ramp = pyramid.RAMP5[1:] if len(vals) <= 4 else pyramid.RAMP5
    ramp = ramp[-len(vals):] if len(vals) < len(ramp) else ramp
    codes = np.zeros(a.shape, np.uint8)
    for i, v in enumerate(vals):
        codes[a == v] = i + 1
    del a
    pal = {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(ramp)}
    pyramid.build(codes, west, north, RES, pal, OUT, 7, how="max",
                  attribution="UNEP-WCMC Global Critical Habitat screening layer v2.1, Dunnett et al. 2025 (CC BY 4.0)", name=ROW,
                  meta={"from": URL, "file": tifs[0], "classes": vals, "names": {str(k): v for k, v in names.items()}})
    key = [[c, names.get(v, f"class {v} in the file (no name given)")] for c, v in zip(ramp, vals)]
    pyramid.write_choices(ROW, [{"label": "land and sea", "archive": f"tiles/{ROW}.pmtiles", "key": key}])


if __name__ == "__main__":
    main()
