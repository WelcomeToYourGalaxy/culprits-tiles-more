#!/usr/bin/env python3
"""
Where each crop is grown, crop by crop (round 101b, asked 28 September: a crop
layer to go with the farm fields, and the crops that destroy the most nature
each on its own).

Source: IFPRI's Spatial Production Allocation Model, SPAM 2020
(www.mapspam.info/data, the global GeoTIFF downloads): for each of its 46
crops or crop groups, the physical area the crop is grown on in each square of
5 arc-minutes (about 9 km at the equator), all farming systems together (the
files whose names end _A.tif). Physical area is the land the crop stands on,
counted once however many harvests a year it gives. Version 2.2 is read if it
downloads, else version 2.0. The download's own read-me files are recorded in
spam/build.json, licence words and all.

Each crop's hectares are shown as a share of the square's whole area, in five
fixed steps, the same for every crop so crops can be compared:
under 1%, 1 to 5%, 5 to 10%, 10 to 25%, 25% or more. Every square with any of
the crop is drawn.

  tiles/spam_<code>.pmtiles          one per crop, zooms 0 to 5
  tiles/spam_coffee.pmtiles          arabica and robusta together
  tiles/crops_spam.choices.json      every crop, as one row's menu
  tiles/crop_<key>.choices.json      the crops that clear most forest, a row each
  spam/build.json                    files read, codes found, read-me text

Built once; SPAM_REBUILD=1 builds it again.
"""
import json, math, os, pathlib, re, sys, tempfile, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "lib"))
import pyramid  # noqa: E402

URLS = [
    ("2.2", "https://www.dropbox.com/scl/fi/ubus2gp4u09133trryaai/spam2020V2r2_global_physical_area.geotiff.zip?rlkey=5wzkn6dtyqq8g8i2xpy49f5wp&dl=1"),
    ("2.0", "https://www.dropbox.com/scl/fi/r1c4fmky9hhz97bhsvou4/spam2020V2r0_global_physical_area.geotiff.zip?rlkey=wdhsdftegjxakqox90cpoi5se&dl=1"),
]
OUT = pathlib.Path("spam")
TOP = 5
STEPS = [(1, "under 1%"), (5, "1 to 5%"), (10, "5 to 10%"), (25, "10 to 25%"), (None, "25% or more")]
# SPAM's crop codes in words (its own list); a code not here is shown as SPAM writes it.
NAMES = {
    "WHEA": "wheat", "RICE": "rice", "MAIZ": "maize (corn)", "BARL": "barley", "PMIL": "pearl millet", "SMIL": "small millet",
    "MILL": "millet", "SORG": "sorghum", "OCER": "other cereals", "POTA": "potato", "SWPO": "sweet potato", "YAMS": "yams",
    "CASS": "cassava", "ORTS": "other roots and tubers", "BEAN": "beans", "CHIC": "chickpeas", "COWP": "cowpeas",
    "PIGE": "pigeon peas", "LENT": "lentils", "OPUL": "other pulses", "SOYB": "soybeans", "GROU": "groundnuts",
    "CNUT": "coconut", "OILP": "oil palm", "SUNF": "sunflower", "RAPE": "rapeseed", "SESA": "sesame", "OOIL": "other oil crops",
    "SUGC": "sugarcane", "SUGB": "sugar beet", "COTT": "cotton", "OFIB": "other fibre crops", "ACOF": "arabica coffee",
    "RCOF": "robusta coffee", "COCO": "cocoa", "TEAS": "tea", "TOBA": "tobacco", "BANA": "banana", "PLNT": "plantain",
    "CITR": "citrus", "TROF": "other tropical fruit", "TEMF": "temperate fruit", "TOMA": "tomato", "ONIO": "onion",
    "VEGE": "other vegetables", "RUBB": "rubber", "REST": "other crops",
}
# The crops that clear the most forest and other wild land, each a row of its own.
OWN_ROWS = {"oilp": ["OILP"], "soyb": ["SOYB"], "coco": ["COCO"], "coffee": ["ACOF", "RCOF"], "sugc": ["SUGC"],
            "maiz": ["MAIZ"], "rice": ["RICE"], "cott": ["COTT"], "cnut": ["CNUT"]}


def key_for(ramp):
    return [[ramp[i], f"grown on {w} of the square"] for i, (_, w) in enumerate(STEPS)]


def codes_of(share):
    import numpy as np
    c = np.zeros(share.shape, np.uint8)
    c[share > 0] = 1
    for i, (edge, _) in enumerate(STEPS[:-1]):
        c[share >= edge] = i + 2
    return c


