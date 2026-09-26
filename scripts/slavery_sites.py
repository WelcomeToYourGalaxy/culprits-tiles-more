"""Brick kilns and artisanal mining sites, each kiln at its own place.

Written 26 September (round 58). The owner saw the brick kilns on a grid, some
of them over water. The anti-slavery map's points.json places each kiln group
at the reference point of the satellite picture it was found in: SentinelKilnDB
(Sustainability Lab, IIT Gandhinagar; CC BY-NC 4.0) is a set of 128 x 128 pixel
Sentinel-2 pictures at 10 m a pixel, each named after its centre
("lat_lon.png", as the dataset's own tile_processing.py makes them), with every
kiln in it drawn as a box. The pictures sit on a regular grid, so the points
did too, and a picture centred just off a coast put its kilns in the sea.

Here every kiln is placed at the centre of its own box: the picture's centre,
moved by the box's offset from the middle of the picture at 10 m a pixel. The
dataset does not say whether its pictures are cut in degrees or in metres, so
a kiln near the edge of a picture may be off by up to about 60 m; nearer the
middle, less. Kilns seen in two overlapping pictures (their boxes' centres
under 40 m apart, same kind) are one kiln.

The artisanal mining sites (IPIS, eastern DR Congo) are taken from the
anti-slavery map's points.json as they are, every field.

Writes tiles/slavery_sites.pmtiles (layer slavery_sites) and
tiles/slavery_sites.build.json. The kilns read from the dataset are kept in
slavery_sites/kilns.json.gz and read again only when the dataset changes.
What the dataset's rows look like is saved in probe/kilns/sample.json.
"""
import gzip, json, math, os, pathlib, re, shutil, subprocess, sys, tempfile, time, urllib.parse, urllib.request

ROW = "slavery_sites"
OUT = pathlib.Path(f"tiles/{ROW}.pmtiles")
STAMP = OUT.with_suffix(".build.json")
CACHE = pathlib.Path("slavery_sites/kilns.json.gz")
PROBE = pathlib.Path("probe/kilns/sample.json")
DATASET = "SustainabilityLabIITGN/SentinelKilnDB"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET}"
ROWS = "https://datasets-server.huggingface.co/rows?dataset={d}&config={c}&split={s}&offset={o}&length=100"
SPLITS_URL = "https://datasets-server.huggingface.co/splits?dataset={d}"
POINTS = "https://raw.githubusercontent.com/WelcomeToYourGalaxy/anti-slavery-map/main/points.json"
PX = 128            # picture size, pixels
M_PER_PX = 10.0     # metres a pixel
SAME_KILN_M = 40.0
UA = {"User-Agent": "Culprits atlas build (github.com/WelcomeToYourGalaxy)"}
LICENCE_KILNS = "SentinelKilnDB, Sustainability Lab IIT Gandhinagar (CC BY-NC 4.0)"


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


def get_json(url, tries=6, timeout=90):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            # The rows server answers 429 or 5xx when pressed; wait longer each time.
            time.sleep(min(120, 5 * 2 ** i))
    raise RuntimeError(f"{url}: {last}")


def dataset_version():
    try:
        return get_json(f"https://huggingface.co/api/datasets/{DATASET}", tries=3).get("sha")
    except Exception as e:
        print(f"  dataset version not read ({e})")
        return None


# ---- the dataset's rows ----------------------------------------------------

def picture_centre(row):
    """The picture's centre from its name ("lat_lon.png" or "lat,lon.png")."""
    for k, v in row.items():
        if isinstance(v, str):
            m = re.search(r"(-?\d{1,2}\.\d+)[_,](-?\d{1,3}\.\d+)(?:\.(?:png|txt|tif))?$", v.strip())
            if m and "name" in k.lower() or (m and k.lower() in ("image", "path", "file", "filename")):
                return float(m.group(1)), float(m.group(2)), v
    for k, v in row.items():
        if isinstance(v, dict) and isinstance(v.get("src") or v.get("path"), str):
            m = re.search(r"(-?\d{1,2}\.\d+)[_,](-?\d{1,3}\.\d+)\.(?:png|jpg|tif)", v.get("path") or v.get("src"))
            if m:
                return float(m.group(1)), float(m.group(2)), v.get("path") or v.get("src")
    return None


def label_lines(v):
    if v is None:
        return []
    if isinstance(v, list):
        out = []
        for x in v:
            out.extend(label_lines(x))
        return out
    s = str(v).strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            return label_lines(json.loads(s))
        except Exception:
            s = s.strip("[]")
    return [l for l in re.split(r"[\n;]+", s) if l.strip()]


