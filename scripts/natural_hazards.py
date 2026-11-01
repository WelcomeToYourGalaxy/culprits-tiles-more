#!/usr/bin/env python3
"""
Natural disasters worldwide for the Culprits map (round 94b, asked 27
September: the Natural disasters heading held only SkyTruth's earthquakes, 2011
to 2015; the owner asked for the rest of natural disasters, as one map of every
kind, as a layer for each kind, or both).

Each part is copied from its publisher and written for the map; one that fails
leaves its earlier copy in place and says why in the log.

  hazards/eonet.geojson        NASA EONET v3, every event open or closed, all
                               categories (wildfires, severe storms, volcanoes,
                               floods, landslides, drought, dust and haze, sea
                               and lake ice, snow, temperature extremes, water
                               colour, earthquakes): the newest point of each
                               event, "group" = its category, its date and
                               magnitude as given. https://eonet.gsfc.nasa.gov/docs/v3
  hazards/gdacs.geojson        GDACS (UN and European Commission) alerts since
                               2000: earthquakes, tropical cyclones, floods,
                               volcanoes, droughts, wildfires, month by month,
                               "group" = the kind, with its alert level.
  hazards/volcanoes.geojson    Smithsonian Global Volcanism Program, Volcanoes of
                               the World: every Holocene volcano (WFS GeoJSON).
  hazards/ncei_tsunamis.geojson, ncei_earthquakes.geojson, ncei_eruptions.geojson
                               NOAA NCEI's Natural Hazards database: tsunami
                               events, significant earthquakes and significant
                               volcanic eruptions, 2100 BC to now, with deaths and
                               damage where recorded (hazard-service API).
  hazards/landslides.geojson   NASA's Global Landslide Catalog (the landslide
                               reporter service, 2,500 records a request).
  tiles/usgs_quakes.pmtiles    USGS earthquake catalogue, magnitude 5 and over,
                               1900 to now, every one at every zoom (layer
                               usgs_quakes: id, x_date, mag, place, depth).
  tiles/ibtracs.pmtiles        IBTrACS v04r01 tropical cyclone tracks since 1980
                               (NOAA NCEI), lines by segment with storm name,
                               season and Saffir-Simpson category.
  hazards/build.json           what each part read

Weekly (Sundays), or by hand.
"""
import datetime, io, json, os, pathlib, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request, zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
OUT = pathlib.Path("hazards")
TILES = pathlib.Path("tiles")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
TODAY = datetime.date.today()


def get(url, timeout=180, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {url[:90]} ({e})", flush=True)
            time.sleep(5 * (i + 1))


def getj(url, **kw):
    return json.loads(get(url, **kw))


# Round 123b (asked 2 October: GDACS's colours "are just colours; improve
# names"): each alert level said in words, as GDACS defines it. The code is
# kept as alert_code.
GDACS_ALERT = {"GREEN": "Green: minor impact, outside help unlikely to be needed",
               "ORANGE": "Orange: moderate impact, outside help may be needed",
               "RED": "Red: severe impact, outside help likely to be needed"}


def write(name, feats, meta, stamp):
    OUT.mkdir(exist_ok=True)
    if name == "gdacs.geojson":
        for f in feats:
            p = f["properties"]
            code = str(p.get("alert_code") or p.get("alert") or "").upper()
            if code in GDACS_ALERT:
                p["alert_code"] = code
                p["alert"] = GDACS_ALERT[code]
    (OUT / name).write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False, separators=(",", ":")))
    stamp[name] = dict(meta, features=len(feats), bytes=(OUT / name).stat().st_size, read=TODAY.isoformat())
    print(f"natural_hazards: {name}: {len(feats):,} features", flush=True)


def pt(lon, lat):
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return None
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return {"type": "Point", "coordinates": [lon, lat]}


def eonet(stamp):
    # Round 123b: one call for every event timed out (28 September); now one
    # year at a time, so one slow year costs only itself.
    feats, seen, bad = [], set(), []
    for year in range(2000, TODAY.year + 1):
        url = f"https://eonet.gsfc.nasa.gov/api/v3/events?status=all&start={year}-01-01&end={year}-12-31"
        try:
            j = getj(url, timeout=300)
        except Exception as e:  # noqa: BLE001
            bad.append(f"{year}: {e}")
            continue
        for ev in j.get("events", []):
            if ev.get("id") in seen:
                continue
            seen.add(ev.get("id"))
            geo = [g for g in ev.get("geometry", []) if g.get("type") == "Point"]
            if not geo:
                continue
            last = max(geo, key=lambda g: g.get("date", ""))
            cats = ", ".join(c.get("title", "") for c in ev.get("categories", []))
            feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": last["coordinates"]},
                          "properties": {"name": ev.get("title"), "group": cats or "Not named", "date": (last.get("date") or "")[:10],
                                         "first_seen": (min(g.get("date", "") for g in geo) or "")[:10],
                                         "magnitude": last.get("magnitudeValue"), "magnitude_unit": last.get("magnitudeUnit"),
                                         "closed": (ev.get("closed") or "")[:10], "positions_recorded": len(geo),
                                         "sources": ", ".join(s.get("id", "") for s in ev.get("sources", [])), "link": ev.get("link")}})
    if not feats:
        raise RuntimeError("no EONET events read: " + "; ".join(bad[:3]))
    write("eonet.geojson", feats, {"from": "https://eonet.gsfc.nasa.gov/api/v3/events?status=all (year by year)", "years_not_read": bad}, stamp)


