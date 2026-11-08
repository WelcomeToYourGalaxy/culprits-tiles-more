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

  Round 132b: shipping is built by scripts/ocean_shipping.py, its own job (it
  never got its turn within this one's time); heat falls back to Coral Reef
  Watch's own file server when ERDDAP does not answer; acid looks through the
  accession's sub-folders for its NetCDF files.

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
STAR = "https://www.star.nesdis.noaa.gov/pub/sod/mecb/crw/data/5km/v3.1_op/nc/v1.0/daily/"
STAR_PARTS = {"CRW_SSTANOMALY": "ssta", "CRW_BAA": "baa", "CRW_DHW": "dhw"}
STAR_VARS = {"CRW_SSTANOMALY": r"sea_surface_temperature_anomaly|ssta", "CRW_BAA": r"bleaching_alert_area|baa", "CRW_DHW": r"degree_heating_week|dhw"}
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
        name = var
        try:
            p.write_bytes(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300).read())
        except Exception as e:  # noqa: BLE001
            print(f"  heat: ERDDAP {var}: {e}; trying Coral Reef Watch's file server", flush=True)
            url = star_newest(var)
            fetch(url, p, "heat")
        ds = netCDF4.Dataset(p)
        if var not in ds.variables:
            name = next(k for k in ds.variables if re.search(STAR_VARS[var], k, re.I) and len(ds.variables[k].dimensions) >= 2)
        v = ds.variables[name]
        sl = (0, slice(None), slice(None)) if len(v.dimensions) == 3 else (slice(None), slice(None))
        raw = v[sl]
        a = np.array(raw, dtype=np.float32)
        if np.ma.isMaskedArray(raw):
            a[np.ma.getmaskarray(raw)] = np.nan
        latn = "latitude" if "latitude" in ds.variables else "lat"
        lonn = "longitude" if "longitude" in ds.variables else "lon"
        lat = np.array(ds.variables[latn][:])
        lon = np.array(ds.variables[lonn][:])
        if a.shape[0] > 1800:
            a, lat, lon = a[::2, ::2], lat[::2], lon[::2]
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


def star_newest(var):
    """The newest daily file of one Coral Reef Watch product on its own server."""
    part = STAR_PARTS[var]
    year = datetime.date.today().year
    for y in (year, year - 1):
        root = f"{STAR}{part}/{y}/"
        try:
            page = urllib.request.urlopen(urllib.request.Request(root, headers=UA), timeout=120).read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            print(f"  heat: {root}: {e}", flush=True)
            continue
        files = sorted(set(re.findall(r'href="(ct5km_[a-z0-9]+_v3\.1_\d{8}\.nc)"', page)))
        if files:
            return root + files[-1]
    raise RuntimeError(f"no {part} file found on {STAR}")


def list_nc(root, depth=3, seen=None):
    """Every .nc file under a folder listing, sub-folders too."""
    seen = seen if seen is not None else set()
    if root in seen or depth < 0:
        return []
    seen.add(root)
    try:
        page = urllib.request.urlopen(urllib.request.Request(root, headers=UA), timeout=120).read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        print(f"  acid: {root}: {e}", flush=True)
        return []
    out = []
    for h in re.findall(r'href="([^"?#]+)"', page):
        if h.startswith(("/", "http", "..", "mailto")):
            continue
        if h.lower().endswith(".nc"):
            out.append(root + h)
        elif h.endswith("/"):
            out += list_nc(root + h, depth - 1, seen)
    return out


def nc_axis(ds, v, kind):
    """The latitude or longitude values of v's grid, as 1-D numpy arrays (round
    175b: the pH files keep them under other names than their dimensions,
    so the old lookup came back empty and failed on .max())."""
    import numpy as np
    rx = r"^(lat|latitude|nav_lat|y)$" if kind == "lat" else r"^(lon|longitude|nav_lon|x)$"
    for dim in v.dimensions:
        if re.match(rx, dim, re.I) and dim in ds.variables:
            return np.array(ds.variables[dim][:], dtype=float).ravel(), dim
    for name, var in ds.variables.items():
        std = str(getattr(var, "standard_name", "") or getattr(var, "units", "")).lower()
        if re.match(rx, name, re.I) or (kind == "lat" and std in ("latitude", "degrees_north")) or (kind == "lon" and std in ("longitude", "degrees_east")):
            a = np.array(var[:], dtype=float)
            if a.ndim == 2:
                a = a[:, 0] if kind == "lat" else a[0, :]
            return a.ravel(), next((d for d in var.dimensions if d in v.dimensions), var.dimensions[-1] if kind == "lon" else var.dimensions[0])
    return None, None


