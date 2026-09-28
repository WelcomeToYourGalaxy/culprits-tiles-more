#!/usr/bin/env python3
"""
Four more ocean layers as the map's own pictures (round 95b, asked 27
September: "yes to all of the worth adding next"). Each part is built on its
own; one that fails leaves the others and says why.

  shipping      World Bank / IMF Global Shipping Traffic Density (CC BY 4.0):
                AIS ship positions counted in 500 m cells, Jan 2015 to Feb
                2021; all ships, and commercial, fishing, oil and gas,
                passenger and leisure. Read at about 2 km, summed, coloured on
                a log scale. tiles/ship_<kind>.pmtiles
  impacts       Cumulative human impacts on the ocean, 2013 (Halpern et al.
                2019, KNB doi:10.5063/F12B8WBS, CC0): fishing, climate change,
                shipping and land-based pollution added up, 1 km, Mollweide.
                tiles/ocean_impacts_2013.pmtiles
  heat          NOAA Coral Reef Watch, daily 5 km (ERDDAP dataset NOAA_DHW):
                sea surface temperature anomaly, coral bleaching alert level
                and degree heating weeks, the newest day. Rebuilt weekly.
                tiles/crw_<var>.pmtiles
  acid          Ocean acidification: surface pH from NOAA NCEI accession
                0259391 (Jiang et al. 2023, CC0), gridded, 1750 to 2100; the
                file's pH variable at its first, present-day and last time
                steps. tiles/ocean_ph_<year>.pmtiles

  Each writes tiles/<row>.choices.json for the map's row, and
  oceans/more.build.json records what each read.

Weekly (Sundays), or by hand. The large files (shipping, impacts, acidity) are
fetched once; OCEANS_REBUILD=1 fetches them again.
"""
import datetime, json, math, os, pathlib, re, sys, tempfile, urllib.request, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
T = pathlib.Path("tiles")
STAMP = pathlib.Path("oceans/more.build.json")
SHIPS = [("all", "All ships", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045406/shipdensity_global.zip"),
         ("commercial", "Commercial ships", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045405/shipdensity_commercial_.zip"),
         ("fishing", "Fishing vessels", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045403/ShipDensity_Fishing.zip"),
         ("oilgas", "Oil and gas vessels", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045402/ShipDensity_OilGas.zip"),
         ("passenger", "Passenger ships", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045404/ShipDensity_Passenger.zip"),
         ("leisure", "Leisure boats", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045401/ShipDensity_Leisure.zip")]
IMPACTS = "https://cn.dataone.org/cn/v2/resolve/urn:uuid:4b023df7-abaf-4d47-8f31-39c5c96db811"
ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/NOAA_DHW"
ACID_ROOTS = ["https://www.ncei.noaa.gov/data/oceans/ncei/ocads/data/0259391/", "https://www.ncei.noaa.gov/archive/accession/0259391/data/0-data/"]


def fetch(url, to, label):
    return pyramid.download(url, to, label)


def log_codes(a, np, steps=10):
    """Counts to codes 1..steps on a log scale from the 50th to the 99.9th percentile of the non-zero cells."""
    pos = a[np.isfinite(a) & (a > 0)]
    if not pos.size:
        return None, None
    lo, hi = np.percentile(pos, 50), np.percentile(pos, 99.9)
    lo, hi = max(lo, 1e-9), max(hi, lo * 10)
    t = (np.log10(np.clip(a, lo, hi)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
    codes = np.where(np.isfinite(a) & (a > 0), 1 + np.clip(np.floor(t * steps), 0, steps - 1), 0).astype(np.uint8)
    edges = [lo * (hi / lo) ** (i / steps) for i in range(steps + 1)]
    return codes, edges


def fmt(x):
    return f"{x:,.0f}" if x >= 10 else f"{x:.2g}"


def shipping(stamp):
    import numpy as np
    work = pathlib.Path(tempfile.gettempdir())
    choices = []
    for kind, label, url in SHIPS:
        out = T / f"ship_{kind}.pmtiles"
        if out.exists() and not os.environ.get("OCEANS_REBUILD"):
            choices.append({"label": label, "archive": f"tiles/{out.name}", "key": json.loads((T / f"ship_{kind}.key.json").read_text())})
            continue
        z = fetch(url, work / f"ship_{kind}.zip", "shipping")
        tif = next(n for n in zipfile.ZipFile(z).namelist() if n.lower().endswith((".tif", ".tiff")))
        a, west, north = pyramid.read_grid(f"/vsizip/{z}/{tif}", 0.02, bounds=(-180, -80, 180, 84), resampling="average")
        codes, edges = log_codes(a, np)
        z.unlink()
        if codes is None:
            continue
        pal = {i + 1: pyramid.rgba(c, 240) for i, c in enumerate(pyramid.RAMP10)}
        pyramid.build(codes, west, north, 0.02, pal, out, 7, how="max", attribution="World Bank / IMF Global Shipping Traffic Density (CC BY 4.0)", name=out.stem,
                      meta={"from": url, "file": tif})
        key = [[c, f"{fmt(edges[i])} to {fmt(edges[i + 1])}"] for i, c in enumerate(pyramid.RAMP10)]
        (T / f"ship_{kind}.key.json").write_text(json.dumps(key))
        choices.append({"label": label, "archive": f"tiles/{out.name}", "key": key})
    pyramid.write_choices("ocean_shipping", choices)
    stamp["shipping"] = {"kinds": [c["label"] for c in choices]}


def impacts(stamp):
    import numpy as np
    out = T / "ocean_impacts_2013.pmtiles"
    if out.exists() and not os.environ.get("OCEANS_REBUILD"):
        return
    tif = fetch(IMPACTS, pathlib.Path(tempfile.gettempdir()) / "cumulative_impact_2013.tif", "impacts")
    a, west, north = pyramid.read_grid(str(tif), 0.02, bounds=(-180, -80, 180, 84), resampling="average")
    tif.unlink()
    pos = a[np.isfinite(a) & (a > 0)]
    edges = list(np.percentile(pos, [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]))
    codes = np.zeros(a.shape, np.uint8)
    ok = np.isfinite(a) & (a > 0)
    for i in range(10):
        codes[ok & (a >= edges[i])] = i + 1
    pal = {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(pyramid.RAMP10)}
    pyramid.build(codes, west, north, 0.02, pal, out, 7, how="mean", attribution="Halpern et al. 2019, cumulative human impacts (CC0)", name=out.stem,
                  meta={"from": IMPACTS, "year": 2013})
    key = [[c, f"{'lowest' if i == 0 else 'highest' if i == 9 else ''} tenth ({edges[i]:.2f} to {edges[i + 1]:.2f})".strip()] for i, c in enumerate(pyramid.RAMP10)]
    pyramid.write_choices("ocean_impacts", [{"label": "2013", "archive": f"tiles/{out.name}", "key": key}])
    stamp["impacts"] = {"from": IMPACTS, "edges": edges}


def heat(stamp):
    import numpy as np
    pyramid.need("netCDF4")
    import netCDF4
    work = pathlib.Path(tempfile.gettempdir())
    choices = []
    specs = [("CRW_SSTANOMALY", "Sea surface temperature against usual, °C", [(-99, -1, "#1A5C92", "1 °C or more colder"), (-1, 0, "#6FC2DA", "up to 1 °C colder"),
                                                                                 (0, 1, "#D8C6C6", "up to 1 °C warmer"), (1, 2, "#C08A8A", "1 to 2 °C warmer"),
                                                                                 (2, 3, "#A0525A", "2 to 3 °C warmer"), (3, 99, "#6E2A38", "3 °C or more warmer")]),
             ("CRW_BAA", "Coral bleaching alert", [(-0.5, 0.5, "#D6EEF6", "no stress"), (0.5, 1.5, "#8FD6E8", "bleaching watch"), (1.5, 2.5, "#C08A8A", "bleaching warning"),
                                                   (2.5, 3.5, "#A0525A", "alert level 1: bleaching likely"), (3.5, 99, "#6E2A38", "alert level 2: corals likely to die")]),
             ("CRW_DHW", "Heat stress built up over 12 weeks (degree heating weeks)", [(0.01, 4, "#8FD6E8", "under 4: little"), (4, 8, "#C08A8A", "4 to 8: bleaching likely"),
                                                                                     (8, 12, "#A0525A", "8 to 12: widespread bleaching, corals dying"), (12, 999, "#6E2A38", "12 or more: severe")])]
    for var, label, bins in specs:
        url = f"{ERDDAP}.nc?{var}%5B(last)%5D%5B(89.975):2:(-89.975)%5D%5B(-179.975):2:(179.975)%5D"
        p = work / f"{var}.nc"
        p.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=900).read())
        ds = netCDF4.Dataset(p)
        v = ds.variables[var]
        a = np.array(v[0, :, :], dtype=np.float32)
        if np.ma.isMaskedArray(v[0, :, :]):
            a[np.ma.getmaskarray(v[0, :, :])] = np.nan
        lat = np.array(ds.variables["latitude"][:])
        lon = np.array(ds.variables["longitude"][:])
        t = ds.variables["time"]
        day = str(netCDF4.num2date(t[-1], t.units))[:10]
        ds.close()
        if lat[0] < lat[-1]:
            a = a[::-1]
            lat = lat[::-1]
        res = float(abs(lat[1] - lat[0]))
        codes = np.zeros(a.shape, np.uint8)
        for i, (lo, hi, _, _) in enumerate(bins):
            codes[np.isfinite(a) & (a >= lo) & (a < hi)] = i + 1
        pal = {i + 1: pyramid.rgba(c, 225) for i, (_, _, c, _) in enumerate(bins)}
        out = T / f"crw_{var.lower()}.pmtiles"
        pyramid.build(codes, float(lon[0]) - res / 2, float(lat[0]) + res / 2, res, pal, out, 6, how="max",
                      attribution="NOAA Coral Reef Watch", name=out.stem, meta={"from": url, "day": day})
        choices.append({"label": f"{label}, {day}", "archive": f"tiles/{out.name}", "key": [[c, t_] for _, _, c, t_ in bins]})
    pyramid.write_choices("ocean_heat", choices)
    stamp["heat"] = {"layers": [c["label"] for c in choices]}


def acid(stamp):
    import numpy as np
    pyramid.need("netCDF4")
    import netCDF4
    if (T / "ocean_acid.choices.json").exists() and not os.environ.get("OCEANS_REBUILD"):
        return
    files = []
    for root in ACID_ROOTS:
        try:
            page = urllib.request.urlopen(urllib.request.Request(root, headers=UA), timeout=120).read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            print(f"  acid: {root}: {e}", flush=True)
            continue
        files += [root + h for h in re.findall(r'href="([^"/?]+\.nc)"', page)]
        if files:
            break
    ph = [f for f in files if re.search(r"ph", f.rsplit("/", 1)[-1], re.I)] or files
    if not ph:
        raise RuntimeError("no NetCDF file listed in the accession's folders")
    p = fetch(ph[0], pathlib.Path(tempfile.gettempdir()) / ph[0].rsplit("/", 1)[-1], "acid")
    ds = netCDF4.Dataset(p)
    name = next((k for k in ds.variables if re.fullmatch(r"ph[_a-z]*", k, re.I)), None)
    if not name:
        raise RuntimeError(f"no pH variable among {list(ds.variables)}")
    v = ds.variables[name]
    dims = v.dimensions
    latn = next(d for d in dims if re.match(r"lat", d, re.I))
    lonn = next(d for d in dims if re.match(r"lon", d, re.I))
    tn = next((d for d in dims if d not in (latn, lonn)), None)
    lat = np.array(ds.variables[latn][:]) if latn in ds.variables else None
    lon = np.array(ds.variables[lonn][:]) if lonn in ds.variables else None
    times = np.array(ds.variables[tn][:]) if tn and tn in ds.variables else [None]
    labels = [str(int(t)) if t is not None and float(t) > 1000 else str(t) for t in times]
    picks = sorted({0, int(np.argmin([abs(float(t) - 2020) if t is not None else 0 for t in times])), len(times) - 1})
    bins = [(0, 7.9, "#6E2A38", "under 7.9"), (7.9, 7.95, "#A0525A", "7.9 to 7.95"), (7.95, 8.0, "#C08A8A", "7.95 to 8.0"),
            (8.0, 8.05, "#6FC2DA", "8.0 to 8.05"), (8.05, 8.1, "#2E8FBA", "8.05 to 8.1"), (8.1, 14, "#0C2E5E", "8.1 or more")]
    choices = []
    for i in picks:
        sl = [slice(None)] * len(dims)
        if tn:
            sl[dims.index(tn)] = i
        a = np.ma.filled(np.ma.array(v[tuple(sl)]).astype(np.float32), np.nan)
        if dims.index(latn) > dims.index(lonn):
            a = a.T
        if lon.max() > 180:
            order = np.argsort(((lon + 180) % 360) - 180)
            lon = ((lon + 180) % 360) - 180
            lon, a = lon[order], a[:, order]
        if lat[0] < lat[-1]:
            a, lat = a[::-1], lat[::-1]
        res = float(abs(lat[1] - lat[0]))
        codes = np.zeros(a.shape, np.uint8)
        for k, (lo, hi, _, _) in enumerate(bins):
            codes[np.isfinite(a) & (a >= lo) & (a < hi)] = k + 1
        out = T / f"ocean_ph_{labels[i]}.pmtiles"
        pyramid.build(codes, float(lon[0]) - res / 2, float(lat[0]) + res / 2, res, {k + 1: pyramid.rgba(c, 225) for k, (_, _, c, _) in enumerate(bins)},
                      out, 5, how="max", attribution="Jiang et al. 2023, NOAA NCEI 0259391 (CC0)", name=out.stem, meta={"from": ph[0], "variable": name, "time": labels[i]})
        choices.append({"label": labels[i], "archive": f"tiles/{out.name}", "key": [[c, t_] for _, _, c, t_ in bins]})
    ds.close()
    pyramid.write_choices("ocean_acid", choices)
    stamp["acid"] = {"file": ph[0], "variable": name, "times": [labels[i] for i in picks]}


def main():
    stamp = json.loads(STAMP.read_text()) if STAMP.exists() else {}
    if stamp and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("oceans_more: weekly; not Sunday")
        return
    pyramid.need("rasterio")
    STAMP.parent.mkdir(exist_ok=True)
    failed = []
    for name, job in (("heat", heat), ("acid", acid), ("impacts", impacts), ("shipping", shipping)):
        try:
            job(stamp)
        except Exception as e:  # noqa: BLE001
            failed.append(name)
            stamp[name] = {"error": f"{type(e).__name__}: {e}"}
            print(f"oceans_more: {name} failed ({e})", flush=True)
        STAMP.write_text(json.dumps(stamp, indent=1, default=str))
    if len(failed) == 4:
        sys.exit(1)


if __name__ == "__main__":
    main()
