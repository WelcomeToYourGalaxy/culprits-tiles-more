#!/usr/bin/env python3
"""
Every facility point behind EPA's Envirofacts multisystem widget, so the
Culprits map can show them at every zoom.

EPA's own service (EMEF/efpoints) draws its points only from about state level
in. This asks the same service for every point in every one of its layers and
tiles them into

  tiles/epa_efpoints.pmtiles     layer "efpoints"

Each point carries only which EPA layer it is in (_lid, _layer), its object id
(_oid) and its name, to keep the file small. The map fetches the full record
from EPA, live, when a point is clicked. Every point is drawn at every zoom; none
are merged (23 September).

Rebuilt once a week (or with EPA_REBUILD=1). A layer EPA does not answer for is
named in the log and left out of that week's build; the build stops rather than
publish if EPA answers for none.
"""
import json, os, pathlib, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request

SERVICE = "https://geopub.epa.gov/arcgis/rest/services/EMEF/efpoints/MapServer"
OUT = pathlib.Path("tiles/epa_efpoints.pmtiles")
LIMIT = 95 * 1024 * 1024
WEEK = 7 * 24 * 3600
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}


def sh(*cmd, **kw):
    print("  $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def tools():
    if shutil.which("tippecanoe"):
        return
    sh("sudo", "apt-get", "update", "-qq")
    sh("sudo", "apt-get", "install", "-y", "-qq", "libsqlite3-dev", "zlib1g-dev", "build-essential")
    d = tempfile.mkdtemp()
    sh("git", "clone", "--depth", "1", "https://github.com/felt/tippecanoe.git", d)
    sh("make", "-j4", cwd=d)
    sh("sudo", "make", "install", cwd=d)


def ask(url, data=None, tries=6):
    body = urllib.parse.urlencode(data).encode() if data else None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers=UA)
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.loads(r.read().decode("utf-8"))
            if isinstance(out, dict) and out.get("error"):
                raise RuntimeError(out["error"].get("message") or str(out["error"]))
            return out
        except Exception as e:
            if i == tries - 1:
                raise
            wait = 5 * (i + 1)
            print(f"    EPA did not answer ({e}); again in {wait}s", flush=True)
            time.sleep(wait)


STAMP = OUT.with_suffix(".build.json")
TRIED = OUT.with_suffix(".tried.json")
MONTH = 28 * 24 * 3600
LIVE_FROM = 6          # the map draws EPA's own picture from zoom 6.5; the copy is for the zooms wider out


def main():
    # Built every four weeks: each build is several files, and every one stays
    # in the repository's history. A build that did not fit is not tried again
    # for a week, and never removes the copy that is there.
    fresh = lambda p, age: p.exists() and time.time() - p.stat().st_mtime < age
    if not os.environ.get("EPA_REBUILD") and (fresh(STAMP, MONTH) or fresh(TRIED, WEEK)):
        print("epa_efpoints: built less than four weeks ago, or tried less than a week ago")
        return
    info = ask(f"{SERVICE}?f=json")
    layers = [l for l in info.get("layers", []) if not l.get("subLayerIds")]
    print(f"epa_efpoints: {len(layers)} layers")
    work = pathlib.Path(tempfile.mkdtemp())
    pts = work / "efpoints.geojsonl"
    total, answered = 0, 0
    with open(pts, "w", encoding="utf-8") as fo:
        for l in layers:
            lid, lname = l["id"], l.get("name", "")
            try:
                meta = ask(f"{SERVICE}/{lid}?f=json")
                name_field = meta.get("displayField") or ""
                oid_field = next((f["name"] for f in meta.get("fields", []) if f.get("type") == "esriFieldTypeOID"), "OBJECTID")
                step = max(100, min(int(meta.get("maxRecordCount") or 1000), 2000))
                ids = sorted(ask(f"{SERVICE}/{lid}/query", {"where": "1=1", "returnIdsOnly": "true", "f": "json"}).get("objectIds") or [])
            except Exception as e:
                print(f"  {lname}: EPA did not answer ({e}); left out this week")
                continue
            answered += 1
            got = 0
            fields = ",".join(x for x in (oid_field, name_field) if x)
            for a in range(0, len(ids), step):
                chunk = ids[a:a + step]
                try:
                    res = ask(f"{SERVICE}/{lid}/query", {
                        "objectIds": ",".join(map(str, chunk)), "outFields": fields,
                        "returnGeometry": "true", "outSR": "4326", "f": "json"})
                except Exception as e:
                    print(f"    {lname}: records {a}-{a + len(chunk)} not answered ({e}); left out")
                    continue
                for f in res.get("features", []):
                    g = f.get("geometry") or {}
                    x, y = g.get("x"), g.get("y")
                    if x is None or y is None or x != x or y != y:
                        continue
                    at = f.get("attributes") or {}
                    props = {"_lid": lid, "_layer": lname, "_oid": at.get(oid_field)}
                    if name_field and at.get(name_field) not in (None, ""):
                        props["name"] = at.get(name_field)
                    fo.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": [x, y]},
                                         "properties": props}, separators=(",", ":"), ensure_ascii=False) + "\n")
                    got += 1
                if (a // step) % 50 == 0:
                    print(f"    {lname}: {min(a + step, len(ids)):,} of {len(ids):,}", flush=True)
                time.sleep(0.15)
            print(f"  {lname}: {got:,} points")
            total += got
    if not answered or not total:
        sys.exit("epa_efpoints: EPA answered for no layer; the last copy stays")
    tools()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # Every point at every zoom, none merged (asked for 23 September). One file
    # holding every point at every zoom was over GitHub's limit at any depth,
    # and the build that found so removed the last copy. Now each zoom from the
    # world view to LIVE_FROM is its own file, each point carries only its EPA
    # layer and object id (a click asks EPA for the rest, as before), and the
    # files replace the old ones only when every one of them fits.
    work = pathlib.Path(tempfile.mkdtemp())
    parts, sizes = [], {}
    for z in range(0, LIVE_FROM + 1):
        name = f"epa_efpoints_z{z}.pmtiles"
        sh("tippecanoe", "-o", str(work / name), "--force", "-q", "-l", "efpoints", f"-Z{z}", f"-z{z}", "-r1",
           "-y", "_lid", "-y", "_oid", "--no-feature-limit", "--no-tile-size-limit", str(pts))
        sizes[z] = (work / name).stat().st_size
        print(f"  zoom {z}: {sizes[z] / 1e6:.1f} MB", flush=True)
        parts.append({"file": name, "from": z, "to": z, "bytes": sizes[z]})
    if any(b > LIMIT for b in sizes.values()):
        TRIED.write_text(json.dumps({"points": total, "bytes_by_zoom": sizes}, indent=1))
        sys.exit("epa_efpoints: a zoom's file is over GitHub's limit; the copy that is there stays (sizes in " + str(TRIED) + ")")
    for p in parts:
        shutil.move(str(work / p["file"]), str(OUT.parent / p["file"]))
    STAMP.write_text(json.dumps({"points": total, "layers": answered, "points_merged": False, "parts": parts}, indent=1))
    OUT.with_suffix(".unmerged").unlink(missing_ok=True)
    TRIED.unlink(missing_ok=True)
    print(f"epa_efpoints: {total:,} points from {answered} of {len(layers)} layers, in {len(parts)} files")


if __name__ == "__main__":
    main()
