#!/usr/bin/env python3
"""
The Atlas for the End of the World's conflict pages, placed on the map
(round 61, 26 September).

Several hotspot PDFs carry, after their first page, a "| CONFLICTS" page (a
map of the hotspot with its cities numbered, where 2030 urban growth meets
threatened species habitat) and then pages of round inset maps, one per
numbered city, each titled "N. CITY, COUNTRY" with its 2015 and 2030
population projections. The owner asked for these to be part of what shows
when a hotspot is opened.

For each PDF copied to atlas/pdfs/ (scripts/atlas_pdfs.py):
  * The conflicts page's map is placed by its own numbered cities: each
    number's position on the page is paired with that city's position in
    OpenStreetMap (Nominatim, from the name the inset page prints), and the
    page's scale and offset are fitted to them (north up, one scale across
    and down). A city whose number sits far from where the others put it is
    left out of the fit (a label set beside its marker, or a name found in
    the wrong place) and said so. The map is kept only if at least four
    cities agree, and the typical error is under 2% of the map's width.
  * Each city's inset is cut from its page as a round picture, with its title
    and population projections as printed, and set at the city's position.
Nothing is placed from a guess: a city neither OpenStreetMap nor Natural
Earth's populated places finds is listed, not placed; the insets have no scale bar, so they are shown as pictures on
the city, not stretched over the ground.

Writes atlas/insets.json and atlas/insets/<slug>_conflicts.webp and
atlas/insets/<slug>_<n>.webp. A hotspot already done is not done again
(ATLAS_INSETS_AGAIN=1 does them all again).
"""
import io, json, math, os, pathlib, re, subprocess, sys, time, urllib.parse, urllib.request

PDFS = pathlib.Path("atlas/pdfs")
OUT = pathlib.Path("atlas/insets")
INDEX = pathlib.Path("atlas/insets.json")
BASE = "https://welcometoyourgalaxy.github.io/culprits-tiles-more/"
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
# Round 98b (28 September): 2. Most PDFs print their conflicts page's title
# as "| Conflicts", not "| CONFLICTS", and the search for it minded the case,
# so Madagascar, the Western Ghats, the Philippines, the Caribbean and five
# more were read as having none. And a look-up that failed (OpenStreetMap
# busy) was kept as "not found" for good: Addis Ababa, Nairobi, Sydney and
# Dar es Salaam were never placed. Everything is done again.
METHOD = 2
# Natural Earth's populated places (1:10m, public domain), asked only when
# OpenStreetMap finds nothing for the name as printed.
NE_PLACES = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_populated_places_simple.geojson"
_ne_places = None
R = 6378137.0


def deps():
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pymupdf", "pillow"], check=True)


def ask_osm(q):
    """OpenStreetMap's first answer for q, None when it has none, or an
    exception when it could not be asked (then nothing is kept)."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1})
    last = None
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                rows = json.loads(r.read())
            time.sleep(1.2)
            if rows and rows[0].get("category", rows[0].get("class")) in ("place", "boundary"):
                return {"lon": float(rows[0]["lon"]), "lat": float(rows[0]["lat"]), "found": rows[0].get("display_name"),
                        "source": "OpenStreetMap"}
            return None
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"    OpenStreetMap {q}: {e}", flush=True)
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"OpenStreetMap did not answer ({last})")


def ne_places():
    global _ne_places
    if _ne_places is None:
        try:
            with urllib.request.urlopen(urllib.request.Request(NE_PLACES, headers=UA), timeout=180) as r:
                _ne_places = [f["properties"] | {"_xy": f["geometry"]["coordinates"]} for f in json.loads(r.read())["features"]]
        except Exception as e:  # noqa: BLE001
            print(f"    Natural Earth's places could not be read ({e})", flush=True)
            _ne_places = []
    return _ne_places


def fold(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]+", " ", s).strip()


def ask_ne(city, country):
    """Natural Earth's place of that name (and, where given, that country)."""
    want, land = fold(city), fold(country)
    hits = []
    for p in ne_places():
        names = {fold(p.get(k)) for k in ("name", "nameascii", "namealt", "namepar") if p.get(k)}
        names |= {fold(x) for x in str(p.get("namealt") or "").split("|")}
        if want in names:
            same = not land or any(land and land in fold(p.get(k)) or fold(p.get(k)) in land
                                   for k in ("adm0name", "sov0name") if p.get(k))
            if same:
                hits.append(p)
    if not hits:
        return None
    p = max(hits, key=lambda p: p.get("pop_max") or 0)
    return {"lon": float(p["_xy"][0]), "lat": float(p["_xy"][1]), "found": f"{p.get('name')}, {p.get('adm0name')}",
            "source": "Natural Earth populated places"}


