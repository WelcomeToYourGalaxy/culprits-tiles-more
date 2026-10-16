#!/usr/bin/env python3
"""
How far light and gravity reach, at every scale (round 210o, asked 15 October
2026): the light and the pull that reach Earth from everything with a
published brightness or mass; what the Sun's light and pull reach; what lies
within Earth's own reach. For the map's Sky, From the Sun and From Earth views
(culprits map/bodies.html). Nothing is filtered: every row of every source is
written; positions and amounts the sources do not give are left empty.

Sources (each named again in the files it feeds):
  HYG star database v4.1 (D. Nash, astronexus), every star, CC BY-SA 4.0
  HYG deep-sky catalogue (dso.csv), every object, CC BY-SA 2.5
  NASA/JPL Horizons (US government, public domain): the Sun, Moon, planets
    and dwarf planets, where they are today, their brightness and GM
  Wikipedia (CC BY-SA 4.0), every row as written: List of nearest stars
    (masses), List of nearest galaxies, Claimed moons of Earth, List of
    objects at Lagrange points, Planetary flyby, List of Earth flybys
  Wikidata (CC0): the galaxies' coordinates, distances and masses
  GCAT (J. McDowell, CC BY): every object still in Earth orbit, counted by
    the height of its orbit
  Published figures for the Milky Way's centre, the Milky Way, Andromeda, the
    Great Attractor and Laniakea, each with its source, in anchors.json

Writes bodies/reach/: stars.json and stars/<n>.json, dso.json and dso/<n>.json,
solar.json, nearest.json, galaxies.json, companions.json, lagrange.json,
flybys.json, earth_orbit.json, anchors.json, build.json.

Units written: distances in AU, angles in degrees (galactic l, b and
equatorial ra, dec). The page works out light (W/m^2) and pull (m/s^2).
"""
import csv, datetime, io, json, math, pathlib, re, sys, time, traceback, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
OUT = pathlib.Path("bodies/reach")
UA = {"User-Agent": "Culprits atlas build (welcometoyourgalaxy@gmail.com)"}
HYG = "https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hygdata_v41.csv"
DSO = "https://raw.githubusercontent.com/astronexus/HYG-Database/main/misc/dso.csv"
HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"
LOOKUP = "https://ssd.jpl.nasa.gov/api/horizons_lookup.api"
WP = "https://en.wikipedia.org/w/api.php"
WD = "https://www.wikidata.org/w/api.php"
GCAT_SAT = "https://planet4589.org/space/gcat/tsv/cat/satcat.tsv"
PC_AU = 206264.806
LY_AU = 63241.077
CHUNK = 2000
# Equatorial (J2000) to galactic, and the obliquity of the ecliptic.
GAL = [[-0.0548755604, -0.8734370902, -0.4838350155],
       [0.4941094279, -0.4448296300, 0.7469822445],
       [-0.8676661490, -0.1980763734, 0.4559837762]]
EPS = math.radians(23.4392911)
BUILD = {"built": datetime.date.today().isoformat(), "parts": {}}


def get(url, tries=4, timeout=180):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def write(name, obj):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


def galactic_from_eq(x, y, z):
    gx = GAL[0][0] * x + GAL[0][1] * y + GAL[0][2] * z
    gy = GAL[1][0] * x + GAL[1][1] * y + GAL[1][2] * z
    gz = GAL[2][0] * x + GAL[2][1] * y + GAL[2][2] * z
    r = math.sqrt(gx * gx + gy * gy + gz * gz) or 1
    return (math.degrees(math.atan2(gy, gx)) % 360, math.degrees(math.asin(max(-1, min(1, gz / r)))))


def radec_to_lb(ra_deg, dec_deg):
    a, d = math.radians(ra_deg), math.radians(dec_deg)
    return galactic_from_eq(math.cos(d) * math.cos(a), math.cos(d) * math.sin(a), math.sin(d))


def ecl_to_eq(x, y, z):
    return x, y * math.cos(EPS) - z * math.sin(EPS), y * math.sin(EPS) + z * math.cos(EPS)


def num(v):
    try:
        f = float(str(v).replace(",", "").replace("−", "-"))
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def r4(v, n=4):
    return None if v is None else round(v, n)


