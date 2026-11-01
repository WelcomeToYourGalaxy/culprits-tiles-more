#!/usr/bin/env python3
"""
Games rigged: match fixing, point shaving and spot-fixing in professional and
college sport, worldwide, as far as Wikidata records them (round 114b, asked
29 September: "those in professional and college sports found to have rigged
games in one way or another").

Read from Wikidata (CC0), weekly, four ways, each marked in the box:
  scandal   an item that is a match-fixing (point-shaving, spot-fixing ...)
            case or scandal, or a narrower kind of one;
  about     an item whose main subject is one of those;
  convicted a person or body Wikidata records as convicted of one of them;
  involved  a team, club, league or person Wikidata records as taking part
            in one of the scandals above (the scandal named in the box).
Recorded, not judged here: "involved" is what Wikidata records as taking part,
which is not always a finding against them; the box says which way each came.
Placed at the item's own coordinates, headquarters, location or country
(citizenship for a person), as the box says. The year is the scandal's date
where Wikidata gives one.

  fixing/cases.geojson   one point per item
  fixing/build.json      the kinds used (item numbers), counts, not placed

Weekly (Mondays) or by hand.
"""
import datetime, json, os, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import wdtools as W  # noqa: E402

OUT = pathlib.Path("fixing")
KINDS = ["match fixing", "match-fixing", "point shaving", "spot-fixing", "spot fixing", "match-fixing scandal", "match fixing scandal",
         "sports betting scandal", "fixed match"]
WHEN = "OPTIONAL { ?item wdt:P585|wdt:P580|wdt:P571 ?time. }"


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("sports_fixing: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    kinds = W.classes(KINDS)
    print(f"sports_fixing: kinds {kinds}", flush=True)
    if not kinds:
        sys.exit("sports_fixing: no match-fixing kind was found in Wikidata by name")
    vals = " ".join(f"wd:{q}" for q in kinds)
    countries = W.country_points()
    items = {}
    ways = [
        ("scandal", f"VALUES ?k {{ {vals} }} ?item wdt:P31 ?k.", "?kLabel ?time", WHEN),
        ("about", f"VALUES ?k {{ {vals} }} ?item wdt:P921 ?k.", "?kLabel ?time", WHEN),
        ("convicted", f"VALUES ?k {{ {vals} }} ?item wdt:P1399 ?k.", "?kLabel ?time", "OPTIONAL { ?item wdt:P569 ?born. }"),
        ("involved", f"VALUES ?k {{ {vals} }} ?ev wdt:P31 ?k. ?ev wdt:P710 ?item.", "?kLabel ?evLabel ?time",
         "OPTIONAL { ?ev wdt:P585|wdt:P580|wdt:P571 ?time. }"),
    ]
    for way, where, sel, extra in ways:
        try:
            rows = W.wikidata_places(where, extra_select=sel, extra_where=extra)
        except Exception as e:  # noqa: BLE001
            print(f"  {way}: not read ({e})", flush=True)
            continue
        print(f"  {way}: {len(rows)} rows", flush=True)
        for r in rows:
            q = W.qid(W.v(r, "item"))
            e = items.setdefault(q, {"r": r, "ways": set(), "cases": set(), "years": set()})
            e["ways"].add(way)
            if W.v(r, "evLabel"):
                e["cases"].add(W.v(r, "evLabel"))
            elif way in ("scandal", "about"):
                e["cases"].add(W.v(r, "kLabel"))
            m = re.match(r"^\+?(\d{4})-", W.v(r, "time"))
            if m:
                e["years"].add(int(m.group(1)))
    feats, unplaced = [], []
    say = {"scandal": "a match-fixing case in Wikidata", "about": "its main subject is match fixing",
           "convicted": "recorded as convicted of it", "involved": "recorded as taking part in a scandal"}
    for q, e in items.items():
        r = e["r"]
        at, how = W.place_row(r, countries)
        name = W.v(r, "itemLabel") or q
        props = {"name": name, "what it is": W.v(r, "itemDescription"), "how it is here": "; ".join(say[w] for w in sorted(e["ways"])),
                 "the case": "; ".join(sorted(e["cases"])), "year": min(e["years"]) if e["years"] else None,
                 "country": W.v(r, "countryLabel"), "Wikipedia": W.v(r, "article"), "Wikidata": f"https://www.wikidata.org/wiki/{q}",
                 "placed at": how, "group": ("Convicted" if "convicted" in e["ways"] else "A case or scandal" if e["ways"] & {"scandal", "about"} else "Involved in a case"),
                 "source": "Wikidata (CC0)"}
        props = {k: val for k, val in props.items() if val not in (None, "")}
        if not at:
            unplaced.append(name)
            continue
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": list(at)}, "properties": props})
    (OUT / "cases.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    stamp.write_text(json.dumps({"date": datetime.date.today().isoformat(), "kinds": kinds, "items": len(items), "placed": len(feats),
                                 "not_placed": sorted(unplaced)}, indent=1, ensure_ascii=False))
    print(f"sports_fixing: {len(feats):,} placed of {len(items):,}")


if __name__ == "__main__":
    main()
