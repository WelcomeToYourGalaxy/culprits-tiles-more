#!/usr/bin/env python3
"""
Where towns and cities are projected to spread, 2015 to 2100, for the
Invasion of non-humans map (round nh3, asked 16 October).

Source: Chen, G. et al. 2020, "Global projections of future urban land
expansion under shared socioeconomic pathways", Nature Communications 11:
537; data: "A global urban land expansion product at 1-km resolution for 2015
to 2100 based on the SSP scenarios", PANGAEA doi:10.1594/PANGAEA.905890,
CC BY-NC-SA 4.0 (non-commercial, credit, and what is made from it shared under
the same licence: these map files are, under CC BY-NC-SA 4.0).

For each of the five Shared Socioeconomic Pathways (SSP1 to SSP5, the IPCC's
storylines of how the world could develop), every 1 km cell is coloured by
the year the projection first makes it urban: already urban in 2015, then each
ten-year step to 2100. Which files, values and years were read is written to
the build file.

  nonhuman/urban2100.json, nonhuman/urban2100/*.pmtiles, nonhuman/urban2100.build.json

Round nh11: the files code each cell 0 (sea or no data), 1 (land, not urban)
and 2 (urban); round nh3 took every cell above 0 as urban, so the whole
land was drawn in the first colour. Only 2 is urban now, and the authors'
2015 map (global_urban_2015.tif, the start of every pathway) is the first
step.

A fixed release: built once (and once more after round nh11's mend);
URBAN2100_REBUILD=1 builds again.
"""
import os, pathlib, re, sys, tempfile, time, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "urban2100"
ZIP = "https://hs.pangaea.de/Maps/ChenG-etal_2019/Global-urban-product_SSPs_2015_2100.zip"
START, BUDGET = time.time(), 140 * 60
TOP = 7       # a zoom-7 pixel is about 1.2 km, close to the 1 km cells
# Already urban in 2015 in bone; each later step from rose to deep plum.
COLOURS = ["#E9E1D3", "#E2B8C4", "#D9A2B2", "#D08A9C", "#BD7690", "#A86584", "#935878", "#7E4C6C", "#6A4060", "#563554"]


def main():
    st = nh.read_stamp(NAME)
    rebuild = os.environ.get("URBAN2100_REBUILD") or st.get("version") != 2
    if (nh.OUT / "urban2100.json").exists() and st.get("complete") and not rebuild:
        print("urban2100: built; a fixed release (set URBAN2100_REBUILD=1 to build again)")
        return
    pyr = nh.lib_pyramid()
    pyr.need("rasterio")
    import numpy as np
    import rasterio
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp()) / "urban2100"
    work.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(nh.download(ZIP, work / "urban.zip", "urban projections"))
    names = [n for n in z.namelist() if re.search(r"\.(tif|tiff)$", n, re.I)]
    z.extractall(work / "x")
    by = {}
    for n in names:
        m = re.search(r"ssp\s*_?([1-5])", n, re.I)
        y = re.search(r"(?<!\d)(20[1-9]\d|2100)(?!\d)", n.split("/")[-1])
        if m and y:
            by.setdefault(f"SSP{m.group(1)}", {})[int(y.group(1))] = str(work / "x" / n)
    base = next((n for n in names if re.search(r"global_urban_2015", n, re.I)), None)
    if base:
        for v in by.values():
            v.setdefault(2015, str(work / "x" / base))
    report = {"files": names[:200], "read as": {k: sorted(v) for k, v in by.items()}}
    if not by:
        nh.write_stamp(NAME, dict(report, failed=True, error="no file names with an SSP and a year"))
        raise SystemExit("urban2100: no SSP files found")
    choices, complete = [], True
    for ssp in sorted(by):
        years = sorted(by[ssp])
        out = nh.OUT / "urban2100" / f"{ssp.lower()}.pmtiles"
        pal = {i + 1: pyr.rgba(c, 235) for i, c in enumerate(COLOURS)}
        key = [[COLOURS[min(k, len(COLOURS) - 1)], ("urban in " if k == 0 else "becomes urban by ") + str(y)] for k, y in enumerate(years)]
        if out.exists() and not rebuild:
            choices.append({"label": ssp, "archive": f"{pyr.PAGES}nonhuman/urban2100/{out.name}", "key": key})
            continue
        if time.time() - START > BUDGET:
            complete = False
            break
        code = None
        geo = None
        for k, y in enumerate(years):
            with rasterio.open(by[ssp][y]) as src:
                if src.crs is not None and src.crs.to_epsg() != 4326:
                    a, w, nn = pyr.read_grid(by[ssp][y], 1 / 60, resampling="max")
                    g = (w, nn, 1 / 60)
                    a = np.nan_to_num(a, nan=0)
                else:
                    a = src.read(1)
                    t = src.transform
                    g = (t.c, t.f, t.a)
                    if src.nodata is not None:
                        a = np.where(a == src.nodata, 0, a)
            if k == 0:
                report.setdefault("values", {})[f"{ssp} {y}"] = [float(v) for v in np.unique(a)[:20]]
            urban = (a > 1.5) & (a < 2.5)      # 2 is urban; 1 land, 0 sea, 255 no data
            if code is None:
                code = np.zeros(urban.shape, np.uint8)
                geo = g
            code[(code == 0) & urban] = min(k + 1, len(COLOURS))
            del a, urban
        pyr.build(code, geo[0], geo[1], geo[2], pal, out, TOP, how="max", attribution="Chen et al. 2020, PANGAEA (CC BY-NC-SA 4.0)", name=out.stem, meta={"ssp": ssp, "years": years})
        choices.append({"label": ssp, "archive": f"{pyr.PAGES}nonhuman/urban2100/{out.name}", "key": key})
        del code
    nh.write_json("urban2100.json", {"source": "Chen et al. 2020, Nature Communications 11: 537; PANGAEA doi:10.1594/PANGAEA.905890", "licence": "CC BY-NC-SA 4.0",
                                     "choices": choices}, compact=False)
    nh.write_stamp(NAME, dict(report, complete=complete, version=2))


if __name__ == "__main__":
    main()
