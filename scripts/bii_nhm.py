#!/usr/bin/env python3
"""
How intact each place's wildlife communities are, 0 to 100 (round 145b, asked
2 October: Global Safety Net's two intactness halves draw in one colour, so
nothing tells 20 from 45).

The Natural History Museum's Biodiversity Intactness Index (BII), version
2.1.1 limited release (data.nhm.ac.uk, CC BY-NC-SA 4.0: non-commercial use
with credit, shared alike). The index estimates how much of a place's
original community of species remains, on average, compared with before
people changed the land. Read through the museum's CKAN API: every resource of
the dataset is listed in bii/build.json; the newest year's GeoTIFF (in a zip
or not) is drawn in ten steps of 10, teal-to-cobalt, lighter = less intact.

  tiles/own_bii.pmtiles, tiles/own_bii.choices.json, bii/build.json

Monthly (first Monday), or by hand. Stops without guessing when the dataset
offers no GeoTIFF; bii/build.json then lists what it does offer.
"""
import datetime, io, json, os, pathlib, re, sys, tempfile, urllib.request, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

ROW = "own_bii"
PACKAGE = "bii-developed-by-nhm-v2-1-1-limited-release"
API = f"https://data.nhm.ac.uk/api/3/action/package_show?id={PACKAGE}"
OUT_DIR = pathlib.Path("bii")
OUT = pathlib.Path("tiles") / f"{ROW}.pmtiles"
RES = 1 / 12   # about 10 km, the index's own grid
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
CITE = "Biodiversity Intactness Index v2.1.1, Natural History Museum, London (data.nhm.ac.uk, CC BY-NC-SA 4.0)"


def get(url, timeout=300):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def year_of(r):
    ys = [int(y) for y in re.findall(r"(?<!\d)(19\d\d|20\d\d)(?!\d)", f"{r.get('name', '')} {r.get('url', '')}")]
    return max(ys) if ys else 0


def main():
    stamp = OUT_DIR / "build.json"
    today = datetime.date.today()
    if OUT.exists() and stamp.exists() and not (today.weekday() == 0 and today.day <= 7) and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print(f"{ROW}: monthly; not the first Monday")
        return
    OUT_DIR.mkdir(exist_ok=True)
    pkg = json.loads(get(API))["result"]
    res = [{"name": r.get("name"), "format": r.get("format"), "url": r.get("url"), "size": r.get("size")} for r in pkg.get("resources", [])]
    info = {"read": today.isoformat(), "dataset": pkg.get("title"), "licence": pkg.get("license_title") or pkg.get("license_id"),
            "resources": res}
    tifs = [r for r in res if re.search(r"\.(tif|tiff|zip)(\?|$)", r["url"] or "", re.I) or (r["format"] or "").lower() in ("geotiff", "tif", "tiff", "zip")]
    if not tifs:
        info["built"] = False
        info["why"] = "the dataset lists no GeoTIFF or zip; see resources"
        stamp.write_text(json.dumps(info, indent=1, ensure_ascii=False))
        print(f"::warning::{ROW}: no GeoTIFF among {len(res)} resources; listed in {stamp}")
        return
    pick = max(tifs, key=year_of)
    info["file"] = pick
    pyramid.need("rasterio")
    import numpy as np
    tmp = pathlib.Path(tempfile.gettempdir()) / "bii_source"
    tmp.mkdir(exist_ok=True)
    raw = pyramid.download(pick["url"], tmp / ("bii.zip" if pick["url"].lower().split("?")[0].endswith(".zip") else "bii.tif"), ROW)
    path = str(raw)
    if path.endswith(".zip"):
        names = [n for n in zipfile.ZipFile(path).namelist() if n.lower().endswith((".tif", ".tiff"))]
        if not names:
            raise SystemExit(f"{ROW}: the zip holds no GeoTIFF ({zipfile.ZipFile(path).namelist()[:20]})")
        names.sort(key=lambda n: max([int(y) for y in re.findall(r"(?<!\d)(19\d\d|20\d\d)(?!\d)", n)] or [0]))
        info["tif_in_zip"] = names[-1]
        path = f"/vsizip/{path}/{names[-1]}"
    a, west, north = pyramid.read_grid(path, RES, bounds=(-180, -60, 180, 84), resampling="average")
    good = a[~np.isnan(a)]
    if not good.size:
        raise SystemExit(f"{ROW}: nothing read from {path}")
    top = float(np.nanpercentile(good, 99.9))
    scale = 100.0 if top <= 1.5 else 1.0   # stored as 0-1 or as percent
    info["values_read"] = {"min": float(good.min()), "p99_9": top, "scaled_by": scale}
    pct = np.clip(a * scale, 0, 100)
    codes = np.zeros(a.shape, np.uint8)
    ok = ~np.isnan(pct)
    codes[ok] = np.minimum(9, (pct[ok] // 10).astype(np.uint8)) + 1
    del a, pct
    ramp = pyramid.RAMP10
    pal = {i + 1: pyramid.rgba(c, 225) for i, c in enumerate(ramp)}
    pyramid.build(codes, west, north, RES, pal, OUT, 6, how="average",
                  attribution=CITE, name=ROW, meta={"from": pick["url"]})
    key = [[c, f"{i * 10} to {i * 10 + 10} (of 100: the original community left)"] for i, c in enumerate(ramp)]
    pyramid.write_choices(ROW, [{"label": "latest year in the file", "archive": f"tiles/{ROW}.pmtiles", "key": key}])
    info["built"] = True
    stamp.write_text(json.dumps(info, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
