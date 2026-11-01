"""The anti-slavery map's ports, ocean squares, Brazil's register of employers
and its forced-labour determinations, with the figures in their text as fields.

Written 30 September (round 117b). The owner asked for these rows to be
coloured by their figures: the ports by impact or exposure, the ocean squares by
impact or status, the employers by the workers found. In the anti-slavery map's
files most of those figures are inside each record's paragraph ("desc"), not
fields of their own, so the map could not colour by them. Here each paragraph
is read and the figures it states become fields; the paragraph and every other
field are kept as they are. Nothing is estimated: a figure the text does not
give is left out, and tiles/slavery_points.build.json counts, per figure, how
many records gave it.

What the anti-slavery map's own scales are (from its harvest scripts):
  ports    impact and exposure are the same for every port (4 and 1): each port
           is there because its country's share of fishing-vessel calls by
           vessels the published model scored high-risk (McDonald et al., PNAS
           2021) is recorded; exposure counts how many selectors flag it, and
           only that one does. The share itself is a country figure, written in
           each port's text; it is kept as high_risk_share_pct.
  ocean    impact 5 = the square's at-risk fishing effort is in the top 1% of
           squares, 4 = the top 10% (harvest_vessels.py); "status" is the
           share of all fishing effort in the square by vessels scored
           high-risk.
  Brazil   impact 5 = 30 or more workers, 4 = 10 to 29, 3 = 2 to 9, 2 = one
           (harvest_bulk.py).

Writes tiles/slavery_points_<ports|fishing|enforcement|determinations>.pmtiles
(each archive's layer named for its row on the map) and
tiles/slavery_points.build.json.
"""
import json, pathlib, re, shutil, sys, tempfile, time, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mines   # noqa: E402  (tippecanoe, as the other scripts get it)

BASE = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/anti-slavery-map/main/"
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
OUT = pathlib.Path("tiles")
STAMP = OUT / "slavery_points.build.json"


def get(name):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(5 * (i + 1))
    raise SystemExit(f"{name}: {last}")


def num(s):
    return float(s.replace(",", "")) if s is not None else None


def found(pattern, text, group=1):
    m = re.search(pattern, text or "")
    return m.group(group).strip() if m else None


def port_fields(r):
    d = r.get("desc") or ""
    out = {}
    share = found(r"(\d+(?:\.\d+)?) \(country-level", d)
    if share is not None:
        out["high_risk_share_pct"] = float(share)
        out["high_risk_share_is"] = ("the share of fishing-vessel calls at this country's ports made by vessels the published "
                                     "model scored high-risk (McDonald et al., PNAS 2021); a country figure, the same for every port in it")
    size = found(r", (very small|small|medium|large|unclassified) harbour", d)
    if size:
        out["harbour_size"] = size
    out["port_of_entry"] = ("yes: customs and immigration present" if "Recorded as a port of entry" in d
                            else "no: no customs or immigration post" if "Not recorded as a port of entry" in d else "not stated")
    if "No medical facilities" in d:
        out["medical_facilities"] = "none"
    return out


RANK = {5: "top 1% of ocean squares by at-risk fishing effort", 4: "top 10% of ocean squares by at-risk fishing effort",
        3: "below the top 10%"}


def fishing_fields(r):
    d = r.get("desc") or ""
    out = {"precision": "grid", "grid_cell": "2.5 degrees"}
    kwh = found(r"attributes ([\d,]+) kW-hours", d)
    if kwh:
        out["at_risk_effort_kw_hours"] = num(kwh)
    share = found(r"([\d.]+)% of all effort recorded in this cell", d)
    if share:
        out["share_of_effort_high_risk_pct"] = float(share)
        out["share_of_effort_is"] = ("of all the fishing effort recorded in this square, the share by vessels the model "
                                     "scored high-risk for forced labour (what the source calls this square's status)")
    gear = found(r"Gear: ([^.]+)\.", d)
    if gear:
        out["gear"] = gear.replace(",", ", ")
    if r.get("impact") in RANK:
        out["rank"] = RANK[r["impact"]]
    return out