GDACS_KIND = {"EQ": "Earthquake", "TC": "Tropical cyclone", "FL": "Flood", "VO": "Volcano", "DR": "Drought", "WF": "Wildfire"}


def gdacs(stamp):
    old = {}
    p = OUT / "gdacs.geojson"
    if p.exists():
        for f in json.loads(p.read_text()).get("features", []):
            old[f["properties"]["key"]] = f
    start = datetime.date(2000, 1, 1) if not old else TODAY - datetime.timedelta(days=120)
    d = start
    while d <= TODAY:
        e = min(TODAY, d + datetime.timedelta(days=9))
        url = ("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?eventlist=EQ;TC;FL;VO;DR;WF"
               f"&fromDate={d.isoformat()}&toDate={e.isoformat()}&alertlevel=green;orange;red")
        try:
            j = getj(url, timeout=120)
        except Exception as ex:  # noqa: BLE001
            print(f"  gdacs {d}: {ex}", flush=True)
            j = {}
        for f in (j or {}).get("features", []):
            pr = f.get("properties", {})
            key = f"{pr.get('eventtype')}-{pr.get('eventid')}"
            sev = pr.get("severitydata") or {}
            old[key] = {"type": "Feature", "geometry": f.get("geometry"), "properties": {
                "key": key, "name": pr.get("name") or pr.get("eventname") or pr.get("description"), "group": GDACS_KIND.get(pr.get("eventtype"), pr.get("eventtype")),
                "alert": pr.get("alertlevel"), "date": (pr.get("fromdate") or "")[:10], "to": (pr.get("todate") or "")[:10],
                "severity": sev.get("severitytext"), "country": pr.get("country"), "source": pr.get("source"),
                "link": (pr.get("url") or {}).get("report") if isinstance(pr.get("url"), dict) else None}}
        d = e + datetime.timedelta(days=1)
        time.sleep(0.3)
    feats = [f for f in old.values() if f.get("geometry") and f["geometry"].get("type") == "Point"]
    write("gdacs.geojson", feats, {"from": "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"}, stamp)


GVP_WFS = "https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows"


def volcanoes(stamp):
    # Round 123b: the layer name of 94b was refused (28 September). The names
    # the service offers are read from its own list, Holocene ones first.
    names = ["GVP-VOTW:Smithsonian_VOTW_Holocene_Volcanoes", "GVP-VOTW:E3WebApp_HoloceneVolcanoes"]
    try:
        cap = get(GVP_WFS + "?service=WFS&version=1.0.0&request=GetCapabilities", timeout=120).decode("utf-8", "replace")
        offered = re.findall(r"<Name>([^<]*Holocene[^<]*)</Name>", cap)
        names = [n for n in offered if "Eruption" not in n] + [n for n in names if n not in offered]
    except Exception as e:  # noqa: BLE001
        print(f"  volcanoes: no capabilities list ({e})", flush=True)
    errs = []
    for name in names:
        url = GVP_WFS + "?service=WFS&version=1.0.0&request=GetFeature&outputFormat=application%2Fjson&typeName=" + urllib.parse.quote(name)
        try:
            j = getj(url, timeout=300)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{name}: {e}")
            continue
        feats = []
        for f in j.get("features", []):
            p = dict(f.get("properties") or {})
            p["group"] = p.get("Primary_Volcano_Type") or p.get("Volcano_Type") or p.get("PrimaryVolcanoType") or "Volcano"
            if f.get("geometry"):
                feats.append({"type": "Feature", "geometry": f.get("geometry"), "properties": p})
        if feats:
            write("volcanoes.geojson", feats, {"from": url, "cite": "Global Volcanism Program, Volcanoes of the World"}, stamp)
            return
        errs.append(f"{name}: no features")
    raise RuntimeError("; ".join(errs))