def part(name):
    def deco(fn):
        def run(*a):
            try:
                out = fn(*a)
                BUILD["parts"][name] = out if isinstance(out, dict) else {"ok": True}
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                BUILD["parts"][name] = {"ok": False, "error": str(e)}
        return run
    return deco


# ---------- stars: HYG, every star ----------
@part("stars")
def stars():
    rows = list(csv.DictReader(io.StringIO(get(HYG))))
    cols = list(rows[0].keys())
    draw, chunks = [], {}
    for r in rows:
        i = int(r["id"])
        ra, dec = num(r["ra"]), num(r["dec"])
        ra_deg = ra * 15 if ra is not None else None
        dist = num(r["dist"])
        known = dist is not None and 0 < dist < 100000          # HYG writes 100000 where no distance is known
        l, b = radec_to_lb(ra_deg, dec) if ra_deg is not None and dec is not None else (None, None)
        name = r["proper"] or ((r["bayer"] or r["flam"]) + " " + r["con"] if (r["bayer"] or r["flam"]) else "") or \
            ("HIP " + r["hip"] if r["hip"] else "HD " + r["hd"] if r["hd"] else r["gl"] if r["gl"] else "HYG " + r["id"])
        draw.append([i, name, r4(ra_deg), r4(dec), r4(dist * PC_AU, 1) if known else None, num(r["mag"]),
                     r4(l), r4(b), num(r["lum"]), r["spect"]])
        chunks.setdefault(i // CHUNK, {})[str(i)] = [r[c] for c in cols]
    write("stars.json", {"cols": ["id", "name", "ra", "dec", "d_au", "mag", "l", "b", "lum", "spect"], "rows": draw,
                         "chunk": CHUNK, "hyg_columns": cols,
                         "source": "HYG star database v4.1 (D. Nash, astronexus.com), CC BY-SA 4.0"})
    for k, v in chunks.items():
        write(f"stars/{k}.json", {"cols": cols, "rows": v})
    return {"ok": True, "stars": len(draw), "no_distance": sum(1 for d in draw if d[4] is None)}


# ---------- deep-sky objects: HYG's dso.csv, every object ----------
@part("dso")
def dso():
    rows = list(csv.DictReader(io.StringIO(get(DSO))))
    cols = list(rows[0].keys())
    draw, chunks = [], {}
    for n, r in enumerate(rows):
        i = int(r["id"]) if r.get("id") else n
        ra, dec = num(r["ra"]), num(r["dec"])
        ra_deg = ra * 15 if ra is not None else None
        l, b = radec_to_lb(ra_deg, dec) if ra_deg is not None and dec is not None else (None, None)
        name = r["name"] or " ".join(x for x in (r["cat1"], r["id1"]) if x) or f"object {i}"
        draw.append([i, name, r["type"], r4(ra_deg), r4(dec), num(r["mag"]), r4(l), r4(b)])
        chunks.setdefault(i // CHUNK, {})[str(i)] = [r[c] for c in cols]
    write("dso.json", {"cols": ["id", "name", "type", "ra", "dec", "mag", "l", "b"], "rows": draw, "chunk": CHUNK,
                       "source": "HYG deep-sky catalogue, dso.csv (astronexus.com), CC BY-SA 2.5; types as in the Historically Corrected NGC"})
    for k, v in chunks.items():
        write(f"dso/{k}.json", {"cols": cols, "rows": v})
    return {"ok": True, "objects": len(draw)}


# ---------- Horizons ----------
def horizons(params):
    q = {"format": "json", "OBJ_DATA": "'YES'", "MAKE_EPHEM": "'YES'", "CSV_FORMAT": "'YES'"}
    q.update({k: f"'{v}'" for k, v in params.items()})
    d = json.loads(get(f"{HORIZONS}?{urllib.parse.urlencode(q)}"))
    time.sleep(0.4)
    return d.get("result", "")


def soe(text):
    if "$$SOE" not in text:
        return []
    body = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    return [[c.strip() for c in line.split(",")] for line in body.strip().splitlines()]


def gm_of(text):
    m = re.search(r"GM[^=\n]{0,25}=\s*([0-9.]+(?:[eE][-+]?\d+)?)", text)
    return float(m.group(1)) if m else None      # km^3/s^2


def vec(command, center, when, extra=None):
    tomorrow = (datetime.date.fromisoformat(when) + datetime.timedelta(days=1)).isoformat()
    p = {"COMMAND": command, "EPHEM_TYPE": "VECTORS", "CENTER": center, "START_TIME": when, "STOP_TIME": tomorrow,
         "STEP_SIZE": "1 d", "REF_PLANE": "ECLIPTIC", "REF_SYSTEM": "ICRF", "VEC_TABLE": "1", "OUT_UNITS": "AU-D", "VEC_LABELS": "NO"}
    if extra:
        p.update(extra)
    t = horizons(p)
    rows = soe(t)
    if not rows:
        return None, t
    c = rows[0]
    return (float(c[2]), float(c[3]), float(c[4])), t


def obs(command, when):
    tomorrow = (datetime.date.fromisoformat(when) + datetime.timedelta(days=1)).isoformat()
    t = horizons({"COMMAND": command, "EPHEM_TYPE": "OBSERVER", "CENTER": "500@399", "START_TIME": when, "STOP_TIME": tomorrow,
                  "STEP_SIZE": "1 d", "QUANTITIES": "1,9,20", "ANG_FORMAT": "DEG"})
    rows = soe(t)
    if not rows or "$$SOE" not in t:
        return None
    # The column names are on the line above the first row.
    head = [h.strip() for h in t.split("$$SOE", 1)[0].strip().splitlines()[-2].split(",")]
    c = dict(zip(head, rows[0]))
    pick = lambda pat: next((num(v) for k, v in c.items() if re.search(pat, k)), None)  # noqa: E731
    ra, dec = pick(r"^R\.A\."), pick(r"^DEC")
    if ra is None or dec is None:
        return None
    return {"ra": ra, "dec": dec, "mag": pick(r"^APmag")}


SOLAR = [("Sun", "10"), ("Mercury", "199"), ("Venus", "299"), ("Earth", "399"), ("Moon", "301"), ("Mars", "499"),
         ("Jupiter", "599"), ("Saturn", "699"), ("Uranus", "799"), ("Neptune", "899"), ("Pluto", "999"),
         ("Ceres", "1;"), ("Eris", "136199;"), ("Haumea", "136108;"), ("Makemake", "136472;"), ("Sedna", "90377;")]


@part("solar")
def solar(today):
    out = []
    for name, cmd in SOLAR:
        rec = {"name": name, "horizons": cmd}
        try:
            h, text = vec(cmd, "500@10", today)
            rec["gm_km3_s2"] = gm_of(text)
            if h:
                rec["helio_au"] = [r4(v, 6) for v in h]
                rec["l_b_from_sun"] = [r4(v) for v in galactic_from_eq(*ecl_to_eq(*h))] if name != "Sun" else None
            g, _ = vec(cmd, "500@399", today)
            if g and name != "Earth":
                rec["geo_au"] = [r4(v, 8) for v in g]
                rec["l_b_from_earth"] = [r4(v) for v in galactic_from_eq(*ecl_to_eq(*g))]
            if name != "Earth":
                o = obs(cmd, today)
                if o:
                    rec["ra"], rec["dec"], rec["mag"] = r4(o["ra"]), r4(o["dec"]), o["mag"]
        except Exception as e:  # noqa: BLE001
            rec["error"] = str(e)
        out.append(rec)
    write("solar.json", {"bodies": out, "date": today, "source": "NASA/JPL Horizons, ssd.jpl.nasa.gov/horizons (positions today; GM from its physical data)"})
    return {"ok": True, "bodies": len(out)}


# ---------- Wikipedia tables ----------
def wiki_tables(page):
    import solar_companies as sc
    q = urllib.parse.urlencode({"action": "parse", "page": page, "prop": "text", "format": "json", "formatversion": 2, "redirects": 1})
    html = json.loads(get(f"{WP}?{q}"))["parse"]["text"]
    p = sc.Page()
    p.feed(html)
    out = []
    for n, t in enumerate(p.tables):
        g = sc.grid(t["rows"])
        if not g:
            continue
        # The header: the leading rows made only of header cells, joined.
        hdr_rows = []
        for line in g:
            if all(c["th"] for c in line):
                hdr_rows.append(line)
            else:
                break
        width = max(len(x) for x in g)
        names = []
        for i in range(width):
            parts = []
            for h in hdr_rows:
                if i < len(h) and h[i]["text"] and (not parts or parts[-1] != h[i]["text"]):
                    parts.append(h[i]["text"])
            names.append(" / ".join(parts) or f"column {i + 1}")
        rows = []
        for line in g[len(hdr_rows):]:
            if all(c["th"] for c in line) and len(set(c["text"] for c in line)) <= 1:
                continue
            rec = {"table": t["section"] or f"table {n + 1}"}
            links = {}
            for i, c in enumerate(line):
                k = names[i] if i < len(names) else f"column {i + 1}"
                if k in rec and rec[k] != c["text"]:
                    k = f"{k} ({i + 1})"
                rec[k] = c["text"]
                if c.get("link"):
                    links[k] = c["link"]
            rows.append({"row": rec, "links": links})
        out.append({"section": t["section"], "columns": names, "rows": rows})
    return out


def coords_in(text):
    """RA/Dec written as in Wikipedia's tables: 14h 29m 43s / -62° 40′ 46″ (any of the usual marks)."""
    t = text.replace("−", "-").replace("−", "-")
    m = re.search(r"(\d{1,2})\s*h\s*(\d{1,2})\s*m\s*([\d.]+)?\s*s?.*?([+-]?\d{1,2})\s*°\s*(\d{1,2})?\s*[′']?\s*([\d.]+)?", t)
    if not m:
        return None
    ra = (int(m.group(1)) + int(m.group(2)) / 60 + (float(m.group(3) or 0)) / 3600) * 15
    sgn = -1 if m.group(4).startswith("-") else 1
    dec = sgn * (abs(int(m.group(4))) + int(m.group(5) or 0) / 60 + float(m.group(6) or 0) / 3600)
    return ra, dec


def first_num(text):
    m = re.search(r"-?\d+(?:\.\d+)?", (text or "").replace(",", "").replace("−", "-"))
    return float(m.group(0)) if m else None


@part("nearest")
def nearest():
    tabs = wiki_tables("List_of_nearest_stars")
    rows = []
    for t in tabs:
        cols = t["columns"]
        mc = next((c for c in cols if re.search(r"mass", c, re.I)), None)
        dc = next((c for c in cols if re.search(r"distance", c, re.I)), None)
        rc = next((c for c in cols if re.search(r"ra/dec|right ascension|ra\b", c, re.I)), None)
        if not mc:
            continue
        for x in t["rows"]:
            r = x["row"]
            pos = coords_in(r.get(rc, "")) if rc else None
            d_ly = first_num(r.get(dc, "")) if dc else None
            mass = first_num(r.get(mc, ""))
            rec = {"row": r, "mass_msun": mass, "d_au": r4(d_ly * LY_AU, 1) if d_ly else None}
            if pos:
                rec["ra"], rec["dec"] = r4(pos[0]), r4(pos[1])
                rec["l"], rec["b"] = [r4(v) for v in radec_to_lb(*pos)]
            rows.append(rec)
    write("nearest.json", {"rows": rows, "source": "Wikipedia, List of nearest stars (CC BY-SA 4.0): every row of its tables with a mass column, as written"})
    return {"ok": True, "rows": len(rows)}


def wikidata_items(titles):
    qid = {}
    titles = list(titles)
    for i in range(0, len(titles), 40):
        q = urllib.parse.urlencode({"action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "redirects": 1,
                                    "titles": "|".join(titles[i:i + 40]), "format": "json"})
        d = json.loads(get(f"{WP}?{q}"))
        back = {}
        for r in d.get("query", {}).get("normalized", []) + d.get("query", {}).get("redirects", []):
            back[r["to"]] = back.get(r["from"], r["from"])
        for p in d.get("query", {}).get("pages", {}).values():
            item = (p.get("pageprops") or {}).get("wikibase_item")
            if item:
                qid[back.get(p["title"], p["title"]).replace(" ", "_")] = item
                qid[p["title"].replace(" ", "_")] = item
        time.sleep(0.3)
    ents = {}
    ids = sorted(set(qid.values()))
    for i in range(0, len(ids), 40):
        q = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(ids[i:i + 40]), "props": "claims", "format": "json"})
        ents.update(json.loads(get(f"{WD}?{q}")).get("entities", {}))
        time.sleep(0.3)
    return qid, ents


