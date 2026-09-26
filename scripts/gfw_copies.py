#!/usr/bin/env python3
"""
Our own copies of Global Forest Watch datasets that its tile service draws
slowly or not at all on the Culprits map: BirdLife's Endemic Bird Areas and
Peru's forest concessions (both of GFW's datasets for them). Each is
downloaded whole from GFW's data API (the dataset's latest version, as a
GeoPackage), and written as one GeoJSON file with every feature and every
field; coordinates are kept to 5 decimal places (about a metre), nothing is
simplified or left out.

  gfw/<dataset>.geojson      the copy
  gfw/<dataset>.build.json   the version copied, its fields, how many features

A dataset is copied again only when GFW publishes a new version. A dataset that
cannot be read keeps its last copy and is named in the log; the others go on.
"""
import json, pathlib, subprocess, sys, tempfile, time, urllib.request

API = "https://data-api.globalforestwatch.org"
DATASETS = ["birdlife_endemic_bird_areas", "per_forest_concessions", "osinfor_per_forest_concessions"]
OUT = pathlib.Path("gfw")
LIMIT = 90 * 1024 * 1024
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}


def need():
    try:
        import geopandas, pyogrio  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "geopandas", "pyogrio"], check=True)


def get(url, tries=5, binary=False):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=900) as r:
                b = r.read()
                return b if binary else json.loads(b)
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"    {url}: {e}; again in {30 * (i + 1)}s", flush=True)
            time.sleep(30 * (i + 1))


def version_of(ds):
    try:
        return get(f"{API}/dataset/{ds}/latest")["data"]["version"]
    except Exception:  # noqa: BLE001
        vs = (get(f"{API}/dataset/{ds}")["data"] or {}).get("versions") or []
        key = lambda v: [int(x) if x.isdigit() else x for x in __import__("re").split(r"(\d+)", v)]
        return sorted(vs, key=key)[-1] if vs else None


def copy(ds):
    import geopandas as gpd
    build = OUT / f"{ds}.build.json"
    old = json.loads(build.read_text()) if build.exists() else {}
    ver = version_of(ds)
    if not ver:
        raise RuntimeError("GFW lists no version")
    if old.get("version") == ver and (OUT / f"{ds}.geojson").exists():
        print(f"  {ds}: {ver} already copied")
        return
    meta = get(f"{API}/dataset/{ds}")["data"].get("metadata") or {}
    with tempfile.TemporaryDirectory() as t:
        src = pathlib.Path(t) / f"{ds}.gpkg"
        src.write_bytes(get(f"{API}/dataset/{ds}/{ver}/download/gpkg", binary=True))
        gdf = gpd.read_file(src)
        if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(4326)
        for c in gdf.columns:
            if c != gdf.geometry.name and str(gdf[c].dtype).startswith(("datetime", "timedelta")):
                gdf[c] = gdf[c].astype(str)
        tmp = pathlib.Path(t) / "out.geojson"
        gdf.to_file(tmp, driver="GeoJSON", engine="pyogrio", COORDINATE_PRECISION=5, RFC7946="YES")
        size = tmp.stat().st_size
        if size > LIMIT:
            raise RuntimeError(f"{size / 1e6:.0f} MB, over the {LIMIT / 1e6:.0f} MB limit; not copied")
        (OUT / f"{ds}.geojson").write_bytes(tmp.read_bytes())
    build.write_text(json.dumps({"dataset": ds, "version": ver, "title": meta.get("title"), "source": meta.get("source"),
                                 "license": meta.get("license"), "features": int(len(gdf)),
                                 "fields": [c for c in gdf.columns if c != gdf.geometry.name], "megabytes": round(size / 1e6, 1)},
                                indent=1))
    print(f"  {ds}: {ver}, {len(gdf)} features, {size / 1e6:.1f} MB", flush=True)


def main():
    need()
    OUT.mkdir(exist_ok=True)
    failed = []
    for ds in DATASETS:
        try:
            copy(ds)
        except Exception as e:  # noqa: BLE001
            print(f"  {ds}: could not be copied ({e}); its last copy stays", flush=True)
            failed.append(ds)
    if len(failed) == len(DATASETS):
        sys.exit("gfw copies: none could be copied")


if __name__ == "__main__":
    main()