def geocode(name, cache):
    """The place for a title as printed ("ADDIS ABABA, ETHIOPIA"). A name the
    look-ups could not be asked about is not kept, so a later run asks again."""
    if cache.get(name):
        return cache[name]
    # The Atlas's own misspellings, asked as the place is spelt; the title
    # stays as printed.
    q0 = re.sub(r"\bJaimaca\b", "Jamaica", name, flags=re.I)
    city, _, country = q0.partition(",")
    tries = [q0]
    if re.search(r"\s+city\s*$", city, re.I):     # "ILOILO CITY": also "ILOILO"
        tries.append(re.sub(r"\s+city\s*$", "", city, flags=re.I) + "," + country)
    if "/" in city:                                   # "MECCA / JEDDAH, SAUDI ARABIA": the first
        tries.append(f"{city.split('/')[0].strip()},{country}")
    got, asked = None, True
    for q in tries:
        try:
            got = ask_osm(q)
        except RuntimeError:
            asked = False
        if got:
            break
    if not got:
        for q in tries:
            c, _, k = q.partition(",")
            got = ask_ne(c.strip(), k.strip())
            if got:
                break
    if got or asked:
        cache[name] = got
    return got


def merc(lon, lat):
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def unmerc(x, y):
    return math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)


def fit(points):
    """points: [(u, v, X, Y, n)]; north up, one scale: X = s u + tx, Y = -s v + ty."""
    n = len(points)
    ub = sum(p[0] for p in points) / n; vb = sum(p[1] for p in points) / n
    Xb = sum(p[2] for p in points) / n; Yb = sum(p[3] for p in points) / n
    num = sum((p[0] - ub) * (p[2] - Xb) - (p[1] - vb) * (p[3] - Yb) for p in points)
    den = sum((p[0] - ub) ** 2 + (p[1] - vb) ** 2 for p in points)
    s = num / den if den else 0
    return s, Xb - s * ub, Yb + s * vb


def residual_km(p, s, tx, ty):
    X, Y = s * p[0] + tx, -s * p[1] + ty
    lat = unmerc(p[2], p[3])[1]
    return math.hypot(X - p[2], Y - p[3]) * math.cos(math.radians(lat)) / 1000.0


def city_headings(page):
    """(n, title as printed, bbox, 2015, 2030) for each inset heading on a page."""
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            s = " ".join(sp["text"] for sp in l["spans"]).strip()
            if s:
                lines.append((l["bbox"], s, l["spans"][0]["size"]))
    heads = []
    for bbox, s, size in lines:
        m = re.match(r"^(\d{1,2})\.\s+(.+)$", s)
        if m and size >= 10:
            title = m.group(2).strip()
            # A title that runs onto a second line (GUATEMALA CITY, / GUATEMALA).
            for b2, s2, z2 in lines:
                if abs(b2[0] - bbox[0]) < 2 and 0 < b2[1] - bbox[1] < 20 and z2 >= 10 and not re.match(r"^\d", s2):
                    title = f"{title} {s2}".strip()
            heads.append({"n": int(m.group(1)), "title": re.sub(r",\s*$", "", title), "bbox": bbox})
    for h in heads:
        x0, y0 = h["bbox"][0], h["bbox"][1]
        near = [(bb, s) for bb, s, z in lines if x0 - 2 < bb[0] < x0 + 160 and y0 < bb[1] < y0 + 80]
        col = {}
        for bb, s in near:
            if s in ("2015:", "2030:"):
                col[s] = bb
        for key, label in (("population_2015", "2015:"), ("population_2030", "2030:")):
            if label in col:
                c = col[label]
                vals = [(bb, s) for bb, s in near if re.fullmatch(r"[\d,]+", s) and abs(bb[0] - c[0]) < 6]
                if vals:
                    h[key] = min(vals, key=lambda t: abs(t[0][1] - c[1]))[1]
    return heads