def main():
    done = pathlib.Path("tiles") / "crops_spam.choices.json"
    if done.exists() and not os.environ.get("SPAM_REBUILD"):
        print("mapspam: already built")
        return
    pyramid.need("rasterio")
    import numpy as np
    import rasterio
    work = pathlib.Path(tempfile.mkdtemp())
    z, version = None, None
    for v, url in URLS:
        try:
            z = pyramid.download(url, work / f"spam_{v}.zip", "mapspam")
            if not zipfile.is_zipfile(z):
                raise RuntimeError("not a zip file")
            version = v
            break
        except Exception as e:  # noqa: BLE001
            print(f"mapspam: version {v} could not be fetched ({e})", flush=True)
            z = None
    if not z:
        raise SystemExit("mapspam: no SPAM 2020 download could be fetched")
    zf = zipfile.ZipFile(z)
    names = zf.namelist()
    print(f"mapspam: version {version}, {len(names)} files, e.g. {names[:6]}", flush=True)
    readme = {}
    for n in names:
        if re.search(r"(read ?me|licen[cs]e|terms)", n, re.I) and n.lower().endswith((".txt", ".md", ".csv")):
            readme[n] = zf.read(n).decode("utf-8", "replace")[:6000]
        elif re.search(r"(read ?me|licen[cs]e|terms)", n, re.I):
            readme[n] = "(not text; kept by name only)"
    tifs = {}
    for n in names:
        m = re.search(r"_([A-Z]{4})_A\.tif$", n, re.I)
        if m:
            tifs[m.group(1).upper()] = n
    if not tifs:
        raise SystemExit(f"mapspam: no crop files ending _A.tif found; files: {names[:40]}")
    print(f"mapspam: {len(tifs)} crops: {sorted(tifs)}", flush=True)
    ramp = pyramid.RAMP5
    pal = {i + 1: pyramid.rgba(c, 235) for i, c in enumerate(ramp)}
    hectares, done_codes, keep, choices, own = {}, [], {}, [], {}
    area = None

    def read(code):
        path = work / pathlib.Path(tifs[code]).name
        with zf.open(tifs[code]) as src, open(path, "wb") as dst:
            while True:
                b = src.read(1 << 22)
                if not b:
                    break
                dst.write(b)
        with rasterio.open(path) as ds:
            a = ds.read(1).astype("float32")
            nod, t = ds.nodata, ds.transform
        path.unlink()
        if nod is not None:
            a[a == nod] = 0
        a[~np.isfinite(a) | (a < 0)] = 0
        return a, t.c, t.f, t.a

    def one(slug, a, west, north, res, parts, label):
        nonlocal area
        if area is None or area.shape != a.shape:
            lats = north - (np.arange(a.shape[0]) + 0.5) * res
            km = (111.32 * res) ** 2 * np.cos(np.radians(lats))
            area = np.repeat((km * 100)[:, None].astype("float32"), a.shape[1], axis=1)   # hectares in each square
        share = np.where(area > 0, a / area * 100, 0)
        out = pathlib.Path("tiles") / f"spam_{slug}.pmtiles"
        pyramid.build(codes_of(share), west, north, res, pal, out, TOP, how="max",
                      attribution="SPAM 2020, IFPRI (mapspam.info)", name=f"spam_{slug}",
                      meta={"version": version, "crops": parts, "hectares": float(a.sum())})
        return {"label": label, "archive": f"tiles/spam_{slug}.pmtiles", "key": key_for(ramp),
                "hint": f"{label}: the share of each square of about 9 km the crop is grown on, around 2020 (SPAM 2020, version {version})"}

    for code in sorted(tifs, key=lambda c: NAMES.get(c, c)):
        a, west, north, res = read(code)
        hectares[code] = float(a.sum())
        choices.append(one(code.lower(), a, west, north, res, [code], NAMES.get(code, code)))
        done_codes.append(code)
        if code in ("ACOF", "RCOF"):
            keep[code] = (a, west, north, res)
    if "ACOF" in keep and "RCOF" in keep:
        a, west, north, res = keep["ACOF"]
        choices.insert(0, one("coffee", a + keep["RCOF"][0], west, north, res, ["ACOF", "RCOF"], "coffee, arabica and robusta together"))
    pyramid.write_choices("crops_spam", choices)
    for slug, parts in OWN_ROWS.items():
        have = [c for c in parts if c in tifs]
        if not have:
            print(f"mapspam: no {parts} in this version; crop_{slug} not written", flush=True)
            continue
        src = f"tiles/spam_{slug if len(parts) > 1 else parts[0].lower()}.pmtiles"
        pick = next((c for c in choices if c["archive"].endswith(src)), None)
        if pick:
            pyramid.write_choices(f"crop_{slug}", [dict(pick)])
            own[slug] = have
    OUT.mkdir(exist_ok=True)
    (OUT / "build.json").write_text(json.dumps({"version": version, "files": len(names), "crops": done_codes,
                                                "hectares": {c: round(h) for c, h in hectares.items()},
                                                "own_rows": own, "readme": readme}, indent=1, ensure_ascii=False))
    print(f"mapspam: {len(done_codes)} crops written; own rows {sorted(own)}")


if __name__ == "__main__":
    main()
