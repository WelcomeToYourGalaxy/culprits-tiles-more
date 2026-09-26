#!/usr/bin/env python3
"""
The Atlas for the End of the World's 33 hotspot-city maps, laid on the Culprits
map where they belong (asked for 23 September).

The hotspot maps were placed from the town names printed in their PDFs
(culprits pipeline/atlas_plates.py). The city maps are pictures, not PDFs:
  https://atlas-for-the-end-of-the-world.com/images/hotspot_cities/<slug>.png
so their names are pixels. This reads the words off each picture (Tesseract
OCR), keeps those that could be place names, looks each up on OpenStreetMap
(Nominatim) near that city, and finds the placement most of them agree on:
random sets of three, at least MIN_AGREE names agreeing, the typical error no
more than 3% of the picture's width. A city whose names do not agree that well
is not placed, and its reason is written down; the map then keeps its old
behaviour for it (zoom to the city, the Atlas's page in the panel).

Writes:
  atlas/city_plates.json            per city: kept, corners (four lon/lat), error, names used or the reason
  atlas/city_plates/<slug>.webp     the picture, for the map to lay down
  atlas/city_geocode.json           the look-ups, kept so a rerun asks nothing twice

By hand only (Actions tab, "atlas_city_plates"). Nominatim is asked at most once a second.
"""
import io, json, math, os, pathlib, random, re, subprocess, sys, time, urllib.parse, urllib.request

CITIES = [["antananarivo", "Antananarivo, Madagascar"], ["auckland", "Auckland, New Zealand"], ["baku", "Baku, Azerbaijan"], ["bogota", "Bogotá, Colombia"], ["brasilia", "Brasília, Brazil"], ["cape_town", "Cape Town, South Africa"], ["chengdu", "Chengdu, China"], ["colombo", "Colombo, Sri Lanka"], ["dar_es_salaam", "Dar es Salaam, Tanzania"], ["davao", "Davao, Philippines"], ["durban", "Durban, South Africa"], ["esfahan", "Esfahan, Iran"], ["guadalajara", "Guadalajara, Mexico"], ["guayaquil", "Guayaquil, Ecuador"], ["hongknog_shenzhen_quangzhou", "Hongkong-Shenzhen-Guangzhou, China"], ["honolulu", "Honolulu, United States"], ["houston", "Houston, United States"], ["jakarta", "Jakarta, Indonesia"], ["lagos", "Lagos, Nigeria"], ["los_angeles", "Los Angeles, United States"], ["makassar", "Makassar, Indonesia"], ["mecca", "Mecca, Saudi Arabia"], ["mexico_city", "Mexico City, Mexico"], ["nairobi", "Nairobi, Kenya"], ["osaka", "Osaka, Japan"], ["perth", "Perth, Australia"], ["port-au-prince", "Port-au-Prince, Haiti"], ["rawalpindi", "Rawalpindi, Pakistan"], ["santiago", "Santiago, Chile"], ["sao_paulo", "São Paulo, Brazil"], ["sydney", "Sydney, Australia"], ["tashkent", "Tashkent, Uzbekistan"], ["tel_aviv", "Tel Aviv, Israel"]]
IMG = "https://atlas-for-the-end-of-the-world.com/images/hotspot_cities/{slug}.png"
POS = pathlib.Path("atlas/cities.json")          # the weekly look-up of each city's own position
OUT = pathlib.Path("atlas")
UA = {"User-Agent": "Culprits atlas (WelcomeToYourGalaxy) placing the Atlas for the End of the World's city maps"}
MIN_AGREE, MAX_ERROR_SHARE, TRIES, REACH_DEG = 4, 0.03, 4000, 1.5
NOT_PLACES = {"kilometers", "km", "miles", "legend", "urban", "growth", "projected", "projection", "protected", "area", "areas",
              "habitat", "species", "threatened", "biodiversity", "hotspot", "conflict", "remnant", "vegetation", "existing",
              "population", "roads", "road", "railroad", "railroads", "water", "river", "rivers", "lake", "ocean", "sea",
              "atlas", "end", "world", "city", "cities", "scale", "north", "source", "data", "map"}
