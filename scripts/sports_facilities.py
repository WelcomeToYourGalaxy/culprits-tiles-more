#!/usr/bin/env python3
"""
Every sports facility on Earth that the open maps hold (round 114b, asked 29
September: "add to the sports category a global map of sport facilities";
the owner chose everything, as map tiles, every pitch and court included).

Source: Overture Maps Foundation's latest release, read in place on its open
bucket (s3://overturemaps-us-west-2, no account) with DuckDB, two parts:
  places     every place whose category is a sport one: stadiums and arenas,
             sports clubs and centres, gyms, golf, pools, rinks, courts,
             race tracks ... (Overture places; CDLA Permissive 2.0, with
             OpenStreetMap parts under ODbL);
  grounds    every land-use shape whose class is a sport one: pitches,
             tracks, stadiums, sports centres, golf courses, ice rinks ...
             each as its middle point (Overture base theme, from
             OpenStreetMap, ODbL).
Which categories and classes count as sport is decided by their own names
(SPORT below) and every one taken, with how many places, is written to
sports/build.json, as is every one left out that came close, so it can be
checked. Each place is put in one of a few groups for its colour (GROUPS).

  tiles/sports_facilities.pmtiles (and _z*.pmtiles parts)   layer "sports"
  tiles/sports_facilities.build.json   parts, counts, release
  sports/build.json                    categories and classes, taken and not

Monthly (the first Monday) or by hand; SPORTS_AGAIN=1 builds again.
"""
import datetime, json, os, pathlib, re, subprocess, sys, time, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))

OUT = pathlib.Path("tiles/sports_facilities.pmtiles")
STAMP = OUT.with_suffix(".build.json")
INFO = pathlib.Path("sports/build.json")
BUCKET = "https://overturemaps-us-west-2.s3.us-west-2.amazonaws.com/"
SPORT = re.compile(r"sport|stadium|arena|athlet|golf|tennis|soccer|football|basketball|baseball|softball|cricket|rugby|hockey|"
                   r"rink|skat|\bski|ski_|snowboard|swim|pool|race_?track|racecourse|raceway|velodrome|bowling|gym|fitness|"
                   r"martial|boxing|climb|equestrian|horse_riding|riding|polo|pitch|court|track|squash|badminton|volleyball|"
                   r"surf|diving|rowing|sailing|shooting|archery|fencing|wrestling|judo|karate|taekwondo|yoga|pilates|"
                   r"cycling|bmx|motocross|karting|go_kart|paintball|handball|netball|lacrosse|curling|table_tennis|padel|"
                   r"pickleball|disc_golf|skate|field_house|playing_field|recreation_ground", re.I)
NOT = re.compile(r"shop|store|retail|goods|apparel|wear|clothing|equipment|supplies|bar\b|_bar|pub|restaurant|cafe|"
                 r"school|coach|instructor|agent|agency|photograph|medicine|therap|physio|massage|news|radio|"
                 r"tv|broadcast|magazine|betting|bookmaker|casino|lottery|ticket|repair|rental|tailor|car_pool|carpool|"
                 r"swimming_pool_(contractor|supply|service)|pool_(hall|supply|service|cleaning)|court(house|_house)|"
                 r"law|legal|judicial|government", re.I)
GROUPS = [("stadiums and arenas", r"stadium|arena|field_house|velodrome"),
          ("pitches and fields", r"pitch|field|soccer|football|rugby|cricket|baseball|softball|hockey|lacrosse|recreation_ground"),
          ("courts", r"court|tennis|basketball|volleyball|squash|badminton|padel|pickleball|netball|handball|table_tennis"),
          ("tracks and racecourses", r"track|race|raceway|racecourse|karting|kart|motocross|bmx|cycling|equestrian|riding|polo"),
          ("golf", r"golf"),
          ("pools and water", r"swim|pool|surf|diving|rowing|sailing"),
          ("rinks and snow", r"rink|skat|ski|snow|curling"),
          ("gyms and sports centres", r"gym|fitness|sports_cent|sport_cent|leisure_cent|recreation_cent|club|martial|boxing|yoga|pilates|climb|judo|karate|taekwondo|wrestling|fencing")]


def group_of(k):
    for g, rx in GROUPS:
        if re.search(rx, k, re.I):
            return g
    return "other sports places"


def latest_release():
    body = urllib.request.urlopen(urllib.request.Request(BUCKET + "?list-type=2&prefix=release/&delimiter=/",
                                                         headers={"User-Agent": "Culprits atlas build"}), timeout=60).read().decode()
    rel = sorted(re.findall(r"<Prefix>release/([^/<]+)/</Prefix>", body))
    if not rel:
        raise SystemExit("sports_facilities: no Overture release listed")
    return rel[-1]


