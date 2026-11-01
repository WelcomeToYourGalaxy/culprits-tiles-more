#!/usr/bin/env python3
"""
Every school on Giga Maps by name and education level, from Giga's School
Location API (round 192o; Giga wrote on 12 October that the API is public, a
key is issued on request, weekly or monthly reads are enough, and asked for
attribution to Giga under a share-alike licence).

Needs the repository secret GIGA_API_KEY (passed in by refresh.yml). Without
it this writes giga/api/build.json saying so and stops.

Giga's own backend (unicef/giga-maps-backend, proco/schools) serves the list
at api/locations/schools-download/, one country at a time (country_id), in
pages, with the key in an "Api-Key" header. The first request is a probe: if
Giga answers with anything but schools, its answer is kept in build.json and
nothing else is asked.

  giga/api/<country id>.json      every school Giga lists for that country,
                                  every field it gives
  tiles/giga_named.pmtiles        every school, layer "schools"
  giga/api/build.json

Weekly (Mondays) or by hand; it goes on country by country where the last
run stopped.
"""
import datetime, json, os, pathlib, shutil, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
START, BUDGET = time.time(), 120 * 60
BASE = "https://uni-ooi-giga-backend-hjekcuagasashucv.a03.azurefd.net"
PATH = "/api/locations/schools-download/"
DIR = pathlib.Path("giga/api")
OUT = pathlib.Path("tiles/giga_named.pmtiles")
UA = "WelcomeToYourGalaxy Culprits map (welcometoyourgalaxy@gmail.com)"
LIMIT = 90 * 1024 * 1024


def get(url, key=None, timeout=180):
    h = {"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"}
    if key:
        h["Api-Key"] = key
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.read()


def countries():
    raw = None
    p = pathlib.Path("giga/countries.json")
    if p.exists():
        raw = json.loads(p.read_text()).get("countries")
    if not raw:
        raw = json.loads(get(BASE + "/api/v2/entities/countries/"))
    raw = raw.get("results", raw) if isinstance(raw, dict) else raw
    return [(c.get("id"), c.get("name"), c.get("iso3_format") or c.get("code")) for c in raw if isinstance(c, dict) and c.get("id") is not None]


def page(cid, n, key, size=1000):
    q = urllib.parse.urlencode({"country_id": cid, "page": n, "page_size": size, "expand": "country"})
    body = get(f"{BASE}{PATH}?{q}", key)
    j = json.loads(body)
    rows = j.get("results", j.get("data")) if isinstance(j, dict) else j
    return rows if isinstance(rows, list) else None, j


def build_tiles(status):
    feats = DIR / "schools.geojsonl"
    n = 0
    with open(feats, "w") as out:
        for f in sorted(DIR.glob("*.json")):
            if f.name == "build.json":
                continue
            d = json.loads(f.read_text())
            for s in d.get("schools", []):
                g = s.get("geopoint") or {}
                xy = g.get("coordinates") if isinstance(g, dict) else None
                if not xy and s.get("longitude") is not None:
                    xy = [s.get("longitude"), s.get("latitude")]
                if not xy:
                    continue
                props = {k: v for k, v in s.items() if k != "geopoint" and not isinstance(v, (dict, list))}
                props["country"] = d.get("country")
                out.write(json.dumps({"type": "Feature", "geometry": {"type": "Point", "coordinates": xy[:2]}, "properties": props}, ensure_ascii=False) + "\n")
                n += 1
    if not n:
        return
    import mines
    mines.tools()
    for z in (11, 10, 9, 8):
        subprocess.run(["tippecanoe", "-o", str(OUT), "--force", "-l", "schools", "-Z0", f"-z{z}", "--drop-densest-as-needed",
                        "--extend-zooms-if-still-dropping", "-q", str(feats)], check=True)
        if OUT.stat().st_size <= LIMIT:
            break
    status["tiles"] = {"schools": n, "max zoom": z, "MB": round(OUT.stat().st_size / 1e6, 1)}
    feats.unlink()


def main():
    DIR.mkdir(parents=True, exist_ok=True)
    stamp = DIR / "build.json"
    old = json.loads(stamp.read_text()) if stamp.exists() else {}
    key = os.environ.get("GIGA_API_KEY", "").strip()
    status = {"read": datetime.date.today().isoformat(), "credit": "Giga (UNICEF and ITU), shared under a share-alike licence as Giga asks",
              "done": old.get("done", {}), "refused": {}}
    if not key:
        status["waiting"] = "no GIGA_API_KEY secret yet: request a key on Giga Maps, add it as a repository secret and pass it in refresh.yml"
        stamp.write_text(json.dumps(status, indent=1))
        print("giga_api: no key yet; nothing read")
        return
    if old.get("complete") and datetime.date.today().weekday() != 0 and os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        print("giga_api: weekly; not Monday")
        return
    if old.get("complete"):
        status["done"] = {}
    cs = countries()
    status["countries"] = len(cs)
    # The probe: one small page; anything but a list of schools stops here.
    try:
        rows, j = page(cs[0][0], 1, key, 10)
        if rows is None:
            raise ValueError(f"no list of schools in the answer: {json.dumps(j)[:400]}")
    except Exception as e:  # noqa: BLE001
        body = e.read().decode("utf-8", "replace")[:500] if isinstance(e, urllib.error.HTTPError) else ""
        status["probe"] = {"refused": f"{type(e).__name__}: {e}"[:300], "answer": body}
        stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
        print(f"::warning::giga_api: Giga did not give schools for the key ({e}); see giga/api/build.json")
        return
    status["probe"] = {"ok": True, "fields": sorted(rows[0].keys()) if rows else []}
    for cid, name, iso in cs:
        if str(cid) in status["done"]:
            continue
        if time.time() - START > BUDGET:
            status["waiting"] = "time budget spent; the next run goes on"
            break
        schools, n = [], 1
        try:
            while True:
                rows, _ = page(cid, n, key)
                if not rows:
                    break
                schools += rows
                if len(rows) < 1000:
                    break
                n += 1
                time.sleep(0.3)
        except Exception as e:  # noqa: BLE001
            status["refused"][str(cid)] = f"{name}: {type(e).__name__}: {e}"[:300]
            continue
        (DIR / f"{cid}.json").write_text(json.dumps({"country": name, "iso3": iso, "schools": schools}, ensure_ascii=False))
        status["done"][str(cid)] = {"country": name, "schools": len(schools)}
        stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    status["complete"] = len(status["done"]) >= len(cs) - len(status["refused"]) and "waiting" not in status
    if status["complete"] or not OUT.exists():
        build_tiles(status)
    stamp.write_text(json.dumps(status, indent=1, ensure_ascii=False))
    print(f"giga_api: {len(status['done'])} of {len(cs)} countries read; {sum(v['schools'] for v in status['done'].values()):,} schools")


if __name__ == "__main__":
    main()