def wd_amount(ent, prop):
    for c in (ent or {}).get("claims", {}).get(prop, []):
        v = (c["mainsnak"].get("datavalue") or {}).get("value")
        if isinstance(v, dict) and "amount" in v:
            return float(v["amount"]), v.get("unit", "")
    return None, None


@part("galaxies")
def galaxies():
    tabs = wiki_tables("List_of_nearest_galaxies")
    rows, titles = [], set()
    for t in tabs:
        gc = next((c for c in t["columns"] if re.search(r"galaxy", c, re.I)), None)
        dc = next((c for c in t["columns"] if re.search(r"\(Mly\)", c)), None)
        if not gc:
            continue
        for x in t["rows"]:
            link = x["links"].get(gc)
            if link:
                titles.add(link)
            rows.append({"row": x["row"], "link": link, "d_mly": first_num(x["row"].get(dc, "")) if dc else None})
    qid, ents = wikidata_items(titles) if titles else ({}, {})
    for r in rows:
        e = ents.get(qid.get(r["link"] or "", ""), {})
        ra, _ = wd_amount(e, "P6257")
        dec, _ = wd_amount(e, "P6258")
        mass, unit = wd_amount(e, "P2067")
        r["wikidata"] = qid.get(r["link"] or "")
        if ra is not None and dec is not None:
            r["ra"], r["dec"] = r4(ra), r4(dec)
            r["l"], r["b"] = [r4(v) for v in radec_to_lb(ra, dec)]
        if mass is not None:
            # Wikidata units: Q180892 is the solar mass; Q11570 the kilogram.
            r["mass_msun"] = mass if unit.endswith("Q180892") else mass / 1.98847e30 if unit.endswith("Q11570") else None
            r["mass_as_given"] = f"{mass} ({unit.rsplit('/', 1)[-1]})"
        if r["d_mly"] is not None:
            r["d_au"] = r4(r["d_mly"] * 1e6 * LY_AU, 0)
    write("galaxies.json", {"rows": rows, "source": "Wikipedia, List of nearest galaxies (CC BY-SA 4.0); coordinates and masses from Wikidata (CC0) where it has them"})
    return {"ok": True, "rows": len(rows), "placed": sum(1 for r in rows if "l" in r)}