R = 6378137.0
# Results made by an earlier way of placing are done again; bump when it changes.
METHOD = 2


def merc(lon, lat):
    lat = max(-85.0, min(85.0, lat))
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def unmerc(x, y):
    # A wild trial fit can put a corner far off the world; the exponent is held
    # in range so it reads as a pole instead of stopping the run (26 September:
    # "math range error" at Chengdu's neighbour stopped every city after it).
    return math.degrees(x / R), math.degrees(2 * math.atan(math.exp(max(-700.0, min(700.0, y / R)))) - math.pi / 2)


def km(a, b):
    (lon1, lat1), (lon2, lat2) = unmerc(*a), unmerc(*b)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, h)))


def fit(pairs):
    """Least squares picture (x, y) -> mercator (X, Y)."""
    import numpy as np
    A = np.array([[x, y, 1.0] for (x, y), _ in pairs])
    if np.linalg.matrix_rank(A) < 3:
        return None
    X = np.array([c[0] for _, c in pairs]); Y = np.array([c[1] for _, c in pairs])
    u = np.linalg.lstsq(A, X, rcond=None)[0]; v = np.linalg.lstsq(A, Y, rcond=None)[0]
    return tuple(u), tuple(v)


def ap(T, x, y):
    (a, b, c), (d, e, f) = T
    return a * x + b * y + c, d * x + e * y + f


def need():
    if subprocess.run(["which", "tesseract"], capture_output=True).returncode != 0:
        subprocess.run(["sudo", "apt-get", "update", "-qq"], check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "tesseract-ocr"], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pytesseract", "pillow", "numpy"], check=True)


def labels(img):
    """Words read off the picture, joined into lines, that could be place names: (text, x, y)."""
    import pytesseract
    from PIL import ImageOps
    # Three times the size, grey and stretched to full contrast; read as
    # scattered text (psm 11) and as blocks (psm 6), both kept. The first run
    # (23 September) read only 1 to 10 words a picture at twice the size.
    big = ImageOps.autocontrast(ImageOps.grayscale(img.resize((img.width * 3, img.height * 3))))
    lines = {}
    for mode in ("--psm 11", "--psm 6"):
        read_words(pytesseract.image_to_data(big, output_type=pytesseract.Output.DICT, config=mode), mode, lines)
    return lines_to_labels(lines)


def read_words(d, mode, lines):
    for i, w in enumerate(d["text"]):
        w = (w or "").strip()
        try:
            conf = float(d["conf"][i])
        except ValueError:
            conf = -1
        if not w or conf < 55:
            continue
        key = (mode, d["block_num"][i], d["par_num"][i], d["line_num"][i])
        l, t, wd, ht = d["left"][i] / 3, d["top"][i] / 3, d["width"][i] / 3, d["height"][i] / 3
        lines.setdefault(key, []).append((w, l, t, l + wd, t + ht))


def lines_to_labels(lines):
    out, seen = [], set()
    for words in lines.values():
        text = re.sub(r"\s+", " ", " ".join(w for w, *_ in words)).strip(" ,.;:-")
        if not (3 <= len(text) <= 40) or re.search(r"\d", text) or not re.match(r"[A-ZÀ-Þ]", text):
            continue
        if any(t.lower() in NOT_PLACES for t in re.split(r"[\s\-()]+", text) if t):
            continue
        x0 = min(w[1] for w in words); y0 = min(w[2] for w in words); x1 = max(w[3] for w in words); y1 = max(w[4] for w in words)
        name = text.title() if text.isupper() else text
        spot = (name.lower(), round((x0 + x1) / 40), round((y0 + y1) / 40))
        if spot in seen:
            continue            # the same words read by both modes
        seen.add(spot)
        out.append((name, (x0 + x1) / 2, (y0 + y1) / 2))
    return out


