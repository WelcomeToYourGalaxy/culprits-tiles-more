"""Round 125b (asked 2 October: points for named culprits of water scarcity,
each one specifically linked by a source to causing it). Each case below was
checked against the source given; the words are this map's summary of it.
Each is placed at the named place by OpenStreetMap's Nominatim (the place,
not the exact well or plant), and says so. Weekly (Mondays) or by hand.
"""
import datetime, json, os, pathlib, time, urllib.parse, urllib.request

OUT = pathlib.Path("water")
UA = {"User-Agent": "Culprits atlas build (WelcomeToYourGalaxy; welcometoyourgalaxy@gmail.com)"}
CASES = [
    {"name": "BlueTriton Brands (Arrowhead; formerly Nestlé Waters North America)", "group": "Bottled water",
     "place": "Strawberry Canyon, San Bernardino National Forest, California, USA", "query": "Strawberry Creek, San Bernardino County, California",
     "what": "In September 2023 California's State Water Resources Control Board ordered the company to stop taking water at 10 of its 13 tunnels and boreholes in the San Bernardino National Forest, finding it held no water right there. Strawberry Creek feeds the Santa Ana River, a source of municipal water for about 750,000 people.",
     "year": 2023, "source": "https://www.waterboards.ca.gov/press_room/press_releases/2023/pr-bluetriton-ruling.html"},
    {"name": "Fondomonte Arizona (Almarai)", "group": "Farming for export",
     "place": "Butler Valley, La Paz County, Arizona, USA", "query": "Butler Valley, La Paz County, Arizona",
     "what": "In October 2023 Arizona's governor cancelled one of the company's state land leases in Butler Valley and said three more would not be renewed, over groundwater pumped without limit or charge to grow alfalfa shipped to feed dairy cattle in Saudi Arabia.",
     "year": 2023, "source": "https://www.ksat.com/news/national/2023/10/03/arizona-to-cancel-leases-allowing-saudi-owned-farm-access-to-states-groundwater/"},
    {"name": "Hindustan Coca-Cola Beverages (The Coca-Cola Company)", "group": "Soft drinks",
     "place": "Plachimada, Palakkad district, Kerala, India", "query": "Plachimada, Palakkad, Kerala",
     "what": "A Kerala government high-power committee found in 2010 that the bottling plant, drawing about 500,000 litres a day from borewells in a drought-prone area, had depleted the groundwater and polluted the village's water, and recommended Rs 216.26 crore in compensation. The plant closed in March 2004. The company disputes the committee's findings.",
     "year": 2010, "source": "https://www.downtoearth.org.in/environment/cocacola-asked-to-pay-rs-216-crore-44"},
]


def place(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        j = json.loads(r.read())
    time.sleep(1.2)
    return (float(j[0]["lon"]), float(j[0]["lat"])) if j else None


def main():
    if (OUT / "cases.geojson").exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("water_cases: weekly; not Monday")
        return
    feats, unplaced = [], []
    for c in CASES:
        try:
            at = place(c["query"])
        except Exception as e:  # noqa: BLE001
            at = None
            print(f"water_cases: {c['query']}: {e}")
        if not at:
            unplaced.append(c["name"])
            continue
        p = {k: v for k, v in c.items() if k != "query"}
        p["placed at"] = "the named place, by OpenStreetMap's Nominatim (not the exact site)"
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(at[0], 5), round(at[1], 5)]}, "properties": p})
    OUT.mkdir(exist_ok=True)
    (OUT / "cases.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    (OUT / "cases.build.json").write_text(json.dumps({"cases": len(CASES), "placed": len(feats), "not_placed": unplaced, "read": datetime.date.today().isoformat()}, indent=1))
    print(f"water_cases: {len(feats)} of {len(CASES)} placed")


if __name__ == "__main__":
    main()