def horizons_target(name):
    """A Horizons command for a row's object: a number, a provisional designation, or a spacecraft name."""
    t = name.replace("ʻ", "'")
    if not re.match(r"^\s*(?:19|20)\d\d\s+[A-Z]{1,2}\d{0,4}\b", t):
        m = re.match(r"^\s*\(?(\d{3,7})\)?\s", t)
        if m:
            return f"{m.group(1)};"
    m = re.search(r"\b((?:19|20)\d\d\s?[A-Z]{1,2}\d{0,4})\b", t)
    if m:
        return f"DES={m.group(1)};"
    return None


@part("companions")
def companions(today):
    tabs = wiki_tables("Claimed_moons_of_Earth")
    rows = []
    for t in tabs:
        nc = next((c for c in t["columns"] if re.search(r"^name", c, re.I)), t["columns"][0])
        for x in t["rows"]:
            r = x["row"]
            rec = {"row": r}
            cmd = horizons_target(r.get(nc, ""))
            if cmd:
                try:
                    g, _ = vec(cmd, "500@399", today)
                    if g:
                        rec["geo_au"] = [r4(v, 8) for v in g]
                        rec["l_b_from_earth"] = [r4(v) for v in galactic_from_eq(*ecl_to_eq(*g))]
                        rec["horizons"] = cmd
                except Exception as e:  # noqa: BLE001
                    rec["error"] = str(e)
            rows.append(rec)
    write("companions.json", {"rows": rows, "date": today,
                              "source": "Wikipedia, Claimed moons of Earth (CC BY-SA 4.0); places today from NASA/JPL Horizons where it follows them"})
    return {"ok": True, "rows": len(rows), "placed": sum(1 for r in rows if "geo_au" in r)}


