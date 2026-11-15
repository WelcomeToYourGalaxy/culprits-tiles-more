#!/usr/bin/env python3
"""
How many farm fields each square of the world holds, for the Fields of The
World row wider out (round 100b, asked 28 September: the fields showed only
close in; the project's own tiles begin only at the higher zooms).

Source: Fields of The World's download tiles on Source Cooperative
(source.coop/ftw/global-field-boundaries, CC BY 4.0): one GeoParquet file per
one-degree square, each row one field. Nothing is downloaded but each file's
footer, which states how many rows (fields) the file holds; the newest year
published is used. The count is shaded per square as fields per 100 km2, in
five steps at the counts' own fifths, and written with its key.

  tiles/ftw_overview.pmtiles        zooms 0 to 6
  tiles/ftw_overview.choices.json   the row's key
  ftw/overview_build.json           the year, files read, counts

Weekly (Mondays) or by hand; FTW_AGAIN=1 reads every footer again.
"""
import datetime, json, math, os, pathlib, re, struct, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

BASE = "https://data.source.coop/ftw/global-field-boundaries/"
UA = {"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy)"}
ROW = "ftw_overview"
OUT = pathlib.Path("ftw")
TILE = pathlib.Path("tiles") / f"{ROW}.pmtiles"


def get(url, headers=None, timeout=120):
    last = None
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=dict(UA, **(headers or {}))), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {last}")


