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

The files are found through DataONE's search, by their names; every name
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
ROWS = {
    "ocean_slr": [("Sea level rise", r"(^|_)(slr|sea_level)")],
    "ocean_light": [("Light at night", r"light")],
    "ocean_trawling": [("Bottom trawling and dredging", r"dem(ersal)?_dest")],
    "ocean_bycatch": [("Demersal, high bycatch", r"dem(ersal)?_nondest_hb|dem(ersal)?_nondest_high"),
                      ("Demersal, low bycatch", r"dem(ersal)?_nondest_lb|dem(ersal)?_nondest_low"),
                      ("Pelagic, high bycatch", r"pel(agic)?_hb|pel(agic)?_high"),
                      ("Pelagic, low bycatch", r"pel(agic)?_lb|pel(agic)?_low")],
    "ocean_coastal_people": [("People on the coast", r"direct_human")],
    "ocean_runoff": [("Nutrients (fertiliser)", r"nutrient"), ("Organic chemicals (pesticides)", r"organic")],
}
YEARS = ("2013", "2003")
START, BUDGET = time.time(), 130 * 60   # what is not built in time waits for the next run


def solr(q, rows=1000):
    url = SOLR + "?" + urllib.parse.urlencode({"q": q, "fl": "identifier,fileName,formatId,size", "rows": rows, "wt": "json"})
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180).read())["response"]["docs"]


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
    docs = {}
    for y in YEARS:
        for d in solr(f'fileName:*{y}*rescaled* AND fileName:*.tif AND formatId:"image/geotiff"') + \
                 solr(f'fileName:*rescaled*{y}* AND fileName:*.tif'):
            docs[d["identifier"]] = d
    names = sorted({d.get("fileName", "") for d in docs.values()})
    stamp = {"read": datetime.date.today().isoformat(), "files_found": names, "rows": {}}
    print(f"ocean_stressors: {len(names)} rescaled files found", flush=True)
    for row, parts in ROWS.items():
        choices, took = [], []
        for label, rx in parts:
            for y in YEARS:
                hits = [d for d in docs.values() if re.search(rx, d.get("fileName", ""), re.I) and y in d.get("fileName", "")
                        and not re.search(r"impact|trend|cumul", d.get("fileName", ""), re.I)]
                if not hits:
                    took.append({"label": label, "year": y, "file": None})
                    continue
                d = sorted(hits, key=lambda d: len(d["fileName"]))[0]
                out = T / f"{row}_{re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')}_{y}.pmtiles"
                if not out.exists() and time.time() - START > BUDGET:
                    took.append({"label": label, "year": y, "file": d["fileName"], "waiting": "time budget spent; next run"})
                    continue
                try:
                    if not out.exists() or os.environ.get("OCEANS_REBUILD"):
                        tif = pyramid.download(RESOLVE + urllib.parse.quote(d["identifier"], safe=""), pathlib.Path(tempfile.gettempdir()) / d["fileName"], row)
                        a, west, north = pyramid.read_grid(str(tif), 0.02, bounds=(-180, -80, 180, 84), resampling="average")
                        tif.unlink()
                        codes = np.zeros(a.shape, np.uint8)
                        ok = np.isfinite(a) & (a > 0)
                        codes[ok] = 1 + np.clip(np.floor(a[ok] * 10), 0, 9).astype(np.uint8)
                        pal = {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(pyramid.RAMP10)}
                        pyramid.build(codes, west, north, 0.02, pal, out, 7, how="max", attribution="Halpern et al. 2019 (CC0)", name=out.stem,
                                      meta={"from": d["identifier"], "file": d["fileName"]})
                    key = [[c, f"{i / 10:.1f} to {(i + 1) / 10:.1f}{' (highest)' if i == 9 else ''}"] for i, c in enumerate(pyramid.RAMP10)]
                    choices.append({"label": f"{label}, {y}" if len(parts) > 1 else y, "archive": f"tiles/{out.name}", "key": key})
                    took.append({"label": label, "year": y, "file": d["fileName"]})
                except Exception as e:  # noqa: BLE001
                    took.append({"label": label, "year": y, "file": d["fileName"], "error": f"{type(e).__name__}: {e}"})
                    print(f"  {row} {label} {y}: {e}", flush=True)
        if choices:
            pyramid.write_choices(row, choices)
        stamp["rows"][row] = took
        STAMP.write_text(json.dumps(stamp, indent=1))
    if not any(c.get("file") for t in stamp["rows"].values() for c in t):
        sys.exit("ocean_stressors: no pressure file matched; see oceans/stressors.build.json files_found")


if __name__ == "__main__":
    main()
