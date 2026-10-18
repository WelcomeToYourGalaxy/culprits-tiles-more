#!/usr/bin/env python3
"""
More of what is done to the ocean, each a layer of its own (round 136b, asked
2 October: "yes to all" of the ocean harms not yet on the map). From the same
study as "Every human impact together": Halpern et al. 2019, Recent pace of
change in human impact on the world's ocean (Scientific Reports 9:11609), whose
data are on the KNB repository under CC0, one package per pressure, 1 km,
Mollweide, 2003 to 2013, each pressure rescaled 0 to 1 by the authors.

  row                    pressure (the authors' layer)
  ocean_slr              sea level rise
  ocean_light            light pollution
  ocean_trawling         demersal destructive fishing (bottom trawling and dredging)
  ocean_bycatch          high- and low-bycatch fishing, demersal and pelagic
  ocean_coastal_people   direct human (people on the coast)
  ocean_runoff           nutrient and organic chemical pollution from land

The files are listed package by package from KNB (round 175b); every name
found is written to oceans/stressors.build.json, with what was taken for each
row, so a wrong pick can be seen and corrected. For each pressure the 2013
and 2003 rescaled rasters are drawn, read at about 2 km, in ten steps.
Daily until all are built (each run within a time budget), then weekly
(Sundays), or by hand.
"""
import datetime, json, os, pathlib, re, sys, tempfile, time, urllib.parse, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
T = pathlib.Path("tiles")
STAMP = pathlib.Path("oceans/stressors.build.json")
SOLR = "https://cn.dataone.org/cn/v2/query/solr/"
RESOLVE = "https://cn.dataone.org/cn/v2/resolve/"
# Round 175b: each pressure's own KNB data package (the links on the Ocean
# Health Index's data page, oceanhealthindex.org/resources/data/
# cumulative-human-impacts/). The 136b search over all of DataONE by file
# name found nothing; the files are now listed package by package.
ROWS = {
    "ocean_slr": [("Sea level rise", "resource_map_doi:10.5063/F1377727")],
    "ocean_light": [("Light at night", "resource_map_doi:10.5063/F1SQ8XQF")],
    "ocean_trawling": [("Bottom trawling and dredging", "resource_map_doi:10.5063/F1TQ5ZVT")],
    "ocean_bycatch": [("Demersal, high bycatch", "resource_map_doi:10.5063/F1K64GC1"),
                      ("Demersal, low bycatch", "resource_map_doi:10.5063/F1PZ574W"),
                      ("Pelagic, high bycatch", "resource_map_doi:10.5063/F1FF3QPR"),
                      ("Pelagic, low bycatch", "resource_map_doi:10.5063/F19S1PCR")],
    "ocean_coastal_people": [("People on the coast", "resource_map_doi:10.5063/F1XG9PGM")],
    "ocean_runoff": [("Nutrients (fertiliser)", "resource_map_doi:10.5063/F1610XPS"),
                     ("Organic chemicals (pesticides)", "resource_map_doi:10.5063/F12805ZF")],
}
MN = "https://knb.ecoinformatics.org/knb/d1/mn/v2/"
YEARS = ("2013", "2003")
START, BUDGET = time.time(), 130 * 60   # what is not built in time waits for the next run


def solr(base, q, rows=1000):
    url = base + "?" + urllib.parse.urlencode({"q": q, "fl": "identifier,fileName,formatId,size", "rows": rows, "wt": "json"})
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read())["response"]["docs"]


def package_files(rmap):
    """Every file of one KNB package: KNB's own index first, DataONE's second."""
    q = f'resourceMap:"{rmap}"'
    for base in (MN + "query/solr/", SOLR):
        try:
            docs = solr(base, q)
        except Exception as e:  # noqa: BLE001
            print(f"  {rmap}: {base}: {e}", flush=True)
            docs = []
        if docs:
            return docs, base
    return [], None


def pick(docs, y):
    """The package's rescaled raster for year y: a .tif named rescaled with
    the year, else a .zip named rescaled (the year's .tif taken from inside).
    Nothing else is guessed at."""
    def ok(n):
        return "rescal" in n.lower() and not re.search(r"impact|trend|cumul", n, re.I)
    tifs = [d for d in docs if d.get("fileName", "").lower().endswith(".tif") and ok(d["fileName"]) and y in d["fileName"]]
    if tifs:
        return sorted(tifs, key=lambda d: len(d["fileName"]))[0], None
    zips = [d for d in docs if d.get("fileName", "").lower().endswith(".zip") and ok(d["fileName"])]
    return (sorted(zips, key=lambda d: len(d["fileName"]))[0], y) if zips else (None, None)