def ncei(stamp, path, name, group):
    feats, page, pages = [], 1, 1
    while page <= pages:
        j = getj(f"https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/{path}?page={page}", timeout=180)
        pages = int(j.get("totalPages") or 1)
        for r in j.get("items", []):
            g = pt(r.get("longitude"), r.get("latitude"))
            if not g:
                continue
            y, m, dd = r.get("year"), r.get("month"), r.get("day")
            date = (f"{int(y):04d}" if isinstance(y, int) and y >= 0 else str(y)) + (f"-{int(m):02d}" if m else "") + (f"-{int(dd):02d}" if dd else "")
            p = {k: v for k, v in r.items() if v not in (None, "")}
            p["date"] = date
            p["group"] = group(r)
            p["name"] = r.get("locationName") or r.get("name") or date
            feats.append({"type": "Feature", "geometry": g, "properties": p})
        page += 1
    write(name, feats, {"from": f"https://www.ngdc.noaa.gov/hazel/hazard-service/api/v1/{path}"}, stamp)


LANDSLIDE_SERVICES = [
    "https://maps.nccs.nasa.gov/server/rest/services/global_landslide_catalog/glc_viewer_service/FeatureServer",
    "https://maps.nccs.nasa.gov/server/rest/services/global_landslide_catalog/landslide_reporter_service/FeatureServer",
]
LANDSLIDE_CSV = "https://data.nasa.gov/docs/legacy/Global_Landslide_Catalog_Export/Global_Landslide_Catalog_Export_rows.csv"


def _landslide_props(p):
    for k in ("event_date", "Event Date"):
        ed = p.get(k)
        if isinstance(ed, (int, float)):
            p[k] = datetime.datetime.utcfromtimestamp(ed / 1000).date().isoformat()
    p["date"] = p.get("event_date") or p.get("Event Date")
    p["group"] = p.get("landslide_trigger") or p.get("trigger") or "trigger not recorded"
    p["name"] = p.get("event_title") or p.get("location_description") or p.get("event_description")
    return p


def landslides(stamp):
    # Round 123b: the 94b service path failed (28 September). Each NASA
    # service is tried, every layer it lists; then NASA's own export file
    # (current to 2016, said so in build.json).
    errs = []
    for svc in LANDSLIDE_SERVICES:
        try:
            info = getj(svc + "?f=json", timeout=120)
            layers = [l.get("id") for l in info.get("layers", [])] or [0]
        except Exception as e:  # noqa: BLE001
            errs.append(f"{svc}: {e}")
            continue
        for lid in layers:
            base = f"{svc}/{lid}/query"
            feats, off = [], 0
            try:
                while True:
                    q = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "f": "geojson", "resultOffset": off, "resultRecordCount": 2000, "orderByFields": "OBJECTID"})
                    j = getj(f"{base}?{q}", timeout=300)
                    got = j.get("features", [])
                    for f in got:
                        if f.get("geometry"):
                            feats.append({"type": "Feature", "geometry": f["geometry"], "properties": _landslide_props(f.get("properties") or {})})
                    if len(got) < 2000:
                        break
                    off += len(got)
            except Exception as e:  # noqa: BLE001
                errs.append(f"{base}: {e}")
                continue
            if len(feats) > 1000:
                write("landslides.geojson", feats, {"from": base, "tried_first": errs}, stamp)
                return
            errs.append(f"{base}: {len(feats)} features only")
    import csv
    rows = list(csv.DictReader(io.StringIO(get(LANDSLIDE_CSV, timeout=300).decode("utf-8", "replace"))))
    feats = []
    for r in rows:
        g = pt(r.get("longitude"), r.get("latitude"))
        if g:
            feats.append({"type": "Feature", "geometry": g, "properties": _landslide_props({k: v for k, v in r.items() if v not in (None, "")})})
    if not feats:
        raise RuntimeError("; ".join(errs + ["NASA export: no rows with a position"]))
    write("landslides.geojson", feats, {"from": LANDSLIDE_CSV, "note": "NASA's one-time export of the catalogue (to 2016); its live services did not answer",
                                        "tried_first": errs}, stamp)


