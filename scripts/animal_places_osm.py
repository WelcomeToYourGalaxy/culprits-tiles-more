#!/usr/bin/env python3
"""
Animal breeding places and zoos and aquariums, worldwide, from OpenStreetMap
(round 114b, asked 29 September: the USDA list of breeders, dealers,
exhibitors and carriers is the United States alone; "make it a global
layer"; and "does the zoos layer cover aquariums and stuff too?").

  breeding/osm.geojson   every place OpenStreetMap tags animal_breeding=*
                         (farms, kennels, catteries, studs, hatcheries ...),
                         every tag kept; the kind of animal is the tag's value
  zoos/osm.geojson       every place tagged tourism=zoo or tourism=aquarium,
                         with its zoo=* kind (petting zoo, safari park,
                         wildlife park, aviary ...), every tag kept
  probe/zoos_kml.json    the Zoos row's own map (Google My Maps, "Zoos of
                         the World"): how many placemarks, and how many are
                         named as aquariums, sea life centres or the like

OpenStreetMap data (c) OpenStreetMap contributors, ODbL. Weekly (Mondays) or
by hand.
"""
import datetime, json, os, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import wdtools as W  # noqa: E402

BREEDING = """[out:json][timeout:900];
nwr["animal_breeding"];
out center tags;"""
ZOOS = """[out:json][timeout:900];
nwr["tourism"~"^(zoo|aquarium)$"];
out center tags;"""
KML = "https://www.google.com/maps/d/kml?mid=1seBCggQGg1tcRYpqpZ5ZKJaxHs4&forcekml=1"


def main():
    stamp = pathlib.Path("breeding/build.json")
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("animal_places_osm: weekly; not Monday")
        return
    status, failed = {"date": datetime.date.today().isoformat()}, []
    for name, q, path, grp in (("breeding", BREEDING, pathlib.Path("breeding/osm.geojson"), lambda t: f"breeding {t.get('animal_breeding', 'animals')}"),
                               ("zoos", ZOOS, pathlib.Path("zoos/osm.geojson"),
                                lambda t: "aquarium" if t.get("tourism") == "aquarium" else (t.get("zoo") or "zoo").replace("_", " "))):
        try:
            j = W.overpass(q)
            feats = W.osm_features(j.get("elements", []))
            for f in feats:
                t = f["properties"]
                t["group"] = grp(t)
                t.setdefault("name", t.get("name:en") or t["group"])
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
            kinds = {}
            for f in feats:
                kinds[f["properties"]["group"]] = kinds.get(f["properties"]["group"], 0) + 1
            status[name] = {"places": len(feats), "kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1]))}
            print(f"animal_places_osm: {name}: {len(feats):,}", flush=True)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name}: {e}")
            print(f"animal_places_osm: {name}: {e}", flush=True)
    try:
        kml = W.get(KML, timeout=120).decode("utf-8", "replace")
        names = [re.sub(r"<!\[CDATA\[|\]\]>", "", n).strip() for n in re.findall(r"<Placemark>[\s\S]*?<name>([\s\S]*?)</name>", kml)]
        folders = re.findall(r"<Folder>\s*<name>([\s\S]*?)</name>", kml)
        aq = [n for n in names if re.search(r"aquar|sea ?life|oceanar|marine|dolphin|ocean ?park|sealife|reef", n, re.I)]
        pathlib.Path("probe").mkdir(exist_ok=True)
        pathlib.Path("probe/zoos_kml.json").write_text(json.dumps({"date": status["date"], "placemarks": len(names), "folders": folders,
                                                                 "named_like_aquariums": len(aq), "examples": aq[:60]}, indent=1, ensure_ascii=False))
        status["zoos_kml"] = {"placemarks": len(names), "named_like_aquariums": len(aq)}
    except Exception as e:  # noqa: BLE001
        status["zoos_kml"] = f"not read ({e})"
    stamp.parent.mkdir(exist_ok=True)
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    if failed:
        sys.exit("animal_places_osm: " + "; ".join(failed))


if __name__ == "__main__":
    main()