def lookup_sct(name):
    q = urllib.parse.urlencode({"sstr": name, "group": "sct", "format": "json"})
    try:
        d = json.loads(get(f"{LOOKUP}?{q}"))
    except Exception:  # noqa: BLE001
        return None
    time.sleep(0.4)
    norm = lambda s: re.sub(r"[^a-z0-9]", "", re.sub(r"\(spacecraft\)", "", s, flags=re.I).lower())  # noqa: E731
    for r in d.get("result") or []:
        if any(norm(n) == norm(name) for n in [r.get("name") or ""] + list(r.get("alias") or [])):
            return str(r.get("spkid"))
    return None


@part("lagrange")
def lagrange(today):
    tabs = wiki_tables("List_of_objects_at_Lagrange_points")
    rows = []
    for t in tabs:
        mc = next((c for c in t["columns"] if re.search(r"mission", c, re.I)), t["columns"][0])
        for x in t["rows"]:
            r = x["row"]
            rec = {"row": r}
            spk = lookup_sct(re.sub(r"\[.*?\]", "", r.get(mc, "")).strip())
            if spk:
                try:
                    g, _ = vec(spk, "500@399", today)
                    if g:
                        rec["geo_au"] = [r4(v, 8) for v in g]
                        rec["l_b_from_earth"] = [r4(v) for v in galactic_from_eq(*ecl_to_eq(*g))]
                        rec["horizons"] = spk
                except Exception as e:  # noqa: BLE001
                    rec["error"] = str(e)
            rows.append(rec)
    write("lagrange.json", {"rows": rows, "date": today,
                            "source": "Wikipedia, List of objects at Lagrange points (CC BY-SA 4.0); places today from NASA/JPL Horizons where it follows them"})
    return {"ok": True, "rows": len(rows), "placed": sum(1 for r in rows if "geo_au" in r)}


