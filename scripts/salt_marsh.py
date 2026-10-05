#!/usr/bin/env python3
"""
Salt marsh lost and gained, 2000 to 2019 (round 179b): NASA's Global Salt
Marsh Change (Campbell, Fatoyinbo and Goldberg 2022, ORNL DAAC,
doi:10.3334/ORNLDAAC/2122; Campbell et al. 2022, Nature 612, 701-706).
Two 30 m files, sm_loss.tif and sm_gain.tif; each cell holds 2000, 2005,
2010 or 2015, the first year of the five-year period in which the marsh was
lost (or gained), or 0 (NASA's guide). Needs the Earthdata login. NASA
shares it without restriction (EOSDIS data use policy).

Salt marsh is a coastal thing a few pixels wide, so each file is read at its
full 30 m, but only in the 1-degree squares that a coastline passes through
(Natural Earth's 10 m coastline, with the squares around it). Each map cell
of 0.005 degrees (about 550 m) takes the latest period of change found in
it, so a thin strip of marsh still shows from far out. Built once; again
only by hand.
"""
import json, math, os, pathlib, sys, tempfile, time, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402
import earthdata  # noqa: E402

ROW = "own_salt_marsh"
T = pathlib.Path("tiles")
STAMP = T / f"{ROW}.build.json"
DOI = "10.3334/ORNLDAAC/2122"
RES = 0.005
COAST = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_coastline.geojson"
CITE = "Campbell, Fatoyinbo and Goldberg 2022, Global Salt Marsh Change 2000-2019, ORNL DAAC, doi:10.3334/ORNLDAAC/2122"
PERIODS = [(2000, "2000 to 2004"), (2005, "2005 to 2009"), (2010, "2010 to 2014"), (2015, "2015 to 2019")]
RAMP4 = ["#8FD6E8", "#3FA9C2", "#1E6FA8", "#0E2F66"]


def coastal_squares():
    """1-degree squares (west, south) a coastline vertex falls in, and their neighbours."""
    with urllib.request.urlopen(urllib.request.Request(COAST, headers={"User-Agent": "Culprits atlas build"}), timeout=300) as r:
        feats = json.loads(r.read())["features"]
    hit = set()
    for f in feats:
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for line in lines:
            for lon, lat in line:
                hit.add((math.floor(lon), math.floor(lat)))
    out = set()
    for x, y in hit:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                xx = ((x + dx + 180) % 360) - 180
                if -90 <= y + dy < 90:
                    out.add((xx, y + dy))
    return out


def grid_of(path, squares, label):
    """The file's latest period of change per 0.005-degree cell, read square by square."""
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    W, S, E, N = -180, -60, 180, 84
    grid = np.zeros((int(round((N - S) / RES)), int(round((E - W) / RES))), np.uint8)
    seen_values = set()
    t0 = time.time()
    with rasterio.open(path) as src:
        b = src.bounds
        todo = sorted((x, y) for x, y in squares if b.left < x + 1 and x < b.right and b.bottom < y + 1 and y < b.top and S <= y < N)
        k = max(1, int(round(RES / abs(src.res[0]))))
        for i, (x, y) in enumerate(todo):
            win = from_bounds(x, y, x + 1, y + 1, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=win, boundless=True, fill_value=0)
            if not a.any():
                continue
            seen_values.update(int(v) for v in np.unique(a)[:20])
            code = np.zeros(a.shape, np.uint8)
            for j, (yr, _) in enumerate(PERIODS):
                code[a == yr] = j + 1
            h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
            m = code[:h, :w].reshape(h // k, k, w // k, k).max(axis=(1, 3))
            r0 = int(round((N - (y + 1)) / RES))
            c0 = int(round((x - W) / RES))
            hh, ww = min(m.shape[0], grid.shape[0] - r0), min(m.shape[1], grid.shape[1] - c0)
            if hh > 0 and ww > 0:
                grid[r0:r0 + hh, c0:c0 + ww] = np.maximum(grid[r0:r0 + hh, c0:c0 + ww], m[:hh, :ww])
            if i % 200 == 0:
                print(f"{label}: {i + 1} of {len(todo)} squares, {time.time() - t0:.0f} s", flush=True)
    return grid, W, N, sorted(seen_values), len(todo)


def main():
    pyramid.need("rasterio", "requests")
    T.mkdir(exist_ok=True)
    if (T / f"{ROW}.choices.json").exists() and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("salt_marsh: built; again only by hand")
        return
    stamp = {"read": time.strftime("%Y-%m-%d"), "source": CITE}
    if not earthdata.have_login():
        stamp.update(built=False, why="no EARTHDATA_USER / EARTHDATA_PASS in the run; see refresh.yml")
        STAMP.write_text(json.dumps(stamp, indent=1))
        print("::warning::salt_marsh: no Earthdata login in this run")
        return
    coll = earthdata.collection(doi=DOI)
    links = earthdata.granule_links(coll["id"], suffix=".tif")
    stamp.update(collection=coll.get("id"), files=[l["href"] for l in links])
    s = earthdata.session()
    squares = coastal_squares()
    stamp["coastal_squares"] = len(squares)
    key = [[c, t] for c, (_, t) in zip(RAMP4, PERIODS)]
    choices = []
    for kind, word in (("loss", "Lost"), ("gain", "Gained")):
        l = next((l for l in links if l["href"].rsplit("/", 1)[-1].lower() == f"sm_{kind}.tif"), None)
        if not l:
            stamp[kind] = "sm_%s.tif not among the collection's files" % kind
            continue
        p = earthdata.download(s, l["href"], pathlib.Path(tempfile.gettempdir()) / f"sm_{kind}.tif", ROW)
        stamp[f"{kind}_bytes"] = p.stat().st_size
        grid, west, north, values, n = grid_of(p, squares, f"{ROW} {kind}")
        p.unlink(missing_ok=True)
        stamp[kind] = {"values_seen": values, "squares_read": n, "cells": int((grid > 0).sum())}
        out = T / f"{ROW}_{kind}.pmtiles"
        pal = {i + 1: pyramid.rgba(c, 240) for i, c in enumerate(RAMP4)}
        pyramid.build(grid, west, north, RES, pal, out, 9, how="max", attribution=CITE, name=out.stem,
                      meta={"from": l["href"], "kind": kind})
        choices.append({"label": f"{word}, by the period it happened", "archive": f"tiles/{out.name}", "key": key})
        STAMP.write_text(json.dumps(stamp, indent=1))
    if choices:
        pyramid.write_choices(ROW, choices)
    stamp["built"] = bool(choices)
    STAMP.write_text(json.dumps(stamp, indent=1))


if __name__ == "__main__":
    main()