def boxes(row):
    """Every kiln box in a row as (x, y) of its centre in pixels, and its kind.
    DOTA ("x1 y1 ... x4 y4 kind difficult") is read first, then YOLO OBB
    ("kind x1 y1 ... y4") and YOLO axis-aligned ("kind xc yc w h"); coordinates
    that are all 1 or less are fractions of the picture."""
    low = {re.sub(r"[^a-z]", "", str(k).lower()): v for k, v in row.items()}
    for key, kind in (("dotalabel", "dota"), ("yoloobblabel", "obb"), ("yoloaalabel", "aa"), ("label", "dota"), ("labels", "dota")):
        lines = label_lines(low.get(key))
        found = []
        for l in lines:
            t = l.replace(",", " ").split()
            nums, words = [], []
            for x in t:
                try:
                    nums.append(float(x))
                except ValueError:
                    words.append(x)
            if kind == "dota" and len(nums) >= 8:
                xs, ys = nums[0:8:2], nums[1:8:2]
                cls = words[0] if words else (str(int(nums[8])) if len(nums) > 8 else "")
            elif kind == "obb" and len(nums) >= 9:
                cls = words[0] if words else str(int(nums[0]))
                pts = nums[1:9] if not words else nums[0:8]
                xs, ys = pts[0::2], pts[1::2]
            elif kind == "aa" and len(nums) >= 5:
                cls = words[0] if words else str(int(nums[0]))
                xc, yc = (nums[1], nums[2]) if not words else (nums[0], nums[1])
                xs, ys = [xc], [yc]
            else:
                continue
            found.append((sum(xs) / len(xs), sum(ys) / len(ys), cls))
        if found:
            if all(x <= 1.0 and y <= 1.0 for x, y, _ in found):
                found = [(x * PX, y * PX, c) for x, y, c in found]
            return found, key
    return [], None


CLASS_NAMES = {"0": "CFCBK", "1": "FCBK", "2": "Zigzag"}   # METAINFO in the dataset's plt_ann_on_img.py


def read_dataset():
    splits = get_json(SPLITS_URL.format(d=urllib.parse.quote(DATASET, safe="")))
    pairs = [(s["config"], s["split"]) for s in splits.get("splits", [])]
    print(f"  splits: {pairs}")
    kilns, pictures, sample, how = [], 0, [], {}
    for config, split in pairs:
        offset = 0
        while True:
            j = get_json(ROWS.format(d=urllib.parse.quote(DATASET, safe=""), c=config, s=split, o=offset))
            rows = j.get("rows") or []
            if not rows:
                break
            for w in rows:
                r = w.get("row") or {}
                plain = {k: v for k, v in r.items() if not isinstance(v, dict)}
                if len(sample) < 5:
                    sample.append({"config": config, "split": split, "fields": plain,
                                   "other_fields": {k: str(v)[:200] for k, v in r.items() if isinstance(v, dict)}})
                    # Saved at once, so a run that fails later still shows what the rows hold.
                    PROBE.parent.mkdir(parents=True, exist_ok=True)
                    PROBE.write_text(json.dumps({"rows": sample}, indent=1, ensure_ascii=False))
                c = picture_centre(r)
                if not c:
                    continue
                pictures += 1
                lat0, lon0, name = c
                found, key = boxes(r)
                how[key] = how.get(key, 0) + 1
                for x, y, cls in found:
                    dy_m = (PX / 2 - y) * M_PER_PX
                    dx_m = (x - PX / 2) * M_PER_PX
                    lat = lat0 + dy_m / 111320.0
                    lon = lon0 + dx_m / (111320.0 * max(0.05, math.cos(math.radians(lat0))))
                    kilns.append({"lat": round(lat, 6), "lon": round(lon, 6), "kind": CLASS_NAMES.get(cls, cls),
                                  "picture": os.path.basename(str(name)), "split": split,
                                  "box_x": round(x, 1), "box_y": round(y, 1)})
            offset += len(rows)
            if offset % 5000 < 100:
                print(f"    {split}: {offset} rows, {len(kilns)} kilns so far", flush=True)
            if len(rows) < 100:
                break
    PROBE.parent.mkdir(parents=True, exist_ok=True)
    PROBE.write_text(json.dumps({"read": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "pictures": pictures,
                                 "labels_read_from": how, "rows": sample}, indent=1, ensure_ascii=False))
    return kilns, pictures


