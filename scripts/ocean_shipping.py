#!/usr/bin/env python3
"""
Ship traffic for the map's ocean_shipping row (round 132b): the World Bank /
IMF Global Shipping Traffic Density (CC BY 4.0), AIS ship positions counted in
500 m cells, January 2015 to February 2021, all ships and five kinds. Read at
about 2 km, summed, coloured on a log scale. tiles/ship_<kind>.pmtiles

It was part of oceans_more.py, which ran it last and ran out of time before
reaching it. Here it is its own job, builds what it can within its time and
leaves the rest for the next run (each built kind is kept). Daily until all
six kinds are built, then weekly (Sundays), or by hand.
"""
import datetime, json, math, os, pathlib, sys, tempfile, time, urllib.request, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

START = time.time()
BUDGET = 120 * 60
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
T = pathlib.Path("tiles")
STAMP = pathlib.Path("oceans/shipping.build.json")
SHIPS = [("all", "All ships", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045406/shipdensity_global.zip"),
         ("commercial", "Commercial ships", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045405/shipdensity_commercial_.zip"),
         ("fishing", "Fishing vessels", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045403/ShipDensity_Fishing.zip"),
         ("oilgas", "Oil and gas vessels", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045402/ShipDensity_OilGas.zip"),
         ("passenger", "Passenger ships", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045404/ShipDensity_Passenger.zip"),
         ("leisure", "Leisure boats", "https://datacatalogfiles.worldbank.org/ddh-published/0037580/5/DR0045401/ShipDensity_Leisure.zip")]


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
        if time.time() - START > BUDGET and not out.exists():
            print(f"ocean_shipping: time budget spent; {label} waits for the next run", flush=True)
            stamp["waiting"] = stamp.get("waiting", []) + [label]
            continue
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
    stamp["kinds"] = [c["label"] for c in choices]



def main():
    stamp = json.loads(STAMP.read_text()) if STAMP.exists() else {}
    done = all((T / f"ship_{k}.pmtiles").exists() for k, _, _ in SHIPS)
    if done and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("ocean_shipping: every kind built; weekly; not Sunday")
        return
    pyramid.need("rasterio")
    STAMP.parent.mkdir(exist_ok=True)
    stamp = {"read": datetime.date.today().isoformat()}
    try:
        shipping(stamp)
    except Exception as e:  # noqa: BLE001
        stamp["error"] = f"{type(e).__name__}: {e}"
        STAMP.write_text(json.dumps(stamp, indent=1))
        raise
    STAMP.write_text(json.dumps(stamp, indent=1))


if __name__ == "__main__":
    main()
