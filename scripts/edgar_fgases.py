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
Round 120b: also every gas together, in tonnes of CO2 equivalent (GWP-100,
IPCC AR5), as a map (tiles/edgar_fgases_all.pmtiles) and as height tiles the
map raises (tiles/edgar_fgases_all_relief.pmtiles).
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
# Round 120b (asked 1 October: one layer of all the F-gases together, as the
# default): each gas's tonnes times its global warming potential over 100
# years, IPCC Fifth Assessment Report (AR5, WG1 chapter 8, table 8.A.1), the
# values EDGAR's own CO2-equivalent totals use, summed cell by cell. A gas not
# in this table is left out of the total and named in the build record.
GWP100_AR5 = {"hfc23": 12400, "hfc32": 677, "hfc41": 116, "hfc125": 3170, "hfc134": 1120, "hfc134a": 1300, "hfc143": 328,
              "hfc143a": 4800, "hfc152a": 138, "hfc227ea": 3350, "hfc236fa": 8060, "hfc245fa": 858, "hfc365mfc": 804,
              "hfc4310mee": 1650, "cf4": 6630, "c2f6": 11100, "c3f8": 8900, "cc4f8": 9540, "c4f10": 9200, "c5f12": 8550,
              "c6f14": 7910, "sf6": 23500, "nf3": 16100, "hcfc141b": 782, "hcfc142b": 1980}
TOTAL = {"grid": None, "t": None, "gases": [], "left_out": [], "year": set(), "unit": None}
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
        g = GWP100_AR5.get(re.sub(r"[^a-z0-9]", "", gas.lower()))
        clean_arr = np.where(np.isfinite(arr) & (arr > 0), arr, 0.0)
        if g is None:
            TOTAL["left_out"].append(gas)
        elif TOTAL["grid"] is None:
            TOTAL.update(grid=clean_arr * g, t=t, unit=unit)
            TOTAL["gases"].append(f"{gas} x {g}")
            TOTAL["year"].add(year)
        elif TOTAL["grid"].shape == clean_arr.shape:
            TOTAL["grid"] += clean_arr * g
            TOTAL["gases"].append(f"{gas} x {g}")
            TOTAL["year"].add(year)
        else:
            TOTAL["left_out"].append(f"{gas} (a different grid)")
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


def relief(grid, t):
    """The total as height tiles (Mapbox's code, -10000 + (R*65536 + G*256 + B)/10),
    zooms 0 to 5, for the map to draw as stepped, raised ground."""
    import io, math, numpy as np
    from PIL import Image
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer
    N, TOP = 256, 5
    west, north, res = t.c, t.f, t.a
    H, W = grid.shape
    lat_of = lambda ty, z: math.degrees(math.atan(math.sinh(math.pi - 2 * math.pi * ty / 2 ** z)))
    tiles = {}
    for z in range(TOP + 1):
        n = 2 ** z
        for ty in range(n):
            lats = np.array([lat_of(ty + (j + 0.5) / N, z) for j in range(N)])
            rows = np.clip(((north - lats) / res).astype(int), 0, H - 1)
            inside = (lats <= north) & (lats >= north - H * res)
            for tx in range(n):
                lons = -180 + 360 * (tx + (np.arange(N) + 0.5) / N) / n
                cols = np.clip(((lons - west) / res).astype(int), 0, W - 1)
                d = grid[rows][:, cols]
                d[~inside, :] = 0
                if not d.any():
                    continue
                code = np.round((np.clip(d, 0, 1_600_000) + 10000) * 10).astype(np.uint32)
                rgb = np.stack([(code >> 16) & 255, (code >> 8) & 255, code & 255], axis=-1).astype(np.uint8)
                buf = io.BytesIO()
                Image.fromarray(rgb, "RGB").save(buf, "PNG", optimize=True)
                tiles[zxy_to_tileid(z, tx, ty)] = buf.getvalue()
    out = pathlib.Path("tiles/edgar_fgases_all_relief.pmtiles")
    with open(out, "wb") as f:
        w = Writer(f)
        for tid in sorted(tiles):
            w.write_tile(tid, tiles[tid])
        w.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": 0, "max_zoom": TOP,
                    "min_lon_e7": -1800000000, "min_lat_e7": -850000000, "max_lon_e7": 1800000000, "max_lat_e7": 850000000,
                    "center_zoom": 1, "center_lon_e7": 0, "center_lat_e7": 0},
                   {"attribution": "EDGAR_2025_GHG, European Commission JRC, CC BY 4.0", "name": out.stem, "encoding": "mapbox"})
    return len(tiles)


def finish():
    import json
    if TOTAL["grid"] is not None:
        import numpy as np
        grid = TOTAL["grid"]
        # Heights are coded up to 1.6 million; the total is drawn in tonnes of
        # CO2 equivalent, the coded figure itself (cells above that are cut).
        yrs = sorted(TOTAL["year"])
        label = f"All fluorinated gases together, tonnes of CO2 equivalent (GWP-100, IPCC AR5), {yrs[-1] if yrs else ''}"
        food_crops.build_array(grid, TOTAL["t"], "EPSG:4326", None, "edgar_fgases_all", label + ", per 0.1-degree cell, EDGAR_2025_GHG",
                               "EDGAR_2025_GHG, European Commission JRC, CC BY 4.0", "edgar")
        squares = relief(grid, TOTAL["t"])
        pos = grid[grid > 0]
        info = {"gases": TOTAL["gases"], "left out (no AR5 value in the table)": TOTAL["left_out"], "years": yrs, "unit of each gas": TOTAL["unit"],
                "unit": "tonnes CO2 equivalent per cell (if each gas is in tonnes per cell)", "squares": squares,
                "p5": float(np.percentile(pos, 5)) if pos.size else 0, "p99": float(np.percentile(pos, 99)) if pos.size else 0,
                "max": float(pos.max()) if pos.size else 0}
        pathlib.Path("tiles/edgar_fgases_all_relief.build.json").write_text(json.dumps(info, indent=1))
        MADE.insert(0, {"label": "All fluorinated gases together (tonnes of CO2 equivalent)", "archive": f"{BASE}/tiles/edgar_fgases_all.pmtiles",
                        "year": yrs[-1] if yrs else None, "unit": "t CO2e", "key": "all"})
    # The map reads this list for the row's chips, so a group split into its
    # gases shows every one of them (edgar/fgases_choices.json).
    (OUT / "fgases.json").write_text(json.dumps({m["key"]: {"year": m["year"], "unit": m["unit"]} for m in MADE}, indent=1))
    (OUT / "fgases_choices.json").write_text(json.dumps({"choices": [{"label": m["label"], "archive": m["archive"]} for m in MADE]}, indent=1))
    print(f"edgar_fgases: {len(MADE)} maps drawn")


if __name__ == "__main__":
    main()
