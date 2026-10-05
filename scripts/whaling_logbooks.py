#!/usr/bin/env python3
"""
Whaling logbooks: where whaling ships were day by day and where they saw,
struck and processed whales, 1784 to 1920 (round 183o).

The consolidated American Offshore Whaling Logbook data (AOWL) of
WhalingHistory.org (New Bedford Whaling Museum, Mystic Seaport Museum and the
Nantucket Historical Association), CC BY 4.0: entries transcribed from about
1,400 logbooks by Maury (1850s), Townsend (1930s) and the Census of Marine
Life (2000 to 2010), with later additions for British Southern Whale Fishery
voyages and Indian Ocean southern right whale voyages. Each entry is joined by
its voyage number to the American Offshore Whaling Voyages database (same
publishers, CC BY 4.0): the vessel, master, home port, dates and what the
voyage brought back.

Every column of both files is kept as the source writes it; the voyage's
columns are prefixed "Voyage: ". Every entry with a position is drawn;
entries without one cannot be placed and are counted in
whaling/build.json, not dropped silently. Colours follow the source's own
Encounter column.

  tiles/whaling_logbooks.pmtiles (and parts)  layer "whaling"
  tiles/whaling_logbooks.build.json           parts, counts
  whaling/build.json                          files read, columns, counts
"""
import csv, datetime, io, json, os, pathlib, re, sys, tempfile, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

LOGS = "https://whalinghistory.org/aowl/AmericanOffshoreWhalingLogbookData.zip"
VOYAGES = "https://whalinghistory.org/aowv/AmericanOffshoreWhalingVoyages.zip"
OUT = pathlib.Path("whaling")
TILE = pathlib.Path("tiles") / "whaling_logbooks.pmtiles"
CITE = ("WhalingHistory.org: American Offshore Whaling Logbook Data and Voyages, New Bedford Whaling Museum, "
        "Mystic Seaport Museum, Nantucket Historical Association (CC BY 4.0)")
# The source's Encounter values, as its column definitions explain them.
ENCOUNTER = {"strike": "Whales struck (harpooned)", "sight": "Whales seen",
             "spoke": "Spoke to a whaler that had caught a whale", "noenc": "No whales reported that day"}
csv.field_size_limit(1 << 30)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def tables(path):
    """Every data table in a zip: (name, header, rows). Readme and other text are skipped by having no columns."""
    out = []
    with zipfile.ZipFile(path) as z:
        for i in z.infolist():
            if i.is_dir() or not re.search(r"\.(txt|csv|tsv|tab)$", i.filename, re.I) or re.search(r"read ?me", i.filename, re.I):
                continue
            raw = z.read(i)
            text = None
            for enc in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            first = text.split("\n", 1)[0]
            delim = max(("\t", ",", "|", ";"), key=first.count)
            if first.count(delim) < 2:
                continue
            rd = csv.reader(io.StringIO(text), delimiter=delim)
            header = [h.strip() for h in next(rd)]
            rows = [r for r in rd if any(c.strip() for c in r)]
            out.append((i.filename, header, rows))
    return out


def col(header, *names):
    n = [norm(h) for h in header]
    for want in names:
        if norm(want) in n:
            return n.index(norm(want))
    return None


def number(s):
    try:
        v = float(str(s).strip())
        return v if v == v else None
    except ValueError:
        return None


def main():
    stamp_f = OUT / "build.json"
    if stamp_f.exists() and TILE.exists() and datetime.date.today().weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("whaling_logbooks: weekly; not Sunday")
        return
    pyramid.need()
    OUT.mkdir(exist_ok=True)
    tmp = pathlib.Path(tempfile.mkdtemp())
    info = {"built": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "sources": [LOGS, VOYAGES], "licence": "CC BY 4.0"}
    logs = tables(pyramid.download(LOGS, tmp / "logs.zip", "whaling_logbooks"))
    info["log_files"] = [{"file": n, "columns": h, "rows": len(r)} for n, h, r in logs]
    voy = {}
    try:
        vt = tables(pyramid.download(VOYAGES, tmp / "voyages.zip", "whaling_logbooks"))
        info["voyage_files"] = [{"file": n, "columns": h, "rows": len(r)} for n, h, r in vt]
        main_t = [t for t in vt if col(t[1], "voyageID", "voyage_id") is not None]
        for name, header, rows in main_t:
            k = col(header, "voyageID", "voyage_id")
            for r in rows:
                vid = r[k].strip() if k < len(r) else ""
                if not vid:
                    continue
                d = voy.setdefault(vid, {})
                for h, v in zip(header, r):
                    v = v.strip()
                    if not v or norm(h) in ("voyageid",):
                        continue
                    key = f"Voyage: {h}"
                    if key not in d:
                        d[key] = v
                    elif v not in str(d[key]).split(" / "):
                        d[key] = f"{d[key]} / {v}"
        info["voyages_read"] = len(voy)
    except Exception as e:  # noqa: BLE001
        info["voyages"] = f"not read: {type(e).__name__}: {e}"
        print(f"::warning::whaling_logbooks: voyages not read: {e}")
    pts, unplaced, by, unmatched = [], 0, {}, set()
    for name, header, rows in logs:
        ilat, ilon = col(header, "Lat", "Latitude"), col(header, "Lon", "Long", "Longitude")
        ivid = col(header, "VoyageID", "Voyage ID", "voyage_id")
        ienc = col(header, "Encounter")
        if ilat is None or ilon is None:
            info.setdefault("not_logbook_tables", []).append(name)
            continue
        for r in rows:
            lat = number(r[ilat]) if ilat < len(r) else None
            lon = number(r[ilon]) if ilon < len(r) else None
            if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 360):
                unplaced += 1
                continue
            if lon > 180:
                lon -= 360
            p = {h: v.strip() for h, v in zip(header, r) if v.strip()}
            raw = r[ienc].strip() if ienc is not None and ienc < len(r) else ""
            p["group"] = ENCOUNTER.get(norm(raw), raw or "Encounter not given")
            vid = r[ivid].strip() if ivid is not None and ivid < len(r) else ""
            if vid:
                if vid in voy:
                    p.update(voy[vid])
                else:
                    unmatched.add(vid)
            by[p["group"]] = by.get(p["group"], 0) + 1
            pts.append((round(lon, 5), round(lat, 5), p))
    info.update(entries_drawn=len(pts), entries_without_position=unplaced, by_encounter=by,
                voyages_in_logs_not_in_voyage_file=len(unmatched), examples_not_matched=sorted(unmatched)[:20])
    if not pts:
        stamp_f.write_text(json.dumps(info, indent=1, ensure_ascii=False))
        sys.exit("whaling_logbooks: no entries with a position were read; see whaling/build.json")
    import pointtiles
    parts = pointtiles.build(pts, TILE, "whaling", "group", attribution=CITE)
    TILE.with_suffix(".build.json").write_text(json.dumps({"layer": "whaling", "places": len(pts), "detail_from": 8, "groups": by,
                                                           "parts": parts, "date": datetime.date.today().isoformat()}, indent=1))
    stamp_f.write_text(json.dumps(info, indent=1, ensure_ascii=False))
    print(f"whaling_logbooks: {len(pts):,} entries drawn, {unplaced:,} without a position, {len(voy):,} voyages joined", flush=True)


if __name__ == "__main__":
    main()
