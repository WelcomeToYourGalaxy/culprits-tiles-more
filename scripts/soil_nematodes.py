#!/usr/bin/env python3
"""
Soil nematodes for the Culprits map: the global database of soil nematode
abundance and functional group composition (van den Hoogen, Geisen, Wall et
al., Scientific Data 7, 103, 2020; https://doi.org/10.1038/s41597-020-0437-3),
the samples behind the global nematode maps of van den Hoogen et al. 2019
(Nature 572, 194). Its figshare collection (10.6084/m9.figshare.c.4718003) is
released under CC0:

  Nematode_abundance_dataset             nematode_full_dataset_wBiome.csv
  Nematode_abundance_aggregated_wCovar   nematode_aggregated_wCovariateData.csv

Both files are copied whole: every row that gives a position becomes a point
with every column of its row. Rows with no position are counted, not dropped
silently. Written to soil/nematodes_samples.geojson and
soil/nematodes_aggregated.geojson, with soil/nematodes.build.json saying what
was read (columns, counts, the columns taken as the position).

Rebuilt only when a file changes (its checksum is kept in the build file).
"""
import csv, hashlib, io, json, pathlib, re, sys, time, urllib.request

API = "https://api.figshare.com/v2"
COLLECTION = 4718003
WANT = {  # figshare article title -> output name
    "Nematode_abundance_dataset": "nematodes_samples",
    "Nematode_abundance_aggregated_wCovar": "nematodes_aggregated",
}
OUT = pathlib.Path("soil")
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
LAT = re.compile(r"^(pixel_?)?lat(itude)?(_?dd)?$", re.I)
LON = re.compile(r"^(pixel_?)?(lon|long|longitude)(_?dd)?$", re.I)


def get(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"    {url}: {e}; again in {20 * (i + 1)}s", flush=True)
            time.sleep(20 * (i + 1))


def value(v):
    t = (v or "").strip()
    if t == "" or t.upper() in ("NA", "NAN", "NULL"):
        return None
    try:
        f = float(t)
        return int(f) if re.fullmatch(r"-?\d+", t) else f
    except ValueError:
        return t


def main():
    OUT.mkdir(exist_ok=True)
    build_file = OUT / "nematodes.build.json"
    old = json.loads(build_file.read_text()) if build_file.exists() else {}
    report = {"source": "van den Hoogen et al. 2020, Scientific Data 7, 103; figshare collection 10.6084/m9.figshare.c.4718003",
              "licence": "CC0 1.0", "files": {}}
    articles = json.loads(get(f"{API}/collections/{COLLECTION}/articles?page_size=100"))
    found = 0
    for art in articles:
        name = WANT.get(art.get("title"))
        if not name:
            continue
        detail = json.loads(get(f"{API}/articles/{art['id']}"))
        lic = (detail.get("license") or {}).get("name", "")
        for f in detail.get("files", []):
            if not f.get("name", "").lower().endswith(".csv"):
                continue
            found += 1
            raw = get(f["download_url"])
            digest = hashlib.sha256(raw).hexdigest()
            out = OUT / f"{name}.geojson"
            if out.exists() and old.get("files", {}).get(name, {}).get("sha256") == digest:
                print(f"  {name}: unchanged")
                report["files"][name] = old["files"][name]
                continue
            text = raw.decode("utf-8-sig", errors="replace")
            rows = list(csv.DictReader(io.StringIO(text)))
            cols = list(rows[0].keys()) if rows else []
            lat = next((c for c in cols if LAT.match(c.strip())), None)
            lon = next((c for c in cols if LON.match(c.strip())), None)
            if not lat or not lon:
                report["files"][name] = {"file": f["name"], "licence": lic, "columns": cols, "rows": len(rows),
                                         "error": "no latitude/longitude columns recognised; nothing written"}
                print(f"  {name}: no position columns among {cols}", flush=True)
                continue
            feats, nowhere = [], 0
            for r in rows:
                y, x = value(r.get(lat)), value(r.get(lon))
                if not isinstance(y, (int, float)) or not isinstance(x, (int, float)) or not (-90 <= y <= 90 and -180 <= x <= 180):
                    nowhere += 1
                    continue
                props = {k.strip(): value(v) for k, v in r.items() if k is not None}
                feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]}, "properties": props})
            out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")))
            report["files"][name] = {"file": f["name"], "figshare_article": art["id"], "licence": lic, "sha256": digest,
                                     "columns": cols, "position_columns": [lat, lon], "rows": len(rows),
                                     "points": len(feats), "no_position": nowhere}
            print(f"  {name}: {len(feats)} points, {nowhere} rows with no position ({f['name']}, {lic})", flush=True)
    if not found:
        sys.exit("soil nematodes: the figshare collection listed none of the expected files")
    build_file.write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
