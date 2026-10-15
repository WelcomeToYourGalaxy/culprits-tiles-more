#!/usr/bin/env python3
"""
Human impact on the Moon and Mars (round 197o, asked 14 October), for the
map's Moon and Mars views (culprits map/bodies.html). Everything each source
gives is kept as it comes; nothing is filtered or merged.

  bodies/moon_objects.geojson   LROC's coordinates of human-made objects on
                                the Moon: landers, rovers, experiments left
                                behind, impact craters, retroreflectors.
                                PDS archive (public domain, LROC's terms);
                                cite Wagner et al. 2017, Icarus 283:92-103.
  bodies/moon_list.geojson      Wikipedia, "List of artificial objects on the
  bodies/mars_list.geojson      Moon" / "...on Mars": every row of every table,
                                every column as written (masses included),
                                placed where the row gives coordinates.
                                Rows with no coordinates are kept in the file
                                with no geometry (the page lists them).
                                CC BY-SA 4.0.
  bodies/moon_names.geojson     IAU names (USGS Gazetteer of Planetary
  bodies/mars_names.geojson     Nomenclature), every feature, for reading the
                                map. USGS, public domain.
  bodies/artemis3.geojson       NASA's nine candidate Artemis III landing
                                regions (October 2024). NASA has published
                                them only as a picture, so each is placed at
                                the IAU centre of the feature it is named
                                after, and says so.
  bodies/rovers/<file>.json     NASA/JPL's rover maps (MMGIS): Perseverance
                                (M20) and Curiosity (MSL) waypoints and drives,
                                copied each run; the page reads NASA's own
                                copy first and these only if that is refused.
  bodies/raw/                   what was downloaded, as it came
  bodies/build.json             counts, what failed, what could not be placed

Daily, with the refresh, or by hand.
"""
import datetime, html, io, json, math, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request, zipfile
from html.parser import HTMLParser

OUT = pathlib.Path("bodies")
RAW = OUT / "raw"
UA = {"User-Agent": "WelcomeToYourGalaxy Culprits map (welcometoyourgalaxy@gmail.com)"}

LROC = ("https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/EXTRAS/SHAPEFILE/"
        "ANTHROPOGENIC_OBJECTS/ANTHROPOGENIC_OBJECTS_180.ZIP")
NAMES = {"moon": "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MOON_nomenclature_center_pts.zip",
         "mars": "https://asc-planetarynames-data.s3.us-west-2.amazonaws.com/MARS_nomenclature_center_pts.zip"}
WIKI = {"moon": "List of artificial objects on the Moon", "mars": "List of artificial objects on Mars"}
ROVERS = ["M20/Layers/json/M20_waypoints.json", "M20/Layers/json/M20_traverse.json",
          "MSL/Layers/json/MSL_waypoints.json", "MSL/Layers/json/MSL_traverse.json"]
ROVER_BASE = "https://mars.nasa.gov/mmgis-maps/"

# NASA's names for the regions (news release, 28 October 2024), and the IAU
# features each is named after, tried in this order.
ARTEMIS = [
    ("Peak near Cabeus B", ["Cabeus B"]),
    ("Haworth", ["Haworth"]),
    ("Malapert Massif", ["Malapert Massif", "Mons Malapert", "Malapert"]),
    ("Mons Mouton Plateau", ["Mons Mouton"]),
    ("Mons Mouton", ["Mons Mouton"]),
    ("Nobile Rim 1", ["Nobile"]),
    ("Nobile Rim 2", ["Nobile"]),
    ("de Gerlache Rim 2", ["de Gerlache"]),
    ("Slater Plain", ["Slater"]),
]
ARTEMIS_SRC = "https://www.nasa.gov/news-release/nasa-provides-update-on-artemis-iii-moon-landing-regions/"

