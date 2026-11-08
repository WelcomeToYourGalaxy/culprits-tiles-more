#!/usr/bin/env python3
"""
Where Giga's map of every school in the world draws its schools from (round
104b, asked 28 September: the school row showed only countries, while Giga's
own map shows every school as a point).

Giga's map (maps.giga.global, UNICEF and ITU) draws its schools from vector
tiles its own service makes, open to other sites (giga-maps-backend,
proco/schools/api.py: SchoolTileRequestHandler, "Access-Control-Allow-Origin:
*"): /api/locations/schools/tiles/?z=Z&x=X&y=Y.mvt, one point per school with
its coverage and connectivity status. The service's address is written into
the map's own scripts when they are built, so it is read from them here, each
address found is tried, and the first that answers with a tile is written for
the Culprits map to use.

  giga/schools_tiles.json   {"tiles": "<address>?z={z}&x={x}&y={y}.mvt", "layer": "default", ...}

Daily; cheap.
"""
import datetime, json, pathlib, re, sys, urllib.parse, urllib.request

OUT = pathlib.Path("giga/schools_tiles.json")
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
KNOWN = ["https://uni-ooi-giga-backend-hjekcuagasashucv.a03.azurefd.net/", "https://uni-ooi-giga-maps-service.azurewebsites.net/"]
PATH = "api/locations/schools/tiles/"


def get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "")


def candidates():
    found = []
    try:
        page, _ = get("https://maps.giga.global/map")
        page = page.decode("utf-8", "replace")
        for src in re.findall(r'src="([^"]+\.js)"', page):
            js, _ = get(urllib.parse.urljoin("https://maps.giga.global/map", src), 120)
            for u in re.findall(r'https://[a-z0-9.-]+(?:azurefd\.net|azurewebsites\.net|giga\.global)/?', js.decode("utf-8", "replace")):
                found.append(u if u.endswith("/") else u + "/")
    except Exception as e:  # noqa: BLE001
        print(f"giga_schools: the map's scripts could not be read ({e})", flush=True)
    return list(dict.fromkeys(found + KNOWN))


def main():
    tried = {}
    for base in candidates():
        url = f"{base}{PATH}?z=2&x=2&y=1.mvt"
        try:
            body, ctype = get(url)
            tried[base] = f"{len(body)} bytes, {ctype}"
            if body and ("protobuf" in ctype or "vector-tile" in ctype or "octet" in ctype or body[:1] == b"\x1a"):
                OUT.parent.mkdir(exist_ok=True)
                OUT.write_text(json.dumps({"tiles": f"{base}{PATH}?z={{z}}&x={{x}}&y={{y}}.mvt", "layer": "default", "base": base,
                                           "tried": tried, "date": datetime.date.today().isoformat()}, indent=1))
                print(f"giga_schools: {base} answers ({len(body)} bytes)")
                return
        except Exception as e:  # noqa: BLE001
            tried[base] = str(e)
    OUT.parent.mkdir(exist_ok=True)
    (OUT.parent / "schools_tiles_failed.json").write_text(json.dumps({"tried": tried, "date": datetime.date.today().isoformat()}, indent=1))
    sys.exit(f"giga_schools: no address answered: {tried}")


if __name__ == "__main__":
    main()
