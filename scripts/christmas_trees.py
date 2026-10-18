#!/usr/bin/env python3
"""
Christmas tree farms and sellers, worldwide (round 102b, asked 28 September:
the Christmas trees row covered only the United States).

Two sources, merged:
  - the "Real Christmas Tree Locator" Google My Maps file the row read before
    (choose-and-cut farms in the United States), every placemark and field;
  - OpenStreetMap, every country: places tagged as growing or selling
    Christmas trees (produce, crop, trees or plant_nursery naming Christmas
    trees; xmas:feature:shop=christmas_tree) and places whose name says
    Christmas tree farm or Christmas tree in the languages below. Every tag of
    each is kept.
A place in both within 300 m is one place, its sources listed.

Each place's "group" says what it is, for the row's colours:
  "Christmas tree farm"            OSM tags or a name saying it grows them, and
                                   every My Maps farm
  "Place selling Christmas trees"  OSM xmas:feature:shop=christmas_tree, or a
                                   shop named for them
  "Other place named for Christmas trees"

  xmas/trees.geojson   xmas/build.json

Weekly (Mondays) or by hand.
"""
import datetime, html, json, math, os, pathlib, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

OUT = pathlib.Path("xmas")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
MYMAPS = "https://www.google.com/maps/d/kml?mid=1c-vPoGf79mfQezTgcFoKb-xN4A4&forcekml=1"
OVERPASS_URLS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
                 "https://overpass.private.coffee/api/interpreter"]
NAMES = (r"christmas ?tree|xmas ?tree|weihnachtsb[äa]um|kerstbo(om|men)|sapins? de no[eë]l|juletr[æe]|julgran|joulukuus|"
         r"choin(ki|ek|ka)|[áa]rbol(es)? de navidad|alber[io] di natale|ёлочн|елочн|ялинк|vánoční strom|karácsonyfa|"
         r"árvore de natal|božićn[ae] drvc|pom de cr[ăa]ciun|jõulukuus|eglutė|ziemassvētku eglīt")
QUERIES = {
    "tags": f"""[out:json][timeout:900];
(
  nwr["produce"~"christmas",i];
  nwr["crop"~"christmas",i];
  nwr["trees"~"christmas",i];
  nwr["plant_nursery"~"christmas",i];
  nwr["xmas:feature:shop"~"christmas_tree|tree",i];
);
out center tags;""",
    "names": f"""[out:json][timeout:900];
(
  nwr["name"~"{NAMES}",i];
);
out center tags;""",
}
GROW = re.compile(r"farm|plantation|nursery|grow|baumschule|kwekerij|pépinière|plantage|gård|tila|plantacj|vivero|vivaio|ферма|питомник", re.I)


def get(url, timeout=300, data=None, headers=None):
    req = urllib.request.Request(url, headers=dict(UA, **(headers or {})), data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def overpass(query):
    last = None
    for u in OVERPASS_URLS:
        try:
            return json.loads(get(u, timeout=1000, data=urllib.parse.urlencode({"data": query}).encode(),
                                  headers={"Accept": "application/json, */*", "Content-Type": "application/x-www-form-urlencoded"}))
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"  {u}: {e}", flush=True)
            time.sleep(20)
    raise RuntimeError(f"no Overpass instance answered ({last})")


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    d = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(d))


