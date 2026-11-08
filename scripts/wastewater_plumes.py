#!/usr/bin/env python3
"""
The Global Wastewater Model's coastal nitrogen plumes (Tuholske et al. 2021,
KNB doi:10.5063/F76B09), drawn as raster archives the map reads square by
square:
  tiles/wastewater_plume_{tot,treated,septic,open}.pmtiles
and each one's colour steps in wastewater/plume_<same>.key.json.

The package's Global_N_Coastal_Plumes_tifs.zip (276 MB) holds four global
rasters of about 3 GB each: global_effluent_2015_{tot,treated,septic,open}_N.tif.
Each is read out of the zip one at a time on the runner, read at a quarter of
its resolution (each cell the average of the sixteen under it, about 4 km), and
drawn to zoom 6 with the same builder as the soy and maize maps
(scripts/food_crops.py: log scale, dark plum to bone, zero left clear, the
largest value kept wider out). The unit is not written in the files; the key
says the package's figure per cell.

By hand only (Actions tab, "wastewater_plumes"); the package is a fixed release.
"""
import os, pathlib, shutil, subprocess, sys, tempfile, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import food_crops  # noqa: E402

ZIP = "https://knb.ecoinformatics.org/knb/d1/mn/v2/object/urn%3Auuid%3Aefef18ef-416e-4d4d-9190-f17485c02c15"
KINDS = {"tot": "all human wastewater", "treated": "sewage treatment", "septic": "septic systems", "open": "untreated waste"}
SHRINK = 4


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("wastewater_plumes: by hand only")
        return
    food_crops.need()
    import numpy as np, rasterio
    from rasterio.enums import Resampling
    work = pathlib.Path(tempfile.mkdtemp())
    zpath = work / "plumes.zip"
    print("wastewater_plumes: downloading the plume rasters (276 MB)", flush=True)
    with urllib.request.urlopen(urllib.request.Request(ZIP, headers={"User-Agent": "Culprits atlas"}), timeout=1800) as r, open(zpath, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    z = zipfile.ZipFile(zpath)
    names = {n.rsplit("/", 1)[-1]: n for n in z.namelist()}
    for key, label in KINDS.items():
        member = names.get(f"global_effluent_2015_{key}_N.tif")
        if not member:
            print(f"  global_effluent_2015_{key}_N.tif is not in the zip; left out", flush=True)
            continue
        tif = work / f"{key}.tif"
        with z.open(member) as src, open(tif, "wb") as out:
            shutil.copyfileobj(src, out, 1 << 22)
        with rasterio.open(tif) as ds:
            h, w = ds.height // SHRINK, ds.width // SHRINK
            arr = ds.read(1, out_shape=(h, w), resampling=Resampling.average).astype("float64")
            t = ds.transform * ds.transform.scale(ds.width / w, ds.height / h)
            crs, nod = ds.crs, ds.nodata
            print(f"  {member}: {ds.width} x {ds.height} cells in {crs}, read as {w} x {h}", flush=True)
        tif.unlink()
        if crs is None:
            print(f"  {member} carries no projection; not drawn rather than placed by a guess", flush=True)
            continue
        food_crops.build_array(arr, t, crs, nod, f"wastewater_plume_{key}",
                               f"Nitrogen from {label} in coastal waters, 2015 (Tuholske et al. 2021)",
                               "Tuholske et al. 2021, Global Wastewater Model (KNB doi:10.5063/F76B09)", "wastewater")
        # The key goes beside the others, named for the plume.
        k = pathlib.Path("wastewater") / f"wastewater_plume_{key}.key.json"
        if k.exists():
            k.rename(pathlib.Path("wastewater") / f"plume_{key}.key.json")
        del arr
    shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