BODY_CMD = {"mercury": "199", "venus": "299", "earth": "399", "moon": "301", "mars": "499", "jupiter": "599", "saturn": "699",
            "uranus": "799", "neptune": "899", "pluto": "999"}
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                         "september", "october", "november", "december"])}


def date_in(text):
    t = (text or "").lower()
    m = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", t)
    if m and m.group(2) in MONTHS:
        return datetime.date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
    m = re.search(r"([a-z]+)\s+(\d{1,2}),?\s+(\d{4})", t)
    if m and m.group(1) in MONTHS:
        return datetime.date(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)))
    return None


@part("flybys")
def flybys():
    rows = []
    for page in ("Planetary_flyby", "List_of_Earth_flybys"):
        for t in wiki_tables(page):
            body = next((b for b in BODY_CMD if re.search(rf"\b{b}\b", (t["section"] or "").lower())), "earth" if page == "List_of_Earth_flybys" else None)
            dc = next((c for c in t["columns"] if re.search(r"flyby date|date", c, re.I)), None)
            for x in t["rows"]:
                r = x["row"]
                rec = {"row": r, "page": page.replace("_", " "), "body": body}
                d = date_in(r.get(dc, "")) if dc else None
                if body and d:
                    rec["date"] = d.isoformat()
                    try:
                        h, _ = vec(BODY_CMD[body], "500@10", d.isoformat())
                        if h:
                            rec["helio_au"] = [r4(v, 6) for v in h]
                    except Exception as e:  # noqa: BLE001
                        rec["error"] = str(e)
                rows.append(rec)
    write("flybys.json", {"rows": rows, "source": "Wikipedia, Planetary flyby and List of Earth flybys (CC BY-SA 4.0); each flown-by body's place on the day from NASA/JPL Horizons"})
    return {"ok": True, "rows": len(rows), "placed": sum(1 for r in rows if "helio_au" in r)}


@part("earth_orbit")
def earth_orbit():
    text = get(GCAT_SAT, timeout=600)
    head, shells = None, {}
    names = [("low Earth orbit (perigee under 2,000 km)", 0, 2000), ("medium Earth orbit (2,000 to 35,586 km)", 2000, 35586),
             ("geostationary band (35,586 to 35,986 km)", 35586, 35986), ("higher (perigee above 35,986 km)", 35986, 1e12)]
    total = 0
    for line in text.splitlines():
        if line.startswith("#"):
            if head is None and "JCAT" in line:
                head = [h.strip() for h in line.lstrip("#").split("\t")]
            continue
        if not head or not line.strip():
            continue
        c = dict(zip(head, [x.strip() for x in line.split("\t")]))
        if c.get("Primary") != "Earth" or c.get("DDate", "-") not in ("", "-"):
            continue
        per = num(c.get("Perigee"))
        kind = {"P": "payloads", "R": "rocket stages", "D": "debris", "C": "components"}.get((c.get("Type") or " ")[0], "other")
        for nm, lo, hi in names:
            if per is not None and lo <= per < hi:
                s = shells.setdefault(nm, {"lo_km": lo, "hi_km": hi if hi < 1e12 else None, "total": 0})
                s["total"] += 1
                s[kind] = s.get(kind, 0) + 1
                total += 1
                break
    write("earth_orbit.json", {"shells": [dict(name=n, **shells[n]) for n, _, _ in names if n in shells], "total": total,
                               "how": "Every object in GCAT's main satellite catalogue whose primary is Earth and which has no decay date, counted by the height of its perigee",
                               "source": "J. McDowell, General Catalog of Artificial Space Objects (GCAT), satcat (CC BY)"})
    return {"ok": True, "objects": total}


