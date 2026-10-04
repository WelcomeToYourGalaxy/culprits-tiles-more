#!/usr/bin/env python3
"""
Illegal mining across the Amazon, from RAISG (Red Amazónica de Información
Socioambiental Georreferenciada), for the Culprits row asked for on 27
September (round 84b).

RAISG gives its files only to registered users (free), so the owner downloads
"Illegal mining" from https://www.raisg.org/en/maps/ and uploads the zip, as it
comes, into this repository's raisg/ folder. This turns every shapefile in it
(points, areas, rivers) into

  raisg/illegal_mining.geojson   every feature, every field, "group" saying
                                 which of RAISG's files it came from
  raisg/status.json              the files read and their counts

Each record keeps RAISG's own fields, citation included. Run daily; does
nothing until a zip is there, and again only when the zip changes.
"""
import hashlib, json, pathlib, subprocess, sys, tempfile, zipfile

DIR = pathlib.Path("raisg")
OUT = DIR / "illegal_mining.geojson"
STAMP = DIR / "status.json"
NAMES = {"pt": "Illegal mining sites (points)", "pol": "Illegal mining areas", "ln": "Rivers with illegal mining"}


def main():
    zips = sorted(DIR.glob("*.zip")) if DIR.is_dir() else []
    if not zips:
        print("raisg: no RAISG zip in raisg/ yet; the owner downloads it from raisg.org (free registration) and uploads it here")
        return
    fp = hashlib.sha1(b"".join(z.read_bytes() for z in zips)).hexdigest()
    try:
        if json.loads(STAMP.read_text()).get("from") == fp:
            print("raisg: unchanged")
            return
    except Exception:  # noqa: BLE001
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyshp", "pyproj"], check=True)
    import shapefile
    work = pathlib.Path(tempfile.mkdtemp())
    for z in zips:
        zipfile.ZipFile(z).extractall(work)
        for inner in work.rglob("*.zip"):
            zipfile.ZipFile(inner).extractall(inner.parent)
    feats, counts = [], {}
    for shp in sorted(work.rglob("*.shp")):
        if shp.name.startswith("._") or "__MACOSX" in str(shp):
            continue
        prj = shp.with_suffix(".prj")
        tr = None
        if prj.exists() and "GEOGCS" not in prj.read_text(errors="replace")[:20]:
            from pyproj import CRS, Transformer
            tr = Transformer.from_crs(CRS.from_wkt(prj.read_text(errors="replace")), "EPSG:4326", always_xy=True)
        rd = shapefile.Reader(str(shp), encoding="utf-8", encodingErrors="replace")
        names = [f[0] for f in rd.fields[1:]]
        stem = shp.stem.lower()
        group = next((v for k, v in NAMES.items() if stem.endswith("_" + k) or f"_{k}_" in stem), shp.stem.replace("_", " "))
        n = 0
        for sr in rd.iterShapeRecords():
            g = sr.shape.__geo_interface__
            if not g or not g.get("coordinates"):
                continue
            if tr:
                def conv(c):
                    if isinstance(c[0], (int, float)):
                        return list(tr.transform(c[0], c[1]))
                    return [conv(x) for x in c]
                g = {"type": g["type"], "coordinates": conv(g["coordinates"])}
            p = {k: v for k, v in zip(names, sr.record) if v not in (None, "")}
            p = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in p.items()}
            p["group"] = group
            p["file"] = shp.name
            feats.append({"type": "Feature", "geometry": g, "properties": p})
            n += 1
        counts[shp.name] = n
    DIR.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats,
                               "source": "RAISG, Amazonía Socioambiental (raisg.org), as downloaded by the owner"}, ensure_ascii=False))
    STAMP.write_text(json.dumps({"from": fp, "files": counts}, indent=1))
    print(f"raisg: {len(feats):,} features from {len(counts)} shapefiles: {counts}")


if __name__ == "__main__":
    main()
