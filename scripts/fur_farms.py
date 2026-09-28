#!/usr/bin/env python3
"""
Fur farms worldwide, gathered from every public source found (round 94b, asked
27 September: the Final Nail map covers the United States only).

Sources, each kept as its own "source" on every farm it gives:
  1. Final Nail (finalnail.com), its WP Go Maps markers: United States.
  2. Farm Transparency Project (farmtransparency.org), its "Farm (skins/fur)"
     category, about 850 facilities in Denmark, the US, Spain, Canada, Sweden,
     Italy, Brazil, Argentina and more: each facility's own page gives its name,
     address, species, status and position. Only fur species are kept (mink,
     fox, chinchilla, rabbit, raccoon dog, sable, and entries naming fur or
     pelts); crocodile, alligator and ostrich skin farms are counted and left
     out, since the row is fur farms.
  3. OpenStreetMap (Overpass): places tagged as keeping mink, foxes,
     chinchillas or raccoon dogs, producing fur, or named as a mink or fur farm
     in the languages of the fur-farming countries.
  4. Poland: the antyfutro map of Polish fur farms (mapa.antyfutro.pl), from
     whatever data file its downloads page offers (KML or CSV), if it answers.
A farm given by two sources within 300 m is one farm, carrying both sources.

  fur/farms.geojson     every farm; group = where it came from first
  fur/countries.json    ISO3 -> each country's fur farming status (Our World
                        in Data's "fur-farming-ban", from the Fur Free
                        Alliance, CC BY 4.0), newest year
  fur/build.json        counts by source, and what each source answered

Weekly (Mondays), or by hand.
"""
import csv, datetime, html, io, json, math, os, pathlib, re, sys, time, urllib.parse, urllib.request, zipfile

OUT = pathlib.Path("fur")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
FUR = re.compile(r"\b(minks?|fox(es)?|chinchillas?|rabbits?|raccoon[ -]?dogs?|sables?|fur|pelts?|nutria|coypu|polecats?|ferrets?)\b", re.I)
NOT_FUR = re.compile(r"\b(crocodiles?|alligators?|ostrich(es)?|caimans?)\b", re.I)