def fetch_tif(d, inner_year, row):
    tmp = pathlib.Path(tempfile.gettempdir())
    for base in (MN + "object/", RESOLVE):
        try:
            got = pyramid.download(base + urllib.parse.quote(d["identifier"], safe=""), tmp / d["fileName"], row)
            break
        except Exception as e:  # noqa: BLE001
            print(f"  {row}: {base}: {e}", flush=True)
    else:
        raise RuntimeError(f"could not download {d['fileName']}")
    if not inner_year:
        return got, d["fileName"]
    import zipfile
    with zipfile.ZipFile(got) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".tif") and inner_year in n.rsplit("/", 1)[-1]
                 and not re.search(r"impact|trend|cumul", n, re.I)]
        if not names:
            raise RuntimeError(f"no {inner_year} .tif inside {d['fileName']}")
        n = sorted(names, key=len)[0]
        out = tmp / n.rsplit("/", 1)[-1]
        out.write_bytes(z.read(n))
    got.unlink()
    return out, f"{d['fileName']} > {n}"


def main():
    stamp = json.loads(STAMP.read_text()) if STAMP.exists() else {}
    built = STAMP.exists() and not any(c.get("waiting") or (c.get("file") and c.get("error")) for t in json.loads(STAMP.read_text()).get("rows", {}).values() for c in t) \
        and all((T / f"{row}.choices.json").exists() for row in ROWS)
    if built and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("ocean_stressors: built; weekly; not Sunday")
        return
    pyramid.need("rasterio")
    import numpy as np
    STAMP.parent.mkdir(exist_ok=True)
    stamp = {"read": datetime.date.today().isoformat(), "packages": {}, "rows": {}}
    for row, parts in ROWS.items():
        choices, took = [], []
        for label, rmap in parts:
            docs, base = package_files(rmap)
            stamp["packages"][rmap] = {"index": base, "files": sorted(d.get("fileName", "") for d in docs)}
            print(f"ocean_stressors: {label}: {len(docs)} files in {rmap}", flush=True)
            for y in YEARS:
                d, inner = pick(docs, y)
                if not d:
                    took.append({"label": label, "year": y, "file": None, "why": "no file named rescaled in the package; see packages"})
                    continue
                out = T / f"{row}_{re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')}_{y}.pmtiles"
                if not out.exists() and time.time() - START > BUDGET:
                    took.append({"label": label, "year": y, "file": d["fileName"], "waiting": "time budget spent; next run"})
                    continue
                try:
                    used = d["fileName"]
                    if not out.exists() or os.environ.get("OCEANS_REBUILD"):
                        tif, used = fetch_tif(d, inner, row)
                        a, west, north = pyramid.read_grid(str(tif), 0.02, bounds=(-180, -80, 180, 84), resampling="average")
                        tif.unlink()
                        codes = np.zeros(a.shape, np.uint8)
                        ok = np.isfinite(a) & (a > 0)
                        codes[ok] = 1 + np.clip(np.floor(a[ok] * 10), 0, 9).astype(np.uint8)
                        pal = {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(pyramid.RAMP10)}
                        pyramid.build(codes, west, north, 0.02, pal, out, 7, how="max", attribution="Halpern et al. 2019 (CC0)", name=out.stem,
                                      meta={"from": d["identifier"], "file": used})
                    key = [[c, f"{i / 10:.1f} to {(i + 1) / 10:.1f}{' (highest)' if i == 9 else ''}"] for i, c in enumerate(pyramid.RAMP10)]
                    choices.append({"label": f"{label}, {y}" if len(parts) > 1 else y, "archive": f"tiles/{out.name}", "key": key})
                    took.append({"label": label, "year": y, "file": used})
                except Exception as e:  # noqa: BLE001
                    took.append({"label": label, "year": y, "file": d["fileName"], "error": f"{type(e).__name__}: {e}"})
                    print(f"  {row} {label} {y}: {e}", flush=True)
        if choices:
            pyramid.write_choices(row, choices)
        stamp["rows"][row] = took
        STAMP.write_text(json.dumps(stamp, indent=1))
    if not any(c.get("file") for t in stamp["rows"].values() for c in t):
        sys.exit("ocean_stressors: no pressure file matched; see oceans/stressors.build.json packages")


if __name__ == "__main__":
    main()