def main():
    today = datetime.date.today()
    if STAMP.exists() and not os.environ.get("SPORTS_AGAIN") and not (today.weekday() == 0 and today.day <= 7) \
            and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("sports_facilities: monthly; not the first Monday")
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "duckdb"], check=True)
    import duckdb
    import pointtiles
    t0 = time.time()
    rel = latest_release()
    print(f"sports_facilities: Overture release {rel}", flush=True)
    con = duckdb.connect()
    for q in ("INSTALL httpfs", "LOAD httpfs", "SET s3_region='us-west-2'", "SET threads=4", "SET memory_limit='10GB'"):
        con.execute(q)
    places = f"read_parquet('s3://overturemaps-us-west-2/release/{rel}/theme=places/type=place/*', hive_partitioning=1)"
    land = f"read_parquet('s3://overturemaps-us-west-2/release/{rel}/theme=base/type=land_use/*', hive_partitioning=1)"
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {places} LIMIT 1").fetchall()]
    cat = "categories.primary" if "categories" in cols else "basic_category"
    print(f"  places columns {cols}; category from {cat}", flush=True)
    counts = dict(con.execute(f"SELECT {cat} AS c, count(*) FROM {places} WHERE {cat} IS NOT NULL GROUP BY 1").fetchall())
    take_p = sorted(c for c in counts if SPORT.search(c) and not NOT.search(c))
    near_p = sorted(c for c in counts if SPORT.search(c) and NOT.search(c))
    print(f"  places: {len(take_p)} sport categories, {sum(counts[c] for c in take_p):,} places ({time.time() - t0:.0f} s)", flush=True)
    lcounts = dict(con.execute(f"SELECT class, count(*) FROM {land} WHERE class IS NOT NULL GROUP BY 1").fetchall())
    take_l = sorted(c for c in lcounts if SPORT.search(c) and not NOT.search(c))
    near_l = sorted(c for c in lcounts if SPORT.search(c) and NOT.search(c))
    print(f"  grounds: {len(take_l)} sport classes, {sum(lcounts[c] for c in take_l):,} shapes ({time.time() - t0:.0f} s)", flush=True)
    pts = []
    if take_p:
        q = (f"SELECT id, names.primary, {cat}, (bbox.xmin + bbox.xmax) / 2, (bbox.ymin + bbox.ymax) / 2 FROM {places} "
             f"WHERE {cat} IN ({','.join('?' for _ in take_p)})")
        for pid, nm, c, x, y in con.execute(q, take_p).fetchall():
            pts.append((round(x, 6), round(y, 6), {"name": nm or c.replace("_", " "), "kind": c.replace("_", " "), "group": group_of(c),
                                                   "from": "Overture places", "id": pid}))
    if take_l:
        q = (f"SELECT id, names.primary, class, subtype, (bbox.xmin + bbox.xmax) / 2, (bbox.ymin + bbox.ymax) / 2 FROM {land} "
             f"WHERE class IN ({','.join('?' for _ in take_l)})")
        for pid, nm, c, sub, x, y in con.execute(q, take_l).fetchall():
            pts.append((round(x, 6), round(y, 6), {"name": nm or c.replace("_", " "), "kind": c.replace("_", " "), "group": group_of(c),
                                                   "from": "OpenStreetMap, through Overture's land use", "id": pid}))
    print(f"sports_facilities: {len(pts):,} places read ({time.time() - t0:.0f} s)", flush=True)
    if not pts:
        sys.exit("sports_facilities: nothing read")
    parts = pointtiles.build(pts, OUT, "sports", "group", attribution="Overture Maps Foundation; OpenStreetMap contributors (ODbL)")
    by = {}
    for _, _, p in pts:
        by[p["group"]] = by.get(p["group"], 0) + 1
    STAMP.write_text(json.dumps({"layer": "sports", "places": len(pts), "detail_from": 8, "release": rel, "groups": by,
                                 "parts": parts, "date": today.isoformat()}, indent=1))
    INFO.parent.mkdir(exist_ok=True)
    INFO.write_text(json.dumps({"release": rel, "places_categories_taken": {c: counts[c] for c in take_p},
                                "places_categories_left_out_by_name": {c: counts[c] for c in near_p},
                                "land_use_classes_taken": {c: lcounts[c] for c in take_l},
                                "land_use_classes_left_out_by_name": {c: lcounts[c] for c in near_l},
                                "groups": [g for g, _ in GROUPS], "seconds": round(time.time() - t0)}, indent=1))
    print(f"sports_facilities: {len(pts):,} places in {len(parts)} file(s), {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