def lookup(name, centre, cache):
    key = f"{name}|{centre[0]:.2f},{centre[1]:.2f}"
    if key in cache:
        return cache[key]
    lon, lat = centre
    q = urllib.parse.urlencode({"q": name, "format": "json", "limit": 5, "bounded": 1,
                                "viewbox": f"{lon - REACH_DEG},{lat + REACH_DEG},{lon + REACH_DEG},{lat - REACH_DEG}"})
    time.sleep(1.1)
    try:
        with urllib.request.urlopen(urllib.request.Request("https://nominatim.openstreetmap.org/search?" + q, headers=UA), timeout=60) as r:
            got = json.loads(r.read())
        cache[key] = [[float(g["lon"]), float(g["lat"])] for g in got]
    except Exception as e:  # noqa: BLE001
        print(f"    {name}: look-up failed ({e})", flush=True)
        return []
    return cache[key]


def fit_north(pairs):
    """Picture -> mercator with north up and one scale: X = s*x + a, Y = -s*y + b."""
    import numpy as np
    A, B = [], []
    for (x, y), (X, Y) in pairs:
        A.append([x, 1, 0]); B.append(X)
        A.append([-y, 0, 1]); B.append(Y)
    s_, a, b = np.linalg.lstsq(np.array(A, float), np.array(B, float), rcond=None)[0]
    if s_ <= 0:
        return None
    return (s_, 0.0, a), (0.0, -s_, b)


def place_north(lbls, w, h, seed=1):
    """The city maps are drawn north up at one scale, so two names fix a placement
    and a third can check it: used where the free fit finds too few names."""
    usable = [l for l in lbls if l[3]]
    if len(usable) < 3:
        return None
    rng, best = random.Random(seed), None
    for _ in range(TRIES):
        pair = rng.sample(usable, 2)
        T = fit_north([((l[1], l[2]), merc(*rng.choice(l[3]))) for l in pair])
        if not T:
            continue
        span = km(ap(T, 0, 0), ap(T, w, 0))
        if not (3 < span < 800):
            continue
        reach = span * MAX_ERROR_SHARE * 2
        agree = []
        for name, x, y, cands in usable:
            d, c = min((km(ap(T, x, y), merc(*c)), c) for c in cands)
            if d <= reach:
                agree.append(((x, y), merc(*c), name))
        if not best or len(agree) > len(best[1]):
            best = (T, agree)
    if not best or len(best[1]) < 3:
        return None
    T = fit_north([(p, c) for p, c, _ in best[1]])
    if not T:
        return None
    span = km(ap(T, 0, 0), ap(T, w, 0))
    errs = [km(ap(T, *p), c) for p, c, _ in best[1]]
    rms = math.sqrt(sum(e * e for e in errs) / len(errs))
    if rms > span * MAX_ERROR_SHARE:
        return None
    corners = [unmerc(*ap(T, x, y)) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]
    return {"kept": True, "fit": "north up, one scale", "error_km": round(rms, 2), "width_km": round(span, 1),
            "names": sorted(n for _, _, n in best[1]), "corners": [[round(a, 6), round(b, 6)] for a, b in corners]}


