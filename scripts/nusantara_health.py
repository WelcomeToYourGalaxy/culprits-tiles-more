#!/usr/bin/env python3
"""
How each of Nusantara Atlas's map layers answers (round 101b, by hand; asked
28 September: several palm oil layers do not draw, draw slowly, or draw only
close in).

For every layer the atlas's two map servers list, and for each of four zooms
(2, 4, 6 and 8, the square over central Kalimantan), the picture the map asks
for is asked for too, and written down: how long it took, what came back (a
picture or an error), its size, and how much of it is drawn. Also each
layer's area and scale limits as the server's list states them, and the scale
limits in its style (GetStyles), since a style that stops at a scale is why a
layer can draw only close in.

  probe/nusantara/health.json

Round 129b: the first run asked every layer for the same square over
Kalimantan, so a layer whose data lies elsewhere (Rawa Singkil in Aceh,
Merauke and Papua in New Guinea) read as drawing nothing even if it draws.
Now each layer is also asked:
  "here"    the same four zooms centred on where its own data is: the first
            feature its WFS returns, else the middle of its stated area;
  "styles"  at zoom 8 there, with each style the server lists for it;
  "wfs"     how many features it holds and its first one's position (a
            layer with no features has nothing to draw anywhere).

Only the layers named below by default (the palm oil and plantation rows);
NUS_ALL=1 tries every layer.
"""
import io, json, math, os, pathlib, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

SERVERS = ["https://map.nusantara-atlas.org/geoserver/atlas-workspace-v3/wms",
           "https://map.nusantara-atlas.org/geoserver/atlas-workspace-v2/wms"]
UA = {"User-Agent": "Mozilla/5.0 (Culprits atlas build; welcometoyourgalaxy@gmail.com)"}
WANT = re.compile(r"millop|concessioniop|PlantationIOP|PlantationAll|PlantationSmallholder|AllExpansion|papua_expansion|"
                  r"plantation_established|rawasingkil|concessionhgu|concessionitp|socialforestry|sago|Coconut", re.I)
OUT = pathlib.Path("probe/nusantara")


def get(url, timeout=90):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.read(), r.headers.get("Content-Type", ""), time.time() - t0, None
    except Exception as e:  # noqa: BLE001
        return b"", "", time.time() - t0, str(e)


def bbox3857(z, lon=113.0, lat=0.5):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    R = 20037508.342789244
    size = 2 * R / n
    return (-R + x * size, R - (y + 1) * size, -R + (x + 1) * size, R - y * size)


def first_feature(base, name):
    """How many features the layer holds, and where its first one is."""
    wfs = base[:-3] + "wfs" if base.endswith("/wms") else base
    url = (f"{wfs}?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&typeNames={urllib.parse.quote(name)}"
           f"&count=1&outputFormat=application/json&srsName=EPSG:4326")
    body, ctype, dt, err = get(url, 120)
    if err:
        return {"error": err}
    try:
        j = json.loads(body)
    except Exception:  # noqa: BLE001
        return {"said": body.decode("utf-8", "replace")[:300]}
    rec = {"matched": j.get("numberMatched", j.get("totalFeatures")), "returned": len(j.get("features") or [])}
    f = (j.get("features") or [None])[0]
    pts = []
    def walk(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            pts.append(c[:2])
        elif isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
    if f and f.get("geometry"):
        walk(f["geometry"].get("coordinates"))
    if pts:
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        lon, lat = sum(xs) / len(xs), sum(ys) / len(ys)
        if abs(lon) <= 90 and abs(lat) > 90:   # written lat, lon
            lon, lat = lat, lon
        rec["at"] = [round(lon, 4), round(lat, 4)]
    return rec


def ask(base, layer, b, style=""):
    url = (f"{base}?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS={urllib.parse.quote(layer)}&STYLES={urllib.parse.quote(style)}&SRS=EPSG:3857"
           f"&BBOX={','.join(f'{v:.2f}' for v in b)}&WIDTH=512&HEIGHT=512&FORMAT=image/png&TRANSPARENT=true")
    body, ctype, dt, err = get(url, 90)
    r = {"seconds": round(dt, 1), "bytes": len(body), "type": ctype}
    if err:
        r["error"] = err
    elif "image" in ctype:
        r.update(drawn_share(body))
    else:
        r["said"] = body.decode("utf-8", "replace")[:400]
    return r


def drawn_share(png):
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(png)).convert("RGBA")
        a = im.getchannel("A")
        hist = a.histogram()
        total = sum(hist)
        return {"drawn": round(1 - hist[0] / total, 4), "faint": round(sum(hist[1:24]) / total, 4)}
    except Exception as e:  # noqa: BLE001
        return {"error": f"not a picture ({e})"}


