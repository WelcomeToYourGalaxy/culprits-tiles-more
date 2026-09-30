#!/usr/bin/env python3
"""
Everyone in sports betting and the gambling around it, worldwide, as far as
Wikidata records them (round 114b, asked 29 September: "add to the sports
category ... any and all entities in sports gambling").

Read from Wikidata (CC0), weekly: every item that is a bookmaker or betting
company (or a narrower kind of one), and every organisation whose industry
Wikidata gives as sports betting, bookmaking, betting, online gambling or
gambling (or a narrower kind). The kinds are found by their English names and
listed in betting/build.json with their item numbers; nothing is left out
for looks. Each is placed at its own coordinates, its headquarters, its
location or its country's middle, as its box says.

  betting/entities.geojson   one point per organisation, every field read
  betting/build.json         the kinds used, counts, what could not be placed

Weekly (Mondays) or by hand.
"""
import datetime, json, os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import wdtools as W  # noqa: E402

OUT = pathlib.Path("betting")
INSTANCE = ["bookmaker", "betting company", "gambling company", "online gambling company", "sportsbook", "betting exchange"]
INDUSTRY = ["sports betting", "bookmaking", "betting", "online gambling", "gambling", "gambling industry", "sports betting industry"]


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("sports_betting: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    inst, ind = W.classes(INSTANCE), W.classes(INDUSTRY)
    print(f"sports_betting: kinds {inst}; industries {ind}", flush=True)
    if not inst and not ind:
        sys.exit("sports_betting: none of the kinds or industries was found in Wikidata by name")
    countries = W.country_points()
    items = {}
    for why, qids, prop in (("is a", inst, "wdt:P31"), ("works in", ind, "wdt:P452")):
        if not qids:
            continue
        vals = " ".join(f"wd:{q}" for q in qids)
        rows = W.wikidata_places(f"VALUES ?k {{ {vals} }} ?item {prop} ?k.", extra_select="?kLabel")
        print(f"  {why}: {len(rows)} rows", flush=True)
        for r in rows:
            q = W.qid(W.v(r, "item"))
            e = items.setdefault(q, {"r": r, "why": set()})
            e["why"].add(f"{why} {W.v(r, 'kLabel')}")
    feats, unplaced = [], []
    for q, e in items.items():
        r = e["r"]
        at, how = W.place_row(r, countries)
        name = W.v(r, "itemLabel") or q
        props = {"name": name, "what it is": W.v(r, "itemDescription"), "why it is here": "; ".join(sorted(e["why"])),
                 "headquarters": W.v(r, "hqLabel"), "country": W.v(r, "countryLabel"), "website": W.v(r, "website"),
                 "Wikipedia": W.v(r, "article"), "Wikidata": f"https://www.wikidata.org/wiki/{q}", "placed at": how,
                 "group": "bookmaker or betting company" if any(w.startswith("is a") for w in e["why"]) else "in the gambling industry",
                 "source": "Wikidata (CC0)"}
        props = {k: val for k, val in props.items() if val}
        if not at:
            unplaced.append(name)
            continue
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(at)}, "properties": props})
    (OUT / "entities.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    stamp.write_text(json.dumps({"date": datetime.date.today().isoformat(), "kinds": inst, "industries": ind, "items": len(items),
                                 "placed": len(feats), "not_placed": sorted(unplaced)}, indent=1, ensure_ascii=False))
    print(f"sports_betting: {len(feats):,} placed of {len(items):,}")


if __name__ == "__main__":
    main()
