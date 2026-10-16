#!/usr/bin/env python3
"""
Oil and gas wells and the rest of the industry's sites, inside and near
protected areas, by distance, for the Invasion of non-humans map (round nh2,
asked 16 October).

Source: Environmental Defense Fund, the Oil and Gas Infrastructure Mapping
database (OGIM), newest version on Zenodo (record 7466758; v3.0 of September
2026 has about 7.6 million records in 193 countries: wells, offshore
platforms, compressor stations, processing plants, LNG terminals, refineries,
pipelines and more), CC BY 4.0. Omara, M. et al. 2023, Earth System Science
Data 15: 3761-3790. Every layer of the GeoPackage is read, every record kept.

Protected areas: the public release of the World Database on Protected Areas
(UNEP-WCMC and IUCN), as for the mines (scripts/lib/nhwdpa.py). Each site is
measured to the nearest protected or conserved area on the globe and put in a
band: inside, within 1 km, within 10 km, within 20 km, further than 20 km.

What each site carries: within 20 km of a protected area, every column OGIM
gives plus the nearest area's id, name, designation and IUCN category;
further away, the columns that name and place it (ids, name, type, status,
operator, country, source), so the files stay inside GitHub's limits.

Points become counted squares wider out and every site closer in (one set of
files per layer and band, scripts/lib/pointtiles.py); lines and shapes
(pipelines, fields, blocks) are tiled as they are, one file per layer and band.

  nonhuman/oilgas.json, nonhuman/oilgas/*.pmtiles, nonhuman/oilgas.build.json

Long: each run does the layers it has time for and the next run carries on.
Rebuilt when OGIM publishes a new version; OILGAS_REBUILD=1 builds again.
"""
import json, os, pathlib, re, sys, tempfile, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import nhcommon as nh  # noqa: E402
import nhwdpa  # noqa: E402

NAME = "oilgas"
RECORD = "https://zenodo.org/api/records/7466758/versions/latest"
START, BUDGET = time.time(), 130 * 60
CHUNK = 400_000
ID_COLS = re.compile(r"(^|_)(ogim_?id|fac_?id|fac_?name|fac_?type|fac_?status|ogim_?status|status|operator|country|state_?prov|src_?ref_?id|src_?date|category)$", re.I)


def tile_shapes(mines, nd, out, layer):
    top = 10
    while True:
        mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-l", layer, "-Z0", f"-z{top}", "--no-feature-limit", "--no-tile-size-limit",
                 "--attribution", "OGIM (Environmental Defense Fund), CC BY 4.0; WDPA (UNEP-WCMC and IUCN)", str(nd))
        if out.stat().st_size <= 95 * 1024 * 1024:
            return top
        if top <= 4:
            out.unlink()
            raise RuntimeError(f"{out.name} is over GitHub's limit even to zoom 4")
        top -= 1


