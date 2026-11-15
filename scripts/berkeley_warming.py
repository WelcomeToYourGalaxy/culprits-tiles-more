"""Round 123b (asked 2 October: "the how much warmer layer in extreme heat
says no map tile published"): Global Forest Watch lists Berkeley Earth's
temperature anomalies but publishes no picture of them, so the map draws its
own from Berkeley Earth's gridded file.

Source: Berkeley Earth, Land + Ocean, 1 x 1 degree, monthly
(Land_and_Ocean_LatLong1.nc), CC BY-NC 4.0. Its figures are already anomalies:
degrees Celsius above or below the 1951-1980 average for that place and month.
Each full year from 2000 is averaged month by month (every month of the year
must be present) and written as its own choice, with the newest first.
Weekly (Mondays) or by hand; a year already made is not made again.
"""
import json, os, pathlib, sys, datetime
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

ROW = "berkeley_warming"
URL = "https://berkeley-earth-temperature.s3.us-west-1.amazonaws.com/Global/Gridded/Land_and_Ocean_LatLong1.nc"
OUT = pathlib.Path("tiles")
WORK = pathlib.Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "berkeley"
# Steps of degrees C against 1951-1980: cooler in blues, warmer in muted reds.
STEPS = [(-99, -0.5, "#3C6E9E", "cooler by more than 0.5 °C"), (-0.5, 0, "#8FB8D0", "cooler by up to 0.5 °C"),
         (0, 0.5, "#D9C9C4", "warmer by up to 0.5 °C"), (0.5, 1, "#C9A3A0", "0.5 to 1 °C warmer"),
         (1, 1.5, "#B07C7C", "1 to 1.5 °C warmer"), (1.5, 2, "#955A62", "1.5 to 2 °C warmer"),
         (2, 3, "#7A3D4C", "2 to 3 °C warmer"), (3, 99, "#5A2338", "more than 3 °C warmer")]
ATTR = "Berkeley Earth, Land + Ocean gridded temperature (CC BY-NC 4.0)"


def main():
    today = datetime.date.today()
    built = OUT / f"{ROW}.choices.json"
    if built.exists() and today.weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print(f"{ROW}: weekly; not Monday")
        return
    pyramid.need("netCDF4")
    import numpy as np, netCDF4
    WORK.mkdir(parents=True, exist_ok=True)
    nc = pyramid.download(URL, WORK / "Land_and_Ocean_LatLong1.nc", ROW)
    d = netCDF4.Dataset(str(nc))
    t = np.array(d.variables["time"][:], dtype=float)
    lat = np.array(d.variables["latitude"][:], dtype=float)
    lon = np.array(d.variables["longitude"][:], dtype=float)
    temp = d.variables["temperature"]
    flip = lat[0] < lat[-1]
    shift = int(np.argmin(np.abs(lon - (-179.5))))
    palette = {i + 1: pyramid.rgba(c) for i, (_, _, c, _) in enumerate(STEPS)}
    key = [[c, words] for (_, _, c, words) in STEPS]
    choices, made = [], {}
    years = sorted({int(np.floor(x)) for x in t})
    for y in reversed(years):
        if y < 2000:
            continue
        idx = np.where(np.floor(t) == y)[0]
        if len(idx) < 12:
            print(f"{ROW}: {y} has {len(idx)} months; not a full year, left out", flush=True)
            continue
        out = OUT / f"{ROW}_{y}.pmtiles"
        if not out.exists():
            a = np.ma.filled(temp[idx, :, :].astype(float), np.nan)
            m = np.nanmean(a, axis=0)
            if flip:
                m = m[::-1, :]
            m = np.roll(m, -shift, axis=1)
            codes = np.zeros(m.shape, dtype=np.uint8)
            for i, (lo, hi, _, _) in enumerate(STEPS):
                codes[(m >= lo) & (m < hi)] = i + 1
            pyramid.build(codes, -180.0, 90.0, 1.0, palette, out, 4, how="max", attribution=ATTR,
                          name=f"Temperature against 1951-1980, {y}", meta={"year": y, "source": URL})
            made[y] = float(np.nanmean(m))
        choices.append({"label": f"{y}", "archive": f"tiles/{out.name}", "key": key})
    if not choices:
        raise SystemExit(f"{ROW}: no full year from 2000 found in {URL}")
    pyramid.write_choices(ROW, choices)
    (OUT / f"{ROW}.build.json").write_text(json.dumps({"from": URL, "years": [c["label"] for c in choices],
                                                       "made_now": made, "read": today.isoformat()}, indent=1))


if __name__ == "__main__":
    main()
