#!/usr/bin/env python3
"""
EDGAR's fluorinated-gas emissions (F-gases) as a map of 0.1-degree cells (about
10 km), for Climate > F-gases: EDGAR_2025_GHG, European Commission JRC, CC BY 4.0.

EDGAR's page lists the gridmaps under folded headings the fetcher cannot open,
so this reads the release's own file index on jeodpp.jrc.ec.europa.eu, writes
what it found to edgar/listing.txt, and takes the F-gas annual gridmap of the
latest year there (the emissions file, not the fluxes one). Every cell with a
value is drawn (tiles/edgar_fgases.pmtiles, zooms 0 to 6, the largest value
kept wider out, dark plum to bone on a log scale cut at the values' own steps);
the steps and the file used go in edgar/fgases.key.json.

Since 23 September (round 2): one map per gas group EDGAR publishes (HFCs,
PFCs, SF6, NF3, HCFCs), each from the latest year inside that gas's zip; the
listing written by the first run named every file, so the index is not walked.

By hand only (Actions tab, "edgar_fgases").
"""
import io, os, pathlib, re, shutil, subprocess, sys, tempfile, urllib.parse, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import food_crops  # noqa: E402

ROOT = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EDGAR/datasets/EDGAR_2025_GHG/"
UA = {"User-Agent": "Culprits atlas (EDGAR F-gas gridmap)"}
OUT = pathlib.Path("edgar")