def main():
    st = nh.read_stamp(NAME)
    nh.pip("geopandas", "pyogrio", "shapely>=2", "pyproj", "pandas")
    import numpy as np
    import pyogrio
    rec = nh.get_json(RECORD)
    version = (rec.get("metadata") or {}).get("version") or str(rec.get("id"))
    meta_path = nh.OUT / "oilgas.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if meta.get("version") != version or os.environ.get("OILGAS_REBUILD"):
        meta = {"version": version, "layers": []}
    done = {l["name"] for l in meta.get("layers", [])}
    if meta.get("complete") and not os.environ.get("OILGAS_REBUILD"):
        print(f"oilgas: OGIM {version} built; built again when a new version is published")
        return
    mines = nh.tools()
    import pointtiles
    work = pathlib.Path(os.environ.get("RUNNER_TEMP") or tempfile.mkdtemp()) / "oilgas"
    work.mkdir(parents=True, exist_ok=True)
    f = next(x for x in rec.get("files", []) if x["key"].lower().endswith(".gpkg"))
    gpkg = nh.download(f["links"]["self"], work / f["key"], "OGIM")
    layers = [(str(n), str(g)) for n, g in pyogrio.list_layers(str(gpkg))]
    print(f"oilgas: OGIM {version}, layers {layers}", flush=True)
    P, Q, wdpa, used = nhwdpa.get(work)
    report = {"version": version, "layers in the file": layers, "wdpa": wdpa, "wdpa layers read": used, "this run": {}}
    for lname, gtype in layers:
        if lname in done:
            continue
        if time.time() - START > BUDGET:
            report["stopped"] = f"time budget reached before {lname}; the next run carries on"
            break
        info = pyogrio.read_info(str(gpkg), layer=lname)
        n = int(info.get("features") or 0)
        cols = list(info["fields"])
        keep_far = [c for c in cols if ID_COLS.search(c)]
        kind = "point" if "point" in gtype.lower() else "line" if "line" in gtype.lower() else "shape"
        counts = {b: 0 for b in nhwdpa.BANDS}
        files = {b: work / f"{nh.slug(lname)}_{nh.slug(b)}.ndjson" for b in nhwdpa.BANDS}
        handles = {b: open(p, "w") for b, p in files.items()}
        for s0 in range(0, max(n, 1), CHUNK):
            df = pyogrio.read_dataframe(str(gpkg), layer=lname, skip_features=s0, max_features=CHUNK)
            if not len(df):
                break
            df = df.to_crs(4326) if df.crs and df.crs.to_epsg() != 4326 else df
            df = df[df.geometry.notna() & ~df.geometry.is_empty]
            km, ix, src = nhwdpa.nearest(df.geometry.values, P, Q, log=lambda t: print(t, flush=True))
            for i, (_, r) in enumerate(df.iterrows()):
                k = float(km[i]) if np.isfinite(km[i]) else None
                band = nhwdpa.band_of(k)
                counts[band] += 1
                near = nhwdpa.describe(km[i], ix[i], src[i], P, Q)
                props = {c: r[c] for c in (cols if near else keep_far) if c in r and r[c] is not None and r[c] == r[c] and str(r[c]).strip() not in ("", "N/A", "NA")}
                props = {c: (v.isoformat()[:10] if hasattr(v, "isoformat") else v.item() if hasattr(v, "item") else v) for c, v in props.items()}
                props.update(near)
                props["band"] = band
                props["layer"] = lname
                g = r.geometry
                if kind == "point":
                    p = g if g.geom_type == "Point" else g.representative_point()
                    handles[band].write(json.dumps([round(p.x, 5), round(p.y, 5), props], ensure_ascii=False, default=str) + "\n")
                else:
                    handles[band].write(json.dumps({"type": "Feature", "geometry": g.__geo_interface__, "properties": props}, ensure_ascii=False, default=str) + "\n")
            print(f"  {lname}: {min(s0 + CHUNK, n):,} of {n:,}", flush=True)
        for h in handles.values():
            h.close()
        sets = {}
        for b, p in files.items():
            if not counts[b]:
                continue
            out = nh.OUT / "oilgas" / f"{nh.slug(lname)}_{nh.slug(b)}.pmtiles"
            if kind == "point":
                pts = [tuple(json.loads(l)) for l in p.open()]
                parts = pointtiles.build(pts, out, "oilgas", "layer", attribution="OGIM (Environmental Defense Fund), CC BY 4.0; WDPA (UNEP-WCMC and IUCN)")
                del pts
                sets[b] = [dict(x, file="oilgas/" + x["file"]) for x in parts]
            else:
                out.parent.mkdir(parents=True, exist_ok=True)
                top = tile_shapes(mines, p, out, "oilgas")
                sets[b] = [{"file": "oilgas/" + out.name, "from": 0, "to": top, "bytes": out.stat().st_size}]
            p.unlink()
        meta["layers"].append({"name": lname, "label": lname.replace("_", " "), "kind": kind, "count": sum(counts.values()), "counts": counts,
                               "columns": cols, "columns kept beyond 20 km": keep_far, "sets": sets})
        report["this run"][lname] = counts
        meta.update({"source": f"OGIM {version} (Environmental Defense Fund), Zenodo record 7466758, CC BY 4.0", "wdpa": wdpa, "bands": nhwdpa.BANDS, "detail": 8,
                     "made": nh.datetime.datetime.utcnow().strftime("%Y-%m-%d")})
        nh.write_json("oilgas.json", meta, compact=False)
    meta["complete"] = "stopped" not in report and {l["name"] for l in meta["layers"]} >= {l for l, _ in layers}
    nh.write_json("oilgas.json", meta, compact=False)
    nh.write_stamp(NAME, dict(report, complete=meta["complete"]))


if __name__ == "__main__":
    main()