def acid(stamp):
    import numpy as np
    pyramid.need("netCDF4")
    import netCDF4
    if (T / "ocean_acid.choices.json").exists() and not os.environ.get("OCEANS_REBUILD"):
        return
    files = []
    for root in ACID_ROOTS:
        files = list_nc(root)
        if files:
            break
    print(f"  acid: {len(files)} NetCDF files listed", flush=True)
    stamp["acid_files"] = [f.rsplit("/", 1)[-1] for f in files]
    # Round 175b: the accession's own multi-model median (pHT_median_*), not
    # one model's file: the past (historical) and two futures, middle of the
    # road (SSP2-4.5) and very high emissions (SSP5-8.5).
    want = [("historical", "past"), ("ssp245", "SSP2-4.5, middle of the road"), ("ssp585", "SSP5-8.5, very high emissions")]
    found = {k: next((f for f in files if f.rsplit("/", 1)[-1].lower() == f"pht_median_{k}.nc"), None) for k, _ in want}
    if not found["historical"]:
        raise RuntimeError("pHT_median_historical.nc not among the accession's files")
    bins = [(0, 7.9, "#6E2A38", "under 7.9 (most acid)"), (7.9, 7.95, "#A0525A", "7.9 to 7.95"), (7.95, 8.0, "#C08A8A", "7.95 to 8.0"),
            (8.0, 8.05, "#6FC2DA", "8.0 to 8.05"), (8.05, 8.1, "#2E8FBA", "8.05 to 8.1"), (8.1, 14, "#0C2E5E", "8.1 or more (least acid)")]
    choices, used = [], []
    for k, words in want:
        url = found.get(k)
        if not url:
            continue
        p = fetch(url, pathlib.Path(tempfile.gettempdir()) / url.rsplit("/", 1)[-1], "acid")
        ds = netCDF4.Dataset(p)
        name = next((n for n in ds.variables if re.fullmatch(r"ph[_a-z]*", n, re.I)), None)
        if not name:
            raise RuntimeError(f"no pH variable among {list(ds.variables)}")
        v = ds.variables[name]
        dims = list(v.dimensions)
        lat, latd = nc_axis(ds, v, "lat")
        lon, lond = nc_axis(ds, v, "lon")
        if lat is None or lon is None or latd not in dims or lond not in dims:
            raise RuntimeError(f"no latitude/longitude found: dims {dims}, variables {list(ds.variables)}")
        tn = next((d for d in dims if d not in (latd, lond)), None)
        tv = np.array(ds.variables[tn][:], dtype=float) if tn and tn in ds.variables else np.array([np.nan])
        years = []
        units = str(getattr(ds.variables[tn], "units", "")) if tn and tn in ds.variables else ""
        for t in tv:
            if np.isfinite(t) and 1700 < t < 2200:
                years.append(int(round(t)))
            elif np.isfinite(t) and "since" in units:
                try:
                    years.append(netCDF4.num2date(t, units, getattr(ds.variables[tn], "calendar", "standard")).year)
                except Exception:  # noqa: BLE001
                    years.append(None)
            else:
                years.append(None)
        # From the past: the earliest and the one nearest 2020; from a future: its last.
        if k == "historical":
            picks = sorted({0, int(np.argmin([abs((y or 0) - 2020) for y in years]))})
        else:
            picks = [len(tv) - 1]
        for i in picks:
            sl = [slice(None)] * len(dims)
            if tn:
                sl[dims.index(tn)] = i
            a = np.ma.filled(np.ma.array(v[tuple(sl)]).astype(np.float32), np.nan)
            a = np.squeeze(a)
            la, lo = lat.copy(), lon.copy()
            rest = [d for d in dims if d != tn]
            if rest.index(latd) > rest.index(lond):
                a = a.T
            if lo.max() > 180:
                lo = ((lo + 180) % 360) - 180
            order = np.argsort(lo)
            lo, a = lo[order], a[:, order]
            if la[0] < la[-1]:
                a, la = a[::-1], la[::-1]
            res = float(abs(la[1] - la[0]))
            codes = np.zeros(a.shape, np.uint8)
            for b, (lo_, hi_, _, _) in enumerate(bins):
                codes[np.isfinite(a) & (a >= lo_) & (a < hi_)] = b + 1
            label = f"{years[i] if years[i] else 'time ' + str(i)}, {words}"
            out = T / f"ocean_ph_{k}_{years[i] or i}.pmtiles"
            pyramid.build(codes, float(lo[0]) - res / 2, float(la[0]) + res / 2, res,
                          {b + 1: pyramid.rgba(c, 225) for b, (_, _, c, _) in enumerate(bins)}, out, 5, how="max",
                          attribution="Jiang et al. 2023, NOAA NCEI 0259391, multi-model median (CC0)", name=out.stem,
                          meta={"from": url, "variable": name, "time": years[i]})
            choices.append({"label": label, "archive": f"tiles/{out.name}", "key": [[c, t_] for _, _, c, t_ in bins]})
            used.append({"file": url.rsplit("/", 1)[-1], "variable": name, "year": years[i]})
        ds.close()
        p.unlink(missing_ok=True)
    pyramid.write_choices("ocean_acid", choices)
    stamp["acid"] = {"used": used}


def main():
    stamp = json.loads(STAMP.read_text()) if STAMP.exists() else {}
    if stamp and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("oceans_more: weekly; not Sunday")
        return
    pyramid.need("rasterio")
    STAMP.parent.mkdir(exist_ok=True)
    failed = []
    for name, job in (("heat", heat), ("acid", acid), ("impacts", impacts)):
        try:
            job(stamp)
        except Exception as e:  # noqa: BLE001
            failed.append(name)
            stamp[name] = {"error": f"{type(e).__name__}: {e}"}
            print(f"oceans_more: {name} failed ({e})", flush=True)
        STAMP.write_text(json.dumps(stamp, indent=1, default=str))
    if len(failed) == 3:
        sys.exit(1)


if __name__ == "__main__":
    main()
