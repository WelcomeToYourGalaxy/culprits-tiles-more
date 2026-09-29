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
            out[f"{base.split('/')[-2]}:{name}"] = rec
            print(f"  {name}: " + "; ".join(f"z{z} {v.get('seconds')}s {v.get('drawn', v.get('error', v.get('said', '')[:40]))}" for z, v in rec["zooms"].items()), flush=True)
    (OUT / "health.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"nusantara_health: {len(out)} layers tried")


if __name__ == "__main__":
    main()