def usgs(stamp):
    import mines
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    lines = work / "q.geojsonl"
    n = 0
    with lines.open("w") as fo:
        y = 1900
        while y <= TODAY.year:
            span = 10 if y < 1970 else 1
            s, e = f"{y}-01-01", f"{min(y + span, TODAY.year + 1)}-01-01"
            url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime={s}&endtime={e}&minmagnitude=5&orderby=time-asc"
            j = getj(url, timeout=300)
            for f in j.get("features", []):
                p = f.get("properties") or {}
                t = p.get("time")
                date = datetime.datetime.utcfromtimestamp(t / 1000).strftime("%Y-%m-%d") if isinstance(t, (int, float)) else ""
                c = (f.get("geometry") or {}).get("coordinates") or []
                if len(c) < 2:
                    continue
                fo.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": c[:2]}, "properties": {
                    "id": f.get("id"), "x_date": date, "mag": p.get("mag"), "place": p.get("place"),
                    "depth": c[2] if len(c) > 2 else None, "tsunami": p.get("tsunami"), "_count": 1}}) + "\n")
                n += 1
            y += span
            time.sleep(0.5)
    out = TILES / "usgs_quakes.pmtiles"
    mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-Z0", "-z10", "-r1", "-l", "usgs_quakes", "--name", "usgs_quakes",
             "--no-feature-limit", "--no-tile-size-limit", "--preserve-input-order", str(lines))
    stamp["usgs_quakes"] = {"from": "https://earthquake.usgs.gov/fdsnws/event/1/query (minmagnitude=5, 1900 on)", "earthquakes": n,
                            "bytes": out.stat().st_size, "read": TODAY.isoformat()}
    print(f"natural_hazards: usgs_quakes: {n:,}", flush=True)


def ibtracs(stamp):
    import mines
    mines.tools()
    work = pathlib.Path(tempfile.mkdtemp())
    url = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r01/access/shapefile/IBTrACS.since1980.list.v04r01.lines.zip"
    z = work / "l.zip"
    z.write_bytes(get(url, timeout=1800))
    zipfile.ZipFile(z).extractall(work / "l")
    shp = next((work / "l").rglob("*.shp"))
    gj = work / "l.geojsonl"
    mines.sh("ogr2ogr", "-f", "GeoJSONSeq", "-t_srs", "EPSG:4326", "-select", "SID,SEASON,NAME,BASIN,ISO_TIME,USA_SSHS,USA_WIND,WMO_WIND,NATURE",
             str(gj), str(shp))
    out = TILES / "ibtracs.pmtiles"
    for zmax in (8, 7, 6):
        mines.sh("tippecanoe", "-o", str(out), "--force", "-q", "-Z0", f"-z{zmax}", "-l", "ibtracs", "--name", "ibtracs",
                 "--drop-densest-as-needed", "--simplification=4", str(gj))
        if out.stat().st_size < 95 * 1024 * 1024:
            break
    stamp["ibtracs"] = {"from": url, "bytes": out.stat().st_size, "to_zoom": zmax, "read": TODAY.isoformat()}


def main():
    stamp_p = OUT / "build.json"
    stamp = json.loads(stamp_p.read_text()) if stamp_p.exists() else {}
    # Round 123b: a part never built yet is tried every day, not only Sundays.
    missing = [n for n in ("eonet.geojson", "volcanoes.geojson", "landslides.geojson") if not (OUT / n).exists()]
    if stamp and not missing and TODAY.weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" and not os.environ.get("HAZARDS_AGAIN"):
        print("natural_hazards: weekly; not Sunday")
        return
    OUT.mkdir(exist_ok=True)
    jobs = [("eonet", eonet), ("gdacs", gdacs), ("volcanoes", volcanoes),
            ("tsunamis", lambda s: ncei(s, "tsunamis/events", "ncei_tsunamis.geojson", lambda r: "Tsunami")),
            ("earthquakes", lambda s: ncei(s, "earthquakes", "ncei_earthquakes.geojson", lambda r: "Significant earthquake")),
            ("eruptions", lambda s: ncei(s, "volcanoes", "ncei_eruptions.geojson", lambda r: f"VEI {r.get('vei')}" if r.get("vei") is not None else "VEI not recorded")),
            ("landslides", landslides), ("usgs", usgs), ("ibtracs", ibtracs)]
    if missing and stamp and TODAY.weekday() != 6 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" and not os.environ.get("HAZARDS_AGAIN"):
        want = {"eonet.geojson": "eonet", "volcanoes.geojson": "volcanoes", "landslides.geojson": "landslides"}
        names = {want[n] for n in missing}
        jobs = [j for j in jobs if j[0] in names]
    failed = []
    for name, job in jobs:
        try:
            job(stamp)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name}: {type(e).__name__}: {e}")
            print(f"natural_hazards: {name} failed ({e}); its earlier copy stays", flush=True)
        stamp_p.write_text(json.dumps(stamp, indent=1, default=str))
    stamp["failed"] = {f.split(":")[0]: f for f in failed}
    stamp_p.write_text(json.dumps(stamp, indent=1, default=str))
    if failed:
        print("natural_hazards: failed parts: " + "; ".join(failed), flush=True)
    if len(failed) == len(jobs):
        sys.exit(1)


if __name__ == "__main__":
    main()
