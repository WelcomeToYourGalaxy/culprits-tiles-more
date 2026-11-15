#!/usr/bin/env python3
"""
Google My Maps maps often store a place as an address rather than a position,
and Google looks the address up itself when it draws the map. Their map files
therefore carry no position for those places. This finds a position for each
such address once, through OpenStreetMap's address search (Nominatim, which
allows one request a second and asks that results be kept), and keeps them in

  mymaps/geocode_<map id>.json    {address: [longitude, latitude] or null}

Only addresses not looked up before are asked each run. The map in Culprits
still reads each map's own file live; it takes positions from here only for the
places that have none, and says so in their boxes.
"""
import html, json, os, pathlib, re, sys, time, urllib.parse, urllib.request

MAPS = ["1PwPKisRf73FPC6hTtZDCv2s_B6_x0Pk7", "1c-vPoGf79mfQezTgcFoKb-xN4A4",
        "1vrnqSW4cWWdnjz6cJ-qFMmd0zbJzYd6V", "1seBCggQGg1tcRYpqpZ5ZKJaxHs4"]
OUT = pathlib.Path(os.environ.get("MYMAPS_OUT", "mymaps"))
UA = "WelcomeToYourGalaxy-Culprits/1.0 (https://github.com/WelcomeToYourGalaxy/culprits)"
NOMINATIM = os.environ.get("NOMINATIM", "https://nominatim.openstreetmap.org/search")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


ADDR_FIELD = re.compile(r"^(full[ _]?)?(address|street|addr|city|town|state|province|region|zip|postal ?code|postcode|country|location)$", re.I)


def clean(t):
    t = re.sub(r"^<!\[CDATA\[|\]\]>$", "", (t or "").strip())
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def address_of(pm):
    """The place's address: its <address>, or else its address-like data fields
    (Address, City, State, Zip, Country ...) joined in the map's order. The
    Culprits map builds the same string (mymapsAddress in app.js)."""
    m = re.search(r"<address>(.*?)</address>", pm, flags=re.S)
    if m and clean(m.group(1)):
        return clean(m.group(1))
    parts = [clean(v) for k, v in re.findall(r'<Data name="([^"]*)">\s*(?:<displayName>.*?</displayName>\s*)?<value>(.*?)</value>', pm, flags=re.S)
             if ADDR_FIELD.match(clean(k))]
    return ", ".join(p for p in parts if p)


def addresses(kml):
    out, bare = [], []
    for pm in re.findall(r"<Placemark\b[^>]*>(.*?)</Placemark>", kml, flags=re.S):
        if re.search(r"<(Point|LineString|Polygon)\b", pm):
            continue
        a = address_of(pm)
        if a:
            out.append(a)
        else:
            bare.append(pm)
    if bare:
        names = sorted({clean(k) for pm in bare for k in re.findall(r'<Data name="([^"]*)"', pm)})
        print(f"    {len(bare)} places have no position and no address; their data fields: {names or 'none'}")
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tpath = OUT / "titles.json"
    titles = json.loads(tpath.read_text()) if tpath.exists() else {}
    for mid in MAPS:
        path = OUT / f"geocode_{mid}.json"
        cache = json.loads(path.read_text()) if path.exists() else {}
        try:
            kml = fetch(f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1")
        except Exception as e:  # noqa: BLE001
            print(f"  {mid}: map file could not be read ({e})", file=sys.stderr)
            continue
        # The map's own title, so the Culprits row can carry it before anyone
        # opens the layer.
        t = re.search(r"<Document>\s*<name>(.*?)</name>", kml, flags=re.S)
        if t:
            titles[mid] = clean(t.group(1))
        todo = [a for a in dict.fromkeys(addresses(kml)) if a not in cache]
        for a in todo:
            # The address as the map gives it; if nothing is found, the part after
            # the place's own name (town, region, country) is tried.
            hit = None
            for q in (a, " ".join(a.split()[-4:])):
                try:
                    res = json.loads(fetch(f"{NOMINATIM}?format=jsonv2&limit=1&q={urllib.parse.quote(q)}"))
                except Exception:  # noqa: BLE001
                    res = []
                time.sleep(1.1)
                if res:
                    hit = [round(float(res[0]["lon"]), 6), round(float(res[0]["lat"]), 6)]
                    break
            cache[a] = hit
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"mymaps {mid}: {len(todo)} new addresses looked up, {sum(1 for v in cache.values() if v)} placed of {len(cache)}")
    tpath.write_text(json.dumps(titles, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"mymaps: titles {titles}")


if __name__ == "__main__":
    main()