def main():
    if os.environ.get("GITHUB_EVENT_NAME", "workflow_dispatch") != "workflow_dispatch":
        print("nusantara_health: by hand only")
        return
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pillow"], check=False)
    OUT.mkdir(parents=True, exist_ok=True)
    out = {}
    for base in SERVERS:
        raw, ct, dt, err = get(f"{base}?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0", 180)
        if err:
            out[base] = {"error": err}
            continue
        root = ET.fromstring(raw)
        ns = {"w": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
        q = (lambda e, t: e.find(f"w:{t}", ns)) if ns else (lambda e, t: e.find(t))
        for layer in root.iter(root.tag.replace("WMS_Capabilities", "Layer") if ns else "Layer"):
            nm = q(layer, "Name")
            if nm is None or list(layer.iter(layer.tag))[1:]:
                continue
            name = nm.text.split(":")[-1]
            if not os.environ.get("NUS_ALL") and not WANT.search(name):
                continue
            geo = q(layer, "EX_GeographicBoundingBox")
            box = {t: float(q(geo, t).text) for t in ("westBoundLongitude", "eastBoundLongitude", "southBoundLatitude", "northBoundLatitude")} if geo is not None else None
            rec = {"server": base, "bbox": box,
                   "min_scale": (q(layer, "MinScaleDenominator").text if q(layer, "MinScaleDenominator") is not None else None),
                   "max_scale": (q(layer, "MaxScaleDenominator").text if q(layer, "MaxScaleDenominator") is not None else None),
                   "styles": [s.text for s in layer.iter() if s.tag.endswith("Name") and s is not nm][:6], "zooms": {}}
            sld, _, _, e = get(f"{base}?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetStyles&LAYERS={urllib.parse.quote(nm.text)}", 60)
            rec["style_scales"] = sorted(set(re.findall(r"<(?:\w+:)?(M(?:in|ax)ScaleDenominator)>([^<]+)<", sld.decode("utf-8", "replace")))) if not e else e
            for z in (2, 4, 6, 8):
                b = bbox3857(z)
                url = (f"{base}?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS={urllib.parse.quote(nm.text)}&STYLES=&SRS=EPSG:3857"
                       f"&BBOX={','.join(f'{v:.2f}' for v in b)}&WIDTH=512&HEIGHT=512&FORMAT=image/png&TRANSPARENT=true")
                body, ctype, dt, err = get(url, 90)
                r = {"seconds": round(dt, 1), "bytes": len(body), "type": ctype}
                if err:
                    r["error"] = err
                elif "image" in ctype:
                    r.update(drawn_share(body))
                else:
                    r["said"] = body.decode("utf-8", "replace")[:400]
                rec["zooms"][z] = r
            rec["wfs"] = first_feature(base, nm.text)
            here = rec["wfs"].get("at")
            if not here and box and (box["eastBoundLongitude"] - box["westBoundLongitude"]) < 300:
                here = [(box["westBoundLongitude"] + box["eastBoundLongitude"]) / 2, (box["southBoundLatitude"] + box["northBoundLatitude"]) / 2]
            if here:
                rec["here_at"] = here
                rec["here"] = {z: ask(base, nm.text, bbox3857(z, here[0], max(-85, min(85, here[1])))) for z in (2, 4, 6, 8)}
                rec["styles_here"] = {st: ask(base, nm.text, bbox3857(8, here[0], max(-85, min(85, here[1]))), st).get("drawn") for st in rec["styles"]}
            out[f"{base.split('/')[-2]}:{name}"] = rec
            print(f"  {name}: " + "; ".join(f"z{z} {v.get('seconds')}s {v.get('drawn', v.get('error', v.get('said', '')[:40]))}" for z, v in rec["zooms"].items()), flush=True)
    (OUT / "health.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"nusantara_health: {len(out)} layers tried")


if __name__ == "__main__":
    main()