def listing():
    """Every download tile: key -> size.

    Round 111b (29 September): source.coop answers the S3 list call of the
    second kind only: it ignored "marker" and gave the same first 1,000 keys
    again and again (998 tiles, until the job was stopped at 160 minutes).
    Now asks with list-type=2 and follows NextContinuationToken, and stops if
    a page brings nothing new."""
    keys, token, seen = {}, None, set()
    while True:
        q = {"list-type": "2"}
        if token:
            q["continuation-token"] = token
        root = ET.fromstring(get(BASE + "?" + urllib.parse.urlencode(q)))
        ns = {"s": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
        find = (lambda e, t: e.findall(f"s:{t}", ns)) if ns else (lambda e, t: e.findall(t))
        text = (lambda e, t: (e.find(f"s:{t}", ns) if ns else e.find(t)))
        got, new = 0, 0
        for c in find(root, "Contents"):
            k, size = text(c, "Key").text, int(text(c, "Size").text)
            got += 1
            if k not in seen:
                seen.add(k)
                new += 1
            if re.search(r"(\d{4})_[NS]\d{2}[EW]\d{3}\.parquet$", k):
                keys[k] = size
        trunc = text(root, "IsTruncated")
        nt = text(root, "NextContinuationToken")
        print(f"  listing: {len(keys):,} tiles so far", flush=True)
        if not got or not new or trunc is None or trunc.text.strip().lower() != "true" or nt is None or not nt.text or nt.text == token:
            break
        token = nt.text
    return keys


def url_of(key):
    # Keys come back as "global-field-boundaries/download-tiles/..." (the
    # bucket is "ftw"); BASE already ends in global-field-boundaries/.
    k = re.sub(r"^(ftw/)?global-field-boundaries/", "", key)
    return BASE + k


def rows_in(key, size):
    import pyarrow as pa
    import pyarrow.parquet as pq
    tail = get(url_of(key), {"Range": f"bytes={size - 8}-{size - 1}"})
    if tail[4:] != b"PAR1":
        raise RuntimeError("not a parquet file")
    n = struct.unpack("<I", tail[:4])[0]
    footer = get(url_of(key), {"Range": f"bytes={size - 8 - n}-{size - 9}"})
    buf = b"PAR1" + footer + tail
    return pq.read_metadata(pa.BufferReader(buf)).num_rows


def main():
    stamp = OUT / "overview_build.json"
    if stamp.exists() and TILE.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print(f"{ROW}: weekly; not Monday")
        return
    pyramid.need("pyarrow")
    import numpy as np
    keys = listing()
    years = sorted({re.search(r"(\d{4})_[NS]\d{2}[EW]\d{3}\.parquet$", k).group(1) for k in keys})
    if not years:
        raise SystemExit(f"{ROW}: no download tiles listed")
    year = years[-1]
    mine = {k: s for k, s in keys.items() if re.search(rf"{year}_[NS]\d{{2}}[EW]\d{{3}}\.parquet$", k)}
    print(f"{ROW}: years {years}; {len(mine):,} tiles for {year}", flush=True)
    old = json.loads(stamp.read_text()) if stamp.exists() and not os.environ.get("FTW_AGAIN") else {}
    counts = {k: v for k, v in (old.get("counts") or {}).items() if k in mine and old.get("sizes", {}).get(k) == mine[k]}

    def one(k):
        try:
            return k, rows_in(k, mine[k])
        except Exception as e:  # noqa: BLE001
            print(f"    {k}: {e}", flush=True)
            return k, None
    todo = [k for k in mine if k not in counts]
    with ThreadPoolExecutor(16) as ex:
        for i, (k, n) in enumerate(ex.map(one, todo)):
            if n is not None:
                counts[k] = n
            if i % 500 == 499:
                print(f"  footers: {i + 1:,} of {len(todo):,}", flush=True)
    grid = np.zeros((180, 360), np.float32)
    for k, n in counts.items():
        m = re.search(r"_([NS])(\d{2})([EW])(\d{3})\.parquet$", k)
        lat = int(m.group(2)) * (1 if m.group(1) == "N" else -1)
        lon = int(m.group(4)) * (1 if m.group(3) == "E" else -1)
        # A tile named N00E005 is taken as the square from (5 E, 0 N) to (6 E, 1 N): its south-west corner.
        r, c = 89 - lat, lon + 180
        if 0 <= r < 180 and 0 <= c < 360:
            km2 = (111.32 ** 2) * math.cos(math.radians(lat + 0.5))
            grid[r, c] += n / max(km2, 1) * 100
    vals = np.sort(grid[grid > 0])
    if not len(vals):
        raise SystemExit(f"{ROW}: no fields counted")
    breaks = [float(vals[int(len(vals) * q)]) for q in (0.2, 0.4, 0.6, 0.8)]
    codes = np.zeros(grid.shape, np.uint8)
    codes[grid > 0] = 1
    for i, b in enumerate(breaks):
        codes[grid > b] = i + 2
    ramp = pyramid.RAMP5
    pal = {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(ramp)}
    pyramid.build(codes, -180.0, 90.0, 1.0, pal, TILE, 6, how="max", attribution="Fields of The World (CC BY 4.0)", name=ROW,
                  meta={"year": year, "tiles": len(counts)})
    fmt = lambda x: f"{x:,.1f}" if x < 10 else f"{x:,.0f}"
    edges = [float(vals[0])] + breaks + [float(vals[-1])]
    key = [[ramp[i], f"{fmt(edges[i])} to {fmt(edges[i + 1])} fields per 100 km²"] for i in range(5)]
    pyramid.write_choices(ROW, [{"label": f"fields counted, {year}", "archive": f"tiles/{ROW}.pmtiles", "key": key}])
    ch = pathlib.Path("tiles") / f"{ROW}.choices.json"
    d = json.loads(ch.read_text())
    d["choices"][0]["hint"] = f"Wider out: fields per 100 km² in each one-degree square, counted from the project's {year} download files"
    ch.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    OUT.mkdir(exist_ok=True)
    stamp.write_text(json.dumps({"year": year, "years": years, "tiles": len(mine), "read": len(counts), "fields": int(sum(counts.values())),
                                 "counts": counts, "sizes": {k: mine[k] for k in counts}, "date": datetime.date.today().isoformat()}))
    print(f"{ROW}: {int(sum(counts.values())):,} fields in {len(counts):,} squares ({year})")


if __name__ == "__main__":
    main()
