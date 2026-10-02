#!/usr/bin/env python3
"""
Animal populations rising or falling, from the Living Planet Database (round
137b, asked 2 October: the decline of salt and fresh water fish; the LPI holds
fish among every vertebrate). ZSL and WWF's public Living Planet Database.

Its download is behind an agreement form (livingplanetindex.org/download), so
the owner downloads it once and uploads the file (csv, or the zip it comes
in) into this repository's lpi/download/ folder. Its terms: for conservation,
scientific analysis or research; credit the database and each record's own
source; anything passed on goes with the same terms; a copy of products made
with it is to be sent to LivingPlanetIndex@ioz.ac.uk.

  tiles/lpi_populations.pmtiles  one point per population at its latitude
                            and longitude, with its class, system, name,
                            change and last counted year
  lpi/lpi_populations/<hh>.json.gz  each population's whole record (every
                            field, the counts as one line of "year: value",
                            first and last counted years, the change)
  lpi/build.json            counts, and populations with no position

Nothing is left out: every class and system (freshwater, marine,
terrestrial) is kept; the map filters by them. Runs when a new download is
in lpi/download/.
"""
import csv, io, json, pathlib, re, zipfile

DL = pathlib.Path("lpi/download")
OUT = pathlib.Path("lpi")


def rows():
    for p in sorted(DL.glob("*")):
        if p.suffix.lower() == ".zip":
            z = zipfile.ZipFile(p)
            for n in z.namelist():
                # Skip the Mac copies the zip carries (__MACOSX/._name.csv): not data.
                if n.lower().endswith(".csv") and "__MACOSX" not in n and not n.rsplit("/", 1)[-1].startswith("._"):
                    yield from csv.DictReader(io.TextIOWrapper(z.open(n), encoding="utf-8-sig", errors="replace"))
        elif p.suffix.lower() == ".csv":
            with open(p, encoding="utf-8-sig", errors="replace") as f:
                yield from csv.DictReader(f)


def num(v):
    try:
        x = float(str(v).strip())
        return x if x == x else None
    except ValueError:
        return None


def main():
    got = [p for p in DL.glob("*") if p.suffix.lower() in (".csv", ".zip")] if DL.exists() else []
    if not got:
        print("lpi_populations: nothing in lpi/download/ yet; upload the Living Planet Database file there")
        return
    stamp = OUT / "build.json"
    newest = max(p.stat().st_size for p in got) + len(got)   # a new file changes the size (git does not keep times)
    if stamp.exists() and json.loads(stamp.read_text()).get("download_time") == newest:
        print("lpi_populations: already built from this download")
        return
    feats, no_place = [], 0
    for r in rows():
        lat, lon = num(r.get("Latitude")), num(r.get("Longitude"))
        years = sorted((int(k), num(v)) for k, v in r.items() if k and re.fullmatch(r"\d{4}", k.strip()) and num(v) is not None)
        p = {k: v for k, v in r.items() if k and not re.fullmatch(r"\d{4}", k.strip()) and v not in (None, "", "NULL")}
        if years:
            (y0, v0), (y1, v1) = years[0], years[-1]
            p["counts (year: value)"] = "; ".join(f"{y}: {v:g}" for y, v in years)
            p["first counted"], p["last counted"] = y0, y1
            if v0 > 0:
                p["change, first to last count (%)"] = round(100 * (v1 - v0) / v0, 1)
        p["group"] = p.get("System", "not given")
        if lat is None or lon is None:
            no_place += 1
            continue
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": p})
    OUT.mkdir(exist_ok=True)
    # 36,000 populations with their citations make a 46 MB file, too heavy for
    # a browser to read whole: the points go to map tiles with the fields the
    # map colours and filters by, and each one's whole record to its box
    # files (as the IBAMA layers do; env_enforcement.write_layer).
    import sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import env_enforcement
    env_enforcement.OUT = OUT
    slim, boxes = [], {}
    for f in feats:
        p = f["properties"]
        key = str(p.get("ID") or len(slim))
        boxes[key] = p
        keep = {"id": key, "x_class": p.get("Class", ""), "x_system": p.get("System", ""), "x_name": p.get("Common_name") or p.get("Binomial", "")}
        if "change, first to last count (%)" in p:
            keep["x_change"] = p["change, first to last count (%)"]
        if "last counted" in p:
            keep["x_last"] = p["last counted"]
        slim.append({"type": "Feature", "geometry": f["geometry"], "properties": keep})
    env_enforcement.write_layer("lpi_populations", slim, boxes)
    classes = {}
    for f in feats:
        k = f["properties"].get("Class", "not given")
        classes[k] = classes.get(k, 0) + 1
    stamp.write_text(json.dumps({"populations": len(feats), "no_position": no_place, "classes": classes, "download_time": newest}, indent=1))
    print(f"lpi_populations: {len(feats)} populations; {no_place} with no position", flush=True)


if __name__ == "__main__":
    main()
