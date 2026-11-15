#!/usr/bin/env python3
"""
The banking dynasties map's missing cities (round 65, 26 September; the owner
said yes). The Suppression page's banking dynasties section lists, for each
family, the cities it worked from; its map plots a city only where its own
table (cityCoords) has a coordinate, so 11 family-city pairs were never
plotted: Bardi in Barcelona, Fugger in Innsbruck, Welser in Santo Domingo and
Caracas, Mitsui in Kyoto, Barings in Liverpool, Warburg and Hambros in
Stockholm, Hambros in Oslo, Yasuda in Yokohama and Kobe.

Each is placed at the city as OpenStreetMap gives it (Nominatim, the first
answer for the city and its country), drawn hollow in the family's colour,
and its box says it is placed at the city, not at a building. Read from
pages/banking_dynasties.html (the section itself) and added to
sitemaps/site_banking_dynasties.places.geojson and .boxes.json. Runs once;
a pair already added is left as it is.
"""
import hashlib, json, pathlib, re, sys, time, urllib.parse, urllib.request

PAGE = pathlib.Path("pages/banking_dynasties.html")
PLACES = pathlib.Path("sitemaps/site_banking_dynasties.places.geojson")
BOXES = pathlib.Path("sitemaps/site_banking_dynasties.boxes.json")
UA = {"User-Agent": "WelcomeToYourGalaxy Culprits map (welcometoyourgalaxy@gmail.com)"}
# The country each listed city is in, so the lookup finds that city.
COUNTRY = {"Barcelona": "Spain", "Innsbruck": "Austria", "Santo Domingo": "Dominican Republic", "Caracas": "Venezuela",
           "Kyoto": "Japan", "Liverpool": "United Kingdom", "Stockholm": "Sweden", "Oslo": "Norway",
           "Yokohama": "Japan", "Kobe": "Japan"}


def families(html):
    out = []
    for m in re.finditer(r'\{name: "([^"]+)", founded: (\d+),.*?decline: (\d+),.*?cities: \[([^\]]*)\]', html, re.S):
        out.append({"name": m.group(1), "founded": m.group(2), "decline": m.group(3), "cities": re.findall(r'"([^"]+)"', m.group(4))})
    i = html.find("const cityCoords")
    known = set(re.findall(r"'([^']+)':\s*\[", html[i:html.find("};", i)])) if i >= 0 else set()
    return out, known


def locate(city):
    q = f"{city}, {COUNTRY[city]}" if city in COUNTRY else city
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "jsonv2", "limit": 1})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        got = json.loads(r.read())
    time.sleep(1.2)
    return (float(got[0]["lon"]), float(got[0]["lat"]), got[0].get("display_name", "")) if got else None


def main():
    if not (PAGE.exists() and PLACES.exists() and BOXES.exists()):
        sys.exit("dynasty_cities: the page or the map's files are not here")
    fams, known = families(PAGE.read_text(encoding="utf-8"))
    places = json.loads(PLACES.read_text(encoding="utf-8"))
    boxes = json.loads(BOXES.read_text(encoding="utf-8"))
    have = {f["properties"].get("k") for f in places["features"]}
    colour = {}
    for f in places["features"]:
        colour.setdefault(f["properties"].get("n"), f["properties"].get("c"))
    added, missed = 0, []
    for fam in fams:
        for city in fam["cities"]:
            if city in known:
                continue
            k = hashlib.sha1(f"{fam['name']}|{city}|city".encode()).hexdigest()[:16]
            if k in have:
                continue
            try:
                at = locate(city)
            except Exception as e:  # noqa: BLE001
                missed.append(f"{fam['name']} in {city}: {e}")
                continue
            if not at:
                missed.append(f"{fam['name']} in {city}: OpenStreetMap found no such city")
                continue
            lon, lat, osm = at
            c = colour.get(fam["name"]) or "#6A5D6B"
            places["features"].append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                                       "properties": {"k": k, "c": "rgba(0,0,0,0)", "r": 6.0, "s": c, "w": 2, "o": 1, "n": fam["name"], "p": 1, "city_only": 1}})
            boxes["boxes"][k] = {"h": (f'<div style="min-width:150px"><div style="font-weight:600;font-size:13px;margin-bottom:4px">{fam["name"]}</div>'
                                       f'<div style="font-size:12px;margin-bottom:2px">{city}</div>'
                                       f'<div style="font-size:10px">{fam["founded"]}–{fam["decline"]}</div>'
                                       f'<div style="font-size:10px;margin-top:4px">Placed at the city: the page lists {city} among the family\'s cities '
                                       f'but gives it no coordinate, so its own map leaves it out. Position: OpenStreetMap\'s for {osm}.</div></div>')}
            added += 1
            print(f"  {fam['name']} in {city}: {lat:.4f}, {lon:.4f} ({osm})", flush=True)
    if added:
        PLACES.write_text(json.dumps(places, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        BOXES.write_text(json.dumps(boxes, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"dynasty_cities: {added} added" + (f"; not placed: {'; '.join(missed)}" if missed else ""))
    if missed and not added:
        sys.exit(1)


if __name__ == "__main__":
    main()