def place(lbls, w, h, seed=0):
    usable = [l for l in lbls if l[3]]
    if len(usable) < 3:
        return {"kept": False, "reason": f"only {len(usable)} names read off the picture were found near the city"}
    rng, best = random.Random(seed), None
    for _ in range(TRIES):
        trio = rng.sample(usable, 3)
        T = fit([((l[1], l[2]), merc(*rng.choice(l[3]))) for l in trio])
        if not T:
            continue
        span = km(ap(T, 0, 0), ap(T, w, 0))
        if not (3 < span < 800):
            continue
        reach = span * MAX_ERROR_SHARE * 2
        agree = []
        for name, x, y, cands in usable:
            P = ap(T, x, y)
            d, c = min((km(P, merc(*c)), c) for c in cands)
            if d <= reach:
                agree.append(((x, y), merc(*c), name))
        if not best or len(agree) > len(best[1]):
            best = (T, agree)
    if not best or len(best[1]) < MIN_AGREE:
        return {"kept": False, "reason": f"only {len(best[1]) if best else 0} names agree on a placement (at least {MIN_AGREE} needed)"}
    T = fit([(p, c) for p, c, _ in best[1]])
    span = km(ap(T, 0, 0), ap(T, w, 0))
    errs = sorted(((km(ap(T, *p), c), n) for p, c, n in best[1]), reverse=True)
    rms = math.sqrt(sum(e * e for e, _ in errs) / len(errs))
    corners = [unmerc(*ap(T, x, y)) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]
    kept = rms <= span * MAX_ERROR_SHARE
    return {"kept": kept, "error_km": round(rms, 2), "width_km": round(span, 1), "names": sorted(n for _, n in errs),
            "corners": [[round(a, 6), round(b, 6)] for a, b in corners],
            **({} if kept else {"reason": f"typical error {rms:.1f} km is over 3% of the {span:.0f} km picture"})}


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("atlas_city_plates: by hand only")
        return
    need()
    from PIL import Image
    pos = json.loads(POS.read_text(encoding="utf-8")) if POS.exists() else {}
    cache_path = OUT / "city_geocode.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    (OUT / "city_plates").mkdir(parents=True, exist_ok=True)
    # Each city takes minutes (reading the names off its picture), more than a
    # job's time allows for all 33. The results are kept city by city and a
    # later run goes on from where the last stopped; ATLAS_PLATES_AGAIN=1 starts over.
    out_path = OUT / "city_plates.json"
    result = {} if os.environ.get("ATLAS_PLATES_AGAIN") or not out_path.exists() else json.loads(out_path.read_text(encoding="utf-8"))
    started = time.time()
    for slug, name in CITIES:
        if result.get(slug, {}).get("v") == METHOD:
            continue
        if time.time() - started > 140 * 60:
            print("atlas_city_plates: time is nearly up; the next run goes on from here", flush=True)
            break
        centre = pos.get(name)
        if not centre:
            result[slug] = {"kept": False, "reason": "the city's own position has not been looked up yet"}
            continue
        try:
            with urllib.request.urlopen(urllib.request.Request(IMG.format(slug=slug), headers=UA), timeout=120) as r:
                img = Image.open(io.BytesIO(r.read())).convert("RGB")
        except Exception as e:  # noqa: BLE001
            result[slug] = {"kept": False, "reason": f"the picture could not be read ({e})"}
            continue
        try:
            lbls = [(t, x, y, lookup(t, centre, cache)) for t, x, y in labels(img)]
            got = place(lbls, img.width, img.height)
            if not got.get("kept"):
                got = place_north(lbls, img.width, img.height) or got
        except Exception as e:  # noqa: BLE001
            lbls, got = [], {"kept": False, "reason": f"placing failed ({type(e).__name__}: {e})"}
        got["read"] = len(lbls)
        got["v"] = METHOD
        if got.get("kept"):
            img.save(OUT / "city_plates" / f"{slug}.webp", "WEBP", quality=82)
            got["image"] = f"https://welcometoyourgalaxy.github.io/culprits-tiles-more/atlas/city_plates/{slug}.webp"
        result[slug] = got
        print(f"atlas_city_plates: {name}: " + (f"placed, {len(got['names'])} names agree, typical error {got['error_km']} km on a {got['width_km']} km picture"
                                                if got.get("kept") else got.get("reason", "not placed")) + f" ({len(lbls)} names read)", flush=True)
        cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"atlas_city_plates: {sum(1 for v in result.values() if v.get('kept'))} of {len(CITIES)} placed")


if __name__ == "__main__":
    main()
