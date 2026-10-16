#!/usr/bin/env python3
"""
Where people could build, mine, drill and farm next, for the Invasion of
non-humans map (round nh3, asked 16 October).

Sources:
  - Oakleaf, J.R. et al. 2019, "Mapping global development potential for
    renewable energy, fossil fuels, mining and agriculture sectors",
    Scientific Data 6: 101; the development potential indices (DPIs) on
    figshare (Springer Nature collection 4249532): one 1 km map per sector
    (concentrated solar, photovoltaic solar, wind, hydropower, coal,
    conventional and unconventional oil and gas, metallic and non-metallic
    mining, crops, biofuels), each scored by how suitable and likely the land
    is for that development. The licence the records state is written to the
    build file.
  - Oakleaf, J.R. et al. 2019, Development Threat Index, v1.00, NASA SEDAC
    doi:10.7927/61jv-th84 (Earthdata login): every 50 km2 cell of land scored
    0 to 100 for each kind of future development, read whole and drawn as its
    cells with every score.

Each DPI is drawn from its continuous map in tenths of its own values, at
about 10 km (the files would pass GitHub's limits at 1 km; each pixel shows
the highest value under it).

  nonhuman/devpotential.json, nonhuman/devpotential/*.pmtiles, nonhuman/devpotential.build.json

Fixed releases: built once (each run carries on where the last stopped);
DEVPOTENTIAL_REBUILD=1 builds again.
"""
import json, os, pathlib, re, sys, tempfile, time, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402

NAME = "devpotential"
COLLECTION = "https://api.figshare.com/v2/collections/4249532/articles?page_size=100"
DTI_DOI = "10.7927/61jv-th84"
START, BUDGET = time.time(), 140 * 60


def main():
    st = nh.read_stamp(NAME)
    meta_p = nh.OUT / "devpotential.json"
    if meta_p.exists() and st.get("complete") and not os.environ.get("DEVPOTENTIAL_REBUILD"):
        print("devpotential: built; fixed releases (set DEVPOTENTIAL_REBUILD=1 to build again)")
        return
    pyr = nh.lib_pyramid()
    pyr.need("rasterio", "requests", "geopandas", "pyogrio")
    import numpy as np
    import rasterio
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp()) / "devpotential"
    work.mkdir(parents=True, exist_ok=True)
    meta = json.loads(meta_p.read_text()) if meta_p.exists() and not os.environ.get("DEVPOTENTIAL_REBUILD") else {"choices": []}
    done = {c["label"] for c in meta.get("choices", [])}
    report = {"articles": [], "built": [], "skipped": []}
    complete = True
    arts = nh.get_json(COLLECTION)
    for a in arts:
        if not complete:
            break
        full = nh.get_json(f"https://api.figshare.com/v2/articles/{a['id']}")
        lic = (full.get("license") or {}).get("name")
        report["articles"].append({"title": full.get("title"), "licence": lic, "files": [f["name"] for f in full.get("files", [])]})
        for f in full.get("files", []):
            if not f["name"].lower().endswith(".zip") or re.search(r"input|script", f["name"], re.I):
                continue
            label = re.sub(r"[_\-]+", " ", pathlib.Path(f["name"]).stem).strip()
            if label in done:
                continue
            if time.time() - START > BUDGET:
                complete = False
                break
            p = nh.download(f["download_url"], work / f["name"], f["name"])
            z = zipfile.ZipFile(p)
            rasters = [n for n in z.namelist() if re.search(r"\.(tif|tiff|img)$", n, re.I) or n.lower().endswith(".adf")]
            # The continuous index, not the classified one or the uncertainty.
            pick = [n for n in rasters if not re.search(r"class|uncert|cls", n, re.I)] or rasters
            if not pick:
                report["skipped"].append({"file": f["name"], "why": "no raster inside", "inside": z.namelist()[:30]})
                continue
            z.extractall(work / pathlib.Path(f["name"]).stem)
            path = str(work / pathlib.Path(f["name"]).stem / sorted(pick, key=len)[0])
            if path.lower().endswith(".adf"):
                path = str(pathlib.Path(path).parent)
            a2, w, n = pyr.read_grid(path, 1 / 12, resampling="max")
            cuts = nh.tenths(a2[np.isfinite(a2)])
            key, pal = nh.ramp_key(cuts, float(np.nanmin(a2[a2 > 0])) if (a2 > 0).any() else 0, float(np.nanmax(a2)), "")
            out = nh.OUT / "devpotential" / f"{nh.slug(label)}.pmtiles"
            pyr.build(nh.coded(a2, cuts), w, n, 1 / 12, pal, out, 4, how="max", attribution="Oakleaf et al. 2019, Scientific Data", name=out.stem, meta={"file": f["name"], "raster": path})
            meta["choices"].append({"label": label, "archive": f"{pyr.PAGES}nonhuman/devpotential/{out.name}", "key": key, "licence": lic})
            report["built"].append(label)
            nh.write_json("devpotential.json", meta, compact=False)
    # The Development Threat Index, from NASA SEDAC.
    if complete and not meta.get("dti"):
        try:
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
            import earthdata
            if not earthdata.have_login():
                raise RuntimeError("no Earthdata login")
            col = earthdata.collection(doi=DTI_DOI)
            links = earthdata.granule_links(col["id"])
            s = earthdata.session()
            files = []
            for l in links:
                to = work / "dti" / l["href"].rsplit("/", 1)[-1]
                to.parent.mkdir(parents=True, exist_ok=True)
                files.append(earthdata.download(s, l["href"], to, "DTI"))
            import geopandas as gpd
            import pyogrio
            vec = []
            for f in files:
                if f.suffix.lower() == ".zip":
                    zipfile.ZipFile(f).extractall(work / "dti" / f.stem)
            for cand in list((work / "dti").rglob("*.shp")) + list((work / "dti").rglob("*.gpkg")) + list((work / "dti").rglob("*.gdb")):
                for lname, _ in pyogrio.list_layers(str(cand)):
                    vec.append((str(cand), lname))
            if not vec:
                raise RuntimeError(f"no vector layer in {[f.name for f in files]}")
            df = gpd.read_file(vec[0][0], layer=vec[0][1]).to_crs(4326)
            nums = [c for c in df.columns if c != "geometry" and str(df[c].dtype).startswith(("int", "float"))]
            nd = work / "dti.geojsonl"
            with nd.open("w") as w2:
                for _, r in df.iterrows():
                    props = {c: (None if r[c] != r[c] else (r[c].item() if hasattr(r[c], "item") else r[c])) for c in df.columns if c != "geometry"}
                    w2.write(json.dumps({"type": "Feature", "geometry": r.geometry.__geo_interface__, "properties": props}, default=str) + "\n")
            mines = nh.tools()
            out = nh.OUT / "devpotential" / "dti.pmtiles"
            mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", "dti", "-Z0", "-z8", "--no-feature-limit", "--no-tile-size-limit",
                     "--no-tiny-polygon-reduction", "--attribution", "Oakleaf et al. 2019, Development Threat Index (NASA SEDAC)", str(nd))
            meta["dti"] = {"archive": "devpotential/dti.pmtiles", "layer": "dti", "columns": nums, "cells": len(df), "from": vec[0][1]}
            report["dti"] = meta["dti"]
        except Exception as e:
            report["dti"] = f"not built: {e}"[:400]
    nh.write_json("devpotential.json", meta, compact=False)
    nh.write_stamp(NAME, dict(report, complete=complete and bool(meta.get("dti")), failed=not meta["choices"] and not meta.get("dti")))


if __name__ == "__main__":
    main()