def enforcement_fields(r):
    d = r.get("desc") or ""
    out = {}
    w = found(r"(\d[\d.,]*) workers? involved", d)
    if w:
        out["workers"] = int(w.replace(".", "").replace(",", ""))
    y = found(r"in the (\d{4}) inspection year", d)
    if y:
        out["inspection_year"] = int(y)
    a = found(r"Added to the register (\d\d/\d\d/\d{4})", d)
    if a:
        out["added_to_register"] = a
        out["year_added"] = int(a[-4:])
    e = found(r"Establishment: (.*?)\. Economic activity", d)
    if e:
        out["establishment"] = e
    c = found(r"Economic activity code ([\d/-]+)", d)
    if c:
        out["activity_code"] = c
    return out


FILES = [
    ("ports", "slavery_ports", "infra.json", port_fields, "World Port Index; McDonald et al., PNAS 2021 (via the anti-slavery map)"),
    ("fishing", "slavery_fishing", "vessels.json", fishing_fields, "emlab-ucsb slavery-in-fisheries (via the anti-slavery map)"),
    ("enforcement", "slavery_enforcement", "bulk.json", enforcement_fields, "Brazil, Cadastro de Empregadores (via the anti-slavery map)"),
    ("determinations", "slavery_determinations", "projects.json", lambda r: {}, "US CBP, US DOL, ILO and others (via the anti-slavery map)"),
]


def main():
    mines.tools()
    stamp = {"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "rows": {}}
    for short, row, name, extra, attribution in FILES:
        rows = get(name).get("projects") or []
        feats, counts, placed = [], {}, 0
        for i, r in enumerate(rows):
            if r.get("lat") is None or r.get("lng") is None:
                continue
            placed += 1
            props = {"id": f"{name}#{i}", "name": r.get("name") or r.get("type"), "_count": 1}
            if r.get("url"):
                props["url"] = r["url"]
            for k, v in r.items():
                if k in ("lat", "lng", "name", "url") or v is None or v == "":
                    continue
                props[f"x_{k}"] = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
            if r.get("precise") is False and short != "fishing":
                props["x_precision"] = "admin"
            for k, v in extra(r).items():
                props[f"x_{k}"] = v
                counts[k] = counts.get(k, 0) + 1
            props["x_from_file"] = f"https://github.com/WelcomeToYourGalaxy/anti-slavery-map/blob/main/{name}"
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(r["lng"]), float(r["lat"])]},
                          "properties": props})
        # Every record at every zoom; its long paragraph only from zoom 8 in
        # (with it, the ports alone came to 22 MB), so a box opened wider out
        # shows the fields and says to zoom in for the text.
        work = pathlib.Path(tempfile.mkdtemp())
        near, far = work / "near.geojsonl", work / "far.geojsonl"
        with near.open("w") as f, far.open("w") as g:
            for ft in feats:
                f.write(json.dumps(ft, ensure_ascii=False) + "\n")
                p = {k: v for k, v in ft["properties"].items() if k != "x_desc"}
                if "x_desc" in ft["properties"]:
                    p["x_full_text"] = "zoom in closer (zoom 8) to read the record's own paragraph"
                g.write(json.dumps(dict(ft, properties=p), ensure_ascii=False) + "\n")
        parts = []
        for src, lo, hi in ((far, 0, 7), (near, 8, 8)):
            o = work / f"z{lo}.pmtiles"
            mines.sh("tippecanoe", "-o", str(o), "--force", "-q", "-l", row, "--name", row, f"-Z{lo}", f"-z{hi}", "-r1",
                     "--no-feature-limit", "--no-tile-size-limit", "--attribution", attribution, str(src))
            parts.append(str(o))
        tmp = work / "out.pmtiles"
        mines.sh("tile-join", "-o", str(tmp), "--force", "-q", "--no-tile-size-limit", "--attribution", attribution, *parts)
        OUT.mkdir(exist_ok=True)
        shutil.move(str(tmp), OUT / f"slavery_points_{short}.pmtiles")
        stamp["rows"][row] = {"file": f"slavery_points_{short}.pmtiles", "records": len(rows), "placed": placed,
                              "figures_read": counts}
        print(f"  {row}: {placed:,} of {len(rows):,} placed; figures read: {counts}")
    STAMP.write_text(json.dumps(stamp, indent=1))


if __name__ == "__main__":
    main()