def one_per_kiln(kilns):
    """A kiln in two overlapping pictures is one kiln."""
    cell = SAME_KILN_M / 111320.0
    grid, kept = {}, []
    for k in kilns:
        gx, gy = int(k["lon"] / cell), int(k["lat"] / cell)
        dup = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for o in grid.get((gx + dx, gy + dy), []):
                    if o["kind"] != k["kind"]:
                        continue
                    dm = math.hypot((o["lat"] - k["lat"]) * 111320.0,
                                    (o["lon"] - k["lon"]) * 111320.0 * math.cos(math.radians(k["lat"])))
                    if dm < SAME_KILN_M:
                        o.setdefault("also_in", []).append(k["picture"])
                        dup = True
                        break
                if dup:
                    break
            if dup:
                break
        if not dup:
            grid.setdefault((gx, gy), []).append(k)
            kept.append(k)
    return kept


# ---- the map's file ---------------------------------------------------------

def feature(ident, name, lon, lat, url, licence, extra):
    props = {"id": ident, "source": ROW, "name": name, "value": None, "unit": "site", "year": None,
             "licence": licence, "url": url, "_count": 1}
    props.update({f"x_{k}": (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                  for k, v in extra.items() if v is not None and v != ""})
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


def main():
    version = dataset_version()
    kilns = None
    if CACHE.exists():
        try:
            c = json.loads(gzip.decompress(CACHE.read_bytes()))
            if version and c.get("version") == version:
                kilns = c["kilns"]
                print(f"  {len(kilns):,} kilns kept from the last read (dataset unchanged, {version})")
        except Exception as e:
            print(f"  kept kilns not read ({e})")
    if kilns is None:
        raw, pictures = read_dataset()
        kilns = one_per_kiln(raw)
        print(f"  {pictures:,} pictures, {len(raw):,} kiln boxes, {len(kilns):,} kilns once overlaps are joined")
        if not kilns:
            sys.exit("No kilns were read; the dataset's rows are described in probe/kilns/sample.json. Nothing changed.")
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(gzip.compress(json.dumps({"version": version, "kilns": kilns}, separators=(",", ":")).encode()))

    points = get_json(POINTS)
    mining = [r for r in points.get("projects", []) if r.get("source") != "kilns" and r.get("lat") is not None and r.get("lng") is not None]
    feats = []
    for r in mining:
        extra = {k: v for k, v in r.items() if k not in ("lat", "lng", "name", "url")}
        if r.get("precise") is False:
            extra["precision"] = "admin"
        feats.append(feature(f"{r.get('source')}:{r.get('name')}:{r['lat']},{r['lng']}", r.get("name") or r.get("type"),
                             float(r["lng"]), float(r["lat"]), r.get("url"), "IPIS open data (via the anti-slavery map)", extra))
    for i, k in enumerate(kilns):
        feats.append(feature(f"kiln:{k['picture']}:{i}", "Brick kiln", k["lon"], k["lat"], DATASET_URL, LICENCE_KILNS, {
            "type": "Brick kiln", "kiln_kind": k["kind"], "dataset": "SentinelKilnDB",
            "picture": k["picture"], "split": k["split"], "box_centre_px": f"{k['box_x']}, {k['box_y']}",
            "also_in_pictures": k.get("also_in"),
            "position": "The centre of the kiln's box in its satellite picture (128 x 128 pixels, 10 m a pixel); "
                        "within about 60 m. Sector infrastructure, not confirmed exploitation.",
        }))
    print(f"  {len(mining):,} mining sites, {len(kilns):,} kilns")
    tools()
    work = pathlib.Path(tempfile.mkdtemp())
    src = work / "in.geojsonl"
    with src.open("w") as f:
        for ft in feats:
            f.write(json.dumps(ft, ensure_ascii=False) + "\n")
    tmp = work / f"{ROW}.pmtiles"
    sh("tippecanoe", "-o", str(tmp), "--force", "-q", "-l", ROW, "--name", ROW, "-Z0", "-z12", "--full-detail=12",
       "--drop-rate=1", "--drop-densest-as-needed", "--preserve-input-order",
       "--attribution", f"{LICENCE_KILNS}; IPIS", str(src))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp), OUT)
    STAMP.write_text(json.dumps({"built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "kilns": len(kilns),
                                 "mining_sites": len(mining), "dataset_version": version}, indent=1))
    print(f"  wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