ANCHORS = [
    {"name": "Sagittarius A*, the black hole at the Milky Way's centre", "ra": 266.41684, "dec": -29.00781, "d_pc": 8277, "mass_msun": 4.297e6,
     "source": "Mass: GRAVITY Collaboration (2023), Astronomy & Astrophysics 677, L10; distance 8,277 pc and position as given on Wikipedia's Sagittarius A* page (CC BY-SA 4.0)"},
    {"name": "The Milky Way, the galaxy as a whole", "ra": 266.41684, "dec": -29.00781, "d_pc": 8320,
     "mass_msun_published": [["5.8e11", "Karachentsev et al. 2006"], ["8.5e11", "Penarrubia et al. 2014"], ["8.8e11", "within 200 kpc, as given on Wikipedia"],
                             ["1.29e12", "2019 estimate"], ["1.54e12", "within about 39.5 kpc, 2019"], ["2.06e11", "2023, from Gaia data"]],
     "orbit_speed_km_s": 220, "orbit_radius_pc": 8320,
     "how": "Its pull on the Sun, and with it on Earth, is worked out from the Sun's orbit round the centre: speed squared over distance, 220 km/s at 8.32 kpc",
     "source": "Wikipedia, Milky Way (CC BY-SA 4.0): masses with their studies; distance 8.32 kpc (Gillessen et al. 2016); speed about 220 km/s"},
    {"name": "Andromeda Galaxy (M31)", "ra": 10.68458, "dec": 41.26917, "d_pc": 765000, "mass_msun": 1.5e12, "mag": 3.44,
     "source": "Wikipedia, Andromeda Galaxy (CC BY-SA 4.0): mass (1.5 +/- 0.2) x 10^12 solar masses, 765 kpc; the article adds that 2018 radio results give about 8 x 10^11"},
    {"name": "The Great Attractor", "l": 307, "b": 9, "d_ly_range": [150e6, 250e6], "mass_msun": 1e16,
     "source": "Wikipedia, Great Attractor (CC BY-SA 4.0): near galactic longitude 307, latitude 9; 150-250 million light-years (NASA 2013); about 10^16 solar masses (Kraan-Korteweg 2005)"},
    {"name": "Laniakea Supercluster, the centre of its pull", "ra": 158.0, "dec": -46.0, "d_ly": 250e6, "mass_msun": 1e17,
     "source": "Tully, Courtois, Hoffman and Pomarede (2014), Nature 513, 71-73; values as given on Wikipedia's Laniakea Supercluster page (CC BY-SA 4.0): centre RA 10h32m, Dec -46 deg, 250 million ly, binding mass 10^17 solar masses"},
]


@part("anchors")
def anchors():
    out = []
    for a in ANCHORS:
        a = dict(a)
        if "ra" in a:
            a["l"], a["b"] = [r4(v) for v in radec_to_lb(a["ra"], a["dec"])]
        d_au = a["d_pc"] * PC_AU if "d_pc" in a else a["d_ly"] * LY_AU if "d_ly" in a else sum(a["d_ly_range"]) / 2 * LY_AU
        a["d_au"] = d_au
        out.append(a)
    write("anchors.json", {"rows": out})
    return {"ok": True, "rows": len(out)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    stars()
    dso()
    solar(today)
    nearest()
    galaxies()
    companions(today)
    lagrange(today)
    flybys()
    earth_orbit()
    anchors()
    write("build.json", BUILD)
    print(json.dumps(BUILD, indent=1))


if __name__ == "__main__":
    main()
