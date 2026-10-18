#!/usr/bin/env python3
"""
The 33 hotspot cities of the Atlas for the End of the World, placed from their
names through OpenStreetMap's address search (the Atlas gives no coordinates).
Kept in atlas/cities.json as {name: [longitude, latitude]}; only names not yet
placed are looked up.
"""
import json, pathlib, time, urllib.parse, urllib.request

CITIES = ["Antananarivo, Madagascar", "Auckland, New Zealand", "Baku, Azerbaijan", "Bogot\u00e1, Colombia",
          "Bras\u00edlia, Brazil", "Cape Town, South Africa", "Chengdu, China", "Colombo, Sri Lanka",
          "Dar es Salaam, Tanzania", "Davao, Philippines", "Durban, South Africa", "Esfahan, Iran",
          "Guadalajara, Mexico", "Guayaquil, Ecuador", "Hongkong-Shenzhen-Guangzhou, China", "Honolulu, United States",
          "Houston, United States", "Jakarta, Indonesia", "Lagos, Nigeria", "Los Angeles, United States",
          "Makassar, Indonesia", "Mecca, Saudi Arabia", "Mexico City, Mexico", "Nairobi, Kenya", "Osaka, Japan",
          "Perth, Australia", "Port-au-Prince, Haiti", "Rawalpindi, Pakistan", "Santiago, Chile",
          "S\u00e3o Paulo, Brazil", "Sydney, Australia", "Tashkent, Uzbekistan", "Tel Aviv, Israel"]
# A name that is a region rather than one city is looked up by the city the Atlas names first.
QUERY = {"Hongkong-Shenzhen-Guangzhou, China": "Shenzhen, China"}
OUT = pathlib.Path("atlas/cities.json")
UA = "WelcomeToYourGalaxy-Culprits/1.0 (https://github.com/WelcomeToYourGalaxy/culprits)"


def main():
    have = json.loads(OUT.read_text()) if OUT.exists() else {}
    for name in CITIES:
        if have.get(name):
            continue
        q = QUERY.get(name, name)
        req = urllib.request.Request("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=" + urllib.parse.quote(q),
                                     headers={"User-Agent": UA})
        try:
            res = json.loads(urllib.request.urlopen(req, timeout=60).read())
            have[name] = [round(float(res[0]["lon"]), 5), round(float(res[0]["lat"]), 5)] if res else None
        except Exception:  # noqa: BLE001
            have[name] = None
        time.sleep(1.1)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(have, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"atlas cities: {sum(1 for v in have.values() if v)} of {len(CITIES)} placed")


if __name__ == "__main__":
    main()
