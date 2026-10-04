#!/usr/bin/env python3
"""
Freshwater fish species in each river basin (round 100b, asked 28 September,
for Biodiversity loss > Fish).

Source: Tedesco et al. 2017, "A global database on freshwater fish species
occurrence in drainage basins", Scientific Data 4, 170141; figshare article
5245072 (collection doi 10.6084/m9.figshare.c.3739145), CC0. 3,119 drainage
basins, and for each every freshwater fish species recorded in it, native or
introduced.

Counted per basin, from the occurrence table as published:
  native_species       species whose status in the basin is native
  introduced_species   species whose status in the basin is introduced/exotic
  endemic_species      native species recorded as native in no other basin
Every field of the basin table is kept with them.

  tiles/fish_basins.pmtiles   layer "basins"
  fish/basins_build.json      the files and columns read, counts

Built once; FISH_REBUILD=1 builds it again.
"""
import collections, csv, io, json, os, pathlib, re, sys, tempfile, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

ARTICLE = "https://api.figshare.com/v2/articles/5245072"
TILE = pathlib.Path("tiles") / "fish_basins.pmtiles"
OUT = pathlib.Path("fish")
UA = {"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy)"}
LIMIT = 95 * 1024 * 1024


def get(url, timeout=600):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def table(raw):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = text.split("\n", 1)[0]
    sep = max([";", ",", "\t"], key=first.count)
    return list(csv.DictReader(io.StringIO(text), delimiter=sep))


def col(rows, *pats):
    keys = list(rows[0]) if rows else []
    for pat in pats:
        for k in keys:
            if re.search(pat, k, re.I):
                return k
    return None


def main():
    if TILE.exists() and not os.environ.get("FISH_REBUILD"):
        print("fish_basins: already built")
        return
    import mines
    mines.tools()
    art = json.loads(get(ARTICLE, 120))
    f = max(art["files"], key=lambda x: x["size"])
    work = pathlib.Path(tempfile.mkdtemp())
    z = work / "fish.zip"
    z.write_bytes(get(f["download_url"], 1800))
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        print(f"fish_basins: in the zip: {names}", flush=True)
        zf.extractall(work)
        # A zip inside the zip (the basin shapes) is opened too.
        for n in names:
            if n.lower().endswith(".zip"):
                with zipfile.ZipFile(work / n) as inner:
                    inner.extractall(work / pathlib.Path(n).stem)
    csvs = [p for p in work.rglob("*.csv") if "__MACOSX" not in str(p)]
    occ_p = next(p for p in csvs if re.search(r"occurr", p.name, re.I))
    bas_p = next((p for p in csvs if re.search(r"basin", p.name, re.I) and p != occ_p), None)
    occ = table(occ_p.read_bytes())
    basin_c = col(occ, r"basin.?name", r"basin")
    species_c = col(occ, r"fishbase.?valid", r"valid.?species", r"species")
    status_c = col(occ, r"native.?exotic", r"status")
    print(f"fish_basins: occurrences {len(occ):,}; columns {list(occ[0])}; basin {basin_c}, species {species_c}, status {status_c}", flush=True)
    native, intro, where = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
    statuses = collections.Counter()
    for r in occ:
        b, sp, st = (r.get(basin_c) or "").strip(), (r.get(species_c) or "").strip(), (r.get(status_c) or "").strip().lower()
        if not b or not sp:
            continue
        statuses[st] += 1
        if st.startswith("nativ"):
            native[b].add(sp)
            where[sp].add(b)
        elif re.match(r"(exotic|introd|non.?nativ|alien)", st):
            intro[b].add(sp)
    print(f"fish_basins: status values {dict(statuses)}", flush=True)
    endemic = {b: {sp for sp in s if len(where[sp]) == 1} for b, s in native.items()}
    extra = {}
    if bas_p:
        bt = table(bas_p.read_bytes())
        bk = col(bt, r"basin.?name", r"basin")
        for r in bt:
            extra[(r.get(bk) or "").strip()] = {k: v for k, v in r.items() if k and v not in (None, "")}
    shp = next(p for p in work.rglob("*.shp") if "__MACOSX" not in str(p))
    gj = work / "basins.geojson"
    mines.sh("ogr2ogr", "-f", "GeoJSON", "-t_srs", "EPSG:4326", "-makevalid", str(gj), str(shp))
    feats = json.loads(gj.read_text(encoding="utf-8", errors="replace"))["features"]
    name_k = next((k for k in (feats[0]["properties"] if feats else {}) if re.search(r"basin.?name|^basin", k, re.I)), None)
    print(f"fish_basins: {len(feats)} basin shapes; name field {name_k}; fields {list(feats[0]['properties']) if feats else []}", flush=True)
    lines = work / "basins.geojsons"
    matched = 0
    with lines.open("w", encoding="utf-8") as w:
        for ft in feats:
            p = dict(ft.get("properties") or {})
            b = str(p.get(name_k) or "").strip()
            if b in native or b in intro:
                matched += 1
            p.update({f"x_{k}": v for k, v in extra.get(b, {}).items() if f"x_{k}" not in p})
            p.update({"native_species": len(native.get(b, ())), "introduced_species": len(intro.get(b, ())), "endemic_species": len(endemic.get(b, ()))})
            w.write(json.dumps({"type": "Feature", "properties": p, "geometry": ft.get("geometry")}) + "\n")
    if not matched:
        raise SystemExit("fish_basins: no basin shape matched a basin of the occurrence table; see the fields above")
    TILE.parent.mkdir(exist_ok=True)
    for top in (8, 7, 6):
        mines.sh("tippecanoe", "-o", str(TILE), "--force", "-q", "-l", "basins", "-Z0", f"-z{top}", "--detect-shared-borders",
                 "--coalesce-densest-as-needed", "--simplification=4", "--maximum-tile-bytes=800000", str(lines))
        if TILE.stat().st_size <= LIMIT:
            break
    OUT.mkdir(exist_ok=True)
    (OUT / "basins_build.json").write_text(json.dumps({"file": f["name"], "occurrences": len(occ), "columns": {"basin": basin_c, "species": species_c, "status": status_c},
                                                      "status_values": dict(statuses), "basins_with_fish": len(set(native) | set(intro)),
                                                      "shapes": len(feats), "shapes_matched": matched, "to_zoom": top}, indent=1))
    print(f"fish_basins: {matched} of {len(feats)} basins matched, zooms 0 to {top}")


if __name__ == "__main__":
    main()
