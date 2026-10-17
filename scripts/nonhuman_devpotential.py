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
    doi:10.7927/61jv-th84 (Earthdata login): land scored 0 to 100 for each
    kind of future development, one GeoTIFF per kind (in the Mollweide
    projection), each drawn in tenths of 0 to 100 at about 10 km (each pixel
    the highest score under it). Round nh4: the files are pictures, not
    outlines, as round nh3 had assumed.

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
# The Development Threat Index's kinds, as its file names run them together.
WORDS = {"agriculturalexpansion": "Agricultural expansion", "urbanexpansion": "Urban expansion", "biofuels": "Biofuels", "coal": "Coal mining",
         "conventionaloilandgas": "Conventional oil and gas", "unconventionaloilandgas": "Unconventional oil and gas", "mining": "Mining",
         "metallicmining": "Metallic mining", "nonmetallicmining": "Non-metallic mining", "solar": "Solar power", "wind": "Wind power",
         "cumulative": "All kinds together", "combined": "All kinds together", "hydropower": "Hydropower"}


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
    # Round nh3 labelled each sector by its file name (UO, CG, ...); each is
    # now labelled by its figshare title, and remembers its file.
    for c in meta.get("choices", []):
        c.setdefault("file", c["label"])
    if isinstance(meta.get("dti"), dict) and not meta["dti"].get("choices"):
        meta.pop("dti")
    done = {c["file"] for c in meta.get("choices", [])}
    titles = {}
    report = {"articles": [], "built": [], "skipped": []}
    complete = True
    arts = nh.get_json(COLLECTION)
    for a in arts:
        if not complete:
            break
        full = nh.get_json(f"https://api.figshare.com/v2/articles/{a['id']}")
        lic = (full.get("license") or {}).get("name")
        report["articles"].append({"title": full.get("title"), "licence": lic, "files": [f["name"] for f in full.get("files", [])]})
        title = re.sub(r"\s*Development Potential Index\s*$", "", full.get("title") or "", flags=re.I).strip()
        for f in full.get("files", []):
            if not f["name"].lower().endswith(".zip") or re.search(r"input|script", f["name"], re.I):
                continue
            label = re.sub(r"[_\-]+", " ", pathlib.Path(f["name"]).stem).strip()
            if title and not re.search(r"spatial data|python code", title, re.I):
                titles[label] = title
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
            meta["choices"].append({"label": titles.get(label, label), "file": label, "archive": f"{pyr.PAGES}nonhuman/devpotential/{out.name}", "key": key, "licence": lic})
            report["built"].append(label)
            nh.write_json("devpotential.json", meta, compact=False)
    for c in meta["choices"]:
        c["label"] = titles.get(c["file"], c["label"])
    meta["choices"].sort(key=lambda c: c["label"].lower())
    # The Development Threat Index, from NASA SEDAC.
    if complete and not meta.get("dti"):
        try:
            sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
            import earthdata
            if not earthdata.have_login():
                raise RuntimeError("no Earthdata login")
            col = earthdata.collection(doi=DTI_DOI)
            # Only the files themselves (the listing also holds links back to
            # the granule search), and for each kind one copy: the lon/lat
            # (geographic) one where both it and a Mollweide one are given.
            links = [l for l in earthdata.granule_links(col["id"]) if re.search(r"\.(zip|tif|tiff)$", l["href"].split("?")[0], re.I)]
            pick = {}
            for l in sorted(links, key=lambda l: ("mollweide" in l["href"].lower(), l["href"])):
                kind = re.sub(r"-(mollweide|geographic).*$", "", l["href"].rsplit("/", 1)[-1].lower())
                pick.setdefault(kind, l)
            links = list(pick.values())
            report["dti files"] = [l["href"].rsplit("/", 1)[-1] for l in links]
            s = earthdata.session()
            files = []
            for l in links:
                to = work / "dti" / l["href"].rsplit("/", 1)[-1]
                to.parent.mkdir(parents=True, exist_ok=True)
                files.append(earthdata.download(s, l["href"], to, "DTI"))
            tifs = []
            for f in files:
                if f.suffix.lower() == ".zip":
                    zipfile.ZipFile(f).extractall(work / "dti" / f.stem)
                elif f.suffix.lower() in (".tif", ".tiff"):
                    tifs.append(f)
            tifs += [t for t in (work / "dti").rglob("*") if t.suffix.lower() in (".tif", ".tiff")]
            # One picture per kind of development, named in its file name;
            # a lon/lat copy preferred to a Mollweide one when both are given.
            kinds = {}
            for t in sorted(set(tifs), key=lambda t: ("mollweide" in t.name.lower(), t.name)):
                k = re.sub(r"(lulc|development|threat|index|mollweide|geographic|geotiff|global|v\d+(\.\d+)*|\d{4})", " ", t.stem.lower())
                k = re.sub(r"[_\-\s]+", " ", k).strip() or t.stem
                kinds.setdefault(k, t)
            if not kinds:
                raise RuntimeError(f"no GeoTIFF in {[f.name for f in files]}")
            cuts = [10, 20, 30, 40, 50, 60, 70, 80, 90]
            key, pal = nh.ramp_key(cuts, 0, 100, "")
            dti = []
            for k, t in sorted(kinds.items()):
                a2, w, n = pyr.read_grid(str(t), 1 / 12, resampling="max")
                a2[a2 < 0] = np.nan
                out = nh.OUT / "devpotential" / f"dti_{nh.slug(k)}.pmtiles"
                code = nh.coded(a2, cuts)
                if not code.any():
                    continue
                pyr.build(code, w, n, 1 / 12, pal, out, 4, how="max", attribution="Oakleaf et al. 2019, Development Threat Index (NASA SEDAC)",
                          name=out.stem, meta={"file": t.name})
                dti.append({"label": WORDS.get(k.replace(" ", ""), k[:1].upper() + k[1:]), "archive": f"{pyr.PAGES}nonhuman/devpotential/{out.name}", "key": key, "file": t.name})
            meta["dti"] = {"choices": dti, "from": [f.name for f in files]}
            report["dti"] = meta["dti"]
        except Exception as e:
            report["dti"] = f"not built: {e}"[:400]
    nh.write_json("devpotential.json", meta, compact=False)
    nh.write_stamp(NAME, dict(report, complete=complete and bool(meta.get("dti")), failed=not meta["choices"] and not meta.get("dti")))


if __name__ == "__main__":
    main()