def index(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        html = r.read().decode("utf-8", "replace")
    links = [urllib.parse.urljoin(url, h) for h in re.findall(r'href="([^"?#]+)"', html)]
    return [l for l in links if l.startswith(url) and l != url]


def crawl(url, depth, found, seen):
    if depth < 0 or url in seen:
        return
    seen.add(url)
    try:
        links = index(url)
    except Exception as e:  # noqa: BLE001
        found.append(f"# could not read {url}: {e}")
        return
    for l in links:
        if l.endswith("/"):
            # The monthly folders are tens of GB; only annual files are wanted.
            if "/monthly/" in l:
                continue
            crawl(l, depth - 1, found, seen)
        else:
            found.append(l)


BASE = "https://welcometoyourgalaxy.github.io/culprits-tiles-more"
MADE = []
GASES = [("HFCs", "Hydrofluorocarbons (HFCs)"), ("PFCs", "Perfluorocarbons (PFCs)"), ("SF6", "Sulphur hexafluoride (SF6)"),
         ("NF3", "Nitrogen trifluoride (NF3)"), ("HCFCs", "Hydrochlorofluorocarbons (HCFCs)")]


def nc_members(z, depth=0):
    """Every .nc file in a zip, looking inside zips held in it too: (name, bytes-reader).

    Some of EDGAR's F-gas group zips (HFCs, PFCs, HCFCs) hold no .nc at their top
    level (the run of 23 September found none), so their files are inside
    further zips, one per gas in the group."""
    out = []
    for n in z.namelist():
        if n.lower().endswith(".nc"):
            out.append((n.rsplit("/", 1)[-1], (lambda z=z, n=n: z.read(n))))
        elif n.lower().endswith(".zip") and depth < 3:
            out += nc_members(zipfile.ZipFile(io.BytesIO(z.read(n))), depth + 1)
    return out


def species_of(name, year):
    """The gas a file is for, from EDGAR's own file name (EDGAR_2025_GHG_<gas>_<year>_TOTALS_emi.nc)."""
    base = re.sub(r"^EDGAR_\d{4}_GHG_", "", name)
    return re.split(rf"_{year}(?:_|\.)", base)[0] or base


def latest_nc(names):
    """Of the yearly .nc files in a gas's zip, the one for the latest year, and that year."""
    # The release's own name (EDGAR_2025_GHG) carries a year too; it is taken out first.
    yr = lambda n: max([int(y) for y in re.findall(r"(?<!\d)(19[7-9]\d|20[0-4]\d)(?!\d)", re.sub(r"EDGAR_\d{4}_GHG", "", n))] or [0])
    ncs = [n for n in names if n.endswith(".nc")]
    if not ncs:
        return None, None
    best = max(ncs, key=yr)
    return best, yr(best)


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("edgar_fgases: by hand only")
        return
    OUT.mkdir(exist_ok=True)
    # The first build (23 September) took one gas's zip and the first file in it:
    # sulphur hexafluoride, and not necessarily the latest year. Each gas group
    # EDGAR publishes is now its own map, from its own latest year. Tonnes of
    # different gases are not added together: they warm very differently.
    food_crops.need()
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "netCDF4"], check=True)
    import json, netCDF4, numpy as np
    from rasterio.transform import from_origin
    for gas, label in GASES:
        url = f"{ROOT}Fgases/{gas}/TOTALS/{gas}_TOTALS_emi_nc.zip"
        work = pathlib.Path(tempfile.mkdtemp())
        path = work / f"{gas}.zip"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=1800) as r, open(path, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
        except Exception as e:  # noqa: BLE001
            print(f"edgar_fgases: {gas}: could not be read ({e})", flush=True)
            continue
        with zipfile.ZipFile(path) as z:
            found = nc_members(z)
            if not found:
                print(f"edgar_fgases: {gas}: no .nc file in {url}, even inside the zips it holds; it holds: {z.namelist()[:40]}", flush=True)
                continue
            _, year = latest_nc([n for n, _ in found])
            latest = [(n, rd) for n, rd in found if latest_nc([n])[1] == year]
            for n, rd in latest:
                (work / n).write_bytes(rd())
        # A group with one file for the latest year is one map; a group whose zip
        # holds a file per gas in it (HFC-134a, HFC-32 ...) is one map per gas:
        # tonnes of different gases are not added together.
        for name, _ in sorted(latest):
            one = len(latest) == 1
            sp = species_of(name, year)
            draw(gas if one else sp, label if one else f"{sp} ({label})", name, year, work, url)
        shutil.rmtree(work, ignore_errors=True)
    finish()


def draw(key, label, name, year, work, url):
        import json, netCDF4, numpy as np
        from rasterio.transform import from_origin
        gas = key
        ds = netCDF4.Dataset(work / name)
        var = next(v for v in ds.variables.values() if v.ndim >= 2 and v.dimensions[-2].startswith("lat"))
        arr = np.array(var[:]).astype("float64")
        while arr.ndim > 2:
            arr = arr[-1]
        lat, lon = np.array(ds.variables["lat"][:]), np.array(ds.variables["lon"][:])
        if lat[0] < lat[-1]:
            arr, lat = arr[::-1], lat[::-1]
        res = abs(float(lon[1] - lon[0]))
        t = from_origin(float(lon.min()) - res / 2, float(lat.max()) + res / 2, res, res)
        unit = getattr(var, "units", "the file's own unit")
        row = "edgar_fgases_" + re.sub(r"[^a-z0-9]+", "_", gas.lower()).strip("_")
        print(f"edgar_fgases: {gas}: {name}, year {year}, {arr.shape}, unit {unit}", flush=True)
        food_crops.build_array(arr, t, "EPSG:4326", None, row, f"{label} emitted per 0.1-degree cell, {year} ({unit}), EDGAR_2025_GHG",
                               "EDGAR_2025_GHG, European Commission JRC, CC BY 4.0", "edgar")
        k = OUT / f"{row}.key.json"
        if k.exists():
            d = json.loads(k.read_text())
            d.update({"file": url, "inside": name, "year": year, "variable": var.name, "unit": unit})
            k.write_text(json.dumps(d, indent=1))
        MADE.append({"label": label, "archive": f"{BASE}/tiles/{row}.pmtiles", "year": year, "unit": unit, "key": gas})


def finish():
    import json
    # The map reads this list for the row's chips, so a group split into its
    # gases shows every one of them (edgar/fgases_choices.json).
    (OUT / "fgases.json").write_text(json.dumps({m["key"]: {"year": m["year"], "unit": m["unit"]} for m in MADE}, indent=1))
    (OUT / "fgases_choices.json").write_text(json.dumps({"choices": [{"label": m["label"], "archive": m["archive"]} for m in MADE]}, indent=1))
    print(f"edgar_fgases: {len(MADE)} maps drawn")


if __name__ == "__main__":
    main()