def round_picture(page, rect, px=420):
    from PIL import Image, ImageDraw
    import pymupdf
    z = px / max(rect.width, 1)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=rect, alpha=False)
    im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).ellipse([1, 1, im.size[0] - 2, im.size[1] - 2], fill=255)
    im.putalpha(mask)
    return im


def do_one(slug, pdf, cache):
    import pymupdf
    doc = pymupdf.open(pdf)
    conf = next((i for i in range(1, doc.page_count) if re.search(r"\|\s*CONFLICTS", doc[i].get_text(), re.I)), None)
    if conf is None:
        return {"v": METHOD, "kept": False, "reason": "no conflicts page in the PDF"}
    cities = {}
    for i in range(conf + 1, doc.page_count):
        page = doc[i]
        pics = [pymupdf.Rect(x["bbox"]) for x in page.get_image_info()]
        for h in city_headings(page):
            hb = pymupdf.Rect(h["bbox"])
            left = [r for r in pics if r.x1 <= hb.x0 + 5 and r.y0 - 20 < hb.y0 < r.y1 and r.width > 60]
            pic = max(left, key=lambda r: r.x1) if left else None
            cities[h["n"]] = {"n": h["n"], "title": h["title"], "page": i + 1,
                              **{k: h[k] for k in ("population_2015", "population_2030") if k in h}, "_pic": pic, "_page": page}
    page = doc[conf]
    infos = [x for x in page.get_image_info(xrefs=True)]
    pics = [pymupdf.Rect(x["bbox"]) for x in infos]
    main_info = max((x for x in infos if pymupdf.Rect(x["bbox"]).x1 < page.rect.width * 0.72),
                    key=lambda x: pymupdf.Rect(x["bbox"]).width * pymupdf.Rect(x["bbox"]).height, default=None)
    main = pymupdf.Rect(main_info["bbox"]) if main_info else None
    if main is None:
        return {"v": METHOD, "kept": False, "reason": "no map picture on the conflicts page", "cities": len(cities)}
    area = pymupdf.Rect(main.x0 - 10, main.y0 - 10, main.x1 + 10, main.y1 + 10)
    labels = {}
    for w in page.get_text("words"):
        r = pymupdf.Rect(w[:4])
        if re.fullmatch(r"\d{1,2}", w[4]) and area.contains(r) and r.height > 9:
            n = int(w[4])
            if n in cities and n not in labels:
                labels[n] = ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)
    OUT.mkdir(parents=True, exist_ok=True)
    out_cities, pts = [], []
    for n, c in sorted(cities.items()):
        g = geocode(c["title"], cache)
        row = {k: v for k, v in c.items() if not k.startswith("_")}
        if g:
            row.update({"lon": g["lon"], "lat": g["lat"], "openstreetmap" if g.get("source", "OpenStreetMap") == "OpenStreetMap" else "natural_earth": g["found"]})
            if n in labels:
                X, Y = merc(g["lon"], g["lat"])
                pts.append((labels[n][0], labels[n][1], X, Y, n))
        else:
            row["not_placed"] = "neither OpenStreetMap nor Natural Earth found the name as printed"
        if c["_pic"] is not None:
            im = round_picture(c["_page"], c["_pic"])
            name = f"{slug}_{n}.webp"
            im.save(OUT / name, "WEBP", quality=84)
            row["image"] = BASE + str(OUT / name)
        out_cities.append(row)
    res = {"v": METHOD, "conflicts_page": conf + 1, "cities": out_cities, "labels_found": len(labels)}
    left_out = []
    while len(pts) >= 4:
        s, tx, ty = fit(pts)
        errs = sorted((residual_km(p, s, tx, ty), p) for p in pts)
        med = errs[len(errs) // 2][0]
        worst = errs[-1]
        if len(pts) > 4 and worst[0] > max(3 * med, 1e-6):
            left_out.append({"n": worst[1][4], "km_off": round(worst[0], 1)})
            pts = [p for p in pts if p is not worst[1]]
            continue
        break
    if len(pts) < 4:
        res.update({"kept": False, "reason": f"only {len(pts)} numbered cities found on the map and in OpenStreetMap (at least 4 needed)"})
        return res
    s, tx, ty = fit(pts)
    errs = sorted(residual_km(p, s, tx, ty) for p in pts)
    typical = errs[len(errs) // 2]
    corners = [unmerc(s * u + tx, -s * v + ty) for u, v in ((main.x0, main.y0), (main.x1, main.y0), (main.x1, main.y1), (main.x0, main.y1))]
    lat_mid = (corners[0][1] + corners[2][1]) / 2
    width_km = s * main.width * math.cos(math.radians(lat_mid)) / 1000.0
    res.update({"fit_cities": [p[4] for p in pts], "left_out_of_fit": left_out, "error_km": round(typical, 1), "width_km": round(width_km, 1)})
    if typical > 0.02 * width_km:
        res.update({"kept": False, "reason": f"typical error {typical:.1f} km is over 2% of the {width_km:.0f} km map"})
        return res
    # The map picture itself, without the page's legend and numbers printed
    # over it; its white paper made clear so the ground shows round the land.
    from PIL import Image
    im = None
    if main_info.get("xref"):
        try:
            pix = pymupdf.Pixmap(doc, main_info["xref"])
            if pix.alpha or pix.n > 3:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
        except Exception:  # noqa: BLE001
            im = None
    if im is None:
        z = 2400 / main.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=main, alpha=False)
        im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    if im.width > 3000:
        im = im.resize((3000, round(im.height * 3000 / im.width)))
    px = im.load()
    for yy in range(im.height):
        for xx in range(im.width):
            r_, g_, b_, a_ = px[xx, yy]
            if r_ > 244 and g_ > 244 and b_ > 244:
                px[xx, yy] = (r_, g_, b_, 0)
    im.save(OUT / f"{slug}_conflicts.webp", "WEBP", quality=82)
    res.update({"kept": True, "corners": [[round(a, 6), round(b, 6)] for a, b in corners], "image": BASE + str(OUT / f"{slug}_conflicts.webp")})
    return res


def n_insets(r):
    """How many city insets a record names. A map not placed because its
    conflicts page has no picture keeps only the count (an int), not the list;
    len() of that stopped the run at mediterranean_basin (round 111b)."""
    c = r.get("cities")
    return c if isinstance(c, int) else len(c or [])


def main():
    deps()
    index = json.loads(INDEX.read_text()) if INDEX.exists() else {}
    cache_p = OUT / "geocode_cache.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    for pdf in sorted(PDFS.glob("*.pdf")):
        slug = pdf.stem
        if index.get(slug, {}).get("v") == METHOD and not os.environ.get("ATLAS_INSETS_AGAIN"):
            continue
        print(f"  {slug}", flush=True)
        try:
            index[slug] = do_one(slug, pdf, cache)
        except Exception as e:  # noqa: BLE001
            index[slug] = {"v": METHOD, "kept": False, "reason": f"could not be read ({e})"}
        r = index[slug]
        print(f"    {'placed' if r.get('kept') else 'not placed: ' + r.get('reason', '')}; {n_insets(r)} insets", flush=True)
        OUT.mkdir(parents=True, exist_ok=True)
        cache_p.write_text(json.dumps(cache, ensure_ascii=False))
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1))
    print(f"atlas_insets: {sum(1 for v in index.values() if v.get('kept'))} conflict maps placed, "
          f"{sum(n_insets(v) for v in index.values())} city insets")


if __name__ == "__main__":
    main()