def get(url, timeout=120, data=None):
    req = urllib.request.Request(url, headers=UA, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def final_nail(status):
    j = json.loads(get("https://finalnail.com/wp-json/wpgmza/v1/features/"))
    out = []
    for m in j.get("markers", []):
        try:
            lat, lng = float(m.get("lat")), float(m.get("lng"))
        except (TypeError, ValueError):
            continue
        desc = re.sub(r"<[^>]+>", " ", html.unescape(str(m.get("description") or ""))).strip()
        out.append({"lon": lng, "lat": lat, "name": m.get("title") or "", "address": m.get("address") or "",
                    "about": re.sub(r"\s+", " ", desc)[:400], "source": "Final Nail", "link": m.get("link") or "https://finalnail.com/"})
    status["Final Nail"] = f"{len(out)} farms"
    return out


def farm_transparency(status):
    page = get("https://www.farmtransparency.org/facilities/skin-fur-farms", timeout=180).decode("utf-8", "ignore")
    ids = list(dict.fromkeys(re.findall(r"(?:location=|/facilities/)([a-z0-9]{5})(?=[-\"'&?/])", page)))
    out, skins, nowhere = [], 0, 0
    for i, fid in enumerate(ids):
        try:
            t = get(f"https://www.farmtransparency.org/map?location={fid}", timeout=60).decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            print(f"  farm transparency {fid}: {e}", flush=True)
            continue
        text = re.sub(r"<[^>]+>", " ", html.unescape(t))
        text = re.sub(r"\s+", " ", text)
        # The position as the page's own map links give it (q=, ll=, query=,
        # destination= or @lat,lon), else the first coordinate pair written out.
        m = (re.search(r"(?:[?&](?:q|ll|query|destination|center)=|@)(-?\d{1,2}\.\d{3,})(?:,|%2C)\s*(-?\d{1,3}\.\d{3,})", t)
             or re.search(r"(-?\d{1,2}\.\d{4,})\s*,\s*(-?\d{1,3}\.\d{4,})", t))
        title = re.search(r"<title>([^<|]+)", t)
        name = html.unescape(title.group(1)).strip() if title else fid
        sp = re.search(r"Species:?\s*([A-Za-z ,/-]{3,80}?)(?:\s{2}|Last known|Status|Address|$)", text)
        species = sp.group(1).strip() if sp else ""
        st = re.search(r"Last known status:?\s*([A-Za-z ,/-]{3,60}?)(?:\s{2}|\.|$|Species|Address)", text)
        addr = re.search(r"Address:?\s*([^|]{5,160}?)(?:\s{2}|Species|Last known|Status|$)", text)
        words = f"{name} {species}"
        if NOT_FUR.search(species) and not FUR.search(species):
            skins += 1
            continue
        if not FUR.search(words) and species:
            skins += 1
            continue
        if not m:
            nowhere += 1
            continue
        lat, lon = float(m.group(1)), float(m.group(2))
        out.append({"lon": lon, "lat": lat, "name": name, "species": species, "status": st.group(1).strip() if st else "",
                    "address": addr.group(1).strip() if addr else "", "source": "Farm Transparency Project",
                    "link": f"https://www.farmtransparency.org/map?location={fid}"})
        if i % 50 == 49:
            print(f"  farm transparency: {i + 1} of {len(ids)} read", flush=True)
        time.sleep(0.4)
    status["Farm Transparency Project"] = f"{len(ids)} facilities listed; {len(out)} fur farms placed; {skins} skin farms of other animals left out; {nowhere} with no position"
    return out


OVERPASS = """[out:json][timeout:900];
(
  nwr["animal_keeping"~"mink|fox|chinchilla|raccoon_dog|sable|fur",i];
  nwr["animal"~"mink|fox|chinchilla|raccoon_dog|fur",i];
  nwr["produce"~"fur|pelt",i];
  nwr["name"~"mink ?farm|minkfarm|mink ranch|fur farm|pelsdyr|turkistarha|ferma norek|ferma lis|nertsenfokkerij|Nerzfarm|granja de vis|звероферм|зверохоз|pälsdjur|minkgård",i];
);
out center tags;"""


def osm(status):
    j = json.loads(get("https://overpass-api.de/api/interpreter", timeout=1000, data=urllib.parse.urlencode({"data": OVERPASS}).encode()))
    out = []
    for e in j.get("elements", []):
        c = e.get("center") or e
        if "lat" not in c:
            continue
        tg = e.get("tags", {})
        out.append({"lon": c["lon"], "lat": c["lat"], "name": tg.get("name", ""), "species": tg.get("animal_keeping") or tg.get("animal") or tg.get("produce") or "",
                    "address": ", ".join(tg[k] for k in ("addr:street", "addr:city", "addr:country") if tg.get(k)), "source": "OpenStreetMap",
                    "link": f"https://www.openstreetmap.org/{e['type']}/{e['id']}"})
    status["OpenStreetMap"] = f"{len(out)} places"
    return out


def poland(status):
    base = "http://mapa.antyfutro.pl/"
    page = get(base + "do-pobrania", timeout=60).decode("utf-8", "ignore")
    links = [urllib.parse.urljoin(base, h) for h in re.findall(r'href="([^"]+\.(?:kml|kmz|csv|geojson|json))"', page, re.I)]
    out = []
    for u in links:
        data = get(u, timeout=120)
        if u.lower().endswith(".kmz"):
            z = zipfile.ZipFile(io.BytesIO(data))
            data = z.read(next(n for n in z.namelist() if n.lower().endswith(".kml")))
        if u.lower().endswith((".kml", ".kmz")):
            for pm in re.findall(r"<Placemark>(.*?)</Placemark>", data.decode("utf-8", "ignore"), re.S):
                c = re.search(r"<coordinates>\s*(-?[\d.]+),(-?[\d.]+)", pm)
                n = re.search(r"<name>(.*?)</name>", pm, re.S)
                if c:
                    out.append({"lon": float(c.group(1)), "lat": float(c.group(2)), "name": html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", n.group(1))).strip() if n else "",
                                "source": "antyfutro (Poland)", "link": base})
        elif u.lower().endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(data.decode("utf-8", "ignore"))))
            for r in rows:
                la = next((r[k] for k in r if k and re.match(r"lat", k, re.I)), None)
                lo = next((r[k] for k in r if k and re.match(r"(lon|lng)", k, re.I)), None)
                try:
                    out.append({"lon": float(lo), "lat": float(la), "name": r.get("nazwa") or r.get("name") or "", "source": "antyfutro (Poland)", "link": base,
                                "about": "; ".join(f"{k}: {v}" for k, v in r.items() if v)[:400]})
                except (TypeError, ValueError):
                    pass
    status["antyfutro (Poland)"] = f"{len(links)} files, {len(out)} farms" if links else "no data file offered on its downloads page"
    return out


