#!/usr/bin/env python3
"""
Copies of ArcGIS apps too heavy for the Culprits map to read live.

The map reads an ArcGIS app (web app or Experience Builder "experience") by
finding its web maps, their layers, and every feature of every layer. Materials
research (Material Research World Atlas, item 3ff82579637f4c7a96bd62d039ac3e00)
holds a US census-tract layer of some 84,000 shapes with many fields each,
which took minutes to read in the browser. This does the same reading here,
once a week, and publishes for each app:

  tiles/<row>.pmtiles            every feature of every layer, layer "places",
                                 each with k (its key), i (which ArcGIS layer),
                                 n (its name, as the app's popup titles it) and
                                 c (its colour, as the app's renderer gives it,
                                 toned as the map tones all ArcGIS colours).
                                 One file per zoom, listed in <row>.build.json,
                                 if one file would pass GitHub's limit.
  arcgis/<row>/manifest.json     the app's title and its layers: title, address,
                                 how many features, the app's own popup setup.
  arcgis/<row>/pieces/<hh>.json.gz   every field of every feature, keyed by k,
                                 in 256 pieces (FNV-1a, as map/app.js pieceOf).

Nothing is filtered: every feature the layers give is kept, every field. A
layer that will not answer is named in the manifest and the log.
"""
import gzip, json, os, pathlib, re, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request

APPS = {
    "arcgis_materialresearch": "3ff82579637f4c7a96bd62d039ac3e00",
}
AGOL = "https://www.arcgis.com/sharing/rest/content/items"
SHARDS = 256
MAXZOOM = 12
LIMIT = 95 * 1024 * 1024
WEEK = 7 * 24 * 3600
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}


def sh(*cmd, **kw):
    print("  $", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def tools():
    if shutil.which("tippecanoe"):
        return
    sh("sudo", "apt-get", "update", "-qq")
    sh("sudo", "apt-get", "install", "-y", "-qq", "libsqlite3-dev", "zlib1g-dev", "build-essential")
    d = tempfile.mkdtemp()
    sh("git", "clone", "--depth", "1", "https://github.com/felt/tippecanoe.git", d)
    sh("make", "-j4", cwd=d)
    sh("sudo", "make", "install", cwd=d)


def shard(key):
    """FNV-1a over the key, two hex digits; map/app.js pieceOf is the same."""
    h = 0x811C9DC5
    for b in str(key).encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return f"{h % SHARDS:02x}"


def text(url, data=None, tries=6):
    body = urllib.parse.urlencode(data).encode() if data else None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=UA), timeout=180) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))
            print(f"    no answer ({e}); again", flush=True)


def ask(url, data=None):
    out = json.loads(text(url, data))
    if isinstance(out, dict) and out.get("error"):
        raise RuntimeError(out["error"].get("message") or str(out["error"]))
    return out


# --- the same reading as map/app.js arcgisWebmapsOf / readArcgisApp ----------

