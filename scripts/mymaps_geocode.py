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


def addresses(kml):
    out = []
    for pm in re.findall(r"<Placemark>(.*?)</Placemark>", kml, flags=re.S):
        if re.search(r"<(Point|LineString|Polygon)>", pm):
            continue
        m = re.search(r"<address>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</address>", pm, flags=re.S)
        if m and m.group(1).strip():
            out.append(re.sub(r"\s+", " ", html.unescape(m.group(1))).strip())
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for mid in MAPS:
        path = OUT / f"geocode_{mid}.json"
        cache = json.loads(path.read_text()) if path.exists() else {}
        try:
            kml = fetch(f"https://www.google.com/maps/d/kml?mid={mid}&forcekml=1")
        except Exception as e:  # noqa: BLE001
            print(f"  {mid}: map file could not be read ({e})", file=sys.stderr)
            continue
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


if __name__ == "__main__":
    main()
