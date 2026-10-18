#!/usr/bin/env python3
"""
The pet food industry, worldwide, as far as Wikidata records it (round 114b,
asked 29 September: the pet food row, "43 U.S. pet food companies", "doesn't
map the whole industry").

Read from Wikidata (CC0), weekly: every organisation whose industry is pet
food (or dog food, cat food, animal feed for pets: any narrower kind), every
one whose products include them, and every item that is a pet food brand or
company. The kinds are found by their English names and listed in
petfood/build.json. Placed at the item's own coordinates, its headquarters,
its location or its country, as its box says; the owner of a brand is named.

  petfood/companies.geojson
  petfood/build.json

Weekly (Mondays) or by hand.
"""
import datetime, json, os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import wdtools as W  # noqa: E402

OUT = pathlib.Path("petfood")
PRODUCTS = ["pet food", "dog food", "cat food"]
KINDS = ["pet food brand", "pet food company", "pet food manufacturer"]


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("pet_food_world: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    prods, kinds = W.classes(PRODUCTS), W.classes(KINDS)
    print(f"pet_food_world: products {prods}; kinds {kinds}", flush=True)
    if not prods:
        sys.exit("pet_food_world: 'pet food' was not found in Wikidata by name")
    countries = W.country_points()
    items = {}
    ways = [("industry", prods, "wdt:P452"), ("makes", prods, "wdt:P1056"), ("is a", kinds, "wdt:P31")]
    for why, qids, prop in ways:
        if not qids:
            continue
        vals = " ".join(f"wd:{q}" for q in qids)
        rows = W.wikidata_places(f"VALUES ?k {{ {vals} }} ?item {prop} ?k.", extra_select="?kLabel ?ownerLabel",
                                 extra_where="OPTIONAL { ?item wdt:P127|wdt:P749 ?owner. }")
        print(f"  {why}: {len(rows)} rows", flush=True)
        for r in rows:
            q = W.qid(W.v(r, "item"))
            e = items.setdefault(q, {"r": r, "why": set(), "owners": set()})
            e["why"].add(f"{why} {W.v(r, 'kLabel')}")
            if W.v(r, "ownerLabel"):
                e["owners"].add(W.v(r, "ownerLabel"))
    feats, unplaced = [], []
    for q, e in items.items():
        r = e["r"]
        at, how = W.place_row(r, countries)
        name = W.v(r, "itemLabel") or q
        props = {"name": name, "what it is": W.v(r, "itemDescription"), "why it is here": "; ".join(sorted(e["why"])),
                 "owned by": "; ".join(sorted(e["owners"])), "headquarters": W.v(r, "hqLabel"), "country": W.v(r, "countryLabel"),
                 "website": W.v(r, "website"), "Wikipedia": W.v(r, "article"), "Wikidata": f"https://www.wikidata.org/wiki/{q}",
                 "placed at": how, "group": "Brand" if any("brand" in w for w in e["why"]) else "Company", "source": "Wikidata (CC0)"}
        props = {k: val for k, val in props.items() if val}
        if not at:
            unplaced.append(name)
            continue
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(at)}, "properties": props})
    (OUT / "companies.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    stamp.write_text(json.dumps({"date": datetime.date.today().isoformat(), "products": prods, "kinds": kinds, "items": len(items),
                                 "placed": len(feats), "not_placed": sorted(unplaced)}, indent=1, ensure_ascii=False))
    print(f"pet_food_world: {len(feats):,} placed of {len(items):,}")


if __name__ == "__main__":
    main()
