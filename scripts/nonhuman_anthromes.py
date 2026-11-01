#!/usr/bin/env python3
"""
How people have taken over the land, 10,000 BCE to 2017, for the Invasion of
non-humans map: the timeline the owner's page links to (footnote 14).

Source: Ellis, E.C. et al. 2021, "People have shaped most of terrestrial
nature for at least 12,000 years", PNAS 118(17): e2023483118, and the
Anthromes 12K data on Harvard Dataverse. The first of the datasets below that
holds anthrome maps GDAL can read is used (CC0 for the first two, CC BY 4.0
for the third); which dataset and files, and how each time step was named,
are written to the build file.

Each time step is drawn in the authors' classes (codes 11 to 63; 70, no data,
is left out). Wider out, where several places share one dot of the map, the
dot shows the most intensively used kind among them (settlements over
villages over cropland over rangeland over used woodland over wild land), so
the spread of use shows from the world view; closer in every place is its
own class.

  nonhuman/anthromes.json, nonhuman/anthromes/*.pmtiles, nonhuman/anthromes.build.json

A fixed release: built once; ANTHROMES_REBUILD=1 builds again.
"""
import json, os, pathlib, re, sys, tempfile, time, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "anthromes"
DV = "https://dataverse.harvard.edu"
DATASETS = ["doi:10.7910/DVN/G0QDNQ", "doi:10.7910/DVN/MWMWPH", "doi:10.7910/DVN/E3H3AK"]
TOP = 4   # a zoom-4 pixel is about 10 km, close to the maps' own 5 arc-minutes (about 9 km)
START, BUDGET = time.time(), 140 * 60
# The authors' classes: code, name, colour. Listed from most to least
# intensively used; the drawing codes run the other way so "max" keeps the
# most used.
CLASSES = [
    (11, "Urban", "#F2ECE0"), (12, "Mixed settlements", "#DCD0BF"),
    (21, "Rice villages", "#D597A6"), (22, "Irrigated villages", "#C2849A"), (23, "Rainfed villages", "#AC728A"), (24, "Pastoral villages", "#966279"),
    (31, "Residential irrigated croplands", "#0C2E5E"), (32, "Residential rainfed croplands", "#13447A"), (33, "Populated croplands", "#1E6FA8"), (34, "Remote croplands", "#2E8FBA"),
    (41, "Residential rangelands", "#46AACB"), (42, "Populated rangelands", "#6FC2DA"), (43, "Remote rangelands", "#9CD6E6"),
    (51, "Residential woodlands", "#6A5E7A"), (52, "Populated woodlands", "#7C7090"), (53, "Remote woodlands", "#8E84A4"), (54, "Inhabited drylands", "#A39AB6"),
    (61, "Wild woodlands", "#2F4A55"), (62, "Wild drylands", "#4A5560"), (63, "Ice", "#C9D2D8"),
]
DRAW = {code: len(CLASSES) - i for i, (code, _, _) in enumerate(CLASSES)}   # 11 -> 20 ... 63 -> 1


def year_of(label):
    """-10000 for 10000BC / 10,000 BCE, 2017 for 2017AD / 2017 CE, else None."""
    s = str(label).replace(",", "")
    m = re.search(r"(\d{1,5})\s*_?(bce|bc|ce|ad)\b", s, re.I) or re.search(r"(?<!\d)(\d{1,5})(bce|bc|ce|ad)(?![a-z])", s, re.I)
    if m:
        y = int(m.group(1))
        return -y if m.group(2).lower().startswith("b") else y
    m = re.search(r"(?<!\d)(1[0-9]{3}|20[0-2][0-9])(?!\d)", s)
    return int(m.group(1)) if m else None


def words(y):
    return f"{-y:,} BCE" if y < 0 else f"{y} CE"


def files_of(doi):
    j = nh.get_json(f"{DV}/api/datasets/:persistentId/versions/:latest/files?persistentId={doi}")
    return [(f["dataFile"]["id"], f["dataFile"].get("filename") or f.get("label"), f["dataFile"].get("filesize") or 0) for f in j.get("data", [])]


def rasters_in(paths):
    """(path for GDAL, band, label) for every raster band found."""
    import rasterio
    found = []
    for p in paths:
        s = str(p)
        cands = []
        if s.lower().endswith(".zip"):
            z = zipfile.ZipFile(p)
            cands = [f"zip://{p}!/{n}" for n in z.namelist() if re.search(r"\.(tif|tiff|asc|nc|img|grd|bil|flt)$", n, re.I)]
        elif re.search(r"\.(tif|tiff|asc|nc|img|grd|bil|flt)$", s, re.I):
            cands = [s]
        for c in cands:
            try:
                with rasterio.open(c) as src:
                    subs = list(src.subdatasets or [])
                    if subs:
                        for sd in subs:
                            with rasterio.open(sd) as s2:
                                for b in range(1, s2.count + 1):
                                    found.append((sd, b, (s2.descriptions[b - 1] or "") + " " + json.dumps(s2.tags(b)) + " " + sd))
                    else:
                        for b in range(1, src.count + 1):
                            found.append((c, b, (src.descriptions[b - 1] or "") + " " + json.dumps(src.tags(b)) + " " + c.split("/")[-1]))
            except Exception as e:
                print(f"  {c}: not readable ({e})", flush=True)
    return found


