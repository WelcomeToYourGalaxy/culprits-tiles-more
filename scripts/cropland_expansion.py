#!/usr/bin/env python3
"""
Cropland and where it spread, 2003 to 2019: the map's own copy of Potapov et
al.'s cropland maps at 3 km (round 90b, asked 27 September).

Source: Potapov, P. et al. 2022, "Global maps of cropland extent and change
show accelerated cropland expansion in the twenty-first century", Nature Food
3:19-28; the University of Maryland GLAD lab's files at
https://gladxfer.umd.edu/Potapov/Global_Crop/Data/ :
Global_cropland_3km_<year>.tif for 2003, 2007, 2011, 2015 and 2019, and
Global_cropland_3km_netgain.tif / _netloss.tif. The lab states no licence for
them. The 30 m release (four files of up to 1.8 GB a year) is too large for a
copy here.

Each file's values are read as they are; the build log records their range.
Values from 0 to 100 are read as the percent of the cell under crops.

  tiles/potapov_cropland_<year>.pmtiles, _netgain, _netloss   zooms 0 to 6
  tiles/potapov_cropland.choices.json                          the choices and keys

Built once; OWN_REBUILD=1 builds it again.
"""
import os, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

BASE = "https://gladxfer.umd.edu/Potapov/Global_Crop/Data/"
ROW = "potapov_cropland"
PARTS = [("2019", "Global_cropland_3km_2019.tif"), ("2015", "Global_cropland_3km_2015.tif"), ("2011", "Global_cropland_3km_2011.tif"),
         ("2007", "Global_cropland_3km_2007.tif"), ("2003", "Global_cropland_3km_2003.tif"),
         ("net gain, 2003 to 2019", "Global_cropland_3km_netgain.tif"), ("net loss, 2003 to 2019", "Global_cropland_3km_netloss.tif")]
RES = 0.025
STEPS = [0, 5, 15, 30, 60]


def main():
    done = pathlib.Path("tiles") / f"{ROW}.choices.json"
    if done.exists() and not os.environ.get("OWN_REBUILD"):
        print(f"{ROW}: already built")
        return
    pyramid.need("rasterio")
    import numpy as np
    choices = []
    for label, name in PARTS:
        slug = name.replace("Global_cropland_3km_", "").replace(".tif", "")
        out = pathlib.Path("tiles") / f"{ROW}_{slug}.pmtiles"
        try:
            tif = pyramid.download(BASE + name, pathlib.Path(tempfile.gettempdir()) / name, ROW)
        except Exception as e:  # noqa: BLE001
            print(f"{ROW}: {name} could not be fetched ({e}); left out", flush=True)
            continue
        a, west, north = pyramid.read_grid(str(tif), RES, bounds=(-180, -60, 180, 80), resampling="average")
        lo, hi = float(np.nanmin(a)), float(np.nanmax(a))
        print(f"{ROW}: {name}: values {lo} to {hi}", flush=True)
        if hi > 100.5 or lo < -0.5:
            print(f"{ROW}: {name}: values outside 0 to 100; left out rather than guessed at", flush=True)
            continue
        ok = ~np.isnan(a) & (a > 0)
        codes = np.zeros(a.shape, np.uint8)
        what = "of the cell gained as cropland" if "gain" in name else "of the cell lost from cropland" if "loss" in name else "of the cell under crops"
        labels = ["up to 5%", "5 to 15%", "15 to 30%", "30 to 60%", "over 60%"]
        key = [[c, f"{l} {what}"] for c, l in zip(pyramid.RAMP5, labels)]
        if hi <= 1:
            # A file of 0 and 1 marks where the change happened, not a share:
            # every marked cell one colour, said so in the key.
            codes[ok] = 4
            key = [[pyramid.RAMP5[3], "marked in the file: " + ("cropland gained" if "gain" in name else "cropland lost" if "loss" in name else "cropland")]]
        else:
            for i, s in enumerate(STEPS):
                codes[ok & (a > s)] = i + 1
        del a
        pyramid.build(codes, west, north, RES, {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(pyramid.RAMP5)}, out, 6, how="mean",
                      attribution="Potapov et al. 2022, Nature Food; UMD GLAD", name=out.stem,
                      meta={"from": BASE + name, "values": [lo, hi], "steps_percent": STEPS})
        choices.append({"label": label, "archive": f"tiles/{out.name}", "key": key})
    if not choices:
        raise SystemExit(f"{ROW}: nothing built")
    pyramid.write_choices(ROW, choices)


if __name__ == "__main__":
    main()