def experience_ids(raw):
    try:
        j = json.loads(raw)
    except Exception:  # noqa: BLE001
        return []
    out = []

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("itemId"), str) and re.fullmatch(r"[0-9a-f]{32}", o["itemId"]) and \
                    re.search(r"WEB_MAP|WEB_SCENE|FEATURE|MAP_SERVICE", str(o.get("type") or ""), re.I):
                out.append(o["itemId"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(j.get("dataSources") if isinstance(j, dict) else None)
    return list(dict.fromkeys(out))


def webmaps_of(item, seen):
    if item in seen or len(seen) > 40:
        return []
    seen.add(item)
    info = ask(f"{AGOL}/{item}?f=json")
    if info.get("type") in ("Web Map", "Web Scene"):
        return [{"id": item, "title": info.get("title")}]
    if info.get("type") in ("Feature Service", "Map Service"):
        return [{"service": info.get("url"), "title": info.get("title")}]
    try:
        raw = text(f"{AGOL}/{item}/data?f=json")
    except Exception:  # noqa: BLE001
        raw = ""
    ids = experience_ids(raw) or [x for x in dict.fromkeys(re.findall(r"\b[0-9a-f]{32}\b", raw)) if x != item]
    out = []
    for i in ids:
        try:
            out += webmaps_of(i, seen)
        except Exception:  # noqa: BLE001
            pass
    return out


def layers_of(ops, out):
    for l in ops or []:
        if l.get("layers") and not l.get("url"):
            layers_of(l["layers"], out)
        elif l.get("url"):
            out.append(l)
    return out


def app_layers(item):
    info = ask(f"{AGOL}/{item}?f=json")
    maps = webmaps_of(item, set())
    if not maps:
        raise RuntimeError("no public web map found in this app")
    layers, skipped = [], []
    for wm in maps:
        if wm.get("service"):
            s = ask(f"{wm['service']}?f=json")
            layers += [{"url": f"{wm['service']}/{x['id']}", "title": x.get("name")} for x in s.get("layers") or []]
            continue
        d = ask(f"{AGOL}/{wm['id']}/data?f=json")
        for l in layers_of(d.get("operationalLayers"), []):
            u = l["url"].rstrip("/")
            if re.search(r"/(FeatureServer|MapServer)/\d+$", u):
                layers.append({"url": u, "title": l.get("title"), "popupInfo": l.get("popupInfo"), "layerDefinition": l.get("layerDefinition")})
            else:
                try:
                    s = ask(f"{u}?f=json")
                    for x in s.get("layers") or []:
                        layers.append({"url": f"{u}/{x['id']}", "title": f"{l.get('title')}: {x.get('name')}",
                                       "popupInfo": l.get("popupInfo"), "layerDefinition": l.get("layerDefinition")})
                except Exception as e:  # noqa: BLE001
                    skipped.append({"title": l.get("title"), "url": u, "why": str(e)})
    seen, unique = set(), []
    for l in layers:
        if l["url"] not in seen:
            seen.add(l["url"])
            unique.append(l)
    title = info.get("title") or (maps[0].get("title") if maps else "")
    return title, unique, skipped


def fill(template, a):
    return re.sub(r"\{([^}]+)\}", lambda m: "" if a.get(m.group(1)) is None else str(a.get(m.group(1))), str(template or ""))


def symbol_colour(ldef, a):
    r = ((ldef or {}).get("drawingInfo") or {}).get("renderer")
    if not r:
        return None
    sym = r.get("symbol")
    if r.get("uniqueValueInfos") and r.get("field1"):
        hit = next((u for u in r["uniqueValueInfos"] if str(u.get("value")) == str(a.get(r["field1"]))), None)
        sym = (hit or {}).get("symbol") or r.get("defaultSymbol") or sym
    c = (sym or {}).get("color")
    return "#" + "".join(f"{int(v):02x}" for v in c[:3]) if isinstance(c, list) and len(c) >= 3 else None


def soft(c, fallback):
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(c or "").strip())
    if not m:
        return str(c) if c else fallback
    n = int(m.group(1), 16)
    g = (0x7A, 0x75, 0x6C)
    return "#" + "".join(f"{round(v * 0.7 + g[i] * 0.3):02x}" for i, v in enumerate(((n >> 16) & 255, (n >> 8) & 255, n & 255)))


def features_of(url):
    """Every feature of a layer: its ids, then the features by id, 500 at a time."""
    meta = ask(f"{url}?f=json")
    oidf = meta.get("objectIdField") or next((f["name"] for f in meta.get("fields") or [] if f.get("type") == "esriFieldTypeOID"), "OBJECTID")
    ids = sorted(ask(f"{url}/query", {"where": "1=1", "returnIdsOnly": "true", "f": "json"}).get("objectIds") or [])
    step = max(50, min(int(meta.get("maxRecordCount") or 1000), 500))
    for a in range(0, len(ids), step):
        chunk = ids[a:a + step]
        j = ask(f"{url}/query", {"objectIds": ",".join(map(str, chunk)), "outFields": "*", "returnGeometry": "true",
                                 "outSR": "4326", "f": "geojson"})
        for f in j.get("features") or []:
            yield oidf, f
        if (a // step) % 20 == 0:
            print(f"    {min(a + step, len(ids)):,} of {len(ids):,}", flush=True)
    return


def build(row, item):
    stamp = pathlib.Path(f"tiles/{row}.build.json")
    if not os.environ.get("ARCGIS_REBUILD") and stamp.exists() and time.time() - stamp.stat().st_mtime < WEEK:
        print(f"{row}: built less than a week ago")
        return
    title, layers, skipped = app_layers(item)
    print(f"{row}: {title}: {len(layers)} layers", flush=True)
    work = pathlib.Path(tempfile.mkdtemp())
    staged = work / "pieces"
    staged.mkdir()
    streams, first = {}, {}

    def put(key, rec):
        hh = shard(key)
        if hh not in streams:
            fo = open(staged / f"{hh}.json.gz", "wb")
            streams[hh] = (fo, gzip.GzipFile(fileobj=fo, mode="wb", mtime=0, compresslevel=9))
            streams[hh][1].write(b"{")
            first[hh] = True
        gz = streams[hh][1]
        if not first[hh]:
            gz.write(b",")
        first[hh] = False
        gz.write(json.dumps(key).encode() + b":" + json.dumps(rec, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    lines = work / "places.geojsonl"
    listed, total = [], 0
    with open(lines, "w", encoding="utf-8") as fo:
        for i, l in enumerate(layers):
            n = 0
            try:
                for oidf, f in features_of(l["url"]):
                    a = f.get("properties") or {}
                    oid = a.get(oidf, f.get("id", n))
                    key = f"{i}:{oid}"
                    info = l.get("popupInfo")
                    name = fill(info.get("title"), a) if info and info.get("title") else (a.get("Name") or a.get("NAME") or a.get("name") or "")
                    put(key, {"i": i, "a": {k: v for k, v in a.items() if not re.match(r"shape", k, re.I)}})
                    if f.get("geometry"):
                        props = {"k": key, "i": i, "n": str(name)[:200], "c": soft(symbol_colour(l.get("layerDefinition"), a), "")}
                        if not props["c"]:
                            del props["c"]
                        fo.write(json.dumps({"type": "Feature", "geometry": f["geometry"], "properties": props},
                                            ensure_ascii=False, separators=(",", ":")) + "\n")
                    n += 1
            except Exception as e:  # noqa: BLE001
                print(f"  {l.get('title')}: would not answer ({e})", flush=True)
                skipped.append({"title": l.get("title"), "url": l["url"], "why": str(e)})
                continue
            print(f"  {l.get('title')}: {n:,} features", flush=True)
            total += n
            listed.append({"i": i, "title": l.get("title"), "url": l["url"], "features": n, "popupInfo": l.get("popupInfo")})
    for fo_, gz in streams.values():
        gz.write(b"}")
        gz.close()
        fo_.close()
    if not total:
        sys.exit(f"{row}: no layer answered; the last copy stays")

    tools()
    out = pathlib.Path(f"tiles/{row}.pmtiles")
    opts = ["-l", "places", "--name", row, "-r1", "--no-feature-limit", "--no-tile-size-limit",
            "--no-tiny-polygon-reduction", "--detect-shared-borders", "--preserve-input-order"]
    one = work / out.name
    sh("tippecanoe", "-o", str(one), "--force", "-q", "-Z0", f"-z{MAXZOOM}", *opts, str(lines))
    parts = []
    if one.stat().st_size <= LIMIT:
        parts = [{"file": out.name, "from": 0, "to": MAXZOOM, "_path": one}]
    else:
        print(f"  one file is {one.stat().st_size / 1e6:.0f} MB; one file per zoom instead", flush=True)
        one.unlink()
        for z in range(0, MAXZOOM + 1):
            name = out.name if z == 0 else f"{row}_z{z}.pmtiles"
            p = work / name
            sh("tippecanoe", "-o", str(p), "--force", "-q", f"-Z{z}", f"-z{z}", *opts, str(lines))
            if p.stat().st_size > LIMIT:
                # The run of 25 September: the Material Research atlas's zoom
                # 12 alone passed the limit. Every shape is already in the
                # zoom below at about 5 m precision (no shape is dropped at
                # any zoom: -r1 and no limits), and the map enlarges the last
                # zoom it has for closer views. So the copy stops a zoom early.
                if z >= 8:
                    print(f"  zoom {z} alone is {p.stat().st_size / 1e6:.0f} MB; the copy stops at zoom {z - 1}, drawn larger closer in", flush=True)
                    p.unlink()
                    break
                sys.exit(f"{row}: zoom {z} alone is over GitHub's limit; the last copy stays")
            parts.append({"file": name, "from": z, "to": z, "_path": p})

    home = pathlib.Path(f"arcgis/{row}")
    home.mkdir(parents=True, exist_ok=True)
    if (home / "pieces").exists():
        shutil.rmtree(home / "pieces")
    shutil.move(str(staged), str(home / "pieces"))
    for old in out.parent.glob(f"{row}_z*.pmtiles"):
        old.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    for p in parts:
        shutil.move(str(p.pop("_path")), str(out.parent / p["file"]))
        p["bytes"] = (out.parent / p["file"]).stat().st_size
    (home / "manifest.json").write_text(json.dumps({"item": item, "title": title, "layers": listed, "skipped": skipped,
                                                    "features": total}, ensure_ascii=False, indent=1))
    info = {"item": item, "title": title, "features": total, "layers": len(listed), "skipped": len(skipped), "points_merged": False}
    if len(parts) > 1:
        info["parts"] = parts
    stamp.write_text(json.dumps(info, indent=1))
    print(f"{row}: {total:,} features from {len(listed)} layers ({len(skipped)} would not answer), {len(parts)} tile file(s)")


def main():
    failed = []
    for row, item in APPS.items():
        try:
            build(row, item)
        except SystemExit as e:
            print(e, flush=True)
            failed.append(row)
        except Exception as e:  # noqa: BLE001
            print(f"{row}: {e}", flush=True)
            failed.append(row)
    if failed:
        sys.exit("arcgis copy: not built: " + ", ".join(failed))


if __name__ == "__main__":
    main()