build = {"built": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z", "failed": {}}


def fetch(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(10 * (i + 1))


def need_pyshp():
    try:
        import shapefile  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pyshp"], check=True)


def plain(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace").strip()
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, str):
        return v.strip()
    return v


def lon180(x):
    x = float(x)
    return x - 360 if x > 180 else x


def write(name, fc):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(fc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def shp_points(blob):
    """Every record of the first shapefile in a zip, as GeoJSON points, all fields kept."""
    need_pyshp()
    import shapefile
    z = zipfile.ZipFile(io.BytesIO(blob))
    stem = next(n[:-4] for n in z.namelist() if n.lower().endswith(".shp"))
    get = lambda ext: io.BytesIO(z.read(next(n for n in z.namelist() if n.lower() == (stem + ext).lower())))
    r = shapefile.Reader(shp=get(".shp"), dbf=get(".dbf"), shx=get(".shx"))
    names = [f[0] for f in r.fields[1:]]
    feats = []
    for sr in r.iterShapeRecords():
        props = {k: plain(v) for k, v in zip(names, sr.record)}
        pts = sr.shape.points
        geom = None
        if pts:
            x, y = pts[0][0], pts[0][1]
            geom = {"type": "Point", "coordinates": [round(lon180(x), 6), round(float(y), 6)]}
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    return feats, names, stem


def lroc():
    blob = fetch(LROC)
    (RAW / "ANTHROPOGENIC_OBJECTS_180.ZIP").write_bytes(blob)
    feats, names, stem = shp_points(blob)
    # The shapefile's own LATITUDE / LONGITUDE fields are the source's figures;
    # where the geometry is missing they place the row.
    for f in feats:
        p = f["properties"]
        if f["geometry"] is None and p.get("LATITUDE") not in (None, "") and p.get("LONGITUDE") not in (None, ""):
            f["geometry"] = {"type": "Point", "coordinates": [lon180(p["LONGITUDE"]), float(p["LATITUDE"])]}
    write("moon_objects.geojson", {"type": "FeatureCollection", "features": feats,
          "source": "LROC, Coordinates of anthropogenic features on the Moon (PDS, " + LROC + ")",
          "credit": "NASA/GSFC/Arizona State University; Wagner et al. 2017, Icarus 283:92-103"})
    build["moon_objects"] = {"rows": len(feats), "fields": names, "file in zip": stem,
                             "unplaced": sum(1 for f in feats if f["geometry"] is None)}


VOID = {"br", "img", "hr", "wbr", "input", "meta", "link", "col", "source"}


class Tables(HTMLParser):
    """Every wikitable on a page: header cells and body cells, with
    rowspan/colspan filled in, each cell's text and its {{coord}} if any."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack = [], []
        self.cell = None
        self.tags = []          # inside the cell: (tag, is_geo, is_hidden)
        self.caption = None

    def _geo(self):
        return any(g for _, g, _ in self.tags)

    def _hidden(self):
        return any(h for _, _, h in self.tags)

    def handle_starttag(self, tag, a):
        a = dict(a)
        cls = (a.get("class") or "").split()
        if tag == "table":
            self.stack.append({"wiki": "wikitable" in cls, "rows": [], "caption": ""})
            return
        if not self.stack:
            return
        t = self.stack[-1]
        if tag == "caption":
            self.caption = []
        if tag == "tr":
            t["rows"].append([])
            return
        if tag in ("td", "th"):
            if not t["rows"]:
                t["rows"].append([])
            num = lambda v: int(re.sub(r"\D", "", v or "1") or 1)
            self.cell = {"th": tag == "th", "text": [], "geo": [], "rs": num(a.get("rowspan")), "cs": num(a.get("colspan"))}
            self.tags = []
            return
        if self.cell is None:
            return
        if tag == "br":
            self.cell["text"].append(" ")
        if tag in VOID:
            return
        hidden = tag in ("style", "sup", "script") or "display:none" in (a.get("style") or "").replace(" ", "")
        self.tags.append((tag, "geo" in cls, hidden))

    def handle_endtag(self, tag):
        if not self.stack:
            return
        if tag == "caption" and self.caption is not None:
            self.stack[-1]["caption"] = " ".join("".join(self.caption).split())
            self.caption = None
            return
        if tag in ("td", "th") and self.cell is not None:
            c = self.cell
            self.stack[-1]["rows"][-1].append({"th": c["th"], "text": " ".join("".join(c["text"]).replace("\ufeff", "").split()),
                                               "geo": "".join(c["geo"]).strip(), "rs": c["rs"], "cs": c["cs"]})
            self.cell, self.tags = None, []
            return
        if tag == "table":
            t = self.stack.pop()
            if t["wiki"]:
                self.tables.append(t)
            return
        if self.cell is not None and tag not in VOID:
            for i in range(len(self.tags) - 1, -1, -1):
                if self.tags[i][0] == tag:
                    del self.tags[i:]
                    break

    def handle_data(self, d):
        if self.caption is not None:
            self.caption.append(d)
        if self.cell is None:
            return
        if self._geo():
            self.cell["geo"].append(d)
        elif not self._hidden():
            self.cell["text"].append(d)


def grid(rows):
    """Rows with rowspan and colspan spread out, so every row has every column."""
    out, carry = [], {}
    for row in rows:
        line, col, cells = [], 0, list(row)
        while cells or col in carry:
            if col in carry:
                cell, left = carry[col]
                line.append(cell)
                if left > 1:
                    carry[col] = (cell, left - 1)
                else:
                    del carry[col]
                col += 1
                continue
            c = cells.pop(0)
            for _ in range(c["cs"]):
                line.append(c)
                if c["rs"] > 1:
                    carry[col] = (c, c["rs"] - 1)
                col += 1
        out.append(line)
    return out


def geo_pair(s):
    s = s.replace("−", "-").replace(",", ";")
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*;\s*(-?\d+(?:\.\d+)?)", s)
    return (float(m.group(1)), float(m.group(2))) if m else None


def wiki(body):
    title = WIKI[body]
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "parse", "page": title, "prop": "text|revid", "format": "json", "formatversion": "2", "redirects": "1"})
    j = json.loads(fetch(url))
    page = j["parse"]["text"]
    (RAW / f"{body}_list.html").write_text(page, encoding="utf-8")
    p = Tables()
    p.feed(page)
    feats, report = [], []
    for ti, t in enumerate(p.tables):
        g = grid(t["rows"])
        head = None
        for line in g:
            if line and all(c["th"] for c in line):
                # The last full header line names the columns (two-line headers keep both words).
                names = [c["text"] for c in line]
                head = names if head is None else [(a if a == b else f"{a} {b}".strip()) for a, b in zip(head + [""] * (len(names) - len(head)), names)]
                continue
            if head is None or not line:
                continue
            props = {"table": t["caption"] or f"Table {ti + 1}"}
            seen = set()
            for k, c in zip(head, line):
                key = k or "column"
                while key in seen:
                    key += " (2)"
                seen.add(key)
                props[key] = c["text"]
            geom = None
            for c in line:
                pr = geo_pair(c["geo"]) if c["geo"] else None
                if pr:
                    geom = {"type": "Point", "coordinates": [round(lon180(pr[1]), 5), round(pr[0], 5)]}
                    break
            feats.append({"type": "Feature", "properties": props, "geometry": geom})
        report.append({"caption": t["caption"], "columns": head, "rows": sum(1 for f in feats if f["properties"]["table"] == (t["caption"] or f"Table {ti + 1}"))})
    write(f"{body}_list.geojson", {"type": "FeatureCollection", "features": feats,
          "source": "Wikipedia, \"" + title + "\" (revision " + str(j["parse"].get("revid")) + ")",
          "licence": "CC BY-SA 4.0", "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))})
    build[f"{body}_list"] = {"revision": j["parse"].get("revid"), "tables": report, "rows": len(feats),
                             "unplaced": [next((v for k, v in f["properties"].items() if k != "table" and v), "") for f in feats if f["geometry"] is None]}


def names(body):
    blob = fetch(NAMES[body])
    (RAW / f"{body.upper()}_nomenclature_center_pts.zip").write_bytes(blob)
    feats, fields, _ = shp_points(blob)
    write(f"{body}_names.geojson", {"type": "FeatureCollection", "features": feats,
          "source": "USGS Gazetteer of Planetary Nomenclature (IAU WGPSN), " + NAMES[body]})
    build[f"{body}_names"] = {"rows": len(feats), "fields": fields}
    return feats


def artemis(moon_names):
    def nm(p):
        for k in ("clean_name", "name", "NAME", "Name", "CLEAN_NAME"):
            if p.get(k):
                return str(p[k])
        return ""
    def norm(s):
        return re.sub(r"\s+", " ", s.replace("’", "'")).strip().lower()
    index = {}
    for f in moon_names:
        index.setdefault(norm(nm(f["properties"])), f)
    feats, missing = [], []
    for region, tries in ARTEMIS:
        hit = next(((t, index[norm(t)]) for t in tries if norm(t) in index), None)
        props = {"region": region, "named by": "NASA, 28 October 2024", "source": ARTEMIS_SRC}
        if not hit:
            missing.append(region)
            feats.append({"type": "Feature", "properties": props, "geometry": None})
            continue
        t, f = hit
        props["placed at"] = f"the IAU centre of {t}, the feature the region is named after"
        props["feature"] = {k: v for k, v in f["properties"].items()}
        props["note"] = ("NASA has published these regions only as a picture, with no outlines or coordinates. "
                         "This mark is the centre of the named feature, not the region; a region named for a rim "
                         "or a plateau lies at its edge, not at this point.")
        feats.append({"type": "Feature", "properties": props, "geometry": f["geometry"]})
    write("artemis3.geojson", {"type": "FeatureCollection", "features": feats, "source": ARTEMIS_SRC})
    build["artemis3"] = {"regions": len(feats), "not found in the names": missing}


def rovers():
    got = {}
    for rel in ROVERS:
        try:
            blob = fetch(ROVER_BASE + rel)
            json.loads(blob)
            p = OUT / "rovers" / rel.split("/")[-1]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(blob)
            got[rel] = len(json.loads(blob).get("features", []))
        except Exception as e:
            got[rel] = "failed: " + str(e)[:200]
    build["rovers"] = got


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    moon_names = []
    for name, fn in [("moon_objects", lroc), ("moon_list", lambda: wiki("moon")), ("mars_list", lambda: wiki("mars")),
                     ("moon_names", lambda: moon_names.extend(names("moon"))), ("mars_names", lambda: names("mars")),
                     ("artemis3", lambda: artemis(moon_names)), ("rovers", rovers)]:
        try:
            fn()
        except Exception as e:
            build["failed"][name] = f"{type(e).__name__}: {str(e)[:300]}"
            print(f"bodies: {name} failed: {e}")
    (OUT / "build.json").write_text(json.dumps(build, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: (v if k == "failed" else "ok") for k, v in build.items()}, indent=1))


if __name__ == "__main__":
    main()