def main():
    st = nh.read_stamp(NAME)
    if (nh.OUT / "anthromes.json").exists() and st.get("complete") and not os.environ.get("ANTHROMES_REBUILD"):
        print("anthromes: built; a fixed release (set ANTHROMES_REBUILD=1 to build again)")
        return
    pyr = nh.lib_pyramid()
    pyr.need("rasterio")
    import numpy as np
    import rasterio
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp()) / "anthromes"
    work.mkdir(parents=True, exist_ok=True)
    report, chosen, bands = {"tried": []}, None, []
    for doi in DATASETS:
        try:
            fl = files_of(doi)
        except Exception as e:
            report["tried"].append({"dataset": doi, "error": str(e)[:200]})
            continue
        report["tried"].append({"dataset": doi, "files": [[n, s] for _, n, s in fl]})
        got = []
        for fid, name, size in fl:
            if re.search(r"\.(mp4|pdf|txt|md|xls|xlsx|csv|r|rds)$", name or "", re.I) or size > 4e9:
                continue
            try:
                got.append(nh.download(f"{DV}/api/access/datafile/{fid}", work / (name or str(fid)), name))
            except Exception as e:
                report["tried"].append({"file": name, "error": str(e)[:200]})
        bands = rasters_in(got)
        # Keep the bands whose label carries a year.
        bands = [(p, b, lab, year_of(lab)) for p, b, lab in bands]
        bands = [x for x in bands if x[3] is not None]
        if bands:
            chosen = doi
            break
    if not chosen:
        nh.write_stamp(NAME, dict(report, failed=True, error="no anthrome maps with years found"))
        raise SystemExit("anthromes: nothing readable")
    # One band per year (the first found).
    by_year = {}
    for p, b, lab, y in bands:
        by_year.setdefault(y, (p, b, lab))
    lut = np.zeros(256, dtype=np.uint8)
    for code, d in DRAW.items():
        lut[code] = d
    pal = {DRAW[code]: pyr.rgba(col, 235) for code, _, col in CLASSES}
    key = [[col, name] for _, name, col in CLASSES]
    prev = {}
    if (nh.OUT / "anthromes.json").exists():
        try:
            prev = {s["year"]: s for s in json.loads((nh.OUT / "anthromes.json").read_text()).get("steps", [])}
        except Exception:
            prev = {}
    steps, complete, seen_codes = [], True, set()
    for y in sorted(by_year):
        out = nh.OUT / "anthromes" / f"anthromes_{'m' if y < 0 else ''}{abs(y)}.pmtiles"
        if y in prev and out.exists() and not os.environ.get("ANTHROMES_REBUILD"):
            steps.append(prev[y])
            continue
        if time.time() - START > BUDGET:
            complete = False
            break
        p, b, lab = by_year[y]
        with rasterio.open(p) as src:
            if src.crs is not None and src.crs.to_epsg() not in (4326, None):
                a, west, north = pyr.read_grid(p, 1 / 12, resampling="nearest", band=b)
                a = np.nan_to_num(a, nan=0).astype(np.int64)
                res = 1 / 12
            else:
                a = src.read(b).astype(np.int64)
                t = src.transform
                west, north, res = t.c, t.f, t.a
        a[(a < 0) | (a > 255)] = 0
        seen_codes |= set(int(v) for v in np.unique(a))
        codes = lut[a.astype(np.uint8)]
        pyr.build(codes, west, north, res, pal, out, TOP, how="max", attribution="Ellis et al. 2021, Anthromes 12K", name=out.stem,
                  meta={"year": y, "from": f"{p} band {b}", "label": lab[:200]})
        steps.append({"year": y, "label": words(y), "archive": f"{pyr.PAGES}nonhuman/anthromes/{out.name}"})
        print(f"anthromes: {words(y)} built", flush=True)
    steps.sort(key=lambda s: s["year"])
    nh.write_json("anthromes.json", {"source": f"Ellis et al. 2021, Anthromes 12K, Harvard Dataverse {chosen}", "steps": steps, "key": key}, compact=False)
    unknown = sorted(c for c in seen_codes if c and c not in DRAW and c != 70)
    nh.write_stamp(NAME, dict(report, chosen=chosen, complete=complete, steps=len(steps), years=sorted(by_year),
                              **({"codes in the files with no class here (not drawn)": unknown} if unknown else {})))


if __name__ == "__main__":
    main()