def mymaps(status):
    raw = get(MYMAPS, 300)
    root = ET.fromstring(raw)
    ns = {"k": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    q = (lambda e, p: e.findall(f".//k:{p}", ns)) if ns else (lambda e, p: e.findall(f".//{p}"))
    title = next((t.text for t in (root.iter(f"{{{ns['k']}}}name") if ns else root.iter("name"))), "") or ""
    out = []
    for pm in q(root, "Placemark"):
        tag = lambda e, t: e.find(f"k:{t}", ns) if ns else e.find(t)
        c = pm.find(".//k:coordinates", ns) if ns else pm.find(".//coordinates")
        if c is None or not (c.text or "").strip():
            continue
        lon, lat = [float(x) for x in c.text.strip().split()[0].split(",")[:2]]
        props = {"name": (tag(pm, "name").text or "").strip() if tag(pm, "name") is not None else ""}
        d = tag(pm, "description")
        if d is not None and d.text:
            props["description"] = re.sub(r"\s+", " ", html.unescape(re.sub(r"<br\s*/?>", "; ", re.sub(r"<(?!br)[^>]+>", " ", d.text)))).strip()
        for dd in (pm.findall(".//k:Data", ns) if ns else pm.findall(".//Data")):
            v = dd.find("k:value", ns) if ns else dd.find("value")
            if v is not None and v.text:
                props[dd.get("name")] = v.text.strip()
        out.append({"lon": lon, "lat": lat, "props": props, "source": f"Google My Maps: {title or 'Real Christmas Tree Locator'}",
                    "group": "Christmas tree farm"})
    status["Google My Maps"] = f"{len(out)} placemarks ({title})"
    return out


def osm(status):
    seen, out = set(), []
    for name, qy in QUERIES.items():
        try:
            j = overpass(qy)
        except Exception as e:  # noqa: BLE001
            status[f"OpenStreetMap {name}"] = f"not read ({e})"
            continue
        n = 0
        for e in j.get("elements", []):
            key = f"{e['type']}/{e['id']}"
            c = e.get("center") or e
            if key in seen or "lat" not in c:
                continue
            seen.add(key)
            tg = e.get("tags", {})
            words = " ".join(str(v) for v in tg.values())
            if tg.get("xmas:feature:shop") or tg.get("shop"):
                group = "Place selling Christmas trees" if not GROW.search(words) or tg.get("xmas:feature:shop") else "Christmas tree farm"
            elif name == "tags" or GROW.search(words) or tg.get("landuse") in ("plant_nursery", "farmland", "orchard", "forest"):
                group = "Christmas tree farm"
            else:
                group = "Other place named for Christmas trees"
            out.append({"lon": c["lon"], "lat": c["lat"], "props": dict(tg, osm=f"https://www.openstreetmap.org/{key}"),
                        "source": "OpenStreetMap", "group": group})
            n += 1
        status[f"OpenStreetMap {name}"] = f"{n} places"
    return out


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("christmas_trees: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    status, places = {}, []
    for label, job in (("Google My Maps", mymaps), ("OpenStreetMap", osm)):
        try:
            places += job(status)
        except Exception as e:  # noqa: BLE001
            status[label] = f"not read ({e})"
            print(f"christmas_trees: {label}: {e}", flush=True)
    if not places:
        raise SystemExit(f"christmas_trees: nothing read ({status})")
    merged = []
    cells = {}
    for p in places:
        cell = (round(p["lat"], 1), round(p["lon"], 1))
        near = [m for dx in (-0.1, 0, 0.1) for dy in (-0.1, 0, 0.1) for m in cells.get((round(cell[0] + dy, 1), round(cell[1] + dx, 1)), [])]
        hit = next((m for m in near if m["source"] != p["source"] and km((m["lon"], m["lat"]), (p["lon"], p["lat"])) < 0.3), None)
        if hit:
            hit["also"].append(p)
            continue
        p["also"] = []
        merged.append(p)
        cells.setdefault(cell, []).append(p)
    feats = []
    for m in merged:
        props = {"name": m["props"].get("name") or m["props"].get("name:en") or "", "group": m["group"],
                 "sources": "; ".join([m["source"]] + [a["source"] for a in m["also"]])}
        for k, v in m["props"].items():
            props.setdefault(k, v)
        for a in m["also"]:
            for k, v in a["props"].items():
                props.setdefault(f"{a['source']}: {k}", v)
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(m["lon"], 5), round(m["lat"], 5)]}, "properties": props})
    (OUT / "trees.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    groups = {}
    for f in feats:
        groups[f["properties"]["group"]] = groups.get(f["properties"]["group"], 0) + 1
    stamp.write_text(json.dumps({"sources": status, "places": len(feats), "read": len(places), "groups": groups,
                                 "date": datetime.date.today().isoformat()}, indent=1, ensure_ascii=False))
    print(f"christmas_trees: {len(feats)} places ({status})")


if __name__ == "__main__":
    main()
