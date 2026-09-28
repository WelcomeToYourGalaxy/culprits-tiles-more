#!/usr/bin/env python3
"""
Where forest could grow back: the map's own copy of the constrained
reforestation potential of Fesenmyer et al. 2025 (round 90b, asked 27
September, in place of Global Safety Net's "Constrained Reforestation" layer).

Source: Fesenmyer, K.A. et al. 2025, Nature Communications,
doi:10.1038/s41467-025-59799-8; figshare doi:10.6084/m9.figshare.27335799 v3
(CC BY 4.0), constrained_reforestation_ha.tif: hectares that could be
reforested in each 1 km pixel, leaving out cropland, towns and natural
grasslands and savannas.

  tiles/own_reforestation.pmtiles        zooms 0 to 7, five steps of hectares
                                         per pixel, the mean of the pixels under
                                         each map pixel
  tiles/own_reforestation.choices.json   the row's choice and its key

Built once; OWN_REBUILD=1 builds it again.
"""
import os, pathlib, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

URL = "https://ndownloader.figshare.com/files/54788645"
ROW = "own_reforestation"
OUT = pathlib.Path("tiles") / f"{ROW}.pmtiles"
RES = 0.01
STEPS = [0, 10, 25, 50, 75]        # hectares in a 1 km pixel (100 ha)


def main():
    if OUT.exists() and (pathlib.Path("tiles") / f"{ROW}.choices.json").exists() and not os.environ.get("OWN_REBUILD"):
        print(f"{ROW}: already built")
        return
    pyramid.need("rasterio")
    import numpy as np
    tif = pyramid.download(URL, pathlib.Path(tempfile.gettempdir()) / "constrained_reforestation_ha.tif", ROW)
    a, west, north = pyramid.read_grid(str(tif), RES, resampling="average")
    ok = ~np.isnan(a) & (a > 0)
    codes = np.zeros(a.shape, np.uint8)
    for i, lo in enumerate(STEPS):
        codes[ok & (a > lo)] = i + 1
    print(f"{ROW}: {int(ok.sum()):,} cells with room for forest; largest {float(np.nanmax(a)):.1f} ha", flush=True)
    del a
    pal = {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(pyramid.RAMP5)}
    pyramid.build(codes, west, north, RES, pal, OUT, 7, how="mean",
                  attribution="Fesenmyer et al. 2025, constrained reforestation potential (CC BY 4.0)", name=ROW,
                  meta={"from": URL, "file": "constrained_reforestation_ha.tif", "unit": "hectares per 1 km pixel", "steps": STEPS})
    labels = ["up to 10 ha", "10 to 25 ha", "25 to 50 ha", "50 to 75 ha", "over 75 ha"]
    pyramid.write_choices(ROW, [{"label": "hectares per square km", "archive": f"tiles/{ROW}.pmtiles",
                                 "key": [[c, l] for c, l in zip(pyramid.RAMP5, labels)]}])


if __name__ == "__main__":
    main()