def countries(status):
    rows = list(csv.DictReader(io.StringIO(get("https://ourworldindata.org/grapher/fur-farming-ban.csv?v=1&csvType=full&useColumnShortNames=false").decode("utf-8"))))
    col = next(k for k in rows[0] if k not in ("Entity", "Code", "Year"))
    best = {}
    for r in rows:
        c = r.get("Code") or ""
        if len(c) != 3 or c.startswith("OWID"):
            continue
        if c not in best or int(r["Year"]) > int(best[c]["Year"]):
            best[c] = r
    out = {c: {"name": r["Entity"], "status": r[col], "year": int(r["Year"])} for c, r in best.items()}
    (OUT / "countries.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    status["Our World in Data (Fur Free Alliance)"] = f"{len(out)} countries; column {col}"


def km(a, b):
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b["lon"] - a["lon"]) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(min(1, h)))


def main():
    stamp = OUT / "build.json"
    if stamp.exists() and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("fur_farms: weekly; not Monday")
        return
    OUT.mkdir(exist_ok=True)
    status, farms = {}, []
    for name, job in (("Final Nail", final_nail), ("Farm Transparency Project", farm_transparency), ("OpenStreetMap", osm), ("antyfutro (Poland)", poland)):
        try:
            farms += job(status)
        except Exception as e:  # noqa: BLE001
            status[name] = f"did not answer ({type(e).__name__}: {e})"
        print(f"fur_farms: {name}: {status.get(name)}", flush=True)
    try:
        countries(status)
    except Exception as e:  # noqa: BLE001
        status["Our World in Data (Fur Free Alliance)"] = f"did not answer ({e})"
    merged = []
    grid = {}
    for f in farms:
        cell = (round(f["lat"], 2), round(f["lon"], 2))
        near = None
        for dy in (-0.01, 0, 0.01):
            for dx in (-0.01, 0, 0.01):
                for g in grid.get((round(cell[0] + dy, 2), round(cell[1] + dx, 2)), []):
                    if km(f, g) < 0.3:
                        near = g
        if near:
            if f["source"] not in near["sources"]:
                near["sources"].append(f["source"])
                near["links"].append(f.get("link", ""))
            for k in ("name", "species", "status", "address", "about"):
                if not near.get(k) and f.get(k):
                    near[k] = f[k]
            continue
        g = dict(f, sources=[f["source"]], links=[f.get("link", "")])
        merged.append(g)
        grid.setdefault(cell, []).append(g)
    feats = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(g["lon"], 6), round(g["lat"], 6)]},
              "properties": {"name": g.get("name") or "Fur farm", "group": g["sources"][0], "sources": ", ".join(g["sources"]),
                             "species": g.get("species", ""), "status": g.get("status", ""), "address": g.get("address", ""),
                             "about": g.get("about", ""), "links": " ".join(l for l in g["links"] if l)}} for g in merged]
    if not feats:
        sys.exit("fur_farms: no farm from any source; nothing written")
    (OUT / "farms.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))
    stamp.write_text(json.dumps({"read": datetime.date.today().isoformat(), "farms": len(feats), "by_source": status}, indent=1, ensure_ascii=False))
    print(f"fur_farms: {len(feats)} farms from {len(farms)} records")


if __name__ == "__main__":
    main()
